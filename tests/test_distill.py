"""Tests for sleep-time memory distillation."""

from unittest.mock import patch

from contemplative_agent.core.distill import (
    _summarize_record,
    distill,
    distill_identity,
)
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore


class TestDistill:
    @patch("contemplative_agent.core.distill.generate")
    def test_basic_distillation(self, mock_generate, tmp_path):
        mock_generate.return_value = "- Pattern one\n- Pattern two"

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
        assert "Pattern one" in ks2.get_learned_patterns()
        assert "Pattern two" in ks2.get_learned_patterns()

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.return_value = "- Dry pattern"

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

        mock_generate.return_value = "- New pattern from today"

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
        assert "New pattern from today" in patterns

    @patch("contemplative_agent.core.distill.generate")
    def test_no_bullet_points_no_save(self, mock_generate, tmp_path):
        """LLM response without bullet points should not save anything."""
        mock_generate.return_value = "No clear patterns found in this session."

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")

        distill(days=1, episode_log=log, knowledge_store=ks)
        assert not (tmp_path / "knowledge.json").exists()


    @patch("contemplative_agent.core.distill.generate")
    def test_log_files_override_days(self, mock_generate, tmp_path):
        """--file option reads from explicit files, ignoring days."""
        mock_generate.return_value = "- Pattern from explicit file"

        # Write a JSONL file manually
        log_file = tmp_path / "custom.jsonl"
        import json
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
        assert "Pattern from explicit file" in ks2.get_learned_patterns()


class TestSummarizeRecord:
    def test_interaction(self):
        result = _summarize_record("interaction", {
            "direction": "sent", "agent_name": "Alice",
            "content_summary": "Hello there",
        })
        assert "sent" in result
        assert "Alice" in result

    def test_post(self):
        result = _summarize_record("post", {"title": "My Post"})
        assert "My Post" in result

    def test_insight(self):
        result = _summarize_record("insight", {"observation": "Good session"})
        assert "Good session" in result

    def test_activity(self):
        result = _summarize_record("activity", {
            "action": "follow", "target_agent": "Bob",
        })
        assert "follow" in result
        assert "Bob" in result

    def test_unknown_type(self):
        assert _summarize_record("unknown", {}) == ""


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
