"""Chaos fault-injection tests for the LLM layer (ADR-0077, F1 + F4 + F5 + F6 + F7).

HTTP-path faults (F1 read-timeout, F4 Ollama-side 429) are injected with the
``responses`` library on the URL the code under test actually resolves;
backend-path faults (F5 circuit sequences, F6 a misbehaving ``count_tokens``
capability, F7 a narrow output budget meeting a length-capped generation)
ride ``configure(backend=...)`` with a chaos backend. Steady
state is asserted on the telemetry channel (``outcome`` / ``error_kind`` in
``llm-calls-{date}.jsonl``) rather than implementation internals, per the
ADR-0075 doctrine that the audit log must answer "why did this call fail?"
offline.

Also carries the ChaosBackend self-tests (schedule determinism, Protocol
compliance) so tests/chaos.py has no untested logic.
"""

from __future__ import annotations

import json
import time

import pytest
import responses as responses_lib
from hypothesis import given, settings, strategies as st

from contemplative_agent.core.llm import (
    BACKEND_FRAMING_RESERVE,
    CIRCUIT_FAILURE_THRESHOLD,
    MIN_CLAMPED_NUM_PREDICT,
    LLMBackend,
    _circuit,
    configure,
    generate,
    generate_for_api,
    reset_llm_config,
)
from tests.chaos import (
    COUNT_EXC,
    COUNT_FAULT_REASONS,
    COUNT_IMPLAUSIBLE,
    COUNT_NEGATIVE,
    COUNT_NONE,
    COUNT_OK,
    COUNT_ZERO,
    EXC_CONNECTION,
    EXC_TIMEOUT,
    NONE,
    OK,
    SHAPE_VIOLATION,
    TRUNCATED,
    ChaosBackend,
    TokenCountingChaosBackend,
    add_generate_429,
    add_generate_timeout,
    real_token_count,
)
from tests.test_llm import PRE_20260801_CLAMP_FLOOR
from tests.test_llm_telemetry import _read_records


@pytest.fixture
def telemetry_dir(tmp_path):
    reset_llm_config()
    configure(telemetry_dir=tmp_path)
    yield tmp_path
    reset_llm_config()


@pytest.fixture
def no_sleep(monkeypatch):
    """Fail the test if anything sleeps — chaos tests must run in 0s wall time."""

    def _boom(seconds):
        raise AssertionError(f"unexpected time.sleep({seconds}) — fail-fast violated")

    monkeypatch.setattr(time, "sleep", _boom)


class TestChaosBackendSelfTest:
    """tests/chaos.py is itself test infrastructure — pin its contract."""

    def test_is_llmbackend(self):
        assert isinstance(ChaosBackend(), LLMBackend)

    def test_from_seed_is_deterministic(self):
        a = ChaosBackend.from_seed(42, 20)
        b = ChaosBackend.from_seed(42, 20)
        assert a.schedule == b.schedule
        assert len(a.schedule) == 20

    def test_ok_response_is_valid_patterns_json(self):
        backend = ChaosBackend(schedule=[OK])
        result = backend.generate("p", "s", 100, None)
        assert result is not None
        parsed = json.loads(result.text)
        assert isinstance(parsed["patterns"], list)
        assert all(isinstance(item, str) for item in parsed["patterns"])

    def test_calls_beyond_schedule_return_ok(self):
        backend = ChaosBackend(schedule=[NONE])
        assert backend.generate("p", "s", 100, None) is None
        assert backend.generate("p", "s", 100, None) is not None


class TestReadTimeoutF1:
    """F1: a mid-generation read timeout must fail fast and leave a
    distinguishable telemetry record (error_kind=timeout, not a generic
    outcome=error blob)."""

    @responses_lib.activate
    def test_generate_returns_none_and_records_timeout(self, telemetry_dir, no_sleep):
        add_generate_timeout(responses_lib.mock)

        result = generate("ping", system="s", caller="chaos.f1")

        assert result is None
        assert _circuit._consecutive_failures == 1
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "error"
        assert record["error_kind"] == "timeout"

    @responses_lib.activate
    def test_connection_error_records_connection(self, telemetry_dir, no_sleep):
        import requests as requests_mod

        responses_lib.add(
            responses_lib.POST,
            "http://127.0.0.1:1/api/generate",
            body=requests_mod.exceptions.ConnectionError("chaos: refused"),
        )

        assert generate("ping", system="s") is None
        assert _read_records(telemetry_dir)[0]["error_kind"] == "connection"


class TestOllama429F4:
    """F4: a 429 from Ollama itself is fail-fast by design — no retry, no
    Retry-After sleep (the circuit breaker is the recovery mechanism for a
    local daemon). This test pins that policy; adding backoff later must
    consciously invert it (ADR-0077 deferred list)."""

    @responses_lib.activate
    def test_429_fails_fast_without_sleeping(self, telemetry_dir, no_sleep):
        add_generate_429(responses_lib.mock, retry_after="60")

        result = generate("ping", system="s", caller="chaos.f4")

        assert result is None  # no retry loop swallowed it
        assert len(responses_lib.calls) == 1  # exactly one attempt
        assert _circuit._consecutive_failures == 1
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "error"
        assert record["error_kind"] == "http_429"

    @responses_lib.activate
    def test_500_records_http_500(self, telemetry_dir, no_sleep):
        responses_lib.add(
            responses_lib.POST,
            "http://127.0.0.1:1/api/generate",
            status=500,
            json={"error": "boom"},
        )

        assert generate("ping", system="s") is None
        assert _read_records(telemetry_dir)[0]["error_kind"] == "http_500"

    @responses_lib.activate
    def test_non_json_body_records_bad_json(self, telemetry_dir, no_sleep):
        responses_lib.add(
            responses_lib.POST,
            "http://127.0.0.1:1/api/generate",
            status=200,
            body="<html>not json</html>",
        )

        assert generate("ping", system="s") is None
        assert _read_records(telemetry_dir)[0]["error_kind"] == "bad_json"


class TestBackendFaultTelemetry:
    """Backend-path faults must be distinguishable in telemetry too."""

    def test_backend_exception_records_backend_exception(self, telemetry_dir):
        configure(backend=ChaosBackend(schedule=[EXC_TIMEOUT]))

        assert generate("ping", system="s") is None
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "error"
        assert record["error_kind"] == "backend_exception"

    def test_ok_record_has_no_error_kind(self, telemetry_dir):
        configure(backend=ChaosBackend(schedule=[OK]))

        assert generate("ping", system="s") is not None
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "ok"
        assert "error_kind" not in record  # sparse field: failure rows only


class TestTokenCounterFaults:
    """F6: the optional ``count_tokens`` capability misbehaves.

    A backend's tokenizer sits inside the C2 pre-flight, so its failure modes
    are budget-guard failure modes. The desired behavior for every one of them
    is the same: fall back to ``_estimate_tokens``, stamp a reason code, and
    keep guarding. The dangerous outcome is not a wrong number — it is a
    *trusted* wrong number, because under-counting sends over-window input
    into Ollama front-truncation / a memory-bounded backend's KV overrun,
    which is exactly what the guard exists to prevent (ADR-0066).
    """

    @staticmethod
    def _backend(count_schedule, *, window=32768):
        return TokenCountingChaosBackend(
            model="counting-model",
            context_window=window,
            count_schedule=list(count_schedule),
        )

    # Long enough on both halves that the ratio-based implausibility check can
    # express; the shape faults are length-independent.
    LONG = "x" * 3000

    @pytest.mark.parametrize("fault", sorted(COUNT_FAULT_REASONS))
    def test_every_count_fault_falls_back_with_its_reason(self, fault, telemetry_dir):
        # Both halves are measured before validation, so a single-entry
        # schedule breaks the system count and leaves the prompt count clean.
        configure(backend=self._backend([fault]))

        assert generate(self.LONG, system=self.LONG) is not None
        record = _read_records(telemetry_dir)[0]
        assert record["token_count_source"] == "estimator"
        assert record["token_count_fallback_reason"] == COUNT_FAULT_REASONS[fault]

    @pytest.mark.parametrize("fault", sorted(COUNT_FAULT_REASONS))
    def test_count_fault_never_records_a_circuit_failure(self, fault):
        """A tokenizer fault is not a generation fault. Scoring it would let
        a broken counter open the breaker and suppress healthy generation —
        the same reasoning that keeps over-budget skips off the breaker."""
        reset_llm_config()
        configure(backend=self._backend([fault]))
        try:
            generate(self.LONG, system=self.LONG)
            assert _circuit._consecutive_failures == 0
        finally:
            reset_llm_config()

    def test_implausibly_small_count_is_rejected(self, telemetry_dir):
        """A well-typed, positive, wildly-too-small count is the most likely
        real-world way this guard gets defeated — not malice but a
        mis-calibrated tokenizer in a sibling backend (wrong unit, wrong
        divisor). Shape validation alone accepts it, and the guard would then
        compute the budget as if the input were nearly free and send
        over-window input into the front-truncation / KV overrun it exists to
        prevent. Rejected by a chars-per-token ceiling no real tokenizer can
        clear (2026-08-01 security review)."""
        configure(backend=self._backend([COUNT_IMPLAUSIBLE, COUNT_IMPLAUSIBLE]))

        assert generate(self.LONG, system=self.LONG) is not None
        record = _read_records(telemetry_dir)[0]
        assert record["token_count_source"] == "estimator"
        assert record["token_count_fallback_reason"] == "counter_implausible"

    def test_compressible_text_is_not_mistaken_for_a_broken_counter(self):
        """The ceiling is a structural impossibility bound, not a calibration
        guess: a genuinely efficient tokenization of repetitive text must stay
        accepted. Rejecting it would only lose the headroom win, but it would
        also fill telemetry with faults that are not faults."""
        from contemplative_agent.core.llm import MAX_CHARS_PER_TOKEN, _measure_input_tokens

        text = "a" * 3000
        efficient = len(text) // (MAX_CHARS_PER_TOKEN - 1)  # just inside the ceiling

        class EfficientBackend:
            model = "efficient-model"
            context_window = 32768

            def count_tokens(self, text_arg):
                return efficient

            def generate(
                self, prompt, system, num_predict, format, *, temperature=1.0, think=False
            ):  # pragma: no cover - not reached
                raise AssertionError("generate() must not run here")

        reset_llm_config()
        configure(backend=EfficientBackend())  # type: ignore[arg-type]
        try:
            measurement = _measure_input_tokens(text, text)
            assert measurement.source == "backend"
            assert measurement.fallback_reason is None
        finally:
            reset_llm_config()

    @pytest.mark.parametrize("broken_index", [0, 1])
    def test_one_broken_half_estimates_both(self, broken_index, telemetry_dir):
        """Measurement is atomic. Mixing a measured system prompt with an
        estimated user prompt yields a budget that describes neither."""
        from contemplative_agent.core.llm import _estimate_tokens, _measure_input_tokens

        schedule = [COUNT_OK, COUNT_OK]
        schedule[broken_index] = COUNT_NONE
        configure(backend=self._backend(schedule))

        measurement = _measure_input_tokens("system text", "prompt text")
        assert measurement.source == "estimator"
        assert measurement.system == _estimate_tokens("system text")
        assert measurement.prompt == _estimate_tokens("prompt text")

    def test_first_failure_wins_the_reason_code(self, telemetry_dir):
        """Two different faults in one call report the system-side one — a
        stable, replayable choice rather than whichever ran last."""
        configure(backend=self._backend([COUNT_NEGATIVE, COUNT_NONE]))

        generate("ping", system="s")
        record = _read_records(telemetry_dir)[0]
        assert record["token_count_fallback_reason"] == "counter_negative"

    def test_broken_counter_does_not_disable_the_guard(self):
        """The fallback keeps the ceiling: an over-window prompt is still
        skipped when the counter is broken, using the estimator's verdict."""
        reset_llm_config()
        backend = self._backend([COUNT_EXC] * 2, window=4096)
        configure(backend=backend)
        try:
            assert generate("x" * 200000, system="s") is None
            assert backend.calls == []
        finally:
            reset_llm_config()

    def test_zero_is_accepted_for_blank_text(self):
        """0 is only degenerate for text with content — a blank string
        legitimately costs nothing, and rejecting it would make a
        whitespace-only half look like a broken tokenizer.

        Exercised at ``_measure_input_tokens`` rather than through
        ``generate()``: a falsy ``system=`` is replaced by the built system
        prompt during ``resolve()``, so a blank half never reaches the guard
        from that direction."""
        from contemplative_agent.core.llm import _measure_input_tokens

        reset_llm_config()
        configure(backend=self._backend([COUNT_ZERO, COUNT_OK]))
        try:
            measurement = _measure_input_tokens("   ", "ping")
            assert measurement.source == "backend"
            assert measurement.system == 0
            assert measurement.fallback_reason is None
        finally:
            reset_llm_config()

    @settings(max_examples=60, deadline=None)
    @given(
        value=st.one_of(
            st.booleans(),  # int subclass, but not a count
            st.text(max_size=8),
            st.floats(),  # incl. integral floats like 3.0
            st.lists(st.integers(), max_size=3),
        )
    )
    def test_no_non_int_return_is_ever_trusted(self, value):
        """Fuzz the capability's return type: nothing outside ``int`` may
        reach the budget arithmetic. ``None`` is excluded here only because
        it has its own reason code (covered by the parametrized cases)."""
        from contemplative_agent.core.llm import _estimate_tokens, _measure_input_tokens

        class FuzzBackend:
            model = "fuzz-model"
            context_window = 32768

            def count_tokens(self, text):
                return value

            def generate(
                self, prompt, system, num_predict, format, *, temperature=1.0, think=False
            ):  # pragma: no cover - never reached in this test
                raise AssertionError("generate() must not run here")

        reset_llm_config()
        configure(backend=FuzzBackend())  # type: ignore[arg-type]
        try:
            measurement = _measure_input_tokens("system", "prompt")
            assert measurement.source == "estimator"
            assert measurement.fallback_reason == "counter_type"
            assert measurement.system == _estimate_tokens("system")
        finally:
            reset_llm_config()


class TestCircuitSequencesF5:
    """F5 (circuit layer): sequences beyond the single-recovery case."""

    def test_alternating_failure_success_never_opens(self):
        reset_llm_config()
        schedule = [NONE, OK] * (CIRCUIT_FAILURE_THRESHOLD + 2)
        configure(backend=ChaosBackend(schedule=schedule))
        try:
            for fault in schedule:
                result = generate("p", system="s")
                assert (result is None) == (fault == NONE)
                assert not _circuit.is_open
        finally:
            reset_llm_config()

    def test_four_then_success_then_four_never_opens(self):
        reset_llm_config()
        n = CIRCUIT_FAILURE_THRESHOLD - 1
        schedule = [EXC_CONNECTION] * n + [OK] + [EXC_CONNECTION] * n
        configure(backend=ChaosBackend(schedule=schedule))
        try:
            for _ in schedule:
                generate("p", system="s")
                assert not _circuit.is_open
        finally:
            reset_llm_config()

    def test_five_consecutive_failures_open_and_short_circuit(self, telemetry_dir):
        backend = ChaosBackend(schedule=[EXC_TIMEOUT] * CIRCUIT_FAILURE_THRESHOLD)
        configure(backend=backend)

        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            generate("p", system="s")
        assert _circuit.is_open

        # Open circuit: the call never reaches the backend and telemetry
        # records circuit_open (no cooldown wait — observation stops here).
        calls_before = len(backend.calls)
        assert generate("p", system="s") is None
        assert len(backend.calls) == calls_before
        assert _read_records(telemetry_dir)[-1]["outcome"] == "circuit_open"

    def test_shape_violation_records_circuit_success(self):
        # Parse-layer failures are NOT backend faults: a wrong-shaped but
        # successful generation must not push the circuit toward open.
        reset_llm_config()
        configure(backend=ChaosBackend(schedule=[SHAPE_VIOLATION]))
        try:
            result = generate("p", system="s")
            assert result is not None  # generation succeeded; parsing is the caller's problem
            assert _circuit._consecutive_failures == 0
        finally:
            reset_llm_config()


class TestNarrowHeadroomTruncationF7:
    """F7: a narrow output budget meeting a length-capped generation.

    Lowering ``MIN_CLAMPED_NUM_PREDICT`` from 2048 to 128 retired a
    *prediction* ("a usable answer needs 2048 tokens") that was never
    validated and measured ~6x over (comment output p50 352 / p90 507,
    n=2,366). The floor keeps only its cheap job — refusing an absurd
    remainder — and the question "was this generation actually cut short?"
    moves downstream to the ``drop_truncated`` gate (audit M2), which
    measures instead of guessing.

    The behavior that changes is therefore *calls that used to be skipped now
    run*, and the failure mode they can newly reach is: clamped to a small
    budget, the model hits ``num_predict`` mid-sentence. This column asserts
    the desired guarded behavior on that path — the publish path drops the
    fragment rather than posting it, the drop is not scored as a backend
    fault, and the skip still fires below the new floor.
    """

    @staticmethod
    def _backend(window):
        return TokenCountingChaosBackend(
            model="counting-model",
            context_window=window,
            schedule=[TRUNCATED],
        )

    @staticmethod
    def _headroom(window, system, prompt):
        """The output budget the guard will compute for this input."""
        measured = real_token_count(system) + real_token_count(prompt)
        return window - measured - BACKEND_FRAMING_RESERVE

    def test_clamped_publish_path_drops_the_cut_fragment(self, telemetry_dir):
        """A call in the newly-opened band runs, is clamped to the real
        remainder, and — when the model hits that budget mid-sentence — is
        dropped by the M2 gate instead of published. Trying and measuring,
        where the old floor guessed and suppressed."""
        window, system = 4096, "s"
        prompt = "瞑" * 3210
        headroom = self._headroom(window, system, prompt)
        assert (
            MIN_CLAMPED_NUM_PREDICT <= headroom < PRE_20260801_CLAMP_FLOOR
        )  # the band that changed

        backend = self._backend(window)
        configure(backend=backend)
        out = generate_for_api(
            prompt, max_length=2000, system=system, chars_per_token=1.5, caller="test.f7"
        )

        assert out.text is None  # dropped, not posted mid-sentence
        assert len(backend.calls) == 1  # but the call WAS attempted (old floor: never reached)
        assert backend.calls[0]["num_predict"] == headroom

        record = _read_records(telemetry_dir)[-1]
        assert record["outcome"] == "truncated_dropped"  # a measured cut, not a predicted one
        assert record["num_predict_requested"] > headroom  # the clamp is still readable offline

    def test_the_truncation_drop_is_not_scored_as_a_backend_failure(self, telemetry_dir):
        """The call succeeded; only its output was unusable. Scoring it would
        let a run of narrow-headroom calls trip the breaker and suppress
        healthy generation — the suppression this change exists to remove."""
        window, system = 4096, "s"
        prompt = "瞑" * 3210
        backend = self._backend(window)
        configure(backend=backend)

        generate_for_api(prompt, max_length=2000, system=system, chars_per_token=1.5)
        assert len(backend.calls) == 1  # the drop path was actually reached
        assert _circuit._consecutive_failures == 0
        assert not _circuit.is_open

    def test_internal_caller_keeps_the_partial_generation(self, telemetry_dir):
        """``drop_truncated`` is the caller's choice, not the guard's. An
        internal caller (distill/insight) still receives the cut text and
        telemetry says so distinctly — the floor must not re-decide this."""
        window, system = 4096, "s"
        prompt = "瞑" * 3210
        backend = self._backend(window)
        configure(backend=backend)

        assert generate(prompt, system=system) is not None
        assert _read_records(telemetry_dir)[-1]["outcome"] == "truncated_kept"

    def test_headroom_below_the_new_floor_is_still_skipped(self, telemetry_dir):
        """The floor keeps its one remaining job. Just under it the call is
        refused before the backend is reached — lowering the floor relaxed
        the guard, it did not remove it."""
        window, system = 4096, "s"
        prompt = "瞑" * 3550
        headroom = self._headroom(window, system, prompt)
        assert 0 < headroom < MIN_CLAMPED_NUM_PREDICT  # positive budget, but an absurd one

        backend = self._backend(window)
        configure(backend=backend)
        assert (
            generate_for_api(prompt, max_length=2000, system=system, chars_per_token=1.5).text
            is None
        )
        assert backend.calls == []
        assert _read_records(telemetry_dir)[-1]["outcome"] == "budget_exceeded"
