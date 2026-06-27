"""Tests for pluggable LLM backend injection.

Exercises the ``configure(backend=...)`` hook without going near
``requests.post`` — the backend path in ``generate()`` bypasses URL
resolution and HTTP entirely, so these tests never touch network code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union

from contemplative_agent.core.llm import (
    CIRCUIT_FAILURE_THRESHOLD,
    BackendResult,
    LLMBackend,
    _circuit,
    configure,
    generate,
    reset_llm_config,
)


@dataclass
class FakeBackend:
    """Record calls and return queued responses.

    ``responses`` entries may be plain strings (wrapped in a
    :class:`BackendResult`), pre-built ``BackendResult`` instances (to set
    ``finish_reason``/``eval_count``), or ``None`` (hard failure).
    """

    model: str = "fake-model"
    responses: List[Union[str, BackendResult, None]] = field(default_factory=list)
    calls: List[dict] = field(default_factory=list)
    raise_exc: Optional[BaseException] = None

    def generate(
        self,
        prompt: str,
        system: str,
        num_predict: int,
        format: Optional[Dict],
        *,
        temperature: float = 1.0,
    ) -> Optional[BackendResult]:
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "num_predict": num_predict,
                "format": format,
                "temperature": temperature,
            }
        )
        if self.raise_exc is not None:
            raise self.raise_exc
        if not self.responses:
            return None
        item = self.responses.pop(0)
        if item is None or isinstance(item, BackendResult):
            return item
        return BackendResult(text=item)


class TestLLMBackendProtocol:
    def test_fake_backend_is_llmbackend(self):
        assert isinstance(FakeBackend(), LLMBackend)


class TestBackendInjection:
    def setup_method(self):
        reset_llm_config()

    def teardown_method(self):
        reset_llm_config()

    def test_generate_routes_through_backend(self):
        backend = FakeBackend(responses=["hello world"])
        configure(backend=backend)

        result = generate("ping", system="you are a test")

        assert result == "hello world"
        assert len(backend.calls) == 1
        call = backend.calls[0]
        assert call["prompt"] == "ping"
        assert call["system"] == "you are a test"
        # Default num_predict cap is 8192 when caller passes None
        assert call["num_predict"] == 8192
        assert call["format"] is None

    def test_generate_forwards_num_predict_and_format(self):
        backend = FakeBackend(responses=["ok"])
        configure(backend=backend)

        schema = {"type": "object", "properties": {"x": {"type": "string"}}}
        generate("p", system="s", num_predict=256, format=schema)

        call = backend.calls[0]
        assert call["num_predict"] == 256
        assert call["format"] == schema

    def test_sanitize_applies_on_cloud_path(self):
        # Backend returns a string containing a forbidden substring pattern.
        # _sanitize_output must still redact it, same as Ollama path.
        backend = FakeBackend(responses=["leaked api_key here"])
        configure(backend=backend)

        result = generate("p", system="s")

        assert result is not None
        assert "api_key" not in result.lower()
        assert "[REDACTED]" in result

    def test_backend_none_response_records_failure(self):
        backend = FakeBackend(responses=[None])
        configure(backend=backend)

        result = generate("p", system="s")

        assert result is None
        # Circuit breaker should have logged one failure
        assert _circuit._consecutive_failures == 1

    def test_backend_empty_string_records_failure(self):
        backend = FakeBackend(responses=["   "])
        configure(backend=backend)

        result = generate("p", system="s")

        assert result is None
        assert _circuit._consecutive_failures == 1

    def test_backend_exception_records_failure(self):
        backend = FakeBackend(raise_exc=RuntimeError("boom"))
        configure(backend=backend)

        result = generate("p", system="s")

        assert result is None
        assert _circuit._consecutive_failures == 1

    def test_circuit_breaker_opens_after_threshold(self):
        backend = FakeBackend(responses=[None] * CIRCUIT_FAILURE_THRESHOLD)
        configure(backend=backend)

        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            generate("p", system="s")

        assert _circuit.is_open
        # Once open, subsequent calls short-circuit without reaching backend
        call_count_before = len(backend.calls)
        result = generate("p", system="s")
        assert result is None
        assert len(backend.calls) == call_count_before

    def test_successful_response_resets_circuit(self):
        backend = FakeBackend(responses=[None, "recovered"])
        configure(backend=backend)

        generate("p", system="s")  # failure
        assert _circuit._consecutive_failures == 1

        generate("p", system="s")  # success
        assert _circuit._consecutive_failures == 0

    def test_reset_clears_backend(self):
        backend = FakeBackend(responses=["never reached"])
        configure(backend=backend)

        reset_llm_config()

        # After reset, generate should fall back to the Ollama path.
        # conftest.py forces OLLAMA_BASE_URL to an unreachable port, so
        # this call returns None without touching the fake backend.
        result = generate("p", system="s")
        assert result is None
        assert backend.calls == []  # backend was not invoked

    def test_backend_receives_built_system_prompt_when_system_omitted(self):
        backend = FakeBackend(responses=["ok"])
        configure(backend=backend, default_system_prompt="DEFAULT_SYSTEM")

        generate("p")  # system omitted

        assert backend.calls[0]["system"] == "DEFAULT_SYSTEM"
