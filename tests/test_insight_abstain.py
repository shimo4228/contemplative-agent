"""In-band promotion abstain for insight extraction (ADR-0096 Decision 1, kept by ADR-0097).

ADR-0096 opened two ways for a cluster to yield nothing on worth: the
extraction call declining in-band (``NOTHING-PROMOTABLE``) and a separate
post-extraction judge. ADR-0097 retired the judge after its own pre-registered
refutation fired (46/46 promote on the first production run); the in-band
channel, its reason code and the control-flow split are what remain and what
this file pins:

- a judged abstain carries its own reason code (``nothing_promotable``) and is
  tallied APART from the fault reasons — a routine week and a backend outage
  must never read the same;
- the yield line is always emitted and reports the judged abstain count;
- an all-abstain run is a verdict (marker-advancing empty result), while an
  all-fault run stays an error string so the window is not consumed;
- extraction is the only LLM call per cluster — no second judge call exists.
"""

from __future__ import annotations

import logging
from unittest.mock import patch

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

    def test_the_retired_judge_left_no_seam_behind(self) -> None:
        """ADR-0097: the post-extraction worth judge is gone, not dormant.

        A leftover opt-out env var or schema constant would invite a future
        call site to quietly revive a judge whose refutation is on record.
        """
        for name in ("_worth_gate", "_worthgate_enabled", "_WORTHGATE_ENV", "_WORTHGATE_SCHEMA"):
            assert not hasattr(insight, name), name


# ---------------------------------------------------------------------------
# _extract_skill: the generation call can decline
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
    def test_declined_cluster_is_tallied_as_the_verdict(
        self, mock_full, mock_gen, tmp_path, caplog
    ) -> None:
        mock_full.return_value = _gen("NOTHING-PROMOTABLE")
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
        # ADR-0097: extraction is the only LLM call per cluster.
        mock_gen.assert_not_called()

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_yield_line_always_reports_the_judged_abstain_count(
        self, mock_full, tmp_path, caplog
    ) -> None:
        mock_full.return_value = _gen("NOTHING-PROMOTABLE")
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
        with caplog.at_level(logging.INFO):
            result = insight.extract_insight(
                knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
            )
        assert not isinstance(result, str)
        assert len(result.skills) == 1
        assert "nothing_promotable=0" in caplog.text
        mock_gen.assert_not_called()

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_fault_only_run_stays_an_error_string(self, mock_full, tmp_path) -> None:
        """A backend outage must not consume the incremental window."""
        mock_full.return_value = None
        result = insight.extract_insight(
            knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
        )
        assert isinstance(result, str)

    @patch("contemplative_agent.core.insight.llm.generate_full")
    def test_all_declined_run_is_a_verdict_not_an_error(self, mock_full, tmp_path) -> None:
        """The window WAS considered, so the caller may advance the marker."""
        mock_full.return_value = _gen("NOTHING-PROMOTABLE")
        result = insight.extract_insight(
            knowledge_store=_store(tmp_path), skills_dir=tmp_path, full=True
        )
        assert not isinstance(result, str)
        assert result.skills == ()
