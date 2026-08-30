"""adopt-staged: promote staged value-layer items through the approval gate.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).

Threat model (recorded 2026-08-15 with the T-WRITE-TMP-NOFOLLOW fix, which
closed the one exception; narrowed 2026-08-22 by ADR-0097 slice 1, extended
the same day by slice 2's archive exit). The adversary is whoever can write
``.staged/``: the sidecar is user-writable between stage and adopt, so
``target`` and ``command`` are attacker-chosen. What that buys them is
bounded to MOLTBOOK_HOME and no further.

* ``target`` is containment-checked twice in ``_load_staged_item`` — once
  resolved, once literal-with-resolved-parent — because reads follow symlinks
  and writes do not. Either check alone leaks in one direction.
* **Adopting a staged item is still a write and nothing else.** The two
  delete primitives this command used to honor from the sidecar —
  ``sources`` (delete the merge's originals) and ``action: drop`` (unlink
  the target) — went with the stocktake merge / clean / drop producers
  ADR-0097 retired. A sidecar naming either is **refused** in
  ``_load_staged_item`` rather than silently read as an ordinary write:
  ignoring the key would turn an approved deletion into an approved
  duplicate.
* **The store's exit is a different module.** ``--archive-names`` is the
  only way an archive enters this command, and no sidecar key is
  consulted for it — not a reviewer's prose, not a ``supersedes`` field.
  The exit's own threat model, its containment argument and its refusal
  codes live in :mod:`.skill_archive`; the shared path predicates live in
  :mod:`.store_paths`.

Deliberately no additional gate on ``target``: it is a subset of what writing
``.staged/`` already grants. The primitives that did exceed the store —
``write_restricted``'s predictable temp sibling, which followed a pre-placed
symlink *or hardlink* to an arbitrary path — are fixed at the writer
(``core/_io.py``), not papered over here.
"""

from __future__ import annotations

import argparse
import json as json_mod
import logging
import math
import sys
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum, auto
from functools import cached_property
from pathlib import Path
from typing import Any, NoReturn

from ..adapters.moltbook import config
from ..core.domain import (
    load_constitution,
)
from . import approval
from .approval import AuditSource
from .registry import CommandSpec, Tier
from .skill_archive import (
    _ARCHIVE_REFUSED_JUST_ADOPTED,
    _ARCHIVE_SUCCESSOR_NOT_ADOPTED,
    _archive_skill_file,
    _record_archive,
)
from .staging import read_sidecar
from .store_paths import (
    _archive_dir,
    _resolved_or_self,
    _skills_dir,
    _target_inside_data_root,
    _writes_into_the_store,
)

logger = logging.getLogger(__name__)


# ADR-0074: one JSON record per staged insight candidate. Feeds the novelty
# gate's known-theme inventory so a theme counts as "considered" once it
# reached human review, whether or not it was adopted.
INSIGHT_STAGED_LEDGER_PATH = config.MOLTBOOK_DATA_DIR / "logs" / "insight-staged.jsonl"


@dataclass(frozen=True)
class _StagedItem:
    """One staged artifact parsed from its ``.meta.json`` sidecar.

    ``meta`` carries the raw sidecar object the rest of the fields were
    validated from, so an outcome that has to WRITE the sidecar back (hold)
    marks the same snapshot it audits. Re-reading the file instead let a
    concurrent rewrite land the marker on new metadata while the audit row
    described the old item (codex review 2026-08-15).
    """

    content_file: Path
    target: Path
    command: str
    text: str
    source_ids: Sequence[str] | None
    epistemic_counts: dict[str, int] | None
    meta: dict[str, Any]


def _load_staged_item(meta_file: Path, data_root: Path) -> _StagedItem | None:
    """Parse and validate one staged entry; None (with a printed reason) on skip.

    Enforces the module's containment boundary; see the module docstring for
    what the adversary can reach once past it.
    """
    meta = read_sidecar(meta_file)
    if meta is None:
        print(f"  Skipped (meta unreadable, not an object, or a symlink): {meta_file.name}")
        return None

    target_str = meta.get("target")
    command = meta.get("command")
    if not target_str or not command:
        print(f"  Skipped (invalid meta): {meta_file.name}")
        return None

    # A sidecar written before ADR-0097 can still ask for a delete
    # (``action: "drop"``) or name a merge's originals (``sources``). Nothing
    # honors those keys any more, so adopting such an item would quietly do
    # the opposite of what the operator approved: a drop item would be
    # *written* — as a `-2.md` twin of the skill it was meant to remove — and
    # a clean rewrite would twin its own original instead of replacing it,
    # both recorded in audit.jsonl as approved writes. Refuse instead; the
    # batch is re-stageable once the producer is gone.
    legacy = [key for key in ("action", "sources") if meta.get(key)]
    if legacy:
        print(
            f"  Skipped (sidecar asks for retired {'/'.join(legacy)} handling, "
            f"ADR-0097): {meta_file.name}",
            file=sys.stderr,
        )
        return None

    target = Path(target_str)
    # Defense in depth: the meta.json is user-writable between stage and
    # adopt, so re-verify the target still lives inside MOLTBOOK_HOME.
    if not _target_inside_data_root(target, data_root):
        print(
            f"Error: staged target escapes MOLTBOOK_HOME: {target}",
            file=sys.stderr,
        )
        return None

    content_file = meta_file.parent / meta_file.name[: -len(".meta.json")]
    if not content_file.exists():
        print(f"  Skipped (content missing): {content_file.name}")
        return None

    try:
        text = content_file.read_text(encoding="utf-8")
    except OSError as err:
        print(f"  Skipped (content read error): {content_file.name}: {err}")
        return None

    return _StagedItem(
        content_file=content_file,
        target=target,
        command=command,
        text=text,
        # ADR-0050: lineage staged alongside the artifact; attach it to
        # the adopt-time audit entry so deferred approval keeps lineage.
        source_ids=meta.get("source_ids") or None,
        epistemic_counts=meta.get("epistemic_counts") or None,
        meta=meta,
    )


# Staging commands that own a canonical file and exist to replace it. Kept as
# a named set so the operator warning below and the predicate cannot drift.
# ``value_layer_due_check.py`` enumerates a wider identity vocabulary
# (``distill-identity-ca``, the shelved ADR-0013 coding-agent path); it has no
# live staging producer, so it cannot reach here — reviving it means adding it
# in both places (code review 2026-08-15).
_REPLACEMENT_COMMANDS = frozenset({"distill-identity", "amend-constitution"})


def _replaces_canonical_target(command: str, target: Path, data_root: Path) -> bool:
    """True when this staged write is *meant* to overwrite the file it names.

    The H5 collision guard (``approval._collision_free_path``) protects
    generated artifacts: two insight batches can slugify to the same
    ``<slug>-YYYYMMDD.md``, and the second write must not silently clobber
    the first. ``distill-identity`` and ``amend-constitution`` invert that —
    each owns exactly one canonical file and replacing it is the whole point,
    so the guard turns an approved amendment into an inert twin
    (``identity-2.md`` / ``contemplative-axioms-2.md``). Two live
    occurrences: 2026-08-09 (constitution — harmful, since the runtime
    concatenates every ``*.md`` in that dir, so both texts were injected at
    once) and 2026-08-15 (identity — silent, since ``IDENTITY_PATH`` is a
    fixed single path, so the twin is never read and the value layer simply
    never changed while ``audit.jsonl`` said ``approved``).

    Bounded by **location as well as command**: the sidecar is user-writable
    between stage and adopt (same threat model as ``_load_staged_item``'s
    containment check), so a tampered ``command`` cannot borrow the
    replacement intent to clobber an arbitrary file — ``distill-identity``
    may overwrite ``identity.md`` and nothing else, ``amend-constitution``
    only a ``*.md`` sitting directly in the constitution dir. A custom
    ``--constitution-dir`` outside that location, and a symlinked canonical
    path, both keep the old guarded behaviour: conservative, and adopt-staged
    has no way to learn which custom dir a past run used. That fallback is
    the very silence this function exists to end, so ``_adopt_write_item``
    says so out loud when it happens rather than minting a quiet twin.
    """
    try:
        # Resolve the PARENT but keep the final component literal: the write
        # lands via ``write_restricted`` → ``os.replace`` on the unresolved
        # path, which replaces a symlinked leaf *itself* rather than its
        # referent. Resolving the leaf would grant the exemption to
        # ``skills/victim.md -> ../identity.md``, clobber that out-of-location
        # path, and leave the canonical file untouched while the budget
        # reading subtracted the referent (codex review 2026-08-15, proven by
        # execution). Parent symlinks are resolved because ``os.replace``
        # does follow those.
        if target.is_symlink():
            return False
        resolved = target.parent.resolve() / target.name
        root = data_root.resolve()
    except OSError:
        return False
    if command == "distill-identity":
        return resolved == root / "identity.md"
    if command == "amend-constitution":
        return resolved.suffix == ".md" and resolved.parent == root / "constitution"
    return False


def _adopt_write_item(
    item: _StagedItem,
    *,
    yes: bool,
    audit_source: AuditSource,
    data_root: Path,
    supersedes: Sequence[str] = (),
) -> Path | None:
    """Write the staged text to its target after approval.

    Returns the path actually written (which the H5 collision guard may have
    renamed) or ``None`` when the item was not adopted. The caller needs the
    path, not a bool: the archive step stamps ``superseded_by:`` with the
    name that ended up on disk, and a stamp naming a file that does not exist
    is worse than no stamp.
    """
    from ..core._io import write_restricted
    from ..core.artifact_extraction import canonicalize_frontmatter_name, slug_from_stem
    from ..core.text_utils import set_frontmatter_field

    # H5 collision guard — exempt when the staging command owns its target and
    # replacing it is the intent (T-ADOPT-OVERWRITE-TARGETS; see
    # _replaces_canonical_target). The other former exemption, a stocktake
    # merge reusing one of its own source names, went with that producer
    # (ADR-0097).
    target = item.target
    replaces_canonical = _replaces_canonical_target(item.command, target, data_root)
    if not replaces_canonical:
        target = approval._collision_free_path(target, item.text)
    # Say what the write destroys, BEFORE the gate. The rename this exemption
    # removes was also the operator's only signal that an existing file was in
    # the way ("Name collision: … writing identity-2.md instead"); without it
    # a destructive in-place replace and a fresh create print the same prompt,
    # and --yes / --adopt-names print nothing at all (security review
    # 2026-08-15, observability regression on the one path this change makes
    # destructive).
    if replaces_canonical and target.is_file():
        print(f"  Replacing existing {target.name} ({target.stat().st_size:,} bytes)")
    elif item.command in _REPLACEMENT_COMMANDS and target != item.target:
        # The fallback fired: a symlinked canonical path or a custom
        # constitution dir. Adoption still records `approved`, but the live
        # value layer will NOT change — exactly the 2026-08-15 shape.
        print(
            f"  Note: {item.command} could not replace {item.target.name} in place "
            f"(symlink or non-canonical location); writing {target.name}, "
            "which the runtime does not read"
        )
    text = item.text
    if supersedes:
        # Stamped BEFORE the gate and before the audit hash rather than
        # patched in after the write: a later rewrite would leave
        # audit.jsonl's content_hash describing bytes no longer on disk, the
        # one invariant this function's logging comment already pins. Said
        # out loud for the same reason the replacement note is — the operator
        # typed the pairing in a separate file and never sees it in the body
        # printed above.
        joined = ", ".join(sorted(supersedes))
        print(f"  Recording supersedes: {joined}")
        text = set_frontmatter_field(text, "supersedes", joined, synthesize=True)
    # One-canonical-identity invariant, established AT the write boundary
    # (weekly 2026-08-08 F1.3): the extraction-time canonicalization
    # (insight/rules-distill) is a producer convention, not an invariant —
    # text staged before that fix landed, staged by a future producer that
    # skips it, or renamed by the collision guard just above would all enter
    # the live store with a frontmatter ``name:`` that ``ls`` never shows.
    # Idempotent normalization, not a gate: an already-canonical candidate
    # (and any body without frontmatter — identity, constitution, legacy
    # rules) passes through byte-identical, and nothing is rejected.
    text = canonicalize_frontmatter_name(text, slug_from_stem(target.stem))
    approved = True if yes else approval._approve_write(target)
    approval._log_approval(
        item.command,
        target,
        approved,
        # Log the canonicalized text — the audit row's content hash must
        # match the bytes actually written to the durable store.
        text,
        source=audit_source,
        source_ids=item.source_ids,
        epistemic_counts=item.epistemic_counts,
    )
    if not approved:
        print("Skipped.")
        return None
    target.parent.mkdir(parents=True, exist_ok=True)
    to_write = text if text.endswith("\n") else text + "\n"
    write_restricted(target, to_write)
    return target


def _staged_sort_key(meta_file: Path) -> tuple[int, str]:
    """Adoption order: staging sequence first, then filename.

    A plain name sort adopts ``dup-2.md`` before ``dup.md`` ('-' sorts
    before '.'), so a collision pair's final target names came out swapped
    from their staging order (codex review round-2 P2). ``seq`` is written
    by ``_stage_results``; metas without it (pre-seq batches, corrupt
    sidecars) sort last by name, preserving the old order among themselves.
    """
    meta = read_sidecar(meta_file)
    seq = meta.get("seq") if meta is not None else None
    return (seq if isinstance(seq, int) else sys.maxsize, meta_file.name)


def _budget_texts(
    meta_files: Sequence[Path], data_root: Path, archived_paths: Sequence[Path]
) -> tuple[list[str], list[str]]:
    """The bodies entering the prompt and the bodies leaving it.

    Split out of :func:`_print_system_budget_for_staged` for the C901 budget
    (2026-08-31). Every containment and refusal test the two loops carry is
    unchanged: the projection must not count an item the adopt loop will
    refuse, so a sidecar naming a path outside ``data_root`` is skipped, a
    symlinked archive candidate is skipped, and an existing target is
    subtracted only when adoption really replaces it.
    """
    new_texts: list[str] = []
    replaced_texts: list[str] = []
    for meta_file in meta_files:
        try:
            meta = read_sidecar(meta_file)
            if meta is None or not meta.get("target"):
                continue
            target = Path(meta["target"])
            # The loop's own containment test, so the projection cannot
            # count an item the loop will refuse (codex 2026-08-15).
            if not _target_inside_data_root(target, data_root):
                continue
            content_file = meta_file.parent / meta_file.name[: -len(".meta.json")]
            text = content_file.read_text(encoding="utf-8")
            new_texts.append(text)
            # Subtract the existing target only when adoption really
            # replaces it: a canonical replacement (identity /
            # constitution) or an idempotent identical write. A same-name,
            # different-content target gets a `-N.md` suffix from
            # approval._collision_free_path and the original survives —
            # subtracting it would under-project (codex 2026-07-10 P2).
            # This asks the same question as the write path above, so the
            # two cannot disagree about whether the old text survives.
            if target.exists():
                existing = target.read_text(encoding="utf-8")
                if (
                    _replaces_canonical_target(meta.get("command") or "", target, data_root)
                    or existing.strip() == text.strip()
                ):
                    replaced_texts.append(existing)
        except (OSError, ValueError):
            continue
    for archived in archived_paths:
        try:
            # Same rule as the staged half above: an item the loop will
            # refuse must not appear in the reading the operator approves
            # against. A symlinked store skill passes containment but
            # `_archive_skill_file` refuses it, and reading it here would
            # subtract the REFERENT's body for a move that never happens
            # (code review 2026-08-22). The other two archive refusals
            # (just-adopted, successor-declined) are not knowable until
            # the loop has run, so they stay out of scope for a
            # before-the-loop projection.
            if archived.is_symlink() or not _target_inside_data_root(archived, data_root):
                continue
            replaced_texts.append(archived.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return new_texts, replaced_texts


def _print_system_budget_for_staged(
    meta_files: Sequence[Path], data_root: Path, *, archived_paths: Sequence[Path] = ()
) -> None:
    """Print the read-only system-prompt budget projection for a staged batch.

    ``archived_paths`` are store skills this run will retire (ADR-0097 D5):
    their bodies leave the prompt, so they are subtracted exactly like a
    replaced canonical file. Without them a batch that adopts three skills
    and archives four would project a rise the operator will never see.

    ADR-0071-style instrument at the adopt gate: shows what adopting the
    whole batch does to the system prompt's share of the context window,
    so the operator approves with the cost visible (2026-07-09: a 13-skill
    batch was approved blind and pushed the prompt past the C2 guard).
    Observability only — the reading gates nothing, and any failure
    degrades to a WARNING so a broken instrument never blocks adoption.
    Invalid sidecars are skipped silently here; the adopt loop itself
    reports and quarantines them.

    Same defense-in-depth as ``_load_staged_item`` (codex review 2026-07-10):
    the sidecar is user-writable between stage and adopt, so any path it
    names is containment-checked against ``data_root`` before being read —
    the instrument must not read (or hang on) an arbitrary path the adopt
    loop would quarantine.
    """

    try:
        from ..core.llm import system_prompt_budget_reading

        new_texts, replaced_texts = _budget_texts(meta_files, data_root, archived_paths)
        # adopt-staged is a Tier-1 (no-LLM-setup) command, so mirror the
        # session-time prompt composition (agent.py startup: identity +
        # axioms + skills + rules) via per-reading overrides — the reading
        # must measure the prompt agents actually run with.
        clauses = load_constitution(config.CONSTITUTION_DIR)
        reading = system_prompt_budget_reading(
            new_texts,
            replaced_texts,
            identity_path=config.IDENTITY_PATH if config.IDENTITY_PATH.is_file() else None,
            axiom_prompt=clauses or None,
            skills_dir=config.SKILLS_DIR if config.SKILLS_DIR.is_dir() else None,
            rules_dir=config.RULES_DIR if config.RULES_DIR.is_dir() else None,
        )
        pct = round(100 * reading.projected_tokens / reading.window)
        print(
            f"System prompt budget: ≈{reading.current_tokens:,} tok → "
            f"≈{reading.projected_tokens:,} tok after this batch "
            f"({pct}% of the {reading.window:,}-token window; "
            f"estimate over-counts — audit C2 scale)"
        )
    except Exception as exc:
        logging.getLogger(__name__).warning(
            "System budget instrument failed (adoption unaffected): %s", exc
        )


def _staged_name(meta_file: Path) -> str:
    """The staged item's name: its content filename (sidecar minus suffix)."""
    return meta_file.name[: -len(".meta.json")]


def _abort_request(problem: str, names: Iterable[str] = ()) -> NoReturn:
    """Refuse the whole request with exit 2, before anything has been mutated.

    Ten checks printed these same two lines in two wordings, and the narrower
    one ("staging left untouched") was wrong wherever the store was equally
    spared — a name shared by ``--hold-names`` and ``--archive-names``, for
    instance (code review 2026-08-22). Only the printing is shared: every
    check keeps its exact position relative to the first mutation, which is
    the property that makes "nothing touched" true rather than merely stated.
    """
    listed = ": " + ", ".join(names) if names else ""
    print(f"Error: {problem}{listed}", file=sys.stderr)
    print("No changes made; the store and staging are untouched.", file=sys.stderr)
    sys.exit(2)


def _read_names_lines(names_file: Path, flag: str) -> list[str]:
    """The non-empty stripped lines of a per-item selection file.

    Shared by every ``--*-names`` flag — ``--adopt-names`` / ``--hold-names``
    through :func:`_read_names_file`, ``--archive-names`` through
    :func:`_read_archive_names_file` — so the three cannot drift on the two
    abort contracts below; ``flag`` only names the offender in the messages.

    Blank lines and surrounding whitespace are ignored. An unreadable file
    aborts with exit code 2 — falling back to "select nothing" or, worse,
    "select everything" would silently invert the operator's per-item
    decision (T-ADOPT-PERITEM).

    An empty selection is a writer bug (truncated write, crashed producer),
    not a valid decision: combined with ``--reject-rest`` it would silently
    delete the ENTIRE staging queue while logging each item as an
    individually decided rejection (2026-08-01 security review C2,
    reproduced). Abort exactly like the unreadable case.
    """
    try:
        raw = names_file.read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        # ValueError covers UnicodeDecodeError — same clean-abort contract as
        # an unreadable file (2026-08-01 security review L1).
        print(f"Error: cannot read {flag} file {names_file}: {err}", file=sys.stderr)
        sys.exit(2)
    lines = [stripped for line in raw.splitlines() if (stripped := line.strip())]
    if not lines:
        print(
            f"Error: {flag} file {names_file} contains no names; "
            "aborting (an empty selection is never a decision).",
            file=sys.stderr,
        )
        sys.exit(2)
    return lines


def _read_names_file(names_file: Path, flag: str) -> set[str]:
    """Read a per-item selection file (one staged filename per line).

    Duplicates collapse; the abort contracts live in
    :func:`_read_names_lines`.
    """
    return set(_read_names_lines(names_file, flag))


# The optional second token of an ``--archive-names`` line. A word rather
# than an arrow so the file says what it means when a human re-reads the
# packet six months later, and so a filename can never be mistaken for it.
_SUPERSEDED_BY_TOKEN = "superseded-by"


def _read_archive_names_file(names_file: Path, flag: str) -> dict[str, str | None]:
    """Read the archive selection file into ``{skill filename: successor}``.

    One **store** skill filename per line — these name files in ``skills/``,
    not staged items — with one optional suffix::

        old-skill-20260601.md
        old-dup-20260715.md superseded-by new-consolidated-20260822.md

    The bare form is a standalone retirement (the ADR-0097 D5 never-selected
    exit). The paired form is D6's ``adopt-superseding`` verdict transcribed
    by the operator, and this argument is its **only** channel: deriving the
    pairing from a staged sidecar or from the reviewer's prose is precisely
    what D5/D6 forbid, so a line that parses as neither form aborts rather
    than degrading to the bare form — silently dropping the pairing would
    archive the skill and lose the pointer to its replacement.

    Same read / empty-file abort contracts as the other two flags (shared
    :func:`_read_names_lines`). An exact duplicate line collapses; the same
    skill named twice with *different* successors aborts, because there is no
    safe way to pick one.
    """
    specs: dict[str, str | None] = {}
    for line in _read_names_lines(names_file, flag):
        parts = line.split()
        if len(parts) == 1:
            archived, successor = parts[0], None
        elif len(parts) == 3 and parts[1] == _SUPERSEDED_BY_TOKEN:
            archived, successor = parts[0], parts[2]
        else:
            print(
                f"Error: cannot parse {flag} line {line!r}; expected "
                f"'<skill.md>' or '<skill.md> {_SUPERSEDED_BY_TOKEN} <staged-name.md>'.",
                file=sys.stderr,
            )
            sys.exit(2)
        if archived in specs and specs[archived] != successor:
            print(
                f"Error: {flag} names {archived} twice with different successors.",
                file=sys.stderr,
            )
            sys.exit(2)
        specs[archived] = successor
    return specs


def _mark_sidecar_held(meta_file: Path, meta: dict[str, Any]) -> bool:
    """Stamp ``held`` / ``held_at`` onto the sidecar; False (loudly) on failure.

    The audit row records the decision, but it lands in ``logs/audit.jsonl``,
    which the next staging run never reads. The marker is what lets the
    ADR-0074 pending guard say *why* it is refusing to stage a new batch
    instead of reporting an anonymous count of leftovers. Every other key is
    preserved verbatim — ``seq`` in particular, which drives adoption order.

    ``meta`` is the snapshot ``_load_staged_item`` validated, deliberately
    NOT a fresh read. **The marker and the audit row must describe the same
    snapshot**, and only the caller can guarantee that: ``_hold_staged_item``
    passes ``item.meta`` here and ``item.target`` / ``item.text`` to
    ``approval._log_decision`` a few lines later. Re-reading the sidecar
    would let one rewritten in between take the marker while the row still
    named the item loaded before it — the file says held, the row names a
    different target (codex review 2026-08-15). Pinned by
    ``test_the_marker_lands_on_the_snapshot_that_was_audited``.
    """
    from ..core._io import now_iso, write_restricted

    marked = dict(meta)
    marked["held"] = True
    marked["held_at"] = now_iso(timespec="seconds")
    try:
        write_restricted(meta_file, json_mod.dumps(marked, ensure_ascii=False) + "\n")
    except (OSError, ValueError) as err:
        print(f"  Could not mark {meta_file.name} as held: {err}", file=sys.stderr)
        return False
    return True


def _hold_staged_item(item: _StagedItem, meta_file: Path, *, audit_source: AuditSource) -> bool:
    """Leave the item staged, on the record. True when the hold stuck.

    The third answer the gate has always offered and the CLI never carried
    (T-ADOPT-HOLD). Marking precedes logging for the same reason the reject
    branch unlinks before logging (2026-08-01 security review H1): an audit
    row describing an outcome that did not reach disk is worse than a
    disk change with no row.
    """
    if not _mark_sidecar_held(meta_file, item.meta):
        return False
    if not approval._log_decision(
        "held",
        item.command,
        item.target,
        item.text,
        source=audit_source,
        snapshot_path=None,
        reason=None,
        source_ids=item.source_ids,
        epistemic_counts=item.epistemic_counts,
    ):
        # The marker landed but the row did not. A hold whose only evidence
        # is a file the audit trail never mentions is exactly the state this
        # feature exists to end, so it is a failure, not a success with a
        # warning (security review 2026-08-15).
        print(
            f"  Held {item.content_file.name} on disk but could not record it in the audit log",
            file=sys.stderr,
        )
        return False
    print(f"  Held (in --hold-names): {item.content_file.name}")
    return True


def _quarantine_invalid_sidecar(meta_file: Path) -> None:
    """Quarantine an unparseable/invalid sidecar instead of leaving it.

    An invalid meta counts toward the ADR-0074 pending guard, so a single
    corrupt sidecar would otherwise block every future --stage run
    permanently (codex review 2026-07-09). Rename preserves the bytes for
    inspection while removing it from the pending count.
    """
    quarantined = meta_file.with_name(meta_file.name + ".invalid")
    try:
        meta_file.rename(quarantined)
        print(f"  Quarantined invalid sidecar → {quarantined.name}")
    except OSError as err:
        print(f"  Could not quarantine {meta_file.name}: {err}", file=sys.stderr)


class _Outcome(Enum):
    """What happened to one staged item — the dispatch's whole return channel.

    An enum rather than eight counter variables threaded through one loop:
    the summary and the exit code are both functions of the tally, and with
    the counters inline every new branch had to remember to increment the
    right one. Three of these mean "the operator asked for something that did
    not happen", which is exactly the exit-1 condition, so that verdict is
    read off the values instead of restated as a boolean expression.
    """

    # `auto()` and not strings: the summary labels live in
    # `_report_adopt_outcomes` and nothing reads `.value`, so string values
    # would read as if editing them changed the output — and two members
    # sharing one would silently ALIAS, merging two outcomes in the Counter and
    # double-counting a summary field with no error anywhere (2026-08-16 code
    # review LOW).
    ADOPTED = auto()
    REJECTED = auto()
    HELD = auto()
    SKIPPED = auto()
    LEFT = auto()
    REJECT_FAILED = auto()
    HOLD_FAILED = auto()
    ADOPT_FAILED = auto()
    # ADR-0097 D5. Not a staged item's fate — one named store skill's — but
    # tallied in the same Counter so the exit code keeps one derivation: a
    # batch whose adoptions landed and whose archives did not is a partially
    # applied batch, and the caller must not read it as success.
    ARCHIVED = auto()
    ARCHIVE_FAILED = auto()

    @property
    def is_failure(self) -> bool:
        """True when what was asserted did not happen (exit 1).

        Not the same as "not adopted": SKIPPED and LEFT are outcomes nobody
        asserted against, and counting them here would fail a bare
        interactive run that simply declined an item.
        """
        return self in (
            _Outcome.REJECT_FAILED,
            _Outcome.HOLD_FAILED,
            _Outcome.ADOPT_FAILED,
            _Outcome.ARCHIVE_FAILED,
        )


@dataclass(frozen=True)
class _ItemResult:
    """One staged item's fate, plus where an adopted one actually landed.

    The path is neither the staged name nor the sidecar's ``target``: the H5
    collision guard can rename it at the last moment. The archive step needs
    the real one, because ``superseded_by:`` pointing at a file that does not
    exist is worse than no pointer at all.
    """

    outcome: _Outcome
    adopted_as: Path | None = None


@dataclass(frozen=True)
class _AdoptPlan:
    """The reconciled request — every flag resolved, every name verified.

    Built before the first destructive operation, which is the property that
    matters: `--adopt-names` with one typo must leave staging untouched, and
    that can only be guaranteed by finishing the reconciliation before the
    loop starts rather than by checking as it goes.

    ``adopt_names is None`` means "every staged item" (a bare interactive run
    or ``--yes``); a set means per-item selection by staged filename.

    ``archive_specs`` maps a **store** skill filename to the staged item that
    supersedes it (``None`` for a standalone retirement). It is the only
    place the ADR-0097 D5 exit enters this command, and it comes from
    ``--archive-names`` alone — never from a sidecar, a reviewer verdict or a
    frontmatter field (see the module docstring's threat model).
    """

    meta_files: list[Path]
    adopt_names: set[str] | None
    hold_names: set[str]
    reject_rest: bool
    yes: bool
    audit_source: AuditSource
    data_root: Path
    archive_specs: dict[str, str | None] = field(default_factory=dict)

    @property
    def per_item(self) -> bool:
        return self.adopt_names is not None

    @property
    def instrument_metas(self) -> list[Path]:
        """The items whose adoption the budget instrument should project.

        In per-item mode the unselected items either stay staged or are
        rejected, and neither outcome changes the system prompt.
        """
        if self.adopt_names is None:
            return self.meta_files
        return [mf for mf in self.meta_files if _staged_name(mf) in self.adopt_names]

    @property
    def archive_sources(self) -> list[Path]:
        """The store files ``--archive-names`` asked to retire, in name order."""
        skills_dir = _skills_dir(self.data_root)
        return [skills_dir / name for name in sorted(self.archive_specs)]

    @cached_property
    def supersedes(self) -> dict[str, tuple[str, ...]]:
        """Staged item name → the store skills its adoption supersedes.

        The inverse of ``archive_specs``, and a tuple rather than a scalar
        because one consolidated skill can retire several variants (the
        08-22 batch's three-variants-of-one-theme shape); the survivor then
        carries ``supersedes: a.md, b.md``.

        Cached: the dispatch loop asks once per staged item, and the answer
        cannot change — ``archive_specs`` is fixed when the plan is built.
        ``cached_property`` writes straight into ``__dict__``, so it works on
        a frozen dataclass that has no ``__slots__``.
        """
        out: dict[str, list[str]] = {}
        for archived, successor in self.archive_specs.items():
            if successor is not None:
                out.setdefault(successor, []).append(archived)
        return {name: tuple(sorted(names)) for name, names in out.items()}


def _reconcile_selection_flags(
    args: argparse.Namespace,
) -> tuple[bool, set[str] | None, set[str], bool]:
    """Read and cross-validate ``--yes`` / ``--adopt-names`` / ``--hold-names``.

    Split out of :func:`_resolve_adopt_plan` (behaviour-preserving): this is
    the self-contained slice that only touches ``args`` and the two names
    files, before ``--archive-names`` or the staging directory enter the
    picture. Returns ``(yes, adopt_names, hold_names, reject_rest)``.
    """
    yes = getattr(args, "yes", False)
    adopt_names_file = getattr(args, "adopt_names", None)
    hold_names_file = getattr(args, "hold_names", None)
    reject_rest = getattr(args, "reject_rest", False)

    if yes and (adopt_names_file or hold_names_file):
        _abort_request(
            "--adopt-names / --hold-names and --yes are mutually exclusive "
            "(per-item selection vs adopt-everything)"
        )
    if reject_rest and not (adopt_names_file or hold_names_file):
        _abort_request("--reject-rest requires --adopt-names or --hold-names")

    adopt_names: set[str] | None = None
    if adopt_names_file:
        adopt_names = _read_names_file(Path(adopt_names_file), "--adopt-names")
    hold_names: set[str] = set()
    if hold_names_file:
        hold_names = _read_names_file(Path(hold_names_file), "--hold-names")
        # Holding without adopting anything is a legitimate week. Normalizing
        # to an empty set (rather than leaving it None) is what keeps the
        # unlisted items out of the interactive branch — otherwise
        # `--hold-names` alone would prompt for every other item.
        if adopt_names is None:
            adopt_names = set()

    return yes, adopt_names, hold_names, reject_rest


def _resolve_archive_specs(
    archive_specs: dict[str, str | None], data_root: Path
) -> dict[str, str | None]:
    """Settle the ``--archive-names`` request against the live store.

    Split out of :func:`_resolve_adopt_plan` (behaviour-preserving). Takes the
    raw mapping (the caller collision-checks it first, on the pre-drop name
    set) and returns the sidecar-ready mapping with already-archived entries
    dropped; aborts (exit 2) on a symlinked or genuinely-unknown name.
    """
    archive_specs = dict(archive_specs)
    archive_targets = set(archive_specs)
    if not archive_targets:
        return archive_specs

    # Store names, not staged names — a different namespace with the same
    # contract: one typo must leave every skill where it is. Derived from
    # MOLTBOOK_DATA_DIR at call time for the same reason
    # ``_handle_remove_skill`` does.
    skills_dir = _skills_dir(data_root)
    live = list(skills_dir.glob("*.md")) if skills_dir.is_dir() else []
    store_names = {p.name for p in live}
    # A symlinked candidate passes every name check and is then refused by
    # the primitive — after the successor was adopted with `supersedes:`
    # stamped on it, leaving the store holding both and the run at exit 1.
    # Symlink-ness is knowable now, so the "one typo leaves every skill
    # where it is" contract covers it (code review 2026-08-22 MEDIUM).
    symlinked = sorted(archive_targets & {p.name for p in live if p.is_symlink()})
    if symlinked:
        _abort_request(
            "--archive-names names symlink(s), not skills; name the referent instead",
            symlinked,
        )
    # Already retired by an earlier run: a no-op, not a typo. Re-running a
    # packet after a partial archive used to abort exit 2 with "unknown
    # skill name(s)", which misdiagnosed the state, pointed at the wrong
    # repair, and — because the abort is pre-loop — also stopped the
    # staged items in the same invocation from being adopted (silent-
    # failure review 2026-08-22 MEDIUM). Dropped from the request here,
    # before the successor checks, so a re-run retries only what is left.
    archive_dir = _archive_dir(data_root)
    archived_names = {p.name for p in archive_dir.glob("*.md")} if archive_dir.is_dir() else set()
    already = sorted((archive_targets - store_names) & archived_names)
    if already:
        print(
            "Already in the archive, nothing to do for: " + ", ".join(already),
            file=sys.stderr,
        )
        for name in already:
            del archive_specs[name]
        archive_targets = set(archive_specs)
    unknown_skills = sorted(archive_targets - store_names)
    if unknown_skills:
        _abort_request(
            "unknown skill name(s) for --archive-names (not in the store, and not "
            "already in .archive/)",
            unknown_skills,
        )
    return archive_specs


def _check_name_collisions(
    adopt_names: set[str] | None, hold_names: set[str], archive_targets: set[str]
) -> None:
    """Abort if any name appears in two of the three selection files.

    Split out of :func:`_resolve_adopt_plan` (behaviour-preserving). Not a
    precedence question: adopting a staged X into the store while archiving
    the store's X out of it cannot both be what the operator meant.
    """
    for left_flag, left, right_flag, right in (
        ("--adopt-names", adopt_names or set(), "--hold-names", hold_names),
        ("--adopt-names", adopt_names or set(), "--archive-names", archive_targets),
        ("--hold-names", hold_names, "--archive-names", archive_targets),
    ):
        both = sorted(left & right)
        if both:
            _abort_request(f"named in both {left_flag} and {right_flag}", both)


def _load_and_verify_staged(
    adopt_names: set[str] | None,
    hold_names: set[str],
    archive_specs: dict[str, str | None],
) -> tuple[list[Path], set[str]] | None:
    """Load ``.staged/*.meta.json`` and verify every requested name exists.

    Split out of :func:`_resolve_adopt_plan` (behaviour-preserving). Returns
    ``None`` when the run ends successfully without touching anything (the
    message is already printed); otherwise ``(meta_files, staged_names)``.
    Aborts (exit 2) on a name matching no staged item.
    """
    # Every name the operator asked about, whatever the verdict — the
    # existence check below must not pass a typo just because it landed in
    # the hold file rather than the adopt file.
    requested_names = (adopt_names or set()) | hold_names

    staged_dir_exists = config.STAGED_DIR.exists()
    meta_files: list[Path] = (
        sorted(config.STAGED_DIR.glob("*.meta.json"), key=_staged_sort_key)
        if staged_dir_exists
        else []
    )
    if not meta_files:
        # One block, two nouns. These three checks used to sit under both a
        # "no directory" and a "no files" arm, so the ADR-0097 archive guard
        # had to be added twice — exactly the drift a duplicated branch
        # produces (code review 2026-08-22).
        empty = "no staged files" if staged_dir_exists else "no staging directory"
        if requested_names:
            _abort_request(f"{empty} — unknown staged item name(s)", sorted(requested_names))
        if not archive_specs:
            print("No staged files." if staged_dir_exists else "No staging directory.")
            return None

    staged_names = {_staged_name(meta_file) for meta_file in meta_files}
    if adopt_names is not None:
        # Verify EVERY requested name before any unlink / adopt / hold /
        # reject / quarantine — a single typo must not half-apply the batch.
        unknown = sorted(requested_names - staged_names)
        if unknown:
            _abort_request("unknown staged item name(s)", unknown)

    return meta_files, staged_names


def _validate_supersede_pairings(
    archive_specs: dict[str, str | None],
    adopt_names: set[str] | None,
    staged_names: set[str],
    meta_files: list[Path],
    data_root: Path,
) -> None:
    """Abort unless every supersede successor lands in this same run.

    Split out of :func:`_resolve_adopt_plan` (behaviour-preserving). A
    supersede pairing is a promise that the replacement lands in the same
    run: the archived text stops being injected and something has to take
    its place. Checked here, before anything moves, so the operator fixes
    the packet transcription rather than discovering at exit 1 that half
    the batch applied. (The run-time half of the promise —
    ``_ARCHIVE_SUCCESSOR_NOT_ADOPTED`` — covers the successor that was
    named, selected, and then declined at the prompt.)
    """
    successors = {name for name in archive_specs.values() if name is not None}
    unstaged = sorted(successors - staged_names)
    if unstaged:
        _abort_request("--archive-names names supersede successor(s) that are not staged", unstaged)
    if adopt_names is not None:
        unselected = sorted(successors - adopt_names)
        if unselected:
            _abort_request(
                "--archive-names names supersede successor(s) that --adopt-names does not adopt",
                unselected,
            )

    if not successors:
        return

    # A supersede successor must be a SKILL. ADR-0097 D5 scopes the two
    # frontmatter halves to skills, and `superseded_by: <name>` only means
    # anything if a `mv` back into `skills/` restores the pair. Without
    # this, `old.md superseded-by identity.md` was accepted for a
    # `distill-identity` item and the supersede stamp synthesized a
    # whole frontmatter block on top of `identity.md` — a file that has
    # none by design, is injected verbatim into every session's system
    # prompt, and is documented three functions down as passing through
    # the adopt path byte-identical (code review 2026-08-22 CRITICAL).
    #
    # The sidecar's `target` is attacker-chosen, so it gets the loop's own
    # containment test before its parent is compared — never a second,
    # weaker reader of that field (module docstring).
    not_skills = []
    for meta_file in meta_files:
        name = _staged_name(meta_file)
        if name not in successors:
            continue
        meta = read_sidecar(meta_file)
        target_str = (meta or {}).get("target")
        if not target_str or not _writes_into_the_store(Path(target_str), data_root):
            not_skills.append(name)
    if not_skills:
        _abort_request(
            "--archive-names names supersede successor(s) that do not write into the skill store",
            sorted(not_skills),
        )


def _resolve_adopt_plan(args: argparse.Namespace) -> _AdoptPlan | None:
    """Reconcile the flags into a plan, or report why there is nothing to do.

    Returns ``None`` when the run ends successfully without touching anything
    (no staging directory, no staged files) — the message is already printed.
    Exits 2 on a request that cannot be honoured: mutually exclusive flags, a
    name in two of the three selection files, a name matching no staged item,
    an ``--archive-names`` entry matching no store skill, or a supersede
    pairing whose successor this run is not adopting. Every one of those
    happens before the caller's loop, so staging **and the store** are
    untouched when they fire.

    ``--archive-names`` alone is a complete request: the never-selected exit
    (ADR-0097 D5) runs on weeks with nothing staged, so an empty staging dir
    is a no-op for the loop rather than an early return.
    """
    yes, adopt_names, hold_names, reject_rest = _reconcile_selection_flags(args)

    archive_names_file = getattr(args, "archive_names", None)
    # Resolved once, above the first use: the store dir is compared against
    # resolved paths in three places below, and `:1032`'s glob only reads
    # `p.name`, so hoisting is behaviour-identical.
    data_root = config.MOLTBOOK_DATA_DIR.resolve()
    raw_archive_specs: dict[str, str | None] = {}
    if archive_names_file:
        raw_archive_specs = _read_archive_names_file(Path(archive_names_file), "--archive-names")
    # Collision-check the raw name set, before the already-archived drop: a
    # name in both --adopt-names and --archive-names must abort even when an
    # earlier partial run has already moved it to .archive/ — otherwise the
    # drop empties the archive side and the contradiction sails through
    # (code review 2026-08-28 MEDIUM).
    _check_name_collisions(adopt_names, hold_names, set(raw_archive_specs))
    archive_specs = _resolve_archive_specs(raw_archive_specs, data_root)

    audit_source: AuditSource = "stage-adopted-auto" if yes else "stage-adopted"
    if adopt_names is not None:
        # Per-item selection, but transcribed — no prompt shown in this
        # process. A distinct source keeps the audit trail honest about
        # provenance (2026-08-01 security review C1).
        audit_source = "stage-adopted-names"

    loaded = _load_and_verify_staged(adopt_names, hold_names, archive_specs)
    if loaded is None:
        return None
    meta_files, staged_names = loaded

    _validate_supersede_pairings(archive_specs, adopt_names, staged_names, meta_files, data_root)

    return _AdoptPlan(
        meta_files=meta_files,
        adopt_names=adopt_names,
        hold_names=hold_names,
        reject_rest=reject_rest,
        yes=yes,
        audit_source=audit_source,
        data_root=data_root,
        archive_specs=archive_specs,
    )


def _hold_one(meta_file: Path, plan: _AdoptPlan) -> _Outcome:
    """Leave one named item in staging with a recorded ``decision="held"``.

    Called only for names in ``plan.hold_names``; the caller owns that check.
    """
    item = _load_staged_item(meta_file, plan.data_root)
    if item is None:
        # Deliberately NOT quarantined, unlike every other branch.
        # Quarantining renames the sidecar out of the pending count, which for
        # an item the operator asked to KEEP would turn a requested hold into
        # a silent removal — and let the next batch overwrite the staged
        # content while the run still exited 0 (codex review 2026-08-15).
        # Counting it as a hold failure preserves both the item and the
        # non-zero exit.
        print(
            f"  Could not hold {_staged_name(meta_file)}: its sidecar did not load",
            file=sys.stderr,
        )
        return _Outcome.HOLD_FAILED
    print(f"\n{'=' * 60}")
    print(f"[{item.command}] {item.content_file.name} -> {item.target}")
    if _hold_staged_item(item, meta_file, audit_source=plan.audit_source):
        return _Outcome.HELD
    return _Outcome.HOLD_FAILED


def _reject_unselected(meta_file: Path, plan: _AdoptPlan) -> _Outcome:
    """Reject one item that ``--adopt-names`` did not select.

    **Unconditionally destructive — the caller owns the ``--reject-rest``
    check.** Forgetting the flag is supposed to leave the item staged, and
    that decision is made in :func:`_dispatch_staged_item`, not here.
    """
    item = _load_staged_item(meta_file, plan.data_root)
    if item is None:
        _quarantine_invalid_sidecar(meta_file)
        return _Outcome.SKIPPED
    # Unlink BEFORE logging: an audit row claiming "rejected" for an item
    # still sitting in staging is worse than a removed item with a missing row
    # (2026-08-01 security review H1 — this branch must not extend the
    # pre-existing log-then-mutate ordering).
    try:
        item.content_file.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)
    except OSError as err:
        print(f"  Could not reject {item.content_file.name}: {err}", file=sys.stderr)
        return _Outcome.REJECT_FAILED
    approval._log_approval(
        item.command,
        item.target,
        False,
        item.text,
        source=plan.audit_source,
        source_ids=item.source_ids,
        epistemic_counts=item.epistemic_counts,
    )
    print(f"  Rejected (not in --adopt-names): {item.content_file.name}")
    return _Outcome.REJECTED


def _print_surprise(surprise: object) -> None:
    """Show the ADR-0096 reading above the artifact at the human gate.

    Restored 2026-08-29 (RFC-0016). Read-only material for this decision, not
    a recommendation. ``ref cos p50`` / ``ref cos spread`` describe THIS
    candidate's own neighbourhood in the reference window — they are not the
    batch's discriminability budget, which is the spread of ``s_mean`` across
    the batch and is logged by ``insight_surprise.log_surprise`` at extraction
    time (the two are different distributions; the module says so explicitly).
    This function prints and returns; no caller reads its result, and no
    adoption outcome, ordering or count is a function of the value it shows.

    Every field is coerced rather than formatted straight from the sidecar. The
    sidecar is the one input this command treats as adversary-writable between
    stage and adopt, and a value that raises in a ``%.4f`` slot would raise out
    of the batch loop, leaving the remaining items staged and — via the
    ADR-0074 pending guard — blocking every future ``--stage`` run. An
    ``isinstance`` check alone does not buy that: ``json`` decodes an
    arbitrary-precision integer literal (``1`` followed by 400 zeros) to an
    ``int`` that passes the check and then makes ``float()`` raise
    ``OverflowError`` — not a ``ValueError``, so nothing upstream catches it —
    and it decodes bare ``NaN`` / ``Infinity`` to floats that pass everything
    and print as ``rank nan/inf``. Both are refused here (security review,
    2026-08-29).
    """
    if not isinstance(surprise, dict):
        return

    def _num(key: str) -> float | None:
        value = surprise.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        try:
            num = float(value)
        except (OverflowError, ValueError):
            return None
        return num if math.isfinite(num) else None

    fields = {
        key: _num(key)
        for key in ("rank", "of", "s_mean", "s_nn", "ref_k", "ref_cos_p50", "ref_cos_spread")
    }
    if any(v is None for v in fields.values()):
        print("  surprise: sidecar reading unusable (non-numeric field) — ignored")
        return
    print(
        f"  surprise: rank {fields['rank']:.0f}/{fields['of']:.0f} pre-gate clusters, "
        f"s_mean={fields['s_mean']:.4f} s_nn={fields['s_nn']:.4f} "
        f"(ref k={fields['ref_k']:.0f} cos p50={fields['ref_cos_p50']:.3f} "
        f"spread={fields['ref_cos_spread']:.3f})"
    )


def _dispatch_staged_item(meta_file: Path, plan: _AdoptPlan) -> _ItemResult:
    """Decide and apply one staged item's fate.

    The four fates are ordered by how specific the operator's instruction was:
    a name in ``--hold-names`` wins, then "not in ``--adopt-names``", then the
    ordinary approve/reject path.

    **Two rough edges follow from the quarantine on the adopt-failure path**,
    recorded here because nothing rediscovers them cheaply:

    - re-running the same ``--adopt-names`` file afterwards aborts with
      ``exit 2, "unknown staged item name(s)"`` and says nothing about
      corruption — the sidecar has been renamed ``*.invalid``, so the name no
      longer matches anything staged. An operator who regenerates the names
      file from the same packet reads that as "the packet is out of sync with
      staging", which is the wrong repair;
    - when the quarantine rename itself fails, the summary still reads
      "quarantined, not applied" while the item stays in the ADR-0074 pending
      count.

    Exit 1 is the right verdict in both.
    """
    name = _staged_name(meta_file)
    if name in plan.hold_names:
        return _ItemResult(_hold_one(meta_file, plan))

    if plan.adopt_names is not None and name not in plan.adopt_names:
        if not plan.reject_rest:
            return _ItemResult(_Outcome.LEFT)
        return _ItemResult(_reject_unselected(meta_file, plan))

    item = _load_staged_item(meta_file, plan.data_root)
    if item is None:
        _quarantine_invalid_sidecar(meta_file)
        if not plan.per_item and not plan.yes:
            # Bare interactive run: nobody asserted this item should be
            # adopted, and a human is reading the stderr line above.
            return _ItemResult(_Outcome.SKIPPED)
        # Either the operator named THIS item or --yes said "adopt everything
        # staged". Counting the load failure as a plain skip let a
        # non-interactive caller read a partially applied batch as success
        # (code review 2026-08-15) — the same hole the hold branch closes, and
        # --yes is the documented path for non-TTY callers. It cannot turn
        # into a recurring failure: the sidecar is quarantined here, so it is
        # out of the glob on the next run. Quarantine stays because an invalid
        # sidecar can never be adopted and leaving it would block every future
        # --stage run (ADR-0074 pending guard).
        print(
            f"  Could not adopt {name}: its sidecar did not load",
            file=sys.stderr,
        )
        return _ItemResult(_Outcome.ADOPT_FAILED)

    print(f"\n{'=' * 60}")
    print(f"[{item.command}] {item.content_file.name} -> {item.target}")
    _print_surprise(item.meta.get("surprise"))
    print(item.text)

    supersedes = plan.supersedes.get(name, ())
    if supersedes and not _writes_into_the_store(item.target, plan.data_root):
        # The plan checked this too, but against a FRESH sidecar read; the
        # write uses the snapshot `_load_staged_item` validated, and a
        # `.staged/` rewrite in between defeats a check made on the other one
        # (silent-failure review 2026-08-22 LOW 10 — reproduced with a
        # concurrent rewrite, which archived a skill with
        # `superseded_by: identity-2.md`). The invariant belongs on the bytes
        # being written, the same snapshot discipline `_mark_sidecar_held`
        # established. The plan-time copy stays: it fails fast with a message
        # that names the offending item, before anything is touched.
        print(
            f"  Could not adopt {name}: it supersedes {', '.join(supersedes)} but does "
            f"not write into the skill store ({item.target})",
            file=sys.stderr,
        )
        _quarantine_invalid_sidecar(meta_file)
        return _ItemResult(_Outcome.ADOPT_FAILED)

    approve_without_prompt = plan.yes or plan.per_item
    adopted_as = _adopt_write_item(
        item,
        yes=approve_without_prompt,
        audit_source=plan.audit_source,
        data_root=plan.data_root,
        supersedes=supersedes,
    )

    item.content_file.unlink(missing_ok=True)
    meta_file.unlink(missing_ok=True)
    if adopted_as is None:
        return _ItemResult(_Outcome.REJECTED)
    return _ItemResult(_Outcome.ADOPTED, adopted_as)


def _archive_named_skills(plan: _AdoptPlan, results: dict[str, _ItemResult]) -> list[_Outcome]:
    """Retire the ``--archive-names`` skills, after the adoption loop.

    **After**, not before, for two reasons that both point the same way: a
    supersede pairing must not archive anything until its replacement is
    actually on disk, and ``superseded_by:`` needs the successor's *final*
    filename, which the H5 collision guard only fixes at write time. A
    successor that was named but then declined at the prompt (or whose write
    failed) leaves its predecessor in the store and fails the run — the store
    losing a skill whose replacement never landed is the one outcome this
    ordering exists to prevent.

    ``results`` is keyed by staged item name; a missing key means the
    successor never reached the loop at all.

    **One residual state this ordering cannot prevent**, recorded because the
    exit code alone does not describe it: when the survivor was adopted and
    then its predecessor's move failed, the store holds both, and the
    survivor's ``supersedes:`` names a skill that is still live. The stamp
    cannot be deferred (it has to be inside the bytes the audit row hashes)
    and rolling back an audited write would be worse, so the failure line
    below names the file to repair instead (code review 2026-08-22).
    """
    if not plan.archive_specs:
        return []
    # Resolved on both sides: an adopted path comes from the sidecar's
    # ``target``, which producers build from the UNresolved
    # ``MOLTBOOK_DATA_DIR``, while the store dir here is resolved. A home
    # reached through a symlinked component would otherwise compare unequal
    # and slip the just-adopted guard below.
    adopted_paths = {
        _resolved_or_self(r.adopted_as) for r in results.values() if r.adopted_as is not None
    }
    outcomes: list[_Outcome] = []
    # ``plan.archive_sources`` and nothing rebuilt here: the module's standing
    # invariant is that the budget instrument and this loop mean the same
    # files (see ``instrument_metas`` and ``_print_system_budget_for_staged``),
    # and two independent derivations is precisely how that stops being true
    # — it already produced one bug in review (code review 2026-08-22).
    for source in plan.archive_sources:
        name = source.name
        successor_staged = plan.archive_specs[name]
        superseded_by: str | None = None
        if successor_staged is not None:
            landed = results.get(successor_staged)
            if landed is None or landed.adopted_as is None:
                print(
                    f"  {_ARCHIVE_SUCCESSOR_NOT_ADOPTED}: keeping {name} — "
                    f"{successor_staged} was not adopted in this run",
                    file=sys.stderr,
                )
                outcomes.append(_Outcome.ARCHIVE_FAILED)
                continue
            superseded_by = landed.adopted_as.name

        if _resolved_or_self(source) in adopted_paths:
            # This run wrote a staged item into the very file it was asked to
            # retire; archiving now would move the adoption into `.archive/`
            # while audit.jsonl said it was approved into the store.
            print(
                f"  {_ARCHIVE_REFUSED_JUST_ADOPTED}: keeping {name} — "
                "this run adopted a staged item into it",
                file=sys.stderr,
            )
            outcomes.append(_Outcome.ARCHIVE_FAILED)
            continue

        result = _archive_skill_file(source, data_root=plan.data_root, superseded_by=superseded_by)
        # `stage-archived-names`, never `plan.audit_source`: an archive is
        # decided in the names file and no prompt is ever shown for it, so
        # inheriting the staged items' source would stamp an archive-only run
        # as "stage-adopted" — a claim that a human answered y/N (2026-08-01
        # security review C1). Its own value rather than "stage-adopted-names"
        # because the source is what separates a retirement from an adoption
        # for a reader (silent-failure review 2026-08-22 HIGH).
        moved = _record_archive(
            result,
            command="adopt-staged",
            source_path=source,
            source="stage-archived-names",
            reason=(
                f"superseded by {superseded_by} (ADR-0097 D5 archive exit)"
                if superseded_by
                else "archived at the adopt gate (ADR-0097 D5 archive exit)"
            ),
        )
        if not moved:
            if superseded_by is not None:
                print(
                    f"  Repair needed: {superseded_by} was adopted and now claims "
                    f"'supersedes: {name}', but {name} is still in the store. "
                    "Re-run the archive, or drop the stamp.",
                    file=sys.stderr,
                )
            outcomes.append(_Outcome.ARCHIVE_FAILED)
            continue
        outcomes.append(_Outcome.ARCHIVED)
    return outcomes


def _report_adopt_outcomes(tally: Counter[_Outcome], plan: _AdoptPlan) -> None:
    """Print the summary and set the exit code.

    The exit code follows from the tally alone. **The summary also needs the
    plan**, because ``held`` and ``left staged`` are shown whenever they were
    REQUESTED, including as zero — ``0 held`` beside ``1 hold FAILURES`` is the
    line that tells the operator a requested hold produced nothing, and
    ``if tally[HELD]`` would drop exactly that case. Said explicitly because
    the earlier wording claimed "from the tally alone" of both, which invites a
    cleanup that removes the parameter and silently deletes those two clauses
    (2026-08-16 code review MEDIUM).
    """
    summary = (
        f"\n--- Summary: {tally[_Outcome.ADOPTED]} adopted, "
        f"{tally[_Outcome.REJECTED]} rejected, {tally[_Outcome.SKIPPED]} skipped"
    )
    if plan.hold_names:
        summary += f", {tally[_Outcome.HELD]} held"
    if plan.archive_specs:
        # Shown even as zero, for the same reason ``held`` is: ``0 archived``
        # beside ``2 archive FAILURES`` is what tells the operator the store
        # did not shrink at all.
        summary += f", {tally[_Outcome.ARCHIVED]} archived"
    if tally[_Outcome.ARCHIVE_FAILED]:
        summary += f", {tally[_Outcome.ARCHIVE_FAILED]} archive FAILURES (still in the store)"
    if tally[_Outcome.REJECT_FAILED]:
        summary += f", {tally[_Outcome.REJECT_FAILED]} reject FAILURES (still staged)"
    if tally[_Outcome.HOLD_FAILED]:
        summary += f", {tally[_Outcome.HOLD_FAILED]} hold FAILURES (staged, unrecorded)"
    if tally[_Outcome.ADOPT_FAILED]:
        summary += f", {tally[_Outcome.ADOPT_FAILED]} adopt FAILURES (quarantined, not applied)"
    if plan.per_item:
        summary += f", {tally[_Outcome.LEFT]} left staged"
    print(summary + " ---")

    still_staged = tally[_Outcome.HELD] + tally[_Outcome.HOLD_FAILED]
    if still_staged:
        # Say the cost at the point of decision, not next Saturday when the
        # weekly batch quietly fails to stage (ADR-0074 pending guard). Failed
        # holds are still sitting in staging, so they block just the same.
        print(
            f"{still_staged} item(s) still in staging: the next insight "
            "batch will be refused until they are decided."
        )
    if any(tally[outcome] for outcome in _Outcome if outcome.is_failure):
        # A non-interactive caller must not read a partially applied batch as
        # success (2026-08-01 security review H1).
        sys.exit(1)


def _handle_adopt_staged(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Walk the staging dir, run each staged file through the approval gate,
    and write accepted files to their target paths. Rejected and accepted
    items are both removed from staging to avoid repeated prompts on rerun.

    Three steps, and each is a separate function because they fail in
    different ways: :func:`_resolve_adopt_plan` reconciles the flags and can
    still refuse with staging untouched, :func:`_dispatch_staged_item` applies
    exactly one item and reports an :class:`_Outcome`, and
    :func:`_report_adopt_outcomes` derives the summary and the exit code from
    the tally.

    With ``--yes`` (``args.yes == True``) the interactive prompts are
    skipped and every staged item is auto-approved. This is the path that
    coding agents (Claude Code, etc.) use because their bash sandbox is
    non-TTY: ``input()`` would otherwise return EOF and reject everything.
    Auto-approved entries are recorded in the audit log with
    ``source="stage-adopted-auto"`` so they can be distinguished from
    interactively reviewed adoptions.

    With ``--adopt-names FILE`` (T-ADOPT-PERITEM) the items named in FILE
    (one staged filename per line) are adopted non-interactively, matched by
    name so the caller never depends on the iteration order (seq order, not
    packet numbering — the 2026-08-01 y/n-pipe gate nearly adopted the wrong
    items over exactly that mismatch). Items not listed are left staged by
    default; ``--reject-rest`` makes their rejection explicit (forgetting the
    flag errs on the safe side). These adoptions are recorded with
    ``source="stage-adopted-names"`` — per-item selection (unlike the blanket
    ``--yes`` batch) but transcribed rather than prompted, so the audit trail
    keeps the provenance distinct from a TTY y/N session (2026-08-01 security
    review C1). An empty names file aborts: combined with ``--reject-rest`` it
    would otherwise wipe the whole staging queue (C2).

    With ``--hold-names FILE`` (T-ADOPT-HOLD) the named items are left in
    staging with a ``decision="held"`` audit row. The gate has always offered
    three answers — approve / reject / hold — but the CLI carried a
    dichotomy, so holding one item meant leaving the entire remainder staged,
    un-rejected and unrecorded. The two files compose: adopt some, hold some,
    ``--reject-rest`` for everything else, one invocation, one decision each.
    A name in both files aborts rather than picking a winner. Held items
    deliberately still count toward the ADR-0074 pending guard, so a hold
    still defers the next batch — the change is that the block is now a
    recorded choice the guard can name (2026-08-15 decision).

    With ``--archive-names FILE`` (ADR-0097 Decision 5) the **store** skills
    named in FILE are retired: moved to ``skills/.archive/`` after the
    adoption loop, never unlinked. This is the store's first exit; before it
    the only way out was ``remove-skill``, which deleted. The names come from
    this argument and nothing else — not from a staged sidecar, not from the
    weekly reviewer's prose — which is what keeps adoption's threat model
    intact (module docstring). A line may pair a retirement with the staged
    item that replaces it (``old.md superseded-by new.md``), in which case
    the survivor gets ``supersedes:`` and the archived file
    ``superseded_by:``; a standalone line records neither half, because a
    ``superseded_by:`` with nothing after it is a pointer to nowhere and the
    audit row plus the file's new location already say "retired". The flag
    composes with everything (including ``--yes``, since it selects store
    files rather than staged ones) and works on a week with nothing staged,
    which is the never-selected exit's normal shape. **Restoring is a plain
    ``mv`` back into ``skills/``** — there is no restore command, and the
    archive holds no state a command would have to reconcile.

    Exit codes: 2 when the request itself cannot be honoured (see
    :func:`_resolve_adopt_plan`), 1 when part of what was asserted did not
    happen (see :meth:`_Outcome.is_failure`), archives included.
    """
    plan = _resolve_adopt_plan(args)
    if plan is None:
        return

    _print_system_budget_for_staged(
        plan.instrument_metas, plan.data_root, archived_paths=plan.archive_sources
    )

    if plan.adopt_names is not None:
        rest_fate = "rejected" if plan.reject_rest else "left staged"
        held_note = f", holding {len(plan.hold_names)}" if plan.hold_names else ""
        print(
            f"Per-item mode: adopting {len(plan.adopt_names)} of "
            f"{len(plan.meta_files)} staged item(s){held_note}; the rest are {rest_fate}."
        )
    elif plan.yes:
        print(
            f"Auto-approve mode (--yes): adopting "
            f"{len(plan.meta_files)} staged item(s) without prompts."
        )
    if plan.archive_specs:
        print(
            f"Archiving {len(plan.archive_specs)} store skill(s) to "
            f"{_archive_dir(plan.data_root)}/ after the adoption loop."
        )

    results = {
        _staged_name(meta_file): _dispatch_staged_item(meta_file, plan)
        for meta_file in plan.meta_files
    }
    tally: Counter[_Outcome] = Counter(result.outcome for result in results.values())
    tally.update(_archive_named_skills(plan, results))
    _report_adopt_outcomes(tally, plan)


def _add_adopt_staged_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Auto-approve all staged items without prompting "
        "(for non-TTY / coding-agent workflows where stdin is not interactive)",
    )
    parser.add_argument(
        "--adopt-names",
        metavar="FILE",
        help="Adopt exactly the staged items named in FILE (one staged filename "
        "per line), non-interactively. Names are matched against staged item "
        "filenames, so callers never depend on the iteration order. Any unknown "
        "name aborts the whole run before anything is touched. Items not listed "
        "are left staged unless --reject-rest is given. Mutually exclusive with "
        "--yes.",
    )
    parser.add_argument(
        "--hold-names",
        metavar="FILE",
        help="Hold exactly the staged items named in FILE (one staged filename "
        "per line): leave them in staging, but record a 'held' decision for "
        "each so the deferral is on the audit trail rather than looking like "
        "an item nobody reviewed. Composes with --adopt-names and "
        "--reject-rest; a name in both files aborts. Held items still block "
        "the next insight batch (ADR-0074), which is now reported rather than "
        "discovered a week later. Mutually exclusive with --yes.",
    )
    parser.add_argument(
        "--archive-names",
        metavar="FILE",
        help="Retire the STORE skills named in FILE (one skill filename per "
        "line) by moving them to skills/.archive/ after the adoption loop — "
        "never by deleting them; restoring is a plain mv (ADR-0097 D5). A "
        "line may pair a retirement with its replacement "
        "('old.md superseded-by new-staged-name.md'), which records "
        "supersedes: / superseded_by: on the two files; the successor must be "
        "adopted in the same run. Any unknown skill name, malformed line, or "
        "name shared with --adopt-names / --hold-names aborts the whole run "
        "before anything moves. Works with nothing staged. These names come "
        "only from FILE — never from a staged sidecar or reviewer output.",
    )
    parser.add_argument(
        "--reject-rest",
        action="store_true",
        help="With --adopt-names / --hold-names: reject (remove from staging, "
        "with an audit record) the staged items NOT listed in either. Default "
        "is to leave them staged.",
    )


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="adopt-staged",
        help="Review files in the staging dir through the approval gate and adopt accepted ones",
        handler=_handle_adopt_staged,
        tier=Tier.NO_LLM,
        add_arguments=_add_adopt_staged_arguments,
    ),
)
