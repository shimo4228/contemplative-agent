"""Staging of distilled results for later human adoption.

Extracted verbatim from the single-file cli.py (ADR-0079 Phase 2).
"""

from __future__ import annotations

import json as json_mod
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ..adapters.moltbook import config
from ..core._io import (
    acquire_run_lock,
)
from . import approval

logger = logging.getLogger(__name__)


# ADR-0074: serialises staging producers. The pending guard alone is a
# check-then-act race — two concurrent `--stage` runs (weekly launchd job +
# a manual run) could both pass the guard and interleave the wipe/write.
# Lives OUTSIDE config.STAGED_DIR so the per-batch wipe never touches it.
STAGED_LOCK_PATH = config.MOLTBOOK_DATA_DIR / ".staged.lock"


@dataclass(frozen=True)
class StageItem:
    """One artifact pending external approval in the staging dir.

    `sources` is set by skill-stocktake merges (original skill filenames
    that `adopt-staged` deletes when the merged result is accepted) and by
    stocktake clean rewrites (the rewrite's own filename, so adoption
    overwrites in place instead of minting a `-2.md` collision copy).
    All other commands leave it empty.

    `action` distinguishes merge (write) from drop (delete) operations.

    `command` overrides the batch command name passed to `_stage_results`.
    Used by stocktake handlers to mix merge ("skill-stocktake") and drop
    ("skill-stocktake-drop") items in a single staging batch — needed
    because `_stage_results` wipes the staging dir on every call, so a
    second call would erase the first batch.

    `source_ids` / `epistemic_counts` are ADR-0050 lineage metadata,
    deliberately distinct from `sources` — `sources` has delete-on-adopt
    semantics, lineage is record-only and rides through meta.json into
    the adopt-time audit entry.
    """

    filename: str
    text: str
    target_path: Path
    sources: list[str] = field(default_factory=list)
    action: Literal["merge", "drop"] = "merge"
    command: str | None = None
    source_ids: list[str] = field(default_factory=list)
    epistemic_counts: dict[str, int] = field(default_factory=dict)


def _pending_staged_count() -> int:
    """Number of unreviewed items sitting in the staging dir.

    Keyed on ``*.meta.json`` sidecars — an ``.md`` without its sidecar is an
    orphan, not a pending batch (adopt-staged pairs on the sidecar too).

    Held items (T-ADOPT-HOLD) are counted like any other: a hold defers the
    decision, and deferring is exactly what the guard exists to notice. They
    are only broken out separately in the refusal message below, so the
    operator can tell a batch nobody reached from one they chose to keep.
    """
    if not config.STAGED_DIR.exists():
        return 0
    return len(list(config.STAGED_DIR.glob("*.meta.json")))


def read_sidecar(meta_file: Path) -> dict[str, Any] | None:
    """The one read of a staged sidecar; None when it is not a usable object.

    Lives beside the writer (`_stage_results`) so the format has one owner,
    and is shared by every reader — the adopt loop, the sort key, the budget
    instrument and the pending-guard's held count. They must not disagree
    about which sidecars exist: the instrument's whole job is to project what
    the loop will do, so a file one of them refuses must not be counted by
    another (both reviews, 2026-08-15).

    ``O_NOFOLLOW`` rather than an ``is_symlink`` guard: the guard was
    lstat-then-open, and the hold outcome writes this object back into
    ``.staged/``, so losing that race copied an outside file's bytes into a
    directory the adversary reads. No producer writes a symlinked sidecar.

    ``isinstance`` rather than ``.get`` on the parse result: a sidecar
    holding valid JSON that is not an object (``[]``, ``"x"``, ``3``) parses
    and then raises ``AttributeError``, which no caller's ``except (OSError,
    ValueError)`` catches — one such file wedged ``adopt-staged``, and
    through the ADR-0074 pending guard, all future staging.
    """
    try:
        fd = os.open(meta_file, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    try:
        with os.fdopen(fd, encoding="utf-8") as handle:
            meta = json_mod.load(handle)
    except (OSError, ValueError):
        return None
    return meta if isinstance(meta, dict) else None


def _held_staged_count() -> int:
    """How many pending sidecars carry the ``held`` marker.

    Unparseable sidecars count as not-held: the adopt loop quarantines them
    and they are already reported by ``_pending_staged_count``. Reporting
    only, never a gate.
    """
    if not config.STAGED_DIR.exists():
        return 0
    return sum(
        1
        for meta_file in config.STAGED_DIR.glob("*.meta.json")
        if (read_sidecar(meta_file) or {}).get("held") is True
    )


def _stage_results(items: list[StageItem], command: str) -> bool:
    """Write generated results to the staging directory for external approval.

    Creates the staging dir, writes each file plus a sidecar `*.meta.json`,
    records a 'staged' entry in the audit log, and prints paths for the
    calling agent to read.

    ADR-0074 pending guard: when an unreviewed batch is still sitting in
    staging, refuse (return ``False``) instead of wiping it — the wipe-per-
    batch semantics silently destroyed candidates that were waiting for
    human review once producers moved to scheduled runs. The invariant is
    "staging holds at most one unreviewed batch".

    The guard + wipe + write run under a non-blocking ``flock``
    (``STAGED_LOCK_PATH``): without it the guard is a check-then-act race —
    two concurrent ``--stage`` producers (weekly launchd insight + a manual
    run) could both see an empty staging dir and interleave their writes
    (codex review 2026-07-09). Losing the lock refuses like the guard does.
    """
    with acquire_run_lock(STAGED_LOCK_PATH, blocking=False) as held:
        if not held:
            print(
                "Another staging producer holds the staging lock — "
                "refusing this batch (ADR-0074). Retry when it finishes."
            )
            return False
        return _stage_results_locked(items, command)


def _stage_results_locked(items: list[StageItem], command: str) -> bool:
    """Body of :func:`_stage_results`; caller holds ``STAGED_LOCK_PATH``."""
    pending = _pending_staged_count()
    if pending:
        held = _held_staged_count()
        # Name the held share: without it this reads as "the last batch was
        # never reviewed", and next week's packet section comes up empty as
        # if no candidates existed (T-ADOPT-HOLD).
        held_note = f" ({held} of them explicitly held at a past gate)" if held else ""
        print(
            f"Staging holds {pending} unreviewed item(s) from a previous run"
            f"{held_note} — refusing to overwrite them (ADR-0074). Review with "
            "`contemplative-agent adopt-staged` first."
        )
        return False

    config.STAGED_DIR.mkdir(parents=True, exist_ok=True)
    for old_file in config.STAGED_DIR.iterdir():
        if old_file.is_file():
            old_file.unlink()
    staged_paths = []
    data_root = config.MOLTBOOK_DATA_DIR.resolve()
    for seq, item in enumerate(items, 1):
        if not item.target_path.resolve().is_relative_to(data_root):
            print(
                f"Error: target path escapes MOLTBOOK_HOME: {item.target_path}",
                file=sys.stderr,
            )
            continue
        item_command = item.command or command
        # Same H5 collision guard as the direct / adopt write paths (round-2
        # R2-H1): two same-slug items in one batch previously clobbered each
        # other's .md + .meta.json in the staging dir — adopt-staged only
        # ever saw the survivor, losing the first artifact with no warning.
        # (The dir is wiped per batch, so collisions are intra-batch only.)
        staged_file = approval._collision_free_path(config.STAGED_DIR / item.filename, item.text)
        # Normalize the trailing newline BEFORE hashing so the "staged" audit
        # entry's content_hash matches both the on-disk bytes and the
        # adopt-time hash of the re-read file (round-2 R2-L2: the
        # unconditional ``+ "\n"`` made every staged↔adopted pair differ).
        text = item.text if item.text.endswith("\n") else item.text + "\n"
        staged_file.write_text(text, encoding="utf-8")
        meta: dict[str, object] = {
            "target": str(item.target_path),
            "command": item_command,
            # Adoption order (codex review round-2 P2): without it,
            # adopt-staged's name sort processes "dup-2.md" before "dup.md"
            # ('-' < '.'), swapping a collision pair's final target names.
            "seq": seq,
        }
        if item.sources:
            meta["sources"] = list(item.sources)
        if item.action != "merge":
            meta["action"] = item.action
        # ADR-0050: lineage rides through meta.json so adopt-staged can
        # attach it to the adopt-time audit entry.
        if item.source_ids:
            meta["source_ids"] = list(item.source_ids)
        if item.epistemic_counts:
            meta["epistemic_counts"] = dict(item.epistemic_counts)
        # Derive the sidecar from the collision-resolved name so the
        # .md ↔ .meta.json pairing adopt-staged relies on stays intact.
        meta_file = config.STAGED_DIR / f"{staged_file.name}.meta.json"
        meta_file.write_text(json_mod.dumps(meta, indent=2) + "\n", encoding="utf-8")
        staged_paths.append((staged_file, item.target_path))
        approval._log_approval(
            item_command,
            item.target_path,
            None,
            text,
            source="stage",
            source_ids=item.source_ids or None,
            epistemic_counts=item.epistemic_counts or None,
        )

    print(f"Staged {len(staged_paths)} file(s) in {config.STAGED_DIR}/")
    for staged, target in staged_paths:
        print(f"  {staged} → {target}")
    return True
