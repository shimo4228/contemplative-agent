"""Tests for core.insight — global-cluster behavioral skill extraction."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import (
    InsightResult,
    _build_cluster_batches,
    _extract_skill,
    extract_insight,
)
from contemplative_agent.core.memory import KnowledgeStore
from contemplative_agent.core.text_utils import extract_title, slugify


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
)


def _unit_vec(dim: int, axis: int) -> list:
    """Unit vector along one axis for deterministic cluster-mocking."""
    v = [0.0] * dim
    v[axis] = 1.0
    return v


@pytest.fixture
def knowledge_store(tmp_path: Path) -> KnowledgeStore:
    """5 patterns on the same axis → one tight cluster under threshold 0.70."""
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(5):
        ks.add_learned_pattern(
            f"Pattern {i}: some behavioral observation",
            embedding=_unit_vec(8, 1),
        )
    ks.save()
    return ks


@pytest.fixture
def skills_dir(tmp_path: Path) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    return d


# ---------------------------------------------------------------------------
# Unit: extract_title / slugify
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_extracts_from_markdown(self) -> None:
        assert extract_title("# My Skill\nsome content") == "My Skill"

    def test_skips_non_title_lines(self) -> None:
        assert extract_title("## Not a title\n# Real Title") == "Real Title"

    def test_returns_none_for_no_title(self) -> None:
        assert extract_title("no title here") is None

    def test_skips_leading_frontmatter(self) -> None:
        # Merge/insight emit a `---` frontmatter block before the title;
        # extract_title must return the heading, not a frontmatter line.
        body = (
            "---\n"
            "name: my-skill\n"
            'description: "x"\n'
            "origin: auto-extracted\n"
            "---\n\n"
            "# My Skill\n\nbody"
        )
        assert extract_title(body) == "My Skill"


class TestSlugify:
    def test_basic(self) -> None:
        assert slugify("Ask Before Reacting") == "ask-before-reacting"

    def test_special_chars(self) -> None:
        assert slugify("a/b\\c:d") == "a-b-c-d"

    def test_max_length(self) -> None:
        assert len(slugify("a" * 100)) <= 50


# ---------------------------------------------------------------------------
# _extract_skill
# ---------------------------------------------------------------------------


class TestExtractSkill:
    @patch("contemplative_agent.core.insight.generate")
    def test_returns_skill_text(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        result = _extract_skill(["p1", "p2"], ["i1"])
        assert result is not None
        assert "# Ask Before Reacting" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure(self, mock_generate) -> None:
        mock_generate.return_value = None
        assert _extract_skill(["p1"], []) is None

    @patch("contemplative_agent.core.insight.generate")
    def test_no_title_returns_none(self, mock_generate) -> None:
        mock_generate.return_value = "some text without a title line"
        assert _extract_skill(["p1"], []) is None

    @patch("contemplative_agent.core.insight.generate")
    def test_passes_topic_to_prompt(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        _extract_skill(["p1"], [], topic="cluster-1")
        prompt_arg = mock_generate.call_args[0][0]
        assert "cluster-1" in prompt_arg

    @patch("contemplative_agent.core.insight.generate")
    def test_uses_distill_system_prompt(self, mock_generate, tmp_path) -> None:
        """Audit H6: skill generation must not be conditioned on the existing
        skill corpus nor identity — same anti-circularity grounding as
        distill. Configure both so a regression to the full or identity
        prompt cannot pass."""
        from contemplative_agent.core.llm import (
            configure,
            get_distill_system_prompt,
            reset_llm_config,
        )
        reset_llm_config()
        identity = tmp_path / "identity.md"
        identity.write_text("# Who I Am\nIDENTITY-MARKER-TEXT")
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "marker.md").write_text("# Marker Skill\nx")
        configure(identity_path=identity, skills_dir=skills_dir)
        try:
            mock_generate.return_value = GOOD_SKILL_RESPONSE
            _extract_skill(["p1"], ["i1"])
            system = mock_generate.call_args.kwargs["system"]
            assert system == get_distill_system_prompt()
            assert "<learned_skills>" not in system
            assert "IDENTITY-MARKER-TEXT" not in system
        finally:
            reset_llm_config()


# ---------------------------------------------------------------------------
# extract_insight (orchestrator)
# ---------------------------------------------------------------------------


class TestExtractInsight:
    def test_no_knowledge_store(self) -> None:
        result = extract_insight(knowledge_store=None)
        assert "No knowledge store" in str(result)

    def test_insufficient_patterns(self, tmp_path) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.json")
        ks.add_learned_pattern("only one", embedding=_unit_vec(8, 1))
        ks.save()
        result = extract_insight(knowledge_store=ks)
        assert "Insufficient patterns" in str(result)

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_extraction_failure(self, mock_skill, knowledge_store) -> None:
        mock_skill.return_value = None
        result = extract_insight(knowledge_store=knowledge_store)
        assert "Failed to extract" in str(result)

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_returns_insight_result(self, mock_skill, knowledge_store) -> None:
        mock_skill.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 1
        assert "# Ask Before Reacting" in result.skills[0].text
        today = date.today().strftime("%Y%m%d")
        assert result.skills[0].filename == f"ask-before-reacting-{today}.md"

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_gated_patterns_excluded(self, mock_skill, tmp_path) -> None:
        """gated=True (noise) patterns must not reach the LLM."""
        ks = KnowledgeStore(path=tmp_path / "k.json")
        # 3 clean, 2 gated — all on the same axis so they'd otherwise cluster.
        for i in range(3):
            ks.add_learned_pattern(
                f"clean-{i}", embedding=_unit_vec(8, 1),
            )
        for i in range(2):
            ks.add_learned_pattern(
                f"noise-{i}", embedding=_unit_vec(8, 1), gated=True,
            )
        ks.save()
        mock_skill.return_value = GOOD_SKILL_RESPONSE

        result = extract_insight(knowledge_store=ks)
        assert isinstance(result, InsightResult)
        # Exactly one cluster formed from the 3 clean patterns.
        called_with = mock_skill.call_args_list
        assert len(called_with) == 1
        patterns_passed = called_with[0][0][0]
        assert set(patterns_passed) == {"clean-0", "clean-1", "clean-2"}


# ---------------------------------------------------------------------------
# _build_cluster_batches
# ---------------------------------------------------------------------------


class TestBuildClusterBatches:
    @staticmethod
    def _pat(text: str, embedding: list, importance: float = 0.5) -> dict:
        return {
            "pattern": text,
            "importance": importance,
            "embedding": embedding,
            "trust_score": 1.0,
        }

    def test_two_clusters_produce_two_batches(self) -> None:
        axis_a = [self._pat(f"a-{i}", _unit_vec(8, 1)) for i in range(3)]
        axis_b = [self._pat(f"b-{i}", _unit_vec(8, 2)) for i in range(3)]
        batches = _build_cluster_batches(axis_a + axis_b, threshold=0.7)
        assert len(batches) == 2
        names = {n for n, _ in batches}
        assert names == {"cluster-1", "cluster-2"}

    def test_gated_patterns_excluded_before_clustering(self) -> None:
        clean = [self._pat(f"c-{i}", _unit_vec(8, 1)) for i in range(3)]
        gated = [
            {**self._pat(f"g-{i}", _unit_vec(8, 1)), "gated": True}
            for i in range(2)
        ]
        batches = _build_cluster_batches(clean + gated, threshold=0.7)
        assert len(batches) == 1
        _, texts = batches[0]
        assert set(texts) == {"c-0", "c-1", "c-2"}

    def test_self_reflection_not_excluded(self) -> None:
        """Self-reflection patterns are *not* filtered out — the LLM can
        still derive a skill from them if the cluster holds together."""
        reflect = [
            self._pat(f"reflect-{i}", _unit_vec(8, 1),
                      importance=0.9) for i in range(3)
        ]
        batches = _build_cluster_batches(reflect, threshold=0.7)
        assert len(batches) == 1
        _, texts = batches[0]
        assert set(texts) == {"reflect-0", "reflect-1", "reflect-2"}

    def test_singletons_skipped(self) -> None:
        # All orthogonal → no cluster of size >= 3.
        orth = [self._pat(f"o-{i}", _unit_vec(8, i + 1)) for i in range(5)]
        batches = _build_cluster_batches(orth, threshold=0.7)
        assert batches == []

    def test_no_cluster_count_cap(self) -> None:
        """Every cluster ≥ min_size becomes a batch — no top-N cap.

        The natural cluster count is determined by CLUSTER_THRESHOLD; an
        artificial cap would drop semantically distinct groups on large
        corpora.
        """
        pats = []
        for axis in range(1, 13):
            pats.extend(self._pat(f"ax{axis}-{i}", _unit_vec(16, axis))
                        for i in range(3))
        batches = _build_cluster_batches(
            pats, threshold=0.7, min_size=3, max_size=10,
        )
        assert len(batches) == 12

    def test_clusters_ordered_by_size_times_importance(self) -> None:
        """Order: larger clusters first, ties broken by mean importance."""
        small_high = [
            self._pat(f"sh-{i}", _unit_vec(16, 1), importance=0.9)
            for i in range(3)
        ]
        large_mid = [
            self._pat(f"lm-{i}", _unit_vec(16, 2), importance=0.5)
            for i in range(6)
        ]
        batches = _build_cluster_batches(
            small_high + large_mid, threshold=0.7,
        )
        # large_mid: 6 × 0.5 = 3.0 > small_high: 3 × 0.9 = 2.7
        _, first_texts = batches[0]
        assert any(t.startswith("lm-") for t in first_texts)

    def test_cluster_batches_respect_max_size(self) -> None:
        pats = [
            self._pat(f"p-{i}", _unit_vec(8, 1), importance=0.9 - i * 0.05)
            for i in range(15)
        ]
        batches = _build_cluster_batches(
            pats, threshold=0.7, min_size=3, max_size=10,
        )
        assert len(batches) == 1
        _, texts = batches[0]
        assert len(texts) == 10


class TestExtractInsightSupersededExclusion:
    """N2: extract_insight must skip patterns whose valid_until is set."""

    def test_superseded_patterns_excluded(self, tmp_path: Path) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.json")
        for i in range(3):
            ks.add_learned_pattern(f"live-{i}", embedding=_unit_vec(8, 1))
        for i in range(2):
            ks.add_learned_pattern(
                f"dead-{i}", embedding=_unit_vec(8, 1),
                valid_until="2020-01-01T00:00:00+00:00",
            )
        ks.save()

        seen_batches = []

        def fake_build(raw_patterns, **_kwargs):
            seen_batches.append([p["pattern"] for p in raw_patterns])
            return []

        with patch(
            "contemplative_agent.core.insight._build_cluster_batches",
            side_effect=fake_build,
        ):
            result = extract_insight(knowledge_store=ks)

        # extract_insight returns an informational string when no batches produce skills.
        assert isinstance(result, str)
        assert seen_batches, "expected _build_cluster_batches to be called"
        # Only live patterns reach batching.
        assert set(seen_batches[0]) == {"live-0", "live-1", "live-2"}
