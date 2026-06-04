"""Tests for ADR-0021 pattern schema additions in KnowledgeStore.

ADR-0028 retired the pattern-level forgetting (access_count /
last_accessed_at / strength) and feedback (success_count / failure_count)
fields. Their tests are removed from this file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from contemplative_agent.core.knowledge_store import (
    DEFAULT_TRUST,
    TRUST_BASE_BY_SOURCE,
    KnowledgeStore,
    effective_importance,
)
from contemplative_agent.core.forgetting import TRUST_FLOOR, is_live


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


class TestAddLearnedPatternADR0021:
    def test_defaults_for_new_pattern(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern("observed something interesting in the agent logs today")
        assert len(store.get_raw_patterns()) == 1
        p = store.get_raw_patterns()[0]
        assert p["provenance"] == {"source_type": "unknown"}
        assert p["trust_score"] == DEFAULT_TRUST
        assert p["valid_until"] is None
        assert p["valid_from"] == p["distilled"]
        # ADR-0028: last_accessed_at / access_count / success_count /
        # failure_count are no longer written.
        assert "access_count" not in p
        assert "last_accessed_at" not in p
        assert "success_count" not in p
        assert "failure_count" not in p

    def test_explicit_provenance_preserved(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        prov = {
            "source_type": "self_reflection",
            "source_episode_ids": ["2026-04-15#1"],
            "pipeline_version": "distill@0.21",
        }
        store.add_learned_pattern(
            "reflective note on boundless care", provenance=prov, trust_score=0.88
        )
        p = store.get_raw_patterns()[0]
        assert p["provenance"] == prov
        assert p["trust_score"] == pytest.approx(0.88)


class TestRoundTripADR0021:
    def test_save_then_load_preserves_new_fields(self, tmp_path: Path):
        path = tmp_path / "k.json"
        store = KnowledgeStore(path=path)
        store.add_learned_pattern(
            "long enough pattern to pass the valid pattern gate easily",
            provenance={"source_type": "external_reply"},
            trust_score=0.42,
        )
        store.save()

        # Re-load and verify round-trip
        store2 = KnowledgeStore(path=path)
        store2.load()
        p = store2.get_raw_patterns()[0]
        assert p["provenance"]["source_type"] == "external_reply"
        assert p["trust_score"] == pytest.approx(0.42)
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


class TestEffectiveImportanceADR0021:
    def test_legacy_path_unaffected_without_fields(self):
        """Patterns without trust/strength fields score as legacy importance × decay."""
        now = datetime.now(timezone.utc)
        p = {"importance": 1.0, "distilled": now.isoformat(timespec="minutes")}
        # Fresh pattern at importance 1.0 → very close to 1.0
        score = effective_importance(p)
        assert 0.9 <= score <= 1.0

    def test_low_trust_reduces_score(self):
        now = datetime.now(timezone.utc)
        high_trust = {
            "importance": 1.0,
            "distilled": now.isoformat(timespec="minutes"),
            "trust_score": 1.0,
        }
        low_trust = {**high_trust, "trust_score": 0.3}
        assert effective_importance(low_trust) < effective_importance(high_trust)
        # Ratio ≈ 0.3 (pure trust; strength multiplier retired by ADR-0028)
        ratio = effective_importance(low_trust) / effective_importance(high_trust)
        assert 0.25 <= ratio <= 0.35


class TestIsLive:
    """ADR-0028: is_live gates on bitemporal + trust floor only."""

    def test_is_live_rejects_invalidated(self):
        p = {"valid_until": "2026-04-01T00:00", "trust_score": 1.0}
        assert not is_live(p)

    def test_is_live_rejects_low_trust(self):
        p = {"valid_until": None, "trust_score": TRUST_FLOOR - 0.01}
        assert not is_live(p)

    def test_is_live_accepts_current_trusted(self):
        p = {"valid_until": None, "trust_score": 0.6}
        assert is_live(p)

    def test_is_live_tolerates_missing_fields(self):
        # Pre-ADR-0021 legacy rows without trust_score / valid_until fall
        # through to defaults (trust=1.0, current=True) and remain live.
        assert is_live({"pattern": "legacy"})


class TestTrustBaseBySource:
    def test_self_reflection_highest(self):
        assert TRUST_BASE_BY_SOURCE["self_reflection"] > TRUST_BASE_BY_SOURCE["external_reply"]
        assert TRUST_BASE_BY_SOURCE["self_reflection"] > TRUST_BASE_BY_SOURCE["mixed"]
        assert TRUST_BASE_BY_SOURCE["self_reflection"] > TRUST_BASE_BY_SOURCE["unknown"]

    def test_all_within_range(self):
        for name, value in TRUST_BASE_BY_SOURCE.items():
            assert 0.0 <= value <= 1.0, f"{name}={value} out of range"


class TestReplacePatternADR0021:
    """ADR-0021 / knowledge_store.py:155-166 — replace_pattern swaps a
    pattern by identity (``is``). If this breaks, bitemporal invalidation
    fails silently: the old pattern stays live and the chain corrupts."""

    def test_returns_true_and_swaps_in_place(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "long enough pattern to pass the valid pattern gate easily",
        )
        old = store._learned_patterns[0]
        new = dict(old)
        new["valid_until"] = "2026-05-01T00:00:00+00:00"

        assert store.replace_pattern(old, new) is True
        assert len(store._learned_patterns) == 1
        assert store._learned_patterns[0] is new

    def test_returns_false_when_target_not_present(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "long enough pattern to pass the valid pattern gate easily",
        )
        stranger = {"pattern": "not in store", "distilled": "2026-01-01"}

        assert store.replace_pattern(stranger, {"pattern": "irrelevant"}) is False
        assert len(store._learned_patterns) == 1


class TestFilterSinceBadTimestampADR0021:
    """ADR-0021 / knowledge_store.py:183-199 — bad ``since`` ISO returns the
    full pool; individual records with malformed ``distilled`` are skipped
    rather than crashing the whole filter."""

    def test_bad_since_string_falls_back_to_full_pool(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "pattern alpha that is long enough to pass the valid gate easily",
        )
        store.add_learned_pattern(
            "pattern beta that is long enough to pass the valid gate easily",
        )

        result = store.get_raw_patterns_since("not-an-iso-timestamp")
        assert len(result) == 2

    def test_record_with_bad_distilled_is_skipped(self, tmp_path: Path):
        store = KnowledgeStore(path=tmp_path / "k.json")
        store.add_learned_pattern(
            "good pattern with a properly formatted distilled timestamp field",
        )
        store._learned_patterns.append({
            "pattern": "broken record with malformed distilled",
            "distilled": "not-a-real-iso",
            "importance": 0.5,
        })

        result = store.get_raw_patterns_since("2020-01-01T00:00:00+00:00")
        assert any("good pattern" in p["pattern"] for p in result)
        assert not any("broken record" in p["pattern"] for p in result)


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
