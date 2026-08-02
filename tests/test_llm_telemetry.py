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
    "think",
    # Which channel supplied the requested reasoning trace, or "absent" when
    # none did. None when the capture guard never ran (think=False, or a call
    # that failed before its success tail). ADR-0068 amendment.
    "thinking_source",
    # Which measure the C2 pre-flight actually used, and the value it used.
    # None on both when the guard did not run (backend with no declared
    # context_window). ADR-0087.
    "token_count_source",
    "input_tokens",
    # 共有 writer (_io.append_jsonl_restricted) が全 JSONL にスタンプする
    # 実行識別子（ADR-0078 follow-up）。session 中は session_id も付く
    "run_id",
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
        # with backends that do) but stays None on this path.
        assert record["cached_tokens"] is None
        assert isinstance(record["duration_ms"], int)

    @patch("contemplative_agent.core.llm.requests.post")
    def test_caller_defaults_to_unknown(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate("test")
        assert _read_records(telemetry_dir)[0]["caller"] == "unknown"

    @patch("contemplative_agent.core.llm.requests.post")
    def test_think_defaults_false(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate("test")
        assert _read_records(telemetry_dir)[0]["think"] is False

    @patch("contemplative_agent.core.llm.requests.post")
    def test_think_true_recorded(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate("test", think=True)
        assert _read_records(telemetry_dir)[0]["think"] is True

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
    def test_truncated_but_kept_records_truncated_kept(self, mock_post, telemetry_dir):
        """Bug-audit 2026-07-06 M1: a length-capped generation kept because
        drop_truncated=False must NOT be recorded as a clean "ok" — otherwise
        telemetry cannot measure how often internal consumers received an
        incomplete generation."""
        mock_post.return_value = _mock_ok_response(done_reason="length")
        result = generate("test", drop_truncated=False)
        assert result == "Hello world"
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "truncated_kept"
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
    def test_clamped_call_records_requested_num_predict(self, mock_post, telemetry_dir):
        """A C2-clamped call is an ok outcome whose record answers 'why was
        the output budget smaller than requested': ``num_predict`` holds the
        clamped value actually sent, ``num_predict_requested`` the original."""
        mock_post.return_value = _mock_ok_response()
        assert generate("y" * 3000, system="x" * 60000, num_predict=13384) is not None
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "ok"
        assert record["num_predict_requested"] == 13384
        assert record["num_predict"] == NUM_CTX - 20000 - 1000

    @patch("contemplative_agent.core.llm.requests.post")
    def test_ollama_path_records_the_estimator_as_the_source(self, mock_post, telemetry_dir):
        """The Ollama path has no tokenizer to reach for, so every row says
        so explicitly rather than leaving the reader to infer it."""
        from contemplative_agent.core.llm import _estimate_tokens

        mock_post.return_value = _mock_ok_response()
        assert generate("test prompt", system="sys") is not None
        record = _read_records(telemetry_dir)[0]
        assert record["token_count_source"] == "estimator"
        assert record["input_tokens"] == _estimate_tokens("sys") + _estimate_tokens("test prompt")
        # Absence of a counter is the default, not a fallback from one.
        assert "token_count_fallback_reason" not in record

    def test_backend_counter_records_backend_source_and_measured_total(self, telemetry_dir):
        from tests.chaos import TokenCountingChaosBackend, real_token_count

        configure(backend=TokenCountingChaosBackend(model="counting-model"))
        assert generate("test prompt", system="sys") is not None
        record = _read_records(telemetry_dir)[0]
        assert record["token_count_source"] == "backend"
        assert record["input_tokens"] == real_token_count("sys") + real_token_count("test prompt")
        assert "token_count_fallback_reason" not in record

    def test_unguarded_backend_records_neither(self, telemetry_dir):
        """A backend with no declared context_window is not budget-guarded at
        all (ADR-0066 graceful degrade), so there is no measurement to
        report — None, not a fabricated estimate."""
        from contemplative_agent.core.llm import BackendResult

        class UnguardedBackend:
            model = "unguarded-model"

            def generate(
                self, prompt, system, num_predict, format, *, temperature=1.0, think=False
            ):
                return BackendResult(text="delegated")

        configure(backend=UnguardedBackend())  # type: ignore[arg-type]
        assert generate("test") == "delegated"
        record = _read_records(telemetry_dir)[0]
        assert record["token_count_source"] is None
        assert record["input_tokens"] is None

    @patch("contemplative_agent.core.llm.requests.post")
    def test_unclamped_call_has_no_requested_field(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        assert generate("test", num_predict=512) is not None
        assert "num_predict_requested" not in _read_records(telemetry_dir)[0]

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

            def generate(
                self, prompt, system, num_predict, format, *, temperature=1.0, think=False
            ):
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


class TestThinkingTraceTelemetry:
    """The think row says whether the requested trace actually arrived.

    ``think`` alone records the REQUEST. Without a companion outcome field a
    row saying ``think: true`` is identical whether the trace was captured or
    silently lost, which is what let a snapshot manifest claim think while its
    ``reasoning.md`` was missing with no reason recorded (ADR-0068 amendment).
    """

    @patch("contemplative_agent.core.llm.requests.post")
    def test_think_off_leaves_the_guard_unrun(self, mock_post, telemetry_dir):
        """Absence of a request is the default, not a fallback from one — so
        the dense field stays None and no reason is stamped. Pinning this is
        what keeps a future "warn whenever a trace is missing" from firing on
        every production row."""
        mock_post.return_value = _mock_ok_response(thinking="unrequested")
        generate("test")
        record = _read_records(telemetry_dir)[0]
        assert record["thinking_source"] is None
        assert "thinking_fallback_reason" not in record

    @patch("contemplative_agent.core.llm.requests.post")
    def test_dedicated_field_records_its_channel(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response(thinking="reasoning here")
        generate("test", think=True)
        record = _read_records(telemetry_dir)[0]
        assert record["thinking_source"] == "field"
        assert "thinking_fallback_reason" not in record

    @patch("contemplative_agent.core.llm.requests.post")
    def test_inline_fallback_records_its_channel(self, mock_post, telemetry_dir):
        """A trace recovered from the text is a successful capture, but from
        the weaker channel — worth telling apart when calibrating which
        backends actually honor the flag."""
        mock_post.return_value = _mock_ok_response(text="<think>inline</think>answer")
        generate("test", think=True)
        record = _read_records(telemetry_dir)[0]
        assert record["thinking_source"] == "inline"
        assert "thinking_fallback_reason" not in record

    @patch("contemplative_agent.core.llm.requests.post")
    def test_absent_trace_is_recorded_with_its_reason(self, mock_post, telemetry_dir):
        mock_post.return_value = _mock_ok_response()
        generate("test", think=True)
        record = _read_records(telemetry_dir)[0]
        assert record["thinking_source"] == "absent"
        assert record["thinking_fallback_reason"] == "trace_absent"
        assert record["outcome"] == "ok"  # the generation succeeded; only the trace is missing

    @patch("contemplative_agent.core.llm.requests.post")
    def test_blank_trace_is_distinct_from_an_absent_one(self, mock_post, telemetry_dir):
        """A channel that carried whitespace worked; its content did not. The
        first is a model behavior, the second a backend that never populates
        the field — collapsing them would hide which one is happening."""
        mock_post.return_value = _mock_ok_response(thinking="   \n ")
        generate("test", think=True)
        assert _read_records(telemetry_dir)[0]["thinking_fallback_reason"] == "trace_blank"

    @patch("contemplative_agent.core.llm.requests.post")
    def test_a_missing_trace_makes_no_claim_about_the_run(self, mock_post, telemetry_dir, caplog):
        """A run can make several think-ON calls (rules-distill 2, stocktake 4),
        so one empty trace does not mean the run wrote no reasoning.md. The
        per-call warning must not assert otherwise — a false diagnosis handed
        out from inside the observability path (codex-review 2026-08-02)."""
        mock_post.return_value = _mock_ok_response()
        with caplog.at_level(logging.WARNING, logger="contemplative_agent.core.llm"):
            generate("test", think=True)
        assert "reason=trace_absent" in caplog.text
        assert "reasoning.md" not in caplog.text

    @patch("contemplative_agent.core.llm.requests.post")
    def test_failed_call_leaves_the_guard_unrun(self, mock_post, telemetry_dir):
        """A row that never reached the success tail has no trace to explain;
        ``outcome`` already answers why. Stamping a trace reason here would
        double-count one fault under two fields."""
        mock_post.return_value = _mock_ok_response(text="")
        generate("test", think=True)
        record = _read_records(telemetry_dir)[0]
        assert record["outcome"] == "empty"
        assert record["thinking_source"] is None
        assert "thinking_fallback_reason" not in record

    @patch("contemplative_agent.core.llm.requests.post")
    def test_trace_content_never_reaches_telemetry(self, mock_post, telemetry_dir):
        """The ADR-0065 metadata-only contract survives the new fields: they
        are closed enumerations over provenance, never the trace itself."""
        mock_post.return_value = _mock_ok_response(thinking="SECRET-TRACE-CONTENT")
        generate("test", think=True)
        assert "SECRET-TRACE-CONTENT" not in json.dumps(_read_records(telemetry_dir)[0])
