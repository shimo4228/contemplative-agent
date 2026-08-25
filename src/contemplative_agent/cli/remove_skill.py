"""``remove-skill``: retire one skill from the store with an audit trail.

The single manual-CRUD entry point for ``skills/``. Archiving is the default
(ADR-0097 D5) and ``--delete`` is the only irreversible path left, kept
because a genuinely wrong file — a mis-staged artifact, a duplicate written
by a bug — should not accumulate in the archive.

The move itself, its refusal codes and its audit row belong to
:mod:`.skill_archive`; this module owns the operator-facing surface: flag
parsing, the two gates that are narrower than the primitive's, the dry run,
the prompt, and the three audit ``source`` values that tell an archive from
a delete from a purge.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from ..adapters.moltbook import config
from . import approval
from .approval import AuditSource
from .registry import CommandSpec, Tier
from .skill_archive import (
    _ARCHIVE_KIND_PURGE,
    _ARCHIVE_REFUSED_ALREADY_ARCHIVED,
    _ARCHIVE_REFUSED_SYMLINK,
    _apply_archive_plan,
    _ArchiveResult,
    _plan_archive,
    _record_archive,
)
from .store_paths import _skills_dir

logger = logging.getLogger(__name__)


def _handle_remove_skill(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Retire a skill from ``skills_dir`` with an audit trail.

    The single manual-CRUD entry point for the skills directory. Writes an
    ``audit.jsonl`` record (command="remove-skill") capturing the reason,
    decision, and content hash so the retirement is reviewable alongside the
    automated approval-gate history (ADR-0012).

    **Archiving is the default** (ADR-0097 Decision 5): the file moves to
    ``skills/.archive/`` and restoring it is a plain ``mv``. ``--delete``
    unlinks instead, and is the only irreversible path left — kept because a
    genuinely wrong file (a mis-staged artifact, a duplicate written by a
    bug) should not accumulate in the archive, but explicit because the six
    deletions this command performed in five months are unrecoverable and
    that was never an intended property.

    ``--reason`` stays mandatory for both. It is not paperwork: CREW library
    weeding found 98% of candidates retained until a written reason was
    required, which is the ADR's stated defence against just-in-case
    retention, and it is also the only field that survives to explain the
    retirement once the file is out of the store.

    The audit row distinguishes the three outcomes by ``source``:
    ``direct-archive*`` for a move, ``direct-remove*`` for deleting a live
    skill, ``direct-purge*`` for deleting one already in the archive. **Not by
    ``path``** — the archive row and the purge row both carry an ``.archive/``
    path and mean opposite things, which is why the earlier claim was wrong
    (silent-failure review 2026-08-22). ``AuditSource`` grows; the row shape
    ``_log_decision`` owns does not. ``path`` still names the file the row is
    about, which for a move is the one a ``mv`` restores.

    With ``--yes`` the interactive prompt is skipped (non-TTY workflows).
    With ``--dry-run`` the target is resolved and printed but nothing is
    written, moved, or removed — including the archive directory, which is
    created lazily at the first real archive.
    """
    reason = (args.reason or "").strip()
    if not reason:
        print(
            "Error: --reason is required and must be non-empty.",
            file=sys.stderr,
        )
        sys.exit(2)

    # Derived from MOLTBOOK_DATA_DIR at call time (never the import-time
    # ``config.SKILLS_DIR``) so this handler honors a per-call / test-patched
    # home — the removal must act on the same store the rest of the
    # invocation uses.
    data_root = config.MOLTBOOK_DATA_DIR.resolve()
    skills_dir = _skills_dir(data_root).resolve()
    name = args.name
    if not name.endswith(".md"):
        name = f"{name}.md"
    # Two spellings, both needed and easy to confuse: ``literal`` is the path
    # the operator named, which is what a rename acts on and the only one
    # that can still be a symlink; ``target`` is its referent, which is what
    # the containment check and the read act on.
    literal = skills_dir / name
    target = literal.resolve()

    # NOT a copy of ``_target_inside_data_root``, and not replaceable by it.
    # This gate is scoped to ``skills/`` while the predicate is scoped to the
    # whole data root, so `remove-skill ../other` — whose referent still lives
    # under the home — passes the predicate and must be stopped here. It also
    # carries a different verdict: **exit 2**, an operator typo with nothing
    # touched, rather than a reason-coded exit 1. Pinned on both sides by
    # ``test_escape_attempt_rejected`` and
    # ``test_a_dangling_symlink_out_of_the_store_reads_as_an_escape``.
    try:
        inside = target.is_relative_to(skills_dir)
    except (OSError, ValueError):
        inside = False
    if not inside:
        print(
            f"Error: target escapes skills dir: {target}",
            file=sys.stderr,
        )
        sys.exit(2)

    # Above the plan on purpose, and not redundant with the plan's MISSING
    # arm: this one names the resolved target the operator can go look for,
    # and `--delete` reaches it too. Reads as duplication; is not.
    if not target.is_file():
        print(f"Error: skill not found: {target}", file=sys.stderr)
        sys.exit(1)

    delete = getattr(args, "delete", False)

    # One plan for the whole invocation. The dry run, the prompt and the move
    # all read it, which is what makes the preview unable to promise something
    # the run refuses (Codex P2 #2) without anyone keeping two lists of checks
    # in step.
    #
    # ``literal``, never ``target``: ``is_symlink()`` on a resolved path is
    # always False, so planning from the referent would turn the symlink
    # refusal below into a silent no-op.
    plan = _plan_archive(literal, data_root=data_root, superseded_by=None)
    if isinstance(plan, _ArchiveResult):
        # In practice only SYMLINK — MISSING and OUTSIDE were answered above,
        # in this handler's own idiom. Handled by code rather than by name so
        # a new source-side refusal cannot fall through unreported.
        #
        # The symlink refusal applies to BOTH branches, above the dry run and
        # above the prompt. This is the silent-failure review's CRITICAL: it
        # used to live under `if not delete:` and its message offered
        # `--delete` as the way to "drop the link" — but `target` is the
        # RESOLVED leaf, so `--delete` unlinked the referent. Reproduced:
        # `remove-skill link --delete --yes` printed "Removed real.md",
        # destroyed the live skill with no archive and no recovery, left
        # `link.md` dangling, and wrote an audit row naming a file the
        # operator never typed.
        #
        # Refused rather than made to unlink the link itself, which was the
        # other option: the row's ``content`` is the referent's bytes, so a row
        # for a removed *link* would hash text that still exists — a second lie
        # in place of the first. A symlink is not a skill; `rm` removes one,
        # and this command stays the entry point for skills only.
        detail = (
            f"{name} is a symlink, not a skill. Name its referent "
            f"({target.name}) to retire that, or remove the link with `rm`."
            if plan.reason == _ARCHIVE_REFUSED_SYMLINK
            else f"{target}{': ' + plan.detail if plan.detail else ''}"
        )
        print(f"Error: {plan.reason}: {detail}", file=sys.stderr)
        sys.exit(1)

    # The INTENDED destination, shown in the dry run and the prompt. Archiving
    # over a name already in `.archive/` with different content appends a
    # counter (``approval._collision_free_path``, which announces itself), so
    # the final path can differ by that suffix — never by directory, and never
    # by overwriting anything, which is why this is safe to promise up front.
    # ``_same_archive_slot`` checks that claim at the move.
    destination = plan.intended
    # ``purging`` and the already-archived refusal are the same question, and
    # the plan answered it once. They used to be two copies of one expression,
    # forty lines apart.
    purging = plan.kind == _ARCHIVE_KIND_PURGE
    if not delete:
        # A file that already left the store has no second exit. `name` is
        # free-form and `.archive/old` resolves inside the skills dir, so the
        # containment check above admits it; archiving it again computed a
        # destination equal to the source and unlinked the last copy
        # (security review 2026-08-22 MEDIUM). `--delete` stays the
        # deliberate, audited way to purge from the archive.
        if purging:
            print(
                f"Error: {_ARCHIVE_REFUSED_ALREADY_ARCHIVED}: {target} is already in the "
                "archive; there is no second exit. Restore it with `mv` first, or "
                "use --delete to remove it permanently.",
                file=sys.stderr,
            )
            sys.exit(1)
        # A field rather than a refusal, precisely so this stays under
        # `if not delete`: `--delete` never touches the archive slot and must
        # keep working when the slot is unusable.
        if plan.destination_refusal:
            print(
                f"Error: {plan.destination_refusal}: cannot archive "
                f"{target.name} to {destination}.",
                file=sys.stderr,
            )
            sys.exit(1)

    if getattr(args, "dry_run", False):
        if delete:
            print(f"[dry-run] would remove: {target}")
        else:
            print(f"[dry-run] would archive: {target} → {destination}")
        print(f"[dry-run] reason: {reason}")
        return

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as err:
        print(f"Error: cannot read {target}: {err}", file=sys.stderr)
        sys.exit(1)

    yes = getattr(args, "yes", False)
    # Three outcomes, three categorical sources — a live skill deleted, a
    # live skill moved to the archive, and a file already in the archive
    # purged. They used to share `direct-remove*`, so an archive row and a
    # purge row differed only in operator free text (silent-failure review
    # 2026-08-22 HIGH). The purge arm is reachable only through `--delete`,
    # because the archive arm refuses an already-archived source above.
    # ``purging`` comes from the plan; this line used to recompute it.
    if not delete:
        source: AuditSource = "direct-archive-auto" if yes else "direct-archive"
    elif purging:
        source = "direct-purge-auto" if yes else "direct-purge"
    else:
        source = "direct-remove-auto" if yes else "direct-remove"

    def _record(path: Path, approved: bool) -> None:
        """One row shape for every verdict this handler reaches.

        ``command`` / ``content`` / ``source`` / ``reason`` are fixed for the
        whole invocation, so writing them out per branch only invited the four
        rows to drift apart (code review 2026-08-22). What varies is the
        verdict and the path. ``source`` carries which of the three
        retirements this is; ``path`` names the file the row is about and is
        NOT the discriminator (see ``_record_archive``).
        """
        approval._log_approval(
            command="remove-skill",
            path=path,
            approved=approved,
            content=text,
            source=source,
            reason=reason,
        )

    if delete:
        if not (yes or approval._approve_delete(target)):
            _record(target, False)
            print("Kept.")
            return
        # Unlink BEFORE logging, matching every other destructive branch in
        # this module (the reject arm's 2026-08-01 H1 ordering, and the new
        # archive path ten lines down): a row claiming a deletion that did not
        # reach disk is worse than a deletion with a missing row. This was the
        # one branch still logging first — pre-existing, aligned while here.
        try:
            target.unlink()
        except OSError as err:
            print(f"Error: could not remove {target}: {err}", file=sys.stderr)
            sys.exit(1)
        _record(target, True)
        print(f"Removed {target.name}")
        return

    if not (yes or approval._approve(f"Archive {target} → {destination}?")):
        _record(target, False)
        print("Kept.")
        return

    # The plan the dry run and the prompt were built from, applied unchanged.
    # Not ``_archive_skill_file(target, ...)``: that would re-plan from the
    # resolved path and hand the move a second chance to disagree with what
    # the operator was shown.
    result = _apply_archive_plan(plan)
    if not _record_archive(
        result,
        command="remove-skill",
        source_path=target,
        source=source,
        reason=reason,
    ):
        sys.exit(1)


def _add_remove_skill_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "name",
        help="Skill filename stem (with or without .md suffix)",
    )
    parser.add_argument(
        "--reason",
        required=True,
        help="Justification recorded in audit.jsonl (required, non-empty)",
    )
    parser.add_argument(
        "--delete",
        action="store_true",
        help="Delete the file instead of archiving it. Irreversible: the "
        "default moves the skill to skills/.archive/, where a plain mv "
        "restores it (ADR-0097 D5).",
    )
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Skip the interactive prompt "
        "(for non-TTY / coding-agent workflows where stdin is not interactive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and print the target without moving, deleting, or writing audit",
    )


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="remove-skill",
        help="Retire a skill from skills_dir with an audit trail "
        "(archives to skills/.archive/; --delete to unlink)",
        handler=_handle_remove_skill,
        tier=Tier.NO_LLM,
        add_arguments=_add_remove_skill_arguments,
    ),
)
