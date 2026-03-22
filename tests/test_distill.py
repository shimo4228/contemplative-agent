"""Tests for sleep-time memory distillation."""

import json
from unittest.mock import patch

from contemplative_agent.core.distill import (
    summarize_record,
    distill,
    distill_identity,
    _is_valid_pattern,
)
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore


class TestDistill:
    @patch("contemplative_agent.core.distill.generate")
    def test_basic_distillation(self, mock_generate, tmp_path):
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

        # Patterns should be saved to knowledge store
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks2.load()
        patterns = ks2.get_learned_patterns()
        assert any("Pattern one" in p for p in patterns)
        assert any("Pattern two" in p for p in patterns)

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": ["Dry pattern that explains how quoting specific details works better"]}),
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Bob",
                                    "content_summary": "Hi", "agent_id": "a1"})

        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, dry_run=True, episode_log=log, knowledge_store=ks)
        assert "Dry pattern" in result

        # Knowledge file should NOT exist
        assert not (tmp_path / "knowledge.json").exists()

    def test_empty_episodes(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "No episodes" in result

    @patch("contemplative_agent.core.distill.generate", return_value=None)
    def test_llm_failure(self, mock_generate, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert result == ""  # All batches failed, nothing returned
        assert not (tmp_path / "knowledge.json").exists()

    @patch("contemplative_agent.core.distill.generate")
    def test_accumulates_with_existing(self, mock_generate, tmp_path):
        """New patterns are appended to existing ones."""
        ks_setup = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks_setup.add_learned_pattern("Existing pattern")
        ks_setup.save()

        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": ["New pattern from today shows concrete improvement in engagement"]}),
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})

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
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})
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
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        distill(days=1, episode_log=log, knowledge_store=ks)
        assert not (tmp_path / "knowledge.json").exists()


    @patch("contemplative_agent.core.distill.generate")
    def test_log_files_override_days(self, mock_generate, tmp_path):
        """--file option reads from explicit files, ignoring days."""
        mock_generate.side_effect = [
            "Some analysis.",
            json.dumps({"patterns": ["Pattern from explicit file shows quoting drives engagement"]}),
        ]

        # Write a JSONL file manually
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
        mock_generate.return_value = "I am an agent who learned about cooperation."
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Cooperation increases with trust")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path)

        assert identity_path.exists()
        assert "cooperation" in result.lower()

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.return_value = "I learned things."
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
        mock_generate.return_value = "My api_key is secret."
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path)

        assert not identity_path.exists()
        assert "api_key" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_identity_path_none(self, mock_generate, tmp_path):
        mock_generate.return_value = "I am curious."
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        result = distill_identity(knowledge_store=ks, identity_path=None)
        assert "curious" in result.lower()

    @patch("contemplative_agent.core.distill.generate")
    def test_archives_identity_before_overwrite(self, mock_generate, tmp_path):
        mock_generate.return_value = "I am new."
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Pattern")
        ks.save()

        identity_path = tmp_path / "identity.md"
        identity_path.write_text("I am old.\n", encoding="utf-8")

        distill_identity(knowledge_store=ks, identity_path=identity_path)

        history_dir = tmp_path / "history" / "identity"
        assert history_dir.exists()
        archives = list(history_dir.glob("*.md"))
        assert len(archives) == 1
        assert "I am old." in archives[0].read_text(encoding="utf-8")
