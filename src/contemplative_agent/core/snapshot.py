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
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np

from .embeddings import EMBEDDING_DIM, _get_embedding_model
from .views import ViewRegistry

logger = logging.getLogger(__name__)

SnapshotCommand = Literal[
    "distill",
    "distill-identity",
    "insight",
    "rules-distill",
    "amend-constitution",
]

_COMPACT_TS_FORMAT = "%Y%m%dT%H%M%S%fZ"


def _format_ts_pair(now: datetime) -> Tuple[str, str]:
    """Return (compact, iso) forms derived from a single ``datetime``.

    Deriving both forms from one instant prevents microsecond drift
    between the snapshot dir name and the manifest ``ts`` field.
    Microsecond precision on the compact form makes same-second runs
    (rare in production, universal in tests) collision-free.
    """
    compact = now.strftime(_COMPACT_TS_FORMAT)
    iso = now.isoformat(timespec="seconds").replace("+00:00", "Z")
    return compact, iso


def collect_thresholds() -> Dict[str, float]:
    """Gather all classification/similarity thresholds that shape a run.

    Reads from ``core/thresholds.py`` (the canonical registry since
    ADR-0035 PR2). Add new thresholds in that module and list them
    here so they appear in pivot snapshots.
    """
    from . import thresholds as _t

    return {
        "NOISE_THRESHOLD": _t.NOISE_THRESHOLD,
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
    prompts_dir: Optional[Path] = None,
    skills_dir: Optional[Path] = None,
    rules_dir: Optional[Path] = None,
    identity_path: Optional[Path] = None,
    view_registry: Optional[ViewRegistry] = None,
) -> Optional[Path]:
    """Write a pivot snapshot for the given command.

    Captures the full inference-time lens so a distill run can be
    replayed later with bit-identical system-prompt content (LLM
    stochasticity aside):

    - Classification layer: views, constitution, thresholds, centroids
    - Extraction layer: prompts, skills, rules, identity

    ``prompts_dir`` / ``skills_dir`` / ``rules_dir`` / ``identity_path``
    are optional for backward compatibility with older callers — a
    missing path just skips that subdir in the snapshot.

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

        centroids: Dict[str, np.ndarray] = {}
        view_names: List[str] = []
        if view_registry is not None:
            view_names = view_registry.names()
            for name in view_names:
                c = view_registry.get_centroid(name)
                if c is not None:
                    centroids[name] = c
        if centroids:
            np.savez(snap_dir / "centroids.npz", **centroids)  # type: ignore[arg-type]

        manifest = {
            "command": command,
            "ts": ts_iso,
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
        (snap_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        return snap_dir
    except OSError as exc:
        logger.warning("Snapshot write failed under %s: %s", snap_dir, exc)
        return None
