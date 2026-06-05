"""Tests for EpisodeEmbeddingStore (SQLite sidecar)."""

from __future__ import annotations

import numpy as np
import pytest

from contemplative_agent.core.episode_embeddings import EpisodeEmbeddingStore


@pytest.fixture
def store(tmp_path):
    return EpisodeEmbeddingStore(db_path=tmp_path / "embeddings.sqlite")


class TestUpsertAndGet:
    def test_round_trip(self, store):
        vec = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        store.upsert("abc", "2026-04-15T07:00:00Z", vec)
        result = store.get("abc")
        assert result is not None
        np.testing.assert_array_almost_equal(result, vec)

    def test_replace_on_duplicate_id(self, store):
        v1 = np.array([0.1, 0.2], dtype=np.float32)
        v2 = np.array([0.9, 0.8], dtype=np.float32)
        store.upsert("abc", "2026-04-15T07:00:00Z", v1)
        store.upsert("abc", "2026-04-15T08:00:00Z", v2)
        result = store.get("abc")
        np.testing.assert_array_almost_equal(result, v2)

    def test_get_missing_returns_none(self, store):
        assert store.get("nonexistent") is None

    def test_get_before_init_returns_none(self, tmp_path):
        store = EpisodeEmbeddingStore(db_path=tmp_path / "missing.sqlite")
        # No upsert yet — file may or may not exist depending on init
        # Either way, get should return None for unknown id
        assert store.get("never_inserted") is None


class TestUpsertMany:
    def test_bulk_insert(self, store):
        items = [
            ("a", "2026-04-15T07:00:00Z", np.array([0.1, 0.2], dtype=np.float32)),
            ("b", "2026-04-15T07:01:00Z", np.array([0.3, 0.4], dtype=np.float32)),
            ("c", "2026-04-15T07:02:00Z", np.array([0.5, 0.6], dtype=np.float32)),
        ]
        n = store.upsert_many(items)
        assert n == 3
        assert store.count() == 3

    def test_empty_items_returns_zero(self, store):
        assert store.upsert_many([]) == 0


class TestGetMany:
    def test_returns_only_present_ids(self, store):
        store.upsert("a", "2026-04-15T07:00:00Z", np.array([0.1, 0.2], dtype=np.float32))
        store.upsert("b", "2026-04-15T07:01:00Z", np.array([0.3, 0.4], dtype=np.float32))
        result = store.get_many(["a", "b", "missing"])
        assert set(result.keys()) == {"a", "b"}
        np.testing.assert_array_almost_equal(result["a"], [0.1, 0.2])

    def test_empty_request(self, store):
        store.upsert("a", "2026-04-15T07:00:00Z", np.array([0.1], dtype=np.float32))
        assert store.get_many([]) == {}


class TestUtilities:
    def test_count_starts_at_zero(self, store):
        assert store.count() == 0

    def test_clear_removes_all(self, store):
        store.upsert("a", "2026-04-15T07:00:00Z", np.array([1.0], dtype=np.float32))
        store.upsert("b", "2026-04-15T07:01:00Z", np.array([2.0], dtype=np.float32))
        assert store.count() == 2
        store.clear()
        assert store.count() == 0


class TestNoDbPath:
    def test_silent_no_op_when_db_path_is_none(self):
        store = EpisodeEmbeddingStore(db_path=None)
        # Should not raise
        store.upsert("a", "ts", np.array([1.0], dtype=np.float32))
        assert store.get("a") is None
        assert store.count() == 0
