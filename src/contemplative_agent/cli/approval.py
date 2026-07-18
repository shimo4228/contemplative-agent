"""Approval gate: audit logging and the interactive approval loop (ADR-0012).

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional, Sequence

if TYPE_CHECKING:
    pass

from ..adapters.moltbook import config
from ..core._io import (
    append_jsonl_restricted,
    now_iso,
)

logger = logging.getLogger(__name__)


AUDIT_LOG_PATH = config.MOLTBOOK_DATA_DIR / "logs" / "audit.jsonl"


AuditSource = Literal[
    "direct",
    "stage",
    "stage-adopted",
    "stage-adopted-auto",
    "direct-remove",
    "direct-remove-auto",
]


def _log_approval(
    command: str,
    path: Path,
    approved: bool | None,
    content: str,
    *,
    source: AuditSource = "direct",
    snapshot_path: Optional[Path] = None,
    reason: Optional[str] = None,
    source_ids: Optional[Sequence[str]] = None,
    epistemic_counts: Optional[dict[str, int]] = None,
) -> None:
    """Append approval decision to audit log.

    Args:
        command: The CLI subcommand name (e.g. "insight", "rules-distill").
        path: Final target path for the generated content.
        approved: True = accepted, False = rejected, None = staged (not yet decided).
        content: Full text of the generated artifact (for hashing).
        source: Execution path identifier.
            - "direct": approval gate was invoked inline during the command run.
            - "stage": written to staging dir (decision deferred).
            - "stage-adopted": adopted interactively from staging via `adopt-staged`.
            - "stage-adopted-auto": adopted from staging via `adopt-staged --yes`
              (no human prompt; used by non-TTY coding-agent workflows).
            - "direct-remove": manual removal via `remove-skill` (interactive).
            - "direct-remove-auto": manual removal via `remove-skill --yes`.
        snapshot_path: Pivot snapshot directory written at run start (ADR-0020).
            ``None`` when the command did not produce a snapshot.
        reason: Human-provided justification for the action. Required for
            ``remove-skill`` and other manual CRUD; the field is always
            present in the record (null when omitted) for forward compat.
        source_ids: Lineage keys of the artifact's inputs (ADR-0050) —
            pattern content-hash ids for insight / distill-identity /
            amend-constitution, skill filenames for rules-distill. Always
            present in the record (null when the command has no lineage).
            Empty collections are deliberately normalized to null: every
            lineage-tracked command has ≥1 input by construction, so
            "tracked but empty" does not occur and null uniformly means
            "no lineage attached".
        epistemic_counts: Provenance-kind tally (observed/generated/unknown)
            of the artifact's input patterns (ADR-0050). Always present in the
            record (null when not applicable; empty dicts normalize to null,
            same rationale). NOT an external-grounding metric: since ADR-0060
            ``observed`` is structurally zero (review 2026-06-27 M2), so a 0 here
            does not mean the inputs lacked external grounding — see
            ``epistemic_counts_for`` and architecture.md.
    """
    if approved is None:
        decision = "staged"
    elif approved:
        decision = "approved"
    else:
        decision = "rejected"
    record = {
        "ts": now_iso(timespec="seconds"),
        "command": command,
        "path": str(path),
        "decision": decision,
        "source": source,
        "content_hash": hashlib.sha256(content.encode()).hexdigest()[:16],
        "snapshot_path": str(snapshot_path) if snapshot_path is not None else None,
        "reason": reason,
        "source_ids": list(source_ids) if source_ids else None,
        "epistemic_counts": dict(epistemic_counts) if epistemic_counts else None,
    }
    try:
        append_jsonl_restricted(AUDIT_LOG_PATH, record)
    except OSError:
        logger.warning("Failed to write audit log: %s", AUDIT_LOG_PATH)


def _approve(prompt: str) -> bool:
    """Prompt user for y/N approval. Default is N (safe side)."""
    print(f"\n{prompt} [y/N] ", end="", flush=True)
    try:
        return input().strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def _approve_write(path: Path) -> bool:
    return _approve(f"Write to {path}?")


def _approve_delete(path: Path) -> bool:
    return _approve(f"Delete {path}?")


def _collision_free_path(target_path: Path, text: str) -> Path:
    """Return a write path that will not silently clobber a different file.

    Two batches in one run (or across runs on the same day) can slugify to
    the same ``<slug>-YYYYMMDD.md``; the second approved write previously
    overwrote the first with no warning, while audit.jsonl recorded both as
    "approved" (bug-audit 2026-07-06 H5). Identical content keeps the
    original path (idempotent re-write); differing content gets a ``-2``,
    ``-3``… suffix before the extension. A suffixed path whose content
    already matches is also reused (codex review 2026-07-06: a rerun of the
    same collision batch must not mint ``-3`` when an identical ``-2``
    exists). Same-minute M12 reprocessing regenerates DIFFERENT text for the
    same sources (LLM non-determinism), so this guard cannot recognize that
    case as a duplicate — stocktake dedup catches it downstream.
    """
    if not target_path.exists():
        return target_path

    def _same_content(path: Path) -> bool:
        try:
            return path.read_text(encoding="utf-8").strip() == text.strip()
        except OSError:
            return False

    if _same_content(target_path):
        return target_path
    for n in range(2, 100):
        candidate = target_path.with_name(f"{target_path.stem}-{n}{target_path.suffix}")
        if not candidate.exists() or _same_content(candidate):
            print(
                f"  Name collision: {target_path.name} exists with different "
                f"content; writing {candidate.name} instead"
            )
            return candidate
    raise RuntimeError(f"No collision-free name available for {target_path} after 98 tries")


def _run_approval_loop(
    items: Sequence[Any],
    *,
    command: str,
    target_dir: Path,
    snapshot_path: Optional[Path] = None,
) -> int:
    """Iterate generated artifacts through the approval gate, write approved.

    Each item must expose ``filename``, ``text``, and ``target_path``
    (``SkillResult`` / ``RuleResult`` from core/, and ``StageItem`` here
    all match this shape — kept structural to avoid dragging core types
    into the cli module signature).

    Per-handler post-loop hooks (``write_last_insight`` /
    ``_write_last_run``) and summary prints stay at the call site
    because the wording differs ("written" vs "revised", per-handler
    counters).

    Returns the count of approved+written items so the caller can
    decide whether to fire its post-loop hook.
    """
    from ..core._io import write_restricted

    written = 0
    for i, item in enumerate(items, 1):
        print(f"\n{'=' * 60}")
        print(f"[{i}/{len(items)}] {item.filename}")
        print(item.text)
        # ADR-0069: show the reasoning trace (think-ON pipelines) so the owner
        # approves with the *why* visible. getattr keeps StageItem-shaped items
        # (no ``thinking`` attribute) working unchanged.
        thinking = getattr(item, "thinking", None)
        if thinking:
            print(f"\n--- Reasoning ---\n{thinking}")
        # Resolve slug collisions BEFORE the gate so the owner approves —
        # and the audit records — the path actually written (H5).
        target_path = _collision_free_path(item.target_path, item.text)
        approved = _approve_write(target_path)
        _log_approval(
            command,
            target_path,
            approved,
            item.text,
            snapshot_path=snapshot_path,
            # ADR-0050: SkillResult carries pattern_ids, RuleResult carries
            # source_ids (skill filenames); StageItem-shaped items carry
            # neither here (staging logs lineage itself).
            source_ids=(getattr(item, "pattern_ids", None) or getattr(item, "source_ids", None)),
            epistemic_counts=getattr(item, "epistemic_counts", None),
        )
        if approved:
            target_dir.mkdir(parents=True, exist_ok=True)
            write_restricted(target_path, item.text)
            written += 1
        else:
            print("Skipped.")
    return written
