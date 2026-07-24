"""Backend abstraction for LLM generation: result DTOs, the pluggable
:class:`LLMBackend` protocol, shared sampling/window constants, and the
circuit breaker guarding every generation path."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Default Ollama settings — overridden by adapter config or env vars
_DEFAULT_OLLAMA_URL = "http://localhost:11434"
# Production generation model. gemma4:e4b supersedes qwen3.5:9b (ADR-0069):
# the think-on/off A/B (docs/evidence/adr-0068/) ranks gemma > qwen on quality
# and gemma think-OFF is faster (0.65x). Embedding stays nomic-embed-text via the
# separate OLLAMA_EMBEDDING_MODEL knob (core/embeddings.py) — this default is
# generation-only. Revert: set OLLAMA_MODEL=qwen3.5:9b (no code change needed,
# launchd plists pin no model). gemma's 128K context >> NUM_CTX (32768), so the
# context-budget assumptions are unchanged.
_DEFAULT_OLLAMA_MODEL = "gemma4:e4b"

CIRCUIT_FAILURE_THRESHOLD = 5
CIRCUIT_COOLDOWN_SECONDS = 120

NUM_CTX = 32768  # Ollama context window (input + output share it). audit C2.

# Floor for the C2 num_predict clamp: when the input leaves less than this
# many output tokens, clamping would yield a generation so short that publish
# paths drop it anyway (done_reason=length → audit M2), so the call is skipped
# instead. 2048 tok ≈ 3-6K chars — comfortably above real post/comment sizes
# (production p90 post ≈ 2,400 chars), so a clamp that survives this floor
# still serves full-size content. 2026-07-09 regression: a 13-skill adoption
# grew the system prompt to ~20.3K tok and the old skip-only guard suppressed
# every self-post for 24+ hours despite ~11.5K tok of usable output budget.
MIN_CLAMPED_NUM_PREDICT = 2048

# Fixed sampling policy shared by EVERY backend (single source of truth). The
# per-call temperature flows through LLMBackend.generate(); top_p/top_k are the
# fixed nucleus + top-k clip applied identically on the built-in Ollama path
# and every injected backend (which imports these).
# Defined once so the backends cannot drift: a backend that silently omits
# these lets high-temperature generation (e.g. COMMENT_TEMPERATURE=1.3)
# degenerate into repetition loops that never emit EOS and run to num_predict.
SAMPLING_TOP_P = 0.95
SAMPLING_TOP_K = 20


@dataclass(frozen=True)
class BackendResult:
    """Raw generation result from an injected :class:`LLMBackend`.

    ``finish_reason`` mirrors Ollama's ``done_reason``: the value
    ``"length"`` signals the output hit ``num_predict`` mid-generation,
    which drives the ``drop_truncated`` fail-closed gate in the caller
    (audit M2). ``eval_count`` (generated-token count) feeds telemetry
    parity with the Ollama path. ``prompt_tokens`` (total input tokens) and
    ``cached_tokens`` (prompt-cache hits; ``cached_tokens / prompt_tokens``
    = the per-call cache-hit rate) let telemetry tell a prompt-cache-churn
    slowdown apart from a memory-pressure cliff. All optional: a backend
    that cannot report a field leaves it ``None`` and only loses the gate /
    telemetry detail, never correctness of the returned text.

    ``thinking`` carries the model's reasoning trace when a thinking-capable
    backend was called with ``think=True`` (None otherwise). It is NOT part of
    the published ``text`` — the caller persists it separately (episode log)
    rather than emitting it externally.
    """

    text: str
    finish_reason: str | None = None
    eval_count: int | None = None
    prompt_tokens: int | None = None
    cached_tokens: int | None = None
    thinking: str | None = None


@dataclass(frozen=True)
class GenerationOutput:
    """Sanitized generation result surfaced to publish-path callers.

    ``text`` is the sanitized, publishable output (None only on the
    truncation-drop / failure paths that previously returned None). ``thinking``
    is the model's reasoning trace when the call ran with ``think=True``,
    already scrubbed of credential/forbidden patterns but NOT emitted
    externally — publish-path callers attach it to the episode log alongside
    ``internal_note`` (untrusted regime: distilled-only read-back). Default
    ``None`` keeps it absent under the production ``think=False`` default.
    """

    text: str | None
    thinking: str | None = None


@runtime_checkable
class LLMBackend(Protocol):
    """Pluggable generation backend.

    Default (``_backend = None``) uses the built-in Ollama HTTP path. An
    external package (e.g. ``contemplative-agent-cloud``) can inject a backend
    implementation via ``configure(backend=...)`` to route generation through a
    different provider. Sanitization, circuit breaker, truncation gating, and
    untrusted-content wrapping remain in the ``core.llm`` package and apply
    uniformly regardless of backend.
    """

    @property
    def model(self) -> str:
        """Served model id recorded in per-call telemetry
        (``llm-calls-{date}.jsonl``). A read-only property so a ``frozen=True``
        backend dataclass satisfies it; declaring it on the protocol lets
        telemetry group by the actual served model across every backend —
        matching the Ollama default's ``_get_model()`` — instead of a
        class-name sentinel. pyright flags any injected backend that omits it."""
        ...

    @property
    def context_window(self) -> int:
        """Effective input+output token budget for the pre-flight guard
        (audit C2) — the ceiling the host can actually serve, NOT the model's
        native window. A cloud backend reports its provider's real context
        limit; a memory-bounded local backend reports the ceiling the host can
        actually serve. Declared here so pyright nudges every
        backend to supply it; the guard still tolerates its absence (the
        caller falls back to None and skips the check), so a not-yet-updated
        external backend keeps delegating unguarded."""
        ...

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
        """Return a :class:`BackendResult`, or None on failure.

        ``temperature`` is forwarded from the caller so backends honor the
        per-call sampling temperature (e.g. 0.0 for deterministic
        verification, 1.3 for outward reflective generation). The truncation
        decision (``drop_truncated``) is made by the caller from
        ``finish_reason``, so implementations need not gate on it.

        ``think`` requests the model's reasoning trace (default False = the
        production behavior). A backend that honors it returns the trace in
        ``BackendResult.thinking``; one that cannot should still accept the
        kwarg and leave ``thinking`` None. The caller always passes ``think=``,
        so every implementer must accept it (or ``**kwargs``): a backend whose
        signature lacks both raises ``TypeError`` at call time — this is a
        required signature update, not a graceful degrade.

        Implementations must not apply sanitization — the caller handles
        ``_sanitize_output`` uniformly across backends.
        """
        ...


class _CircuitBreaker:
    """Simple circuit breaker for LLM requests.

    Opens after CIRCUIT_FAILURE_THRESHOLD consecutive failures,
    auto-resets after CIRCUIT_COOLDOWN_SECONDS.
    """

    def __init__(self) -> None:
        self._consecutive_failures: int = 0
        self._opened_at: float = 0.0
        self._shield_depth: int = 0

    @property
    def is_open(self) -> bool:
        if self._consecutive_failures < CIRCUIT_FAILURE_THRESHOLD:
            return False
        elapsed = time.time() - self._opened_at
        if elapsed >= CIRCUIT_COOLDOWN_SECONDS:
            # Cooldown elapsed, allow a retry (half-open)
            return False
        return True

    def record_failure(self) -> None:
        if self._shield_depth > 0:
            return
        self._consecutive_failures += 1
        if self._consecutive_failures >= CIRCUIT_FAILURE_THRESHOLD:
            self._opened_at = time.time()
            logger.warning(
                "Circuit breaker OPEN after %d consecutive failures. Cooldown %ds.",
                self._consecutive_failures,
                CIRCUIT_COOLDOWN_SECONDS,
            )

    def record_success(self) -> None:
        if self._shield_depth > 0:
            return
        if self._consecutive_failures > 0:
            logger.info("Circuit breaker reset after successful request")
        self._consecutive_failures = 0
        self._opened_at = 0.0

    def reset(self) -> None:
        """Reset circuit breaker state. Useful for testing."""
        self._consecutive_failures = 0
        self._opened_at = 0.0


_circuit = _CircuitBreaker()


@contextmanager
def circuit_shield() -> Iterator[None]:
    """Suspend circuit-breaker *accounting* for the duration of the block.

    For observability-only LLM calls (ADR-0076 shadow skill selection): an
    instrument's own failures must never open the circuit that guards the
    publish-path generation it observes — without this, a repeatedly
    failing selector call would trip the breaker and the subsequent
    comment/reply/post generation would be skipped as ``circuit_open``
    (codex review 2026-07-10 P2). Only ``record_failure`` /
    ``record_success`` become no-ops; ``is_open`` is still honored, so a
    shielded call cannot un-trip or sneak past an already-open circuit.
    Depth-counted so nested shields compose; single-process agent, so no
    thread-safety concern.
    """
    _circuit._shield_depth += 1
    try:
        yield
    finally:
        _circuit._shield_depth -= 1
