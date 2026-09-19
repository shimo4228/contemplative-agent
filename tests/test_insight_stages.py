"""The naming and duplicate stages around insight extraction (RFC-0042 items 2-4).

What this file pins, stage by stage:

- the naming call stops a cluster on ``reconfirm`` / ``insufficient`` /
  ``revise`` and only lets ``new`` reach the body call — the whole point of
  the change is the volume reaching the Saturday gate;
- ``duplicate`` keeps a written candidate out of staging, ``distinct`` does
  not;
- every failure of either stage fails OPEN, with its own reason code in the
  audit log — a stage that cannot judge must never suppress;
- an off-enum or hallucinated answer is refused rather than trusted;
- the audit log stores prompt and output base64 + sha256 and keeps verdicts,
  reasons and the store names shown in plain text (ADR-0075).
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core import insight, insight_stages
from contemplative_agent.core.llm import GenerationOutput
from contemplative_agent.core.skill_projection import (
    PROJECTION_CLIP,
    SkillProjection,
    StoreIndex,
    project_skill,
)

NEAREST = (
    SkillProjection("ask-first", "Ask before reacting", "Ask a question", "On a new claim"),
    SkillProjection("cite-source", "Cite the source", "Name the source", "On a claim"),
)


def _gen(payload: dict) -> GenerationOutput:
    return GenerationOutput(text=json.dumps(payload))


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


# ---------------------------------------------------------------------------
# The projection both stages share
# ---------------------------------------------------------------------------


class TestSkillProjection:
    def test_reads_the_template_sections_when_they_exist(self) -> None:
        text = (
            '---\nname: ask-first\ndescription: "Ask before reacting"\n---\n\n'
            "# Ask First\n\n## Solution\nAsk a question.\n\n## When to Use\nOn a new claim.\n"
        )
        projection = project_skill(text)
        assert projection.name == "ask-first"
        assert projection.does == "Ask a question."
        assert projection.when == "On a new claim."

    def test_falls_back_to_the_body_head_for_a_free_form_body(self) -> None:
        """RFC-0024 bodies have no sections, and two empty fields would ask
        the judge to compare nothing."""
        text = '---\nname: ask-first\ndescription: "d"\n---\n\n# Ask First\n\nAsk a question.\n'
        projection = project_skill(text)
        assert projection.does == "Ask a question."
        assert projection.when == ""

    def test_sections_are_clipped_at_the_measured_width(self) -> None:
        text = "# T\n\n## Solution\n" + ("x" * (PROJECTION_CLIP + 50))
        assert len(project_skill(text).does) == PROJECTION_CLIP

    def test_an_unembeddable_store_yields_no_index(self, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text('---\nname: a\ndescription: "d"\n---\n\n# A\n\nbody\n')
        with patch(
            "contemplative_agent.core.skill_projection._embed_normalized", return_value=None
        ):
            assert StoreIndex.build(tmp_path) is None

    def test_an_empty_store_yields_no_index_without_embedding(self, tmp_path: Path) -> None:
        with patch("contemplative_agent.core.skill_projection._embed_normalized") as embed:
            assert StoreIndex.build(tmp_path) is None
        embed.assert_not_called()

    def test_a_store_skill_sharing_the_candidate_name_is_still_shown(self) -> None:
        """The nearest-k slice excludes nothing by name (code review 2026-09-19).

        The replay's leave-one-out arm skipped the candidate's own store row
        because there the candidate WAS that row. In production the candidate
        lives in staging and is never in this index, so a name match is a
        different skill that re-slugified the same way — the strongest
        duplicate evidence there is, and dropping it would stage exactly the
        recurrence this stage exists to catch.
        """
        import numpy as np

        index = StoreIndex(projections=NEAREST, vectors=np.eye(2))
        with patch(
            "contemplative_agent.core.skill_projection._embed_normalized",
            return_value=np.array([[1.0, 0.0]]),
        ):
            shown = index.nearest("anything", k=2)
        assert shown is not None
        assert [p.name for p in shown] == ["ask-first", "cite-source"]


# ---------------------------------------------------------------------------
# Stage 1: naming
# ---------------------------------------------------------------------------


class TestJudgeNaming:
    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_a_new_verdict_carries_its_evidence(self, mock_gen, tmp_path: Path) -> None:
        mock_gen.return_value = _gen(
            {
                "kind": "new",
                "target_skill": None,
                "change_reason": "no skill covers this",
                "evidence_ids": ["id-1"],
            }
        )
        log = tmp_path / "stages.jsonl"
        verdict = insight_stages.judge_naming(
            "cluster-1", ["obs one"], ("id-1",), NEAREST, audit_path=log
        )
        assert verdict is not None
        assert verdict.kind == "new"
        assert verdict.evidence_ids == ("id-1",)
        assert _records(log)[0]["verdict"] == "new"

    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_it_runs_at_temperature_zero_with_enum_constraints(self, mock_gen) -> None:
        mock_gen.return_value = _gen(
            {"kind": "new", "target_skill": None, "change_reason": "r", "evidence_ids": []}
        )
        insight_stages.judge_naming("cluster-1", ["obs"], ("id-1",), NEAREST)
        kwargs = mock_gen.call_args.kwargs
        assert kwargs["temperature"] == 0.0
        schema = kwargs["format"]["properties"]
        assert schema["kind"]["enum"] == ["reconfirm", "insufficient", "revise", "new"]
        assert schema["target_skill"]["enum"] == ["ask-first", "cite-source", None]
        assert schema["evidence_ids"]["items"]["enum"] == ["id-1"]

    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_a_target_outside_the_shown_slice_is_dropped(self, mock_gen) -> None:
        """A name the call was not shown cannot be revised — the same rule the
        novelty gate applies to hallucinated cluster ids."""
        mock_gen.return_value = _gen(
            {
                "kind": "revise",
                "target_skill": "a-skill-that-was-never-shown",
                "change_reason": "r",
                "evidence_ids": ["nope"],
            }
        )
        verdict = insight_stages.judge_naming("cluster-1", ["obs"], ("id-1",), NEAREST)
        assert verdict is not None
        assert verdict.target_skill is None
        assert verdict.evidence_ids == ()

    @pytest.mark.parametrize(
        ("output", "reason"),
        [
            (GenerationOutput(text="not json"), "unparseable"),
            (GenerationOutput(text=json.dumps({"kind": "maybe"})), "off_enum"),
            (None, "llm_none"),
        ],
    )
    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_every_failure_fails_open_with_a_reason(
        self, mock_gen, output, reason, tmp_path: Path
    ) -> None:
        mock_gen.return_value = output
        log = tmp_path / "stages.jsonl"
        assert (
            insight_stages.judge_naming("cluster-1", ["obs"], ("id-1",), NEAREST, audit_path=log)
            is None
        )
        record = _records(log)[0]
        assert record["verdict"] is None
        assert record["reason"] == reason

    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_no_store_slice_fails_open_without_a_call(self, mock_gen, tmp_path: Path) -> None:
        log = tmp_path / "stages.jsonl"
        assert insight_stages.judge_naming("c", ["obs"], ("id-1",), None, audit_path=log) is None
        mock_gen.assert_not_called()
        assert _records(log)[0]["reason"] == "no_store"


# ---------------------------------------------------------------------------
# Stage 2: the duplicate judge
# ---------------------------------------------------------------------------


CANDIDATE = SkillProjection("new-skill", "Something new", "Do it", "When it applies")


class TestJudgeDuplicate:
    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_a_duplicate_verdict_names_its_neighbour(self, mock_gen, tmp_path: Path) -> None:
        mock_gen.return_value = _gen({"verdict": "duplicate", "nearest": "ask-first"})
        log = tmp_path / "stages.jsonl"
        verdict = insight_stages.judge_duplicate(CANDIDATE, NEAREST, audit_path=log)
        assert verdict == insight_stages.DuplicateVerdict("duplicate", "ask-first")
        record = _records(log)[0]
        assert record["kind"] == insight_stages.DUPLICATE_RECORD_KIND
        assert record["store_shown"] == ["ask-first", "cite-source"]

    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_it_runs_at_temperature_zero_with_an_enum_verdict(self, mock_gen) -> None:
        mock_gen.return_value = _gen({"verdict": "distinct", "nearest": "ask-first"})
        insight_stages.judge_duplicate(CANDIDATE, NEAREST)
        kwargs = mock_gen.call_args.kwargs
        assert kwargs["temperature"] == 0.0
        assert kwargs["format"]["properties"]["verdict"]["enum"] == ["duplicate", "distinct"]
        assert kwargs["format"]["properties"]["nearest"]["enum"] == ["ask-first", "cite-source"]

    @pytest.mark.parametrize(
        ("output", "reason"),
        [
            (GenerationOutput(text="{"), "unparseable"),
            (GenerationOutput(text=json.dumps({"verdict": "same"})), "off_enum"),
            (None, "llm_none"),
        ],
    )
    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_every_failure_fails_open_with_a_reason(
        self, mock_gen, output, reason, tmp_path: Path
    ) -> None:
        mock_gen.return_value = output
        log = tmp_path / "stages.jsonl"
        assert insight_stages.judge_duplicate(CANDIDATE, NEAREST, audit_path=log) is None
        assert _records(log)[0]["reason"] == reason


# ---------------------------------------------------------------------------
# The audit log (ADR-0075)
# ---------------------------------------------------------------------------


class TestStageAudit:
    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_untrusted_text_is_stored_base64_and_hashed(self, mock_gen, tmp_path: Path) -> None:
        mock_gen.return_value = _gen({"verdict": "distinct", "nearest": "ask-first"})
        log = tmp_path / "stages.jsonl"
        insight_stages.judge_duplicate(CANDIDATE, NEAREST, audit_path=log)
        record = _records(log)[0]
        assert "Do it" not in json.dumps(record)  # never in plain text
        assert "Do it" in base64.b64decode(record["prompt_b64"]).decode("utf-8")
        assert len(record["prompt_sha256"]) == 64
        assert record["temperature"] == 0.0
        assert record["run_id"]  # stamped by the shared jsonl writer

    @patch("contemplative_agent.core.insight_stages.llm.generate_full")
    def test_an_unwritable_log_does_not_break_the_stage(self, mock_gen, tmp_path: Path) -> None:
        """An instrument may never break its host (read-only-instruments 3)."""
        mock_gen.return_value = _gen({"verdict": "distinct", "nearest": "ask-first"})
        unwritable = tmp_path / "a-file" / "stages.jsonl"
        (tmp_path / "a-file").write_text("not a directory")
        verdict = insight_stages.judge_duplicate(CANDIDATE, NEAREST, audit_path=unwritable)
        assert verdict is not None


# ---------------------------------------------------------------------------
# The stages inside the extraction path
# ---------------------------------------------------------------------------


def _one_cluster_store(tmp_path: Path):
    from contemplative_agent.core.memory import KnowledgeStore

    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(4):
        ks.add_learned_pattern(f"observation {i} long enough to clear the gate", embedding=[1.0])
    ks.save()
    return ks


def _run(tmp_path: Path, **patches):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir(exist_ok=True)
    return insight.extract_insight(
        knowledge_store=_one_cluster_store(tmp_path), skills_dir=skills_dir, full=True, **patches
    )


class TestRetrievalQuery:
    def test_the_naming_query_is_the_novelty_gate_cluster_block(self) -> None:
        """Both stages must retrieve against the same rendering of a cluster.

        If they diverge, the naming stage and the novelty gate disagree for a
        reason that has nothing to do with their inventories — and the
        divergence would be silent, since both still return five names.
        """
        from contemplative_agent.core import insight_novelty

        patterns = [f"observation {i}" for i in range(6)]
        assert insight._naming_query("cluster-1", patterns) == insight_novelty._cluster_block(
            "cluster-1", patterns
        )


class TestStagesInTheExtractionPath:
    @pytest.mark.parametrize(
        ("kind", "reason"),
        [
            ("reconfirm", insight.ABSTAIN_RECONFIRM),
            ("insufficient", insight.ABSTAIN_INSUFFICIENT),
            ("revise", insight.ABSTAIN_REVISE),
        ],
    )
    def test_a_non_new_naming_verdict_never_reaches_the_body_call(
        self, tmp_path: Path, kind, reason
    ) -> None:
        verdict = insight_stages.NamingVerdict(kind, "ask-first", "r", ())
        with (
            patch.object(insight.StoreIndex, "build", return_value=_FakeIndex()),
            patch.object(insight_stages, "judge_naming", return_value=verdict),
            patch.object(insight, "_extract_skill") as body,
        ):
            result = _run(tmp_path)
        body.assert_not_called()
        assert not isinstance(result, str)
        assert result.skills == ()
        assert result.abstained[reason] == 1
        # A judged stop is not a fault: the window is consumed, not preserved.
        assert result.fault_count == 0

    def test_a_new_verdict_lets_the_body_call_run(self, tmp_path: Path) -> None:
        verdict = insight_stages.NamingVerdict("new", None, "r", ())
        with (
            patch.object(insight.StoreIndex, "build", return_value=_FakeIndex()),
            patch.object(insight_stages, "judge_naming", return_value=verdict),
            patch.object(insight_stages, "judge_duplicate", return_value=None),
            patch.object(insight, "_extract_skill", return_value=(_SKILL, None)),
        ):
            result = _run(tmp_path)
        assert not isinstance(result, str)
        assert len(result.skills) == 1

    def test_a_duplicate_candidate_does_not_reach_staging(self, tmp_path: Path) -> None:
        with (
            patch.object(insight.StoreIndex, "build", return_value=_FakeIndex()),
            patch.object(insight_stages, "judge_naming", return_value=None),
            patch.object(
                insight_stages,
                "judge_duplicate",
                return_value=insight_stages.DuplicateVerdict("duplicate", "ask-first"),
            ),
            patch.object(insight, "_extract_skill", return_value=(_SKILL, None)),
        ):
            result = _run(tmp_path)
        assert not isinstance(result, str)
        assert result.skills == ()
        assert result.abstained[insight.ABSTAIN_DUPLICATE] == 1
        assert result.fault_count == 0

    def test_a_distinct_candidate_is_staged(self, tmp_path: Path) -> None:
        with (
            patch.object(insight.StoreIndex, "build", return_value=_FakeIndex()),
            patch.object(insight_stages, "judge_naming", return_value=None),
            patch.object(
                insight_stages,
                "judge_duplicate",
                return_value=insight_stages.DuplicateVerdict("distinct", "ask-first"),
            ),
            patch.object(insight, "_extract_skill", return_value=(_SKILL, None)),
        ):
            result = _run(tmp_path)
        assert not isinstance(result, str)
        assert len(result.skills) == 1

    def test_the_yield_line_names_every_verdict(self, tmp_path: Path, caplog) -> None:
        import logging

        verdict = insight_stages.NamingVerdict("reconfirm", "ask-first", "r", ())
        with (
            caplog.at_level(logging.INFO),
            patch.object(insight.StoreIndex, "build", return_value=_FakeIndex()),
            patch.object(insight_stages, "judge_naming", return_value=verdict),
        ):
            _run(tmp_path)
        for reason in insight.VERDICT_ABSTAIN_REASONS:
            assert f"{reason}=" in caplog.text


_SKILL = (
    '---\nname: new-skill\ndescription: "Something new"\norigin: auto-extracted\n---\n\n'
    "# New Skill\n\nDo it when it applies.\n"
)


class _FakeIndex:
    """A store index that always returns the same slice — no embedding calls."""

    def nearest(self, query: str, k: int = 5):
        return NEAREST
