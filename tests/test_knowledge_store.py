"""Tests for ADR-0021 pattern schema additions in KnowledgeStore.

ADR-0028 retired the pattern-level forgetting (access_count /
last_accessed_at / strength) and feedback (success_count / failure_count)
fields. Their tests are removed from this file.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from contemplative_agent.core.knowledge_store import (
    KnowledgeStore,
    effective_importance,
    is_live,
)


class TestLoadIdempotency:
    """Regression: load() must reset state so repeated calls do not duplicate.

    Multiple commands (insight, distill, distill-identity) call load()
    at both the CLI handler and core function layer. Without idempotency
    a subsequent save() persists the doubled list — observed in the wild
    as 285 pairs with identical valid_from on a production knowledge.json.
    """

    def test_load_twice_does_not_duplicate(self, tmp_path: Path):
        path = tmp_path / "k.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("first observed behavior pattern in agent logs")
        store.add_learned_pattern("second observed behavior pattern in agent logs")
        store.save()

        fresh = KnowledgeStore(path=path)
        fresh.load()
        first_count = len(fresh.get_raw_patterns())
        fresh.load()
        second_count = len(fresh.get_raw_patterns())

        assert first_count == 2
        assert second_count == first_count

    def test_load_resets_preexisting_in_memory_state(self, tmp_path: Path):
        path = tmp_path / "k.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern("persisted pattern written to disk")
        store.save()

        fresh = KnowledgeStore(path=path)
        fresh.add_learned_pattern("in-memory only pattern not on disk")
        fresh.load()

        texts = [p["pattern"] for p in fresh.get_raw_patterns()]
        assert texts == ["persisted pattern written to disk"]


class TestSaveRefusesAfterFailedLoad:
    """HIGH-4 regression (ultracode sweep 2026-06-23).

    When load() finds an existing file it cannot read/parse it leaves
    _learned_patterns empty. An unconditional save() would then atomically
    replace the populated file with `[]` and no `.bak` — destroying ~all
    persisted patterns. save() must refuse while _load_failed is set.
    """

    def _populated_file(self, tmp_path: Path) -> Path:
        path = tmp_path / "k.json"
        seed = KnowledgeStore(path=path)
        seed.add_learned_pattern("first persisted behavior pattern from the logs")
        seed.add_learned_pattern("second persisted behavior pattern from the logs")
        seed.save()
        return path

    def test_forbidden_pattern_load_then_save_does_not_wipe_file(self, tmp_path: Path):
        path = self._populated_file(tmp_path)
        # Taint the file with a forbidden substring (config: "api_key").
        path.write_text(path.read_text().replace("first", "api_key first"), "utf-8")

        store = KnowledgeStore(path=path)
        store.load()  # forbidden pattern → load fails, in-memory list empty
        assert store.get_raw_patterns() == []
        store.save()  # must be a no-op, not an empty overwrite

        # File on disk is untouched: a fresh clean store still loads 2 patterns.
        path.write_text(path.read_text().replace("api_key first", "first"), "utf-8")
        recovered = KnowledgeStore(path=path)
        recovered.load()
        assert len(recovered.get_raw_patterns()) == 2

    def test_corrupt_json_load_then_save_does_not_wipe_file(self, tmp_path: Path):
        path = self._populated_file(tmp_path)
        original = path.read_text()
        path.write_text("[ this is not valid json", "utf-8")

        store = KnowledgeStore(path=path)
        store.load()  # JSONDecodeError → load fails
        assert store.get_raw_patterns() == []
        store.save()  # no-op

        # The corrupt bytes are still there (not replaced with "[]").
        assert path.read_text() == "[ this is not valid json"
        # And restoring the original content reloads cleanly.
        path.write_text(original, "utf-8")
        recovered = KnowledgeStore(path=path)
        recovered.load()
        assert len(recovered.get_raw_patterns()) == 2

    def test_fresh_store_with_no_file_can_still_save(self, tmp_path: Path):
        # A brand-new store (no backing file) must NOT be blocked: the
        # missing-file path is a legitimate empty store, not a failed load.
        path = tmp_path / "new.json"
        store = KnowledgeStore(path=path)
        store.load()  # file does not exist → not a failure
        store.add_learned_pattern("a freshly distilled behavior pattern")
        store.save()

        recovered = KnowledgeStore(path=path)
        recovered.load()
        assert len(recovered.get_raw_patterns()) == 1


class TestAddLearnedPatternADR0021:
    def test_defaults_for_new_pattern(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern("observed something interesting in the agent logs today")
        assert len(store.get_raw_patterns()) == 1
        p = store.get_raw_patterns()[0]
        assert p["provenance"] == {"source_type": "unknown"}
        assert p["valid_until"] is None
        assert p["valid_from"] == p["distilled"]
        # ADR-0028: last_accessed_at / access_count / success_count /
        # failure_count are no longer written.
        assert "access_count" not in p
        assert "last_accessed_at" not in p
        assert "success_count" not in p
        assert "failure_count" not in p
        # ADR-0051: trust fields are no longer written.
        assert "trust_score" not in p
        assert "trust_updated_at" not in p

    def test_explicit_provenance_preserved(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        prov = {
            "source_type": "self_reflection",
            "source_episode_ids": ["2026-04-15#1"],
            "pipeline_version": "distill@0.21",
        }
        store.add_learned_pattern(
            "reflective note on boundless care", provenance=prov
        )
        p = store.get_raw_patterns()[0]
        assert p["provenance"] == prov


class TestRoundTripADR0021:
    def test_save_then_load_preserves_new_fields(self, tmp_path: Path):
        path = tmp_path / "k.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern(
            "long enough pattern to pass the valid pattern gate easily",
            provenance={"source_type": "external_reply"},
        )
        store.save()

        # Re-load and verify round-trip
        store2 = KnowledgeStore(path=path)
        store2.load()
        p = store2.get_raw_patterns()[0]
        assert p["provenance"]["source_type"] == "external_reply"
        assert p["valid_until"] is None
        # ADR-0028: retired fields never round-trip even if artificially
        # present in the on-disk JSON.
        assert "last_accessed_at" not in p
        assert "access_count" not in p
        # ADR-0029: ``provenance.sanitized`` is dropped at load even if
        # present on disk.
        assert "sanitized" not in p["provenance"]

    def test_legacy_file_loads_without_adr0021_fields(self, tmp_path: Path):
        """Files written by pre-0021 code should load cleanly, without auto-fill."""
        path = tmp_path / "k.json"
        legacy = [
            {
                "pattern": "legacy pattern without any ADR-0021 metadata present",
                "distilled": "2026-03-01T00:00",
                "importance": 0.7,
                "category": "uncategorized",
            }
        ]
        path.write_text(json.dumps(legacy), encoding="utf-8")
        store = KnowledgeStore(path=path)
        store.load()
        p = store.get_raw_patterns()[0]
        assert "provenance" not in p
        assert "trust_score" not in p
        assert "valid_until" not in p

    def test_legacy_trust_fields_load_cleanly_and_are_shed(self, tmp_path: Path):
        """ADR-0051: rows carrying trust_score / trust_updated_at load
        without error, the fields are not carried into memory, and the
        next save writes them out of the file."""
        path = tmp_path / "k.json"
        legacy = [
            {
                "pattern": "legacy row with trust fields from the ADR-0021 era",
                "distilled": "2026-04-16T00:00",
                "importance": 0.7,
                "provenance": {"source_type": "self_reflection"},
                "trust_score": 0.9,
                "trust_updated_at": "2026-04-16T00:00",
                "valid_from": "2026-04-16T00:00",
                "valid_until": None,
            }
        ]
        path.write_text(json.dumps(legacy), encoding="utf-8")
        store = KnowledgeStore(path=path)
        store.load()
        p = store.get_raw_patterns()[0]
        assert "trust_score" not in p
        assert "trust_updated_at" not in p
        # ADR-0056: a legacy importance rating is shed on load too.
        assert "importance" not in p
        assert p["provenance"]["source_type"] == "self_reflection"

        store.save()
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert "trust_score" not in on_disk[0]
        assert "trust_updated_at" not in on_disk[0]
        assert "importance" not in on_disk[0]

    def test_legacy_last_accessed_loads_cleanly_and_is_shed(self, tmp_path: Path):
        """ADR-0028: rows carrying ``last_accessed`` (pattern-layer forgetting)
        load without error, the field is not carried into memory, and the next
        save writes it out of the file."""
        path = tmp_path / "k.json"
        legacy = [
            {
                "pattern": "legacy row with a last_accessed forgetting field",
                "distilled": "2026-03-01T00:00",
                "provenance": {"source_type": "self_reflection"},
                "last_accessed": "2026-03-15T12:00",
                "valid_from": "2026-03-01T00:00",
                "valid_until": None,
            }
        ]
        path.write_text(json.dumps(legacy), encoding="utf-8")
        store = KnowledgeStore(path=path)
        store.load()
        p = store.get_raw_patterns()[0]
        assert "last_accessed" not in p
        assert p["provenance"]["source_type"] == "self_reflection"

        store.save()
        on_disk = json.loads(path.read_text(encoding="utf-8"))
        assert "last_accessed" not in on_disk[0]


class TestEffectiveImportance:
    def test_fresh_pattern_scores_near_one(self):
        """ADR-0056: pure time decay — a fresh pattern is ~1.0 with no
        dependence on any stored importance rating."""
        now = datetime.now(timezone.utc)
        p = {"distilled": now.isoformat(timespec="minutes")}
        score = effective_importance(p)
        assert 0.9 <= score <= 1.0

    def test_legacy_importance_and_trust_are_ignored(self):
        """ADR-0051/0056: legacy trust_score and importance fields on the row
        must not move the decay-only score."""
        now = datetime.now(timezone.utc)
        plain = {"distilled": now.isoformat(timespec="minutes")}
        with_legacy = {**plain, "trust_score": 0.3, "importance": 0.2}
        assert effective_importance(with_legacy) == pytest.approx(
            effective_importance(plain)
        )

    def test_aged_pattern_decays_monotonically(self):
        """Batch G regression (ultracode sweep 2026-06-23): the aged branch
        (0.95**days) previously had no coverage — only the days=0 case was
        tested, so a regression in the decay math would reorder distill output
        silently. Pin the curve at several ages."""
        now = datetime.now(timezone.utc)

        def at_age(days: float) -> float:
            ts = (now - timedelta(days=days)).isoformat(timespec="minutes")
            return effective_importance({"distilled": ts})

        fresh, d10, d30, d60 = at_age(0), at_age(10), at_age(30), at_age(60)
        # Strictly decreasing with age.
        assert fresh > d10 > d30 > d60
        # Known points of 0.95**days (decay-only, ADR-0056).
        assert d10 == pytest.approx(0.95 ** 10, abs=1e-3)
        assert d60 == pytest.approx(0.95 ** 60, abs=1e-3)
        # ~58-day half-life: 0.95**~13.5 ≈ 0.5.
        assert at_age(13.5) == pytest.approx(0.5, abs=0.02)


class TestIsLive:
    """ADR-0051: is_live gates on bitemporal only."""

    def test_is_live_rejects_invalidated(self):
        p = {"valid_until": "2026-04-01T00:00"}
        assert not is_live(p)

    def test_is_live_ignores_legacy_low_trust(self):
        """ADR-0051: a legacy trust_score, however low, no longer gates."""
        p = {"valid_until": None, "trust_score": 0.1}
        assert is_live(p)

    def test_is_live_accepts_current(self):
        p = {"valid_until": None}
        assert is_live(p)

    def test_is_live_tolerates_missing_fields(self):
        # Pre-ADR-0021 legacy rows without valid_until remain live.
        assert is_live({"pattern": "legacy"})


class TestFilterSinceBadTimestampADR0021:
    """ADR-0021 — bad ``since`` ISO returns the full pool; individual
    records with malformed ``distilled`` are skipped rather than crashing
    the whole filter. Exercised via ``get_live_patterns_since`` (the only
    surviving ``_filter_since`` consumer after the dead
    ``get_raw_patterns_since`` was removed)."""

    def test_bad_since_string_falls_back_to_full_pool(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "pattern alpha that is long enough to pass the valid gate easily",
        )
        store.add_learned_pattern(
            "pattern beta that is long enough to pass the valid gate easily",
        )

        result = store.get_live_patterns_since("not-an-iso-timestamp")
        assert len(result) == 2

    def test_record_with_bad_distilled_is_skipped(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "good pattern with a properly formatted distilled timestamp field",
        )
        store._learned_patterns.append({
            "pattern": "broken record with malformed distilled",
            "distilled": "not-a-real-iso",
        })

        result = store.get_live_patterns_since("2020-01-01T00:00:00+00:00")
        assert any("good pattern" in p["pattern"] for p in result)
        assert not any("broken record" in p["pattern"] for p in result)

    def test_naive_distilled_not_dropped_against_aware_since(self, tmp_path: Path):
        # D10 regression (ultracode sweep 2026-06-23): a tz-naive ``distilled``
        # compared against a tz-aware ``since`` used to raise TypeError and
        # silently drop the pattern. Both sides are now coerced to UTC, so a
        # naive timestamp clearly after the since-bound is kept.
        store = KnowledgeStore(path=tmp_path / "k.json")
        store._learned_patterns.append({
            "pattern": "recent pattern stamped with a tz-naive distilled time",
            "distilled": "2026-06-20T12:00:00",  # naive (no offset)
        })
        result = store.get_live_patterns_since("2026-06-01T00:00:00+00:00")  # aware
        assert any("recent pattern" in p["pattern"] for p in result)


class TestPatternIdADR0050:
    """ADR-0050 — computed content-hash identity, no persisted field."""

    def test_stable_for_same_dict(self):
        from contemplative_agent.core.knowledge_store import pattern_id

        p = {"pattern": "observed a recurring greeting style", "distilled": "2026-06-05T10:00+00:00"}
        assert pattern_id(p) == pattern_id(dict(p))

    def test_twelve_hex_chars(self):
        from contemplative_agent.core.knowledge_store import pattern_id

        p = {"pattern": "some pattern text", "distilled": "2026-06-05T10:00+00:00"}
        pid = pattern_id(p)
        assert len(pid) == 12
        assert all(c in "0123456789abcdef" for c in pid)

    def test_differs_on_text_change(self):
        """Bitemporal revision (ADR-0021 soft-invalidate + revised ADD) yields
        a new row with different text — the revised row must get its own id."""
        from contemplative_agent.core.knowledge_store import pattern_id

        old = {"pattern": "agents prefer short replies", "distilled": "2026-06-05T10:00+00:00"}
        revised = {"pattern": "agents prefer short replies in technical threads", "distilled": "2026-06-05T10:00+00:00"}
        assert pattern_id(old) != pattern_id(revised)

    def test_differs_on_timestamp_change(self):
        from contemplative_agent.core.knowledge_store import pattern_id

        a = {"pattern": "same text", "distilled": "2026-06-05T10:00+00:00"}
        b = {"pattern": "same text", "distilled": "2026-06-05T10:01+00:00"}
        assert pattern_id(a) != pattern_id(b)

    def test_legacy_row_missing_fields_still_computes(self):
        from contemplative_agent.core.knowledge_store import pattern_id

        assert isinstance(pattern_id({}), str)
        assert len(pattern_id({})) == 12


class TestEpistemicKindForADR0050:
    """ADR-0050 — 2-valued read-time derivation from provenance.source_type."""

    @pytest.mark.parametrize("source_type,expected", [
        ("self_reflection", "generated"),
        ("mixed", "generated"),
        ("external_reply", "observed"),
        ("unknown", None),
    ], ids=["self-reflection", "mixed", "external-reply", "unknown"])
    def test_mapping(self, source_type, expected):
        from contemplative_agent.core.knowledge_store import epistemic_kind_for

        p = {"provenance": {"source_type": source_type}}
        assert epistemic_kind_for(p) == expected

    def test_missing_provenance_returns_none(self):
        from contemplative_agent.core.knowledge_store import epistemic_kind_for

        assert epistemic_kind_for({}) is None
        assert epistemic_kind_for({"provenance": {}}) is None


class TestEpistemicCountsForADR0050:
    def test_counts_all_three_keys_always_present(self):
        from contemplative_agent.core.knowledge_store import epistemic_counts_for

        patterns = [
            {"provenance": {"source_type": "self_reflection"}},
            {"provenance": {"source_type": "self_reflection"}},
            {"provenance": {"source_type": "external_reply"}},
            {"provenance": {"source_type": "unknown"}},
            {},  # legacy row without provenance
        ]
        counts = epistemic_counts_for(patterns)
        assert counts == {"observed": 1, "generated": 2, "unknown": 2}

    def test_empty_input(self):
        from contemplative_agent.core.knowledge_store import epistemic_counts_for

        assert epistemic_counts_for([]) == {"observed": 0, "generated": 0, "unknown": 0}
