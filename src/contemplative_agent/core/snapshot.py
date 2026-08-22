"""Pivot snapshot — persist interpretive context at behavior-producing commands.

ADR-0020: the lens that produced a given ``identity.md`` / ``skills/*.md`` /
``rules/*.md`` artifact is the combination of views + constitution +
thresholds + embedding model + centroids. Without snapshots, any of those
changing retroactively makes the resulting artifact's provenance opaque.

This module writes a snapshot directory for each run.
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np

from .embeddings import EMBEDDING_DIM, _get_embedding_model
from .run_context import RUN_ID, current_session_id
from .views import ViewRegistry

logger = logging.getLogger(__name__)

# Pivot snapshots (ADR-0020) are observability/replay artifacts, not episodes,
# so the oldest may be pruned. Without a cap they grow unbounded on every
# approval-gated run (ultracode sweep 2026-06-23 observed 137 dirs / 17 MB).
# The most recent snapshots are the ones a replay actually needs.
MAX_SNAPSHOTS = 100

SnapshotCommand = Literal[
    "distill",
    "distill-identity",
    "insight",
    "amend-constitution",
    "skill-stocktake",
]

_COMPACT_TS_FORMAT = "%Y%m%dT%H%M%S%fZ"


def _format_ts_pair(now: datetime) -> tuple[str, str]:
    """Return (compact, iso) forms derived from a single ``datetime``.

    Deriving both forms from one instant prevents microsecond drift
    between the snapshot dir name and the manifest ``ts`` field.
    Microsecond precision on the compact form makes same-second runs
    (rare in production, universal in tests) collision-free.
    """
    compact = now.strftime(_COMPACT_TS_FORMAT)
    iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    return compact, iso


def collect_thresholds() -> dict[str, float]:
    """Gather all classification/similarity thresholds that shape a run.

    Reads from ``core/thresholds.py`` (the canonical registry since
    ADR-0035 PR2). Add new thresholds in that module and list them
    here so they appear in pivot snapshots.
    """
    from . import thresholds as _t

    return {
        "SIM_DUPLICATE": _t.SIM_DUPLICATE,
        "SIM_UPDATE": _t.SIM_UPDATE,
        "DEDUP_IMPORTANCE_FLOOR": _t.DEDUP_IMPORTANCE_FLOOR,
    }


def _copy_markdown_tree(src: Path, dst: Path) -> None:
    """Copy ``*.md`` files from src to dst (flat, no recursion into subdirs)."""
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for md in sorted(src.glob("*.md")):
        shutil.copy2(md, dst / md.name)


def write_snapshot(
    *,
    command: SnapshotCommand,
    views_dir: Path,
    constitution_dir: Path,
    snapshots_dir: Path,
    prompts_dir: Path | None = None,
    skills_dir: Path | None = None,
    rules_dir: Path | None = None,
    identity_path: Path | None = None,
    view_registry: ViewRegistry | None = None,
    generation_model: str | None = None,
    think: bool = False,
) -> Path | None:
    """Write a pivot snapshot for the given command.

    Captures the full inference-time lens so a distill run can be
    replayed later with bit-identical system-prompt content (LLM
    stochasticity aside):

    - Classification layer: views, constitution, thresholds, centroids
    - Extraction layer: prompts, skills, rules, identity

    ``prompts_dir`` / ``skills_dir`` / ``rules_dir`` / ``identity_path``
    are optional for backward compatibility with older callers — a
    missing path just skips that subdir in the snapshot.

    ``generation_model`` / ``think`` (ADR-0069) record the run's generation
    config in the manifest beside ``embedding_model``. Supplied by the caller
    (``_take_snapshot`` passes ``served_model()`` and the command's think state)
    so this writer stays decoupled from the LLM module.

    ``run_id`` (and ``session_id`` while a session is active) are stamped here,
    matching the keys every audit record carries, so a snapshot joins directly
    to its own ``llm-calls`` rows instead of through ``audit.jsonl``.

    Returns the snapshot directory on success, ``None`` on any failure.
    Snapshots are observability — callers must not rely on snapshot
    success for correctness.
    """
    ts_compact, ts_iso = _format_ts_pair(datetime.now(timezone.utc))
    try:
        snap_dir = snapshots_dir / f"{command}_{ts_compact}"
        snap_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        logger.warning("Snapshot dir creation failed: %s", exc)
        return None

    try:
        _copy_markdown_tree(views_dir, snap_dir / "views")
        _copy_markdown_tree(constitution_dir, snap_dir / "constitution")
        if prompts_dir is not None:
            _copy_markdown_tree(prompts_dir, snap_dir / "prompts")
        if skills_dir is not None:
            _copy_markdown_tree(skills_dir, snap_dir / "skills")
        if rules_dir is not None:
            _copy_markdown_tree(rules_dir, snap_dir / "rules")
        if identity_path is not None and identity_path.is_file():
            shutil.copy2(identity_path, snap_dir / "identity.md")

        view_names = _save_centroids(snap_dir, view_registry)

        manifest = {
            "command": command,
            "ts": ts_iso,
            # Which process execution produced this snapshot. Same key, same
            # value as every audit record (ADR-0078 follow-up), so one join
            # reaches this run's llm-calls rows directly. Stamped here rather
            # than inherited: the manifest is a document written with
            # write_text, not a JSONL record, so it never passes through
            # append_jsonl_restricted where the other producers get it for
            # free. Input-side metadata, so it sits under the same
            # responsibility as generation_model (ADR-0069 decision 5) and
            # makes no claim about what the run produced.
            "run_id": RUN_ID,
            # Generation model + think state for this run (ADR-0069). The
            # embedding model has always been recorded; the generation model and
            # per-run think setting close the reproducibility gap so a snapshot
            # records the full inference config (which model, thinking on/off)
            # that produced the run, not just the embedding lens.
            "generation_model": generation_model,
            "think": think,
            "embedding_model": _get_embedding_model(),
            "embedding_dim": EMBEDDING_DIM,
            "thresholds": collect_thresholds(),
            "views": view_names,
            "views_dir": str(views_dir),
            "constitution_dir": str(constitution_dir),
            "prompts_dir": str(prompts_dir) if prompts_dir is not None else None,
            "skills_dir": str(skills_dir) if skills_dir is not None else None,
            "rules_dir": str(rules_dir) if rules_dir is not None else None,
            "identity_path": str(identity_path) if identity_path is not None else None,
        }
        # Sparse, matching append_jsonl_restricted: the key's absence means no
        # agent session was active. Every snapshot-taking command is invoked
        # manually today, so a dense null here would be a field that is always
        # null and teaches a reader nothing.
        session_id = current_session_id()
        if session_id is not None:
            manifest["session_id"] = session_id
        # manifest.json is written LAST and marks the snapshot complete: a dir
        # without it is partial. Write to a temp name then rename so a reader
        # never sees a half-written manifest.
        manifest_tmp = snap_dir / "manifest.json.tmp"
        manifest_tmp.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        manifest_tmp.replace(snap_dir / "manifest.json")

        _prune_snapshots(snapshots_dir, MAX_SNAPSHOTS)
        return snap_dir
    except OSError as exc:
        logger.warning("Snapshot write failed under %s: %s", snap_dir, exc)
        # Remove the partially-written dir so it is not mistaken for complete.
        shutil.rmtree(snap_dir, ignore_errors=True)
        return None


def _prune_snapshots(snapshots_dir: Path, keep: int) -> None:
    """Keep only the ``keep`` most-recent snapshot dirs; remove the rest.

    Snapshot dirs are named ``{command}_{ts_compact}``. Multiple commands share
    one snapshots dir, so sorting by the whole name would order by command
    prefix first and prune a brand-new snapshot of one command ahead of an old
    one of another. Sort by the ``{ts_compact}`` suffix instead: it is a
    fixed-width, underscore-free timestamp (lexicographic == chronological), and
    command names contain no underscores, so the single-underscore template
    makes ``rsplit("_", 1)[-1]`` reliably isolate the timestamp. Best-effort:
    pruning failures are logged, never raised (snapshots are observability,
    ADR-0020 — pruning must not break a command).
    """
    try:
        snaps = sorted(
            (p for p in snapshots_dir.iterdir() if p.is_dir()),
            key=lambda p: p.name.rsplit("_", 1)[-1],
        )
    except OSError:
        return
    for stale in snaps[:-keep] if keep > 0 else snaps:
        shutil.rmtree(stale, ignore_errors=True)


def _save_centroids(snap_dir: Path, view_registry: ViewRegistry | None) -> list[str]:
    """Save view centroids to centroids.npz; return the view names."""
    centroids: dict[str, np.ndarray] = {}
    view_names: list[str] = []
    if view_registry is not None:
        view_names = view_registry.names()
        for name in view_names:
            c = view_registry.get_centroid(name)
            if c is not None:
                centroids[name] = c
    if centroids:
        np.savez(snap_dir / "centroids.npz", **centroids)  # type: ignore[arg-type]
    return view_names
