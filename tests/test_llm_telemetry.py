"""Tests for per-call LLM telemetry (llm-calls-{date}.jsonl).

Telemetry records call-level metadata (caller, tokens, duration, outcome)
without the prompt body — the prompt may embed untrusted external content,
and telemetry is meant to be read back by LLM-assisted analysis sessions,
so recording bodies would create a second injection path.
"""

import json
import logging
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests

from contemplative_agent.core import llm as llm_module
from contemplative_agent.core.llm import (
    NUM_CTX,
    configure,
    generate,
    generate_for_api,
    reset_llm_config,
)

CANARY = "SECRET-PROMPT-BODY-MARKER-9e1c"


@pytest.fixture
def telemetry_dir(tmp_path):
    configure(telemetry_dir=tmp_path)
    yield tmp_path
    reset_llm_config()


def _read_records(telemetry_dir):
    files = sorted(telemetry_dir.glob("llm-calls-*.jsonl"))
    records = []
    for path in files:
        for line in path.read_text(encoding="utf-8").splitlines():
            records.append(json.loads(line))
    return records


def _mock_ok_response(text="Hello world", **extra):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": text, **extra}
    mock_resp.raise_for_status.return_value = None
    return mock_resp


EXPECTED_FIELDS = {
    "ts",
    "caller",
    "model",
    "prompt_chars",
    "system_chars",
    "num_predict",
    "temperature",
    "has_format",
    "prompt_sha256",
    "duration_ms",
    "outcome",
    "done_reason",
    "prompt_eval_count",
    "eval_count",
    "cached_tokens",
}


class TestTelemetryOkPath:
    @patch("contemplative_agent.core.llm.requests.post")
    def test_ok_record_has_all_fields(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response(
            done_reason="stop", prompt_eval_count=10, eval_count=5
        )
        result = generate("test prompt", caller="distill.category")
        assert result == "Hello world"

        records = _read_records(telemetry_dir)
        assert len(records) == 1
        record = records[0]
        assert set(record) == EXPECTED_FIELDS
        assert record["outcome"] == "ok"
        assert record["caller"] == "distill.category"
        assert record["prompt_chars"] == len("test prompt")
        assert record["system_chars"] > 0
        assert record["num_predict"] == 8192
        assert record["temperature"] == 1.0
        assert record["has_format"] is False
        assert record["done_reason"] == "stop"
        assert record["prompt_eval_count"] == 10
        assert record["eval_count"] == 5
        # Ollama does not report prompt-cache hits; the field exists (parity
        # with the MLX path) but stays None on this path.
        assert record["cached_tokens"] is None
        assert isinstance(record["duration_ms"], int)

    @patch("contemplative_agent.core.llm.requests.post")
    def test_caller_defaults_to_unknown(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate("test")
        assert _read_records(telemetry_dir)[0]["caller"] == "unknown"

    @patch("contemplative_agent.core.llm.requests.post")
    def test_three_calls_three_records(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        for _ in range(3):
            generate("test")
        assert len(_read_records(telemetry_dir)) == 3

    @patch("contemplative_agent.core.llm.requests.post")
    def test_filename_is_utc_dated(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate("test")
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        assert (telemetry_dir / f"llm-calls-{date_str}.jsonl").exists()

    @patch("contemplative_agent.core.llm.requests.post")
    def test_truncated_but_kept_is_ok_with_done_reason(
        self, mock_post, telemetry_dir
    ):
        mock_post.return_value = _mock_ok_response(done_reason="length")
        result = generate("test", drop_truncated=False)
        assert result == "Hello world"
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "ok"
        assert record["done_reason"] == "length"


class TestTelemetryFailurePaths:
    def test_circuit_open(self, telemetry_dir):
        for _ in range(5):
            llm_module._circuit.record_failure()
        assert generate("test") is None
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "circuit_open"
        assert record["system_chars"] is None

    @patch("contemplative_agent.core.llm.requests.post")
    def test_request_exception_is_error(self, mock_post, telemetry_dir):
        mock_post.side_effect = requests.RequestException("boom")
        assert generate("test") is None
        assert _read_records(telemetry_dir)[0]["outcome"] == "error"

    @patch("contemplative_agent.core.llm.requests.post")
    def test_empty_response(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response("   ")
        assert generate("test") is None
        assert _read_records(telemetry_dir)[0]["outcome"] == "empty"

    def test_budget_exceeded(self, telemetry_dir):
        huge_prompt = "a" * (NUM_CTX * 3 + 30000)
        assert generate(huge_prompt) is None
        assert _read_records(telemetry_dir)[0]["outcome"] == "budget_exceeded"

    @patch("contemplative_agent.core.llm.requests.post")
    def test_truncated_dropped(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response(done_reason="length")
        assert generate("test", drop_truncated=True) is None
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "truncated_dropped"
        assert record["done_reason"] == "length"

    def test_backend_raise_is_error(self, telemetry_dir):
        class _RaisingBackend:
            model = "raising-model"
            # Satisfies the LLMBackend protocol's context_window member; the
            # tiny "test" prompt stays well under it, so the budget guard
            # passes and the backend's raising generate() is still reached.
            context_window = 32768

            def generate(self, prompt, system, num_predict, format,
                         *, temperature=1.0):
                raise RuntimeError("backend boom")

        configure(backend=_RaisingBackend())
        assert generate("test") is None
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "error"
        # Backend declares its served model id via the LLMBackend contract;
        # telemetry records that real id (not a class-name sentinel) even on
        # the error path.
        assert record["model"] == "raising-model"


class TestTelemetrySecurity:
    @patch("contemplative_agent.core.llm.requests.post")
    def test_prompt_body_never_written(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate(f"prompt with {CANARY} inside", system=f"system {CANARY}")
        for path in telemetry_dir.glob("llm-calls-*.jsonl"):
            assert CANARY not in path.read_text(encoding="utf-8")

    @patch("contemplative_agent.core.llm.requests.post")
    def test_prompt_sha256_stable_12_hex(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate("same prompt")
        generate("same prompt")
        generate("other prompt")
        records = _read_records(telemetry_dir)
        hashes = [r["prompt_sha256"] for r in records]
        assert all(len(h) == 12 for h in hashes)
        assert all(int(h, 16) >= 0 for h in hashes)
        assert hashes[0] == hashes[1]
        assert hashes[0] != hashes[2]


class TestTelemetryIsolation:
    @patch("contemplative_agent.core.llm.requests.post")
    def test_disabled_when_dir_not_configured(self, mock_post, tmp_path):
        mock_post.return_value = _mock_ok_response()
        assert generate("test") == "Hello world"
        assert list(tmp_path.glob("llm-calls-*.jsonl")) == []

    @patch("contemplative_agent.core.llm.append_jsonl_restricted")
    @patch("contemplative_agent.core.llm.requests.post")
    def test_write_failure_does_not_break_generate(
        self, mock_post, mock_append, telemetry_dir, caplog
    ):
        mock_post.return_value = _mock_ok_response()
        mock_append.side_effect = OSError("disk full")
        with caplog.at_level(logging.WARNING):
            assert generate("test") == "Hello world"
        assert "Failed to write LLM telemetry" in caplog.text

    @patch("contemplative_agent.core.llm.requests.post")
    def test_generate_for_api_passes_caller(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate_for_api("test", 200, caller="moltbook.comment")
        record = _read_records(telemetry_dir)[0]
        assert record["caller"] == "moltbook.comment"
