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

FAULT_VOCABULARY = (
    OK,
    NONE,
    EMPTY,
    EXC_TIMEOUT,
    EXC_CONNECTION,
    TRUNCATED,
    SHAPE_VIOLATION,
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
        raise ValueError(f"unknown fault {fault!r}")


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
