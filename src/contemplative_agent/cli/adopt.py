"""adopt-staged / remove-skill: promote or drop staged value-layer items.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import json as json_mod
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

from ..adapters.moltbook import config
from ..core.domain import (
    load_constitution,
)
from . import approval
from .approval import AuditSource
from .registry import CommandSpec, Tier

logger = logging.getLogger(__name__)


# ADR-0074: one JSON record per staged insight candidate. Feeds the novelty
# gate's known-theme inventory so a theme counts as "considered" once it
# reached human review, whether or not it was adopted.
INSIGHT_STAGED_LEDGER_PATH = config.MOLTBOOK_DATA_DIR / "logs" / "insight-staged.jsonl"


@dataclass(frozen=True)
class _StagedItem:
    """One staged artifact parsed from its ``.meta.json`` sidecar."""

    content_file: Path
    target: Path
    command: str
    text: str
    action: str
    sources: list[str]
    source_ids: Sequence[str] | None
    epistemic_counts: dict[str, int] | None


def _load_staged_item(meta_file: Path, data_root: Path) -> _StagedItem | None:
    """Parse and validate one staged entry; None (with a printed reason) on skip."""
    try:
        meta = json_mod.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        print(f"  Skipped (meta read error): {meta_file.name}: {err}")
        return None

    target_str = meta.get("target")
    command = meta.get("command")
    if not target_str or not command:
        print(f"  Skipped (invalid meta): {meta_file.name}")
        return None

    target = Path(target_str)
    # Defense in depth: the meta.json is user-writable between stage and
    # adopt, so re-verify the target still lives inside MOLTBOOK_HOME.
    try:
        inside = target.resolve().is_relative_to(data_root)
    except OSError:
        inside = False
    if not inside:
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
    )


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


def _adopt_write_item(item: _StagedItem, *, yes: bool, audit_source: AuditSource) -> bool:
    """Write the staged text to its target after approval; True when adopted."""
    from ..core._io import write_restricted

    # H5 collision guard — exempt when a stocktake merge deliberately reuses
    # one of its own source names (merge-into-source overwrite).
    target = item.target
    if target.name not in (item.sources or ()):
        target = approval._collision_free_path(target, item.text)
    approved = True if yes else approval._approve_write(target)
    approval._log_approval(
        item.command,
        target,
        approved,
        item.text,
        source=audit_source,
        source_ids=item.source_ids,
        epistemic_counts=item.epistemic_counts,
    )
    if not approved:
        print("Skipped.")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    to_write = item.text if item.text.endswith("\n") else item.text + "\n"
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
    try:
        seq = json_mod.loads(meta_file.read_text(encoding="utf-8")).get("seq")
    except (OSError, ValueError):
        seq = None
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
                meta = json_mod.loads(meta_file.read_text(encoding="utf-8"))
                if not meta.get("target"):
                    continue
                target = Path(meta["target"])
                if not _inside_data_root(target):
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
                # sources) or an idempotent identical write. A same-name,
                # different-content, non-source target gets a `-N.md` suffix
                # from approval._collision_free_path and the original survives —
                # subtracting it would under-project (codex 2026-07-10 P2).
                if target.exists() and (
                    target.name in sources
                    or target.read_text(encoding="utf-8").strip() == text.strip()
                ):
                    replaced_texts.append(target.read_text(encoding="utf-8"))
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


def _read_adopt_names(names_file: Path) -> list[str]:
    """Read the ``--adopt-names`` file (one staged filename per line).

    Blank lines and surrounding whitespace are ignored; duplicates collapse.
    An unreadable file aborts with exit code 2 — falling back to "adopt
    nothing" or, worse, "adopt everything" would silently invert the
    operator's per-item decision (T-ADOPT-PERITEM).
    """
    try:
        raw = names_file.read_text(encoding="utf-8")
    except (OSError, ValueError) as err:
        # ValueError covers UnicodeDecodeError — same clean-abort contract as
        # an unreadable file (2026-08-01 security review L1).
        print(f"Error: cannot read --adopt-names file {names_file}: {err}", file=sys.stderr)
        sys.exit(2)
    seen: dict[str, None] = {}
    for line in raw.splitlines():
        name = line.strip()
        if name:
            seen.setdefault(name)
    if not seen:
        # An empty selection is a writer bug (truncated write, crashed
        # producer), not a valid decision: combined with --reject-rest it
        # would silently delete the ENTIRE staging queue while logging each
        # item as an individually decided rejection (2026-08-01 security
        # review C2, reproduced). Abort exactly like the unreadable case.
        print(
            f"Error: --adopt-names file {names_file} contains no names; "
            "aborting (an empty selection is never a decision).",
            file=sys.stderr,
        )
        sys.exit(2)
    return list(seen)


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


def _handle_adopt_staged(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Walk the staging dir, run each staged file through the approval gate,
    and write accepted files to their target paths. Rejected and accepted
    items are both removed from staging to avoid repeated prompts on rerun.

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
    items over exactly that mismatch). All names are verified against the
    staged set BEFORE any destructive operation: one unknown name aborts the
    whole run with the offending names listed and staging untouched. Items
    not listed are left staged by default; ``--reject-rest`` makes their
    rejection explicit (forgetting the flag errs on the safe side). These
    adoptions are recorded with ``source="stage-adopted-names"`` — per-item
    selection (unlike the blanket ``--yes`` batch) but transcribed rather
    than prompted, so the audit trail keeps the provenance distinct from a
    TTY y/N session (2026-08-01 security review C1). An empty names file
    aborts: combined with ``--reject-rest`` it would otherwise wipe the
    whole staging queue (C2).
    """
    yes = getattr(args, "yes", False)
    adopt_names_file = getattr(args, "adopt_names", None)
    reject_rest = getattr(args, "reject_rest", False)

    if adopt_names_file and yes:
        print(
            "Error: --adopt-names and --yes are mutually exclusive "
            "(per-item selection vs adopt-everything).",
            file=sys.stderr,
        )
        sys.exit(2)
    if reject_rest and not adopt_names_file:
        print("Error: --reject-rest requires --adopt-names.", file=sys.stderr)
        sys.exit(2)

    # None = process every staged item (interactive or --yes);
    # a set = per-item selection by staged filename.
    adopt_names: set[str] | None = None
    if adopt_names_file:
        adopt_names = set(_read_adopt_names(Path(adopt_names_file)))

    audit_source: AuditSource = "stage-adopted-auto" if yes else "stage-adopted"
    if adopt_names is not None:
        # Per-item selection, but transcribed — no prompt shown in this
        # process. A distinct source keeps the audit trail honest about
        # provenance (2026-08-01 security review C1).
        audit_source = "stage-adopted-names"

    if not config.STAGED_DIR.exists():
        if adopt_names:
            print(
                "Error: no staging directory — unknown staged item name(s): "
                + ", ".join(sorted(adopt_names)),
                file=sys.stderr,
            )
            sys.exit(2)
        print("No staging directory.")
        return

    meta_files = sorted(config.STAGED_DIR.glob("*.meta.json"), key=_staged_sort_key)
    if not meta_files:
        if adopt_names:
            print(
                "Error: no staged files — unknown staged item name(s): "
                + ", ".join(sorted(adopt_names)),
                file=sys.stderr,
            )
            sys.exit(2)
        print("No staged files.")
        return

    if adopt_names is not None:
        # Verify EVERY requested name before any unlink / adopt / reject /
        # quarantine — a single typo must not half-apply the batch.
        staged_names = {_staged_name(meta_file) for meta_file in meta_files}
        unknown = sorted(adopt_names - staged_names)
        if unknown:
            print(
                "Error: unknown staged item name(s): " + ", ".join(unknown),
                file=sys.stderr,
            )
            print("No changes made; staging left untouched.", file=sys.stderr)
            sys.exit(2)

    data_root = config.MOLTBOOK_DATA_DIR.resolve()
    # In per-item mode, project the budget for the items actually being
    # adopted — unselected items either stay staged or are rejected, and
    # neither outcome changes the system prompt.
    instrument_metas = meta_files
    if adopt_names is not None:
        instrument_metas = [mf for mf in meta_files if _staged_name(mf) in adopt_names]
    _print_system_budget_for_staged(instrument_metas, data_root)

    if adopt_names is not None:
        rest_fate = "rejected" if reject_rest else "left staged"
        print(
            f"Per-item mode (--adopt-names): adopting {len(adopt_names)} of "
            f"{len(meta_files)} staged item(s); the rest are {rest_fate}."
        )
    elif yes:
        print(
            f"Auto-approve mode (--yes): adopting {len(meta_files)} staged item(s) without prompts."
        )

    adopted = 0
    rejected = 0
    skipped = 0
    left = 0
    reject_failures = 0
    for meta_file in meta_files:
        if adopt_names is not None and _staged_name(meta_file) not in adopt_names:
            if not reject_rest:
                left += 1
                continue
            item = _load_staged_item(meta_file, data_root)
            if item is None:
                _quarantine_invalid_sidecar(meta_file)
                skipped += 1
                continue
            # Unlink BEFORE logging: an audit row claiming "rejected" for an
            # item still sitting in staging is worse than a removed item with
            # a missing row (2026-08-01 security review H1 — the new branch
            # must not extend the pre-existing log-then-mutate ordering).
            try:
                item.content_file.unlink(missing_ok=True)
                meta_file.unlink(missing_ok=True)
            except OSError as err:
                print(
                    f"  Could not reject {item.content_file.name}: {err}",
                    file=sys.stderr,
                )
                reject_failures += 1
                continue
            approval._log_approval(
                item.command,
                item.target,
                False,
                item.text,
                source=audit_source,
                source_ids=item.source_ids,
                epistemic_counts=item.epistemic_counts,
            )
            print(f"  Rejected (not in --adopt-names): {item.content_file.name}")
            rejected += 1
            continue

        item = _load_staged_item(meta_file, data_root)
        if item is None:
            _quarantine_invalid_sidecar(meta_file)
            skipped += 1
            continue

        print(f"\n{'=' * 60}")
        print(f"[{item.command}] {item.content_file.name} -> {item.target}")
        print(item.text)

        approve_without_prompt = yes or adopt_names is not None
        if item.action == "drop":
            ok = _adopt_drop_item(item, yes=approve_without_prompt, audit_source=audit_source)
        else:
            ok = _adopt_write_item(item, yes=approve_without_prompt, audit_source=audit_source)
        if ok:
            adopted += 1
        else:
            rejected += 1

        item.content_file.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)

    summary = f"\n--- Summary: {adopted} adopted, {rejected} rejected, {skipped} skipped"
    if reject_failures:
        summary += f", {reject_failures} reject FAILURES (still staged)"
    if adopt_names is not None:
        summary += f", {left} left staged"
    print(summary + " ---")
    if reject_failures:
        # A non-interactive caller must not read a partially applied batch as
        # success (2026-08-01 security review H1).
        sys.exit(1)


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
        "--reject-rest",
        action="store_true",
        help="With --adopt-names: reject (remove from staging, with an audit "
        "record) the staged items NOT listed. Default is to leave them staged.",
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
