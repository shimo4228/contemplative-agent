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
from typing import Any, Literal

import numpy as np

from ._io import write_restricted
from .embeddings import EMBEDDING_DIM, _get_embedding_model
from .llm import SERVING_ENV_KEYS
from .portable_path import portable_path as _portable_path
from .provenance import PROVENANCE_KEYS, manifest_provenance
from .run_context import RUN_ID, current_session_id
from .views import ViewRegistry

logger = logging.getLogger(__name__)

# Pivot snapshots (ADR-0020) are observability/replay artifacts, not episodes.
# Only the daily ``distill`` kind is capped (ADR-0020 Amendment, D-P3-04-2 = A);
# other kinds are value-layer pivots and are kept (see _prune_snapshots).
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

    Derived from ``core/thresholds.py`` (the canonical registry since
    ADR-0035 PR2): every upper-case numeric constant of that module, sorted
    by name. Declaring a threshold there is the whole registration — the hand
    written mirror this used to hold had already fallen behind by two
    constants (ADR-0020 addendum 2026-09-12), which is the failure mode the
    registry's own docstring promised was impossible.
    """
    from . import thresholds as _t

    return {
        name: value
        for name, value in sorted(vars(_t).items())
        if name.isupper() and isinstance(value, (int, float)) and not isinstance(value, bool)
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
    data_root: Path | None = None,
    prompts_dir: Path | None = None,
    skills_dir: Path | None = None,
    rules_dir: Path | None = None,
    identity_path: Path | None = None,
    view_registry: ViewRegistry | None = None,
    generation_model: str | None = None,
    think: bool = False,
    serving_env: dict[str, Any] | None = None,
    provenance: dict[str, Any] | None = None,
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

    ``data_root`` is ``MOLTBOOK_HOME``: the manifest's six path columns are
    written relative to it, with the user home as ``~`` outside it
    (``core.portable_path``, RFC-0050 / ADR-0020 addendum 2026-10-12). Nothing
    reads those columns back; they record where the run read its lens from.

    ``generation_model`` / ``think`` (ADR-0069) record the run's generation
    config in the manifest beside ``embedding_model``. Supplied by the caller
    (``_take_snapshot`` passes ``served_model()`` and the command's think state)
    so this writer stays decoupled from the LLM module. ``serving_env`` is the
    dict from ``core.llm.serving_environment()`` (weight digests + Ollama
    version, ADR-0069 addendum 2026-09-06), passed by the caller for the same
    reason; ``None`` omits those keys. ``provenance`` is the dict from
    ``core.provenance.ProvenanceRecord.as_dict()`` (P1-07.13): the same record
    the session-start episode carries, copied here rather than recomputed; only
    its known keys are written, and ``None`` omits them.

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
            # Which code ran (P0-06.4): framework_version / git_commit /
            # prompt_digests / manifest_schema, additive to every older key.
            **manifest_provenance(prompts_dir),
            # Model names are mutable tags; the digests pin the weights. Only
            # the known keys, so a caller dict can never shadow the fields
            # above and the manifest schema stays statically knowable.
            **{k: serving_env[k] for k in SERVING_ENV_KEYS if serving_env and k in serving_env},
            **{k: provenance[k] for k in PROVENANCE_KEYS if provenance and k in provenance},
            "embedding_model": _get_embedding_model(),
            "embedding_dim": EMBEDDING_DIM,
            "thresholds": collect_thresholds(),
            "views": view_names,
            # Where the lens was read from, never the machine's home path
            # (RFC-0050): this file is published as-is by the data sync.
            "views_dir": _portable_path(views_dir, data_root),
            "constitution_dir": _portable_path(constitution_dir, data_root),
            "prompts_dir": _portable_path(prompts_dir, data_root),
            "skills_dir": _portable_path(skills_dir, data_root),
            "rules_dir": _portable_path(rules_dir, data_root),
            "identity_path": _portable_path(identity_path, data_root),
        }
        # Sparse, matching append_jsonl_restricted: the key's absence means no
        # agent session was active. Every snapshot-taking command is invoked
        # manually today, so a dense null here would be a field that is always
        # null and teaches a reader nothing.
        session_id = current_session_id()
        if session_id is not None:
            manifest["session_id"] = session_id
        # manifest.json is written LAST and marks the snapshot complete: a dir
        # without it is partial. write_restricted publishes through a rename,
        # so a reader never sees a half-written manifest — and it owns the
        # temp-file rules (O_EXCL, 0600, cleanup on failure) rather than this
        # call site guessing a predictable ".tmp" name.
        write_restricted(
            snap_dir / "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        )

        _prune_snapshots(snapshots_dir, MAX_SNAPSHOTS)
        return snap_dir
    # RuntimeError: Path.home() with no resolvable home, or resolve() on a
    # symlink loop (Python < 3.13) inside _portable_path. Dropping the
    # snapshot keeps it observability-only and writes no unredacted path.
    except (OSError, RuntimeError) as exc:
        logger.warning("Snapshot write failed under %s: %s", snap_dir, exc)
        # Remove the partially-written dir so it is not mistaken for complete.
        shutil.rmtree(snap_dir, ignore_errors=True)
        return None


def add_manifest_section(snap_dir: Path | None, key: str, value: dict[str, Any]) -> bool:
    """Add one new top-level key to an existing snapshot's manifest.

    For values that only exist after the run's input selection (P0-07.7: the
    amendment's matched / live pattern counts), which the manifest writer
    cannot know when the snapshot is taken. Additive only: an existing key is
    never replaced, and the rewrite goes through the same atomic writer.
    Observability like the snapshot itself — any failure returns ``False``.
    """
    if snap_dir is None:
        return False
    path = snap_dir / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or key in manifest:
            return False
        manifest[key] = value
        write_restricted(path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    except (OSError, ValueError, TypeError) as exc:
        logger.warning("Manifest section %r not added under %s: %s", key, snap_dir, exc)
        return False
    return True


def _prune_snapshots(snapshots_dir: Path, keep: int) -> None:
    """Keep the ``keep`` most-recent ``distill`` snapshots; never prune other kinds.

    ADR-0020 Amendment (2026-10, D-P3-04-2 = A): the daily ``distill`` run is
    the only kind that grows without bound, so it alone is capped. Pivot
    snapshots of every other kind (``distill-identity`` / ``amend-constitution``
    / ``insight`` / ``skill-stocktake`` and the retired ``rules-distill``) mark
    value-layer pivots and are kept indefinitely — a kind-blind chronological
    prune let daily distill runs push them out of the window.

    Snapshot dirs are named ``{command}_{ts_compact}``. ``{ts_compact}`` is a
    fixed-width, underscore-free timestamp (lexicographic == chronological) and
    command names contain no underscores, so ``rsplit("_", 1)`` splits kind from
    timestamp reliably. Best-effort: an ``OSError`` from ``iterdir`` returns
    after one warning and each ``rmtree`` runs with ``ignore_errors=True``, so
    pruning never raises (snapshots are observability — pruning must not break
    a command). Each removal logs one line.
    """
    try:
        snaps = sorted(
            (
                p
                for p in snapshots_dir.iterdir()
                if p.is_dir() and p.name.rsplit("_", 1)[0] == "distill"
            ),
            key=lambda p: p.name.rsplit("_", 1)[-1],
        )
    except OSError as exc:
        logger.warning("Snapshot prune skipped for %s: %s", snapshots_dir, exc)
        return
    for stale in snaps[:-keep] if keep > 0 else snaps:
        logger.info("Pruned snapshot %s (kind=distill, keep=%d)", stale.name, keep)
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
