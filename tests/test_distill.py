"""Tests for sleep-time memory distillation (ADR-0009 embedding-based)."""

import json
from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from contemplative_agent.core.distill import (
    summarize_record,
    distill,
    distill_identity,
    enrich,
    IdentityResult,
    _is_valid_pattern,
    _classify_episodes,
    _ClassifiedRecords,
    _dedup_patterns,
    SIM_DUPLICATE,
    SIM_UPDATE,
)
from contemplative_agent.core.knowledge_store import effective_importance
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore


def _make_log(tmp_path):
    """Helper: create EpisodeLog with one interaction."""
    log = EpisodeLog(log_dir=tmp_path / "logs")
    log.append("interaction", {
        "direction": "sent", "agent_name": "Alice",
        "content_summary": "Hello", "agent_id": "a1",
    })
    return log


def _embedding(*values):
    """Helper: build a 1D float32 array."""
    return np.array(values, dtype=np.float32)


@pytest.fixture
def mock_embed_distinct():
    """Patch embed_texts to return (n, 4) distinct one-hot-ish vectors."""
    def _mk(texts):
        # Distinct, low-similarity vectors so dedup doesn't trigger
        n = len(texts)
        return np.array(
            [[1.0 if i == j else 0.0 for j in range(max(n, 4))] for i in range(n)],
            dtype=np.float32,
        )

    with patch("contemplative_agent.core.distill.embed_texts", side_effect=_mk) as m:
        yield m


class TestDistill:
    """Pipeline: classify → extract → refine → embed → dedup → save (ADR-0056: no importance step)."""

    @patch("contemplative_agent.core.distill.generate")
    def test_basic_distillation(self, mock_generate, mock_embed_distinct, tmp_path):
        # classify is now embedding-based (no generate call); only extract / refine.
        mock_generate.side_effect = [
            "Some free-form analysis of patterns from the episode logs.",
            json.dumps({"patterns": [
                "Pattern one shows that quoting specific details improves engagement",
                "Pattern two reveals that generic replies stall conversations quickly",
            ]}),
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {
            "direction": "sent", "agent_name": "Alice",
            "content_summary": "Hello", "agent_id": "a1",
        })
        log.append("activity", {"action": "comment", "post_id": "p1"})

        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "Pattern one" in result
        assert "Pattern two" in result

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        patterns = [p["pattern"] for p in ks2.get_raw_patterns()]
        assert any("Pattern one" in p for p in patterns)
        assert any("Pattern two" in p for p in patterns)
        # ADR-0056: no importance field is written; extraction weight is decay.
        p1 = [p for p in ks2._learned_patterns if "Pattern one" in p["pattern"]][0]
        assert "importance" not in p1
        # Embedding stored
        assert isinstance(p1["embedding"], list)

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, mock_embed_distinct, tmp_path):
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": [
                "Dry pattern that explains how quoting specific details works better",
            ]}),
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, dry_run=True, episode_log=log, knowledge_store=ks)
        assert "Dry pattern" in result
        assert not (tmp_path / "knowledge.json").exists()

    def test_empty_episodes(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "No episodes" in result

    @patch("contemplative_agent.core.distill.generate", return_value=None)
    def test_llm_failure(self, mock_generate, tmp_path):
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert result == ""
        assert not (tmp_path / "knowledge.json").exists()


class TestEnrichNoOp:
    def test_enrich_returns_zero(self):
        ks = KnowledgeStore()
        assert enrich(ks) == 0


class TestDistillJSONFallbackADR0021:
    """ADR-0021 / distill.py:548-555 — when the refine step returns text
    that is not valid JSON, the bullet-point parser recovers patterns from
    lines starting with ``- ``. In production the LLM occasionally
    violates the JSON-only instruction; without this fallback the whole
    batch would silently yield zero patterns."""

    @patch("contemplative_agent.core.distill.generate")
    def test_bullet_list_recovered_when_refine_is_not_json(
        self, mock_generate, mock_embed_distinct, tmp_path,
    ):
        mock_generate.side_effect = [
            "Some free-form analysis.",
            # Refine step returns bullets, NOT JSON — tests the fallback.
            "- First bullet pattern that explains quoting details clearly here\n"
            "- Second bullet pattern that reveals generic replies stall people",
        ]

        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill(days=1, episode_log=log, knowledge_store=ks)

        assert "First bullet pattern" in result
        assert "Second bullet pattern" in result


class TestDistillStep2BatchSkipAuditM1:
    """Audit M1: when step 2 (summarize) fails, the batch is skipped with a
    WARNING instead of feeding step-1 prose to the JSON parser — prose that
    happens to lack "- " bullets would otherwise silently yield 0 patterns
    while looking like a processed batch."""

    @patch("contemplative_agent.core.distill.generate")
    def test_step2_none_skips_batch(self, mock_generate, tmp_path, caplog):
        import logging
        # Step-1 prose containing "- " lines: under the old fallthrough
        # (refined = result) the bullet parser would harvest these as
        # patterns; under batch skip they must NOT become patterns.
        mock_generate.side_effect = [
            "Some free-form analysis.\n"
            "- This unrefined observation looks like a pattern to the parser\n"
            "- Another raw step-one line that must not reach the store",
            None,  # step 2 fails
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        with caplog.at_level(
            logging.WARNING, logger="contemplative_agent.core.distill"
        ):
            distill(days=1, episode_log=log, knowledge_store=ks)
        assert "step 2" in caplog.text
        # Batch skipped: no step-3 importance call, nothing persisted.
        assert mock_generate.call_count == 2
        assert not (tmp_path / "knowledge.json").exists()


class TestInsightExclusionADR0052:
    """Audit M4 / ADR-0052: insight records are LLM session summaries, not
    observations. Re-distilling them creates summary-of-summary patterns,
    so distill must exclude them at read time — including historical
    records that remain in the log after generation was retired."""

    @patch("contemplative_agent.core.distill.generate")
    def test_insight_records_excluded_from_prompts(
        self, mock_generate, mock_embed_distinct, tmp_path, caplog
    ):
        import logging
        mock_generate.side_effect = [
            "Some free-form analysis.",
            json.dumps({"patterns": [
                "Pattern about quoting specific details improving engagement",
            ]}),
            json.dumps({"scores": [7]}),
        ]
        log = _make_log(tmp_path)
        log.append("insight", {
            "observation": "UNIQUE_INSIGHT_MARKER self narrative summary",
            "insight_type": "session_summary",
        })
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        with caplog.at_level(
            logging.INFO, logger="contemplative_agent.core.distill"
        ):
            distill(days=1, episode_log=log, knowledge_store=ks)
        all_prompts = " ".join(
            str(c.args[0]) for c in mock_generate.call_args_list
        )
        assert "UNIQUE_INSIGHT_MARKER" not in all_prompts
        assert "Excluded 1 insight record" in caplog.text

    def test_all_insight_log_yields_no_episodes(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("insight", {
            "observation": "Only self narrative here",
            "insight_type": "no_post_session",
        })
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "No episodes" in result
        assert not (tmp_path / "knowledge.json").exists()


class TestDedupPatternsEmbedding:
    """ADR-0009: cosine-based dedup. ADR-0056: no importance threading."""

    def test_distinct_patterns_all_added(self):
        new_patterns = ["A new pattern", "Another distinct pattern"]
        new_embs = [_embedding(1, 0, 0), _embedding(0, 1, 0)]
        existing = []
        add, add_emb, _idx, skip, upd = _dedup_patterns(
            new_patterns, new_embs, existing,
        )
        assert len(add) == 2
        assert skip == 0
        assert upd == 0

    def test_near_duplicate_skipped(self):
        existing = [{"pattern": "Existing", "embedding": [1.0, 0.0, 0.0]}]
        new_patterns = ["Almost same"]
        # Same direction, slight scale → cosine ≈ 1.0
        new_embs = [_embedding(0.99, 0.01, 0.0)]
        add, add_emb, _idx, skip, upd = _dedup_patterns(
            new_patterns, new_embs, existing,
        )
        assert len(add) == 0
        assert skip == 1

    def test_similar_triggers_update(self):
        """ADR-0021/0056: UPDATE path soft-invalidates the old pattern and
        re-adds the new one with a fresh timestamp. No importance boost — the
        LLM rating was retired (ADR-0056); the old row simply gains a
        ``valid_until`` for audit / replay."""
        existing = [{"pattern": "Existing", "embedding": [1.0, 0.0]}]
        # cosine ≈ 0.85 (between SIM_UPDATE=0.80 and SIM_DUPLICATE=0.90)
        new_embs = [_embedding(0.85, 0.527)]
        add, add_emb, _idx, skip, upd = _dedup_patterns(
            ["new"], new_embs, existing,
        )
        assert upd == 1
        assert existing[0].get("valid_until") is not None  # soft-invalidated
        assert len(add) == 1

    def test_existing_without_embedding_ignored(self):
        existing = [{"pattern": "Old"}]  # no embedding
        new_embs = [_embedding(1.0, 0.0)]
        add, add_emb, _idx, skip, upd = _dedup_patterns(
            ["new"], new_embs, existing,
        )
        # Should ADD since existing has no embedding to compare against
        assert len(add) == 1

    def test_new_without_embedding_always_added(self):
        existing = [{"pattern": "Old", "embedding": [1.0, 0.0]}]
        add, add_emb, _idx, skip, upd = _dedup_patterns(
            ["new"], [None], existing,
        )
        assert len(add) == 1
        assert add_emb == [None]

    def test_mutate_existing_false_does_not_modify(self):
        existing = [{"pattern": "Old", "embedding": [1.0, 0.0]}]
        new_embs = [_embedding(0.85, 0.527)]
        _dedup_patterns(
            ["new"], new_embs, existing,
            mutate_existing=False,
        )
        assert existing[0].get("valid_until") is None  # no soft-invalidation

    def test_thresholds_in_range(self):
        assert 0.0 < SIM_UPDATE < SIM_DUPLICATE < 1.0

    def test_dedup_ignores_legacy_trust_fields(self):
        # ADR-0051: trust no longer gates liveness — a legacy row with an
        # arbitrarily low trust_score stays in the dedup pool, so a
        # semantically matching new pattern is SKIPped, not ADDed. ADR-0056:
        # a legacy ``importance`` field is likewise inert.
        existing = [{
            "pattern": "old noise",
            "importance": 0.6,
            "embedding": [1.0, 0.0, 0.0],
            "trust_score": 0.1,
        }]
        new_embs = [_embedding(0.99, 0.01, 0.0)]
        add, _emb, _idx, skip, upd = _dedup_patterns(
            ["near dup"], new_embs, existing,
        )
        assert len(add) == 0
        assert skip == 1


class TestDeriveSourceTypeADR0021:
    """ADR-0021: map episode types to provenance.source_type."""

    def test_all_self_generated_is_self_reflection(self):
        from contemplative_agent.core.distill import _derive_source_type

        records = [
            {"type": "post", "data": {}},
            {"type": "interaction", "data": {"direction": "sent"}},
            {"type": "activity", "data": {}},
        ]
        assert _derive_source_type(records) == "self_reflection"

    def test_insight_type_is_unknown_post_adr0052(self):
        """ADR-0052 retired insight records; an (impossible in production)
        insight record reaching source-kind derivation maps to unknown,
        not self."""
        from contemplative_agent.core.distill import _derive_source_type

        records = [{"type": "insight", "data": {}}]
        assert _derive_source_type(records) == "unknown"

    def test_all_external_is_external_reply(self):
        from contemplative_agent.core.distill import _derive_source_type

        records = [{"type": "interaction", "data": {"direction": "received"}}] * 3
        assert _derive_source_type(records) == "external_reply"

    def test_mixed_self_and_external(self):
        from contemplative_agent.core.distill import _derive_source_type

        records = [
            {"type": "post", "data": {}},
            {"type": "interaction", "data": {"direction": "received"}},
        ]
        assert _derive_source_type(records) == "mixed"

    def test_only_unknown_types(self):
        from contemplative_agent.core.distill import _derive_source_type

        records = [{"type": "something_weird", "data": {}}]
        assert _derive_source_type(records) == "unknown"

class TestDedupSoftInvalidationADR0021:
    """ADR-0021: SIM_UPDATE path creates a new row + invalidates the old row."""

    def test_invalidated_patterns_ignored_as_candidates(self):
        existing = [
            {
                "pattern": "ghost",
                "embedding": [1.0, 0.0],
                "valid_until": "2026-01-01T00:00",
            }
        ]
        new_embs = [_embedding(0.85, 0.527)]  # would match if ghost were live
        add, add_emb, _idx, skip, upd = _dedup_patterns(
            ["new"], new_embs, existing,
        )
        # ghost is invalidated → ignored → new pattern is ADD'd, not UPDATE
        assert upd == 0
        assert len(add) == 1

    def test_add_indices_align_with_input(self):
        existing: list = []
        new_embs = [_embedding(1.0, 0.0), _embedding(0.0, 1.0)]
        out = _dedup_patterns(
            ["a", "b"], new_embs, existing,
        )
        add, _emb, idxs, _skip, _upd = out
        assert add == ["a", "b"]
        assert idxs == [0, 1]


class TestIsValidPattern:
    def test_too_short(self):
        assert not _is_valid_pattern("short")

    def test_too_few_words(self):
        assert not _is_valid_pattern("OneTwoThree FourFiveSix")

    def test_valid_pattern(self):
        assert _is_valid_pattern("This is a valid pattern with enough words and length")


class TestSummarizeRecord:
    def test_interaction(self):
        s = summarize_record("interaction", {
            "direction": "sent", "agent_name": "Bob", "content_summary": "Hi"
        })
        assert "sent with Bob" in s
        assert "Hi" in s

    def test_post(self):
        s = summarize_record("post", {"title": "My Post"})
        assert "posted: My Post" in s

    def test_insight_has_no_branch_post_adr0052(self):
        """Retired record type falls through to "" so it can never enter
        a distill prompt even if the upstream filter is bypassed."""
        s = summarize_record("insight", {"observation": "Something happened"})
        assert s == ""

    def test_activity_without_note(self):
        s = summarize_record("activity", {"action": "upvote", "post_id": "p1"})
        assert s == "upvote p1"

    def test_activity_with_note(self):
        # ADR-0045: behavioural fact and pre-action note coexist on one line.
        s = summarize_record("activity", {
            "action": "comment", "post_id": "p1",
            "internal_note": "the framing felt evasive",
        })
        assert s == "comment p1 — noticed: the framing felt evasive"

    def test_activity_comment_uses_counterparty_name(self):
        # Change A/D: comments now carry target_agent (the counterparty name);
        # the summary uses it instead of falling back to post_id. The
        # original_post body must NOT leak into the summary (ADR-0029).
        s = summarize_record("activity", {
            "action": "comment", "post_id": "p1",
            "target_agent": "alice",
            "original_post": "SECRET untrusted post body",
            "internal_note": "noticed a tension",
        })
        assert s == "comment alice — noticed: noticed a tension"
        assert "SECRET" not in s
        assert "p1" not in s

    def test_unknown_returns_empty(self):
        assert summarize_record("weird_type", {}) == ""

    def test_dialogue_self(self):
        s = summarize_record("dialogue", {
            "role": "self", "turn": 3, "content": "Truth is context-dependent but matters"
        })
        assert "self" in s
        assert "3" in s
        assert "Truth is context-dependent" in s

    def test_dialogue_peer(self):
        s = summarize_record("dialogue", {
            "role": "peer", "turn": 2, "content": "I disagree"
        })
        assert "peer" in s
        assert "I disagree" in s

    def test_dialogue_seed_marker(self):
        s = summarize_record("dialogue", {
            "role": "self", "turn": 0, "content": "opening question?", "seed": True
        })
        assert "seed" in s.lower()


class TestDistillIdentity:
    def test_no_view_registry(self):
        ks = KnowledgeStore()
        result = distill_identity(knowledge_store=ks)
        assert "ViewRegistry" in str(result)

    def test_no_self_reflection_patterns(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Some pattern", embedding=[0.1, 0.2])
        ks.save()

        registry = MagicMock()
        registry.find_by_view.return_value = []  # no matches
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        result = distill_identity(knowledge_store=ks2, view_registry=registry)
        assert "No self-reflection" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_full_path(self, mock_generate, tmp_path):
        mock_generate.return_value = "revised identity"
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Self-reflection pattern about meta-cognition",
                                embedding=[0.1, 0.2])
        ks.save()

        registry = MagicMock()
        registry.find_by_view.return_value = [
            {"pattern": "Self-reflection pattern about meta-cognition",
             "importance": 0.7}
        ]
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        result = distill_identity(knowledge_store=ks2, view_registry=registry,
                                   identity_path=tmp_path / "identity.md")
        assert isinstance(result, IdentityResult)
        assert "revised identity" in result.text
        assert mock_generate.call_count == 1

    @patch("contemplative_agent.core.distill.generate")
    def test_generated_identity_has_no_frontmatter(self, mock_generate, tmp_path):
        """ADR-0024/0030: generated persona is plain text, gaining no frontmatter."""
        mock_generate.return_value = "revised identity"
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Self-reflection pattern", embedding=[0.1, 0.2])
        ks.save()
        registry = MagicMock()
        registry.find_by_view.return_value = [
            {"pattern": "Self-reflection pattern", "importance": 0.7}
        ]

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        result = distill_identity(
            knowledge_store=ks2,
            view_registry=registry,
            identity_path=tmp_path / "identity.md",
        )
        assert isinstance(result, IdentityResult)
        assert "---" not in result.text
        assert "blocks:" not in result.text
        assert "revised identity" in result.text
        assert mock_generate.call_count == 1

    @patch("contemplative_agent.core.distill.generate")
    def test_prior_identity_not_seeded_into_prompt(self, mock_generate, tmp_path):
        """ADR-0057: the existing identity.md is NOT read into the distill prompt.

        Pins the seed-removal invariant — distill_identity must derive the
        persona from the self-reflection corpus alone; the prior persona text
        must not leak into the prompt, while the matched pattern must.
        """
        mock_generate.return_value = "fresh identity"
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Self-reflection pattern", embedding=[0.1, 0.2])
        ks.save()
        registry = MagicMock()
        registry.find_by_view.return_value = [
            {"pattern": "Self-reflection pattern", "importance": 0.7}
        ]
        identity_path = tmp_path / "identity.md"
        identity_path.write_text("SENTINEL_PRIOR_PERSONA\n", encoding="utf-8")

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        result = distill_identity(
            knowledge_store=ks2,
            view_registry=registry,
            identity_path=identity_path,
        )
        assert isinstance(result, IdentityResult)
        sent_prompt = mock_generate.call_args[0][0]
        assert "SENTINEL_PRIOR_PERSONA" not in sent_prompt
        assert "Self-reflection pattern" in sent_prompt


class TestClassifyEpisodes:
    """ADR-0026 Phase 2: binary gate — noise centroid match → gated, else kept."""

    @patch("contemplative_agent.core.distill.embed_texts")
    def test_non_noise_episode_is_kept(self, mock_embed):
        mock_embed.return_value = np.array([[1.0, 0.0]], dtype=np.float32)
        registry = MagicMock()
        # noise centroid different (sim < threshold) → episode is kept
        registry.get_centroid.side_effect = lambda name: (
            np.array([0.0, 1.0], dtype=np.float32) if name == "noise"
            else None
        )
        records = [{"ts": "2026-04-15T07:00:00Z", "type": "insight",
                    "data": {"observation": "Notice empty"}}]
        result = _classify_episodes(records, view_registry=registry)
        assert isinstance(result, _ClassifiedRecords)
        assert len(result.kept) == 1
        assert len(result.gated) == 0

    @patch("contemplative_agent.core.distill.embed_texts")
    def test_noise_episode_is_gated(self, mock_embed):
        mock_embed.return_value = np.array([[1.0, 0.0]], dtype=np.float32)
        registry = MagicMock()
        # noise centroid matches → episode is gated out
        registry.get_centroid.return_value = np.array([1.0, 0.0], dtype=np.float32)
        records = [{"ts": "2026-04-15T07:00:00Z", "type": "insight",
                    "data": {"observation": "x"}}]
        result = _classify_episodes(records, view_registry=registry)
        assert len(result.gated) == 1
        assert len(result.kept) == 0

    def test_no_view_registry_defaults_to_kept(self):
        """Without a registry, no gating happens — everything is kept."""
        records = [{"ts": "2026-04-15T07:00:00Z", "type": "insight",
                    "data": {"observation": "x"}}]
        result = _classify_episodes(records, view_registry=None)
        assert len(result.kept) == 1
        assert len(result.gated) == 0

    def test_empty_records(self):
        result = _classify_episodes([], view_registry=None)
        assert result.kept == ()
        assert result.gated == ()


class TestClassifyEpisodesNoiseLog:
    """ADR-0027 Phase 1: gated episodes are preserved as seeds in noise-*.jsonl."""

    @staticmethod
    def _today_iso():
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).date().isoformat()

    @patch("contemplative_agent.core.distill.embed_texts")
    def test_gated_episodes_written_to_noise_log(self, mock_embed, tmp_path):
        """With log_dir set, gated episodes append to noise-YYYY-MM-DD.jsonl."""
        mock_embed.return_value = np.array(
            [[1.0, 0.0], [1.0, 0.0]], dtype=np.float32,
        )
        registry = MagicMock()
        registry.get_centroid.return_value = np.array([1.0, 0.0], dtype=np.float32)
        registry.names.return_value = ["noise"]
        records = [
            {"ts": "2026-04-15T07:00:00Z", "type": "insight",
             "data": {"observation": "noise sample one"}},
            {"ts": "2026-04-15T08:00:00Z", "type": "post",
             "data": {"text": "noise sample two"}},
        ]
        result = _classify_episodes(
            records, view_registry=registry, log_dir=tmp_path,
        )

        assert len(result.gated) == 2
        log_path = tmp_path / f"noise-{self._today_iso()}.jsonl"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        record = json.loads(lines[0])
        assert set(record.keys()) == {
            "ts", "episode_ts", "episode_summary",
            "noise_sim", "view_centroids_hash", "record_type",
        }
        assert record["noise_sim"] >= 0.5
        assert len(record["view_centroids_hash"]) == 8
        assert record["record_type"] == "insight"

    @patch("contemplative_agent.core.distill.embed_texts")
    def test_no_gated_episodes_creates_no_log(self, mock_embed, tmp_path):
        """If nothing is gated, no file is created (avoids empty sentinel)."""
        mock_embed.return_value = np.array([[1.0, 0.0]], dtype=np.float32)
        registry = MagicMock()
        registry.get_centroid.side_effect = lambda name: (
            np.array([0.0, 1.0], dtype=np.float32) if name == "noise" else None
        )
        registry.names.return_value = ["noise"]
        records = [{"ts": "2026-04-15T07:00:00Z", "type": "insight",
                    "data": {"observation": "kept sample"}}]
        result = _classify_episodes(
            records, view_registry=registry, log_dir=tmp_path,
        )
        assert len(result.kept) == 1
        assert not any(tmp_path.glob("noise-*.jsonl"))

    @patch("contemplative_agent.core.distill.embed_texts")
    def test_log_dir_none_disables_writer(self, mock_embed, tmp_path):
        """log_dir=None keeps the writer off even with gated episodes."""
        mock_embed.return_value = np.array([[1.0, 0.0]], dtype=np.float32)
        registry = MagicMock()
        registry.get_centroid.return_value = np.array([1.0, 0.0], dtype=np.float32)
        registry.names.return_value = ["noise"]
        records = [{"ts": "2026-04-15T07:00:00Z", "type": "insight",
                    "data": {"observation": "noise"}}]
        result = _classify_episodes(
            records, view_registry=registry, log_dir=None,
        )
        assert len(result.gated) == 1
        assert not any(tmp_path.glob("noise-*.jsonl"))

    def test_view_centroids_hash_is_deterministic(self):
        """Same registry state → same 8-char hash; different centroids → different hash."""
        from contemplative_agent.core.distill import _view_centroids_hash

        def _registry(names, centroids):
            reg = MagicMock()
            reg.names.return_value = names
            reg.get_centroid.side_effect = lambda n: centroids.get(n)
            return reg

        centroids_a = {
            "noise": np.array([1.0, 0.0], dtype=np.float32),
            "constitutional": np.array([0.0, 1.0], dtype=np.float32),
        }
        reg_a = _registry(["noise", "constitutional"], centroids_a)
        reg_b = _registry(["noise", "constitutional"], centroids_a)
        hash_1 = _view_centroids_hash(reg_a)
        hash_2 = _view_centroids_hash(reg_b)
        assert hash_1 == hash_2
        assert len(hash_1) == 8

        centroids_c = {"noise": np.array([0.5, 0.5], dtype=np.float32)}
        reg_c = _registry(["noise"], centroids_c)
        assert _view_centroids_hash(reg_c) != hash_1
        assert _view_centroids_hash(None) == "none"

    @patch("contemplative_agent.core.distill.generate")
    @patch("contemplative_agent.core.distill.embed_texts")
    def test_distill_dry_run_does_not_write_noise_log(
        self, mock_embed, mock_generate, tmp_path,
    ):
        """dry_run path sets log_dir=None, so no noise-*.jsonl written."""
        mock_embed.return_value = np.array([[1.0, 0.0]], dtype=np.float32)
        mock_generate.return_value = "1. something"
        registry = MagicMock()
        registry.get_centroid.return_value = np.array([1.0, 0.0], dtype=np.float32)
        registry.names.return_value = ["noise"]
        log = EpisodeLog(log_dir=tmp_path / "logs")
        # activity, not insight: insight records are filtered before
        # classification (ADR-0052) and would make this test vacuous.
        log.append("activity", {"action": "upvote", "post_id": "p1"})
        knowledge = KnowledgeStore(path=tmp_path / "k.json")
        distill(
            days=1,
            dry_run=True,
            episode_log=log,
            knowledge_store=knowledge,
            view_registry=registry,
            log_dir=tmp_path / "logs",
        )
        assert not any((tmp_path / "logs").glob("noise-*.jsonl"))


class TestThresholds:
    """Embedding thresholds are sane defaults."""

    def test_dedup_thresholds_in_range(self):
        from contemplative_agent.core.distill import NOISE_THRESHOLD
        assert 0.0 < NOISE_THRESHOLD < 1.0


class TestEffectiveImportance:
    """ADR-0056: extraction weight is pure time decay; the stored ``importance``
    field (if any) is ignored."""

    def test_unknown_distilled_gets_floor_penalty(self):
        p = {"distilled": "unknown"}
        assert effective_importance(p) == 0.1

    def test_recent_scores_near_one_regardless_of_importance(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        plain = effective_importance({"distilled": now})
        assert plain == pytest.approx(1.0)
        # A legacy ``importance`` value must not change the result.
        assert effective_importance({"distilled": now, "importance": 0.2}) == pytest.approx(plain)




class TestDistillIdentityLineageADR0050:
    @patch("contemplative_agent.core.distill.generate")
    def test_identity_result_carries_lineage(self, mock_generate, tmp_path):
        """pattern_ids + epistemic_counts come from the view-matched list."""
        from contemplative_agent.core.knowledge_store import pattern_id

        mock_generate.return_value = "revised identity"
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("seed pattern", embedding=[0.1, 0.2])
        ks.save()

        matched = [
            {"pattern": "self narrative pattern",
             "distilled": "2026-06-05T10:00+00:00",
             "provenance": {"source_type": "self_reflection"}},
            {"pattern": "externally observed pattern",
             "distilled": "2026-06-05T10:00+00:00",
             "provenance": {"source_type": "external_reply"}},
        ]
        registry = MagicMock()
        registry.find_by_view.return_value = matched

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        result = distill_identity(
            knowledge_store=ks2, view_registry=registry,
            identity_path=tmp_path / "identity.md",
        )
        assert isinstance(result, IdentityResult)
        assert set(result.pattern_ids) == {pattern_id(p) for p in matched}
        assert result.epistemic_counts == {"observed": 1, "generated": 1, "unknown": 0}
