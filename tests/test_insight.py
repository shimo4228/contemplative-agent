"""Tests for core.insight — global-cluster behavioral skill extraction."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.core import insight_novelty
from contemplative_agent.core.artifact_extraction import (
    canonicalize_frontmatter_name,
    resolve_artifact_path,
)
from contemplative_agent.core.insight import (
    FULL_RECLUSTER_WARN_N,
    InsightResult,
    _build_cluster_batches,
    _extract_skill,
    _select_patterns,
    extract_insight,
    skill_theme,
)
from contemplative_agent.core.llm import GenerationOutput
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
# Frontmatter name canonicalization (one identity per staged skill)
# ---------------------------------------------------------------------------


# Same shape as GOOD_SKILL_RESPONSE, but the frontmatter name and the heading
# disagree — the divergence measured on the live store 2026-08-01.
DIVERGENT_NAME_RESPONSE = (
    "---\n"
    "name: trace-structural-authority\n"
    'description: "Trace where authority in a structure comes from"\n'
    "origin: auto-extracted\n"
    "---\n"
    "\n"
    "# Structure Authority Tracing\n"
    "\n"
    "**Context:** When a claim rests on an unnamed authority\n"
    "\n"
    "## Problem\n"
    "Authority claims stay unexamined\n"
    "\n"
    "## Solution\n"
    "Trace the claim to its source\n"
)


class TestCanonicalizeFrontmatterName:
    def test_rewrites_diverging_name_to_slug(self) -> None:
        out = canonicalize_frontmatter_name(DIVERGENT_NAME_RESPONSE, "structure-authority-tracing")
        assert skill_theme(out)[0] == "structure-authority-tracing"
        # Heading and the other scalars survive untouched.
        assert extract_title(out) == "Structure Authority Tracing"
        assert skill_theme(out)[1] == "Trace where authority in a structure comes from"
        assert "origin: auto-extracted" in out

    def test_inserts_name_when_frontmatter_lacks_one(self) -> None:
        text = '---\ndescription: "d"\n---\n\n# My Skill\n\nbody'
        out = canonicalize_frontmatter_name(text, "my-skill")
        assert skill_theme(out)[0] == "my-skill"
        assert skill_theme(out)[1] == "d"

    def test_body_without_frontmatter_is_unchanged(self) -> None:
        text = "# My Skill\n\nbody"
        assert canonicalize_frontmatter_name(text, "my-skill") == text

    def test_only_the_top_level_name_key_is_rewritten(self) -> None:
        """A ``name:`` nested inside a block scalar must survive.

        The rewrite is a regex, not a YAML parse, so pin the boundary it
        relies on: block-scalar content is indented, and the pattern is
        anchored at column 0 (findings F1.3 review).
        """
        text = (
            "---\n"
            "description: |\n"
            "  name: not the identity, prose inside a scalar\n"
            "name: stale-declared-name\n"
            "---\n"
            "\n"
            "# My Skill\n"
        )
        out = canonicalize_frontmatter_name(text, "my-skill")
        assert "  name: not the identity, prose inside a scalar" in out
        assert "name: stale-declared-name" not in out
        assert skill_theme(out)[0] == "my-skill"


class TestStagedSkillIdentityInvariant:
    @patch(
        "contemplative_agent.core.llm.generate_full",
        return_value=GenerationOutput(text=DIVERGENT_NAME_RESPONSE),
    )
    def test_declared_name_equals_filename_stem(self, _mock_generate, knowledge_store) -> None:
        """skill_theme(text)[0] == filename stem minus the date suffix."""
        result = extract_insight(knowledge_store=knowledge_store, full=True)
        assert isinstance(result, InsightResult)
        skill = result.skills[0]
        today = date.today().strftime("%Y%m%d")
        assert skill.filename == f"structure-authority-tracing-{today}.md"
        stem_without_date = Path(skill.filename).stem.removesuffix(f"-{today}")
        assert skill_theme(skill.text)[0] == stem_without_date

    def test_invariant_holds_for_every_file_a_store_is_written_with(self, tmp_path) -> None:
        """The finding specified the invariant over *every* file in the store,
        not one fresh candidate. Materialize a store through the real
        resolve + canonicalize path and walk all of it (findings F1.3 review).

        This guards the write path. Files already in the live store predate
        the canonicalization and are not repaired by it — that gap is tracked
        separately, not silently asserted away here.
        """
        headings_and_names = [
            ("Structure Authority Tracing", "trace-structural-authority"),
            ("Mapping Epistemic Boundaries", "articulate-epistemic-boundaries"),
            ("Deconstruct Foundational Claims", "cross-reference-foundational-claims"),
            ("Subjective Attention Calibration", "internal-process-audit"),
        ]
        for heading, declared in headings_and_names:
            body = (
                f'---\nname: {declared}\ndescription: "d"\norigin: auto-extracted\n---\n'
                f"\n# {heading}\n\nbody\n"
            )
            resolved = resolve_artifact_path(body, tmp_path, label="test")
            assert resolved is not None
            resolved.target_path.write_text(
                canonicalize_frontmatter_name(body, resolved.slug), encoding="utf-8"
            )

        written = sorted(tmp_path.glob("*.md"))
        assert len(written) == len(headings_and_names)
        today = date.today().strftime("%Y%m%d")
        for path in written:
            stem_without_date = path.stem.removesuffix(f"-{today}")
            declared_name = skill_theme(path.read_text(encoding="utf-8"))[0]
            assert declared_name == stem_without_date, f"{path.name} declares {declared_name}"


# ---------------------------------------------------------------------------
# _extract_skill
# ---------------------------------------------------------------------------


class TestExtractSkill:
    @patch("contemplative_agent.core.llm.generate_full")
    def test_returns_skill_text(self, mock_generate) -> None:
        mock_generate.return_value = GenerationOutput(text=GOOD_SKILL_RESPONSE)
        result = _extract_skill(["p1", "p2"])
        assert result is not None
        text, _thinking = result
        assert "# Ask Before Reacting" in text

    @patch("contemplative_agent.core.llm.generate_full")
    def test_llm_failure(self, mock_generate) -> None:
        mock_generate.return_value = None
        assert _extract_skill(["p1"]) is None

    @patch("contemplative_agent.core.llm.generate_full")
    def test_no_title_returns_none(self, mock_generate) -> None:
        mock_generate.return_value = GenerationOutput(text="some text without a title line")
        assert _extract_skill(["p1"]) is None

    @patch("contemplative_agent.core.llm.generate_full")
    def test_passes_topic_to_prompt(self, mock_generate) -> None:
        mock_generate.return_value = GenerationOutput(text=GOOD_SKILL_RESPONSE)
        _extract_skill(["p1"], topic="cluster-1")
        prompt_arg = mock_generate.call_args[0][0]
        assert "cluster-1" in prompt_arg

    @patch("contemplative_agent.core.llm.generate_full")
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
            mock_generate.return_value = GenerationOutput(text=GOOD_SKILL_RESPONSE)
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
        result = extract_insight(knowledge_store=ks, full=True)
        assert "Insufficient patterns" in str(result)

    @patch("contemplative_agent.core.llm.generate_full", return_value=None)
    def test_extraction_failure(self, mock_generate, knowledge_store) -> None:
        result = extract_insight(knowledge_store=knowledge_store, full=True)
        assert "Failed to extract" in str(result)
        mock_generate.assert_called_once()

    @patch(
        "contemplative_agent.core.llm.generate_full",
        return_value=GenerationOutput(text=GOOD_SKILL_RESPONSE),
    )
    def test_returns_insight_result(self, mock_generate, knowledge_store) -> None:
        result = extract_insight(knowledge_store=knowledge_store, full=True)
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 1
        assert "# Ask Before Reacting" in result.skills[0].text
        today = date.today().strftime("%Y%m%d")
        assert result.skills[0].filename == f"ask-before-reacting-{today}.md"

    @patch("contemplative_agent.core.llm.generate_full")
    def test_gated_patterns_excluded(self, mock_generate, tmp_path) -> None:
        """gated=True (noise) patterns must not reach the LLM prompt."""
        ks = KnowledgeStore(path=tmp_path / "k.json")
        # 3 clean, 2 gated — all on the same axis so they'd otherwise cluster.
        for i in range(3):
            ks.add_learned_pattern(
                f"clean-{i}",
                embedding=_unit_vec(8, 1),
            )
        for i in range(2):
            ks.add_learned_pattern(
                f"noise-{i}",
                embedding=_unit_vec(8, 1),
                gated=True,
            )
        ks.save()

        prompts: list[str] = []

        def fake_generate(prompt, **kwargs):
            # Guard: the only expected LLM traffic is skill extraction (the
            # novelty gate stays silent with no known themes).
            assert kwargs.get("caller") == "insight.skill_extract"
            prompts.append(prompt)
            return GenerationOutput(text=GOOD_SKILL_RESPONSE)

        mock_generate.side_effect = fake_generate

        result = extract_insight(knowledge_store=ks, full=True)
        assert isinstance(result, InsightResult)
        # Exactly one cluster formed from the 3 clean patterns; the gated
        # ones are invisible at the LLM boundary.
        assert len(prompts) == 1
        for i in range(3):
            assert f"clean-{i}" in prompts[0]
        assert "noise-0" not in prompts[0]
        assert "noise-1" not in prompts[0]


# ---------------------------------------------------------------------------
# _build_cluster_batches
# ---------------------------------------------------------------------------


class TestFullReclusterWarning:
    """--full past the measured threshold warns about the review-batch size
    (ADR-0074 reworded the M4 advisory: clustering is fast now, the cost
    that scales with the pool is the human review batch); small pools stay
    quiet."""

    @staticmethod
    def _ks(n: int) -> MagicMock:
        ks = MagicMock()
        ks.get_live_patterns.return_value = [{"pattern": f"p{i}"} for i in range(n)]
        return ks

    def test_warns_when_full_pool_large(self, caplog) -> None:
        import logging as _logging

        ks = self._ks(FULL_RECLUSTER_WARN_N + 1)
        with caplog.at_level(_logging.WARNING, logger="contemplative_agent.core.insight"):
            patterns = _select_patterns(ks, None, full=True)
        assert patterns is not None
        assert len(patterns) == FULL_RECLUSTER_WARN_N + 1
        assert "large first review batch" in caplog.text

    def test_no_warning_for_small_full_pool(self, caplog) -> None:
        import logging as _logging

        ks = self._ks(3)
        with caplog.at_level(_logging.WARNING, logger="contemplative_agent.core.insight"):
            _select_patterns(ks, None, full=True)
        assert "large first review batch" not in caplog.text


class TestBuildClusterBatches:
    @staticmethod
    def _pat(text: str, embedding: list, days_old: float = 0.0) -> dict:
        # ADR-0056: ordering is effective_importance = pure time decay, so the
        # pattern's age (days_old) — not a stored rating — drives the slice.
        distilled = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
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
        gated = [{**self._pat(f"g-{i}", _unit_vec(8, 1)), "gated": True} for i in range(2)]
        batches = _build_cluster_batches(clean + gated, threshold=0.7)
        assert len(batches) == 1
        _, texts, _ = batches[0]
        assert set(texts) == {"c-0", "c-1", "c-2"}

    def test_self_reflection_not_excluded(self) -> None:
        """Self-reflection patterns are *not* filtered out — the LLM can
        still derive a skill from them if the cluster holds together."""
        reflect = [self._pat(f"reflect-{i}", _unit_vec(8, 1)) for i in range(3)]
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
        with caplog.at_level(_logging.INFO, logger="contemplative_agent.core.insight"):
            batches = _build_cluster_batches(orth, threshold=0.7)
        assert batches == []
        assert "5 singleton" in caplog.text
        assert "effective_importance" in caplog.text

    def test_dropped_singletons_log_nearest_view_with_registry(self, caplog) -> None:
        """M3 follow-up: when a view registry is provided, each logged
        singleton also shows its nearest *consumed* view and cosine —
        visibility for the future rescue-lane decision, never a gate."""
        import logging as _logging

        import numpy as np

        class _Reg:
            def get(self, name):
                return None

            def get_centroid(self, name):
                if name == "self_reflection":
                    return np.asarray(_unit_vec(8, 1), dtype=np.float32)
                return None

        orth = [self._pat(f"o-{i}", _unit_vec(8, i + 1)) for i in range(5)]
        with caplog.at_level(_logging.INFO, logger="contemplative_agent.core.insight"):
            batches = _build_cluster_batches(orth, threshold=0.7, view_registry=_Reg())
        assert batches == []
        assert "view≈self_reflection" in caplog.text

    def test_no_cluster_count_cap(self) -> None:
        """Every cluster ≥ min_size becomes a batch — no top-N cap.

        The natural cluster count is determined by CLUSTER_THRESHOLD; an
        artificial cap would drop semantically distinct groups on large
        corpora.
        """
        pats = []
        for axis in range(1, 13):
            pats.extend(self._pat(f"ax{axis}-{i}", _unit_vec(16, axis)) for i in range(3))
        batches = _build_cluster_batches(
            pats,
            threshold=0.7,
            min_size=3,
            max_size=10,
        )
        assert len(batches) == 12

    def test_clusters_ordered_by_size_times_decay(self) -> None:
        """Order: cluster_size × mean(effective_importance). ADR-0056: the
        weight is pure decay, so a larger slightly-aged cluster still outranks
        a smaller fresh one as long as decay has not dropped too far."""
        small_fresh = [self._pat(f"sf-{i}", _unit_vec(16, 1), days_old=0.0) for i in range(3)]
        large_aged = [self._pat(f"la-{i}", _unit_vec(16, 2), days_old=2.0) for i in range(6)]
        batches = _build_cluster_batches(
            small_fresh + large_aged,
            threshold=0.7,
        )
        # large_aged: 6 × 0.95^2 ≈ 5.42 > small_fresh: 3 × 1.0 = 3.0
        _, first_texts, _ = batches[0]
        assert any(t.startswith("la-") for t in first_texts)

    def test_cluster_batches_respect_max_size(self) -> None:
        # p-0 newest, p-14 oldest — decay keeps the 10 freshest.
        pats = [self._pat(f"p-{i}", _unit_vec(8, 1), days_old=i * 0.5) for i in range(15)]
        batches = _build_cluster_batches(
            pats,
            threshold=0.7,
            min_size=3,
            max_size=10,
        )
        assert len(batches) == 1
        _, texts, _ = batches[0]
        assert len(texts) == 10


class TestExtractInsightSupersededExclusion:
    """N2: patterns whose valid_until is set must be invisible at the LLM
    boundary — live patterns cluster and extract normally, superseded ones
    never appear in the extraction prompt."""

    @patch("contemplative_agent.core.llm.generate_full")
    def test_superseded_patterns_excluded(self, mock_generate, tmp_path: Path) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.json")
        for i in range(3):
            ks.add_learned_pattern(f"live-{i}", embedding=_unit_vec(8, 1))
        for i in range(2):
            ks.add_learned_pattern(
                f"dead-{i}",
                embedding=_unit_vec(8, 1),
                valid_until="2020-01-01T00:00:00+00:00",
            )
        ks.save()

        prompts: list[str] = []

        def fake_generate(prompt, **kwargs):
            assert kwargs.get("caller") == "insight.skill_extract"
            prompts.append(prompt)
            return GenerationOutput(text=GOOD_SKILL_RESPONSE)

        mock_generate.side_effect = fake_generate

        result = extract_insight(knowledge_store=ks, full=True)

        # The 3 live patterns form one cluster and extract one skill; the
        # superseded ones never reach the prompt.
        assert isinstance(result, InsightResult)
        assert len(result.skills) == 1
        assert len(prompts) == 1
        for i in range(3):
            assert f"live-{i}" in prompts[0]
        assert "dead-0" not in prompts[0]
        assert "dead-1" not in prompts[0]


# ---------------------------------------------------------------------------
# ADR-0050: approval lineage plumbing
# ---------------------------------------------------------------------------


class TestBuildClusterBatchesLineageADR0050:
    @staticmethod
    def _pat(text: str, embedding: list, days_old: float = 0.0) -> dict:
        # ADR-0056: age drives the kept/demoted slice (effective_importance is
        # pure decay), so vary distilled by days_old instead of a rating.
        distilled = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
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
        pats = [self._pat(f"p-{i}", _unit_vec(8, 1), days_old=i * 0.5) for i in range(15)]
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

        mock_skill.return_value = (GOOD_SKILL_RESPONSE, None)
        result = extract_insight(knowledge_store=knowledge_store, full=True)
        assert isinstance(result, InsightResult)
        skill = result.skills[0]
        expected = {pattern_id(p) for p in knowledge_store.get_raw_patterns()}
        assert set(skill.pattern_ids) == expected

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_skill_result_carries_epistemic_counts(self, mock_skill, tmp_path) -> None:
        ks = KnowledgeStore(path=tmp_path / "k.json")
        for i in range(2):
            ks.add_learned_pattern(
                f"self-{i}",
                embedding=_unit_vec(8, 1),
                provenance={"source_type": "self_reflection"},
            )
        ks.add_learned_pattern(
            "ext-0",
            embedding=_unit_vec(8, 1),
            # ADR-0082 retired the observed kind — this tallies as unknown
            provenance={"source_type": "external_reply"},
        )
        ks.save()
        mock_skill.return_value = (GOOD_SKILL_RESPONSE, None)

        result = extract_insight(knowledge_store=ks, full=True)
        assert isinstance(result, InsightResult)
        counts = result.skills[0].epistemic_counts
        assert counts == {"generated": 2, "unknown": 1}

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
                f"new-{i}",
                embedding=_unit_vec(8, 1),
                distilled="2099-01-01T00:00+00:00",
            )
        ks.save()
        mock_skill.return_value = (GOOD_SKILL_RESPONSE, None)

        result = extract_insight(knowledge_store=ks, skills_dir=skills_dir)
        assert isinstance(result, InsightResult)
        assert len(result.skills[0].pattern_ids) == 3


class TestTruncationPolicyH1:
    """Bug-audit 2026-07-06 H1: skill extraction passes drop_truncated=True."""

    @patch("contemplative_agent.core.llm.generate_full", return_value=None)
    def test_extract_skill_drops_truncated(self, mock_generate) -> None:
        assert _extract_skill(["p1"]) is None
        assert mock_generate.call_args.kwargs["drop_truncated"] is True


# ---------------------------------------------------------------------------
# ADR-0074: marker guard — no silent full recluster
# ---------------------------------------------------------------------------


class TestMarkerGuardADR0074:
    """Missing .last_insight must refuse instead of silently processing all."""

    def test_no_marker_refuses_incremental(self, knowledge_store, skills_dir) -> None:
        result = extract_insight(knowledge_store=knowledge_store, skills_dir=skills_dir)
        assert isinstance(result, str)
        assert "--full" in result

    def test_no_skills_dir_refuses_incremental(self, knowledge_store) -> None:
        result = extract_insight(knowledge_store=knowledge_store)
        assert isinstance(result, str)
        assert "--full" in result

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_full_bypasses_marker_guard(self, mock_skill, knowledge_store, skills_dir) -> None:
        mock_skill.return_value = (GOOD_SKILL_RESPONSE, None)
        result = extract_insight(knowledge_store=knowledge_store, skills_dir=skills_dir, full=True)
        assert isinstance(result, InsightResult)

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_marker_present_runs_incremental(self, mock_skill, tmp_path) -> None:
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / ".last_insight").write_text("2020-01-01T00:00:00+00:00\n")
        ks = KnowledgeStore(path=tmp_path / "k.json")
        for i in range(3):
            ks.add_learned_pattern(f"new-{i}", embedding=_unit_vec(8, 1))
        ks.save()
        mock_skill.return_value = (GOOD_SKILL_RESPONSE, None)
        result = extract_insight(knowledge_store=ks, skills_dir=skills_dir)
        assert isinstance(result, InsightResult)


# ---------------------------------------------------------------------------
# ADR-0074: LLM novelty gate — skip clusters whose theme is already covered
# ---------------------------------------------------------------------------


class TestFilterNovelBatches:
    BATCHES = [
        ("cluster-1", ["p1", "p2", "p3"], ("id1", "id2", "id3")),
        ("cluster-2", ["q1", "q2", "q3"], ("id4", "id5", "id6")),
    ]
    KNOWN = [("skill-a", "handles consensus friction")]

    @patch("contemplative_agent.core.llm.generate_full")
    def test_covered_cluster_is_filtered(self, mock_generate) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text='{"covered": ["cluster-1"]}')
        result = _filter_novel_batches(self.BATCHES, self.KNOWN)
        assert [b[0] for b in result.novel] == ["cluster-2"]
        assert result.skipped_known == 1
        assert result.fail_open_topics == frozenset()

    @patch("contemplative_agent.core.llm.generate_full", return_value=None)
    def test_llm_failure_fails_open(self, _mock_generate) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        result = _filter_novel_batches(self.BATCHES, self.KNOWN)
        assert len(result.novel) == 2
        assert result.skipped_known == 0
        assert result.fail_open_topics == frozenset({"cluster-1", "cluster-2"})

    @patch("contemplative_agent.core.llm.generate_full")
    def test_unparseable_output_fails_open(self, mock_generate) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text="not json at all")
        result = _filter_novel_batches(self.BATCHES, self.KNOWN)
        assert len(result.novel) == 2
        assert result.skipped_known == 0
        assert result.fail_open_topics == frozenset({"cluster-1", "cluster-2"})

    @patch("contemplative_agent.core.llm.generate_full")
    def test_hallucinated_cluster_ids_ignored(self, mock_generate) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text='{"covered": ["cluster-9"]}')
        result = _filter_novel_batches(self.BATCHES, self.KNOWN)
        assert len(result.novel) == 2
        assert result.skipped_known == 0
        assert result.fail_open_topics == frozenset()

    @patch("contemplative_agent.core.llm.generate_full")
    def test_prompt_carries_known_themes_and_samples(self, mock_generate) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text='{"covered": []}')
        _filter_novel_batches(self.BATCHES, self.KNOWN)
        prompt = mock_generate.call_args.args[0]
        assert "skill-a" in prompt
        assert "handles consensus friction" in prompt
        assert "cluster-1" in prompt
        assert "p1" in prompt


class TestNoveltyChunking:
    """Token-bounded chunking (grill 2026-07-18): the judge prompt is split
    into budgeted batches instead of one unbounded call — the 2026-07-18
    weekly run assembled 40,074 input tokens against the 32,768 window and
    fail-opened all 117 clusters."""

    KNOWN = [("skill-a", "handles consensus friction")]

    @staticmethod
    def _batches(n: int, size: int = 3):
        return [
            (
                f"cluster-{i}",
                [f"pattern {i}-{j} some behavioral text" for j in range(size)],
                tuple(f"id{i}-{j}" for j in range(size)),
            )
            for i in range(1, n + 1)
        ]

    @staticmethod
    def _window_for_blocks(known, batches, n_blocks: int) -> int:
        """Context window sized to fit exactly ``n_blocks`` cluster blocks."""
        from contemplative_agent.core.insight_novelty import (
            _NOVELTY_OUTPUT_RESERVE,
            _cluster_block,
            _novelty_fixed_tokens,
            _render_known_lines,
        )
        from contemplative_agent.core.llm import _estimate_tokens

        known_lines = _render_known_lines(known)
        block_costs = sorted(
            _estimate_tokens(_cluster_block(topic, patterns) + "\n\n")
            for topic, patterns, _ in batches
        )
        budget = sum(block_costs[-n_blocks:]) if n_blocks else 0
        return _NOVELTY_OUTPUT_RESERVE + _novelty_fixed_tokens(known_lines) + budget

    @patch("contemplative_agent.core.llm.generate_full")
    def test_single_call_when_budget_fits(self, mock_generate) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text='{"covered": []}')
        result = _filter_novel_batches(self._batches(3), self.KNOWN)
        assert mock_generate.call_count == 1
        assert len(result.novel) == 3

    @patch("contemplative_agent.core.llm.generate_full")
    def test_splits_when_budget_forces_it(self, mock_generate) -> None:
        from contemplative_agent.core import insight_novelty

        batches = self._batches(3)
        window = self._window_for_blocks(self.KNOWN, batches, 1)
        mock_generate.return_value = GenerationOutput(text='{"covered": []}')
        with patch.object(insight_novelty, "_NOVELTY_CTX_WINDOW", window):
            result = insight_novelty._filter_novel_batches(batches, self.KNOWN)
        assert mock_generate.call_count == 3
        assert len(result.novel) == 3
        # Every chunk prompt carries the FULL known inventory but only its
        # own cluster block.
        for i, call in enumerate(mock_generate.call_args_list, start=1):
            prompt = call.args[0]
            assert "skill-a" in prompt
            assert f"cluster-{i}:" in prompt
            for j in range(1, 4):
                if j != i:
                    assert f"cluster-{j}:" not in prompt

    @patch("contemplative_agent.core.llm.generate_full")
    def test_packing_is_deterministic(self, mock_generate) -> None:

        batches = self._batches(5)
        window = self._window_for_blocks(self.KNOWN, batches, 2)
        mock_generate.return_value = GenerationOutput(text='{"covered": []}')
        with patch.object(insight_novelty, "_NOVELTY_CTX_WINDOW", window):
            insight_novelty._filter_novel_batches(batches, self.KNOWN)
            first = [c.args[0] for c in mock_generate.call_args_list]
            mock_generate.reset_mock()
            insight_novelty._filter_novel_batches(batches, self.KNOWN)
            second = [c.args[0] for c in mock_generate.call_args_list]
        assert first == second

    @patch("contemplative_agent.core.llm.generate_full")
    def test_chunk_failure_is_isolated(self, mock_generate) -> None:
        """One failed chunk fails open alone; judged chunks keep their
        verdicts (the 2026-07-18 failure mode collapsed ALL clusters into
        one fail-open)."""

        batches = self._batches(3)
        window = self._window_for_blocks(self.KNOWN, batches, 1)
        mock_generate.side_effect = [
            GenerationOutput(text='{"covered": ["cluster-1"]}'),
            None,
            GenerationOutput(text='{"covered": []}'),
        ]
        with patch.object(insight_novelty, "_NOVELTY_CTX_WINDOW", window):
            result = insight_novelty._filter_novel_batches(batches, self.KNOWN)
        assert [b[0] for b in result.novel] == ["cluster-2", "cluster-3"]
        assert result.skipped_known == 1
        assert result.fail_open_topics == frozenset({"cluster-2"})

    @patch("contemplative_agent.core.llm.generate_full")
    def test_covered_id_from_other_chunk_ignored(self, mock_generate) -> None:

        batches = self._batches(2)
        window = self._window_for_blocks(self.KNOWN, batches, 1)
        # Chunk 1 hallucinates coverage of a cluster living in chunk 2.
        mock_generate.side_effect = [
            GenerationOutput(text='{"covered": ["cluster-2"]}'),
            GenerationOutput(text='{"covered": []}'),
        ]
        with patch.object(insight_novelty, "_NOVELTY_CTX_WINDOW", window):
            result = insight_novelty._filter_novel_batches(batches, self.KNOWN)
        assert len(result.novel) == 2
        assert result.skipped_known == 0

    @patch("contemplative_agent.core.llm.generate_full")
    def test_known_overflow_fails_open_without_llm_call(self, mock_generate, tmp_path) -> None:
        """When the known inventory alone exhausts the budget, no judge call
        is possible — every cluster fails open with an audit reason (the
        quantitative trigger for a future retrieval design)."""
        import json as _json

        batches = self._batches(2)
        audit = tmp_path / "insight-novelty.jsonl"
        with patch.object(insight_novelty, "_NOVELTY_CTX_WINDOW", 1):
            result = insight_novelty._filter_novel_batches(batches, self.KNOWN, audit_path=audit)
        mock_generate.assert_not_called()
        assert len(result.novel) == 2
        assert result.fail_open_topics == frozenset({"cluster-1", "cluster-2"})
        records = [_json.loads(line) for line in audit.read_text().splitlines()]
        assert [r["verdict"] for r in records] == ["fail_open_budget"]
        assert records[0]["clusters"] == ["cluster-1", "cluster-2"]
        # Not part of the chunk sequence — a separate event type, so the
        # batch fields stay None instead of a misleading count (codex P2).
        assert records[0]["batch_index"] is None
        assert records[0]["batch_count"] is None

    def test_ctx_window_follows_smaller_injected_backend(self) -> None:
        """Packing must budget against the SAME window the generate preflight
        validates (codex P2): an injected backend advertising a smaller
        context_window lowers the packing budget; a larger one never raises
        it above the module ceiling."""
        from contemplative_agent.core.llm import configure, reset_llm_config

        class _TinyBackend:
            context_window = 4096
            model = "tiny"

            def generate(self, *a, **k):  # pragma: no cover - never called
                return None

        class _HugeBackend(_TinyBackend):
            context_window = 200_000

        assert insight_novelty._novelty_ctx_window() == insight_novelty._NOVELTY_CTX_WINDOW
        reset_llm_config()
        configure(backend=_TinyBackend())
        try:
            assert insight_novelty._novelty_ctx_window() == 4096
        finally:
            reset_llm_config()
        configure(backend=_HugeBackend())
        try:
            assert insight_novelty._novelty_ctx_window() == insight_novelty._NOVELTY_CTX_WINDOW
        finally:
            reset_llm_config()

    @patch("contemplative_agent.core.llm.generate_full")
    def test_oversized_cluster_gets_truncated_samples(self, mock_generate) -> None:
        """A cluster block that alone exceeds the budget is retried with
        truncated samples before failing open."""
        from contemplative_agent.core.insight_novelty import (
            _NOVELTY_OUTPUT_RESERVE,
            _cluster_block,
            _novelty_fixed_tokens,
            _render_known_lines,
        )
        from contemplative_agent.core.llm import _estimate_tokens

        batches = [
            (
                "cluster-1",
                ["x" * 300, "y" * 300, "z" * 300],
                ("id1", "id2", "id3"),
            )
        ]
        known_lines = _render_known_lines(self.KNOWN)
        full_cost = _estimate_tokens(_cluster_block("cluster-1", batches[0][1]) + "\n\n")
        truncated_cost = _estimate_tokens(
            _cluster_block(
                "cluster-1",
                batches[0][1],
                sample_n=insight_novelty._NOVELTY_TRUNCATED_SAMPLE_PER_CLUSTER,
                sample_chars=insight_novelty._NOVELTY_TRUNCATED_SAMPLE_CHARS,
            )
            + "\n\n"
        )
        assert truncated_cost < full_cost
        window = _NOVELTY_OUTPUT_RESERVE + _novelty_fixed_tokens(known_lines) + truncated_cost
        mock_generate.return_value = GenerationOutput(text='{"covered": []}')
        with patch.object(insight_novelty, "_NOVELTY_CTX_WINDOW", window):
            result = insight_novelty._filter_novel_batches(batches, self.KNOWN)
        assert mock_generate.call_count == 1
        prompt = mock_generate.call_args.args[0]
        assert "cluster-1" in prompt
        # Truncated to one sample of _NOVELTY_TRUNCATED_SAMPLE_CHARS chars.
        assert "x" * insight_novelty._NOVELTY_TRUNCATED_SAMPLE_CHARS in prompt
        assert "x" * (insight_novelty._NOVELTY_TRUNCATED_SAMPLE_CHARS + 1) not in prompt
        assert "y" * 10 not in prompt
        assert result.fail_open_topics == frozenset()


class TestFailopenExtractionCap:
    """Fail-open extraction cap (grill 2026-07-18): a review-budget circuit
    breaker. Applies ONLY to clusters that reached extraction unjudged
    (through a fail-open batch); judged-novel clusters are never deferred,
    so the cap is a blast-radius guard, not a quality filter."""

    @staticmethod
    def _batches(n: int, size: int = 3):
        return [
            (
                f"cluster-{i}",
                [f"p{i}-{j}" for j in range(size)],
                tuple(f"id{i}-{j}" for j in range(size)),
            )
            for i in range(1, n + 1)
        ]

    def test_empty_inputs_skip_the_gate(self) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        result = _filter_novel_batches([], [("skill-a", "d")])
        assert result.novel == ()
        assert result.skipped_known == 0
        assert result.fail_open_topics == frozenset()

    def test_deferral_audit_failure_never_breaks_cap(self, tmp_path) -> None:
        from contemplative_agent.core.insight import _apply_failopen_extraction_cap

        batches = self._batches(3)
        bad = tmp_path / "audit-as-dir"
        bad.mkdir()
        kept = _apply_failopen_extraction_cap(
            batches,
            frozenset(b[0] for b in batches),
            {},
            cap=1,
            audit_path=bad,
        )
        assert len(kept) == 1

    def test_under_cap_is_noop(self, tmp_path) -> None:
        from contemplative_agent.core.insight import _apply_failopen_extraction_cap

        batches = self._batches(3)
        audit = tmp_path / "insight-novelty.jsonl"
        kept = _apply_failopen_extraction_cap(
            batches,
            frozenset({"cluster-1", "cluster-2"}),
            {},
            cap=2,
            audit_path=audit,
        )
        assert kept == batches
        assert not audit.exists()

    def test_defers_beyond_cap_by_size_then_topic(self) -> None:
        from contemplative_agent.core.insight import _apply_failopen_extraction_cap

        batches = [
            ("cluster-1", ["a"] * 3, ("i1",)),
            ("cluster-2", ["b"] * 5, ("i2",)),
            ("cluster-3", ["c"] * 4, ("i3",)),
        ]
        kept = _apply_failopen_extraction_cap(
            batches,
            frozenset({"cluster-1", "cluster-2", "cluster-3"}),
            {},
            cap=2,
            audit_path=None,
        )
        # Largest two survive; cluster-1 (size 3) is deferred. Original
        # batch order is preserved for the survivors.
        assert [b[0] for b in kept] == ["cluster-2", "cluster-3"]

    def test_judged_novel_batches_never_deferred(self) -> None:
        from contemplative_agent.core.insight import _apply_failopen_extraction_cap

        batches = self._batches(4)
        # Only cluster-3 / cluster-4 came through a fail-open batch.
        kept = _apply_failopen_extraction_cap(
            batches,
            frozenset({"cluster-3", "cluster-4"}),
            {},
            cap=1,
            audit_path=None,
        )
        topics = [b[0] for b in kept]
        assert "cluster-1" in topics and "cluster-2" in topics
        assert len([t for t in topics if t in ("cluster-3", "cluster-4")]) == 1

    def test_importance_breaks_size_ties(self) -> None:
        from contemplative_agent.core.insight import _apply_failopen_extraction_cap

        batches = [
            ("cluster-1", ["a"] * 3, ("old",)),
            ("cluster-2", ["b"] * 3, ("new",)),
        ]
        patterns_by_id = {
            "old": {"distilled": "2020-01-01T00:00:00+00:00"},
            "new": {"distilled": "2026-07-18T00:00:00+00:00"},
        }
        kept = _apply_failopen_extraction_cap(
            batches,
            frozenset({"cluster-1", "cluster-2"}),
            patterns_by_id,
            cap=1,
            audit_path=None,
        )
        assert [b[0] for b in kept] == ["cluster-2"]

    def test_deferral_writes_audit_record(self, tmp_path) -> None:
        import json as _json

        from contemplative_agent.core.insight import _apply_failopen_extraction_cap

        batches = self._batches(3)
        audit = tmp_path / "insight-novelty.jsonl"
        _apply_failopen_extraction_cap(
            batches,
            frozenset({"cluster-1", "cluster-2", "cluster-3"}),
            {},
            cap=1,
            audit_path=audit,
        )
        records = [_json.loads(line) for line in audit.read_text().splitlines()]
        assert len(records) == 1
        rec = records[0]
        assert rec["reason"] == "review_budget_deferred"
        assert rec["cap"] == 1
        assert len(rec["deferred"]) == 2
        entry = rec["deferred"][0]
        assert set(entry) == {"topic", "size", "pattern_ids"}

    def test_cap_env_override(self, monkeypatch) -> None:
        from contemplative_agent.core.insight import (
            _DEFAULT_FAILOPEN_EXTRACTION_CAP,
            _failopen_extraction_cap,
        )

        monkeypatch.delenv("MOLTBOOK_INSIGHT_FAILOPEN_CAP", raising=False)
        assert _failopen_extraction_cap() == _DEFAULT_FAILOPEN_EXTRACTION_CAP
        monkeypatch.setenv("MOLTBOOK_INSIGHT_FAILOPEN_CAP", "5")
        assert _failopen_extraction_cap() == 5

    def test_cap_env_invalid_falls_back_with_warning(self, monkeypatch, caplog) -> None:
        import logging

        from contemplative_agent.core.insight import (
            _DEFAULT_FAILOPEN_EXTRACTION_CAP,
            _failopen_extraction_cap,
        )

        for bad in ("abc", "0", "-3"):
            monkeypatch.setenv("MOLTBOOK_INSIGHT_FAILOPEN_CAP", bad)
            with caplog.at_level(logging.WARNING, logger="contemplative_agent.core.insight"):
                assert _failopen_extraction_cap() == _DEFAULT_FAILOPEN_EXTRACTION_CAP
        assert caplog.text.count("MOLTBOOK_INSIGHT_FAILOPEN_CAP") == 3

    @patch("contemplative_agent.core.llm.generate_full", return_value=None)
    @patch("contemplative_agent.core.insight._extract_skill")
    def test_capped_failopen_run_extracts_at_most_cap(
        self, mock_skill, _mock_generate, monkeypatch, tmp_path
    ) -> None:
        """End to end: gate fail-open + cap=1 → exactly one extraction call;
        deferred clusters are never staged (and thus never enter the
        ledger, so they can resurface in later windows)."""
        monkeypatch.setenv("MOLTBOOK_INSIGHT_FAILOPEN_CAP", "1")
        skills_dir = tmp_path / "sk"
        skills_dir.mkdir()
        (skills_dir / "known.md").write_text(GOOD_SKILL_RESPONSE)
        ks = KnowledgeStore(path=tmp_path / "k.json")
        for axis in (1, 2, 3):
            for j in range(3):
                ks.add_learned_pattern(
                    f"axis {axis} pattern {j} behavioral observation",
                    embedding=_unit_vec(8, axis),
                )
        ks.save()
        mock_skill.return_value = (GOOD_SKILL_RESPONSE, None)
        result = extract_insight(knowledge_store=ks, skills_dir=skills_dir, full=True)
        assert isinstance(result, InsightResult)
        assert mock_skill.call_count == 1
        assert len(result.skills) == 1


class TestLoadKnownThemes:
    def test_reads_skill_frontmatter(self, tmp_path) -> None:
        from contemplative_agent.core.insight_novelty import _load_known_themes

        d = tmp_path / "skills"
        d.mkdir()
        (d / "a-skill.md").write_text(GOOD_SKILL_RESPONSE)
        themes = _load_known_themes(d, None)
        assert (
            "ask-before-reacting",
            "Ask clarifying questions before forming a response",
        ) in themes

    def test_falls_back_to_title_without_frontmatter(self, tmp_path) -> None:
        from contemplative_agent.core.insight_novelty import _load_known_themes

        d = tmp_path / "skills"
        d.mkdir()
        (d / "bare.md").write_text("# Bare Title\n\nBody only.\n")
        themes = _load_known_themes(d, None)
        assert any(name == "bare" or "Bare Title" in desc for name, desc in themes)

    def test_reads_staged_ledger(self, tmp_path) -> None:
        import json as json_mod

        from contemplative_agent.core.insight_novelty import _load_known_themes

        ledger = tmp_path / "insight-staged.jsonl"
        ledger.write_text(
            json_mod.dumps({"name": "staged-theme", "description": "previously staged"}) + "\n"
        )
        themes = _load_known_themes(None, ledger)
        assert ("staged-theme", "previously staged") in themes

    def test_dedups_by_name(self, tmp_path) -> None:
        import json as json_mod

        from contemplative_agent.core.insight_novelty import _load_known_themes

        d = tmp_path / "skills"
        d.mkdir()
        (d / "a-skill.md").write_text(GOOD_SKILL_RESPONSE)
        ledger = tmp_path / "insight-staged.jsonl"
        ledger.write_text(
            json_mod.dumps({"name": "ask-before-reacting", "description": "dup"}) + "\n"
        )
        themes = _load_known_themes(d, ledger)
        names = [n for n, _ in themes]
        assert names.count("ask-before-reacting") == 1


class TestNoveltyGateIntegration:
    @patch("contemplative_agent.core.llm.generate_full")
    @patch("contemplative_agent.core.insight._extract_skill")
    def test_all_covered_returns_empty_result_with_count(
        self, mock_skill, mock_generate, knowledge_store, tmp_path
    ) -> None:
        """When every cluster is known, no LLM extraction runs and the
        result is an InsightResult with zero skills and skipped_known set,
        so the caller can still advance the marker."""
        skills_dir = tmp_path / "sk"
        skills_dir.mkdir()
        (skills_dir / "known.md").write_text(GOOD_SKILL_RESPONSE)
        mock_generate.return_value = GenerationOutput(text='{"covered": ["cluster-1"]}')
        result = extract_insight(knowledge_store=knowledge_store, skills_dir=skills_dir, full=True)
        assert isinstance(result, InsightResult)
        assert result.skills == ()
        assert result.skipped_known == 1
        mock_skill.assert_not_called()

    @patch("contemplative_agent.core.insight._extract_skill")
    def test_gate_skipped_when_no_known_themes(self, mock_skill, knowledge_store, tmp_path) -> None:
        """Empty skills dir + no ledger → no novelty LLM call, batches flow
        straight to extraction."""
        skills_dir = tmp_path / "sk"
        skills_dir.mkdir()
        mock_skill.return_value = (GOOD_SKILL_RESPONSE, None)
        with patch("contemplative_agent.core.llm.generate_full") as mock_generate:
            result = extract_insight(
                knowledge_store=knowledge_store, skills_dir=skills_dir, full=True
            )
        assert isinstance(result, InsightResult)
        mock_generate.assert_not_called()


class TestNoveltyGateAudit:
    """ADR-0075: the covered→drop judgment must be replayable offline —
    insight-novelty.jsonl stores the exact judge prompt and raw output as
    base64 + sha256."""

    BATCHES = [
        ("cluster-1", ["p1", "p2", "p3"], ("id1", "id2", "id3")),
        ("cluster-2", ["q1", "q2", "q3"], ("id4", "id5", "id6")),
    ]
    KNOWN = [("skill-a", "handles consensus friction")]

    @staticmethod
    def _records(path):
        import json as _json

        return [_json.loads(line) for line in path.read_text().splitlines()]

    @patch("contemplative_agent.core.llm.generate_full")
    def test_judged_run_writes_replayable_record(self, mock_generate, tmp_path) -> None:
        import base64 as _base64
        import json as _json

        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text='{"covered": ["cluster-1"]}')
        audit = tmp_path / "insight-novelty.jsonl"
        result = _filter_novel_batches(self.BATCHES, self.KNOWN, audit_path=audit)
        assert result.skipped_known == 1
        records = self._records(audit)
        assert len(records) == 1
        rec = records[0]
        assert rec["verdict"] == "judged"
        assert rec["covered"] == ["cluster-1"]
        assert rec["clusters"] == ["cluster-1", "cluster-2"]
        assert rec["known_themes_count"] == 1
        assert rec["batch_index"] == 0
        assert rec["batch_count"] == 1
        prompt = _base64.b64decode(rec["prompt_b64"]).decode("utf-8")
        assert "skill-a" in prompt and "cluster-1" in prompt
        assert rec["prompt_truncated"] is False
        output = _base64.b64decode(rec["output_b64"]).decode("utf-8")
        assert _json.loads(output) == {"covered": ["cluster-1"]}

    @patch("contemplative_agent.core.llm.generate_full", return_value=None)
    def test_llm_failure_writes_fail_open_record(self, _mock_generate, tmp_path) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        audit = tmp_path / "insight-novelty.jsonl"
        result = _filter_novel_batches(self.BATCHES, self.KNOWN, audit_path=audit)
        assert len(result.novel) == 2
        rec = self._records(audit)[0]
        assert rec["verdict"] == "fail_open_llm"
        assert rec["output_b64"] is None
        assert rec["covered"] == []

    @patch("contemplative_agent.core.llm.generate_full")
    def test_unparseable_writes_fail_open_parse(self, mock_generate, tmp_path) -> None:
        import base64 as _base64

        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text="not json at all")
        audit = tmp_path / "insight-novelty.jsonl"
        _filter_novel_batches(self.BATCHES, self.KNOWN, audit_path=audit)
        rec = self._records(audit)[0]
        assert rec["verdict"] == "fail_open_parse"
        assert _base64.b64decode(rec["output_b64"]).decode("utf-8") == "not json at all"

    @patch("contemplative_agent.core.llm.generate_full")
    def test_audit_write_failure_never_breaks_gate(self, mock_generate, tmp_path) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text='{"covered": []}')
        # A directory at the audit path forces the append to fail.
        bad = tmp_path / "audit-as-dir"
        bad.mkdir()
        result = _filter_novel_batches(self.BATCHES, self.KNOWN, audit_path=bad)
        assert len(result.novel) == 2
        assert result.skipped_known == 0

    @patch("contemplative_agent.core.llm.generate_full")
    def test_no_audit_path_writes_nothing(self, mock_generate, tmp_path) -> None:
        from contemplative_agent.core.insight_novelty import _filter_novel_batches

        mock_generate.return_value = GenerationOutput(text='{"covered": []}')
        result = _filter_novel_batches(self.BATCHES, self.KNOWN)
        assert len(result.novel) == 2
        assert list(tmp_path.iterdir()) == []
