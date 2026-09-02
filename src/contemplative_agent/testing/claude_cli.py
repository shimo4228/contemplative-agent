"""An :class:`~contemplative_agent.core.llm.LLMBackend` over ``claude -p``
(RFC-0017 S4, D9).

The replay's two Claude arms need the *same* wiki loops gemma runs, driven by
a different model. That is exactly what the ``LLMBackend`` seam is for, so
this is an adapter and nothing more: the loops, the schemas, the validation
and the audit rows are unchanged, and only the generation call is redirected.

**Why this lives under ``testing/`` and not ``core/llm/``.** It is the one
cloud-egress seam RFC-0017 adds, and D14 says the RFC must not add a path by
which production reaches outward. ``contemplative_agent.testing`` already
carries a machine-enforced version of that promise — the ADR-0088
import-linter contract forbids ``core`` / ``adapters`` / ``cli`` from
importing anything under it — so putting the backend here makes
"unreachable from the composition root" a checked property rather than a
convention. A module under ``core/llm/`` would have needed a new contract to
say the same thing, next to the code that is allowed to be reached.

Isolation is the judge's, verbatim (``evals/judging.py``, ADR-0089):
``--setting-sources ""`` (no settings / CLAUDE.md / memory), ``--tools ""``
(no tools at all — D9 requires that the Claude arms get no filesystem, so
``read_file`` stays the code-owned enum loop the gemma arm uses),
``--strict-mcp-config`` with no MCP config, a scratch cwd, an environment
allowlist, and the prompt on stdin. The allowlist is restated rather than
imported because ``evals/`` is not in the wheel and this package may import
nothing but the standard library and ``core.llm``; it is also the kind of
constant that should not be able to change under this file from elsewhere.

Three ``LLMBackend`` arguments have no counterpart in ``claude -p`` and are
handled explicitly rather than silently:

- ``format`` — the CLI has no constrained decoding, so the schema is appended
  to the prompt as an instruction and the answer is parsed by the caller.
  A model that ignores it costs the turn as ``fail_closed_parse``, which is
  a reading about the Claude arms, not a defect to paper over (D9).
- ``num_predict`` — no CLI equivalent. Ignored. The consequence is that the
  Claude arms cannot produce ``fail_closed_truncated`` from an output budget.
- ``think`` — no CLI equivalent at this seam. Ignored; ``thinking`` is
  always ``None``.

Every failure returns ``None``, which the wiki loops record as
``fail_closed_llm``. Nothing here degrades to a guess.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess  # noqa: S404 - spawning the claude CLI is this module's job
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..core.llm import BackendResult

logger = logging.getLogger(__name__)

# The paper's capacity (RFC-0017 D9 arm ①). Deliberately NOT the window the
# CLI reports for the model: on 2026-09-02 ``claude -p`` reported a 1,000,000
# token window for claude-opus-5, and running the "faithful reproduction" arm
# at five times the paper's context would change what the arm measures. The
# constrained arms pass ``context_window=32768`` to match gemma instead.
PAPER_CONTEXT_WINDOW = 200_000

# Minimal environment the claude CLI needs to run and authenticate. An
# allowlist, not a denylist, for the reason ``evals/judging.py`` gives: the
# denied namespace (ANTHROPIC_*, CLAUDE_*, …) is not ours to enumerate and
# grows, so a new billing / model / effort override cannot silently change
# what the replay measured. No API-key variable is listed — the CLI
# authenticates through the operator's subscription, exactly as the judge does.
CLAUDE_ENV_ALLOWLIST = ("HOME", "PATH", "USER", "SHELL", "LANG", "LC_ALL", "TMPDIR", "TERM")

# ``stop_reason`` values that mean the same thing Ollama's ``done_reason`` does.
# Only the truncation spelling is translated, because that is the one the
# caller's ``drop_truncated`` gate keys on (audit M2); everything else is
# passed through so the audit records what the CLI actually said.
_TRUNCATION_STOP_REASONS = frozenset({"max_tokens"})

_SCHEMA_INSTRUCTION = (
    "## Output format\n\n"
    "Answer with a single JSON object and nothing else — no prose before or "
    "after it, no code fence. It must conform strictly to this JSON Schema, "
    "including every `enum`: a value outside an enum discards the turn.\n\n"
)


@dataclass
class ClaudeUsage:
    """What one arm spent. The one mutable class here — it is a running tally.

    Registered in ``tests/test_frozen_dataclasses.py``'s ``ALLOWED_MUTABLE``
    rather than rebuilt frozen on every call: the backend that owns it is
    frozen, so its *identity* cannot be swapped mid-run, which is the
    invariant the immutability rule is protecting (the same shape as
    ``wiki_maintainer._LoopState``).

    Kept on the backend rather than derived from the telemetry JSONL because
    the replay's ``summary.json`` needs the arm's own numbers and the
    telemetry file is shared with whatever else wrote to that home.
    """

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    failures: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_tokens": self.cache_read_tokens,
            "cache_creation_tokens": self.cache_creation_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "failures": self.failures,
        }


@dataclass(frozen=True)
class _CallUsage:
    """One call's numbers, whichever field of the envelope carried them."""

    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read: int | None = None
    cache_creation: int | None = None
    cost_usd: float = 0.0


def _int(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def _read_usage(envelope: dict[str, Any], model: str) -> _CallUsage:
    """This arm's usage, preferring the per-model breakdown.

    ``claude -p`` bills more than one model per invocation — the 2026-09-02
    probe showed a claude-haiku-4-5 row alongside claude-opus-5 for session
    housekeeping. The arm's reading must be the arm's model alone, so
    ``modelUsage[model]`` wins when present; the flat ``usage`` block is the
    fallback for an envelope that does not carry the breakdown.
    """
    per_model = envelope.get("modelUsage")
    row = per_model.get(model) if isinstance(per_model, dict) else None
    if isinstance(row, dict):
        return _CallUsage(
            input_tokens=_int(row.get("inputTokens")),
            output_tokens=_int(row.get("outputTokens")),
            cache_read=_int(row.get("cacheReadInputTokens")),
            cache_creation=_int(row.get("cacheCreationInputTokens")),
            cost_usd=_float(row.get("costUSD")),
        )
    flat = envelope.get("usage")
    flat = flat if isinstance(flat, dict) else {}
    return _CallUsage(
        input_tokens=_int(flat.get("input_tokens")),
        output_tokens=_int(flat.get("output_tokens")),
        cache_read=_int(flat.get("cache_read_input_tokens")),
        cache_creation=_int(flat.get("cache_creation_input_tokens")),
        cost_usd=_float(envelope.get("total_cost_usd")),
    )


@dataclass(frozen=True)
class ClaudeCliBackend:
    """One isolated ``claude -p`` invocation per :meth:`generate` call.

    Frozen, with a mutable :class:`ClaudeUsage` inside: nothing may swap the
    model, the isolation settings or the tally out from under a running arm,
    while the tally's counters still grow. ``model`` and ``context_window``
    are plain fields, which is all the ``LLMBackend`` protocol's read-only
    properties ask for.
    """

    model: str
    scratch_dir: Path
    context_window: int = PAPER_CONTEXT_WINDOW
    claude_bin: str = "claude"
    timeout: int = 900
    audit_path: Path | None = None
    usage: ClaudeUsage = field(default_factory=ClaudeUsage)

    def generate(
        self,
        prompt: str,
        system: str,
        num_predict: int,
        format: dict | None,
        *,
        temperature: float = 1.0,
        think: bool = False,
    ) -> BackendResult | None:
        """One judgment, or ``None`` — which the wiki loops read as a fault.

        ``num_predict``, ``temperature`` and ``think`` are accepted and
        ignored (see the module docstring): the CLI exposes none of them, and
        a backend that pretended otherwise would make the arms' readings
        incomparable to the gemma arm's for a reason no log would name.
        """
        del num_predict, temperature, think  # no counterpart in `claude -p`
        payload = self._payload(prompt, system, format)
        self.scratch_dir.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, prompt on stdin
                self._argv(),
                input=payload,
                capture_output=True,
                encoding="utf-8",
                timeout=self.timeout,
                cwd=self.scratch_dir,
                env=self._env(),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return self._fail(payload, "timeout")
        except OSError as exc:
            logger.warning("claude CLI could not be spawned: %s", type(exc).__name__)
            return self._fail(payload, "spawn_error")

        if proc.returncode != 0:
            return self._fail(payload, f"exit_{proc.returncode}")
        try:
            envelope = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return self._fail(payload, "bad_envelope")
        if not isinstance(envelope, dict) or envelope.get("is_error"):
            return self._fail(payload, "is_error")

        text = envelope.get("result")
        if not isinstance(text, str) or not text.strip():
            return self._fail(payload, "empty_result")

        call = _read_usage(envelope, self.model)
        self._record(call)
        self._audit(payload, "response", extra={"usage": asdict(call)})
        stop = envelope.get("stop_reason")
        return BackendResult(
            text=text,
            finish_reason="length" if stop in _TRUNCATION_STOP_REASONS else stop,
            eval_count=call.output_tokens,
            prompt_tokens=call.input_tokens,
            cached_tokens=call.cache_read,
        )

    # ------------------------------------------------------------- internals

    def _argv(self) -> list[str]:
        return [
            self.claude_bin,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            "--setting-sources",
            "",
            "--tools",
            "",
            "--strict-mcp-config",
        ]

    def _env(self) -> dict[str, str]:
        env = {k: os.environ[k] for k in CLAUDE_ENV_ALLOWLIST if k in os.environ}
        env["DISABLE_AUTOUPDATER"] = "1"
        env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
        return env

    def _payload(self, prompt: str, system: str, format: dict | None) -> str:
        """System, schema and prompt as one stdin document.

        One document rather than ``--append-system-prompt``: argv is visible
        in ``ps`` and the episode sample is untrusted external content, which
        is the same reason the judge keeps its prompt on stdin.
        """
        parts = [system.strip()]
        if format is not None:
            parts.append(_SCHEMA_INSTRUCTION + "```json\n" + json.dumps(format, indent=2) + "\n```")
        parts.append(prompt)
        return "\n\n".join(part for part in parts if part) + "\n"

    def _record(self, call: _CallUsage) -> None:
        """Fold one call into the arm's tally (the one mutation this class makes)."""
        self.usage.calls += 1
        self.usage.input_tokens += call.input_tokens or 0
        self.usage.output_tokens += call.output_tokens or 0
        self.usage.cache_read_tokens += call.cache_read or 0
        self.usage.cache_creation_tokens += call.cache_creation or 0
        self.usage.cost_usd += call.cost_usd

    def _fail(self, payload: str, outcome: str) -> None:
        self.usage.failures += 1
        self._audit(payload, outcome)
        logger.warning("claude -p call failed: %s", outcome)
        return None

    def _audit(self, payload: str, outcome: str, *, extra: dict[str, Any] | None = None) -> None:
        """One row per attempt: what was asked (by hash), and what came of it.

        The prompt body is deliberately absent — the wiki loops already write
        it base64-encoded to their own audit JSONL, and a second copy here
        would be a second place for untrusted episode text to live.
        """
        if self.audit_path is None:
            return
        row: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "model": self.model,
            "prompt_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            "prompt_chars": len(payload),
            "outcome": outcome,
        }
        if extra:
            row.update(extra)
        try:
            self.audit_path.parent.mkdir(parents=True, exist_ok=True)
            with self.audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            logger.warning("claude -p audit row lost (outcome=%s)", outcome)
