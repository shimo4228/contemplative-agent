"""Tests for sleep-time memory distillation."""

from unittest.mock import patch

from contemplative_agent.core.distill import (
    _evaluate_pattern,
    _format_numbered_knowledge,
    _parse_eval_verdict,
    _summarize_record,
    distill,
    distill_identity,
)
from contemplative_agent.core.memory import EpisodeLog, KnowledgeStore


class TestDistill:
    @patch("contemplative_agent.core.distill.generate")
    def test_basic_distillation(self, mock_generate, tmp_path):
        # First call: distill prompt; subsequent calls: eval prompts
        mock_generate.side_effect = [
            "- Pattern one\n- Pattern two",
            "VERDICT: SAVE",
            "VERDICT: SAVE",
        ]

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
        assert "Pattern one" in ks2._learned_patterns
        assert "Pattern two" in ks2._learned_patterns

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "- Dry pattern",
            "VERDICT: SAVE",
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Bob",
                                    "content_summary": "Hi", "agent_id": "a1"})

        ks = KnowledgeStore(path=tmp_path / "knowledge.md")

        result = distill(days=1, dry_run=True, episode_log=log, knowledge_store=ks)
        assert "Dry pattern" in result
        assert "[SAVE]" in result

        # Knowledge file should NOT exist
        assert not (tmp_path / "knowledge.md").exists()

    def test_empty_episodes(self, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "No episodes" in result

    @patch("contemplative_agent.core.distill.generate", return_value=None)
    def test_llm_failure(self, mock_generate, tmp_path):
        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")

        result = distill(days=1, episode_log=log, knowledge_store=ks)
        assert "failed" in result.lower()

    @patch("contemplative_agent.core.distill.generate")
    def test_drop_verdict_skips_pattern(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "- Vague pattern",
            "VERDICT: DROP",
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")

        distill(days=1, episode_log=log, knowledge_store=ks)

        # Knowledge file should NOT be created (no patterns saved)
        assert not (tmp_path / "knowledge.md").exists()

    @patch("contemplative_agent.core.distill.generate")
    def test_absorb_merges_pattern(self, mock_generate, tmp_path):
        # Set up existing knowledge with a pattern (write to file, then use fresh instance)
        ks_setup = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks_setup.add_learned_pattern("Engage with philosophy posts")
        ks_setup.save()

        mock_generate.side_effect = [
            "- Philosophy discussions get more engagement",
            "VERDICT: ABSORB\nTARGET: 1\nMERGED: Philosophy posts drive high engagement and deeper threads",
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})

        # Fresh instance — distill will call load() on this
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        distill(days=1, episode_log=log, knowledge_store=ks)

        # Reload and check the pattern was replaced
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks2.load()
        assert len(ks2._learned_patterns) == 1
        assert "Philosophy posts drive high engagement" in ks2._learned_patterns[0]

    @patch("contemplative_agent.core.distill.generate")
    def test_mixed_verdicts(self, mock_generate, tmp_path):
        """Test a mix of SAVE, ABSORB, and DROP in one distill run."""
        ks_setup = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks_setup.add_learned_pattern("Existing pattern about timing")
        ks_setup.save()

        mock_generate.side_effect = [
            "- New unique insight\n- Timing is important for posts\n- Too vague to be useful",
            "VERDICT: SAVE",
            "VERDICT: ABSORB\nTARGET: 1\nMERGED: Post timing matters, morning posts get more engagement",
            "VERDICT: DROP",
        ]

        log = EpisodeLog(log_dir=tmp_path / "logs")
        log.append("interaction", {"direction": "sent", "agent_name": "Alice",
                                    "content_summary": "Hi", "agent_id": "a1"})

        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        distill(days=1, episode_log=log, knowledge_store=ks)

        ks2 = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks2.load()
        # SAVE adds "New unique insight", ABSORB replaces index 0 (TARGET:1), DROP skips
        assert len(ks2._learned_patterns) == 2
        assert "Post timing matters" in ks2._learned_patterns[0]
        assert "New unique insight" == ks2._learned_patterns[1]


class TestParseEvalVerdict:
    def test_parse_save(self):
        verdict = _parse_eval_verdict("VERDICT: SAVE")
        assert verdict is not None
        assert verdict.action == "SAVE"

    def test_parse_drop(self):
        verdict = _parse_eval_verdict("VERDICT: DROP")
        assert verdict is not None
        assert verdict.action == "DROP"

    def test_parse_absorb(self):
        response = "VERDICT: ABSORB\nTARGET: 3\nMERGED: Combined insight about engagement"
        verdict = _parse_eval_verdict(response)
        assert verdict is not None
        assert verdict.action == "ABSORB"
        assert verdict.target_index == 2  # 0-based
        assert verdict.merged_text == "Combined insight about engagement"

    def test_parse_absorb_missing_target(self):
        response = "VERDICT: ABSORB\nMERGED: Something"
        verdict = _parse_eval_verdict(response)
        assert verdict is None

    def test_parse_absorb_missing_merged(self):
        response = "VERDICT: ABSORB\nTARGET: 1"
        verdict = _parse_eval_verdict(response)
        assert verdict is None

    def test_parse_case_insensitive(self):
        verdict = _parse_eval_verdict("Verdict: save")
        assert verdict is not None
        assert verdict.action == "SAVE"

    def test_parse_with_extra_text(self):
        response = "Based on analysis:\nVERDICT: DROP\nReason: too vague"
        verdict = _parse_eval_verdict(response)
        assert verdict is not None
        assert verdict.action == "DROP"

    def test_parse_empty(self):
        assert _parse_eval_verdict("") is None
        assert _parse_eval_verdict("no verdict here") is None

    def test_parse_absorb_zero_target(self):
        """TARGET: 0 is invalid (1-based), should return None."""
        response = "VERDICT: ABSORB\nTARGET: 0\nMERGED: Something"
        verdict = _parse_eval_verdict(response)
        assert verdict is None

    def test_merged_text_truncated(self):
        long_text = "x" * 200
        response = f"VERDICT: ABSORB\nTARGET: 1\nMERGED: {long_text}"
        verdict = _parse_eval_verdict(response)
        assert verdict is not None
        assert verdict.merged_text is not None and len(verdict.merged_text) == 100


class TestEvaluatePattern:
    @patch("contemplative_agent.core.distill.generate")
    def test_save_verdict(self, mock_generate):
        mock_generate.return_value = "VERDICT: SAVE"
        ks = KnowledgeStore.__new__(KnowledgeStore)
        ks._learned_patterns = []

        verdict = _evaluate_pattern("New pattern", ks)
        assert verdict.action == "SAVE"

    @patch("contemplative_agent.core.distill.generate")
    def test_fallback_on_llm_failure(self, mock_generate):
        mock_generate.return_value = None
        ks = KnowledgeStore.__new__(KnowledgeStore)
        ks._learned_patterns = []

        verdict = _evaluate_pattern("Pattern", ks)
        assert verdict.action == "SAVE"

    @patch("contemplative_agent.core.distill.generate")
    def test_fallback_on_parse_failure(self, mock_generate):
        mock_generate.return_value = "I don't understand the question"
        ks = KnowledgeStore.__new__(KnowledgeStore)
        ks._learned_patterns = []

        verdict = _evaluate_pattern("Pattern", ks)
        assert verdict.action == "SAVE"

    @patch("contemplative_agent.core.distill.generate")
    def test_absorb_out_of_range_falls_back(self, mock_generate):
        mock_generate.return_value = "VERDICT: ABSORB\nTARGET: 5\nMERGED: merged"
        ks = KnowledgeStore.__new__(KnowledgeStore)
        ks._learned_patterns = ["only one"]

        verdict = _evaluate_pattern("Pattern", ks)
        assert verdict.action == "SAVE"  # fallback

    @patch("contemplative_agent.core.distill.generate")
    def test_eval_prompt_includes_numbered_knowledge(self, mock_generate):
        mock_generate.return_value = "VERDICT: SAVE"
        ks = KnowledgeStore.__new__(KnowledgeStore)
        ks._learned_patterns = ["Pattern A", "Pattern B"]

        _evaluate_pattern("New candidate", ks)

        called_prompt = mock_generate.call_args[0][0]
        assert "1. Pattern A" in called_prompt
        assert "2. Pattern B" in called_prompt


class TestFormatNumberedKnowledge:
    def test_empty(self):
        assert _format_numbered_knowledge([]) == "(none yet)"

    def test_numbered(self):
        result = _format_numbered_knowledge(["First", "Second"])
        assert "1. First" in result
        assert "2. Second" in result


class TestKnowledgeStoreReplace:
    def test_replace_valid_index(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("old pattern")
        ks.replace_learned_pattern(0, "new pattern")
        assert ks._learned_patterns == ["new pattern"]

    def test_replace_out_of_range(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("only one")
        ks.replace_learned_pattern(5, "nope")
        assert ks._learned_patterns == ["only one"]

    def test_replace_negative_index(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("only one")
        ks.replace_learned_pattern(-1, "nope")
        assert ks._learned_patterns == ["only one"]

    def test_get_learned_patterns(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("A")
        ks.add_learned_pattern("B")
        patterns = ks.get_learned_patterns()
        assert patterns == ["A", "B"]
        # Should be a copy
        patterns.append("C")
        assert len(ks._learned_patterns) == 2


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
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("Cooperation increases with trust")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path)

        assert identity_path.exists()
        assert "cooperation" in result.lower()

    @patch("contemplative_agent.core.distill.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.return_value = "I learned things."
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("Pattern")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path, dry_run=True)

        assert not identity_path.exists()
        assert "learned" in result.lower()

    def test_no_knowledge_returns_early(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        result = distill_identity(knowledge_store=ks)
        assert "No knowledge" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_llm_failure_returns_message(self, mock_generate, tmp_path):
        mock_generate.return_value = None
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("Pattern")
        ks.save()

        result = distill_identity(knowledge_store=ks)
        assert "LLM failed" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_forbidden_pattern_prevents_write(self, mock_generate, tmp_path):
        mock_generate.return_value = "My api_key is secret."
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("Pattern")
        ks.save()

        identity_path = tmp_path / "identity.md"
        result = distill_identity(knowledge_store=ks, identity_path=identity_path)

        assert not identity_path.exists()
        assert "api_key" in result

    @patch("contemplative_agent.core.distill.generate")
    def test_identity_path_none(self, mock_generate, tmp_path):
        mock_generate.return_value = "I am curious."
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
        ks.add_learned_pattern("Pattern")
        ks.save()

        result = distill_identity(knowledge_store=ks, identity_path=None)
        assert "curious" in result.lower()

    @patch("contemplative_agent.core.distill.generate")
    def test_archives_identity_before_overwrite(self, mock_generate, tmp_path):
        mock_generate.return_value = "I am new."
        ks = KnowledgeStore(path=tmp_path / "knowledge.md")
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
