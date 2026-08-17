"""Promotion-worth abstain path for insight extraction (ADR-0096).

TDD contract: these tests state the desired behavior BEFORE the code exists.
ADR-0053 canonicalizes "promotion worth" as an insight-time LLM judgment, but
the implementation had no way to say no — ``_extract_skill`` dropped a cluster
only on an LLM failure or a missing title, so on 2026-07-25 all 84 surviving
clusters that produced a titled document became candidates and **none were
dropped on worth**.

What is asserted here mirrors the distill precedent (ADR-0084):

- a judged abstain carries its own reason code (``nothing_promotable``) and is
  tallied APART from the fault reasons — a routine week and a backend outage
  must never read the same;
- the yield line is always emitted and reports the judged abstain count;
- the worth gate fails OPEN with a greppable reason on every failure path;
- the gate is ON by default and ``MOLTBOOK_INSIGHT_WORTHGATE=0`` opts out,
  restoring the pre-ADR-0096 behavior exactly;
- an all-abstain run is a verdict (marker-advancing empty result), while an
  all-fault run stays an error string so the window is not consumed.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

import pytest

from contemplative_agent.core import insight
from contemplative_agent.core.llm import GenerationOutput

SKILL_TEXT = """---
name: pre-processing-state-validation
description: "Suspend the default frame before inquiry"
origin: auto-extracted
---

# Pre-Processing State Validation

**Context:** before an inquiry starts

## Problem
The default frame runs before it is chosen.

## Solution
Name the frame, then suspend it.

## When to Use
When a question arrives already framed.
"""


def _gen(text: str) -> GenerationOutput:
    return GenerationOutput(text=text, thinking=None)


@pytest.fixture(autouse=True)
def _worthgate_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo conftest's suite-wide opt-out — this file is where the gate runs."""
    monkeypatch.delenv(insight._WORTHGATE_ENV, raising=False)


# ---------------------------------------------------------------------------
# Reason codes
# ---------------------------------------------------------------------------


class TestReasonCodes:
    def test_judged_abstain_is_not_a_fault(self) -> None:
        assert insight.ABSTAIN_NOTHING_PROMOTABLE not in insight.FAULT_ABSTAIN_REASONS

    def test_every_fault_reason_is_distinct_from_the_verdict(self) -> None:
        assert insight.FAULT_ABSTAIN_REASONS == frozenset(
            {
                insight.ABSTAIN_LLM_NONE,
                insight.ABSTAIN_NO_TITLE,
                insight.ABSTAIN_FORBIDDEN_CONTENT,
                insight.ABSTAIN_PATH_UNRESOLVED,
            }
        )


# ---------------------------------------------------------------------------
# _extract_skill: the generation call can now decline
# ---------------------------------------------------------------------------


class TestExtractSkillAbstain:
    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_declining_output_returns_the_verdict_reason(self, mock_gen) -> None:
        mock_gen.return_value = _gen("NOTHING-PROMOTABLE")
        assert insight._extract_skill(["p1", "p2", "p3"]) == (insight.ABSTAIN_NOTHING_PROMOTABLE)

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_decoration_around_the_token_still_reads_as_a_verdict(self, mock_gen) -> None:
        mock_gen.return_value = _gen("**NOTHING-PROMOTABLE**\n")
        assert insight._extract_skill(["p1"]) == insight.ABSTAIN_NOTHING_PROMOTABLE

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_a_decline_under_its_own_heading_is_still_a_verdict(self, mock_gen) -> None:
        """The prompt's abstain section carries a heading, and a model that
        follows the template will echo it. Read as a fault, that decline would
        preserve the window and — if every cluster declined — turn a clean run
        into an error, which is the exact fault/verdict confusion this path
        exists to remove (code review 2026-08-17)."""
        mock_gen.return_value = _gen("## If there is no skill here\n\nNOTHING-PROMOTABLE\n")
        assert insight._extract_skill(["p1"]) == insight.ABSTAIN_NOTHING_PROMOTABLE

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_the_token_anywhere_in_a_titleless_output_reads_as_a_verdict(self, mock_gen) -> None:
        mock_gen.return_value = _gen("I am declining this one.\n\nNOTHING-PROMOTABLE")
        assert insight._extract_skill(["p1"]) == insight.ABSTAIN_NOTHING_PROMOTABLE

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_a_titled_skill_mentioning_the_token_is_not_a_decline(self, mock_gen) -> None:
        """A produced skill wins over a stray token: the title is the stronger
        signal, and misreading a real candidate as a decline loses material."""
        mock_gen.return_value = _gen(SKILL_TEXT + "\n\nNOTHING-PROMOTABLE\n")
        assert isinstance(insight._extract_skill(["p1"]), tuple)

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_llm_failure_is_a_fault_reason_not_the_verdict(self, mock_gen) -> None:
        mock_gen.return_value = None
        assert insight._extract_skill(["p1"]) == insight.ABSTAIN_LLM_NONE

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_untitled_output_is_a_fault_reason(self, mock_gen) -> None:
        mock_gen.return_value = _gen("no heading here")
        assert insight._extract_skill(["p1"]) == insight.ABSTAIN_NO_TITLE

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_a_real_skill_still_returns_text(self, mock_gen) -> None:
        mock_gen.return_value = _gen(SKILL_TEXT)
        out = insight._extract_skill(["p1"])
        assert isinstance(out, tuple)
        assert out[0].startswith("---")


# ---------------------------------------------------------------------------
# The worth gate itself (ADR-0084 shape: judge holds the artifact)
# ---------------------------------------------------------------------------


class TestWorthGate:
    @patch("contemplative_agent.core.insight.llm.generate")
    def test_promote_false_declines(self, mock_gen) -> None:
        mock_gen.return_value = '{"promote": false}'
        assert insight._worth_gate(SKILL_TEXT, ["p1", "p2"]) is False

    @patch("contemplative_agent.core.insight.llm.generate")
    def test_promote_true_keeps(self, mock_gen) -> None:
        mock_gen.return_value = '{"promote": true}'
        assert insight._worth_gate(SKILL_TEXT, ["p1"]) is True

    @patch("contemplative_agent.core.insight.llm.generate")
    def test_gate_sees_only_the_candidate_and_its_own_patterns(self, mock_gen) -> None:
        """Coverage against the adopted corpus is ADR-0074's novelty gate.
        Worth is intrinsic to the candidate, so the gate takes no corpus — a
        future parameter for one would be a second axis, not a bug fix."""
        import inspect

        params = inspect.signature(insight._worth_gate).parameters
        assert [p for p in params if params[p].kind is not params[p].KEYWORD_ONLY] == [
            "skill_text",
            "patterns",
        ]
        assert "corpus" not in params and "skills" not in params
        mock_gen.return_value = '{"promote": true}'
        insight._worth_gate(SKILL_TEXT, ["a distinguishing pattern text"])
        prompt = mock_gen.call_args.args[0]
        assert "pre-processing-state-validation" in prompt
        assert "a distinguishing pattern text" in prompt

    @pytest.mark.parametrize(
        ("response", "reason"),
        [
            (None, "worthgate_llm_none"),
            ("not json at all", "worthgate_parse"),
            ('{"promote": "maybe"}', "worthgate_shape"),
            ("[1, 2, 3]", "worthgate_shape"),
        ],
    )
    @patch("contemplative_agent.core.insight.llm.generate")
    def test_every_failure_path_fails_open_with_a_reason(
        self, mock_gen, response, reason, caplog
    ) -> None:
        mock_gen.return_value = response
        with caplog.at_level(logging.WARNING):
            assert insight._worth_gate(SKILL_TEXT, ["p1"]) is True
        assert f"reason={reason}" in caplog.text


class TestWorthGateDefault:
    """The production default must be ON — flipping it back cannot pass
    silently (ADR-0084 Decision 7 / TestPostGateDefault)."""

    def test_enabled_without_the_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(insight._WORTHGATE_ENV, raising=False)
        assert insight._worthgate_enabled() is True

    def test_zero_opts_out(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(insight._WORTHGATE_ENV, "0")
        assert insight._worthgate_enabled() is False

    def test_any_other_value_stays_on(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(insight._WORTHGATE_ENV, "1")
        assert insight._worthgate_enabled() is True


# ---------------------------------------------------------------------------
# Tally + yield line + control flow
# ---------------------------------------------------------------------------


def _store(tmp_path, n: int = 6):
    from contemplative_agent.core.memory import KnowledgeStore

    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(n):
        ks.add_learned_pattern(
            f"pattern {i} about naming the frame before inquiry",
            embedding=[1.0, 0.0, 0.0, 0.0],
        )
    ks.save()
    return ks


class TestAbstainTally:
    @patch("contemplative_agent.core.insight.llm.generate")
    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_gate_declined_cluster_is_tallied_as_the_verdict(
        self, mock_full, mock_gen, tmp_path, caplog
    ) -> None:
        mock_full.return_value = _gen(SKILL_TEXT)
        mock_gen.return_value = '{"promote": false}'
        with caplog.at_level(logging.INFO):
            result = insight.extract_insight(
                knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
            )
        assert not isinstance(result, str)
        assert result.skills == ()
        assert result.abstained[insight.ABSTAIN_NOTHING_PROMOTABLE] == 1
        assert (
            sum(c for r, c in result.abstained.items() if r in insight.FAULT_ABSTAIN_REASONS) == 0
        )

    @patch("contemplative_agent.core.insight.llm.generate")
    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_yield_line_always_reports_the_judged_abstain_count(
        self, mock_full, mock_gen, tmp_path, caplog
    ) -> None:
        mock_full.return_value = _gen(SKILL_TEXT)
        mock_gen.return_value = '{"promote": false}'
        with caplog.at_level(logging.INFO):
            insight.extract_insight(
                knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
            )
        assert "Insight extraction yield:" in caplog.text
        assert "nothing_promotable=1" in caplog.text

    @patch("contemplative_agent.core.insight.llm.generate")
    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_yield_line_is_emitted_on_a_clean_run_too(
        self, mock_full, mock_gen, tmp_path, caplog
    ) -> None:
        mock_full.return_value = _gen(SKILL_TEXT)
        mock_gen.return_value = '{"promote": true}'
        with caplog.at_level(logging.INFO):
            result = insight.extract_insight(
                knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
            )
        assert not isinstance(result, str)
        assert len(result.skills) == 1
        assert "nothing_promotable=0" in caplog.text

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_fault_only_run_stays_an_error_string(self, mock_full, tmp_path) -> None:
        """A backend outage must not consume the incremental window."""
        mock_full.return_value = None
        result = insight.extract_insight(
            knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
        )
        assert isinstance(result, str)

    @patch("contemplative_agent.core.insight.llm.generate")
    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_all_declined_run_is_a_verdict_not_an_error(
        self, mock_full, mock_gen, tmp_path
    ) -> None:
        """The window WAS considered, so the caller may advance the marker."""
        mock_full.return_value = _gen(SKILL_TEXT)
        mock_gen.return_value = '{"promote": false}'
        result = insight.extract_insight(
            knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
        )
        assert not isinstance(result, str)
        assert result.skills == ()


class TestOptOut:
    @patch("contemplative_agent.core.insight.llm.generate")
    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_opt_out_restores_the_previous_behavior(
        self, mock_full, mock_gen, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setenv(insight._WORTHGATE_ENV, "0")
        mock_full.return_value = _gen(SKILL_TEXT)
        mock_gen.return_value = '{"promote": false}'
        result = insight.extract_insight(
            knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
        )
        assert not isinstance(result, str)
        assert len(result.skills) == 1
        mock_gen.assert_not_called()


# ---------------------------------------------------------------------------
# Replay record (ADR-0075: the declined candidate's text survives nowhere else)
# ---------------------------------------------------------------------------


class TestWorthAudit:
    def _records(self, path):
        import json

        return [json.loads(line) for line in path.read_text().splitlines()]

    @patch("contemplative_agent.core.insight.llm.generate")
    def test_decline_is_recorded_with_prompt_and_output(self, mock_gen, tmp_path) -> None:
        mock_gen.return_value = '{"promote": false}'
        audit = tmp_path / "insight-worth.jsonl"
        insight._worth_gate(
            SKILL_TEXT, ["p1"], topic="cluster-1", pattern_ids=("abc",), audit_path=audit
        )
        (record,) = self._records(audit)
        assert record["verdict"] == "decline"
        assert record["topic"] == "cluster-1"
        assert record["pattern_ids"] == ["abc"]
        assert record["prompt_b64"] and record["output_b64"]
        assert record["prompt_sha256"]

    @patch("contemplative_agent.core.insight.llm.generate")
    def test_promote_is_recorded_too(self, mock_gen, tmp_path) -> None:
        """Only recording declines would make the log's own base rate unreadable."""
        mock_gen.return_value = '{"promote": true}'
        audit = tmp_path / "insight-worth.jsonl"
        insight._worth_gate(SKILL_TEXT, ["p1"], audit_path=audit)
        assert self._records(audit)[0]["verdict"] == "promote"

    @patch("contemplative_agent.core.insight.llm.generate")
    def test_fail_open_is_recorded_with_its_reason(self, mock_gen, tmp_path) -> None:
        mock_gen.return_value = None
        audit = tmp_path / "insight-worth.jsonl"
        insight._worth_gate(SKILL_TEXT, ["p1"], audit_path=audit)
        assert self._records(audit)[0]["verdict"] == "worthgate_llm_none"

    @patch("contemplative_agent.core.insight.llm.generate")
    def test_an_unwritable_audit_path_never_breaks_the_gate(self, mock_gen, tmp_path) -> None:
        mock_gen.return_value = '{"promote": false}'
        assert (
            insight._worth_gate(SKILL_TEXT, ["p1"], audit_path=tmp_path / "no" / "such" / "d.jsonl")
            is False
        )

    @patch("contemplative_agent.core.insight.llm.generate")
    def test_both_inputs_are_framed_as_untrusted(self, mock_gen) -> None:
        """The first insight-stage call whose output decides something."""
        mock_gen.return_value = '{"promote": true}'
        insight._worth_gate(SKILL_TEXT, ["a distinctive pattern"])
        prompt = mock_gen.call_args.args[0]
        assert prompt.count("untrusted_content") >= 4  # open + close, twice
