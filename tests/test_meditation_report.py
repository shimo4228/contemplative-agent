"""Tests for meditation report — formatting, LLM interpretation, and storage."""

from __future__ import annotations

from unittest.mock import patch

from contemplative_agent.adapters.meditation.config import CONTEXT_STATES
from contemplative_agent.adapters.meditation.meditate import MeditationResult
from contemplative_agent.adapters.meditation.report import (
    format_meditation_summary,
    interpret_and_store,
)
from contemplative_agent.core.knowledge_store import KnowledgeStore


def _make_result(cycles: int = 10) -> MeditationResult:
    """Create a sample MeditationResult for testing."""
    return MeditationResult(
        initial_beliefs=(0.3, 0.3, 0.2, 0.2),
        final_beliefs=(0.25, 0.35, 0.2, 0.2),
        belief_trajectory=(
            (0.3, 0.3, 0.2, 0.2),
            (0.25, 0.35, 0.2, 0.2),
        ),
        pruned_policies=5,
        cycles_run=cycles,
        entropy_initial=1.35,
        entropy_final=1.37,
        convergence_delta=0.001,
    )


class TestFormatMeditationSummary:
    def test_contains_key_sections(self):
        result = _make_result()
        summary = format_meditation_summary(result)
        assert "Meditation Session Summary" in summary
        assert "Cycles run: 10" in summary
        assert "Entropy" in summary
        assert "Initial:" in summary
        assert "Final:" in summary

    def test_contains_context_states(self):
        result = _make_result()
        summary = format_meditation_summary(result)
        for ctx in CONTEXT_STATES:
            assert ctx in summary

    def test_contains_belief_changes(self):
        result = _make_result()
        summary = format_meditation_summary(result)
        # early_session: 0.3 → 0.25
        assert "0.300" in summary
        assert "0.250" in summary


class TestInterpretAndStore:
    def test_zero_cycles_returns_early(self):
        result = _make_result(cycles=0)
        ks = KnowledgeStore(path=None)
        output = interpret_and_store(result, ks)
        assert "No meditation cycles run" in output

    def test_with_llm_output(self):
        result = _make_result()
        ks = KnowledgeStore(path=None)
        llm_response = (
            "- The agent became slightly more focused on mid-session activity\n"
            "- Pruned policies suggest releasing idle behaviors\n"
        )
        with patch(
            "contemplative_agent.adapters.meditation.report.generate",
            return_value=llm_response,
        ):
            output = interpret_and_store(
                result, ks, dry_run=True,
                prompt_template="Test: {meditation_summary}",
            )
        assert "more focused on mid-session" in output
        assert "dry run" in output
        # Should not have saved (dry run)
        assert len(ks.get_learned_patterns()) == 0

    def test_saves_patterns_when_not_dry_run(self, tmp_path):
        result = _make_result()
        ks_path = tmp_path / "knowledge.json"
        ks_path.write_text("[]")
        ks = KnowledgeStore(path=ks_path)
        llm_response = "- Insight one\n- Insight two\n"
        with patch(
            "contemplative_agent.adapters.meditation.report.generate",
            return_value=llm_response,
        ):
            interpret_and_store(
                result, ks, dry_run=False,
                prompt_template="Test: {meditation_summary}",
            )
        patterns = ks.get_learned_patterns()
        assert len(patterns) == 2
        assert "Insight one" in patterns[0]

    def test_llm_returns_none(self):
        result = _make_result()
        ks = KnowledgeStore(path=None)
        with patch(
            "contemplative_agent.adapters.meditation.report.generate",
            return_value=None,
        ):
            output = interpret_and_store(
                result, ks, dry_run=False,
                prompt_template="Test: {meditation_summary}",
            )
        assert "LLM returned no output" in output

    def test_no_prompt_template(self):
        result = _make_result()
        ks = KnowledgeStore(path=None)
        output = interpret_and_store(result, ks, prompt_template=None)
        # Should fall back gracefully (no prompt template attr)
        assert "Meditation Session Summary" in output
