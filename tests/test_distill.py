"""Tests for sleep-time memory distillation."""

from unittest.mock import patch

from contemplative_moltbook.distill import distill, _summarize_record
from contemplative_moltbook.memory import EpisodeLog, KnowledgeStore


class TestDistill:
    @patch("contemplative_moltbook.distill.generate")
    def test_basic_distillation(self, mock_generate, tmp_path):
        mock_generate.return_value = "- Pattern one\n- Pattern two"

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {
            "direction": "sent", "agent_name": "Alice",
            "content_summary": "Hello", "agent_id": "a1",
        })
        log.append("activity", {"action": "comment", "post_id": "p1"})

        ks = KnowledgeStore(path=tmp_path / "knowledge.md")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "Pattern one" in result
        assert "Pattern two" in result

        # Patterns should be saved to knowledge store
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks2.load()
        assert "Pattern one" in ks2.get_insights(limit=10) or \
            any("Pattern" in p for p in ks2._learned_patterns)

    @patch("contemplative_moltbook.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.return_value = "- Dry pattern"

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Bob",
                                    "content_summary": "Hi", "agent_id": "a1"})

        ks = KnowledgeStore(path=tmp_path / "knowledge.md")

        result = distill(days=1, dry_run=True, episode_log=log, knowledge_store=ks)
        assert "Dry pattern" in result

        # Knowledge file should NOT exist
        assert not (tmp_path / "knowledge.md").exists()

    def test_empty_episodes(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "No episodes" in result

    @patch("contemplative_moltbook.distill.generate", return_value=None)
    def test_llm_failure(self, mock_generate, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "failed" in result.lower()


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
