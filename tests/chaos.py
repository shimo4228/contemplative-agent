"""Shared chaos fault-injection helpers (test-side only, ADR-0077).

Deterministic fault injection at the two existing seams — the ``LLMBackend``
Protocol (``ChaosBackend``) and the ``requests`` HTTP layer (``responses``
registration helpers) — plus hypothesis strategies for fault schedules and
schema-violating LLM output. No production hook is added: everything here
rides ``configure(backend=...)`` and library-level HTTP interception.

Determinism discipline:
- every fault schedule is either an explicit list or derived from a seed
  via ``ChaosBackend.from_seed`` (inspectable before the run);
- latency faults are expressed as injected ``ReadTimeout`` exceptions —
  the observable outcome of ``requests.post(..., timeout=...)`` expiring —
  so no test ever sleeps.
"""

from __future__ import annotations

import json
import math
import os
import random
from dataclasses import dataclass, field

import requests
import responses as responses_lib
from hypothesis import strategies as st

from contemplative_agent.core.llm import BackendResult

# ---------------------------------------------------------------------------
# Fault vocabulary
# ---------------------------------------------------------------------------

OK = "ok"
NONE = "none"  # backend hard failure: generate() returns None
EMPTY = "empty"  # whitespace-only text (treated as empty by llm.py)
EXC_TIMEOUT = "exc_timeout"  # raises requests.exceptions.ReadTimeout
EXC_CONNECTION = "exc_connection"  # raises requests.exceptions.ConnectionError
TRUNCATED = "truncated"  # finish_reason="length" (num_predict hit)
SHAPE_VIOLATION = "shape_violation"  # valid JSON, wrong {"patterns": [str]} shape
# Not a fault: a well-formed response carrying the model's verdict that the
# episode evidences nothing durable. Kept in the vocabulary so schedules mix
# it with real faults — the pipeline must keep the two apart (a routine week
# must never read as a backend outage), and only a schedule can prove that.
JUDGED_EMPTY = "judged_empty"

FAULT_VOCABULARY = (
    OK,
    NONE,
    EMPTY,
    EXC_TIMEOUT,
    EXC_CONNECTION,
    TRUNCATED,
    SHAPE_VIOLATION,
    JUDGED_EMPTY,
)

# Faults that surface to distill as generate() -> None (reason=llm_none).
# SHAPE_VIOLATION is the exception: generate() succeeds, the parse layer
# abstains. Kept here so schedule-driven tests can compute the expected
# per-reason tally from the schedule alone.
LLM_NONE_FAULTS = frozenset({NONE, EMPTY, EXC_TIMEOUT, EXC_CONNECTION, TRUNCATED})

# Faults that record a circuit-breaker FAILURE. TRUNCATED is absent by
# design: a length-capped generation is a successful call (audit M2), and
# SHAPE_VIOLATION fails at the parse layer after a successful call.
CIRCUIT_FAILING_FAULTS = frozenset({NONE, EMPTY, EXC_TIMEOUT, EXC_CONNECTION})


def trips_circuit(schedule: list[str], threshold: int) -> bool:
    """True when the schedule would open the circuit breaker mid-run.

    Schedule-driven pipeline tests that predict per-episode outcomes from
    the schedule alone must exclude such schedules — once the breaker opens,
    later OK entries short-circuit to None and the prediction breaks.
    """
    consecutive = 0
    for fault in schedule:
        if fault in CIRCUIT_FAILING_FAULTS:
            consecutive += 1
            if consecutive >= threshold:
                return True
        else:
            consecutive = 0
    return False


# ---------------------------------------------------------------------------
# ChaosBackend — LLMBackend-Protocol fault injector
# ---------------------------------------------------------------------------


@dataclass
class ChaosBackend:
    """Inject faults per an explicit, inspectable schedule.

    Each ``generate()`` call consumes ``schedule[call_index]``; calls beyond
    the schedule return OK. OK responses are valid ``{"patterns": [...]}``
    JSON derived deterministically from the call index, so schedule-driven
    pipeline tests can predict stored patterns exactly.
    """

    schedule: list[str] = field(default_factory=list)
    model: str = "chaos-model"
    context_window: int = 32768
    calls: list[dict] = field(default_factory=list)

    @classmethod
    def from_seed(
        cls,
        seed: int,
        n: int,
        weights: dict[str, float] | None = None,
    ) -> ChaosBackend:
        """Build a schedule of ``n`` faults from ``seed`` (deterministic).

        ``weights`` maps fault name -> relative weight (default: uniform over
        the full vocabulary). The schedule is materialized at construction so
        a failing test can print it verbatim for replay.
        """
        rng = random.Random(seed)
        vocab = list(weights.keys()) if weights else list(FAULT_VOCABULARY)
        wts = list(weights.values()) if weights else None
        schedule = rng.choices(vocab, weights=wts, k=n)
        return cls(schedule=schedule)

    def _ok_text(self, idx: int) -> str:
        # Long enough (>=30 chars, >=4 words) to clear _is_valid_pattern's
        # decision gate, so schedule-driven tests can predict stored counts.
        return json.dumps(
            {"patterns": [f"chaos ok pattern {idx} long enough to clear the validity gate"]}
        )

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
        idx = len(self.calls)
        self.calls.append(
            {
                "prompt": prompt,
                "system": system,
                "num_predict": num_predict,
                "format": format,
                "temperature": temperature,
                "think": think,
            }
        )
        fault = self.schedule[idx] if idx < len(self.schedule) else OK
        if fault == OK:
            return BackendResult(text=self._ok_text(idx))
        if fault == NONE:
            return None
        if fault == EMPTY:
            return BackendResult(text="   ")
        if fault == EXC_TIMEOUT:
            raise requests.exceptions.ReadTimeout("chaos: read timed out")
        if fault == EXC_CONNECTION:
            raise requests.exceptions.ConnectionError("chaos: connection refused")
        if fault == TRUNCATED:
            return BackendResult(text=self._ok_text(idx), finish_reason="length")
        if fault == SHAPE_VIOLATION:
            return BackendResult(text=json.dumps(["not", "the", "expected", "shape"]))
        if fault == JUDGED_EMPTY:
            return BackendResult(text=json.dumps({"patterns": []}))
        raise ValueError(f"unknown fault {fault!r}")


# ---------------------------------------------------------------------------
# TokenCountingChaosBackend — optional count_tokens capability, fault-injected
# ---------------------------------------------------------------------------

COUNT_OK = "count_ok"
COUNT_EXC = "count_exc"  # count_tokens() raises
COUNT_NONE = "count_none"  # returns None
COUNT_TYPE = "count_type"  # returns a non-int ("123")
COUNT_BOOL = "count_bool"  # returns True — an int subclass that is not a count
COUNT_NEGATIVE = "count_negative"  # returns -1
COUNT_ZERO = "count_zero"  # returns 0 for non-blank text (degenerate)
# Well-typed, positive, and wildly too small — a mis-calibrated tokenizer
# (wrong unit, off-by-orders divisor) rather than a broken one. Expresses only
# on text longer than MAX_CHARS_PER_TOKEN chars, since the check is a ratio.
COUNT_IMPLAUSIBLE = "count_implausible"

COUNT_FAULT_VOCABULARY = (
    COUNT_OK,
    COUNT_EXC,
    COUNT_NONE,
    COUNT_TYPE,
    COUNT_BOOL,
    COUNT_NEGATIVE,
    COUNT_ZERO,
    COUNT_IMPLAUSIBLE,
)

# Fault -> the reason code the guard must stamp on telemetry when it rejects
# that count and falls back to the estimator. Lets a schedule-driven test
# compute the expected reason from the schedule alone.
COUNT_FAULT_REASONS = {
    COUNT_EXC: "counter_exception",
    COUNT_NONE: "counter_none",
    COUNT_TYPE: "counter_type",
    COUNT_BOOL: "counter_type",
    COUNT_NEGATIVE: "counter_negative",
    COUNT_ZERO: "counter_degenerate",
    COUNT_IMPLAUSIBLE: "counter_implausible",
}


def real_token_count(text: str) -> int:
    """Stand-in for a real tokenizer: cheaper than ``_estimate_tokens``.

    ASCII at ~4 chars/tok and non-ASCII at ~1.1 tok/char, against the
    estimator's deliberately conservative 3 chars/tok and 2 tok/char. The
    resulting over-count ratio is ~1.33x for pure ASCII and ~1.82x for pure
    CJK — the band the 2026-08-01 Apple ``SystemLanguageModel.token_count``
    measurement found in production corpora (1.73-1.95x on Japanese-dominant
    input). Deterministic and dependency-free, so a fault test can predict
    the guard's arithmetic exactly.
    """
    ascii_count = sum(1 for ch in text if ord(ch) < 128)
    non_ascii = len(text) - ascii_count
    # Integer arithmetic throughout: ``ceil(n * 1.1)`` in float would make
    # 1200 -> 1321 (1320.0000000000002), and a test predicting the guard's
    # clamp value must not hinge on binary-float representation.
    return math.ceil(ascii_count / 4) + (non_ascii * 11 + 9) // 10


@dataclass
class TokenCountingChaosBackend(ChaosBackend):
    """``ChaosBackend`` plus the optional ``count_tokens`` capability.

    A separate class rather than a flag on ``ChaosBackend``: the base class
    must keep NOT satisfying ``TokenCountingBackend`` so the existing chaos
    suite keeps exercising the estimator path unchanged.

    ``count_schedule`` is consumed per ``count_tokens()`` call. The guard
    measures the system prompt first and the user prompt second and always
    attempts both (it validates after, not during), so within one guarded
    ``generate()`` index 0 is the system prompt and index 1 is the user
    prompt. Calls beyond the schedule return a clean count.
    """

    count_schedule: list[str] = field(default_factory=list)
    count_calls: list[str] = field(default_factory=list)

    def count_tokens(self, text: str) -> int:
        idx = len(self.count_calls)
        self.count_calls.append(text)
        fault = self.count_schedule[idx] if idx < len(self.count_schedule) else COUNT_OK
        if fault == COUNT_OK:
            return real_token_count(text)
        if fault == COUNT_EXC:
            raise RuntimeError("chaos: tokenizer unavailable")
        if fault == COUNT_NONE:
            return None  # type: ignore[return-value]
        if fault == COUNT_TYPE:
            return "123"  # type: ignore[return-value]
        if fault == COUNT_BOOL:
            return True  # type: ignore[return-value]
        if fault == COUNT_NEGATIVE:
            return -1
        if fault == COUNT_ZERO:
            return 0
        if fault == COUNT_IMPLAUSIBLE:
            return 1
        raise ValueError(f"unknown count fault {fault!r}")


def count_fault_schedules(min_size: int = 1, max_size: int = 6) -> st.SearchStrategy[list[str]]:
    """Sequences over the count-fault vocabulary."""
    return st.lists(st.sampled_from(COUNT_FAULT_VOCABULARY), min_size=min_size, max_size=max_size)


# ---------------------------------------------------------------------------
# responses helpers — requests-layer fault registration
# ---------------------------------------------------------------------------


def ollama_url(path: str) -> str:
    """Resolve the endpoint URL the code under test will actually hit."""
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    return f"{base}{path}"


def add_generate_429(rsps: responses_lib.RequestsMock, retry_after: str = "30") -> None:
    rsps.add(
        responses_lib.POST,
        ollama_url("/api/generate"),
        status=429,
        headers={"Retry-After": retry_after},
        json={"error": "rate limited"},
    )


def add_generate_timeout(rsps: responses_lib.RequestsMock) -> None:
    rsps.add(
        responses_lib.POST,
        ollama_url("/api/generate"),
        body=requests.exceptions.ReadTimeout("chaos: read timed out"),
    )


def add_embed_429(rsps: responses_lib.RequestsMock) -> None:
    rsps.add(
        responses_lib.POST,
        ollama_url("/api/embed"),
        status=429,
        json={"error": "rate limited"},
    )


def add_embed_timeout(rsps: responses_lib.RequestsMock) -> None:
    rsps.add(
        responses_lib.POST,
        ollama_url("/api/embed"),
        body=requests.exceptions.ReadTimeout("chaos: read timed out"),
    )


def add_embed_ragged(rsps: responses_lib.RequestsMock) -> None:
    """Rows of unequal dimension — np.asarray(dtype=float32) must fail."""
    rsps.add(
        responses_lib.POST,
        ollama_url("/api/embed"),
        status=200,
        json={"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5]]},
    )


def add_embed_short(rsps: responses_lib.RequestsMock, n_returned: int, dim: int = 4) -> None:
    """Fewer rows than requested texts (M < N) — parses fine, wrong length."""
    rsps.add(
        responses_lib.POST,
        ollama_url("/api/embed"),
        status=200,
        json={"embeddings": [[0.1] * dim for _ in range(n_returned)]},
    )


# ---------------------------------------------------------------------------
# hypothesis strategies
# ---------------------------------------------------------------------------

_SCALARS = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.text(max_size=40),
)


def non_patterns_json() -> st.SearchStrategy[str]:
    """JSON texts that parse but violate the ``{"patterns": [str, ...]}`` schema.

    Covers: top-level scalar / array / dict without "patterns", "patterns"
    that is not a list, and "patterns" lists containing non-string items
    (the structured-output schema says ``items: {"type": "string"}``, so a
    non-str item is a schema violation the backend let through).
    """
    wrong_top_level = st.one_of(
        _SCALARS,
        st.lists(_SCALARS, max_size=5),
        st.dictionaries(
            st.text(max_size=10).filter(lambda k: k != "patterns"),
            _SCALARS,
            max_size=4,
        ),
        st.fixed_dictionaries(
            {
                "patterns": st.one_of(
                    st.none(),
                    st.booleans(),
                    st.integers(),
                    st.text(max_size=20),
                    st.dictionaries(st.text(max_size=5), _SCALARS, max_size=3),
                )
            }
        ),
    )
    non_str_item = st.one_of(
        st.none(), st.booleans(), st.integers(), st.floats(allow_nan=False, allow_infinity=False)
    )
    patterns_with_non_str = st.fixed_dictionaries(
        {
            "patterns": st.lists(
                st.one_of(st.text(max_size=20), non_str_item),
                min_size=1,
                max_size=5,
            ).filter(lambda items: any(not isinstance(i, str) for i in items))
        }
    )
    return st.one_of(wrong_top_level, patterns_with_non_str).map(json.dumps)


def fault_schedules(min_size: int = 1, max_size: int = 12) -> st.SearchStrategy[list[str]]:
    """Sequences over the fault vocabulary (flapping, bursts, mixtures)."""
    return st.lists(st.sampled_from(FAULT_VOCABULARY), min_size=min_size, max_size=max_size)
