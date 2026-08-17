"""adopt-staged / remove-skill: promote or drop staged value-layer items.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).

Threat model (recorded 2026-08-15 with the T-WRITE-TMP-NOFOLLOW fix, which
closed the one exception). The adversary is whoever can write ``.staged/``:
the sidecar is user-writable between stage and adopt, so ``target``,
``command``, ``action`` and ``sources`` are all attacker-chosen. What that
buys them is bounded to MOLTBOOK_HOME and no further.

* ``target`` is containment-checked twice in ``_load_staged_item`` — once
  resolved, once literal-with-resolved-parent — because reads follow symlinks
  and writes do not. Either check alone leaks in one direction.
* ``sources`` is otherwise unvalidated, but ``_delete_adopted_sources``
  requires each name to resolve into the target's own directory, so the reach
  is "any file beside the target", not any file.
* ``action: drop`` unlinks the target with no allowlist — again any file in
  the store, and ``unlink`` removes a link rather than its referent.

Deliberately no additional gate: each of these is a subset of what writing
``.staged/`` already grants, and a guessed allowlist would fail closed on
legitimate curation (a stocktake merge names arbitrary sibling skills)
without removing a capability. The primitives that did exceed the store —
``write_restricted``'s predictable temp sibling, which followed a pre-placed
symlink *or hardlink* to an arbitrary path — are fixed at the writer
(``core/_io.py``), not papered over here.
"""

from __future__ import annotations

import argparse
import json as json_mod
import logging
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any

from ..adapters.moltbook import config
from ..core.domain import (
    load_constitution,
)
from . import approval
from .approval import AuditSource
from .registry import CommandSpec, Tier
from .staging import read_sidecar

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
    action: str
    sources: list[str]
    source_ids: Sequence[str] | None
    epistemic_counts: dict[str, int] | None
    meta: dict[str, Any]


def _target_inside_data_root(target: Path, data_root: Path) -> bool:
    """Containment for a staged target, on BOTH readings of the path.

    The operations disagree about which reading they mean, so the check has
    to satisfy each. ``_print_system_budget_for_staged`` READS the target and
    a read follows every link, so the referent must be inside. The write
    (``write_restricted`` -> ``os.replace``) and the drop (``unlink``) act on
    the LITERAL path — they swap or remove the link itself, never its
    referent — so the literal location must be inside too. The parent IS
    resolved on the literal side, because ``os.replace`` follows parent
    symlinks; the same idiom ``_replaces_canonical_target`` settled on for
    the mirror-image bug found the same day.

    Checking only the referent let a symlink sitting OUTSIDE the store and
    pointing back in pass as "inside", after which the adoption landed
    outside (security review 2026-08-15, reproduced). Checking only the
    literal path would let a link inside the store expose an outside file to
    the reader.

    One predicate shared by the loader and the budget instrument, because
    the instrument's whole job is to project what the loop will do: an item
    the loop refuses must not appear in the reading the operator approves
    against (codex review 2026-08-15).
    """
    try:
        return target.resolve().is_relative_to(data_root) and (
            target.parent.resolve() / target.name
        ).is_relative_to(data_root)
    except OSError:
        return False


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
        action=meta.get("action", "merge"),
        sources=meta.get("sources") or [],
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


def _adopt_drop_item(item: _StagedItem, *, yes: bool, audit_source: AuditSource) -> bool:
    """Delete the drop target after approval; True when adopted."""
    approved = True if yes else approval._approve_delete(item.target)
    approval._log_approval(
        item.command,
        item.target,
        approved,
        item.text,
        source=audit_source,
        source_ids=item.source_ids,
        epistemic_counts=item.epistemic_counts,
    )
    if not approved:
        print("  Kept.")
        return False
    if item.target.exists():
        item.target.unlink()
        print(f"  Deleted {item.target.name}")
    else:
        print(f"  Already absent: {item.target.name}")
    return True


def _delete_adopted_sources(target: Path, sources: Sequence[str]) -> None:
    """Delete the merge's original filenames once the merged result is adopted."""
    target_parent = target.parent.resolve()
    try:
        target_resolved = target.resolve()
    except OSError:
        target_resolved = target
    for src_name in sources:
        src_path = (target.parent / src_name).resolve()
        try:
            same_dir = src_path.parent == target_parent
        except OSError:
            same_dir = False
        if not same_dir:
            print(f"  Skipped source delete (outside target dir): {src_name}")
            continue
        # Guard: when the merged title collides with an original
        # filename, src_path == target. Skip so we don't delete
        # the file we just wrote.
        if src_path == target_resolved:
            continue
        if src_path.exists():
            src_path.unlink()
            print(f"  Deleted {src_name}")


def _adopt_write_item(
    item: _StagedItem, *, yes: bool, audit_source: AuditSource, data_root: Path
) -> bool:
    """Write the staged text to its target after approval; True when adopted."""
    from ..core._io import write_restricted
    from ..core.artifact_extraction import canonicalize_frontmatter_name, slug_from_stem

    # H5 collision guard — exempt when a stocktake merge deliberately reuses
    # one of its own source names (merge-into-source overwrite), or when the
    # staging command owns its target and replacing it is the intent
    # (T-ADOPT-OVERWRITE-TARGETS; see _replaces_canonical_target).
    target = item.target
    replaces_canonical = _replaces_canonical_target(item.command, target, data_root)
    if target.name not in (item.sources or ()) and not replaces_canonical:
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
    # One-canonical-identity invariant, established AT the write boundary
    # (weekly 2026-08-08 F1.3): the extraction-time canonicalization
    # (insight/rules-distill) is a producer convention, not an invariant —
    # text staged before that fix landed, staged by a future producer that
    # skips it, or renamed by the collision guard just above would all enter
    # the live store with a frontmatter ``name:`` that ``ls`` never shows.
    # Idempotent normalization, not a gate: an already-canonical candidate
    # (and any body without frontmatter — identity, constitution, legacy
    # rules) passes through byte-identical, and nothing is rejected.
    text = canonicalize_frontmatter_name(item.text, slug_from_stem(target.stem))
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
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    to_write = text if text.endswith("\n") else text + "\n"
    write_restricted(target, to_write)
    # skill-stocktake merges pass the original filenames in `sources`
    # so they get deleted once the merged result is adopted.
    _delete_adopted_sources(target, item.sources)
    return True


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


def _print_system_budget_for_staged(meta_files: Sequence[Path], data_root: Path) -> None:
    """Print the read-only system-prompt budget projection for a staged batch.

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

    def _inside_data_root(path: Path) -> bool:
        try:
            return path.resolve().is_relative_to(data_root.resolve())
        except OSError:
            return False

    try:
        from ..core.llm import system_prompt_budget_reading

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
                sources = meta.get("sources") or []
                if meta.get("action", "merge") == "drop":
                    if target.exists():
                        replaced_texts.append(target.read_text(encoding="utf-8"))
                    continue
                content_file = meta_file.parent / meta_file.name[: -len(".meta.json")]
                text = content_file.read_text(encoding="utf-8")
                new_texts.append(text)
                # Subtract the existing target only when adoption really
                # replaces it: an in-place rewrite/merge (target listed in
                # sources), a canonical replacement (identity / constitution),
                # or an idempotent identical write. A same-name,
                # different-content, non-source target gets a `-N.md` suffix
                # from approval._collision_free_path and the original survives —
                # subtracting it would under-project (codex 2026-07-10 P2).
                # This asks the same question as the write path above, so the
                # two cannot disagree about whether the old text survives.
                if target.exists():
                    existing = target.read_text(encoding="utf-8")
                    if (
                        target.name in sources
                        or _replaces_canonical_target(meta.get("command") or "", target, data_root)
                        or existing.strip() == text.strip()
                    ):
                        replaced_texts.append(existing)
                for src_name in sources:
                    src_path = target.parent / src_name
                    if src_path != target and _inside_data_root(src_path) and src_path.exists():
                        replaced_texts.append(src_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
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


def _read_names_file(names_file: Path, flag: str) -> set[str]:
    """Read a per-item selection file (one staged filename per line).

    Shared by ``--adopt-names`` and ``--hold-names`` so the two cannot drift
    on the abort contracts below; ``flag`` only names the offender in the
    messages.

    Blank lines and surrounding whitespace are ignored; duplicates collapse.
    An unreadable file aborts with exit code 2 — falling back to "select
    nothing" or, worse, "select everything" would silently invert the
    operator's per-item decision (T-ADOPT-PERITEM).
    """
    try:
        raw = names_file.read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        # ValueError covers UnicodeDecodeError — same clean-abort contract as
        # an unreadable file (2026-08-01 security review L1).
        print(f"Error: cannot read {flag} file {names_file}: {err}", file=sys.stderr)
        sys.exit(2)
    names = {name for line in raw.splitlines() if (name := line.strip())}
    if not names:
        # An empty selection is a writer bug (truncated write, crashed
        # producer), not a valid decision: combined with --reject-rest it
        # would silently delete the ENTIRE staging queue while logging each
        # item as an individually decided rejection (2026-08-01 security
        # review C2, reproduced). Abort exactly like the unreadable case.
        print(
            f"Error: {flag} file {names_file} contains no names; "
            "aborting (an empty selection is never a decision).",
            file=sys.stderr,
        )
        sys.exit(2)
    return names


def _mark_sidecar_held(meta_file: Path, meta: dict[str, Any]) -> bool:
    """Stamp ``held`` / ``held_at`` onto the sidecar; False (loudly) on failure.

    The audit row records the decision, but it lands in ``logs/audit.jsonl``,
    which the next staging run never reads. The marker is what lets the
    ADR-0074 pending guard say *why* it is refusing to stage a new batch
    instead of reporting an anonymous count of leftovers. Every other key is
    preserved verbatim — ``seq`` in particular, which drives adoption order.

    ``meta`` is the snapshot ``_load_staged_item`` validated, deliberately
    NOT a fresh read: re-reading let a sidecar rewritten in between receive
    the marker while ``_log_hold`` described the item loaded before it, so
    the file said held and the audit row named a different target (codex
    review 2026-08-15).
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

    @property
    def is_failure(self) -> bool:
        """True when what was asserted did not happen (exit 1).

        Not the same as "not adopted": SKIPPED and LEFT are outcomes nobody
        asserted against, and counting them here would fail a bare
        interactive run that simply declined an item.
        """
        return self in (_Outcome.REJECT_FAILED, _Outcome.HOLD_FAILED, _Outcome.ADOPT_FAILED)


@dataclass(frozen=True)
class _AdoptPlan:
    """The reconciled request — every flag resolved, every name verified.

    Built before the first destructive operation, which is the property that
    matters: `--adopt-names` with one typo must leave staging untouched, and
    that can only be guaranteed by finishing the reconciliation before the
    loop starts rather than by checking as it goes.

    ``adopt_names is None`` means "every staged item" (a bare interactive run
    or ``--yes``); a set means per-item selection by staged filename.
    """

    meta_files: list[Path]
    adopt_names: set[str] | None
    hold_names: set[str]
    reject_rest: bool
    yes: bool
    audit_source: AuditSource
    data_root: Path

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


def _resolve_adopt_plan(args: argparse.Namespace) -> _AdoptPlan | None:
    """Reconcile the flags into a plan, or report why there is nothing to do.

    Returns ``None`` when the run ends successfully without touching anything
    (no staging directory, no staged files) — the message is already printed.
    Exits 2 on a request that cannot be honoured: mutually exclusive flags, a
    name in both files, or a name matching no staged item. Every one of those
    happens before the caller's loop, so staging is untouched when they fire.
    """
    yes = getattr(args, "yes", False)
    adopt_names_file = getattr(args, "adopt_names", None)
    hold_names_file = getattr(args, "hold_names", None)
    reject_rest = getattr(args, "reject_rest", False)

    if yes and (adopt_names_file or hold_names_file):
        print(
            "Error: --adopt-names / --hold-names and --yes are mutually exclusive "
            "(per-item selection vs adopt-everything).",
            file=sys.stderr,
        )
        sys.exit(2)
    if reject_rest and not (adopt_names_file or hold_names_file):
        print(
            "Error: --reject-rest requires --adopt-names or --hold-names.",
            file=sys.stderr,
        )
        sys.exit(2)

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

    both = sorted(hold_names & (adopt_names or set()))
    if both:
        print(
            "Error: named in both --adopt-names and --hold-names: " + ", ".join(both),
            file=sys.stderr,
        )
        print("No changes made; staging left untouched.", file=sys.stderr)
        sys.exit(2)

    audit_source: AuditSource = "stage-adopted-auto" if yes else "stage-adopted"
    if adopt_names is not None:
        # Per-item selection, but transcribed — no prompt shown in this
        # process. A distinct source keeps the audit trail honest about
        # provenance (2026-08-01 security review C1).
        audit_source = "stage-adopted-names"

    # Every name the operator asked about, whatever the verdict — the
    # existence check below must not pass a typo just because it landed in
    # the hold file rather than the adopt file.
    requested_names = (adopt_names or set()) | hold_names

    if not config.STAGED_DIR.exists():
        if requested_names:
            print(
                "Error: no staging directory — unknown staged item name(s): "
                + ", ".join(sorted(requested_names)),
                file=sys.stderr,
            )
            sys.exit(2)
        print("No staging directory.")
        return None

    meta_files = sorted(config.STAGED_DIR.glob("*.meta.json"), key=_staged_sort_key)
    if not meta_files:
        if requested_names:
            print(
                "Error: no staged files — unknown staged item name(s): "
                + ", ".join(sorted(requested_names)),
                file=sys.stderr,
            )
            sys.exit(2)
        print("No staged files.")
        return None

    if adopt_names is not None:
        # Verify EVERY requested name before any unlink / adopt / hold /
        # reject / quarantine — a single typo must not half-apply the batch.
        staged_names = {_staged_name(meta_file) for meta_file in meta_files}
        unknown = sorted(requested_names - staged_names)
        if unknown:
            print(
                "Error: unknown staged item name(s): " + ", ".join(unknown),
                file=sys.stderr,
            )
            print("No changes made; staging left untouched.", file=sys.stderr)
            sys.exit(2)

    return _AdoptPlan(
        meta_files=meta_files,
        adopt_names=adopt_names,
        hold_names=hold_names,
        reject_rest=reject_rest,
        yes=yes,
        audit_source=audit_source,
        data_root=config.MOLTBOOK_DATA_DIR.resolve(),
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

    Read-only material for this decision, not a recommendation:
    ``ref cos spread`` is the ambiguity note — a narrow spread means the rank
    separates very little (see ``core/insight_surprise.py``).

    Every field is coerced rather than formatted straight from the sidecar. The
    sidecar is the one input this command treats as adversary-writable between
    stage and adopt, and a non-numeric value in a ``%.4f`` slot would raise out
    of the batch loop, leaving the remaining items staged and — via the
    ADR-0074 pending guard — blocking every future ``--stage`` run.
    """
    if not isinstance(surprise, dict):
        return

    def _num(key: str) -> float | None:
        value = surprise.get(key)
        return (
            float(value)
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            else None
        )

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


def _dispatch_staged_item(meta_file: Path, plan: _AdoptPlan) -> _Outcome:
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
        return _hold_one(meta_file, plan)

    if plan.adopt_names is not None and name not in plan.adopt_names:
        if not plan.reject_rest:
            return _Outcome.LEFT
        return _reject_unselected(meta_file, plan)

    item = _load_staged_item(meta_file, plan.data_root)
    if item is None:
        _quarantine_invalid_sidecar(meta_file)
        if not plan.per_item and not plan.yes:
            # Bare interactive run: nobody asserted this item should be
            # adopted, and a human is reading the stderr line above.
            return _Outcome.SKIPPED
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
        return _Outcome.ADOPT_FAILED

    print(f"\n{'=' * 60}")
    print(f"[{item.command}] {item.content_file.name} -> {item.target}")
    _print_surprise(item.meta.get("surprise"))
    print(item.text)

    approve_without_prompt = plan.yes or plan.per_item
    if item.action == "drop":
        ok = _adopt_drop_item(item, yes=approve_without_prompt, audit_source=plan.audit_source)
    else:
        ok = _adopt_write_item(
            item,
            yes=approve_without_prompt,
            audit_source=plan.audit_source,
            data_root=plan.data_root,
        )

    item.content_file.unlink(missing_ok=True)
    meta_file.unlink(missing_ok=True)
    return _Outcome.ADOPTED if ok else _Outcome.REJECTED


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

    Exit codes: 2 when the request itself cannot be honoured (see
    :func:`_resolve_adopt_plan`), 1 when part of what was asserted did not
    happen (see :meth:`_Outcome.is_failure`).
    """
    plan = _resolve_adopt_plan(args)
    if plan is None:
        return

    _print_system_budget_for_staged(plan.instrument_metas, plan.data_root)

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

    tally: Counter[_Outcome] = Counter(
        _dispatch_staged_item(meta_file, plan) for meta_file in plan.meta_files
    )
    _report_adopt_outcomes(tally, plan)


def _handle_remove_skill(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Delete a skill from ``skills_dir`` with an audit trail.

    The single manual-CRUD entry point for the skills directory. Writes an
    ``audit.jsonl`` record (command="remove-skill") capturing the reason,
    decision, and content hash so the deletion is reviewable alongside the
    automated approval-gate history (ADR-0012).

    With ``--yes`` the interactive prompt is skipped (non-TTY workflows).
    With ``--dry-run`` the target is resolved and printed but nothing is
    written or removed.
    """
    reason = (args.reason or "").strip()
    if not reason:
        print(
            "Error: --reason is required and must be non-empty.",
            file=sys.stderr,
        )
        sys.exit(2)

    # Derive from config.MOLTBOOK_DATA_DIR (not the import-time config.SKILLS_DIR constant) so
    # this handler honors a per-call / test-patched data dir — the deletion path
    # must resolve against the same home the rest of the invocation uses.
    skills_dir = (config.MOLTBOOK_DATA_DIR / "skills").resolve()
    name = args.name
    if not name.endswith(".md"):
        name = f"{name}.md"
    target = (skills_dir / name).resolve()

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

    if not target.is_file():
        print(f"Error: skill not found: {target}", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "dry_run", False):
        print(f"[dry-run] would remove: {target}")
        print(f"[dry-run] reason: {reason}")
        return

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as err:
        print(f"Error: cannot read {target}: {err}", file=sys.stderr)
        sys.exit(1)

    yes = getattr(args, "yes", False)
    source: AuditSource = "direct-remove-auto" if yes else "direct-remove"
    approved = True if yes else approval._approve_delete(target)

    approval._log_approval(
        command="remove-skill",
        path=target,
        approved=approved,
        content=text,
        source=source,
        reason=reason,
    )

    if approved:
        target.unlink()
        print(f"Removed {target.name}")
    else:
        print("Kept.")


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
        "--reject-rest",
        action="store_true",
        help="With --adopt-names / --hold-names: reject (remove from staging, "
        "with an audit record) the staged items NOT listed in either. Default "
        "is to leave them staged.",
    )


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
        "-y",
        "--yes",
        action="store_true",
        help="Skip the interactive prompt "
        "(for non-TTY / coding-agent workflows where stdin is not interactive)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and print the target without deleting or writing audit",
    )


COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="adopt-staged",
        help="Review files in the staging dir through the approval gate and adopt accepted ones",
        handler=_handle_adopt_staged,
        tier=Tier.NO_LLM,
        add_arguments=_add_adopt_staged_arguments,
    ),
    CommandSpec(
        name="remove-skill",
        help="Remove a skill from skills_dir with an audit trail",
        handler=_handle_remove_skill,
        tier=Tier.NO_LLM,
        add_arguments=_add_remove_skill_arguments,
    ),
)
