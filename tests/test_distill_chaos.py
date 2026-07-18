"""Chaos fault-injection tests for the distill pipeline (ADR-0077, F3 + F5).

TDD contract: these tests state the DESIRED guarded behavior first —
valid-JSON-wrong-shape output abstains with ``reason=shape_violation``
instead of silently degrading to a bullet scan of the JSON body, and every
per-episode failure carries a machine-greppable reason code (ADR-0075:
abstain with reason codes, no silent fallback).

Determinism: hypothesis runs under the ``ci`` profile registered in
conftest.py (derandomize, no example database); known failure shapes are
pinned with explicit ``@example`` decorators; schedule-driven tests use
explicit fault lists or seed-derived, circuit-safe schedules.
"""

from __future__ import annotations

import json
import logging
from unittest.mock import patch

import numpy as np
from hypothesis import example, given
from hypothesis import strategies as st

from contemplative_agent.core.distill import (
    ABSTAIN_EMPTY_RENDER,
    ABSTAIN_LLM_NONE,
    ABSTAIN_SHAPE_VIOLATION,
    _distill_episodes,
    _distill_one,
    _parse_patterns,
)
from contemplative_agent.core.llm import (
    CIRCUIT_FAILURE_THRESHOLD,
    configure,
    reset_llm_config,
)
from contemplative_agent.core.memory import KnowledgeStore

from tests.chaos import (
    EXC_TIMEOUT,
    LLM_NONE_FAULTS,
    NONE,
    OK,
    SHAPE_VIOLATION,
    TRUNCATED,
    ChaosBackend,
    fault_schedules,
    non_patterns_json,
    trips_circuit,
)


def _episode(idx: int = 0) -> dict:
    """One rich engagement episode record (mirrors test_distill._make_log)."""
    return {
        "ts": f"2026-07-13T10:{idx:02d}:00+00:00",
        "type": "activity",
        "data": {
            "action": "comment",
            "post_id": f"p{idx}",
            "original_post": "A post about quoting specific details in replies.",
            "content": "Quoting the exact phrase keeps the thread grounded and clear.",
            "internal_note": "Noticed they responded better to concrete quotes.",
        },
    }


def _distinct_embed(texts):
    n = len(texts)
    return np.array(
        [[1.0 if i == j else 0.0 for j in range(max(n, 4))] for i in range(n)],
        dtype=np.float32,
    )


# ---------------------------------------------------------------------------
# F3 — valid-JSON-wrong-shape must abstain, never bullet-scan the JSON body
# ---------------------------------------------------------------------------


class TestParsePatternsShapeViolationFuzz:
    """F3: ``_parse_patterns`` classifies parse outcomes explicitly.

    New contract: returns ``(patterns, parse_mode)`` with parse_mode in
    {"json", "bullet_fallback", "shape_violation"}. A syntactically valid
    JSON value that deviates from ``{"patterns": [str, ...]}`` is a
    ``shape_violation`` yielding NO patterns — previously it fell through
    to the bullet scanner, whose near-certain empty result was
    indistinguishable from a legitimate empty extraction.
    """

    @given(raw=non_patterns_json())
    @example(raw='["pattern one", "pattern two"]')
    @example(raw='"just a string"')
    @example(raw="42")
    @example(raw="null")
    @example(raw='{"patterns": "one long pattern string here"}')
    @example(raw='{"patterns": {"some dict key": "value"}}')
    @example(raw='{"patterns": [123]}')
    @example(raw='{"patterns": [null]}')
    @example(raw='{"patterns": ["valid string item", 123]}')
    def test_wrong_shape_abstains_with_no_patterns(self, raw):
        patterns, mode = _parse_patterns(raw)
        assert mode == "shape_violation"
        assert patterns == []

    @given(raw=st.text(max_size=300))
    @example(raw="- bullet one recovered from a non-JSON body\n- bullet two")
    @example(raw="")
    @example(raw="\x00\x1f weird control chars")
    def test_parse_never_raises_on_arbitrary_text(self, raw):
        patterns, mode = _parse_patterns(raw)
        assert mode in {"json", "bullet_fallback", "shape_violation"}
        assert all(isinstance(p, str) for p in patterns)

    def test_valid_shape_parses_as_json_mode(self):
        raw = json.dumps({"patterns": ["alpha pattern", "  beta  ", ""]})
        patterns, mode = _parse_patterns(raw)
        assert mode == "json"
        assert patterns == ["alpha pattern", "beta"]

    def test_non_json_body_keeps_bullet_fallback(self):
        # H2 guarantee unchanged: a backend that ignores format= and emits
        # bullets still yields patterns — but tagged as bullet_fallback.
        raw = "- first bullet pattern body\n- second bullet pattern body"
        patterns, mode = _parse_patterns(raw)
        assert mode == "bullet_fallback"
        assert patterns == ["first bullet pattern body", "second bullet pattern body"]


class TestDistillOneAbstainReasons:
    """F3/ADR-0075: ``_distill_one`` returns a reason code, not a bare None."""

    @patch("contemplative_agent.core.distill.generate")
    def test_shape_violation_reason(self, mock_generate, caplog):
        mock_generate.return_value = '["not", "the", "expected", "shape"]'
        with caplog.at_level(logging.WARNING, logger="contemplative_agent.core.distill"):
            result = _distill_one(_episode())
        assert result == ABSTAIN_SHAPE_VIOLATION
        assert "reason=shape_violation" in caplog.text

    @patch("contemplative_agent.core.distill.generate", return_value=None)
    def test_llm_none_reason(self, mock_generate, caplog):
        with caplog.at_level(logging.WARNING, logger="contemplative_agent.core.distill"):
            result = _distill_one(_episode())
        assert result == ABSTAIN_LLM_NONE
        assert "reason=llm_none" in caplog.text

    def test_empty_render_reason(self):
        with patch("contemplative_agent.core.episode_render.render_episode", return_value=""):
            assert _distill_one(_episode()) == ABSTAIN_EMPTY_RENDER

    @patch("contemplative_agent.core.distill.generate")
    def test_valid_output_still_returns_batch_output(self, mock_generate):
        mock_generate.return_value = json.dumps(
            {"patterns": ["A grounded pattern about quoting concrete details in replies"]}
        )
        out = _distill_one(_episode())
        assert not isinstance(out, str)
        assert out is not None
        assert len(out.patterns) == 1


# ---------------------------------------------------------------------------
# F5 — flapping backend: per-reason tally must match the fault schedule
# ---------------------------------------------------------------------------


def _run_schedule(schedule):
    """Run _distill_episodes over one episode per schedule entry."""
    records = [_episode(i) for i in range(len(schedule))]
    knowledge = KnowledgeStore()
    reset_llm_config()
    configure(backend=ChaosBackend(schedule=list(schedule)))
    try:
        with patch("contemplative_agent.core.distill.embed_texts", side_effect=_distinct_embed):
            return _distill_episodes(records, knowledge, None, dry_run=True)
    finally:
        reset_llm_config()


class TestFlappingBackendSchedule:
    def test_explicit_flapping_schedule_tally(self, caplog):
        schedule = [OK, NONE, OK, EXC_TIMEOUT, SHAPE_VIOLATION, TRUNCATED, OK]
        with caplog.at_level(logging.WARNING, logger="contemplative_agent.core.distill"):
            result = _run_schedule(schedule)

        # Successful episodes: exactly the OK entries.
        assert len(result.results) == schedule.count(OK)
        # Per-reason summary is machine-readable and matches the schedule:
        # NONE / EXC_TIMEOUT / TRUNCATED all surface as generate() -> None.
        assert "llm_none=3" in caplog.text
        assert "shape_violation=1" in caplog.text
        # Per-episode abstain lines carry greppable reason codes.
        assert caplog.text.count("reason=llm_none") == 3
        assert caplog.text.count("reason=shape_violation") == 1

    def test_alternating_failures_do_not_open_circuit(self):
        # Strict alternation never reaches CIRCUIT_FAILURE_THRESHOLD
        # consecutive failures, so every OK episode must succeed.
        schedule = [NONE, OK] * (CIRCUIT_FAILURE_THRESHOLD + 2)
        result = _run_schedule(schedule)
        assert len(result.results) == schedule.count(OK)

    @given(schedule=fault_schedules(min_size=1, max_size=10))
    @example(schedule=[OK, NONE, OK, EXC_TIMEOUT, SHAPE_VIOLATION, OK])
    @example(schedule=[SHAPE_VIOLATION] * 6)  # parse failures never open the circuit
    def test_success_count_always_matches_schedule(self, schedule):
        if trips_circuit(schedule, CIRCUIT_FAILURE_THRESHOLD):
            return  # circuit-opening schedules are covered by test_llm_chaos.py
        result = _run_schedule(schedule)
        assert len(result.results) == schedule.count(OK)


class TestEmbeddingShortRowsF2:
    """F2 (pipeline layer): an /api/embed response with fewer rows than
    requested texts parses fine at the HTTP layer — the distill tail must
    catch the length mismatch, store without embeddings (dedup degraded),
    and say so with a greppable reason token instead of crashing or
    misaligning pattern↔vector pairs."""

    def test_short_embed_rows_degrade_with_reason_token(self, caplog):
        import responses as responses_lib

        from tests.chaos import add_embed_short

        records = [_episode(i) for i in range(3)]
        knowledge = KnowledgeStore()
        reset_llm_config()
        configure(backend=ChaosBackend(schedule=[OK, OK, OK]))
        try:
            with responses_lib.RequestsMock() as rsps:
                add_embed_short(rsps, n_returned=1)
                with caplog.at_level(logging.WARNING, logger="contemplative_agent.core.distill"):
                    result = _distill_episodes(records, knowledge, None, dry_run=True)
        finally:
            reset_llm_config()

        assert len(result.results) == 3  # episodes themselves succeeded
        assert "reason=embed_failed" in caplog.text


class TestFlappingBackendProperties:
    @given(schedule=fault_schedules(min_size=1, max_size=10))
    def test_pipeline_never_crashes_on_any_schedule(self, schedule):
        # Even circuit-opening schedules must degrade, not raise.
        result = _run_schedule(schedule)
        assert result.added == 0  # dry_run stores nothing
        expected_llm_none = sum(1 for f in schedule if f in LLM_NONE_FAULTS)
        # Success count can only shrink below the schedule's OK count if the
        # circuit opened; it can never exceed it.
        assert len(result.results) <= schedule.count(OK)
        assert expected_llm_none <= len(schedule)
