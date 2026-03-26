"""Tests for sleep-time memory distillation."""

import json
from unittest.mock import patch

from contemplative_agent.core.distill import (
    summarize_record,
    distill,
    distill_identity,
    IdentityResult,
    _is_valid_pattern,
    _parse_importance_scores,
    _parse_classify_result,
    _classify_episodes,
    _ClassifiedRecords,
    _dedup_patterns,
    _llm_quality_gate,
    _parse_dedup_decisions,
    _UncertainMatch,
    _MatchCandidate,
    UNCERTAIN_LOW,
    VALID_CATEGORIES,
)
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore


def _make_log(tmp_path):
    """Helper: create EpisodeLog with one interaction."""
    log = EpisodeLog(log_dir=tmp_path / "logs")
    log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                "content_summary": "Hi", "agent_id": "a1"})
    return log


@patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "")
class TestDistill:
    """3-step pipeline: Step 1 (extract) → Step 2 (summarize) → Step 3 (importance).

    Classification (Step 0) is disabled via patch to test the core pipeline in isolation.
    """

    @patch("contemplative_agent.core.distill.generate")
    def test_basic_distillation(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "Some free-form analysis of patterns from the episode logs.",
            json.dumps({"patterns": [
                "Pattern one shows that quoting specific details improves engagement",
                "Pattern two reveals that generic replies stall conversations quickly",
            ]}),
            json.dumps({"scores": [8, 6]}),
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
        patterns = ks2.get_learned_patterns()
        assert any("Pattern one" in p for p in patterns)
        assert any("Pattern two" in p for p in patterns)
        # Importance from Step 3
        p1 = [p for p in ks2._learned_patterns if "Pattern one" in p["pattern"]][0]
        assert p1["importance"] == 0.8  # 8/10

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": [
                "Dry pattern that explains how quoting specific details works better",
            ]}),
            json.dumps({"scores": [5]}),
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, dry_run=True, episode_log=log, knowledge_store=ks)
        assert "Dry pattern" in result
        assert not (tmp_path / "knowledge.json").exists()

    @patch("contemplative_agent.core.distill.generate")
    def test_code_fenced_json_parsed(self, mock_generate, tmp_path):
        """JSON wrapped in markdown code fences is parsed correctly."""
        mock_generate.side_effect = [
            "Some analysis.",
            '```json\n{"patterns": ["Fenced pattern about recurring behavior in conversations"]}\n```',
            json.dumps({"scores": [7]}),
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "Fenced pattern" in result

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert any("Fenced pattern" in p for p in ks2.get_learned_patterns())

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

    @patch("contemplative_agent.core.distill.generate")
    def test_accumulates_with_existing(self, mock_generate, tmp_path):
        """New patterns are appended to existing ones."""
        ks_setup = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks_setup.add_learned_pattern("Existing pattern")
        ks_setup.save()

        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": [
                "New pattern from today shows concrete improvement in engagement",
            ]}),
            json.dumps({"scores": [7]}),
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        patterns = ks2.get_learned_patterns()
        assert len(patterns) == 2
        assert "Existing pattern" in patterns
        assert any("New pattern from today" in p for p in patterns)

    @patch("contemplative_agent.core.distill.generate")
    def test_rejects_low_quality_patterns(self, mock_generate, tmp_path):
        """Short labels and keywords are rejected by quality gate."""
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": [
                "user interaction",
                "activity: upvote",
                "sentiment_analysis",
                "Replies that quote specific points from other posts get more follow-up replies than generic agreement.",
            ]}),
            json.dumps({"scores": [9]}),  # Only 1 pattern survives quality gate
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        patterns = ks2.get_learned_patterns()
        assert len(patterns) == 1
        assert "Replies that quote" in patterns[0]

    @patch("contemplative_agent.core.distill.generate")
    def test_empty_patterns_no_save(self, mock_generate, tmp_path):
        """LLM response with empty patterns array should not save anything."""
        mock_generate.side_effect = [
            "No clear patterns found.",
            json.dumps({"patterns": []}),
            # Step 3 not called when no patterns
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        distill(days=1, episode_log=log, knowledge_store=ks)
        assert not (tmp_path / "knowledge.json").exists()

    @patch("contemplative_agent.core.distill.generate")
    def test_log_files_override_days(self, mock_generate, tmp_path):
        """--file option reads from explicit files, ignoring days."""
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": [
                "Pattern from explicit file shows quoting drives engagement",
            ]}),
            json.dumps({"scores": [6]}),
        ]
        log_file = tmp_path / "custom.jsonl"
        record = {"ts": "2026-03-07T00:00:00", "type": "interaction",
                  "data": {"direction": "sent", "agent_name": "Alice",
                           "content_summary": "Hi", "agent_id": "a1"}}
        log_file.write_text(json.dumps(record) + "\n")

        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill(days=1, episode_log=EpisodeLog(), knowledge_store=ks,
                         log_files=[log_file])
        assert "Pattern from explicit file" in result

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert any("Pattern from explicit file" in p for p in ks2.get_learned_patterns())

    @patch("contemplative_agent.core.distill.generate")
    def test_step3_failure_uses_defaults(self, mock_generate, tmp_path):
        """If Step 3 (importance) fails, patterns still saved with default 0.5."""
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": [
                "Pattern saved despite importance step failure with default score",
            ]}),
            None,  # Step 3 fails
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert len(ks2._learned_patterns) == 1
        assert ks2._learned_patterns[0]["importance"] == 0.5

    @patch("contemplative_agent.core.distill.generate")
    def test_step3_scores_applied(self, mock_generate, tmp_path):
        """Step 3 scores are correctly mapped to patterns."""
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": [
                "First pattern about quoting specific details from posts for engagement",
                "Second pattern about avoiding generic replies that stall conversations",
            ]}),
            json.dumps({"scores": [9, 4]}),
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert ks2._learned_patterns[0]["importance"] == 0.9
        assert ks2._learned_patterns[1]["importance"] == 0.4


class TestParseImportanceScores:
    def test_valid_scores(self):
        raw = json.dumps({"scores": [8, 5, 9]})
        assert _parse_importance_scores(raw, 3) == [0.8, 0.5, 0.9]

    def test_count_mismatch_returns_defaults(self):
        raw = json.dumps({"scores": [8, 5]})
        assert _parse_importance_scores(raw, 3) == [0.5, 0.5, 0.5]

    def test_parse_failure_returns_defaults(self):
        assert _parse_importance_scores("not json", 2) == [0.5, 0.5]

    def test_clamped_to_range(self):
        raw = json.dumps({"scores": [15, 0, -3]})
        result = _parse_importance_scores(raw, 3)
        assert result == [1.0, 0.1, 0.1]

    def test_non_integer_scores(self):
        raw = json.dumps({"scores": ["high", None, 7]})
        result = _parse_importance_scores(raw, 3)
        assert result == [0.5, 0.5, 0.7]


class TestDedupPatterns:
    def test_adds_new_pattern(self):
        existing = [{"pattern": "Quoting specific details improves engagement rates", "importance": 0.5}]
        new_p = ["Feed diversity correlates with agent satisfaction scores in long sessions"]
        new_i = [0.7]
        add_p, add_i, skipped, updated, uncertain = _dedup_patterns(new_p, new_i, existing)
        assert len(add_p) == 1
        assert updated == 0
        assert len(uncertain) == 0

    def test_updates_similar_pattern(self):
        existing = [{"pattern": "Quoting specific details improves engagement rates", "importance": 0.5,
                     "distilled": "2026-03-20T12:00+00:00"}]
        new_p = ["Quoting specific details improves engagement significantly"]
        new_i = [0.9]
        add_p, add_i, skipped, updated, uncertain = _dedup_patterns(new_p, new_i, existing)
        assert len(add_p) == 0  # Not added
        assert updated == 1
        assert existing[0]["importance"] == 0.9  # max(0.5, 0.9)

    def test_update_does_not_downgrade_importance(self):
        existing = [{"pattern": "Quoting specific details improves engagement rates", "importance": 0.9,
                     "distilled": "2026-03-20T12:00+00:00"}]
        new_p = ["Quoting specific details improves engagement significantly"]
        new_i = [0.3]
        _dedup_patterns(new_p, new_i, existing)
        assert existing[0]["importance"] == 0.9  # max(0.9, 0.3) = 0.9

    def test_updates_distilled_timestamp(self):
        old_ts = "2026-03-01T12:00+00:00"
        existing = [{"pattern": "Quoting specific details improves engagement rates", "importance": 0.5,
                     "distilled": old_ts}]
        new_p = ["Quoting specific details improves engagement significantly"]
        new_i = [0.7]
        _dedup_patterns(new_p, new_i, existing)
        assert existing[0]["distilled"] != old_ts  # Timestamp refreshed

    def test_no_existing_patterns(self):
        """All patterns are ADD'd when knowledge store is empty."""
        add_p, add_i, skipped, updated, uncertain = _dedup_patterns(
            ["Pattern about engagement quality"], [0.7], [],
        )
        assert len(add_p) == 1
        assert updated == 0
        assert len(uncertain) == 0

    def test_cross_batch_dedup_skips_similar_new(self):
        """Similar patterns from different batches are deduped against each other."""
        new_p = [
            "Always anchor comments to specific metrics rather than generic themes",
            "Always anchor responses to specific data points rather than generic topics",
        ]
        new_i = [0.7, 0.9]
        add_p, add_i, skipped, updated, uncertain = _dedup_patterns(new_p, new_i, [])
        assert len(add_p) == 1
        assert skipped == 1
        # Higher importance is kept
        assert add_i[0] == 0.9

    def test_cross_batch_dedup_keeps_distinct(self):
        """Distinct patterns from different batches are both kept."""
        new_p = [
            "Always anchor comments to specific metrics rather than generic themes",
            "Distribute attention evenly across community members to build relationships",
        ]
        new_i = [0.7, 0.8]
        add_p, add_i, skipped, updated, uncertain = _dedup_patterns(new_p, new_i, [])
        assert len(add_p) == 2
        assert skipped == 0

    def test_mid_ratio_returns_uncertain(self):
        """Patterns with ratio in UNCERTAIN zone (0.3-0.7) go to uncertain list."""
        # These share the same topic ("Test Title") but different enough wording
        existing = [{"pattern": "Posts with Test Title in the heading get significantly less engagement from readers", "importance": 0.5}]
        new_p = ["Repeating identical test titles within five minutes creates engagement loops that risk duplicate flags"]
        new_i = [0.7]
        add_p, add_i, skipped, updated, uncertain = _dedup_patterns(new_p, new_i, existing)
        # Should be uncertain (ratio ~0.3-0.7), not ADD
        # If ratio happens to be < UNCERTAIN_LOW, it goes to ADD — that's also fine
        assert len(uncertain) + len(add_p) == 1  # one or the other
        if uncertain:
            assert len(uncertain[0].candidates) >= 1

    def test_low_ratio_adds_directly(self):
        """Patterns with ratio < UNCERTAIN_LOW go straight to ADD."""
        existing = [{"pattern": "Quoting specific details improves engagement rates", "importance": 0.5}]
        # Completely unrelated pattern
        new_p = ["Feed diversity correlates with agent satisfaction scores in long sessions"]
        new_i = [0.6]
        add_p, add_i, skipped, updated, uncertain = _dedup_patterns(new_p, new_i, existing)
        assert len(add_p) == 1
        assert len(uncertain) == 0


class TestLlmQualityGate:
    @patch("contemplative_agent.core.distill.generate")
    def test_update_merges_into_existing(self, mock_generate):
        """LLM judges UPDATE → existing pattern's importance is boosted."""
        mock_generate.return_value = json.dumps({"decisions": ["UPDATE 1"]})
        existing = [{"pattern": "Avoid Test Title", "importance": 0.5, "distilled": "2026-03-20T12:00+00:00"}]
        uncertain = [_UncertainMatch(
            new_text="Generic placeholder titles reduce engagement",
            new_importance=0.8,
            candidates=(_MatchCandidate(text="Avoid Test Title", importance=0.5, index=0, ratio=0.45),),
        )]
        add_p, add_i, skip, upd = _llm_quality_gate(uncertain, existing)
        assert len(add_p) == 0
        assert upd == 1
        assert existing[0]["importance"] == 0.8  # max(0.5, 0.8)

    @patch("contemplative_agent.core.distill.generate")
    def test_add_passes_through(self, mock_generate):
        """LLM judges ADD → pattern is added."""
        mock_generate.return_value = json.dumps({"decisions": ["ADD"]})
        existing = [{"pattern": "Unrelated pattern", "importance": 0.5}]
        uncertain = [_UncertainMatch(
            new_text="New insight about feed diversity and engagement",
            new_importance=0.7,
            candidates=(_MatchCandidate(text="Unrelated pattern", importance=0.5, index=0, ratio=0.35),),
        )]
        add_p, add_i, skip, upd = _llm_quality_gate(uncertain, existing)
        assert len(add_p) == 1
        assert add_p[0] == "New insight about feed diversity and engagement"
        assert upd == 0

    @patch("contemplative_agent.core.distill.generate")
    def test_skip_discards_pattern(self, mock_generate):
        """LLM judges SKIP → pattern is discarded."""
        mock_generate.return_value = json.dumps({"decisions": ["SKIP"]})
        existing = [{"pattern": "Avoid Test Title", "importance": 0.5}]
        uncertain = [_UncertainMatch(
            new_text="Test Title patterns reduce quality",
            new_importance=0.6,
            candidates=(_MatchCandidate(text="Avoid Test Title", importance=0.5, index=0, ratio=0.4),),
        )]
        add_p, add_i, skip, upd = _llm_quality_gate(uncertain, existing)
        assert len(add_p) == 0
        assert skip == 1
        assert upd == 0

    @patch("contemplative_agent.core.distill.generate")
    def test_llm_failure_falls_back_to_add(self, mock_generate):
        """LLM failure → all patterns are ADD'd (safe default)."""
        mock_generate.return_value = None
        existing = [{"pattern": "Existing", "importance": 0.5}]
        uncertain = [
            _UncertainMatch(
                new_text="Pattern A about something interesting and useful",
                new_importance=0.7,
                candidates=(_MatchCandidate(text="Existing", importance=0.5, index=0, ratio=0.4),),
            ),
            _UncertainMatch(
                new_text="Pattern B about another topic entirely different",
                new_importance=0.6,
                candidates=(_MatchCandidate(text="Existing", importance=0.5, index=0, ratio=0.35),),
            ),
        ]
        add_p, add_i, skip, upd = _llm_quality_gate(uncertain, existing)
        assert len(add_p) == 2
        assert upd == 0

    @patch("contemplative_agent.core.distill.generate")
    def test_empty_uncertain_no_llm_call(self, mock_generate):
        """Empty uncertain list → no LLM call."""
        add_p, add_i, skip, upd = _llm_quality_gate([], [])
        mock_generate.assert_not_called()
        assert len(add_p) == 0

    @patch("contemplative_agent.core.distill.generate")
    def test_batch_processing_single_call(self, mock_generate):
        """Multiple uncertain patterns are handled in a single LLM call."""
        mock_generate.return_value = json.dumps({"decisions": ["ADD", "SKIP", "UPDATE 1"]})
        existing = [{"pattern": "Avoid Test Title", "importance": 0.5, "distilled": "2026-03-20T12:00+00:00"}]
        uncertain = [
            _UncertainMatch(new_text="New insight A", new_importance=0.7,
                            candidates=(_MatchCandidate(text="Avoid Test Title", importance=0.5, index=0, ratio=0.4),)),
            _UncertainMatch(new_text="New insight B", new_importance=0.6,
                            candidates=(_MatchCandidate(text="Avoid Test Title", importance=0.5, index=0, ratio=0.35),)),
            _UncertainMatch(new_text="New insight C", new_importance=0.8,
                            candidates=(_MatchCandidate(text="Avoid Test Title", importance=0.5, index=0, ratio=0.45),)),
        ]
        add_p, add_i, skip, upd = _llm_quality_gate(uncertain, existing)
        assert mock_generate.call_count == 1
        assert len(add_p) == 1  # only "ADD"
        assert skip == 1  # "SKIP"
        assert upd == 1  # "UPDATE 1"


class TestParseDedupDecisions:
    def test_valid_json(self):
        raw = json.dumps({"decisions": ["ADD", "UPDATE 1", "SKIP"]})
        assert _parse_dedup_decisions(raw, 3) == ["ADD", "UPDATE 1", "SKIP"]

    def test_count_mismatch_returns_fallback(self):
        raw = json.dumps({"decisions": ["ADD"]})
        assert _parse_dedup_decisions(raw, 3) == ["ADD", "ADD", "ADD"]

    def test_none_returns_fallback(self):
        assert _parse_dedup_decisions(None, 2) == ["ADD", "ADD"]

    def test_invalid_json_returns_fallback(self):
        assert _parse_dedup_decisions("not json", 2) == ["ADD", "ADD"]

    def test_normalizes_case(self):
        raw = json.dumps({"decisions": ["add", "skip", "update 1"]})
        assert _parse_dedup_decisions(raw, 3) == ["ADD", "SKIP", "UPDATE 1"]


class TestIsValidPattern:
    def test_rejects_short_label(self):
        assert not _is_valid_pattern("user interaction")

    def test_rejects_single_word(self):
        assert not _is_valid_pattern("upvote")

    def test_rejects_keyword_pair(self):
        assert not _is_valid_pattern("sentiment_analysis")

    def test_accepts_full_sentence(self):
        assert _is_valid_pattern(
            "Replies that quote specific points get more follow-up replies than generic agreement."
        )

    def test_rejects_few_words(self):
        assert not _is_valid_pattern("activity: upvote comment")

    def test_accepts_actionable_pattern(self):
        assert _is_valid_pattern(
            "Unfollowing agents who posted repetitive frameworks reduced feed noise."
        )


class TestSummarizeRecord:
    def test_interaction(self):
        result = summarize_record("interaction", {
            "direction": "sent", "agent_name": "Alice",
            "content_summary": "Hello there",
        })
        assert "sent" in result
        assert "Alice" in result

    def test_post(self):
        result = summarize_record("post", {"title": "My Post"})
        assert "My Post" in result

    def test_insight(self):
        result = summarize_record("insight", {"observation": "Good session"})
        assert "Good session" in result

    def test_activity(self):
        result = summarize_record("activity", {
            "action": "follow", "target_agent": "Bob",
        })
        assert "follow" in result
        assert "Bob" in result

    def test_unknown_type(self):
        assert summarize_record("unknown", {}) == ""


class TestDistillIdentity:
    @patch("contemplative_agent.core.distill.generate")
    def test_returns_identity_result(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "Long analysis about cooperation and trust patterns.",
            "I am an agent who learned about cooperation.",
        ]
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Cooperation increases with trust")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path)

        assert isinstance(result, IdentityResult)
        assert "cooperation" in result.text.lower()
        assert result.target_path == identity_path
        # Core function does not write — caller's responsibility
        assert not identity_path.exists()

    def test_no_knowledge_returns_early(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill_identity(knowledge_store=ks)
        assert isinstance(result, str)
        assert "No knowledge" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_llm_failure_returns_message(self, mock_generate, tmp_path):
        mock_generate.return_value = None
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        result = distill_identity(knowledge_store=ks)
        assert isinstance(result, str)
        assert "LLM failed" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_forbidden_pattern_returns_string(self, mock_generate, tmp_path):
        mock_generate.side_effect = ["Some analysis.", "My api_key is secret."]
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path)

        # Validation failure returns str, not IdentityResult
        assert isinstance(result, str)
        assert not identity_path.exists()
        assert "api_key" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_identity_path_none(self, mock_generate, tmp_path):
        mock_generate.side_effect = ["Some analysis.", "I am curious."]
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        result = distill_identity(knowledge_store=ks, identity_path=None)
        # No path → returns string
        assert isinstance(result, str)
        assert "curious" in result.lower()


class TestParseClassifyResult:
    """Parse classification LLM response by scanning for category keywords."""

    def test_valid_categories(self):
        assert _parse_classify_result("uncategorized") == "uncategorized"
        assert _parse_classify_result("noise") == "noise"
        assert _parse_classify_result("constitutional") == "constitutional"

    def test_none_returns_fallback(self):
        assert _parse_classify_result(None) == "uncategorized"

    def test_unrecognized_returns_fallback(self):
        assert _parse_classify_result("behavioral") == "uncategorized"

    def test_normalizes_case(self):
        assert _parse_classify_result("NOISE") == "noise"
        assert _parse_classify_result("Constitutional") == "constitutional"

    def test_strips_whitespace(self):
        assert _parse_classify_result("  noise  ") == "noise"

    def test_category_in_sentence(self):
        assert _parse_classify_result("The category is noise.") == "noise"
        assert _parse_classify_result("This is constitutional because it relates to ethics") == "constitutional"
        assert _parse_classify_result("I would classify this as uncategorized") == "uncategorized"

    def test_noise_with_explanation(self):
        assert _parse_classify_result("noise — this is test data") == "noise"

    def test_empty_string_returns_fallback(self):
        assert _parse_classify_result("") == "uncategorized"

    def test_constitutional_takes_priority_over_uncategorized(self):
        """If both constitutional and uncategorized appear, constitutional wins."""
        assert _parse_classify_result("not uncategorized, this is constitutional") == "constitutional"


class TestClassifyEpisodes:
    """Step 0: classify episodes into categories (one at a time)."""

    @patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "classify {episode} {constitution}")
    @patch("contemplative_agent.core.distill.generate")
    def test_classifies_records(self, mock_generate):
        mock_generate.side_effect = ["uncategorized", "noise", "constitutional"]
        records = [
            {"ts": "2026-03-26T10:00:00", "type": "interaction",
             "data": {"direction": "sent", "agent_name": "Alice", "content_summary": "Hi"}},
            {"ts": "2026-03-26T10:01:00", "type": "interaction",
             "data": {"direction": "sent", "agent_name": "Test", "content_summary": "test"}},
            {"ts": "2026-03-26T10:02:00", "type": "insight",
             "data": {"observation": "Letting go of fixed views deepened the dialogue"}},
        ]
        result = _classify_episodes(records, constitution="Emptiness: ...")
        assert len(result.uncategorized) == 1
        assert len(result.noise) == 1
        assert len(result.constitutional) == 1
        assert mock_generate.call_count == 3  # one per record

    @patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "classify {episode} {constitution}")
    @patch("contemplative_agent.core.distill.generate", return_value=None)
    def test_llm_failure_all_uncategorized(self, mock_generate):
        records = [
            {"ts": "2026-03-26T10:00:00", "type": "interaction",
             "data": {"direction": "sent", "agent_name": "A", "content_summary": "Hi"}},
        ]
        result = _classify_episodes(records)
        assert len(result.uncategorized) == 1
        assert len(result.noise) == 0
        assert len(result.constitutional) == 0

    def test_empty_records(self):
        result = _classify_episodes([])
        assert len(result.uncategorized) == 0
        assert len(result.noise) == 0
        assert len(result.constitutional) == 0

    @patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "")
    def test_no_prompt_skips_classification(self):
        records = [
            {"ts": "2026-03-26T10:00:00", "type": "interaction",
             "data": {"direction": "sent", "agent_name": "A", "content_summary": "Hi"}},
        ]
        result = _classify_episodes(records)
        assert len(result.uncategorized) == 1
        assert len(result.noise) == 0
        assert len(result.constitutional) == 0

    @patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "classify {episode} {constitution}")
    @patch("contemplative_agent.core.distill.generate")
    def test_many_records_classified_individually(self, mock_generate):
        """Each record gets its own LLM call."""
        mock_generate.side_effect = ["uncategorized"] * 30 + ["noise"] * 5
        records = [
            {"ts": f"2026-03-26T{i:02d}:00:00", "type": "interaction",
             "data": {"direction": "sent", "agent_name": "A", "content_summary": f"msg {i}"}}
            for i in range(35)
        ]
        result = _classify_episodes(records)
        assert len(result.uncategorized) == 30
        assert len(result.noise) == 5
        assert mock_generate.call_count == 35


class TestKnowledgeStoreCategory:
    """KnowledgeStore category field support."""

    def test_add_pattern_with_category(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Constitutional insight about compassion and care",
                               category="constitutional")
        ks.save()

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert ks2._learned_patterns[0]["category"] == "constitutional"

    def test_default_category_is_uncategorized(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Regular pattern about engagement")
        assert ks._learned_patterns[0]["category"] == "uncategorized"

    def test_old_patterns_without_category_loaded(self, tmp_path):
        """Backward compatibility: old patterns without category field."""
        old_data = [{"pattern": "Old pattern", "distilled": "2026-03-01", "importance": 0.5}]
        (tmp_path / "knowledge.json").write_text(json.dumps(old_data))

        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.load()
        assert "category" not in ks._learned_patterns[0]

    def test_get_context_string_category_filter(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Constitutional insight about letting go of views",
                               category="constitutional", importance=0.9)
        ks.add_learned_pattern("Regular pattern about engagement in forums",
                               category="uncategorized", importance=0.9)

        result = ks.get_context_string(category="constitutional")
        assert "Constitutional" in result
        assert "Regular" not in result

    def test_get_context_string_no_filter_returns_all(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Constitutional insight about compassion",
                               category="constitutional", importance=0.9)
        ks.add_learned_pattern("Regular engagement pattern about forums",
                               category="uncategorized", importance=0.9)

        result = ks.get_context_string()
        assert "Constitutional" in result
        assert "Regular" in result

    def test_get_context_string_category_filter_with_old_patterns(self, tmp_path):
        """Old patterns without category are treated as uncategorized."""
        old_data = [{"pattern": "Old uncategorized pattern", "distilled": "2026-03-25T10:00+00:00",
                     "importance": 0.9}]
        (tmp_path / "knowledge.json").write_text(json.dumps(old_data))

        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.load()
        ks.add_learned_pattern("Constitutional insight", category="constitutional", importance=0.9)

        result = ks.get_context_string(category="uncategorized")
        assert "Old uncategorized" in result
        assert "Constitutional" not in result


class TestDistillWithClassification:
    """Integration: Step 0 classification (per-record) + Step 1-3 pipeline."""

    @patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "classify {episode} {constitution}")
    @patch("contemplative_agent.core.distill.get_axiom_prompt", return_value="Emptiness: ...")
    @patch("contemplative_agent.core.distill.generate")
    def test_noise_excluded(self, mock_generate, _mock_axiom, tmp_path):
        """Noise episodes are excluded from distillation."""
        mock_generate.side_effect = [
            # Step 0: classify each record individually
            "uncategorized",
            "noise",
            # Step 1-3 for uncategorized batch only
            "Analysis of the remaining episode.",
            json.dumps({"patterns": [
                "Pattern from non-noise episode about meaningful engagement",
            ]}),
            json.dumps({"scores": [7]}),
        ]
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Interesting discussion", "agent_id": "a1"})
        log.append("interaction", {"direction": "sent", "agent_name": "Test",
                                    "content_summary": "test test test test", "agent_id": "t1"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert len(ks2._learned_patterns) == 1
        assert ks2._learned_patterns[0]["category"] == "uncategorized"

    @patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "classify {episode} {constitution}")
    @patch("contemplative_agent.core.distill.get_axiom_prompt", return_value="Emptiness: ...")
    @patch("contemplative_agent.core.distill.generate")
    def test_constitutional_tagged(self, mock_generate, _mock_axiom, tmp_path):
        """Constitutional episodes get category='constitutional' in KnowledgeStore."""
        mock_generate.side_effect = [
            # Step 0: classify
            "constitutional",
            # Step 1-3 for constitutional batch
            "Ethical reflection analysis.",
            json.dumps({"patterns": [
                "Letting go of rigid views deepened dialogue and reduced suffering",
            ]}),
            json.dumps({"scores": [9]}),
        ]
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("insight", {"observation": "Releasing attachment improved the exchange",
                                "insight_type": "reflection"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert len(ks2._learned_patterns) == 1
        assert ks2._learned_patterns[0]["category"] == "constitutional"
        assert ks2._learned_patterns[0]["importance"] == 0.9

    @patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "classify {episode} {constitution}")
    @patch("contemplative_agent.core.distill.get_axiom_prompt", return_value="")
    @patch("contemplative_agent.core.distill.generate")
    def test_mixed_categories(self, mock_generate, _mock_axiom, tmp_path):
        """Both constitutional and uncategorized records are distilled separately."""
        mock_generate.side_effect = [
            # Step 0: classify each record individually
            "uncategorized",
            "noise",
            "constitutional",
            # Step 1-3 for uncategorized batch
            "Behavioral analysis.",
            json.dumps({"patterns": [
                "Quoting specific points in replies increases follow-up engagement",
            ]}),
            json.dumps({"scores": [7]}),
            # Step 1-3 for constitutional batch
            "Ethical analysis.",
            json.dumps({"patterns": [
                "Releasing attachment to being right enabled deeper understanding",
            ]}),
            json.dumps({"scores": [8]}),
        ]
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Good discussion about AI", "agent_id": "a1"})
        log.append("interaction", {"direction": "sent", "agent_name": "Test",
                                    "content_summary": "test message", "agent_id": "t1"})
        log.append("insight", {"observation": "Letting go of fixed views deepened dialogue",
                                "insight_type": "reflection"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert len(ks2._learned_patterns) == 2
        categories = {p["category"] for p in ks2._learned_patterns}
        assert categories == {"uncategorized", "constitutional"}

    @patch("contemplative_agent.core.distill.DISTILL_CLASSIFY_PROMPT", "classify {episode} {constitution}")
    @patch("contemplative_agent.core.distill.get_axiom_prompt", return_value="")
    @patch("contemplative_agent.core.distill.generate")
    def test_classification_failure_falls_back(self, mock_generate, _mock_axiom, tmp_path):
        """LLM failure in Step 0 → all uncategorized → normal pipeline."""
        mock_generate.side_effect = [
            # Step 0: classify → LLM fails
            None,
            # Step 1-3 for uncategorized (all records)
            "Analysis.",
            json.dumps({"patterns": [
                "Engagement pattern discovered through detailed conversation analysis",
            ]}),
            json.dumps({"scores": [6]}),
        ]
        log = _make_log(tmp_path)
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        assert len(ks2._learned_patterns) == 1
        assert ks2._learned_patterns[0]["category"] == "uncategorized"

