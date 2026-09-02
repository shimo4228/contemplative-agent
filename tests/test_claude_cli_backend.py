"""RFC-0017 S4: the ``claude -p`` backend the replay's Claude arms run on.

This is the only cloud-egress seam the RFC adds, and it is deliberately
unreachable from production (``contemplative_agent.testing`` is forbidden to
every production layer by the ADR-0088 import-linter contract — the test at
the bottom of this file fixes that as a property rather than a habit).

What these tests hold still is the isolation set and the fail-closed edges:
the flags that keep the subprocess free of settings / tools / MCP, the
environment allowlist that stops a stray ``ANTHROPIC_*`` override changing
what was measured, and the four ways a call can fail (non-zero exit, an
envelope that is not JSON, ``is_error``, timeout) all landing on ``None`` so
the wiki loops record ``fail_closed_llm`` instead of a quiet no-op.
"""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from contemplative_agent.core.llm import BackendResult, LLMBackend
from contemplative_agent.testing.claude_cli import (
    CLAUDE_ENV_ALLOWLIST,
    ClaudeCliBackend,
)

MODEL = "claude-opus-5"


def _envelope(
    result: str = "ok",
    *,
    stop_reason: str = "end_turn",
    is_error: bool = False,
    model_usage: dict | None = None,
) -> dict:
    return {
        "type": "result",
        "subtype": "success",
        "is_error": is_error,
        "stop_reason": stop_reason,
        "result": result,
        "total_cost_usd": 0.5,
        "usage": {
            "input_tokens": 11,
            "output_tokens": 3,
            "cache_read_input_tokens": 1,
            "cache_creation_input_tokens": 2,
        },
        "modelUsage": model_usage
        if model_usage is not None
        else {
            MODEL: {
                "inputTokens": 100,
                "outputTokens": 20,
                "cacheReadInputTokens": 7,
                "cacheCreationInputTokens": 5,
                "costUSD": 0.25,
            }
        },
    }


def _fake_claude(tmp_path: Path, script: str) -> Path:
    """A ``claude`` on PATH that behaves however the test needs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    path = bin_dir / "claude"
    path.write_text("#!/usr/bin/env python3\n" + script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


def _echo_script(envelope: dict) -> str:
    """Record argv / env / stdin next to the scratch dir, then answer.

    The record path is derived from cwd rather than an env var precisely
    because the backend replaces the environment with its allowlist — a
    fixture variable would not survive, which is the property under test.
    """
    return (
        "import json, os, sys\n"
        "record = {'argv': sys.argv[1:], 'stdin': sys.stdin.read(), "
        "'env': dict(os.environ), 'cwd': os.getcwd()}\n"
        "open(os.path.join(os.getcwd(), os.pardir, 'record.json'), 'w')"
        ".write(json.dumps(record))\n"
        f"sys.stdout.write({json.dumps(json.dumps(envelope))})\n"
    )


def _backend(tmp_path: Path, script: str, **kw) -> ClaudeCliBackend:
    binary = _fake_claude(tmp_path, script)
    return ClaudeCliBackend(
        model=MODEL,
        scratch_dir=tmp_path / "scratch",
        claude_bin=str(binary),
        audit_path=tmp_path / "claude-cli-audit.jsonl",
        **kw,
    )


def _record(tmp_path: Path) -> dict:
    return json.loads((tmp_path / "record.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ contract


def test_satisfies_the_backend_protocol(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope()))
    assert isinstance(backend, LLMBackend)
    assert backend.model == MODEL
    assert backend.context_window == 200_000


def test_returns_the_result_text_and_maps_stop_reason(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope('{"action": "abstain"}')))
    out = backend.generate('{"a": 1}', "be brief", 3000, None)
    assert isinstance(out, BackendResult)
    assert out.text == '{"action": "abstain"}'
    assert out.finish_reason == "end_turn"


def test_max_tokens_is_reported_as_length(tmp_path):
    """``length`` is the Ollama spelling the truncation gate keys on."""
    backend = _backend(tmp_path, _echo_script(_envelope(stop_reason="max_tokens")))
    out = backend.generate("p", "s", 3000, None)
    assert out is not None
    assert out.finish_reason == "length"


# ------------------------------------------------------------------ isolation


def test_isolation_flags_are_all_present(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope()))
    backend.generate("p", "s", 3000, None)
    argv = _record(tmp_path)["argv"]
    assert argv[0] == "-p"
    assert "--strict-mcp-config" in argv
    for flag, value in (
        ("--output-format", "json"),
        ("--model", MODEL),
        ("--setting-sources", ""),
        ("--tools", ""),
    ):
        assert argv[argv.index(flag) + 1] == value


def test_prompt_travels_on_stdin_not_argv(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope()))
    backend.generate("SECRET-PROMPT", "SECRET-SYSTEM", 3000, None)
    record = _record(tmp_path)
    assert "SECRET-PROMPT" in record["stdin"]
    assert "SECRET-SYSTEM" in record["stdin"]
    assert not any("SECRET" in arg for arg in record["argv"])


def test_environment_is_an_allowlist(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "leaked")
    monkeypatch.setenv("CLAUDE_CODE_MAX_OUTPUT_TOKENS", "1")
    backend = _backend(tmp_path, _echo_script(_envelope()))
    backend.generate("p", "s", 3000, None)
    env = _record(tmp_path)["env"]
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_MAX_OUTPUT_TOKENS" not in env
    assert env["DISABLE_AUTOUPDATER"] == "1"
    passed = set(env) - {"DISABLE_AUTOUPDATER", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"}
    # macOS's libc injects __CF_USER_TEXT_ENCODING into every child; it is not
    # ours to pass or withhold, and it carries no model / billing override.
    assert passed <= set(CLAUDE_ENV_ALLOWLIST) | {"__CF_USER_TEXT_ENCODING"}
    assert "ANTHROPIC_API_KEY" not in CLAUDE_ENV_ALLOWLIST


def test_runs_in_the_scratch_directory(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope()))
    backend.generate("p", "s", 3000, None)
    assert Path(_record(tmp_path)["cwd"]).resolve() == (tmp_path / "scratch").resolve()


# --------------------------------------------------------------------- schema


def test_schema_is_carried_in_the_prompt_because_the_cli_has_no_format(tmp_path):
    """``claude -p`` has no constrained decoding, so the schema is an instruction."""
    backend = _backend(tmp_path, _echo_script(_envelope()))
    schema = {"type": "object", "properties": {"action": {"enum": ["write", "abstain"]}}}
    backend.generate("p", "s", 3000, schema)
    stdin = _record(tmp_path)["stdin"]
    assert json.dumps(schema, indent=2) in stdin


def test_no_schema_adds_no_schema_section(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope()))
    backend.generate("p", "s", 3000, None)
    assert "JSON Schema" not in _record(tmp_path)["stdin"]


# --------------------------------------------------------------- fail-closed


@pytest.mark.parametrize(
    ("script", "outcome"),
    [
        ("import sys; sys.exit(3)", "exit_3"),
        ("print('not json')", "bad_envelope"),
        (f"print({json.dumps(json.dumps(_envelope(is_error=True)))})", "is_error"),
    ],
)
def test_failures_return_none_and_are_audited(tmp_path, script, outcome):
    backend = _backend(tmp_path, script)
    assert backend.generate("p", "s", 3000, None) is None
    rows = [
        json.loads(line)
        for line in (tmp_path / "claude-cli-audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [row["outcome"] for row in rows] == [outcome]
    assert backend.usage.failures == 1


def test_timeout_returns_none(tmp_path):
    backend = _backend(tmp_path, "import time; time.sleep(5)", timeout=1)
    assert backend.generate("p", "s", 3000, None) is None
    assert backend.usage.failures == 1


def test_empty_result_returns_none(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope(result="   ")))
    assert backend.generate("p", "s", 3000, None) is None


# ----------------------------------------------------------------- accounting


def test_usage_prefers_this_arms_model_over_the_envelope_total(tmp_path):
    """The envelope tallies helper models too; the arm's reading is its own."""
    backend = _backend(tmp_path, _echo_script(_envelope()))
    out = backend.generate("p", "s", 3000, None)
    assert out is not None
    assert (out.prompt_tokens, out.eval_count, out.cached_tokens) == (100, 20, 7)
    usage = backend.usage
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (1, 100, 20)
    assert (usage.cache_read_tokens, usage.cache_creation_tokens) == (7, 5)
    assert usage.cost_usd == pytest.approx(0.25)


def test_usage_falls_back_to_the_envelope_when_the_model_is_absent(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope(model_usage={})))
    out = backend.generate("p", "s", 3000, None)
    assert out is not None
    assert (out.prompt_tokens, out.eval_count, out.cached_tokens) == (11, 3, 1)
    assert backend.usage.cost_usd == pytest.approx(0.5)


def test_usage_accumulates_across_calls(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope()))
    backend.generate("p", "s", 3000, None)
    backend.generate("p", "s", 3000, None)
    assert backend.usage.calls == 2
    assert backend.usage.input_tokens == 200
    assert backend.usage.as_dict()["cost_usd"] == pytest.approx(0.5)


def test_audit_records_the_prompt_hash_not_the_prompt(tmp_path):
    backend = _backend(tmp_path, _echo_script(_envelope()))
    backend.generate("SECRET-PROMPT", "s", 3000, None)
    text = (tmp_path / "claude-cli-audit.jsonl").read_text(encoding="utf-8")
    assert "SECRET-PROMPT" not in text
    row = json.loads(text.splitlines()[0])
    assert row["outcome"] == "response"
    assert len(row["prompt_sha256"]) == 64
    assert row["model"] == MODEL


def test_missing_binary_returns_none(tmp_path):
    backend = ClaudeCliBackend(
        model=MODEL,
        scratch_dir=tmp_path / "scratch",
        claude_bin=str(tmp_path / "nope"),
        audit_path=tmp_path / "audit.jsonl",
    )
    assert backend.generate("p", "s", 3000, None) is None
    assert backend.usage.failures == 1


# ------------------------------------------------------- production distance


def test_no_production_module_imports_the_claude_cli_backend():
    """The machine gate is the ADR-0088 forbidden contract; this states why.

    ``lint-imports`` already bans ``core`` / ``adapters`` / ``cli`` from
    importing ``contemplative_agent.testing`` at all, so the cloud-egress
    seam cannot be reached from the composition root. Grepping for the class
    name additionally catches a copy pasted into production, which an import
    contract would not see.
    """
    src = Path(__file__).resolve().parent.parent / "src" / "contemplative_agent"
    offenders = [
        path.relative_to(src).as_posix()
        for layer in ("core", "adapters", "cli")
        for path in (src / layer).rglob("*.py")
        if "ClaudeCliBackend" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
