"""Backend abstraction for LLM generation: result DTOs, the pluggable
:class:`LLMBackend` protocol, shared sampling/window constants, and the
circuit breaker guarding every generation path."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal, Protocol, runtime_checkable

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

# Floor for the C2 num_predict clamp: when the input leaves fewer than this
# many output tokens, the remainder is too small to be worth a generation and
# the call is skipped instead. That refusal is the floor's ONLY job. It does
# not predict how long a usable answer is — that question is answered
# downstream by measurement, not here by guess: drop_truncated (audit M2) sees
# the actual done_reason=length and drops the fragment, so a call that turns
# out too short costs one generation rather than being refused in advance.
#
# 128 rests on three measured values, not an estimate: generate_for_api's own
# minimum (max_length/chars_per_token + 50), Ollama's default output length
# (128 — an unsent num_predict cuts there, which is why this code always sends
# one), and the observed size of what this agent actually emits (comment
# output p50 352 / p90 507 tokens, n=2,366, measured with a real tokenizer
# over reports/comment-reports/). A floor below 507 cannot turn a complete
# comment away at the door.
#
# The floor was 2048 until 2026-08-01 (ADR-0087 amendment). That value carried
# a second, unvalidated job — the prediction "a usable answer needs 2048
# tokens" — which measured ~6x over and, on a small-window backend, inverted
# into an input ceiling (50% of a 4,096 window). Only the prediction was
# retired.
#
# The clamp itself is load-bearing and must stay: num_predict reserves
# nothing, it is only a stop condition, so a value exceeding the remaining
# window lets generation run past the edge and Ollama evicts from the FRONT —
# the system prompt's value layer (identity / axioms) goes first. Clamping to
# the exact remainder stops generation at the boundary instead.
#
# Why a floor exists at all rather than clamping to whatever is left:
# 2026-07-09 showed the opposite failure. A 13-skill adoption grew the system
# prompt to ~20.3K tok and the then skip-only guard suppressed every self-post
# for 24+ hours while ~11.5K tok of output budget sat unused. Skipping is the
# expensive branch; it is reserved for remainders no generation can use.
MIN_CLAMPED_NUM_PREDICT = 128

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


@runtime_checkable
class TokenCountingBackend(LLMBackend, Protocol):
    """Optional capability: exact input-token counting for the C2 pre-flight.

    Deliberately NOT a member of :class:`LLMBackend`. Protocols are
    structural, so a member declared there is required of every implementer
    regardless of whether it carries a default body — and a backend with no
    tokenizer is legitimate (the built-in Ollama path; any HTTP-only
    provider). Requiring it would break the sibling ``contemplative-agent-cloud``
    / ``-mlx`` backends at type-check time for a capability they cannot
    honor. Splitting it out gives a backend that CAN count a typed target
    pyright verifies, while the guard resolves it structurally at runtime
    (``getattr`` + ``callable``) and falls back to ``_estimate_tokens``
    otherwise — the same tolerate-absence discipline as ``context_window``
    (ADR-0066), one layer looser.
    """

    def count_tokens(self, text: str) -> int:
        """Tokens *text* costs as input under the served model's tokenizer.

        Raising is permitted: the caller catches it, falls back to the
        estimator, and records the reason. A returned value that is not a
        plain non-negative ``int`` — ``None``, a ``str``, a ``bool``, a
        negative, or ``0`` for text that has content — is rejected the same
        way. The guard never trusts an implausible count because
        under-counting is the failure direction that sends over-window input
        into Ollama front-truncation or a memory-bounded backend's KV
        overrun, which is what the guard exists to prevent.
        """
        ...


# Reason codes stamped on telemetry when a backend counter existed but its
# value was not used. Absence of a counter is NOT in this vocabulary — that
# is the default, not a fallback from something.
TOKEN_COUNT_FALLBACK_REASONS = (
    "counter_exception",  # count_tokens() raised
    "counter_none",  # returned None
    "counter_type",  # returned a non-int (incl. bool, an int subclass)
    "counter_negative",  # returned a negative count
    "counter_degenerate",  # returned 0 for text that has content
    "counter_implausible",  # positive but below any real tokenizer's density
)

# Chars per token above which a reported count cannot be a real tokenization.
# A structural impossibility bound, NOT a calibration guess: no production BPE
# vocabulary contains tokens anywhere near 50 characters long, so a count
# implying a longer average token means the backend is reporting something
# other than tokens (wrong unit, wrong divisor, an order-of-magnitude bug).
# Deliberately far above any real density — a genuinely efficient tokenization
# of repetitive text must stay accepted, since a false rejection only loses the
# headroom and fills telemetry with faults that are not faults.
MAX_CHARS_PER_TOKEN = 50

# Output-budget headroom withheld when the input was counted for real.
# count_tokens() measures the two texts; the backend then renders them into a
# chat template whose role separators and control tokens no caller-side count
# sees. Clamping num_predict to the exact measured remainder would put
# input + output at precisely context_window and let that framing tip it over.
# Not applied on the estimator path, whose 1.73-1.95x over-count is already a
# reserve many times this size (ADR-0087).
BACKEND_FRAMING_RESERVE = 64

# Values of the telemetry field ``token_count_source``.
TOKEN_COUNT_SOURCE_BACKEND = "backend"
TOKEN_COUNT_SOURCE_ESTIMATOR = "estimator"


# Reason codes stamped on telemetry when a call requested a reasoning trace
# (``think=True``) and did not get a usable one. think=False is NOT in this
# vocabulary — a call that never asked has nothing to fall back from, and a
# reason on every production row would bury the real ones.
#
# Nor does this vocabulary say anything about a backend's NATURE. Each code is
# a statement about what was observed on THIS call, which is what keeps it
# valid if a capability marker ever lands (T-BACKEND-CONTRACT-KIT): a marker
# would only SUBTRACT ``trace_absent`` rows for backends that never claimed to
# produce traces, leaving the codes and their consumers unchanged.
ThinkingFallbackReason = Literal["trace_absent", "trace_blank", "trace_type"]

# think=True, but neither the dedicated field nor an inline <think> block
# carried anything. The generation itself succeeded.
TRACE_ABSENT: ThinkingFallbackReason = "trace_absent"
# A trace arrived and sanitization left nothing. In practice a whitespace-only
# trace: _scrub_secrets REPLACES matches with "[REDACTED]" rather than deleting
# them, so a trace that was entirely a credential survives as non-empty.
# Separate from trace_absent because the diagnosis differs — the channel worked
# and the content did not, which is a model behavior rather than a backend bug.
TRACE_BLANK: ThinkingFallbackReason = "trace_blank"
# The dedicated trace field was not a str. Rejected BEFORE _sanitize_thinking,
# which would otherwise reach re.sub()/str.lower() on a non-str and raise —
# after the caller had already stamped outcome="ok".
TRACE_TYPE: ThinkingFallbackReason = "trace_type"

THINKING_FALLBACK_REASONS: tuple[ThinkingFallbackReason, ...] = (
    TRACE_ABSENT,
    TRACE_BLANK,
    TRACE_TYPE,
)

# Values of the telemetry field ``thinking_source``: which channel the captured
# trace came from, or that none did. None (the field's default) means the
# capture guard never ran — think=False, or a call that failed before it.
# Deliberately not "backend": TOKEN_COUNT_SOURCE_BACKEND already spends that
# word on the injected backend's tokenizer, while this channel covers the
# built-in Ollama response field too. The name says which channel, not who.
THINKING_SOURCE_FIELD = "field"
THINKING_SOURCE_INLINE = "inline"
THINKING_SOURCE_ABSENT = "absent"


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


@dataclass(frozen=True)
class CircuitReading:
    """Read-only view of the breaker's state at one instant.

    An instrument in the ADR-0071 sense: a reading over existing state that
    adds no mechanism and feeds no gate. It exists because the conformance
    kit (``contemplative_agent.testing``) has to assert which calls the
    breaker counted — "a truncation drop is not a failure" is a claim about
    the counter, and no black-box observation expresses it without also
    exercising the threshold, which is a different claim.

    Before this, the sibling backends read ``_circuit._consecutive_failures``
    directly, so a rename inside :class:`_CircuitBreaker` broke three
    repositories silently. The reading is the supported surface; the
    attribute names behind it are not.
    """

    consecutive_failures: int
    is_open: bool


def circuit_reading() -> CircuitReading:
    """Return the breaker's current :class:`CircuitReading`.

    Reading ``is_open`` consults the cooldown clock exactly as the guarded
    generation path does, so a reading taken after the cooldown elapsed
    reports the half-open state (``consecutive_failures`` still at the
    threshold, ``is_open`` False) rather than a contradiction.
    """
    return CircuitReading(
        consecutive_failures=_circuit._consecutive_failures,
        is_open=_circuit.is_open,
    )


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
