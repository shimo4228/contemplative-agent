"""The skill store's exit: archive one skill, or say why it stayed (ADR-0097 D5).

Retiring a skill is a **move** into ``skills/.archive/``, never an unlink, so
restoring it is a plain ``mv``. Two callers share this module — the
``adopt-staged --archive-names`` batch and the single-file ``remove-skill``
command — and there is exactly one primitive underneath both.

Threat model (the archive half; the staged-write half stays in
:mod:`.adopt`). The exit reaches this code as ``--archive-names FILE`` or as
a ``remove-skill`` argument, and **nothing a staged file carries can name a
skill to archive**: not a reviewer's prose, not a ``supersedes`` field, not a
producer's suggestion. An adversary who owns ``.staged/`` therefore cannot
remove anything from the store; the worst they reach is the write they
already had. The one place a staged item influences an archive is the
*lineage stamp*: an operator-typed pairing may point an archived file's
``superseded_by:`` at a staged item's name. That rewrites the archived
file's frontmatter — adding a minimal block when it had none, announced at
the time — and reaches no path; a standalone archive is byte-identical.

Because it is a move, **both ends are containment-checked** with the same
``_target_inside_data_root`` predicate the write path uses
(:mod:`.store_paths`), and a symlinked source is refused outright rather
than relocated. It writes the destination before unlinking the source: an
interruption leaves a duplicate (recoverable) rather than a hole, which is
the whole point of an exit that "never deletes".

The module is split plan / apply. :func:`_plan_archive` decides everything
knowable without reading the file; :func:`_apply_archive_plan` is the only
function here that mutates anything, and it takes a plan and nothing else.
That is what lets a dry run, a prompt and a move agree by construction
rather than by three sets of checks kept in step by hand.
"""

from __future__ import annotations

import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import approval
from .approval import AuditSource
from .store_paths import (
    _archive_dir,
    _inside_archive,
    _resolved_or_self,
    _target_inside_data_root,
)

logger = logging.getLogger(__name__)


# Reason codes for a refused or half-finished archive. Every one of them also
# produces a nonzero exit at the caller (ADR-0075: a store that did not shrink
# must never read as a clean run), and every one names the skill it kept.
_ARCHIVE_REFUSED_MISSING = "ARCHIVE_REFUSED_MISSING"
_ARCHIVE_REFUSED_SYMLINK = "ARCHIVE_REFUSED_SYMLINK"
_ARCHIVE_REFUSED_OUTSIDE = "ARCHIVE_REFUSED_OUTSIDE"
_ARCHIVE_REFUSED_UNREADABLE = "ARCHIVE_REFUSED_UNREADABLE"
_ARCHIVE_REFUSED_JUST_ADOPTED = "ARCHIVE_REFUSED_JUST_ADOPTED"
# The destination resolves to the source, so the "move" would rewrite the one
# copy and then unlink it. Security review 2026-08-22 reproduced two spellings:
# `remove-skill .archive/old` (the name argument accepts a nested path, and
# `.archive/` is inside the skills dir), and an `.archive` symlinked back into
# the store. Both ended with the file gone, exit 0, and an audit row saying
# `approved` for a path that no longer existed.
_ARCHIVE_REFUSED_NOT_A_MOVE = "ARCHIVE_REFUSED_NOT_A_MOVE"
# A file already inside `.archive/` has no second exit. `--archive-names`
# cannot reach one (its store listing is a non-recursive glob); the
# `remove-skill` name argument can, so that handler says so by name.
_ARCHIVE_REFUSED_ALREADY_ARCHIVED = "ARCHIVE_REFUSED_ALREADY_ARCHIVED"
_ARCHIVE_SUCCESSOR_NOT_ADOPTED = "ARCHIVE_SUCCESSOR_NOT_ADOPTED"
_ARCHIVE_WRITE_FAILED = "ARCHIVE_WRITE_FAILED"
_ARCHIVE_SOURCE_LEFT_BEHIND = "ARCHIVE_SOURCE_LEFT_BEHIND"
# The move succeeded and its audit row did not reach disk. The only failure
# here where the store DID shrink, so it cannot be retried blindly and is not
# rolled back — putting the file back would delete from `.archive/`.
_ARCHIVE_UNRECORDED = "ARCHIVE_UNRECORDED"
# A paired archive whose destination the collision guard would rename. The
# survivor's ``supersedes:`` is fixed before the guard runs, so it would name
# ``.archive/old.md`` while the retirement landed at ``.archive/old-2.md`` —
# pointing a reader at an unrelated earlier retirement.
_ARCHIVE_REFUSED_LINEAGE_AMBIGUOUS = "ARCHIVE_REFUSED_LINEAGE_AMBIGUOUS"
# The archive directory cannot hold a file: it is a regular file, or a link
# out of the store. Knowable before the move, so the dry run checks it too.
_ARCHIVE_REFUSED_BAD_DESTINATION = "ARCHIVE_REFUSED_BAD_DESTINATION"
# ``approval._collision_free_path`` exhausted its 98 suffixes. It raises
# rather than returning, and `.archive/` is never pruned by design, so the
# collision space only grows — caught here so one name cannot kill the loop.
_ARCHIVE_REFUSED_NO_FREE_NAME = "ARCHIVE_REFUSED_NO_FREE_NAME"


@dataclass(frozen=True)
class _ArchiveResult:
    """Where an archived skill landed, or why it did not move.

    ``text`` is the exact string written to ``destination`` — the caller
    hashes it into ``audit.jsonl``, so a lineage stamp added on the way must
    be in it (same rule as the adopt path: the row describes the bytes on
    disk, not the bytes we started from).

    ``stray_copy`` is set on the one failure that still put bytes on disk:
    the copy landed but the source could not be unlinked. Seven of the eight
    refusals move nothing and so deserve no audit row; this one does, or the
    durable trail stays silent about a file appearing in the archive
    (security review 2026-08-22 LOW).
    """

    destination: Path | None = None
    text: str = ""
    reason: str | None = None
    detail: str = ""
    stray_copy: Path | None = None


def _same_archive_slot(intended: Path, final: Path) -> bool:
    """True when *final* is *intended* or *intended* with a collision suffix.

    ``remove-skill`` shows the INTENDED destination in its dry run and its
    prompt, before the content is read, while the guard that fixes the final
    path (``approval._collision_free_path``) runs after. What makes that
    preview honest is a property of the guard: it may append ``-N``, and it
    may never change directory or extension. That property was asserted in a
    comment; this is the same claim as a check, so a change to the guard's
    shape fails loudly here instead of silently making the preview a lie.
    """
    if final.parent != intended.parent or final.suffix != intended.suffix:
        return False
    if final.stem == intended.stem:
        return True
    return re.fullmatch(rf"{re.escape(intended.stem)}-\d+", final.stem) is not None


def _archive_destination_refusal(destination: Path, data_root: Path) -> str | None:
    """Why the archive cannot hold *destination*, or None. Knowable pre-move.

    Split out so the ``remove-skill`` dry run answers the same question the
    real invocation will (Codex P2 #2): the preview used to promise an archive
    that then failed with ``ARCHIVE_WRITE_FAILED`` because ``skills/.archive``
    was a regular file, or with ``ARCHIVE_REFUSED_OUTSIDE`` because it was a
    link out of the store. Only checks that need no file content, so it is
    safe to run before anything is read.
    """
    if not _target_inside_data_root(destination, data_root):
        return _ARCHIVE_REFUSED_OUTSIDE
    parent = destination.parent
    if parent.exists() and not parent.is_dir():
        return _ARCHIVE_REFUSED_BAD_DESTINATION
    return None


_ARCHIVE_KIND_ARCHIVE = "archive"  # a live store skill leaving for `.archive/`


_ARCHIVE_KIND_PURGE = "purge"  # the source already sits inside `.archive/`


@dataclass(frozen=True)
class _ArchivePlan:
    """One retirement, decided as far as it can be without reading the file.

    **Why this exists.** ``remove-skill`` shows a dry run and a prompt, then
    moves; those three used to reach their own verdicts from their own
    copies of the same checks, kept in step by hand. A plan is built once
    and :func:`_apply_archive_plan` takes *only* a plan — so the preview,
    the prompt and the move cannot read different inputs. That is the whole
    property; the rest is bookkeeping.

    ``source`` is the LITERAL path, never a resolved one. ``is_symlink()``
    on a resolved path is always False, so planning from the referent would
    make the symlink refusal a silent no-op, and ``unlink`` acts on the
    literal path anyway.

    ``destination_refusal`` is a **field, not a refusal**, and the asymmetry
    is deliberate: a bad archive slot forbids an archive, but ``--delete``
    never touches the slot and must still work when it is broken. Returning
    it as a plain refusal would newly fail that case.

    **Refusals learned here write no audit row**; refusals learned in apply
    do. Not an inconsistency — a plan is checked before the operator is
    asked anything, so there is no decision to record, while apply runs
    after a recorded decision. This is the load-bearing reason the split is
    safe (pinned by ``test_a_failed_archive_exits_nonzero_with_no_audit_row``).
    """

    source: Path
    data_root: Path
    superseded_by: str | None
    kind: str
    intended: Path
    destination_refusal: str | None


def _plan_archive(
    source: Path, *, data_root: Path, superseded_by: str | None
) -> _ArchivePlan | _ArchiveResult:
    """Everything about a retirement knowable without reading the file.

    Returns a refusal only for facts about the **source** — those forbid
    every retirement, ``--delete`` included. Facts about the destination
    ride on the plan (see :class:`_ArchivePlan`).

    A symlinked source is refused rather than relocated: moving the link
    would leave its referent in the store while the audit row claimed the
    skill had left, and resolving it instead would archive a file the
    operator did not name.

    Reads nothing, so it is safe to run before the dry run — which is the
    point. It is also why the preview never emits
    :data:`_ARCHIVE_REFUSED_UNREADABLE`.
    """
    if source.is_symlink():
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_SYMLINK)
    if not source.is_file():
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_MISSING)
    if not _target_inside_data_root(source, data_root):
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_OUTSIDE)
    intended = _archive_dir(data_root) / source.name
    return _ArchivePlan(
        source=source,
        data_root=data_root,
        superseded_by=superseded_by,
        kind=(_ARCHIVE_KIND_PURGE if _inside_archive(source, data_root) else _ARCHIVE_KIND_ARCHIVE),
        intended=intended,
        destination_refusal=_archive_destination_refusal(intended, data_root),
    )


def _archive_skill_file(
    source: Path, *, data_root: Path, superseded_by: str | None
) -> _ArchiveResult:
    """Plan, then apply. The batch caller's entry to the exit primitive."""
    plan = _plan_archive(source, data_root=data_root, superseded_by=superseded_by)
    if isinstance(plan, _ArchiveResult):
        return plan
    return _apply_archive_plan(plan)


def _apply_archive_plan(plan: _ArchivePlan) -> _ArchiveResult:
    """Move the planned skill into ``skills/.archive/``. The only mutation.

    Takes a plan and nothing else — that signature *is* the guarantee that
    the preview and the move agree, so do not add a ``source`` or
    ``data_root`` parameter back (pinned by
    ``test_a_plan_is_never_applied_with_a_different_source``).

    A move, not a delete, so **both ends are containment-checked** with
    ``_target_inside_data_root`` — the predicate the write path uses, which
    tests the resolved referent and the literal-path-with-resolved-parent
    because a read follows links and a rename does not. The source end was
    checked in the plan; the destination end is checked here, because it is
    only known once the collision guard has run.

    Writes the destination *before* unlinking the source. An interruption
    between the two leaves the same text in two places, which a human can
    reconcile; the other order leaves a hole, which is the one outcome an
    exit that "never deletes" must not produce. A failed unlink is reported
    as :data:`_ARCHIVE_SOURCE_LEFT_BEHIND` rather than swallowed — the store
    did not shrink, so the run must not read as success.

    Collisions inside the archive go through the same H5 guard as every other
    write (``approval._collision_free_path``): re-archiving identical content
    reuses the file, different content gets ``-2``. Overwriting would destroy
    an earlier retirement, i.e. exactly the deletion this directory exists to
    prevent. When that reuse makes the destination BE the source, the move is
    refused (``_ARCHIVE_REFUSED_NOT_A_MOVE``) — rewriting and then unlinking
    one path is the deletion, not a degenerate archive.

    The directory is created lazily here, on the first archive.
    """
    from ..core._io import write_restricted
    from ..core.text_utils import set_frontmatter_field, split_frontmatter

    source = plan.source
    data_root = plan.data_root
    superseded_by = plan.superseded_by

    # The source-side gates again, immediately before the read that follows
    # links and the unlink that does not. **A plan is a decision, not a
    # promise about the filesystem** — it is built before the dry run, and
    # ``remove-skill`` then blocks on an approval prompt, so between planning
    # and here the store can change. Swap the named file for a symlink out of
    # the store in that window and, without this, apply reads through the
    # link and copies foreign content into `.archive/` with an `approved`
    # row (reproduced 2026-08-25; found independently by code review and
    # security review, which is why it is closed rather than documented).
    #
    # The destination end was never trusted this way — it is re-checked below
    # after the collision guard — so this only makes the two ends symmetric.
    # The batch caller re-plans per item and never had the window; the fix
    # costs it one redundant stat.
    #
    # **What this restores, and what it does not.** It puts the window back to
    # what the pre-split code had: microseconds between this check and the
    # read below, rather than the whole prompt. It does NOT eliminate the
    # class — only an ``O_NOFOLLOW`` open reading from the fd would, the way
    # ``core/_io.write_restricted`` does on the write side
    # (T-WRITE-TMP-NOFOLLOW). That residue predates the split and is left as
    # found; closing it is a change to the read primitive, not to this seam.
    if source.is_symlink():
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_SYMLINK)
    if not source.is_file():
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_MISSING)
    if not _target_inside_data_root(source, data_root):
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_OUTSIDE)

    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_UNREADABLE, detail=str(err))

    # Both halves of an ADR-0097 supersede pair go through
    # ``core.text_utils.set_frontmatter_field`` with ``synthesize=True``: legacy
    # skills predate the emitted block, and a lineage pointer stapled above a bare
    # ``# Title`` would not be found by any frontmatter reader. The value is a
    # *filename*, not the frontmatter ``name:`` slug — a slug is only unique per
    # date (``slug_from_stem`` exists precisely because two files can share one),
    # whereas restoring an archived skill is a plain ``mv`` and a ``mv`` needs a
    # filename. Both halves are validated against real files before they are
    # stamped, so the scalar is never free text.
    if superseded_by:
        stamped = set_frontmatter_field(text, "superseded_by", superseded_by, synthesize=True)
        if not split_frontmatter(text)[0]:
            # The one case where archiving is not byte-preserving. Said out
            # loud: a standalone archive copies the file verbatim, and an
            # operator should not discover a rewrite by diffing the archive.
            print(
                f"  Adding a frontmatter block to {source.name} (it had none) "
                f"to carry superseded_by: {superseded_by}"
            )
        text = stamped
    # From the plan, not recomputed: the dry run and the prompt already
    # showed this destination, and deriving it a second time here is exactly
    # how the two would drift apart.
    intended = plan.intended
    if plan.destination_refusal:
        return _ArchiveResult(reason=plan.destination_refusal, detail=str(intended))
    try:
        destination = approval._collision_free_path(intended, text)
    except RuntimeError as err:
        # Escapes every frame otherwise, killing the loop before
        # ``_report_adopt_outcomes`` — no summary, remaining archives skipped,
        # applied ones unreported (code review 2026-08-22 LOW).
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_NO_FREE_NAME, detail=str(err))
    if not _target_inside_data_root(destination, data_root):
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_OUTSIDE)
    if not _same_archive_slot(intended, destination):
        # ``remove-skill`` already promised ``intended`` in its dry run and
        # its prompt, on the standing claim that the guard only ever appends
        # a counter. Checked rather than trusted: if that ever stops holding
        # the preview becomes a lie, and this is the one frame that can still
        # tell. Refused as OUTSIDE because a destination in an unexpected
        # directory is exactly the containment failure that name describes.
        return _ArchiveResult(
            reason=_ARCHIVE_REFUSED_OUTSIDE,
            detail=f"{destination} is not {intended} with a collision suffix",
        )
    if superseded_by and destination.name != source.name:
        # The survivor's ``supersedes:`` was fixed before this rename could be
        # known — it has to be inside the bytes the audit row hashes — so it
        # names ``source.name`` while the retirement would land beside an
        # unrelated earlier one. Refuse rather than write a pointer to the
        # wrong file; the operator moves the older retirement aside and
        # re-runs (silent-failure review 2026-08-22 MEDIUM 7).
        return _ArchiveResult(
            reason=_ARCHIVE_REFUSED_LINEAGE_AMBIGUOUS,
            detail=(
                f"{intended.name} is taken by different content, so the retirement "
                f"would land at {destination.name} while the survivor says "
                f"'supersedes: {source.name}'"
            ),
        )
    # The one check the containment predicate cannot make: both ends inside
    # the data root is satisfied when they are the SAME file, and then the
    # write-then-unlink below destroys the only copy. The H5 guard causes
    # this rather than catching it — "identical content reuses the path"
    # degenerates when the destination is the source. Resolved on both sides
    # so an `.archive` symlinked back into the store is caught too.
    if _resolved_or_self(destination) == _resolved_or_self(source):
        return _ArchiveResult(reason=_ARCHIVE_REFUSED_NOT_A_MOVE, detail=str(destination))

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        write_restricted(destination, text)
    except (OSError, ValueError) as err:
        return _ArchiveResult(text=text, reason=_ARCHIVE_WRITE_FAILED, detail=str(err))
    try:
        source.unlink()
    except OSError as err:
        return _ArchiveResult(
            text=text,
            reason=_ARCHIVE_SOURCE_LEFT_BEHIND,
            detail=f"{err}; the copy at {destination} is intact",
            stray_copy=destination,
        )
    return _ArchiveResult(destination=destination, text=text)


def _record_archive(
    result: _ArchiveResult, *, command: str, source_path: Path, source: AuditSource, reason: str
) -> bool:
    """Write the audit row for one finished archive attempt; True when it moved.

    Both call sites — the adopt gate and ``remove-skill`` — did these same
    four steps, and the two copies had already produced two sentences for one
    stray-copy event (code review 2026-08-22).

    **What tells an archive from a delete is ``source``, not ``path``.** The
    earlier claim (a path under ``.archive/`` means archived) was false and
    had a live consumer: ``remove-skill --delete`` on a file already in the
    archive writes an ``.archive/`` path while meaning the opposite, and the
    two rows were otherwise identical in command, decision, path, hash and
    run_id (silent-failure review 2026-08-22 HIGH). The categorical field is
    ``AuditSource`` — ``direct-archive*`` / ``stage-archived-names`` for a
    move, ``direct-remove*`` for a delete, ``direct-purge*`` for a purge from
    the archive — which grows the vocabulary without growing the row shape
    that ``_log_decision`` owns. The destination is still what gets logged
    for a move, because it names the file a ``mv`` would restore.

    **Every outcome writes a row**, including a refusal: the reason codes are
    the point of ADR-0075, and a refused archive that logs nothing is
    indistinguishable from a command that never ran. Only a move writes
    ``approved``; a refusal writes not-approved carrying its code, and a
    stray copy is named as the path so the leftover bytes are findable.

    Returns True only when the skill actually left the store **and** the row
    reached disk. A move whose audit write failed is a failure: the store
    lost a skill, and the whole point of a retirement is the reason attached
    to it (Codex P2 #1, the same argument ``_hold_staged_item`` makes).
    """
    name = source_path.name
    if result.destination is None:
        detail = f": {result.detail}" if result.detail else ""
        print(f"  Could not archive {name}: {result.reason}{detail}", file=sys.stderr)
        stray = f"; copy written, {name} not removed" if result.stray_copy else ""
        # The refused path still gets a row. Answering "y" and then hitting a
        # refusal used to write nothing at all, leaving the log unable to
        # distinguish it from a command nobody ran, while merely DECLINING
        # wrote a `rejected` row (silent-failure review 2026-08-22 MEDIUM 8).
        approval._log_decision(
            "rejected",
            command,
            result.stray_copy if result.stray_copy is not None else source_path,
            result.text,
            source=source,
            snapshot_path=None,
            reason=f"{reason} [{result.reason}{stray}]",
            source_ids=None,
            epistemic_counts=None,
        )
        return False
    logged = approval._log_decision(
        "approved",
        command,
        result.destination,
        result.text,
        source=source,
        snapshot_path=None,
        reason=reason,
        source_ids=None,
        epistemic_counts=None,
    )
    print(f"  Archived {name} → {result.destination}")
    if not logged:
        # The move happened and the record did not. Not rolled back — putting
        # the file back would re-introduce a delete from `.archive/`, the very
        # act this exit exists to avoid — so it is surfaced as a failure with
        # both paths named, the way the paired-archive survivor is.
        print(
            f"  {_ARCHIVE_UNRECORDED}: {name} left the store for "
            f"{result.destination} but the audit row did not reach disk. "
            "The retirement is not on the record; re-record it by hand.",
            file=sys.stderr,
        )
        return False
    return True
