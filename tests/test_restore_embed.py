"""Tests for scripts/restore-embed-knowledge.py — post-restore embedding backfill.

The backup mirror stores knowledge.json embedding-free (vectors are
re-derivable, ~97% of raw weight). After a restore, this script rebuilds
the missing vectors so views / dedup see the full store again. It is also
the general backfill for embed-outage rows (added with no embedding by
distill's graceful-degradation branch).

Since ADR-0108 the vectors land in ``pattern-embeddings.sqlite`` beside the
JSON, so these tests read the filled result back through ``KnowledgeStore``
rather than out of the JSON text.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from contemplative_agent.core.knowledge_store import KnowledgeStore

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


def _reload(path: Path) -> list[dict]:
    """The store as a later run sees it: JSON rows + sidecar vectors."""
    store = KnowledgeStore(path=path)
    store.load()
    return store.get_raw_patterns()


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
        out = _reload(path)
        assert out[0]["embedding"] == [9.0, 9.0]
        assert out[1]["embedding"] == [1.0, 1.0]
        assert out[2]["embedding"] == [1.0, 1.0]
        # The JSON itself is text-only now (ADR-0108).
        assert all("embedding" not in r for r in json.loads(path.read_text(encoding="utf-8")))

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
        assert not (tmp_path / "pattern-embeddings.sqlite").exists()

    def test_aborts_without_writing_on_a_failed_load(self, tmp_path, monkeypatch):
        """A tainted / unparseable store must not be re-saved as an empty one."""
        path = tmp_path / "knowledge.json"
        path.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(
            rek, "embed_texts", lambda texts: pytest.fail("must not embed a failed load")
        )
        with pytest.raises(SystemExit):
            rek.backfill(path)
        assert path.read_text(encoding="utf-8") == "{not json"

    def test_aborts_without_writing_when_embedder_down(self, tmp_path, monkeypatch):
        rows = [{"pattern": "missing"}]
        path = _write(tmp_path, rows)
        before = path.read_text(encoding="utf-8")
        monkeypatch.setattr(rek, "embed_texts", lambda texts: None)
        with pytest.raises(SystemExit):
            rek.backfill(path)
        assert path.read_text(encoding="utf-8") == before
        assert not (tmp_path / "pattern-embeddings.sqlite").exists()

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
        assert all(r["embedding"] == [1.0, 1.0] for r in _reload(path))


class TestRefusesToShedRows:
    def test_refuses_when_the_file_holds_unparseable_elements(self, tmp_path, monkeypatch):
        path = _write(tmp_path, [{"pattern": "needs a vector"}, {"this_is": "not a row"}])
        before = path.read_text(encoding="utf-8")
        monkeypatch.setattr(
            rek, "embed_texts", lambda texts: pytest.fail("must not embed a sheddable store")
        )
        with pytest.raises(SystemExit):
            rek.backfill(path)
        assert path.read_text(encoding="utf-8") == before
