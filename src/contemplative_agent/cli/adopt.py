"""adopt-staged / remove-skill: promote or drop staged value-layer items.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import argparse
import json as json_mod
from dataclasses import dataclass
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    pass

from ..adapters.moltbook import config
from ..core.domain import (
    load_constitution,
)


from . import approval
from .approval import AuditSource

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
    source_ids: Optional[Sequence[str]]
    epistemic_counts: Optional[dict[str, int]]


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
    """
    yes = getattr(args, "yes", False)
    audit_source: AuditSource = "stage-adopted-auto" if yes else "stage-adopted"

    if not config.STAGED_DIR.exists():
        print("No staging directory.")
        return

    meta_files = sorted(config.STAGED_DIR.glob("*.meta.json"), key=_staged_sort_key)
    if not meta_files:
        print("No staged files.")
        return

    data_root = config.MOLTBOOK_DATA_DIR.resolve()
    _print_system_budget_for_staged(meta_files, data_root)

    if yes:
        print(
            f"Auto-approve mode (--yes): adopting {len(meta_files)} staged item(s) without prompts."
        )

    adopted = 0
    rejected = 0
    skipped = 0
    for meta_file in meta_files:
        item = _load_staged_item(meta_file, data_root)
        if item is None:
            # Quarantine instead of leaving the sidecar in place: an invalid
            # meta counts toward the ADR-0074 pending guard, so a single
            # corrupt sidecar would otherwise block every future --stage run
            # permanently (codex review 2026-07-09). Rename preserves the
            # bytes for inspection while removing it from the pending count.
            quarantined = meta_file.with_name(meta_file.name + ".invalid")
            try:
                meta_file.rename(quarantined)
                print(f"  Quarantined invalid sidecar → {quarantined.name}")
            except OSError as err:
                print(f"  Could not quarantine {meta_file.name}: {err}", file=sys.stderr)
            skipped += 1
            continue

        print(f"\n{'=' * 60}")
        print(f"[{item.command}] {item.content_file.name} -> {item.target}")
        print(item.text)

        if item.action == "drop":
            ok = _adopt_drop_item(item, yes=yes, audit_source=audit_source)
        else:
            ok = _adopt_write_item(item, yes=yes, audit_source=audit_source)
        if ok:
            adopted += 1
        else:
            rejected += 1

        item.content_file.unlink(missing_ok=True)
        meta_file.unlink(missing_ok=True)

    print(f"\n--- Summary: {adopted} adopted, {rejected} rejected, {skipped} skipped ---")


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
