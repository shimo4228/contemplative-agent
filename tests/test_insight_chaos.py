"""Chaos fault-injection tests for the insight gates (ADR-0077).

TDD contract: these tests state the DESIRED guarded behavior first — the
token-bounded chunked novelty judge (grill 2026-07-18) must fail open per
BATCH, never collapse every cluster into one fail-open, and the fail-open
extraction cap must bound the blast radius of an unjudged batch. Steady
state is asserted through observable channels (the insight-novelty.jsonl
verdict field and greppable log reasons), not internal state.

Fault catalog rows exercised here:
- F-NOV-1 backend hard failure mid-run (NONE) → only that chunk fails open
- F-NOV-2 malformed judge output (SHAPE_VIOLATION) → fail_open_parse per chunk
- F-NOV-3 truncated judge output (TRUNCATED + drop_truncated) → fail_open_llm
- F-NOV-4 known-inventory budget overflow → fail_open_budget, no LLM call
- F-NOV-5 fail-open flood → extraction cap defers beyond the configured N
- F-ABSTAIN-* the in-band promotion abstain (bottom of file) — a decline is a
  verdict, a dead backend is a fault, and extraction is the only call per
  cluster (ADR-0097 retired the separate worth judge)

Determinism: explicit fault schedules only; the chunk split is forced by a
patched context window computed from the same token estimator the packer
uses (no magic numbers).
"""

from __future__ import annotations

import json
from unittest.mock import patch

from contemplative_agent.core import insight, insight_novelty
from contemplative_agent.core.llm import (
    BackendResult,
    _estimate_tokens,
    configure,
    reset_llm_config,
)
from tests.chaos import NONE, OK, SHAPE_VIOLATION, TRUNCATED, ChaosBackend

KNOWN = [("skill-a", "handles consensus friction")]


class NoveltyChaosBackend(ChaosBackend):
    """ChaosBackend whose OK responses carry the novelty-judge shape."""

    def _ok_text(self, idx: int) -> str:
        return json.dumps({"covered": []})


def _batches(n: int, size: int = 3):
    return [
        (
            f"cluster-{i}",
            [f"pattern {i}-{j} some behavioral text" for j in range(size)],
            tuple(f"id{i}-{j}" for j in range(size)),
        )
        for i in range(1, n + 1)
    ]


def _window_for_one_block(batches) -> int:
    """Context window that fits exactly one cluster block per judge call."""
    known_lines = insight_novelty._render_known_lines(KNOWN)
    max_block = max(
        _estimate_tokens(insight_novelty._cluster_block(topic, patterns) + "\n\n")
        for topic, patterns, _ in batches
    )
    return (
        insight_novelty._NOVELTY_OUTPUT_RESERVE
        + insight_novelty._novelty_fixed_tokens(known_lines)
        + max_block
    )


def _run_gate(schedule, batches, audit_path=None):
    """Run the chunked gate through a real generate_full + ChaosBackend."""
    window = _window_for_one_block(batches)
    reset_llm_config()
    configure(backend=NoveltyChaosBackend(schedule=list(schedule)))
    try:
        with patch.object(insight_novelty, "_NOVELTY_CTX_WINDOW", window):
            return insight_novelty._filter_novel_batches(batches, KNOWN, audit_path=audit_path)
    finally:
        reset_llm_config()


def _verdicts(audit_path):
    return [json.loads(line)["verdict"] for line in audit_path.read_text().splitlines()]


class TestPerChunkFailOpenIsolation:
    def test_backend_none_fails_open_one_chunk_only(self, tmp_path) -> None:
        audit = tmp_path / "insight-novelty.jsonl"
        result = _run_gate([OK, NONE, OK], _batches(3), audit_path=audit)
        assert len(result.novel) == 3  # OK chunks judged covered=[] → all novel
        assert result.fail_open_topics == frozenset({"cluster-2"})
        assert _verdicts(audit) == ["judged", "fail_open_llm", "judged"]

    def test_shape_violation_fails_open_parse(self, tmp_path) -> None:
        audit = tmp_path / "insight-novelty.jsonl"
        result = _run_gate([OK, SHAPE_VIOLATION], _batches(2), audit_path=audit)
        assert result.fail_open_topics == frozenset({"cluster-2"})
        assert _verdicts(audit) == ["judged", "fail_open_parse"]

    def test_truncated_output_fails_open_llm(self, tmp_path) -> None:
        # drop_truncated=True: a length-capped judge answer is unusable.
        audit = tmp_path / "insight-novelty.jsonl"
        result = _run_gate([TRUNCATED, OK], _batches(2), audit_path=audit)
        assert result.fail_open_topics == frozenset({"cluster-1"})
        assert _verdicts(audit) == ["fail_open_llm", "judged"]

    def test_all_faults_never_crash_and_keep_every_cluster(self, tmp_path) -> None:
        audit = tmp_path / "insight-novelty.jsonl"
        result = _run_gate([NONE, SHAPE_VIOLATION, TRUNCATED], _batches(3), audit_path=audit)
        assert len(result.novel) == 3
        assert result.fail_open_topics == frozenset({"cluster-1", "cluster-2", "cluster-3"})


class TestBudgetOverflowFailOpen:
    def test_known_overflow_writes_fail_open_budget_without_call(self, tmp_path) -> None:
        audit = tmp_path / "insight-novelty.jsonl"
        backend = NoveltyChaosBackend(schedule=[OK])
        reset_llm_config()
        configure(backend=backend)
        try:
            with patch.object(insight_novelty, "_NOVELTY_CTX_WINDOW", 1):
                result = insight_novelty._filter_novel_batches(_batches(2), KNOWN, audit_path=audit)
        finally:
            reset_llm_config()
        assert backend.calls == []  # no judge call was possible
        assert len(result.novel) == 2
        assert _verdicts(audit) == ["fail_open_budget"]


class TestFailOpenFloodCap:
    def test_cap_bounds_extraction_after_total_fail_open(self, tmp_path) -> None:
        """F-NOV-5: every chunk fails open (the 2026-07-18 shape) — the cap
        defers all but N clusters, with a review_budget_deferred record."""
        audit = tmp_path / "insight-novelty.jsonl"
        batches = _batches(4)
        result = _run_gate([NONE, NONE, NONE, NONE], batches, audit_path=audit)
        assert result.fail_open_topics == frozenset(b[0] for b in batches)
        kept = insight._apply_failopen_extraction_cap(
            list(result.novel),
            result.fail_open_topics,
            {},
            cap=2,
            audit_path=audit,
        )
        assert len(kept) == 2
        records = [json.loads(line) for line in audit.read_text().splitlines()]
        deferral = [r for r in records if r.get("reason") == "review_budget_deferred"]
        assert len(deferral) == 1
        assert deferral[0]["cap"] == 2
        assert len(deferral[0]["deferred"]) == 2


class TestOkPathStillWorksThroughBackend:
    def test_covered_verdict_via_backend_result(self, tmp_path) -> None:
        """A judged covered verdict flows through the real generate_full
        path (BackendResult → GenerationOutput → parse)."""

        class CoveredBackend(NoveltyChaosBackend):
            def generate(
                self, prompt, system, num_predict, format, *, temperature=1.0, think=False
            ):
                self.calls.append({"prompt": prompt})
                return BackendResult(text=json.dumps({"covered": ["cluster-1"]}))

        batches = _batches(1)
        reset_llm_config()
        configure(backend=CoveredBackend())
        try:
            result = insight_novelty._filter_novel_batches(batches, KNOWN, audit_path=None)
        finally:
            reset_llm_config()
        assert result.novel == ()
        assert result.skipped_known == 1


# ---------------------------------------------------------------------------
# In-band promotion abstain (ADR-0096 Decision 1, kept by ADR-0097) — fault column
# ---------------------------------------------------------------------------
#
# F-ABSTAIN-1 extraction declines in-band (OK text = token) → judged verdict, not a fault
# F-ABSTAIN-2 extraction backend hard failure (NONE)       → error string, window preserved
# F-ABSTAIN-3 extraction returns an untitled prose blob     → no_title fault, not a decline
#
# ADR-0097 retired the post-extraction worth judge, so the extraction call is
# the only LLM call per cluster: the schedule addresses it directly. Steady
# state is asserted through observable channels only: the reason token in the
# log line and the per-reason tally on InsightResult.


_CHAOS_SKILL = """---
name: chaos-candidate
description: "a candidate produced under fault injection"
origin: auto-extracted
---

# Chaos Candidate

**Context:** under fault injection

## Problem
The gate may fail.

## Solution
Fail open and say why.

## When to Use
Whenever the judge is unusable.
"""


class DecliningExtractionBackend(ChaosBackend):
    """Extraction that declines in-band on every OK call."""

    def _ok_text(self, idx: int) -> str:
        return "NOTHING-PROMOTABLE"


class ProducingExtractionBackend(ChaosBackend):
    def _ok_text(self, idx: int) -> str:
        return _CHAOS_SKILL


def _one_cluster_store(tmp_path):
    from contemplative_agent.core.memory import KnowledgeStore

    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(4):
        ks.add_learned_pattern(
            f"chaos pattern {i} long enough to clear the validity gate",
            embedding=[1.0, 0.0, 0.0, 0.0],
        )
    ks.save()
    return ks


def _run_insight(backend, tmp_path):
    reset_llm_config()
    configure(backend=backend)
    try:
        return insight.extract_insight(
            knowledge_store=_one_cluster_store(tmp_path), skills_dir=tmp_path, full=True
        )
    finally:
        reset_llm_config()


class TestInBandAbstainThroughBackend:
    def test_a_decline_is_a_verdict_not_a_fault(self, tmp_path) -> None:
        result = _run_insight(DecliningExtractionBackend(schedule=[OK]), tmp_path)
        assert not isinstance(result, str)
        assert result.skills == ()
        assert result.abstained[insight.ABSTAIN_NOTHING_PROMOTABLE] == 1
        assert (
            sum(c for r, c in result.abstained.items() if r in insight.FAULT_ABSTAIN_REASONS) == 0
        )

    def test_extraction_fault_never_reads_as_a_decline(self, tmp_path) -> None:
        """A dead backend must not be recorded as "nothing was worth
        promoting" — that is the whole point of the fault/verdict split."""
        result = _run_insight(ProducingExtractionBackend(schedule=[NONE]), tmp_path)
        assert isinstance(result, str)  # window preserved, marker not advanced

    def test_one_llm_call_per_cluster(self, tmp_path) -> None:
        """ADR-0097: no second judge call follows a produced skill."""
        backend = ProducingExtractionBackend(schedule=[OK])
        result = _run_insight(backend, tmp_path)
        assert not isinstance(result, str)
        assert len(result.skills) == 1
        assert len(backend.calls) == 1
