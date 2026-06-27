"""Tests for core.insight — global-cluster behavioral skill extraction."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.core.insight import (
    FULL_RECLUSTER_WARN_N,
    InsightResult,
    _build_cluster_batches,
    _extract_skill,
    _select_patterns,
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
        result = _extract_skill(["p1", "p2"])
        assert result is not None
        assert "# Ask Before Reacting" in result

    @patch("contemplative_agent.core.insight.generate")
    def test_llm_failure(self, mock_generate) -> None:
        mock_generate.return_value = None
        assert _extract_skill(["p1"]) is None

    @patch("contemplative_agent.core.insight.generate")
    def test_no_title_returns_none(self, mock_generate) -> None:
        mock_generate.return_value = "some text without a title line"
        assert _extract_skill(["p1"]) is None

    @patch("contemplative_agent.core.insight.generate")
    def test_passes_topic_to_prompt(self, mock_generate) -> None:
        mock_generate.return_value = GOOD_SKILL_RESPONSE
        _extract_skill(["p1"], topic="cluster-1")
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
            _extract_skill(["p1"])
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


class TestFullReclusterWarning:
    """M4 (review 2026-06-27): insight --full reclusters the whole live pool
    through the naive ~O(N^3) agglomerative merge, so a warning fires past a
    measured threshold; small pools stay quiet."""

    @staticmethod
    def _ks(n: int) -> MagicMock:
        ks = MagicMock()
        ks.get_live_patterns.return_value = [
            {"pattern": f"p{i}"} for i in range(n)
        ]
        return ks

    def test_warns_when_full_pool_large(self, caplog) -> None:
        import logging as _logging

        ks = self._ks(FULL_RECLUSTER_WARN_N + 1)
        with caplog.at_level(
            _logging.WARNING, logger="contemplative_agent.core.insight"
        ):
            patterns = _select_patterns(ks, None, full=True)
        assert len(patterns) == FULL_RECLUSTER_WARN_N + 1
        assert "may be slow" in caplog.text

    def test_no_warning_for_small_full_pool(self, caplog) -> None:
        import logging as _logging

        ks = self._ks(3)
        with caplog.at_level(
            _logging.WARNING, logger="contemplative_agent.core.insight"
        ):
            _select_patterns(ks, None, full=True)
        assert "may be slow" not in caplog.text


class TestBuildClusterBatches:
    @staticmethod
    def _pat(text: str, embedding: list, days_old: float = 0.0) -> dict:
        # ADR-0056: ordering is effective_importance = pure time decay, so the
        # pattern's age (days_old) — not a stored rating — drives the slice.
        distilled = (
            datetime.now(timezone.utc) - timedelta(days=days_old)
        ).isoformat()
        return {
            "pattern": text,
            "distilled": distilled,
            "embedding": embedding,
        }

    def test_two_clusters_produce_two_batches(self) -> None:
        axis_a = [self._pat(f"a-{i}", _unit_vec(8, 1)) for i in range(3)]
        axis_b = [self._pat(f"b-{i}", _unit_vec(8, 2)) for i in range(3)]
        batches = _build_cluster_batches(axis_a + axis_b, threshold=0.7)
        assert len(batches) == 2
        names = {b[0] for b in batches}
        assert names == {"cluster-1", "cluster-2"}

    def test_gated_patterns_excluded_before_clustering(self) -> None:
        clean = [self._pat(f"c-{i}", _unit_vec(8, 1)) for i in range(3)]
        gated = [
            {**self._pat(f"g-{i}", _unit_vec(8, 1)), "gated": True}
            for i in range(2)
        ]
        batches = _build_cluster_batches(clean + gated, threshold=0.7)
        assert len(batches) == 1
        _, texts, _ = batches[0]
        assert set(texts) == {"c-0", "c-1", "c-2"}

    def test_self_reflection_not_excluded(self) -> None:
        """Self-reflection patterns are *not* filtered out — the LLM can
        still derive a skill from them if the cluster holds together."""
        reflect = [
            self._pat(f"reflect-{i}", _unit_vec(8, 1)) for i in range(3)
        ]
        batches = _build_cluster_batches(reflect, threshold=0.7)
        assert len(batches) == 1
        _, texts, _ = batches[0]
        assert set(texts) == {"reflect-0", "reflect-1", "reflect-2"}

    def test_singletons_skipped(self) -> None:
        # All orthogonal → no cluster of size >= 3.
        orth = [self._pat(f"o-{i}", _unit_vec(8, i + 1)) for i in range(5)]
        batches = _build_cluster_batches(orth, threshold=0.7)
        assert batches == []

    def test_dropped_singletons_are_logged(self, caplog) -> None:
        """M3 (review 2026-06-27): patterns that never cluster (plus demoted
        >max_size tails) are dropped from skill extraction. Their count and
        effective_importance distribution must be visible so a rare-singleton
        lane and floor can be decided from real data later. Visibility only —
        no lane/threshold is applied here."""
        import logging as _logging

        orth = [self._pat(f"o-{i}", _unit_vec(8, i + 1)) for i in range(5)]
        with caplog.at_level(
            _logging.INFO, logger="contemplative_agent.core.insight"
        ):
            batches = _build_cluster_batches(orth, threshold=0.7)
        assert batches == []
        assert "5 singleton" in caplog.text
        assert "effective_importance" in caplog.text

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

    def test_clusters_ordered_by_size_times_decay(self) -> None:
        """Order: cluster_size × mean(effective_importance). ADR-0056: the
        weight is pure decay, so a larger slightly-aged cluster still outranks
        a smaller fresh one as long as decay has not dropped too far."""
        small_fresh = [
            self._pat(f"sf-{i}", _unit_vec(16, 1), days_old=0.0)
            for i in range(3)
        ]
        large_aged = [
            self._pat(f"la-{i}", _unit_vec(16, 2), days_old=2.0)
            for i in range(6)
        ]
        batches = _build_cluster_batches(
            small_fresh + large_aged, threshold=0.7,
        )
        # large_aged: 6 × 0.95^2 ≈ 5.42 > small_fresh: 3 × 1.0 = 3.0
        _, first_texts, _ = batches[0]
        assert any(t.startswith("la-") for t in first_texts)

    def test_cluster_batches_respect_max_size(self) -> None:
        # p-0 newest, p-14 oldest — decay keeps the 10 freshest.
        pats = [
            self._pat(f"p-{i}", _unit_vec(8, 1), days_old=i * 0.5)
            for i in range(15)
        ]
        batches = _build_cluster_batches(
            pats, threshold=0.7, min_size=3, max_size=10,
        )
        assert len(batches) == 1
        _, texts, _ = batches[0]
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


# ---------------------------------------------------------------------------
# ADR-0050: approval lineage plumbing
# ---------------------------------------------------------------------------


class TestBuildClusterBatchesLineageADR0050:
    @staticmethod
    def _pat(text: str, embedding: list, days_old: float = 0.0) -> dict:
        # ADR-0056: age drives the kept/demoted slice (effective_importance is
        # pure decay), so vary distilled by days_old instead of a rating.
        distilled = (
            datetime.now(timezone.utc) - timedelta(days=days_old)
        ).isoformat()
        return {
            "pattern": text,
            "distilled": distilled,
            "embedding": embedding,
        }

    def test_batches_carry_pattern_ids(self) -> None:
        from contemplative_agent.core.knowledge_store import pattern_id

        pats = [self._pat(f"p-{i}", _unit_vec(8, 1)) for i in range(3)]
        batches = _build_cluster_batches(pats, threshold=0.7)
        assert len(batches) == 1
        _, texts, pids = batches[0]
        assert len(pids) == len(texts) == 3
        assert set(pids) == {pattern_id(p) for p in pats}

    def test_pattern_ids_kept_members_only(self) -> None:
        """Demoted tail beyond max_size must not be attributed."""
        from contemplative_agent.core.knowledge_store import pattern_id

        # p-0 newest, p-14 oldest — decay keeps the 10 freshest (ADR-0056).
        pats = [
            self._pat(f"p-{i}", _unit_vec(8, 1), days_old=i * 0.5)
            for i in range(15)
        ]
        batches = _build_cluster_batches(pats, threshold=0.7, min_size=3, max_size=10)
        assert len(batches) == 1
        _, texts, pids = batches[0]
        assert len(pids) == len(texts) == 10
        # Freshest 10 are kept; the 5 oldest are demoted.
        kept_expected = {pattern_id(p) for p in pats[:10]}
        assert set(pids) == kept_expected


class TestExtractInsightLineageADR0050:
    @patch("contemplative_agent.core.insight._extract_skill")
    def test_skill_result_carries_pattern_ids(self, mock_skill, knowledge_store) -> None:
        from contemplative_agent.core.knowledge_store import pattern_id

        mock_skill.return_value = GOOD_SKILL_RESPONSE
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, InsightResult)
        skill = result.skills[0]
        expected = {pattern_id(p) for p in knowledge_store.get_raw_patterns()}
        assert set(skill.pattern_ids) == expected

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_skill_result_carries_epistemic_counts(self, mock_skill, tmp_path) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.json")
        for i in range(2):
            ks.add_learned_pattern(
                f"self-{i}", embedding=_unit_vec(8, 1),
                provenance={"source_type": "self_reflection"},
            )
        ks.add_learned_pattern(
            "ext-0", embedding=_unit_vec(8, 1),
            provenance={"source_type": "external_reply"},
        )
        ks.save()
        mock_skill.return_value = GOOD_SKILL_RESPONSE

        result = extract_insight(knowledge_store=ks)
        assert isinstance(result, InsightResult)
        counts = result.skills[0].epistemic_counts
        assert counts == {"observed": 1, "generated": 2, "unknown": 0}

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_incremental_mode_still_carries_ids(self, mock_skill, tmp_path) -> None:
        """get_live_patterns_since path must plumb ids identically."""
        from contemplative_agent.core.insight import write_last_insight

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        write_last_insight(skills_dir)  # marker in the past relative to adds below
        ks = KnowledgeStore(path=tmp_path / "k.json")
        for i in range(3):
            ks.add_learned_pattern(
                f"new-{i}", embedding=_unit_vec(8, 1),
                distilled="2099-01-01T00:00+00:00",
            )
        ks.save()
        mock_skill.return_value = GOOD_SKILL_RESPONSE

        result = extract_insight(knowledge_store=ks, skills_dir=skills_dir)
        assert isinstance(result, InsightResult)
        assert len(result.skills[0].pattern_ids) == 3
