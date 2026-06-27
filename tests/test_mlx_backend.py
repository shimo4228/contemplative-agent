"""Tests for the MLX generation backend (mlx_lm.server, OpenAI API shape).

Unit tests mock ``mlx_backend.requests.post`` to assert the request the
backend builds and how it maps the OpenAI response onto a ``BackendResult``.
Integration tests drive the same backend through the core ``generate()``
path to confirm sanitization, the ``drop_truncated`` gate, and circuit
accounting apply uniformly with the Ollama path.
"""

from __future__ import annotations

import json
from typing import Dict, Optional
from unittest.mock import MagicMock, patch

import pytest
import requests

from contemplative_agent.core.llm import (
    SAMPLING_TOP_P,
    SAMPLING_TOP_K,
    BackendResult,
    LLMBackend,
    _circuit,
    configure,
    generate,
    reset_llm_config,
)
from contemplative_agent.core.mlx_backend import MlxLmBackend

_BASE_URL = "http://localhost:8080"
_MODEL = "mlx-community/Qwen3.5-9B-4bit"


def _mock_response(
    content: str = "hello",
    finish_reason: str = "stop",
    completion_tokens: Optional[int] = 7,
    prompt_tokens: Optional[int] = None,
    cached_tokens: Optional[int] = None,
):
    """Build a MagicMock mimicking an OpenAI chat-completion HTTP response.

    ``prompt_tokens`` / ``cached_tokens`` mirror mlx_lm.server's prefill
    accounting: ``usage.prompt_tokens`` (total input) and
    ``usage.prompt_tokens_details.cached_tokens`` (prompt-cache hits). Both
    default to absent so existing callers exercise the no-accounting case.
    """
    resp = MagicMock()
    usage: Dict = {}
    if completion_tokens is not None:
        usage["completion_tokens"] = completion_tokens
    if prompt_tokens is not None:
        usage["prompt_tokens"] = prompt_tokens
    if cached_tokens is not None:
        usage["prompt_tokens_details"] = {"cached_tokens": cached_tokens}
    resp.json.return_value = {
        "choices": [
            {"message": {"content": content}, "finish_reason": finish_reason}
        ],
        "usage": usage,
    }
    resp.raise_for_status.return_value = None
    return resp


@pytest.fixture
def backend():
    return MlxLmBackend(base_url=_BASE_URL, model=_MODEL)


class TestProtocolConformance:
    def test_is_llmbackend(self, backend):
        assert isinstance(backend, LLMBackend)

    def test_is_frozen(self, backend):
        with pytest.raises(Exception):
            backend.model = "other"  # type: ignore[misc]

    def test_context_window_default(self, backend):
        """The MLX window is memory-bounded on the 16 GB host (~32k), NOT
        Qwen3.5-9B's 262k native window: mlx_lm.server has no context flag
        (issue #615) and grows the KV cache to OOM past it. The core
        budget guard reads this value via the LLMBackend.context_window
        contract."""
        assert backend.context_window == 32768


class TestRequestShape:
    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_returns_backend_result(self, mock_post, backend):
        mock_post.return_value = _mock_response(
            content="hi there", finish_reason="stop", completion_tokens=3
        )
        result = backend.generate("ping", "be terse", 256, None)
        assert isinstance(result, BackendResult)
        assert result.text == "hi there"
        assert result.finish_reason == "stop"
        assert result.eval_count == 3

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_payload_and_url(self, mock_post, backend):
        mock_post.return_value = _mock_response()
        backend.generate("the prompt", "the system", 128, None, temperature=0.0)

        args, kwargs = mock_post.call_args
        assert args[0] == "http://localhost:8080/v1/chat/completions"
        assert kwargs["allow_redirects"] is False
        payload = kwargs["json"]
        assert payload["model"] == _MODEL
        assert payload["max_tokens"] == 128
        assert payload["temperature"] == 0.0
        assert payload["stream"] is False
        assert payload["chat_template_kwargs"] == {"enable_thinking": False}
        assert payload["messages"] == [
            {"role": "system", "content": "the system"},
            {"role": "user", "content": "the prompt"},
        ]

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_payload_sends_top_p_and_top_k(self, mock_post, backend):
        """Regression: the payload must carry the SAME top_p/top_k the Ollama
        path uses, sourced from the single source of truth in core/llm
        (SAMPLING_TOP_P / SAMPLING_TOP_K) — asserting against the shared
        constants, not literals, so the two backends provably cannot drift.

        Without nucleus + top-k sampling, Qwen3.5-9B-4bit on mlx_lm.server
        degenerates into repetition loops at the outward COMMENT_TEMPERATURE
        (1.3): it never emits EOS and runs to max_tokens (finish_reason=length),
        so a single content generation can take 10-25 minutes and block all
        posting. mlx_lm.server applies no default top_p and ignores
        repetition_penalty, so these must be sent explicitly. Dropping either
        key (or hardcoding a value that drifts from the Ollama path)
        reintroduces the runaway, hence this guard.
        """
        mock_post.return_value = _mock_response()
        backend.generate("p", "s", 128, None, temperature=1.3)
        payload = mock_post.call_args.kwargs["json"]
        assert payload["top_p"] == SAMPLING_TOP_P
        assert payload["top_k"] == SAMPLING_TOP_K

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_system_omitted_when_empty(self, mock_post, backend):
        mock_post.return_value = _mock_response()
        backend.generate("only user", "", 64, None)
        messages = mock_post.call_args.kwargs["json"]["messages"]
        assert messages == [{"role": "user", "content": "only user"}]

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_temperature_default_is_one(self, mock_post, backend):
        mock_post.return_value = _mock_response()
        backend.generate("p", "s", 64, None)
        assert mock_post.call_args.kwargs["json"]["temperature"] == 1.0

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_trailing_slash_in_base_url(self, mock_post):
        mock_post.return_value = _mock_response()
        MlxLmBackend(base_url="http://localhost:8080/", model=_MODEL).generate(
            "p", "s", 16, None
        )
        assert (
            mock_post.call_args.args[0]
            == "http://localhost:8080/v1/chat/completions"
        )


class TestFormatHandling:
    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_format_becomes_prompt_instruction(self, mock_post, backend):
        mock_post.return_value = _mock_response(content='{"patterns": []}')
        schema = {"type": "object", "properties": {"patterns": {"type": "array"}}}
        backend.generate("distill this", "system", 3000, schema)

        payload = mock_post.call_args.kwargs["json"]
        # No native structured-output field is sent (server has none).
        assert "format" not in payload
        assert "response_format" not in payload
        # The schema is embedded into the user message instead.
        user_msg = payload["messages"][-1]["content"]
        assert "distill this" in user_msg
        assert json.dumps(schema, ensure_ascii=False) in user_msg
        assert "JSON Schema" in user_msg

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_no_instruction_when_format_none(self, mock_post, backend):
        mock_post.return_value = _mock_response()
        backend.generate("plain", "system", 256, None)
        user_msg = mock_post.call_args.kwargs["json"]["messages"][-1]["content"]
        assert user_msg == "plain"


class TestResponseMapping:
    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_finish_reason_length_propagates(self, mock_post, backend):
        mock_post.return_value = _mock_response(finish_reason="length")
        result = backend.generate("p", "s", 8, None)
        assert result is not None
        assert result.finish_reason == "length"

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_eval_count_none_when_usage_missing(self, mock_post, backend):
        mock_post.return_value = _mock_response(completion_tokens=None)
        result = backend.generate("p", "s", 64, None)
        assert result is not None
        assert result.eval_count is None

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_prompt_and_cached_tokens_parsed(self, mock_post, backend):
        """mlx_lm.server reports prefill accounting in usage: prompt_tokens
        (total input) and prompt_tokens_details.cached_tokens (served from
        the prompt KV cache vs freshly prefilled). Surfacing both lets
        telemetry compute the per-call cache-hit rate that tells a
        cache-churn slowdown apart from a memory-pressure cliff."""
        mock_post.return_value = _mock_response(
            prompt_tokens=7434, cached_tokens=7237
        )
        result = backend.generate("p", "s", 64, None)
        assert result is not None
        assert result.prompt_tokens == 7434
        assert result.cached_tokens == 7237

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_prompt_and_cached_tokens_none_when_absent(self, mock_post, backend):
        """A response without prefill accounting (older server, or nothing
        cached) leaves both None — never raises, never fabricates a count."""
        mock_post.return_value = _mock_response()  # only completion_tokens
        result = backend.generate("p", "s", 64, None)
        assert result is not None
        assert result.prompt_tokens is None
        assert result.cached_tokens is None

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_prompt_tokens_without_cached_details(self, mock_post, backend):
        """prompt_tokens present but no prompt_tokens_details block (no cache
        hit reported): prompt_tokens surfaces, cached_tokens stays None."""
        mock_post.return_value = _mock_response(prompt_tokens=500)
        result = backend.generate("p", "s", 64, None)
        assert result is not None
        assert result.prompt_tokens == 500
        assert result.cached_tokens is None

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_null_content_becomes_empty_string(self, mock_post, backend):
        resp = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": None}, "finish_reason": "stop"}],
            "usage": {},
        }
        resp.raise_for_status.return_value = None
        mock_post.return_value = resp
        result = backend.generate("p", "s", 64, None)
        assert result is not None
        assert result.text == ""

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_malformed_response_raises(self, mock_post, backend):
        resp = MagicMock()
        resp.json.return_value = {"unexpected": "shape"}
        resp.raise_for_status.return_value = None
        mock_post.return_value = resp
        with pytest.raises(ValueError):
            backend.generate("p", "s", 64, None)


class TestSecurity:
    def test_untrusted_host_raises_at_construction(self, monkeypatch):
        # Fail fast: a misconfigured external host is rejected at construction
        # (cli.py startup), not deferred to the first generate() call.
        monkeypatch.delenv("OLLAMA_TRUSTED_HOSTS", raising=False)
        with pytest.raises(ValueError, match="trusted host"):
            MlxLmBackend(base_url="http://evil.com:8080", model=_MODEL)

    def test_non_http_scheme_rejected(self, monkeypatch):
        monkeypatch.delenv("OLLAMA_TRUSTED_HOSTS", raising=False)
        with pytest.raises(ValueError, match="http or https"):
            MlxLmBackend(base_url="file://localhost/etc/passwd", model=_MODEL)

    def test_non_positive_context_window_rejected(self):
        # Fail fast: a non-positive window would make the core budget guard
        # skip every call (est_input + num_predict > 0 always) — a silent
        # generation blackout. Reject it at construction like a bad URL.
        with pytest.raises(ValueError, match="context_window must be positive"):
            MlxLmBackend(base_url=_BASE_URL, model=_MODEL, context_window=0)

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_http_error_propagates(self, mock_post, backend):
        resp = MagicMock()
        resp.raise_for_status.side_effect = requests.HTTPError("500")
        mock_post.return_value = resp
        with pytest.raises(requests.HTTPError):
            backend.generate("p", "s", 64, None)


class TestIntegrationThroughCore:
    def setup_method(self):
        reset_llm_config()

    def teardown_method(self):
        reset_llm_config()

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_sanitization_applies(self, mock_post):
        mock_post.return_value = _mock_response(content="leaked api_key here")
        configure(backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL))
        result = generate("p", system="s")
        assert result is not None
        assert "api_key" not in result.lower()
        assert "[REDACTED]" in result

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_temperature_reaches_backend(self, mock_post):
        mock_post.return_value = _mock_response()
        configure(backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL))
        generate("p", system="s", temperature=1.3)
        assert mock_post.call_args.kwargs["json"]["temperature"] == 1.3

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_drop_truncated_returns_none(self, mock_post):
        mock_post.return_value = _mock_response(
            content="cut off mid", finish_reason="length"
        )
        configure(backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL))
        assert generate("p", system="s", drop_truncated=True) is None

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_truncated_kept_when_not_dropped(self, mock_post):
        mock_post.return_value = _mock_response(
            content="partial answer", finish_reason="length"
        )
        configure(backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL))
        assert generate("p", system="s", drop_truncated=False) == "partial answer"

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_truncation_drop_is_not_circuit_failure(self, mock_post):
        # A deliberate truncation drop is a successful call (audit M2):
        # it must reset, not trip, the circuit breaker.
        mock_post.return_value = _mock_response(
            content="cut", finish_reason="length"
        )
        configure(backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL))
        generate("p", system="s", drop_truncated=True)
        assert _circuit._consecutive_failures == 0

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_http_failure_records_circuit_failure(self, mock_post):
        mock_post.side_effect = requests.ConnectionError("server down")
        configure(backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL))
        assert generate("p", system="s") is None
        assert _circuit._consecutive_failures == 1

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_over_budget_skips_before_request(self, mock_post):
        """An over-window prompt is skipped by the core budget guard BEFORE
        the HTTP call — the request is never sent. Regression for the hole
        the MLX path had: mlx_lm.server has no context cap, so an oversized
        prompt would grow the KV cache until the 16 GB host swaps/OOMs."""
        configure(backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL))
        # ~66k est tokens for ASCII at 3 chars/tok > the 32768 window.
        assert generate("x" * 200000, system="s") is None
        mock_post.assert_not_called()

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_telemetry_records_real_model_id(self, mock_post, tmp_path):
        """The injected backend's served model id — not its class name — is
        recorded in per-call telemetry, so telemetry groups by the actual
        model uniformly across backends (parity with the Ollama path)."""
        mock_post.return_value = _mock_response()
        configure(
            backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL),
            telemetry_dir=tmp_path,
        )
        generate("p", system="s")

        files = list(tmp_path.glob("llm-calls-*.jsonl"))
        assert len(files) == 1
        records = [
            json.loads(line)
            for line in files[0].read_text().splitlines()
            if line.strip()
        ]
        assert records
        assert records[-1]["model"] == _MODEL

    @patch("contemplative_agent.core.mlx_backend.requests.post")
    def test_telemetry_records_prefill_cache_accounting(self, mock_post, tmp_path):
        """MLX prefill accounting reaches per-call telemetry: prompt_eval_count
        (total input tokens, unified with the Ollama path's field name) and
        cached_tokens (prompt-cache hits). cached_tokens / prompt_eval_count is
        the cache-hit rate that distinguishes a cache-churn slowdown (the
        ~7.5k system prefix evicted by smaller prompts, re-prefilled in full)
        from a memory-pressure cliff — the open question after the 2026-06-27
        58-minute prefill hang."""
        mock_post.return_value = _mock_response(
            prompt_tokens=7434, cached_tokens=7237
        )
        configure(
            backend=MlxLmBackend(base_url=_BASE_URL, model=_MODEL),
            telemetry_dir=tmp_path,
        )
        generate("p", system="s")

        files = list(tmp_path.glob("llm-calls-*.jsonl"))
        assert len(files) == 1
        records = [
            json.loads(line)
            for line in files[0].read_text().splitlines()
            if line.strip()
        ]
        assert records
        assert records[-1]["prompt_eval_count"] == 7434
        assert records[-1]["cached_tokens"] == 7237
