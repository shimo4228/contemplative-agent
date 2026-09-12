"""Tests for ADR-0108 — the pattern-embedding sidecar and its consistency codes.

The sidecar moves the 768-dim vectors out of ``knowledge.json`` while leaving
the in-memory pattern dict shape untouched (ADR-0108 D2), so what these tests
guard is the *persistence* boundary: round-trip exactness, the backward
compatible read of an inline-embedding file, the five half-state reason codes,
and the sidecar-before-JSON write order.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from contemplative_agent.core.embeddings import cosine
from contemplative_agent.core.knowledge_store import KnowledgeStore, pattern_id
from contemplative_agent.core.pattern_embeddings import (
    PATTERN_EMBEDDINGS_FILENAME,
    PatternEmbeddingStore,
    sidecar_path_for,
)


def _vec(seed: int, dim: int = 8) -> list[float]:
    rng = np.random.default_rng(seed)
    return rng.standard_normal(dim, dtype=np.float32).tolist()


def _all(store: PatternEmbeddingStore) -> dict[str, np.ndarray]:
    """``get_all()`` where the test asserts the sidecar is readable.

    ``get_all`` returns ``None`` for a damaged file (ADR-0108 D3), so every
    call site has to say which of the three answers it expects; these expect a
    healthy store.
    """
    got = store.get_all()
    assert got is not None, "sidecar unexpectedly unreadable"
    return got


def _inline_store(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


class TestPatternEmbeddingStore:
    def test_upsert_and_get_many_round_trip(self, tmp_path: Path):
        store = PatternEmbeddingStore(tmp_path / PATTERN_EMBEDDINGS_FILENAME)
        v = np.asarray(_vec(1), dtype=np.float32)
        store.upsert_many([("abc123", v)])
        got = _all(store)
        assert list(got) == ["abc123"]
        assert np.array_equal(got["abc123"], v)

    def test_upsert_replaces_by_id(self, tmp_path: Path):
        store = PatternEmbeddingStore(tmp_path / PATTERN_EMBEDDINGS_FILENAME)
        store.upsert_many([("k", np.asarray(_vec(1), dtype=np.float32))])
        second = np.asarray(_vec(2), dtype=np.float32)
        store.upsert_many([("k", second)])
        assert store.count() == 1
        assert np.array_equal(_all(store)["k"], second)

    def test_no_path_is_inert(self):
        store = PatternEmbeddingStore(None)
        assert store.upsert_many([("k", np.zeros(4, dtype=np.float32))]) == 0
        assert store.get_all() == {}
        assert store.count() == 0

    def test_prune_removes_only_unclaimed_ids(self, tmp_path: Path):
        store = PatternEmbeddingStore(tmp_path / PATTERN_EMBEDDINGS_FILENAME)
        store.upsert_many(
            [
                ("keep", np.asarray(_vec(1), dtype=np.float32)),
                ("drop", np.asarray(_vec(2), dtype=np.float32)),
            ]
        )
        assert store.prune({"keep"}) == 1
        assert list(_all(store)) == ["keep"]

    def test_sidecar_path_is_beside_the_knowledge_file(self, tmp_path: Path):
        assert sidecar_path_for(tmp_path / "knowledge.json") == (
            tmp_path / PATTERN_EMBEDDINGS_FILENAME
        )


class TestSaveWritesSidecarNotJson:
    def test_saved_json_carries_no_embedding(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("a pattern worth remembering", embedding=_vec(1))
        store.save()

        rows = json.loads(path.read_text(encoding="utf-8"))
        assert "embedding" not in rows[0]
        assert rows[0]["pattern"] == "a pattern worth remembering"
        assert sidecar_path_for(path).exists()

    def test_save_leaves_the_in_memory_dict_intact(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "knowledge.json")
        store.add_learned_pattern("a pattern worth remembering", embedding=_vec(1))
        store.save()
        assert store.get_raw_patterns()[0]["embedding"] == pytest.approx(_vec(1))

    def test_round_trip_is_bit_exact(self, tmp_path: Path):
        """float32 in, float32 out — cosine verdicts cannot shift (ADR-0108 D1)."""
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        for i in range(5):
            store.add_learned_pattern(
                f"pattern number {i} about agent behaviour", embedding=_vec(i)
            )
        store.save()

        fresh = KnowledgeStore(path=path)
        fresh.load()
        before = store.get_raw_patterns()
        after = fresh.get_raw_patterns()
        assert [p["pattern"] for p in after] == [p["pattern"] for p in before]
        for b, a in zip(before, after, strict=True):
            assert a["embedding"] == b["embedding"]

    def test_cosine_is_identical_across_the_migration(self, tmp_path: Path):
        """Goal 3: the dedup primitive returns the same number before and after."""
        rows = [
            {
                "pattern": f"legacy pattern {i} observed in the wild",
                "distilled": f"2026-09-0{i + 1}T00:00:00+00:00",
                "embedding": _vec(i),
                "valid_until": None,
            }
            for i in range(4)
        ]
        path = _inline_store(tmp_path, rows)

        pre = KnowledgeStore(path=path)
        pre.load()
        query = np.asarray(_vec(99), dtype=np.float32)
        before = [
            cosine(query, np.asarray(p["embedding"], dtype=np.float32))
            for p in pre.get_raw_patterns()
        ]
        pre.save()  # migrates inline → sidecar

        post = KnowledgeStore(path=path)
        post.load()
        after = [
            cosine(query, np.asarray(p["embedding"], dtype=np.float32))
            for p in post.get_raw_patterns()
        ]
        assert after == before  # bit-identical, not approx

    def test_save_refuses_after_a_failed_load(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        path.write_text("not json at all", encoding="utf-8")
        store = KnowledgeStore(path=path)
        store.load()
        store.save()
        assert path.read_text(encoding="utf-8") == "not json at all"
        assert not sidecar_path_for(path).exists()

    def test_sidecar_failure_leaves_the_json_untouched(self, tmp_path: Path):
        """Write order (ADR-0108 D3): sidecar first, so a JSON with no vectors
        anywhere is not reachable through a sidecar fault."""
        path = tmp_path / "knowledge.json"
        path.write_text("[]\n", encoding="utf-8")
        store = KnowledgeStore(path=path)
        store.load()
        store.add_learned_pattern("a pattern worth remembering", embedding=_vec(1))

        def boom(_items):
            raise sqlite3.OperationalError("disk I/O error")

        store._embeddings.upsert_many = boom  # type: ignore[method-assign]
        with pytest.raises(sqlite3.OperationalError):
            store.save()
        assert path.read_text(encoding="utf-8") == "[]\n"


class TestBackwardCompatibleLoad:
    def test_inline_embeddings_are_read_and_reported(self, tmp_path: Path):
        rows = [
            {
                "pattern": "an inline legacy pattern about agents",
                "distilled": "2026-09-01T00:00:00+00:00",
                "embedding": _vec(1),
                "valid_until": None,
            }
        ]
        path = _inline_store(tmp_path, rows)
        store = KnowledgeStore(path=path)
        store.load()
        assert store.get_raw_patterns()[0]["embedding"] == pytest.approx(_vec(1))
        assert store.sidecar_consistency().inline_legacy == 1

    def test_inline_embeddings_move_to_the_sidecar_on_save(self, tmp_path: Path):
        rows = [
            {
                "pattern": "an inline legacy pattern about agents",
                "distilled": "2026-09-01T00:00:00+00:00",
                "embedding": _vec(1),
                "valid_until": None,
            }
        ]
        path = _inline_store(tmp_path, rows)
        store = KnowledgeStore(path=path)
        store.load()
        store.save()

        assert "embedding" not in json.loads(path.read_text(encoding="utf-8"))[0]
        sidecar = PatternEmbeddingStore(sidecar_path_for(path))
        assert list(_all(sidecar)) == [pattern_id(rows[0])]


class TestConsistencyReasonCodes:
    def test_sidecar_absent_is_named(self, tmp_path: Path):
        rows = [
            {
                "pattern": "a pattern restored without its vectors",
                "distilled": "2026-09-01T00:00:00+00:00",
                "valid_until": None,
            }
        ]
        path = _inline_store(tmp_path, rows)
        store = KnowledgeStore(path=path)
        store.load()
        report = store.sidecar_consistency()
        assert report.sidecar_absent is True
        assert report.row_missing == 1
        assert "embedding" not in store.get_raw_patterns()[0]

    def test_row_missing_is_named_and_the_id_recorded(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("first pattern with a vector", embedding=_vec(1))
        store.add_learned_pattern("second pattern with a vector", embedding=_vec(2))
        store.save()
        orphaned = pattern_id(store.get_raw_patterns()[1])
        PatternEmbeddingStore(sidecar_path_for(path)).prune(
            {pattern_id(store.get_raw_patterns()[0])}
        )

        fresh = KnowledgeStore(path=path)
        fresh.load()
        report = fresh.sidecar_consistency()
        assert report.sidecar_absent is False
        assert report.row_missing == 1
        assert orphaned in report.missing_ids

    def test_dim_mismatch_is_named_and_the_row_left_unembedded(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        for i in range(3):
            store.add_learned_pattern(
                f"pattern number {i} about agent behaviour", embedding=_vec(i)
            )
        store.save()
        odd = pattern_id(store.get_raw_patterns()[2])
        PatternEmbeddingStore(sidecar_path_for(path)).upsert_many(
            [(odd, np.ones(3, dtype=np.float32))]
        )

        fresh = KnowledgeStore(path=path)
        fresh.load()
        report = fresh.sidecar_consistency()
        assert report.dim_mismatch == 1
        assert "embedding" not in fresh.get_raw_patterns()[2]
        assert len(fresh.get_raw_patterns()[0]["embedding"]) == 8

    def test_unreadable_sidecar_is_named_not_raised(self, tmp_path: Path):
        """An interrupted restore must not make load() throw (ADR-0108 D3)."""
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("a pattern whose sidecar got truncated", embedding=_vec(1))
        store.save()
        sidecar_path_for(path).write_bytes(b"not a database, a truncated restore")

        fresh = KnowledgeStore(path=path)
        fresh.load()  # must not raise
        report = fresh.sidecar_consistency()
        assert report.sidecar_unreadable is True
        assert report.sidecar_absent is False
        assert report.row_missing == 1
        assert "sidecar_unreadable" in report.reason_codes()
        assert "embedding" not in fresh.get_raw_patterns()[0]
        # The rows survive; only the vectors are gone.
        assert fresh.get_raw_patterns()[0]["pattern"] == "a pattern whose sidecar got truncated"

    def test_get_all_returns_none_for_an_unreadable_file(self, tmp_path: Path):
        p = tmp_path / PATTERN_EMBEDDINGS_FILENAME
        p.write_bytes(b"not a database")
        assert PatternEmbeddingStore(p).get_all() is None

    def test_get_all_returns_empty_for_an_absent_file(self, tmp_path: Path):
        assert PatternEmbeddingStore(tmp_path / PATTERN_EMBEDDINGS_FILENAME).get_all() == {}

    def test_orphan_vectors_are_counted(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("the only surviving pattern", embedding=_vec(1))
        store.save()
        PatternEmbeddingStore(sidecar_path_for(path)).upsert_many(
            [("deadbeefdead", np.zeros(8, dtype=np.float32))]
        )

        fresh = KnowledgeStore(path=path)
        fresh.load()
        assert fresh.sidecar_consistency().orphan_vectors == 1

    def test_a_clean_store_reports_nothing(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("a perfectly ordinary pattern", embedding=_vec(1))
        store.save()
        fresh = KnowledgeStore(path=path)
        fresh.load()
        report = fresh.sidecar_consistency()
        assert report.clean is True
        assert report.reason_codes() == []

    def test_reason_codes_lists_every_fired_code(self, tmp_path: Path):
        rows = [
            {
                "pattern": "a pattern restored without its vectors",
                "distilled": "2026-09-01T00:00:00+00:00",
                "valid_until": None,
            }
        ]
        path = _inline_store(tmp_path, rows)
        store = KnowledgeStore(path=path)
        store.load()
        assert set(store.sidecar_consistency().reason_codes()) == {
            "sidecar_absent",
            "row_missing",
        }


class TestExplicitSidecarPath:
    def test_embeddings_path_overrides_the_sibling_default(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        elsewhere = tmp_path / "vectors" / "custom.sqlite"
        store = KnowledgeStore(path=path, embeddings_path=elsewhere)
        store.add_learned_pattern("a pattern worth remembering", embedding=_vec(1))
        store.save()
        assert elsewhere.exists()
        assert not sidecar_path_for(path).exists()

    def test_a_pathless_store_still_works_in_memory(self):
        store = KnowledgeStore()
        store.add_learned_pattern("a pattern worth remembering", embedding=_vec(1))
        store.save()  # no path — a no-op, must not raise
        assert store.get_raw_patterns()[0]["embedding"] == pytest.approx(_vec(1))


class TestSidecarFileMode:
    def test_sidecar_is_not_world_readable(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("a pattern worth remembering", embedding=_vec(1))
        store.save()
        mode = sidecar_path_for(path).stat().st_mode & 0o077
        assert mode == 0


class TestMalformedEmbeddingsDoNotBlockSave:
    """A corrupt legacy row must not make the whole store unsaveable.

    Before ADR-0108 such a row round-tripped through the JSON untouched. The
    sidecar has to coerce it to float32, so the failure mode has to be chosen:
    skip the vector and keep the text, rather than raise and lose the save.
    """

    @pytest.mark.parametrize(
        "bad",
        [
            pytest.param(["not", "numbers"], id="strings"),
            pytest.param([[1.0, 2.0], [3.0, 4.0]], id="nested"),
            pytest.param([None, None], id="nulls-become-nan"),
            pytest.param([float("nan")] * 8, id="nan"),
            pytest.param([float("inf")] * 8, id="inf"),
        ],
    )
    def test_bad_vector_is_skipped_and_the_row_survives(self, tmp_path: Path, bad, caplog):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("a good pattern with a good vector", embedding=_vec(1))
        store.add_learned_pattern("a pattern whose vector is corrupt", embedding=bad)
        with caplog.at_level("WARNING"):
            store.save()

        fresh = KnowledgeStore(path=path)
        fresh.load()
        rows = fresh.get_raw_patterns()
        assert [p["pattern"] for p in rows] == [
            "a good pattern with a good vector",
            "a pattern whose vector is corrupt",
        ]
        assert rows[0]["embedding"] == pytest.approx(_vec(1))
        assert "embedding" not in rows[1]
        assert fresh.sidecar_consistency().row_missing == 1

    def test_empty_vector_is_skipped_without_a_warning(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("a pattern with an empty vector", embedding=[])
        store.save()
        assert PatternEmbeddingStore(sidecar_path_for(path)).count() == 0


class TestContentionIsLoudDamageIsNamed:
    """Code review 2026-09-12: a momentary lock must not read as a corrupt file.

    Both arrive as ``sqlite3.Error``. Degrading on contention the way D3
    degrades on damage would run a whole distill with zero vectors — dedup and
    views skip embedding-less rows, so the run re-adds duplicates and the
    views return nothing, with one WARNING as the only evidence.
    """

    def test_a_damaged_file_degrades(self, tmp_path: Path):
        p = tmp_path / PATTERN_EMBEDDINGS_FILENAME
        p.write_bytes(b"not a database")
        assert PatternEmbeddingStore(p).get_all() is None

    def test_a_locked_file_raises(self, tmp_path: Path, monkeypatch):
        p = tmp_path / PATTERN_EMBEDDINGS_FILENAME
        store = PatternEmbeddingStore(p)
        store.upsert_many([("k", np.asarray(_vec(1), dtype=np.float32))])

        def locked(*_a, **_kw):
            raise sqlite3.OperationalError("database is locked")

        monkeypatch.setattr(sqlite3, "connect", locked)
        with pytest.raises(sqlite3.OperationalError):
            store.get_all()

    def test_connect_carries_a_busy_timeout(self, tmp_path: Path):
        """Contention has to have time to clear before it becomes an error."""
        from contemplative_agent.core.pattern_embeddings import _BUSY_TIMEOUT_S

        assert _BUSY_TIMEOUT_S >= 30.0


class TestDimColumnIsRead:
    """The dim column has to be checked, or it is write-only documentation."""

    def test_a_truncated_blob_is_treated_as_absent(self, tmp_path: Path):
        p = tmp_path / PATTERN_EMBEDDINGS_FILENAME
        store = PatternEmbeddingStore(p)
        store.upsert_many([("k", np.asarray(_vec(1, dim=8), dtype=np.float32))])
        with sqlite3.connect(str(p)) as conn:
            conn.execute(
                "UPDATE pattern_embeddings SET vector = ? WHERE pattern_id = 'k'",
                (np.ones(4, dtype=np.float32).tobytes(),),
            )
        assert _all(store) == {}

    def test_an_intact_blob_survives(self, tmp_path: Path):
        p = tmp_path / PATTERN_EMBEDDINGS_FILENAME
        store = PatternEmbeddingStore(p)
        store.upsert_many([("k", np.asarray(_vec(1, dim=8), dtype=np.float32))])
        assert list(_all(store)) == ["k"]


class TestTablelessSidecarDoesNotRaise:
    """A zero-byte file (interrupted first save, rsync leftover) reaches prune
    *after* save() has rewritten the store — a traceback there lands where the
    runbook says the migration succeeded."""

    def test_prune_survives_a_file_with_no_table(self, tmp_path: Path):
        p = tmp_path / PATTERN_EMBEDDINGS_FILENAME
        p.write_bytes(b"")
        assert PatternEmbeddingStore(p).prune({"anything"}) == 0

    def test_count_survives_a_file_with_no_table(self, tmp_path: Path):
        p = tmp_path / PATTERN_EMBEDDINGS_FILENAME
        p.write_bytes(b"")
        assert PatternEmbeddingStore(p).count() == 0

    def test_count_survives_a_damaged_file(self, tmp_path: Path):
        p = tmp_path / PATTERN_EMBEDDINGS_FILENAME
        p.write_bytes(b"not a database")
        assert PatternEmbeddingStore(p).count() == 0


class TestRowsThePaserRefuses:
    """A save rewrites the whole array, so a row the parser drops is deleted."""

    def test_dropped_rows_are_counted_and_warned(self, tmp_path: Path, caplog):
        path = tmp_path / "knowledge.json"
        path.write_text(
            json.dumps(
                [
                    {"pattern": "a real row", "distilled": "2026-09-01T00:00:00+00:00"},
                    {"no_pattern_key": True},
                    12345,
                ]
            ),
            encoding="utf-8",
        )
        store = KnowledgeStore(path=path)
        with caplog.at_level("WARNING"):
            store.load()
        assert store.dropped_rows == 2
        assert "NOT loaded" in caplog.text

    def test_a_clean_store_drops_nothing(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("a perfectly ordinary pattern", embedding=_vec(1))
        store.save()
        fresh = KnowledgeStore(path=path)
        fresh.load()
        assert fresh.dropped_rows == 0
