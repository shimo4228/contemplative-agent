"""Tests for core.insight — behavioral skill extraction with rubric evaluation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import (
    RubricScore,
    _clamp,
    _evaluate_skill,
    _extract_skill,
    _extract_title,
    _parse_rubric_response,
    _render_score_table,
    _slugify,
    extract_insight,
)
from contemplative_agent.core.memory import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_SKILL_RESPONSE = (
    "---\n"
    "name: ask-before-reacting\n"
    'description: "Ask clarifying questions before forming a response"\n'
    "origin: auto-extracted\n"
    "---\n"
    "\n"
    "# Ask Before Reacting\n"
    "\n"
    "**Extracted:** 2026-03-20\n"
    "**Context:** When encountering unfamiliar viewpoints\n"
    "\n"
    "## Problem\n"
    "Premature responses reduce engagement quality\n"
    "\n"
    "## Solution\n"
    "Ask clarifying questions before forming a response\n"
    "\n"
    "## When to Use\n"
    "When an agent presents a viewpoint you haven't encountered before\n"
)

GOOD_EVAL_RESPONSE = (
    "SPECIFICITY: 4\n"
    "ACTIONABILITY: 4\n"
    "SCOPE_FIT: 3\n"
    "NON_REDUNDANCY: 3\n"
    "COVERAGE: 3\n"
)

LOW_EVAL_RESPONSE = (
    "SPECIFICITY: 2\n"
    "ACTIONABILITY: 4\n"
    "SCOPE_FIT: 3\n"
    "NON_REDUNDANCY: 1\n"
    "COVERAGE: 3\n"
)


@pytest.fixture
def knowledge_store(tmp_path: Path) -> KnowledgeStore:
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(5):
        ks.add_learned_pattern(f"Pattern {i}: some behavioral observation")
    ks.save()
    return ks


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Unit: _extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_extracts_from_markdown(self) -> None:
        assert _extract_title("# My Skill\nsome content") == "My Skill"

    def test_skips_non_title_lines(self) -> None:
        assert _extract_title("## Not a title\n# Real Title") == "Real Title"

    def test_returns_none_for_no_title(self) -> None:
        assert _extract_title("no title here") is None

    def test_strips_whitespace(self) -> None:
        assert _extract_title("#   Spaced Title  ") == "Spaced Title"

    def test_with_frontmatter(self) -> None:
        text = "---\nname: foo\n---\n\n# Title After Frontmatter"
        assert _extract_title(text) == "Title After Frontmatter"


# ---------------------------------------------------------------------------
# Unit: _parse_rubric_response
# ---------------------------------------------------------------------------


class TestParseRubricResponse:
    def test_good_response(self) -> None:
        score = _parse_rubric_response(GOOD_EVAL_RESPONSE)
        assert score.specificity == 4
        assert score.actionability == 4
        assert score.scope_fit == 3
        assert score.non_redundancy == 3
        assert score.coverage == 3
        assert score.total == 17
        assert score.passed is True

    def test_clamps_out_of_range(self) -> None:
        response = (
            "SPECIFICITY: 0\n"
            "ACTIONABILITY: 7\n"
            "SCOPE_FIT: 0\n"
            "NON_REDUNDANCY: 99\n"
            "COVERAGE: 3\n"
        )
        score = _parse_rubric_response(response)
        assert score.specificity == 1
        assert score.actionability == 5
        assert score.scope_fit == 1
        assert score.non_redundancy == 5
        assert score.coverage == 3

    def test_missing_dimension_defaults_to_min(self) -> None:
        response = "SPECIFICITY: 4\n"
        score = _parse_rubric_response(response)
        assert score.specificity == 4
        assert score.actionability == 1

    def test_unparseable_drops_candidate(self) -> None:
        score = _parse_rubric_response("garbage output")
        assert score.total == 5  # MIN_SCORE * 5
        assert score.passed is False

    def test_table_format(self) -> None:
        response = (
            "| SPECIFICITY | 4 |\n"
            "| ACTIONABILITY | 3 |\n"
            "| SCOPE_FIT | 5 |\n"
            "| NON_REDUNDANCY | 2 |\n"
            "| COVERAGE | 3 |\n"
        )
        score = _parse_rubric_response(response)
        assert score.specificity == 4
        assert score.scope_fit == 5

    def test_markdown_bold_format(self) -> None:
        response = (
            "**SPECIFICITY**: 4\n"
            "**ACTIONABILITY**: 5\n"
            "**SCOPE_FIT**: 3\n"
            "**NON_REDUNDANCY**: 3\n"
            "**COVERAGE**: 4\n"
        )
        score = _parse_rubric_response(response)
        assert score.specificity == 4
        assert score.actionability == 5


# ---------------------------------------------------------------------------
# Unit: RubricScore
# ---------------------------------------------------------------------------


class TestRubricScore:
    def test_passed_all_above_threshold(self) -> None:
        score = RubricScore(3, 4, 5, 3, 3)
        assert score.passed is True

    def test_failed_one_below_threshold(self) -> None:
        score = RubricScore(3, 4, 2, 3, 3)
        assert score.passed is False

    def test_confidence(self) -> None:
        score = RubricScore(5, 5, 5, 5, 5)
        assert score.confidence == 1.0
        score2 = RubricScore(1, 1, 1, 1, 1)
        assert score2.confidence == pytest.approx(0.2)

    def test_total(self) -> None:
        score = RubricScore(1, 2, 3, 4, 5)
        assert score.total == 15


# ---------------------------------------------------------------------------
# Unit: helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_clamp(self) -> None:
        assert _clamp(0, 1, 5) == 1
        assert _clamp(6, 1, 5) == 5
        assert _clamp(3, 1, 5) == 3

    def test_slugify(self) -> None:
        assert _slugify("Ask Before Reacting") == "ask-before-reacting"
        assert _slugify("a/b\\c:d") == "a-b-c-d"
        assert _slugify("") == ""
        long_title = "a" * 100
        assert len(_slugify(long_title)) <= 50

    def test_render_score_table(self) -> None:
        score = RubricScore(4, 3, 5, 2, 4)
        table = _render_score_table(score)
        assert "4/5" in table
        assert "**18/25**" in table


# ---------------------------------------------------------------------------
# Integration: _extract_skill
# ---------------------------------------------------------------------------


class TestExtractSkill:
    @patch("contemplative_agent.core.insight.generate")
    def test_success(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        result = _extract_skill(["p1", "p2"], ["i1"])
        assert result is not None
        assert "# Ask Before Reacting" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure(self, mock_generate) -> None:
        mock_generate.return_value = None
        result = _extract_skill(["p1"], [])
        assert result is None

    @patch("contemplative_agent.core.insight.generate")
    def test_no_title_drops(self, mock_generate) -> None:
        mock_generate.return_value = "some text without a title line"
        result = _extract_skill(["p1"], [])
        assert result is None


# ---------------------------------------------------------------------------
# Integration: _evaluate_skill
# ---------------------------------------------------------------------------


class TestEvaluateSkill:
    @patch("contemplative_agent.core.insight.generate")
    def test_success(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_EVAL_RESPONSE
        score = _evaluate_skill(GOOD_SKILL_RESPONSE)
        assert score.specificity == 4
        assert score.passed is True

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure_drops_candidate(self, mock_generate) -> None:
        mock_generate.return_value = None
        score = _evaluate_skill(GOOD_SKILL_RESPONSE)
        assert score.total == 5
        assert score.passed is False


# ---------------------------------------------------------------------------
# Integration: extract_insight (orchestrator)
# ---------------------------------------------------------------------------


class TestExtractInsight:
    def test_no_knowledge_store(self) -> None:
        result = extract_insight(knowledge_store=None)
        assert "No knowledge store" in result

    def test_insufficient_patterns(self, tmp_path: Path) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.md")
        ks.add_learned_pattern("only one")
        ks.save()
        result = extract_insight(knowledge_store=ks)
        assert "Insufficient patterns" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_extraction_failure(self, mock_generate, knowledge_store) -> None:
        mock_generate.return_value = None
        result = extract_insight(knowledge_store=knowledge_store)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.insight.validate_identity_content")
    @patch("contemplative_agent.core.insight.generate")
    def test_forbidden_pattern(
        self, mock_generate, mock_validate, knowledge_store
    ) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        mock_validate.return_value = False
        result = extract_insight(knowledge_store=knowledge_store)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_quality_gate_fail(self, mock_generate, knowledge_store) -> None:
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, LOW_EVAL_RESPONSE]
        result = extract_insight(knowledge_store=knowledge_store)
        assert "did not pass" in result
        assert "Ask Before Reacting" in result
        assert "Summary:" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_dry_run(self, mock_generate, knowledge_store) -> None:
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, GOOD_EVAL_RESPONSE]
        result = extract_insight(
            knowledge_store=knowledge_store, dry_run=True
        )
        assert "# Ask Before Reacting" in result
        assert "Score" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_save_to_file(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, GOOD_EVAL_RESPONSE]
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        assert "# Ask Before Reacting" in result
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "auto-extracted" in content

    @patch("contemplative_agent.core.insight.generate")
    def test_drop_does_not_write(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, LOW_EVAL_RESPONSE]
        extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 0

    @patch("contemplative_agent.core.insight.generate")
    def test_path_traversal_guard(
        self, mock_generate, knowledge_store, tmp_path
    ) -> None:
        evil_response = GOOD_SKILL_RESPONSE.replace(
            "# Ask Before Reacting", "# ../../etc/passwd"
        )
        mock_generate.side_effect = [evil_response, GOOD_EVAL_RESPONSE]
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 1
        assert "etc-passwd" in files[0].name
        assert ".." not in files[0].name


# ---------------------------------------------------------------------------
# Integration: batch processing
# ---------------------------------------------------------------------------


class TestBatchProcessing:
    @pytest.fixture
    def three_batch_store(self, tmp_path: Path) -> KnowledgeStore:
        """KnowledgeStore with patterns for 3 batches (no merge needed)."""
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        for i in range(65):
            ks.add_learned_pattern(f"Pattern {i}: observation about behavior {i}")
        ks.save()
        ks._learned_patterns.clear()
        return ks

    @patch("contemplative_agent.core.insight.generate")
    def test_multiple_batches_produce_multiple_skills(
        self, mock_generate, three_batch_store, skills_dir
    ) -> None:
        """65 patterns → 3 batches → 3 skills."""
        skill_b = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Adapt Tone").replace("ask-before-reacting", "adapt-tone")
        skill_c = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Set Boundaries").replace("ask-before-reacting", "set-boundaries")
        mock_generate.side_effect = [
            GOOD_SKILL_RESPONSE, GOOD_EVAL_RESPONSE,
            skill_b, GOOD_EVAL_RESPONSE,
            skill_c, GOOD_EVAL_RESPONSE,
        ]
        result = extract_insight(
            knowledge_store=three_batch_store,
            skills_dir=skills_dir,
        )
        assert "3 saved" in result
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 3

    @patch("contemplative_agent.core.insight.generate")
    def test_partial_failure_saves_passing_batches(
        self, mock_generate, three_batch_store, skills_dir
    ) -> None:
        skill_c = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Set Boundaries").replace("ask-before-reacting", "set-boundaries")
        mock_generate.side_effect = [
            None,  # batch 1: extraction failure
            GOOD_SKILL_RESPONSE, GOOD_EVAL_RESPONSE,
            skill_c, GOOD_EVAL_RESPONSE,
        ]
        result = extract_insight(
            knowledge_store=three_batch_store,
            skills_dir=skills_dir,
        )
        assert "2 saved" in result
        assert "1 dropped" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_small_last_batch_merged(self, mock_generate, tmp_path: Path) -> None:
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        for i in range(32):
            ks.add_learned_pattern(f"Pattern {i}: unique observation {i}")
        ks.save()
        ks._learned_patterns.clear()

        call_count = 0

        def count_calls(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 1:
                return GOOD_SKILL_RESPONSE
            return GOOD_EVAL_RESPONSE

        mock_generate.side_effect = count_calls
        extract_insight(knowledge_store=ks, dry_run=True)
        assert call_count == 2

    def test_single_batch_unchanged(self, knowledge_store, skills_dir) -> None:
        with patch("contemplative_agent.core.insight.generate") as mock_gen:
            mock_gen.side_effect = [GOOD_SKILL_RESPONSE, GOOD_EVAL_RESPONSE]
            result = extract_insight(
                knowledge_store=knowledge_store,
                skills_dir=skills_dir,
            )
            assert "1 saved" in result
            files = list(skills_dir.glob("*.md"))
            assert len(files) == 1
