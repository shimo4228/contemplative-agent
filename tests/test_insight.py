"""Tests for core.insight — behavioral skill extraction with LLM verdict."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import (
    _evaluate_skill,
    _extract_skill,
    _extract_title,
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
# Unit: _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic(self) -> None:
        assert _slugify("Ask Before Reacting") == "ask-before-reacting"

    def test_special_chars(self) -> None:
        assert _slugify("a/b\\c:d") == "a-b-c-d"

    def test_empty(self) -> None:
        assert _slugify("") == ""

    def test_max_length(self) -> None:
        assert len(_slugify("a" * 100)) <= 50


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
        assert _extract_skill(["p1"], []) is None

    @patch("contemplative_agent.core.insight.generate")
    def test_no_title_drops(self, mock_generate) -> None:
        mock_generate.return_value = "some text without a title line"
        assert _extract_skill(["p1"], []) is None


# ---------------------------------------------------------------------------
# Integration: _evaluate_skill
# ---------------------------------------------------------------------------


class TestEvaluateSkill:
    @patch("contemplative_agent.core.insight.generate")
    def test_save(self, mock_generate) -> None:
        mock_generate.return_value = "Save"
        assert _evaluate_skill(GOOD_SKILL_RESPONSE) is True

    @patch("contemplative_agent.core.insight.generate")
    def test_drop(self, mock_generate) -> None:
        mock_generate.return_value = "Drop"
        assert _evaluate_skill(GOOD_SKILL_RESPONSE) is False

    @patch("contemplative_agent.core.insight.generate")
    def test_save_with_explanation(self, mock_generate) -> None:
        mock_generate.return_value = "Save because it is specific and actionable"
        assert _evaluate_skill(GOOD_SKILL_RESPONSE) is True

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure_drops(self, mock_generate) -> None:
        mock_generate.return_value = None
        assert _evaluate_skill(GOOD_SKILL_RESPONSE) is False

    @patch("contemplative_agent.core.insight.generate")
    def test_garbage_output_drops(self, mock_generate) -> None:
        mock_generate.return_value = "I think this skill is great!"
        assert _evaluate_skill(GOOD_SKILL_RESPONSE) is False

    @patch("contemplative_agent.core.insight.generate")
    def test_empty_output_drops(self, mock_generate) -> None:
        mock_generate.return_value = ""
        assert _evaluate_skill(GOOD_SKILL_RESPONSE) is False


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
    def test_verdict_drop(self, mock_generate, knowledge_store) -> None:
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, "Drop"]
        result = extract_insight(knowledge_store=knowledge_store)
        assert "dropped" in result
        assert "Summary:" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_dry_run(self, mock_generate, knowledge_store) -> None:
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, "Save"]
        result = extract_insight(
            knowledge_store=knowledge_store, dry_run=True
        )
        assert "# Ask Before Reacting" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_save_to_file(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, "Save"]
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        assert "# Ask Before Reacting" in result
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 1
        today = date.today().strftime("%Y%m%d")
        assert files[0].name == f"ask-before-reacting-{today}.md"
        content = files[0].read_text()
        assert "auto-extracted" in content

    @patch("contemplative_agent.core.insight.generate")
    def test_drop_does_not_write(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, "Drop"]
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
        mock_generate.side_effect = [evil_response, "Save"]
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
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        for i in range(65):
            ks.add_learned_pattern(f"Pattern {i}: observation about behavior {i}")
        ks.save()
        ks._learned_patterns.clear()
        return ks

    @patch("contemplative_agent.core.insight.generate")
    def test_multiple_batches(
        self, mock_generate, three_batch_store, skills_dir
    ) -> None:
        skill_b = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Adapt Tone").replace("ask-before-reacting", "adapt-tone")
        skill_c = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Set Boundaries").replace("ask-before-reacting", "set-boundaries")
        mock_generate.side_effect = [
            GOOD_SKILL_RESPONSE, "Save",
            skill_b, "Save",
            skill_c, "Save",
        ]
        result = extract_insight(
            knowledge_store=three_batch_store,
            skills_dir=skills_dir,
        )
        assert "3 saved" in result
        files = list(skills_dir.glob("*.md"))
        assert len(files) == 3

    @patch("contemplative_agent.core.insight.generate")
    def test_partial_failure(
        self, mock_generate, three_batch_store, skills_dir
    ) -> None:
        skill_c = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Set Boundaries").replace("ask-before-reacting", "set-boundaries")
        mock_generate.side_effect = [
            None,  # batch 1: extraction failure
            GOOD_SKILL_RESPONSE, "Save",
            skill_c, "Save",
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
            if call_count == 1:
                return GOOD_SKILL_RESPONSE
            return "Save"

        mock_generate.side_effect = count_calls
        extract_insight(knowledge_store=ks, dry_run=True)
        assert call_count == 2

    def test_single_batch(self, knowledge_store, skills_dir) -> None:
        with patch("contemplative_agent.core.insight.generate") as mock_gen:
            mock_gen.side_effect = [GOOD_SKILL_RESPONSE, "Save"]
            result = extract_insight(
                knowledge_store=knowledge_store,
                skills_dir=skills_dir,
            )
            assert "1 saved" in result
            files = list(skills_dir.glob("*.md"))
            assert len(files) == 1
