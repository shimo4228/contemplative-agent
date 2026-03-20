"""Tests for meditation report — formatting, LLM interpretation, and storage."""

from __future__ import annotations

import json
from unittest.mock import patch

from contemplative_agent.adapters.meditation.config import CONTEXT_STATES
from contemplative_agent.adapters.meditation.meditate import MeditationResult
from contemplative_agent.adapters.meditation.report import (
    format_meditation_summary,
    interpret_and_save,
)


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
        assert "0.300" in summary
        assert "0.250" in summary


class TestInterpretAndSave:
    def test_zero_cycles_returns_early(self, tmp_path):
        result = _make_result(cycles=0)
        results_path = tmp_path / "meditation" / "results.json"
        output = interpret_and_save(result, results_path)
        assert "No meditation cycles run" in output
        assert not results_path.exists()

    def test_dry_run_does_not_save(self, tmp_path):
        result = _make_result()
        results_path = tmp_path / "meditation" / "results.json"
        llm_response = (
            "- The agent became slightly more focused on mid-session activity\n"
            "- Pruned policies suggest releasing idle behaviors\n"
        )
        with patch(
            "contemplative_agent.adapters.meditation.report.generate",
            return_value=llm_response,
        ):
            output = interpret_and_save(
                result, results_path, dry_run=True,
                prompt_template="Test: {meditation_summary}",
            )
        assert "more focused on mid-session" in output
        assert "dry run" in output
        assert not results_path.exists()

    def test_saves_result_json(self, tmp_path):
        result = _make_result()
        results_path = tmp_path / "meditation" / "results.json"
        llm_response = "- Insight one\n- Insight two\n"
        with patch(
            "contemplative_agent.adapters.meditation.report.generate",
            return_value=llm_response,
        ):
            interpret_and_save(
                result, results_path, dry_run=False,
                prompt_template="Test: {meditation_summary}",
            )
        assert results_path.exists()
        data = json.loads(results_path.read_text())
        assert len(data) == 1
        assert data[0]["cycles_run"] == 10
        assert data[0]["pruned_policies"] == 5
        assert "ts" in data[0]

    def test_appends_to_existing_results(self, tmp_path):
        result = _make_result()
        results_path = tmp_path / "meditation" / "results.json"
        results_path.parent.mkdir(parents=True)
        results_path.write_text('[{"ts": "old", "cycles_run": 5}]')
        with patch(
            "contemplative_agent.adapters.meditation.report.generate",
            return_value="- test\n",
        ):
            interpret_and_save(
                result, results_path, dry_run=False,
                prompt_template="Test: {meditation_summary}",
            )
        data = json.loads(results_path.read_text())
        assert len(data) == 2
        assert data[0]["cycles_run"] == 5
        assert data[1]["cycles_run"] == 10

    def test_llm_returns_none(self, tmp_path):
        result = _make_result()
        results_path = tmp_path / "meditation" / "results.json"
        with patch(
            "contemplative_agent.adapters.meditation.report.generate",
            return_value=None,
        ):
            output = interpret_and_save(
                result, results_path, dry_run=False,
                prompt_template="Test: {meditation_summary}",
            )
        assert "LLM returned no output" in output
        # Result should still be saved even if LLM fails
        assert results_path.exists()

    def test_no_prompt_template(self, tmp_path):
        result = _make_result()
        results_path = tmp_path / "meditation" / "results.json"
        output = interpret_and_save(result, results_path, prompt_template=None)
        assert "Meditation Session Summary" in output
