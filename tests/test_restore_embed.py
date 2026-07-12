"""Tests for scripts/restore-embed-knowledge.py — post-restore embedding backfill.

The backup mirror stores knowledge.json embedding-free (vectors are
re-derivable, ~97% of raw weight). After a restore, this script rebuilds
the missing vectors so views / dedup see the full store again. It is also
the general backfill for embed-outage rows (added with no embedding by
distill's graceful-degradation branch).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "restore_embed_knowledge",
    Path(__file__).resolve().parent.parent / "scripts" / "restore-embed-knowledge.py",
)
assert _SPEC is not None and _SPEC.loader is not None
rek = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rek)


def _write(tmp_path: Path, rows) -> Path:
    p = tmp_path / "knowledge.json"
    p.write_text(json.dumps(rows), encoding="utf-8")
    return p


class TestBackfill:
    def test_fills_only_missing_embeddings(self, tmp_path, monkeypatch):
        rows = [
            {"pattern": "has one", "embedding": [9.0, 9.0]},
            {"pattern": "missing"},
            {"pattern": "explicit none", "embedding": None},
        ]
        path = _write(tmp_path, rows)
        monkeypatch.setattr(
            rek, "embed_texts", lambda texts: np.ones((len(texts), 2), dtype=np.float32)
        )
        filled = rek.backfill(path)
        assert filled == 2
        out = json.loads(path.read_text(encoding="utf-8"))
        assert out[0]["embedding"] == [9.0, 9.0]
        assert out[1]["embedding"] == [1.0, 1.0]
        assert out[2]["embedding"] == [1.0, 1.0]

    def test_noop_when_all_present_does_not_rewrite(self, tmp_path, monkeypatch):
        rows = [{"pattern": "a", "embedding": [1.0]}]
        path = _write(tmp_path, rows)
        before = path.read_text(encoding="utf-8")
        monkeypatch.setattr(
            rek,
            "embed_texts",
            lambda texts: pytest.fail("embed_texts must not be called on a no-op"),
        )
        assert rek.backfill(path) == 0
        assert path.read_text(encoding="utf-8") == before

    def test_aborts_without_writing_when_embedder_down(self, tmp_path, monkeypatch):
        rows = [{"pattern": "missing"}]
        path = _write(tmp_path, rows)
        before = path.read_text(encoding="utf-8")
        monkeypatch.setattr(rek, "embed_texts", lambda texts: None)
        with pytest.raises(SystemExit):
            rek.backfill(path)
        assert path.read_text(encoding="utf-8") == before

    def test_batches_large_inputs(self, tmp_path, monkeypatch):
        rows = [{"pattern": f"p{i}"} for i in range(150)]
        path = _write(tmp_path, rows)
        calls: list[int] = []

        def fake_embed(texts):
            calls.append(len(texts))
            return np.ones((len(texts), 2), dtype=np.float32)

        monkeypatch.setattr(rek, "embed_texts", fake_embed)
        assert rek.backfill(path, batch_size=64) == 150
        assert calls == [64, 64, 22]
