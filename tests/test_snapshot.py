"""Tests for core.snapshot — pivot snapshot (ADR-0020)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from contemplative_agent.core.snapshot import (
    _copy_markdown_tree,
    _prune_snapshots,
    collect_thresholds,
    write_snapshot,
)
import contemplative_agent.core.snapshot as snapshot_mod
from contemplative_agent.core.views import ViewRegistry


@pytest.fixture
def layout(tmp_path: Path):
    """Canonical on-disk layout with views, constitution, knowledge, snapshots dirs."""
    views = tmp_path / "views"
    views.mkdir()
    (views / "constitutional.md").write_text(
        "---\nthreshold: 0.55\nseed_from: ../constitution/*.md\n---\n\nFallback constitutional body.\n",
        encoding="utf-8",
    )
    (views / "noise.md").write_text(
        "---\nthreshold: 0.55\n---\n\nRepetitive boilerplate / status / traceback content.\n",
        encoding="utf-8",
    )
    (views / "self_reflection.md").write_text(
        "---\nthreshold: 0.55\n---\n\nInternal observations, self-aware reflection.\n",
        encoding="utf-8",
    )

    constitution = tmp_path / "constitution"
    constitution.mkdir()
    (constitution / "axioms.md").write_text(
        "Treat all frameworks as provisional. Boundless care.\n",
        encoding="utf-8",
    )

    snapshots = tmp_path / "snapshots"
    # don't create — let write_snapshot create it

    return {
        "root": tmp_path,
        "views": views,
        "constitution": constitution,
        "snapshots": snapshots,
    }


def _fake_embed(text: str) -> np.ndarray:
    """Cross-process deterministic fake embedder: SHA256-seeded 8-dim vector.

    Using ``hash()`` here would break under Python's per-process hash
    salting (parallel pytest / CI).
    """
    seed = int.from_bytes(hashlib.sha256(text.encode()).digest()[:4], "big")
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(8).astype(np.float32)
    return v / np.linalg.norm(v)


@pytest.fixture
def view_registry(layout):
    """Registry loaded from fixture views_dir with fake embedding backend."""
    reg = ViewRegistry(
        views_dir=layout["views"],
        path_vars={"CONSTITUTION_DIR": layout["constitution"]},
    )
    reg.load_views()
    with patch("contemplative_agent.core.views.embed_one", side_effect=_fake_embed):
        # force centroid computation upfront
        for name in reg.names():
            reg.get_centroid(name)
    return reg


class TestCollectThresholds:
    def test_includes_distill_constants(self):
        t = collect_thresholds()
        # NOISE_THRESHOLD was removed with the noise gate (ADR-0060).
        for k in ("SIM_DUPLICATE", "SIM_UPDATE", "DEDUP_IMPORTANCE_FLOOR"):
            assert k in t
            assert isinstance(t[k], float)
        assert "NOISE_THRESHOLD" not in t


class TestCopyMarkdownTree:
    def test_copies_md_files(self, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.md").write_text("alpha", encoding="utf-8")
        (src / "b.md").write_text("beta", encoding="utf-8")
        (src / "ignore.txt").write_text("ignored", encoding="utf-8")
        dst = tmp_path / "dst"
        _copy_markdown_tree(src, dst)
        assert (dst / "a.md").read_text(encoding="utf-8") == "alpha"
        assert (dst / "b.md").read_text(encoding="utf-8") == "beta"
        assert not (dst / "ignore.txt").exists()

    def test_missing_source_is_noop(self, tmp_path):
        dst = tmp_path / "dst"
        _copy_markdown_tree(tmp_path / "nonexistent", dst)
        assert not dst.exists()


class TestSnapshotRetention:
    """Batch G regression (ultracode sweep 2026-06-23): snapshot dirs grew
    unbounded (137 dirs / 17 MB observed). Retention keeps the most recent N."""

    def test_prune_keeps_most_recent(self, tmp_path):
        snaps = tmp_path / "snapshots"
        snaps.mkdir()
        # ts_compact-style names sort chronologically by name.
        for ts in ("20260101T000000", "20260102T000000", "20260103T000000",
                   "20260104T000000", "20260105T000000"):
            (snaps / f"distill_{ts}").mkdir()
        _prune_snapshots(snaps, keep=2)
        remaining = sorted(p.name for p in snaps.iterdir())
        assert remaining == ["distill_20260104T000000", "distill_20260105T000000"]

    def test_write_snapshot_prunes_beyond_cap(self, layout, view_registry, monkeypatch):
        monkeypatch.setattr(snapshot_mod, "MAX_SNAPSHOTS", 3)
        # Pre-seed older snapshot dirs (deterministic names sort before a
        # current-time write), then write one real snapshot.
        layout["snapshots"].mkdir()
        for ts in ("20200101T000000", "20200102T000000",
                   "20200103T000000", "20200104T000000"):
            (layout["snapshots"] / f"distill_{ts}").mkdir()
        path = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        dirs = sorted(p.name for p in layout["snapshots"].iterdir() if p.is_dir())
        assert len(dirs) == 3
        # The freshly written snapshot (newest) survives the prune.
        assert path is not None and path.name in dirs


class TestWriteSnapshot:
    def test_creates_expected_layout(self, layout, view_registry):
        path = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        assert path is not None
        assert path.parent == layout["snapshots"]
        assert path.name.startswith("distill_")
        assert (path / "manifest.json").exists()
        assert (path / "views" / "constitutional.md").exists()
        assert (path / "views" / "noise.md").exists()
        assert (path / "constitution" / "axioms.md").exists()
        assert (path / "centroids.npz").exists()

    def test_manifest_captures_context(self, layout, view_registry, monkeypatch):
        monkeypatch.setenv("OLLAMA_EMBEDDING_MODEL", "custom-embed")
        path = write_snapshot(
            command="insight",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        manifest = json.loads((path / "manifest.json").read_text())
        assert manifest["command"] == "insight"
        assert manifest["embedding_model"] == "custom-embed"
        assert manifest["embedding_dim"] == 768
        assert set(manifest["views"]) == {"constitutional", "noise", "self_reflection"}
        # NOISE_THRESHOLD removed with the noise gate (ADR-0060).
        assert "NOISE_THRESHOLD" not in manifest["thresholds"]
        assert manifest["thresholds"]["SIM_DUPLICATE"] == 0.90
        assert manifest["views_dir"] == str(layout["views"])

    def test_centroids_npz_roundtrips(self, layout, view_registry):
        path = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        data = np.load(path / "centroids.npz")
        for name in ("constitutional", "noise", "self_reflection"):
            saved = data[name]
            original = view_registry.get_centroid(name)
            np.testing.assert_array_equal(saved, original)

    def test_without_view_registry_still_saves_manifest(self, layout):
        """amend-constitution path: no view_registry, no centroids, but manifest + constitution persist."""
        path = write_snapshot(
            command="amend-constitution",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=None,
        )
        assert path is not None
        assert (path / "manifest.json").exists()
        assert (path / "constitution" / "axioms.md").exists()
        # no centroids file because no centroids
        assert not (path / "centroids.npz").exists()
        manifest = json.loads((path / "manifest.json").read_text())
        assert manifest["views"] == []

    def test_captures_extraction_layer(self, layout, view_registry, tmp_path):
        """Snapshot includes prompts / skills / rules / identity so the
        complete inference-time system prompt can be reconstructed."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "distill.md").write_text("distill prompt content", encoding="utf-8")

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "inquiry.md").write_text("skill content", encoding="utf-8")

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "hold-lightly.md").write_text("rule content", encoding="utf-8")

        identity_path = tmp_path / "identity.md"
        identity_path.write_text("identity content", encoding="utf-8")

        path = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            prompts_dir=prompts_dir,
            skills_dir=skills_dir,
            rules_dir=rules_dir,
            identity_path=identity_path,
            view_registry=view_registry,
        )
        assert path is not None
        assert (path / "prompts" / "distill.md").read_text(encoding="utf-8") == "distill prompt content"
        assert (path / "skills" / "inquiry.md").read_text(encoding="utf-8") == "skill content"
        assert (path / "rules" / "hold-lightly.md").read_text(encoding="utf-8") == "rule content"
        assert (path / "identity.md").read_text(encoding="utf-8") == "identity content"
        manifest = json.loads((path / "manifest.json").read_text())
        assert manifest["prompts_dir"] == str(prompts_dir)
        assert manifest["skills_dir"] == str(skills_dir)
        assert manifest["rules_dir"] == str(rules_dir)
        assert manifest["identity_path"] == str(identity_path)

    def test_extraction_layer_optional_for_backward_compat(self, layout, view_registry):
        """Omitting the extraction-layer args leaves the snapshot exactly
        as it was before this expansion — no skills/rules/prompts/identity
        entries appear, manifest records None for each."""
        path = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        assert path is not None
        assert not (path / "prompts").exists()
        assert not (path / "skills").exists()
        assert not (path / "rules").exists()
        assert not (path / "identity.md").exists()
        manifest = json.loads((path / "manifest.json").read_text())
        assert manifest["prompts_dir"] is None
        assert manifest["skills_dir"] is None
        assert manifest["rules_dir"] is None
        assert manifest["identity_path"] is None

    def test_continues_on_unwritable_snapshots_dir(self, tmp_path):
        unwritable = tmp_path / "ro" / "snapshots"
        unwritable.parent.mkdir()
        # make parent read-only so mkdir fails
        os.chmod(unwritable.parent, 0o400)
        try:
            result = write_snapshot(
                command="distill",
                views_dir=tmp_path / "views",
                constitution_dir=tmp_path / "constitution",
                snapshots_dir=unwritable,
                view_registry=None,
            )
            assert result is None  # no exception
        finally:
            os.chmod(unwritable.parent, 0o700)

    def test_returns_none_on_oserror_after_snap_dir_created(
        self, layout, view_registry, monkeypatch,
    ):
        """ADR-0020 / snapshot.py:162-164 — once snap_dir.mkdir succeeds, any
        later OSError (copy / npz / manifest write) is swallowed and
        write_snapshot returns None. The unwritable-parent test above covers
        the earlier mkdir failure (124-126); this covers the second except."""
        import contemplative_agent.core.snapshot as snap_mod

        def fail(*args, **kwargs):
            raise OSError("simulated copy failure")

        monkeypatch.setattr(snap_mod, "_copy_markdown_tree", fail)

        result = write_snapshot(
            command="distill",
            views_dir=layout["views"],
            constitution_dir=layout["constitution"],
            snapshots_dir=layout["snapshots"],
            view_registry=view_registry,
        )
        assert result is None
