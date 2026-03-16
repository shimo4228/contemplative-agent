"""Tests for core.insight — behavioral skill extraction with rubric evaluation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import (
    MAX_FIELD_LENGTH,
    RubricScore,
    SkillCandidate,
    _clamp,
    _evaluate_skill,
    _extract_skill,
    _parse_rubric_response,
    _parse_skill_response,
    _render_score_table,
    _render_skill_file,
    _slugify,
    extract_insight,
)
from contemplative_agent.core.memory import KnowledgeStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_EXTRACTION_RESPONSE = (
    "TITLE: Ask before reacting\n"
    "CONTEXT: When encountering unfamiliar viewpoints\n"
    "PROBLEM: Premature responses reduce engagement quality\n"
    "BEHAVIOR: Ask clarifying questions before forming a response\n"
    "EVIDENCE: Patterns show better engagement when understanding precedes reaction"
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
    ks = KnowledgeStore(path=tmp_path / "knowledge.md")
    for i in range(5):
        ks.add_learned_pattern(f"Pattern {i}: some behavioral observation")
    ks.add_insight("Recent insight about engagement")
    ks.save()
    return ks


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Unit: _parse_skill_response
# ---------------------------------------------------------------------------


class TestParseSkillResponse:
    def test_good_response(self) -> None:
        result = _parse_skill_response(GOOD_EXTRACTION_RESPONSE)
        assert result is not None
        assert result.title == "Ask before reacting"
        assert "unfamiliar" in result.context
        assert "clarifying" in result.behavior

    def test_missing_field_returns_none(self) -> None:
        incomplete = "TITLE: foo\nCONTEXT: bar\nPROBLEM: baz\n"
        assert _parse_skill_response(incomplete) is None

    def test_truncates_long_fields(self) -> None:
        long_value = "x" * 500
        response = (
            f"TITLE: {long_value}\n"
            f"CONTEXT: ctx\n"
            f"PROBLEM: prob\n"
            f"BEHAVIOR: beh\n"
            f"EVIDENCE: evi\n"
        )
        result = _parse_skill_response(response)
        assert result is not None
        assert len(result.title) == MAX_FIELD_LENGTH

    def test_case_insensitive(self) -> None:
        response = (
            "title: foo\n"
            "context: bar\n"
            "problem: baz\n"
            "behavior: qux\n"
            "evidence: quux\n"
        )
        result = _parse_skill_response(response)
        assert result is not None
        assert result.title == "foo"


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

    def test_negative_value_defaults_to_min(self) -> None:
        """Negative numbers don't match \\d+ regex, so default to MIN_SCORE (fail-safe)."""
        response = "SPECIFICITY: -1\nACTIONABILITY: 4\n"
        score = _parse_rubric_response(response)
        assert score.specificity == 1
        assert score.actionability == 4

    def test_missing_dimension_defaults_to_min(self) -> None:
        """Missing dimensions default to MIN_SCORE (fail-safe)."""
        response = "SPECIFICITY: 4\n"
        score = _parse_rubric_response(response)
        assert score.specificity == 4
        assert score.actionability == 1
        assert score.scope_fit == 1

    def test_unparseable_drops_candidate(self) -> None:
        """Fully unparseable response should fail the quality gate."""
        score = _parse_rubric_response("garbage output")
        assert score.total == 5  # MIN_SCORE * 5
        assert score.passed is False

    def test_table_format(self) -> None:
        """Qwen sometimes responds with Markdown table format."""
        response = (
            "| SPECIFICITY | 4 |\n"
            "| ACTIONABILITY | 3 |\n"
            "| SCOPE_FIT | 5 |\n"
            "| NON_REDUNDANCY | 2 |\n"
            "| COVERAGE | 3 |\n"
        )
        score = _parse_rubric_response(response)
        assert score.specificity == 4
        assert score.actionability == 3
        assert score.scope_fit == 5
        assert score.non_redundancy == 2
        assert score.coverage == 3

    def test_markdown_bold_format(self) -> None:
        """Qwen sometimes wraps dimension names in bold."""
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
        assert score.coverage == 4


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

    def test_render_skill_file(self) -> None:
        candidate = SkillCandidate(
            title="Test Skill",
            context="When testing",
            problem="Tests may fail",
            behavior="Write tests first",
            evidence="TDD patterns",
        )
        score = RubricScore(4, 4, 3, 3, 3)
        rendered = _render_skill_file(candidate, score, source_patterns=5)
        assert "# Test Skill" in rendered
        assert "confidence: 0.68" in rendered
        assert "origin: auto-extracted" in rendered
        assert "source_patterns: 5" in rendered

    def test_render_skill_file_newline_injection(self) -> None:
        """YAML frontmatter must not contain raw newlines that break YAML structure."""
        candidate = SkillCandidate(
            title="Skill\nmalicious_key: injected",
            context="Context\nfoo: bar",
            problem="prob",
            behavior="beh",
            evidence="evi",
        )
        score = RubricScore(3, 3, 3, 3, 3)
        rendered = _render_skill_file(candidate, score, source_patterns=1)
        frontmatter = rendered.split("---")[1]
        # Newlines should be replaced with spaces (then hyphens in name).
        # Values stay inside double quotes, so no YAML key injection.
        assert "\nmalicious_key:" not in frontmatter
        assert "\nfoo:" not in frontmatter
        # Description is quoted: 'description: "Context foo: bar"' — safe
        assert 'description: "Context foo: bar"' in frontmatter
        # Title heading should have newline replaced with space
        assert "# Skill malicious_key: injected" in rendered

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
        mock_generate.return_value = GOOD_EXTRACTION_RESPONSE
        result = _extract_skill(["p1", "p2"], ["i1"])
        assert result is not None
        assert result.title == "Ask before reacting"

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure(self, mock_generate) -> None:
        mock_generate.return_value = None
        result = _extract_skill(["p1"], [])
        assert result is None

    @patch("contemplative_agent.core.insight.generate")
    def test_parse_failure(self, mock_generate) -> None:
        mock_generate.return_value = "not a valid response"
        result = _extract_skill(["p1"], [])
        assert result is None


# ---------------------------------------------------------------------------
# Integration: _evaluate_skill
# ---------------------------------------------------------------------------


class TestEvaluateSkill:
    @patch("contemplative_agent.core.insight.generate")
    def test_success(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_EVAL_RESPONSE
        candidate = SkillCandidate("t", "c", "p", "b", "e")
        score = _evaluate_skill(candidate)
        assert score.specificity == 4
        assert score.passed is True

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure_drops_candidate(self, mock_generate) -> None:
        """LLM failure should fail-safe to DROP, not pass."""
        mock_generate.return_value = None
        candidate = SkillCandidate("t", "c", "p", "b", "e")
        score = _evaluate_skill(candidate)
        assert score.total == 5  # MIN_SCORE * 5
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
        mock_generate.return_value = GOOD_EXTRACTION_RESPONSE
        mock_validate.return_value = False
        result = extract_insight(knowledge_store=knowledge_store)
        assert "forbidden" in result.lower()

    @patch("contemplative_agent.core.insight.generate")
    def test_quality_gate_fail(self, mock_generate, knowledge_store) -> None:
        mock_generate.side_effect = [GOOD_EXTRACTION_RESPONSE, LOW_EVAL_RESPONSE]
        result = extract_insight(knowledge_store=knowledge_store)
        assert "did not pass" in result
        # DROP should still show the full candidate
        assert "Ask before reacting" in result
        assert "Context:" in result
        assert "Behavior:" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_dry_run(self, mock_generate, knowledge_store) -> None:
        mock_generate.side_effect = [GOOD_EXTRACTION_RESPONSE, GOOD_EVAL_RESPONSE]
        result = extract_insight(
            knowledge_store=knowledge_store, dry_run=True
        )
        assert "# Ask before reacting" in result
        assert "Score" in result
        assert "{source_patterns}" not in result

    @patch("contemplative_agent.core.insight.generate")
    def test_save_to_file(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        mock_generate.side_effect = [GOOD_EXTRACTION_RESPONSE, GOOD_EVAL_RESPONSE]
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        assert "# Ask before reacting" in result
        # Verify file was written
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 1
        content = files[0].read_text()
        assert "auto-extracted" in content

    @patch("contemplative_agent.core.insight.generate")
    def test_drop_does_not_write(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        mock_generate.side_effect = [GOOD_EXTRACTION_RESPONSE, LOW_EVAL_RESPONSE]
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
        # Title with path traversal attempt
        evil_response = GOOD_EXTRACTION_RESPONSE.replace(
            "Ask before reacting", "../../etc/passwd"
        )
        mock_generate.side_effect = [evil_response, GOOD_EVAL_RESPONSE]
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        # _slugify strips path separators: "../../etc/passwd" → "etc-passwd"
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 1
        assert "etc-passwd" in files[0].name
        assert ".." not in files[0].name
