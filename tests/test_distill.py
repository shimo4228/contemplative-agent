"""Tests for sleep-time memory distillation."""

import json
from unittest.mock import patch

from contemplative_agent.core.distill import (
    summarize_record,
    distill,
    distill_identity,
    _is_valid_pattern,
    _parse_importance_scores,
    _dedup_patterns,
)
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore


def _make_log(tmp_path):
    """Helper: create EpisodeLog with one interaction."""
    log = EpisodeLog(log_dir=tmp_path / "logs")
    log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                "content_summary": "Hi", "agent_id": "a1"})
    return log


class TestDistill:
    """3-step pipeline: Step 1 (extract) → Step 2 (summarize) → Step 3 (importance)."""

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
        existing = [{"pattern": "Existing pattern about engagement", "importance": 0.5}]
        new_p = ["Completely different pattern about feed quality management"]
        new_i = [0.7]
        add_p, add_i, skipped, updated = _dedup_patterns(new_p, new_i, existing)
        assert len(add_p) == 1
        assert updated == 0

    def test_updates_similar_pattern(self):
        existing = [{"pattern": "Quoting specific details improves engagement rates", "importance": 0.5,
                     "distilled": "2026-03-20T12:00+00:00"}]
        new_p = ["Quoting specific details improves engagement significantly"]
        new_i = [0.9]
        add_p, add_i, skipped, updated = _dedup_patterns(new_p, new_i, existing)
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
        add_p, add_i, skipped, updated = _dedup_patterns(
            ["Pattern about engagement quality"], [0.7], [],
        )
        assert len(add_p) == 1
        assert updated == 0

    def test_cross_batch_dedup_skips_similar_new(self):
        """Similar patterns from different batches are deduped against each other."""
        new_p = [
            "Always anchor comments to specific metrics rather than generic themes",
            "Always anchor responses to specific data points rather than generic topics",
        ]
        new_i = [0.7, 0.9]
        add_p, add_i, skipped, updated = _dedup_patterns(new_p, new_i, [])
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
        add_p, add_i, skipped, updated = _dedup_patterns(new_p, new_i, [])
        assert len(add_p) == 2
        assert skipped == 0


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
    def test_writes_identity_file(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "Long analysis about cooperation and trust patterns.",
            "I am an agent who learned about cooperation.",
        ]
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Cooperation increases with trust")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path)

        assert identity_path.exists()
        assert "cooperation" in result.lower()

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.side_effect = ["Some analysis.", "I learned things."]
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path, dry_run=True)

        assert not identity_path.exists()
        assert "learned" in result.lower()

    def test_no_knowledge_returns_early(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        result = distill_identity(knowledge_store=ks)
        assert "No knowledge" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_llm_failure_returns_message(self, mock_generate, tmp_path):
        mock_generate.return_value = None
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        result = distill_identity(knowledge_store=ks)
        assert "LLM failed" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_forbidden_pattern_prevents_write(self, mock_generate, tmp_path):
        mock_generate.side_effect = ["Some analysis.", "My api_key is secret."]
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path)

        assert not identity_path.exists()
        assert "api_key" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_identity_path_none(self, mock_generate, tmp_path):
        mock_generate.side_effect = ["Some analysis.", "I am curious."]
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        result = distill_identity(knowledge_store=ks, identity_path=None)
        assert "curious" in result.lower()

