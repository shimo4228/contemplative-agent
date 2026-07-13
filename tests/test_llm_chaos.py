"""Chaos fault-injection tests for the LLM layer (ADR-0077, F1 + F4 + F5).

HTTP-path faults (F1 read-timeout, F4 Ollama-side 429) are injected with the
``responses`` library on the URL the code under test actually resolves;
backend-path faults ride ``configure(backend=ChaosBackend(...))``. Steady
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

from contemplative_agent.core.llm import (
    CIRCUIT_FAILURE_THRESHOLD,
    LLMBackend,
    _circuit,
    configure,
    generate,
    reset_llm_config,
)
from tests.chaos import (
    EXC_CONNECTION,
    EXC_TIMEOUT,
    NONE,
    OK,
    SHAPE_VIOLATION,
    ChaosBackend,
    add_generate_429,
    add_generate_timeout,
)
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
