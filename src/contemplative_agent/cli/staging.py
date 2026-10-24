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
from typing import Any

from ..adapters.moltbook import config
from ..core._io import (
    acquire_run_lock,
    write_restricted,
)
from . import approval
from .store_paths import _target_inside_data_root

logger = logging.getLogger(__name__)


# ADR-0074: serialises staging producers. The pending guard alone is a
# check-then-act race — two concurrent `--stage` runs (weekly launchd job +
# a manual run) could both pass the guard and interleave the wipe/write.
# Lives OUTSIDE config.STAGED_DIR so the per-batch wipe never touches it.
STAGED_LOCK_PATH = config.MOLTBOOK_DATA_DIR / ".staged.lock"


@dataclass(frozen=True)
class StageItem:
    """One artifact pending external approval in the staging dir.

    `source_ids` / `epistemic_counts` are ADR-0050 lineage metadata:
    record-only, riding through meta.json into the adopt-time audit entry.

    ADR-0097 removed `sources` (delete-on-adopt of a merge's originals),
    `action` (merge vs drop) and the per-item `command` override with the
    stocktake merge / clean / drop producers that were their only writers.
    Every surviving producer stages one artifact per target under the batch
    command, so adoption is a write and nothing else. ADR-0097 Decision 5's
    exit landed as `adopt-staged --archive-names FILE` and deliberately took
    no field here: a staged file still cannot name anything to remove from
    the store, and adding one would undo the narrowing above.

    `surprise` is the ADR-0096 read-only reading for an insight candidate,
    restored 2026-08-29 by RFC-0016. It rides the same sidecar because that
    sidecar is already where the reviewer meets the item, in both surviving
    read paths: `adopt-staged` prints it above the artifact at the human gate
    (`cli/adopt.py::_dispatch_staged_item`), and the Saturday `/weekly-gate`
    session reads every `.meta.json` in `.staged/` directly (skill step 4).
    The `weekly-pipeline.sh` stage that used to `cat` sidecars into an
    insight-review prompt was retired by ADR-0098 and is deliberately NOT
    named here — it no longer exists.

    It stays compatible with ADR-0097 Decision 3 ("adoption is a write and
    nothing else") because it is display-only: nothing branches on it, and no
    adoption outcome, ordering or count is a function of it
    (`tests/test_cli_adopt.py::TestSurpriseIsDisplayOnly`).

    `topic` / `nearest` / `stages` are the same kind of display material
    (P2-06.2, D-P2-06-1 = C): the cluster label, the store neighbours the
    duplicate judge was shown for this candidate, and the entrance stages'
    verdict columns (naming kind, duplicate verdict, fail-open reasons).
    `adopt-staged` prints one line from them beside `surprise`, and
    `scripts/staged_item_axes.py` joins them with the novelty verdict and the
    related skills' reply rate for the Saturday gate. Per-axis, no composite;
    no adoption outcome, order or count is a function of them
    (`tests/test_cli_adopt.py::TestStageReadingIsDisplayOnly`). Empty values
    are not written, so a sidecar from a producer that has none is unchanged.
    """

    filename: str
    text: str
    target_path: Path
    source_ids: list[str] = field(default_factory=list)
    epistemic_counts: dict[str, int] = field(default_factory=dict)
    surprise: dict[str, float | int] = field(default_factory=dict)
    topic: str = ""
    nearest: list[str] = field(default_factory=list)
    stages: dict[str, str | bool | None] = field(default_factory=dict)


def _pending_staged_count() -> int:
    """Number of unreviewed items sitting in the staging dir.

    Keyed on ``*.meta.json`` sidecars — an ``.md`` without its sidecar is an
    orphan, not a pending batch (adopt-staged pairs on the sidecar too).
    """
    if not config.STAGED_DIR.exists():
        return 0
    return len(list(config.STAGED_DIR.glob("*.meta.json")))


def ensure_trailing_newline(text: str) -> str:
    """The staged and adopted bytes' one normalization: exactly one final newline.

    Both writes go through this. The staged audit row's ``content_hash`` is
    taken over the normalized text and adopt re-hashes the file it writes, so
    a second spelling of the rule is how a staged↔adopted pair silently stops
    matching (round-2 R2-L2, where an unconditional ``+ "\n"`` made every
    pair differ).
    """
    return text if text.endswith("\n") else text + "\n"


def read_sidecar(meta_file: Path) -> dict[str, Any] | None:
    """The one read of a staged sidecar; None when it is not a usable object.

    Lives beside the writer (`_stage_results`) so the format has one owner,
    and is shared by every reader — the adopt loop, the sort key and the
    budget instrument. They must not disagree about which sidecars exist: the
    instrument's whole job is to project what the loop will do, so a file one
    of them refuses must not be counted by another (both reviews,
    2026-08-15).

    ``O_NOFOLLOW`` rather than an ``is_symlink`` guard: the guard was
    lstat-then-open, so losing that race let a planted link decide which
    bytes the adopt loop read as a sidecar. No producer writes a symlinked
    sidecar, so refusing one outright costs nothing.

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


def _refuse_if_pending(command: str) -> bool:
    """ADR-0074 fast-fail: True when a pending batch should abort this run.

    Producers call this at the top of their handler, BEFORE the LLM work,
    and return early when it is True. ``_stage_results`` refuses again at
    write time, so this is an efficiency guard, not the invariant itself:
    without it the batch is discarded anyway, just after the generation
    calls have been paid for.

    The early return does skip more than LLM spend: a producer that would
    have run to completion and been refused at the tail also printed its
    report and its reasoning trace on the way. Those are lost too. Accepted
    cost — they describe a batch that was never going to be staged.

    Deliberately not folded into ``_stage_results``: by the time a producer
    reaches that call its LLM work is done. The staging call sites live in
    shared approval/staging tails (``_handle_single_result``,
    ``_run_stocktake_phases``) while every LLM call sits one frame up in the
    command handler, so "where staging is written" and "where the guard
    pays off" are different places (T-GUARD).

    Equally deliberate in the other direction: the call stays per-handler and
    is not hoisted up into ``main()``'s dispatch. Tests and scripts reach the
    handlers directly without passing through ``main()``, so a hoisted guard
    would leave that whole entry path unguarded. The per-handler contract is
    pinned by ``tests/test_staging_pending_guard.py``'s
    ``TestEveryStageProducerIsGuarded`` (T-GUARD).

    Only meaningful under ``--stage``; callers gate on the flag so the
    interactive path — which never writes to the staging dir — is unaffected.
    """
    pending = _pending_staged_count()
    if not pending:
        return False
    print(
        f"Staging holds {pending} unreviewed item(s) — "
        f"skipping this {command} run (ADR-0074). Review with "
        "`contemplative-agent adopt-staged` first."
    )
    return True


def _stage_results(items: list[StageItem], command: str, snapshot_path: Path | None = None) -> bool:
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
        return _stage_results_locked(items, command, snapshot_path)


def _stamp_generation_model(meta: dict[str, object], command: str) -> None:
    """P0-07.8: record the model that generated an amendment in its sidecar.

    Known only at staging (the same process ran the generation);
    ``adopt-staged`` writes it into the constitution's provenance sidecar.
    """
    if command == "amend-constitution":
        from ..core.llm import served_model

        meta["generation_model"] = served_model()


def _snapshot_key(snapshot_path: Path | None) -> dict[str, str]:
    """The sidecar's ``snapshot`` entry (P1-12.9), or nothing.

    The producer's pivot snapshot rides the sidecar so the ``stage`` row here
    and the adopt / reject row later name the same run. Home-relative, like
    every path in the audit row it ends up in; omitted (not null) when the
    producer wrote no snapshot, so old and new sidecars stay one shape.
    """
    if snapshot_path is None:
        return {}
    return {"snapshot": approval.home_relative(snapshot_path)}


def _stage_reading_meta(item: StageItem) -> dict[str, object]:
    """P2-06.2: the entrance stages' display fields, only those that are set.

    Kept out of ``_stage_results_locked`` so the writer's branches stay about
    staging; an empty field is not written, so a producer without them (identity,
    skill-stocktake) leaves its sidecar byte-for-byte as before.
    """
    out: dict[str, object] = {}
    if item.topic:
        out["topic"] = item.topic
    if item.nearest:
        out["nearest"] = list(item.nearest)
    if item.stages:
        out["stages"] = dict(item.stages)
    return out


def _stage_results_locked(
    items: list[StageItem], command: str, snapshot_path: Path | None = None
) -> bool:
    """Body of :func:`_stage_results`; caller holds ``STAGED_LOCK_PATH``."""
    # Authoritative half of the invariant; producers also fast-fail before
    # their LLM work. Neither is redundant with the other — see
    # _refuse_if_pending's docstring before deleting either (T-GUARD).
    pending = _pending_staged_count()
    if pending:
        print(
            f"Staging holds {pending} unreviewed item(s) from a previous run"
            " — refusing to overwrite them (ADR-0074). Review with "
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
        # The shared predicate, not a referent-only test: it checks the literal
        # path too, which is what makes the containment argument hold for a
        # symlinked leaf (store_paths' docstring: a second reader of "is this
        # inside" is how that argument stops being one).
        if not _target_inside_data_root(item.target_path, data_root):
            print(
                f"Error: target path escapes MOLTBOOK_HOME: {item.target_path}",
                file=sys.stderr,
            )
            continue
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
        text = ensure_trailing_newline(item.text)
        write_restricted(staged_file, text)
        meta: dict[str, object] = {
            "target": str(item.target_path),
            "command": command,
            # Adoption order (codex review round-2 P2): without it,
            # adopt-staged's name sort processes "dup-2.md" before "dup.md"
            # ('-' < '.'), swapping a collision pair's final target names.
            "seq": seq,
        }
        _stamp_generation_model(meta, command)

        meta.update(_snapshot_key(snapshot_path))
        # ADR-0050: lineage rides through meta.json so adopt-staged can
        # attach it to the adopt-time audit entry.
        if item.source_ids:
            meta["source_ids"] = list(item.source_ids)
        if item.epistemic_counts:
            meta["epistemic_counts"] = dict(item.epistemic_counts)
        # ADR-0096 / RFC-0016: the surprise reading travels with the candidate
        # to the human gate. Read-only — no consumer branches on it.
        if item.surprise:
            meta["surprise"] = dict(item.surprise)
        meta.update(_stage_reading_meta(item))
        # Derive the sidecar from the collision-resolved name so the
        # .md ↔ .meta.json pairing adopt-staged relies on stays intact.
        meta_file = config.STAGED_DIR / f"{staged_file.name}.meta.json"
        write_restricted(meta_file, json_mod.dumps(meta, indent=2) + "\n")
        staged_paths.append((staged_file, item.target_path))
        approval._log_approval(
            command,
            item.target_path,
            None,
            text,
            source="stage",
            snapshot_path=snapshot_path,
            source_ids=item.source_ids or None,
            epistemic_counts=item.epistemic_counts or None,
        )

    print(f"Staged {len(staged_paths)} file(s) in {config.STAGED_DIR}/")
    for staged, target in staged_paths:
        print(f"  {staged} → {target}")
    return True
