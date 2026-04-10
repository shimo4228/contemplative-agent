"""Tests for core.insight — behavioral skill extraction."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import (
    InsightResult,
    SkillResult,
    _build_stratified_batches,
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
# Integration: extract_insight (orchestrator)
# ---------------------------------------------------------------------------


class TestExtractInsight:
    def test_no_knowledge_store(self) -> None:
        result = extract_insight(knowledge_store=None)
        assert isinstance(result, str)
        assert "No knowledge store" in result

    def test_insufficient_patterns(self, tmp_path: Path) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.md")
        ks.add_learned_pattern("only one")
        ks.save()
        result = extract_insight(knowledge_store=ks)
        assert isinstance(result, str)
        assert "Insufficient patterns" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_extraction_failure(self, mock_generate, knowledge_store) -> None:
        mock_generate.return_value = None
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.insight.validate_identity_content")
    @patch("contemplative_agent.core.insight.generate")
    def test_forbidden_pattern(
        self, mock_generate, mock_validate, knowledge_store
    ) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        mock_validate.return_value = False
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_returns_insight_result(self, mock_generate, knowledge_store) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 1
        assert "# Ask Before Reacting" in result.skills[0].text
        today = date.today().strftime("%Y%m%d")
        assert result.skills[0].filename == f"ask-before-reacting-{today}.md"

    @patch("contemplative_agent.core.insight.generate")
    def test_result_has_target_path(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        today = date.today().strftime("%Y%m%d")
        assert result.skills[0].target_path == skills_dir / f"ask-before-reacting-{today}.md"
        # Core function does not write files — caller's responsibility
        assert len(list(skills_dir.glob("*.md"))) == 0

    @patch("contemplative_agent.core.insight.generate")
    def test_path_traversal_guard(
        self, mock_generate, knowledge_store, tmp_path
    ) -> None:
        evil_response = GOOD_SKILL_RESPONSE.replace(
            "# Ask Before Reacting", "# ../../etc/passwd"
        )
        mock_generate.return_value = evil_response
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        # Path traversal is blocked but slug sanitization makes it safe
        assert isinstance(result, InsightResult)
        assert "etc-passwd" in result.skills[0].filename
        assert ".." not in result.skills[0].filename


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
        mock_generate.side_effect = [GOOD_SKILL_RESPONSE, skill_b, skill_c]
        result = extract_insight(
            knowledge_store=three_batch_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 3

    @patch("contemplative_agent.core.insight.generate")
    def test_partial_failure(
        self, mock_generate, three_batch_store, skills_dir
    ) -> None:
        skill_c = GOOD_SKILL_RESPONSE.replace("Ask Before Reacting", "Set Boundaries").replace("ask-before-reacting", "set-boundaries")
        mock_generate.side_effect = [None, GOOD_SKILL_RESPONSE, skill_c]
        result = extract_insight(
            knowledge_store=three_batch_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 2
        assert result.dropped_count == 1

    @patch("contemplative_agent.core.insight.generate")
    def test_small_last_batch_merged(self, mock_generate, tmp_path: Path) -> None:
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        for i in range(32):
            ks.add_learned_pattern(f"Pattern {i}: unique observation {i}")
        ks.save()
        ks._learned_patterns.clear()

        mock_generate.return_value = GOOD_SKILL_RESPONSE
        extract_insight(knowledge_store=ks)
        assert mock_generate.call_count == 1  # 1 batch, 1 LLM call

    def test_single_batch(self, knowledge_store, skills_dir) -> None:
        with patch("contemplative_agent.core.insight.generate") as mock_gen:
            mock_gen.return_value = GOOD_SKILL_RESPONSE
            result = extract_insight(
                knowledge_store=knowledge_store,
                skills_dir=skills_dir,
            )
            assert isinstance(result, InsightResult)
            assert len(result.skills) == 1


# ---------------------------------------------------------------------------
# Integration: incremental mode
# ---------------------------------------------------------------------------


class TestIncrementalMode:
    @patch("contemplative_agent.core.insight.generate")
    def test_no_marker_written_by_core(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        """Core function does not write marker — caller's responsibility."""
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
        )
        assert isinstance(result, InsightResult)
        marker = skills_dir / ".last_insight"
        assert not marker.exists()

    @patch("contemplative_agent.core.insight.generate")
    def test_incremental_filters_old_patterns(
        self, mock_generate, tmp_path
    ) -> None:
        """With .last_insight set, only new patterns are processed."""
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("old pattern", distilled="2026-01-01T00:00+00:00")
        ks.add_learned_pattern("new pattern", distilled="2026-03-20T12:00+00:00")
        ks.save()
        ks._learned_patterns.clear()

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # Set last insight to before the new pattern
        (skills_dir / ".last_insight").write_text("2026-03-01T00:00+00:00\n")

        mock_generate.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(
            knowledge_store=ks,
            skills_dir=skills_dir,
        )
        # Only 1 new pattern, which is < MIN_PATTERNS_REQUIRED (3)
        assert isinstance(result, str)
        assert "Insufficient patterns (1/3)" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_full_ignores_marker(
        self, mock_generate, knowledge_store, skills_dir
    ) -> None:
        """--full processes all patterns regardless of marker."""
        (skills_dir / ".last_insight").write_text("2099-01-01T00:00+00:00\n")
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(
            knowledge_store=knowledge_store,
            skills_dir=skills_dir,
            full=True,
        )
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 1


# ---------------------------------------------------------------------------
# Unit: _build_stratified_batches
# ---------------------------------------------------------------------------


class TestStratifiedBatches:
    """Test stratified batch building for diverse skill extraction."""

    @staticmethod
    def _make_pattern(
        text: str,
        subcategory: str | None = None,
        rarity: float | None = None,
    ) -> dict:
        p: dict = {"pattern": text, "category": "uncategorized"}
        if subcategory is not None:
            p["subcategory"] = subcategory
        if rarity is not None:
            p["rarity"] = rarity
        return p

    def test_single_subcategory_fallback(self) -> None:
        """All patterns without subcategory degrade to single-group batching."""
        patterns = [self._make_pattern(f"p{i}") for i in range(10)]
        batches = _build_stratified_batches(patterns, batch_size=5)
        assert len(batches) == 2
        total = sum(len(b) for b in batches)
        assert total == 10

    def test_even_distribution(self) -> None:
        """Patterns from 3 subcategories are distributed across batches."""
        patterns = []
        for sub in ("communication", "reasoning", "social"):
            for i in range(10):
                patterns.append(self._make_pattern(f"{sub}-{i}", subcategory=sub))
        batches = _build_stratified_batches(patterns, batch_size=9)
        # Each batch of 9 should have 3 from each subcategory
        for batch in batches:
            subs = set()
            for text in batch:
                subs.add(text.split("-")[0])
            assert len(subs) == 3, f"Expected 3 subcategories in batch, got {subs}"

    def test_rarity_priority(self) -> None:
        """Higher rarity patterns appear in earlier batches."""
        patterns = [
            self._make_pattern("high", subcategory="technical", rarity=9.0),
            self._make_pattern("low", subcategory="technical", rarity=2.0),
            self._make_pattern("mid", subcategory="technical", rarity=5.0),
        ]
        batches = _build_stratified_batches(patterns, batch_size=2)
        assert batches[0][0] == "high"
        assert batches[0][1] == "mid"

    def test_tail_merge(self) -> None:
        """Small last batch gets merged into previous."""
        patterns = [self._make_pattern(f"p{i}", subcategory="content") for i in range(8)]
        batches = _build_stratified_batches(patterns, batch_size=5, min_batch_size=3)
        # 8 patterns, batch_size=5: [5, 3] -> last batch has 3 >= min, keep separate
        assert len(batches) == 2
        # Now with 7 patterns: [5, 2] -> 2 < 3, merge into one batch of 7
        patterns7 = patterns[:7]
        batches7 = _build_stratified_batches(patterns7, batch_size=5, min_batch_size=3)
        assert len(batches7) == 1
        assert len(batches7[0]) == 7

    def test_mixed_enriched_unenriched(self) -> None:
        """Patterns with and without subcategory/rarity are all included."""
        patterns = [
            self._make_pattern("enriched-1", subcategory="reasoning", rarity=8.0),
            self._make_pattern("enriched-2", subcategory="social", rarity=6.0),
            self._make_pattern("bare-1"),
            self._make_pattern("bare-2"),
        ]
        batches = _build_stratified_batches(patterns, batch_size=10)
        all_texts = batches[0]
        assert len(all_texts) == 4
        assert set(all_texts) == {"enriched-1", "enriched-2", "bare-1", "bare-2"}
