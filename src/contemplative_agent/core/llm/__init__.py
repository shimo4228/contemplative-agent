"""Local LLM interface via Ollama REST API.

Package layout (ADR-0079): this ``__init__`` is the permanent facade — the
public import path ``contemplative_agent.core.llm`` is API for the sibling
backends (contemplative-agent-cloud / -mlx) and every internal caller, so
all public symbols are re-exported here regardless of which submodule they
live in. Generation routing and the transport-side mutable configuration
stay in this module; the Ollama HTTP transport is :class:`.ollama.OllamaBackend`
(the default ``LLMBackend``, P1-06.1); :mod:`.backend` holds the
backend protocol + circuit breaker, :mod:`.prompting` the system-prompt
assembly (and owns the prompt-side mutable state), :mod:`.guard` the
security guards (SSRF, secret scrubbing, untrusted wrapping).
"""

from __future__ import annotations

import hashlib
import logging
import math
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# Facade re-exports (ADR-0079): the `X as X` redundant-alias form marks each
# name as an intentional part of the public `core.llm` surface — including the
# underscore names that tests and siblings import — so ruff/pyright treat them
# as re-exports rather than unused imports.
from .._io import append_jsonl_restricted, now_iso
from ..env import env_get
from . import prompting
from .backend import (
    BACKEND_FRAMING_RESERVE as BACKEND_FRAMING_RESERVE,
    CIRCUIT_COOLDOWN_SECONDS as CIRCUIT_COOLDOWN_SECONDS,
    CIRCUIT_FAILURE_THRESHOLD as CIRCUIT_FAILURE_THRESHOLD,
    DEFAULT_OLLAMA_MODEL as DEFAULT_OLLAMA_MODEL,
    DEFAULT_OLLAMA_URL as DEFAULT_OLLAMA_URL,
    MAX_CHARS_PER_TOKEN as MAX_CHARS_PER_TOKEN,
    MIN_CLAMPED_NUM_PREDICT as MIN_CLAMPED_NUM_PREDICT,
    NUM_CTX as NUM_CTX,
    SAMPLING_TOP_K as SAMPLING_TOP_K,
    SAMPLING_TOP_P as SAMPLING_TOP_P,
    THINKING_FALLBACK_REASONS as THINKING_FALLBACK_REASONS,
    THINKING_SOURCE_ABSENT as THINKING_SOURCE_ABSENT,
    THINKING_SOURCE_FIELD as THINKING_SOURCE_FIELD,
    THINKING_SOURCE_INLINE as THINKING_SOURCE_INLINE,
    TOKEN_COUNT_FALLBACK_REASONS as TOKEN_COUNT_FALLBACK_REASONS,
    TOKEN_COUNT_SOURCE_BACKEND as TOKEN_COUNT_SOURCE_BACKEND,
    TOKEN_COUNT_SOURCE_ESTIMATOR as TOKEN_COUNT_SOURCE_ESTIMATOR,
    TRACE_ABSENT as TRACE_ABSENT,
    TRACE_BLANK as TRACE_BLANK,
    TRACE_TYPE as TRACE_TYPE,
    BackendResult as BackendResult,
    CircuitReading as CircuitReading,
    GenerationOutput as GenerationOutput,
    InputTokenMeasurement as InputTokenMeasurement,
    LLMBackend as LLMBackend,
    ThinkingCapture as ThinkingCapture,
    ThinkingFallbackReason as ThinkingFallbackReason,
    TokenCountingBackend as TokenCountingBackend,
    capture_thinking as capture_thinking,
    circuit_breaker as circuit_breaker,
    circuit_reading as circuit_reading,
    circuit_shield as circuit_shield,
    measure_input_tokens as measure_input_tokens,
)
from .decision import (
    DECISION_REASONS as DECISION_REASONS,
    LABEL_ALPHABET as LABEL_ALPHABET,
    OLLAMA_TOP_LOGPROBS_CAP as OLLAMA_TOP_LOGPROBS_CAP,
    REASON_ANSWERED as REASON_ANSWERED,
    ChoiceQuestion as ChoiceQuestion,
    DecisionBackend as DecisionBackend,
    DecisionQuestion as DecisionQuestion,
    DecisionRequest as DecisionRequest,
    DecisionResult as DecisionResult,
    NoulQuestion as NoulQuestion,
    OllamaLogprobsDecisionBackend as OllamaLogprobsDecisionBackend,
    QuestionAnswer as QuestionAnswer,
    ScoreQuestion as ScoreQuestion,
    batch_reason as batch_reason,
    binary_softmax as binary_softmax,
    label_alphabet as label_alphabet,
)
from .guard import (
    DEFAULT_MARKER_COMPLETE as DEFAULT_MARKER_COMPLETE,
    DEFAULT_MARKER_TRUNCATED as DEFAULT_MARKER_TRUNCATED,
    DEFAULT_UNTRUSTED_FRAME as DEFAULT_UNTRUSTED_FRAME,
    INJECTION_TOKENS as INJECTION_TOKENS,
    LOCALHOST_HOSTS as LOCALHOST_HOSTS,
    MAX_THINKING_CHARS as MAX_THINKING_CHARS,
    configure_untrusted_guard as configure_untrusted_guard,
    extract_inline_thinking as extract_inline_thinking,
    nonce_stable_digest as nonce_stable_digest,
    reset_untrusted_guard as reset_untrusted_guard,
    sanitize_output as sanitize_output,
    sanitize_thinking as sanitize_thinking,
    scrub_secrets as scrub_secrets,
    strip_injection_tokens as strip_injection_tokens,
    strip_thinking as strip_thinking,
    validate_trusted_url as validate_trusted_url,
    wrap_untrusted_content as wrap_untrusted_content,
)
from .ollama import (
    OllamaBackend,
    OllamaRequestError,
    drop_for_output_truncation,
    finalize_ok,
)
from .prompting import (
    DEFAULT_LEARNED_RULES_FRAMING as DEFAULT_LEARNED_RULES_FRAMING,
    DEFAULT_LEARNED_SKILLS_FRAMING as DEFAULT_LEARNED_SKILLS_FRAMING,
    MD_CACHE as MD_CACHE,
    SystemBudgetReading as SystemBudgetReading,
    build_system_prompt as build_system_prompt,
    build_system_prompt_with_skills as build_system_prompt_with_skills,
    estimate_input_tokens as estimate_input_tokens,
    get_distill_system_prompt as get_distill_system_prompt,
    get_identity_system_prompt as get_identity_system_prompt,
    load_md_files as load_md_files,
    system_prompt_budget_reading as system_prompt_budget_reading,
    validate_identity_content as validate_identity_content,
)
from .request import (
    DEFAULT_NUM_PREDICT as DEFAULT_NUM_PREDICT,
    GenerationRequest as GenerationRequest,
    ResolvedRequest as ResolvedRequest,
)

# The declared public surface of ``core.llm`` (P1-06.3). Underscore names are not
# part of it: callers import the public name or the submodule.
__all__ = [
    "BACKEND_FRAMING_RESERVE",
    "BackendResult",
    "CIRCUIT_COOLDOWN_SECONDS",
    "CIRCUIT_FAILURE_THRESHOLD",
    "ChoiceQuestion",
    "CircuitReading",
    "DECISION_REASONS",
    "DEFAULT_LEARNED_RULES_FRAMING",
    "DEFAULT_LEARNED_SKILLS_FRAMING",
    "DEFAULT_MARKER_COMPLETE",
    "DEFAULT_MARKER_TRUNCATED",
    "DEFAULT_NUM_PREDICT",
    "DEFAULT_OLLAMA_MODEL",
    "DEFAULT_OLLAMA_URL",
    "DEFAULT_UNTRUSTED_FRAME",
    "DecisionBackend",
    "DecisionQuestion",
    "DecisionRequest",
    "DecisionResult",
    "GenerationOutput",
    "GenerationRequest",
    "INJECTION_TOKENS",
    "InputTokenMeasurement",
    "LABEL_ALPHABET",
    "LLMBackend",
    "LOCALHOST_HOSTS",
    "MAX_CHARS_PER_TOKEN",
    "MAX_THINKING_CHARS",
    "MD_CACHE",
    "MIN_CLAMPED_NUM_PREDICT",
    "NUM_CTX",
    "NoulQuestion",
    "OLLAMA_TOP_LOGPROBS_CAP",
    "OllamaBackend",
    "OllamaLogprobsDecisionBackend",
    "OllamaRequestError",
    "QuestionAnswer",
    "REASON_ANSWERED",
    "ResolvedRequest",
    "SAMPLING_TOP_K",
    "SAMPLING_TOP_P",
    "SERVING_ENV_KEYS",
    "ScoreQuestion",
    "SystemBudgetReading",
    "THINKING_FALLBACK_REASONS",
    "THINKING_SOURCE_ABSENT",
    "THINKING_SOURCE_FIELD",
    "THINKING_SOURCE_INLINE",
    "TOKEN_COUNT_FALLBACK_REASONS",
    "TOKEN_COUNT_SOURCE_BACKEND",
    "TOKEN_COUNT_SOURCE_ESTIMATOR",
    "TRACE_ABSENT",
    "TRACE_BLANK",
    "TRACE_TYPE",
    "ThinkingCapture",
    "ThinkingFallbackReason",
    "TokenCountingBackend",
    "batch_reason",
    "binary_softmax",
    "build_system_prompt",
    "build_system_prompt_with_skills",
    "capture_thinking",
    "circuit_breaker",
    "circuit_reading",
    "circuit_shield",
    "configure",
    "configure_untrusted_guard",
    "decide",
    "decision_backend_name",
    "decision_model_name",
    "emit_llm_telemetry",
    "estimate_input_tokens",
    "extract_inline_thinking",
    "generate",
    "generate_for_api",
    "generate_full",
    "generate_request",
    "get_distill_system_prompt",
    "get_identity_system_prompt",
    "get_ollama_model",
    "get_ollama_url",
    "label_alphabet",
    "load_md_files",
    "measure_backend_input_tokens",
    "measure_input_tokens",
    "nonce_stable_digest",
    "ollama_model",
    "reset_llm_config",
    "reset_untrusted_guard",
    "sanitize_output",
    "sanitize_thinking",
    "scrub_secrets",
    "served_model",
    "serving_environment",
    "strip_injection_tokens",
    "strip_thinking",
    "system_prompt_budget_reading",
    "validate_identity_content",
    "validate_trusted_url",
    "wrap_untrusted_content",
]

logger = logging.getLogger(__name__)

# Module-level settings — set by configure() from the adapter. Transport-side
# state only; prompt-side state is owned by .prompting (single owner).
_ollama_base_url: str = DEFAULT_OLLAMA_URL
_ollama_model: str = DEFAULT_OLLAMA_MODEL
_backend: LLMBackend | None = None  # an INJECTED backend; None = the built-in Ollama one
# The default backend (stateless; model and URL are resolved per call). Kept
# apart from ``_backend`` so "injected" keeps its meaning for ``served_model``,
# ``serving_environment`` and the novelty window.
_OLLAMA = OllamaBackend()
# ADR-0112: the judgment seam. None — the default — means no backend: no
# call, no telemetry, and :func:`decide` answers None. Its one caller, the
# relevance gate (ADR-0113 amendment 3), fails closed on that — no backend is
# no engagement, never a fallback judgment.
_decision_backend: DecisionBackend | None = None
_telemetry_dir: Path | None = None
# Per-process cache for serving_environment(); None until first call.
_serving_env: dict[str, Any] | None = None


def configure(
    *,
    identity_path: Path | None = None,
    ollama_base_url: str | None = None,
    ollama_model: str | None = None,
    default_system_prompt: str | None = None,
    axiom_prompt: str | None = None,
    skills_dir: Path | None = None,
    rules_dir: Path | None = None,
    backend: LLMBackend | None = None,
    decision_backend: DecisionBackend | None = None,
    telemetry_dir: Path | None = None,
) -> None:
    """Configure LLM module with adapter-specific settings.

    Called by the adapter (e.g. Moltbook) at startup to inject
    platform-specific paths and URLs.

    Args:
        axiom_prompt: Contemplative Constitutional AI clauses (Appendix C).
            Appended to the identity/system prompt for CCAI alignment.
        skills_dir: Directory containing learned skill .md files.
            Skill contents are appended to the system prompt.
        rules_dir: Directory containing learned behavioral rule .md files.
            Rule contents are appended to the system prompt.
        backend: Optional ``LLMBackend`` implementation. When set, all
            ``generate()`` calls route through it instead of the built-in
            Ollama HTTP path. Sanitization and circuit breaker continue
            to apply. Main-repo default is ``None`` (local Ollama only);
            external add-ons may inject a provider here.
        decision_backend: Optional ``DecisionBackend`` (ADR-0112). ``None``
            (the default, and what ``reset_llm_config`` restores) leaves no
            backend — :func:`decide` returns None and nothing is sent. The
            CLI constructs one unless ``DECISION_MODEL`` is set empty.
        telemetry_dir: Directory for per-call telemetry JSONL
            (``llm-calls-{date}.jsonl``). ``None`` (default) disables
            telemetry. Records carry call metadata only, never the prompt
            body (see ``emit_llm_telemetry``).
    """
    global _ollama_base_url, _ollama_model, _backend, _decision_backend
    global _telemetry_dir, _serving_env
    # Any of these can change which daemon / which model is serving.
    _serving_env = None
    prompting.configure_prompting(
        identity_path=identity_path,
        default_system_prompt=default_system_prompt,
        axiom_prompt=axiom_prompt,
        skills_dir=skills_dir,
        rules_dir=rules_dir,
    )
    if ollama_base_url is not None:
        _ollama_base_url = ollama_base_url
    if ollama_model is not None:
        _ollama_model = ollama_model
    if backend is not None:
        _backend = backend
    if decision_backend is not None:
        _decision_backend = decision_backend
    if telemetry_dir is not None:
        _telemetry_dir = telemetry_dir


def reset_llm_config() -> None:
    """Reset module-level LLM config and circuit breaker to defaults. Useful for testing."""
    global _ollama_base_url, _ollama_model, _backend, _decision_backend
    global _telemetry_dir, _serving_env
    prompting.reset_prompting()
    _ollama_base_url = DEFAULT_OLLAMA_URL
    _ollama_model = DEFAULT_OLLAMA_MODEL
    _backend = None
    _decision_backend = None
    _telemetry_dir = None
    _serving_env = None
    circuit_breaker.reset()


def get_ollama_url() -> str:
    url = env_get("OLLAMA_BASE_URL", _ollama_base_url)
    return validate_trusted_url(url, source="OLLAMA_BASE_URL")


def get_ollama_model() -> str:
    return env_get("OLLAMA_MODEL", _ollama_model)


def ollama_model() -> str:
    """The Ollama generation model (``OLLAMA_MODEL``, else the configured one).

    What the built-in Ollama path generates with, whether or not a sibling
    ``LLMBackend`` is injected — unlike :func:`served_model`, which then names
    the injected backend's model (a cloud or MLX id Ollama cannot serve).
    """
    return get_ollama_model()


def served_model() -> str:
    """The model id actually serving generation, across any backend.

    An injected ``LLMBackend`` declares its served model via the ``model``
    contract; the built-in Ollama path uses ``get_ollama_model()``. Single source of
    truth for per-call telemetry and the snapshot manifest (ADR-0069), so both
    record the same served model regardless of backend.
    """
    return _backend.model if _backend is not None else get_ollama_model()


def decision_backend_name() -> str | None:
    """Class name of the configured ``DecisionBackend``, or None when unset.

    The record field that names which judge wrote a row (ADR-0112). It is the
    class rather than the model because two backends can serve the same model
    id through different interfaces — a logprobs readout and a trained head
    are not the same judge.
    """
    return type(_decision_backend).__name__ if _decision_backend is not None else None


def decision_model_name() -> str | None:
    """The configured ``DecisionBackend``'s model id, or None when unset.

    Read before any question is asked — e.g. to pin a remembered answer to
    the judge that gave it (RFC-0046 S38) — where :func:`decide`'s
    ``result.model`` only exists after a call.
    """
    return _decision_backend.model if _decision_backend is not None else None


def decide(
    state: str,
    questions: tuple[DecisionQuestion, ...],
    *,
    caller: str,
    system: str = "",
) -> DecisionResult | None:
    """Ask the configured :class:`DecisionBackend` one batch of questions.

    Returns ``None`` **only** when no backend is configured (``DECISION_MODEL``
    set empty) — what lets a caller write "unconfigured" into its record
    without asking a second question. Every other outcome, the
    breaker included, comes back as a :class:`DecisionResult` carrying a
    reason from :data:`DECISION_REASONS`.

    The shared circuit breaker is read, never written: this path is
    observability, and an instrument's failures must not open the circuit that
    guards the generation it observes (the rule ``circuit_shield`` enforces for
    the shadow selector). A backend that raises, or that returns ``None``
    instead of a named abstain, degrades to ``backend_exception``.

    One telemetry row per batch, not per question: the batch is the unit a
    caller scheduled and the unit whose latency the shadow reading prices, and
    a row per question would bury the generation rows around it.
    """
    if _decision_backend is None:
        return None
    backend = _decision_backend
    tel: dict[str, Any] = {
        "ts": now_iso(timespec="seconds"),
        # The one field that separates this family from the generation rows
        # sharing the file. Absent on those rows, which read as generation.
        "kind": "decision",
        "caller": caller,
        "model": backend.model,
        "duration_ms": None,
        "outcome": "error",
        "question_count": len(questions),
        "answered_count": 0,
        # Metadata only, never the state body: the state embeds untrusted
        # external content, and telemetry is read back by analysis sessions.
        "prompt_chars": len(state),
        "prompt_norm_sha256": nonce_stable_digest(state),
        "num_predict": 1,
        "temperature": 0.0,
        "decision_reason": None,
    }
    started = time.monotonic()
    # One try around the call AND the reading of its result: a backend that
    # returns something DecisionResult-shaped but not a DecisionResult raises
    # where the fields are read, not where it is called, and an escape from
    # here reaches the caller's own handler, which then has to tell a broken
    # backend from a broken caller.
    try:
        if circuit_breaker.is_open:
            logger.debug("Circuit breaker open — skipping decision request")
            result = DecisionResult(
                model=backend.model, latency_ms=0, answers=(), reason="circuit_open"
            )
        else:
            result = backend.decide(state, questions, system=system) or DecisionResult(
                model=backend.model,
                latency_ms=int((time.monotonic() - started) * 1000),
                answers=(),
                reason="backend_exception",
            )
        answered = sum(1 for a in result.answers if a.reason == REASON_ANSWERED)
        reason = result.reason
    except Exception as exc:
        logger.warning("Decision backend failed (generation unaffected): %s", exc)
        result = DecisionResult(
            model=backend.model,
            latency_ms=int((time.monotonic() - started) * 1000),
            answers=(),
            reason="backend_exception",
        )
        answered, reason = 0, result.reason
    tel["duration_ms"] = int((time.monotonic() - started) * 1000)
    tel["answered_count"] = answered
    tel["decision_reason"] = reason
    # Coarse verdict in the vocabulary the generation rows already use, so a
    # reading can count outcomes across both families; decision_reason carries
    # the fine-grained diagnosis.
    if answered or reason == REASON_ANSWERED:
        tel["outcome"] = "ok"
    elif reason in ("circuit_open", "budget_exceeded"):
        tel["outcome"] = reason
        if reason == "budget_exceeded":
            # Which budget: ``time`` or ``context`` (P1-07.9). Sparse.
            kind = next(
                (k for a in result.answers if (k := getattr(a, "error_kind", None))), None
            )
            if kind:
                tel["error_kind"] = kind
    emit_llm_telemetry(tel)
    return result


# Digest prefix length. Same convention as ``prompt_sha256`` in the telemetry
# record: 12 hex distinguishes any two weights that were ever pulled here.
_DIGEST_PREFIX = 12
# Connect-biased: a hung-but-connected daemon must not hold session start for
# long on a purely observational read.
_SERVING_ENV_TIMEOUT = (2, 5)
SERVING_ENV_KEYS = (
    "ollama_version",
    "generation_model_digest",
    "embedding_model_digest",
    "serving_environment_reason",
)


def _normalize_tag(name: str) -> str:
    """``/api/tags`` lists every model with an explicit tag (``:latest`` when
    the pull omitted one) while config may name the bare model."""
    return name if ":" in name else f"{name}:latest"


def _ollama_metadata(path: str) -> object:
    """One GET against the trusted Ollama URL. Raises on transport failure or
    non-JSON body; the caller turns that into a reason code."""
    base = get_ollama_url()
    return requests.get(f"{base}{path}", timeout=_SERVING_ENV_TIMEOUT, allow_redirects=False).json()


def _fetch_ollama_metadata() -> tuple[object, object, str | None]:
    """``(version_body, tags_body, reason)``. Both bodies are ``None`` with a
    reason when either call fails: a version read cannot be attributed to
    "this run" once the listing next to it was not obtained."""
    try:
        return _ollama_metadata("/api/version"), _ollama_metadata("/api/tags"), None
    except requests.RequestException as exc:
        logger.info("serving_environment: Ollama unreachable: %s", exc)
        return None, None, "ollama_unreachable"
    except ValueError as exc:  # non-JSON body
        logger.info("serving_environment: Ollama returned non-JSON: %s", exc)
        return None, None, "ollama_malformed_response"


def _digests_from_tags(tags: object) -> dict[str, str] | None:
    """``{tag: digest_prefix}`` from a ``/api/tags`` body, ``None`` when the
    body is not a listing we can trust (so an absent model is not reported
    as "not listed")."""
    models = tags.get("models") if isinstance(tags, dict) else None
    if not isinstance(models, list):
        return None
    return {
        m["name"]: m["digest"][:_DIGEST_PREFIX]
        for m in models
        if isinstance(m, dict)
        and isinstance(m.get("name"), str)
        and isinstance(m.get("digest"), str)
    }


def serving_environment() -> dict[str, Any]:
    """Which weights and which Ollama build are serving this process.

    Model *names* (``served_model()``, ``_get_embedding_model()``) are mutable
    tags: a re-pull silently swaps the weights behind ``gemma4:e4b``. The
    digest is the only identity that survives, so the session-start episode
    and the pivot-snapshot manifest (ADR-0069 addendum 2026-09-06) carry it.

    Asks Ollama once per process (``GET /api/version`` + ``GET /api/tags``)
    and caches. Observability only: never raises, never blocks generation.
    Every key in ``SERVING_ENV_KEYS`` is always present — a value that could
    not be resolved is ``None`` and ``serving_environment_reason`` says why
    (``ok`` / ``ollama_unreachable`` / ``ollama_malformed_response`` /
    ``backend_injected`` / ``model_not_listed:<tag>``, ``;``-joined when
    several apply; reason codes over silent fallback, ADR-0075). Not recorded
    on every llm-calls row: the session_id / run_id join reaches it from there.
    """
    global _serving_env
    if _serving_env is not None:
        return dict(_serving_env)

    from ..embeddings import _get_embedding_model  # module-level import would be circular

    env: dict[str, Any] = dict.fromkeys(SERVING_ENV_KEYS)
    reasons: list[str] = []
    version, tags, fetch_reason = _fetch_ollama_metadata()
    if fetch_reason is not None:
        reasons.append(fetch_reason)

    if isinstance(version, dict) and isinstance(version.get("version"), str):
        env["ollama_version"] = version["version"]
    elif version is not None:
        reasons.append("ollama_malformed_response")

    listed = _digests_from_tags(tags)
    if tags is not None and listed is None and "ollama_malformed_response" not in reasons:
        reasons.append("ollama_malformed_response")
    if listed is not None:
        if _backend is not None:
            reasons.append("backend_injected")
        else:
            gen = _normalize_tag(get_ollama_model())
            env["generation_model_digest"] = listed.get(gen)
            if env["generation_model_digest"] is None:
                reasons.append(f"model_not_listed:{gen}")
        emb = _normalize_tag(_get_embedding_model())
        env["embedding_model_digest"] = listed.get(emb)
        if env["embedding_model_digest"] is None:
            reasons.append(f"model_not_listed:{emb}")

    env["serving_environment_reason"] = ";".join(reasons) if reasons else "ok"
    _serving_env = env
    return dict(env)


def refresh_serving_environment() -> dict[str, Any]:
    """``serving_environment()`` with the cached reading dropped.

    For the startup check that retries a daemon still coming up (D-P0-05-1).
    """
    global _serving_env
    _serving_env = None
    return serving_environment()


def emit_llm_telemetry(record: dict[str, Any]) -> None:
    """Append one telemetry record to ``llm-calls-{date}.jsonl``.

    No-op when ``_telemetry_dir`` is unset. Never raises: a telemetry
    write failure must not break the generation it observes. The record
    carries call metadata only — never the prompt body, which may embed
    untrusted external content and would otherwise become a second
    injection path when telemetry is read back by analysis sessions. That
    metadata-only contract binds every caller.

    Public because ``core.embeddings`` records its own calls on this channel
    (``caller="embed"``). It routes through here rather than writing the file
    itself so that within this channel the no-op condition, the failure
    swallowing, and above all the date rotation have one owner — a second copy
    of the rotation rule would drift the moment either side changed its
    filename or its granularity.
    """
    if _telemetry_dir is None:
        return
    try:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        append_jsonl_restricted(_telemetry_dir / f"llm-calls-{date_str}.jsonl", record)
    except Exception as exc:
        # ERROR, not WARNING: a dead telemetry sink blinds every downstream
        # reading while the run goes on (P1-06.8 log-level convention).
        logger.error("Failed to write LLM telemetry: %s", exc)


def generate(
    prompt: str,
    system: str | None = None,
    max_length: int | None = None,
    num_predict: int | None = None,
    format: dict | None = None,
    temperature: float = 1.0,
    drop_truncated: bool = False,
    caller: str = "unknown",
    think: bool = False,
) -> str | None:
    """Generate text via the configured backend (default: local Ollama).

    Args:
        max_length: Char-level truncation applied to the sanitized output.
            None (default) skips slicing — appropriate for internal callers
            (distill/insight/etc). External callers that must satisfy a
            platform character limit (post / comment / reply) pass the
            relevant constant explicitly.
        num_predict: Max tokens the model may emit. Caller-specific caps
            prevent runaway generation on short prompts (M1 can take 14+
            minutes at the default 8192). Falls back to 8192 if None.
        format: JSON Schema dict for structured output (Ollama v0.5+).
                When set, output is constrained at the token level.
        temperature: Sampling temperature. Default 1.0 (production
            baseline). Outward reflective generation (comment/reply/post)
            raises it to break formulaic, RLHF-baked openings (ADR-0047);
            scoring/distill paths keep 1.0. Judgment calls pass 0, where
            sampling noise moved the answer rather than the prompt: the
            verification arithmetic, the insight judging stages (novelty
            gate, naming, post-extraction duplicate — RFC-0042), and the
            skill selector (RFC-0044).
            Forwarded to an injected backend via the ``LLMBackend`` protocol
            so it honors the same per-call temperature.
        drop_truncated: When True and the backend reports a length-capped
            stop (Ollama ``done_reason == "length"`` / OpenAI
            ``finish_reason == "length"``, output hit ``num_predict``
            mid-generation), return None instead of the cut text —
            external publish paths must not POST a mid-sentence fragment
            (audit M2; "skip, don't substitute"). Default False: internal
            callers (distill/insight) keep the partial text and rely on
            their own fallbacks; a WARNING is logged either way. Applies
            uniformly across the Ollama and injected-backend paths.
        caller: Stage label recorded in per-call telemetry (e.g.
            ``"distill.category"``). Identifies which pipeline stage made
            the call; never affects generation.
        think: Request the model's reasoning trace. Default False = the
            production behavior (no thinking; fastest). When True, the
            reasoning trace is captured but NOT returned here — ``generate``
            still yields only the sanitized published text. Publish-path
            callers that want the trace use ``generate_for_api`` (which
            returns a :class:`GenerationOutput` carrying ``.thinking``).
            Recorded in telemetry either way.

    Returns sanitized output, or None on failure. Context budget (audit C2,
    against ``NUM_CTX`` on the Ollama path or ``LLMBackend.context_window``
    for an injected backend that declares one): when estimated input +
    ``num_predict`` exceeds the window but the input still leaves at least
    ``MIN_CLAMPED_NUM_PREDICT`` tokens, ``num_predict`` is clamped to the
    remaining budget and the call proceeds (WARNING logged, requested value
    kept in telemetry as ``num_predict_requested``). Only when the input
    alone leaves less than the clamp floor is the call skipped (None) —
    skip rather than front-truncate the value layer (Ollama) or overrun an
    injected backend's context window. Surviving the floor is not a promise
    that the budget suffices: a clamped generation may still hit its budget
    mid-sentence, and that is judged after the fact from ``done_reason``
    (``drop_truncated``, audit M2), not predicted by the floor.

    If an ``LLMBackend`` was injected via ``configure(backend=...)``, the
    raw generation is delegated to it; otherwise the built-in Ollama HTTP
    path runs. Sanitization, circuit breaker, and empty-response handling
    apply uniformly across both paths.
    """
    out = generate_full(
        prompt,
        system,
        max_length,
        num_predict,
        format,
        temperature,
        drop_truncated,
        caller,
        think,
    )
    return out.text if out is not None else None


def generate_full(
    prompt: str,
    system: str | None = None,
    max_length: int | None = None,
    num_predict: int | None = None,
    format: dict | None = None,
    temperature: float = 1.0,
    drop_truncated: bool = False,
    caller: str = "unknown",
    think: bool = False,
) -> GenerationOutput | None:
    """Like :func:`generate` but returns the full :class:`GenerationOutput`.

    Internal trace-keeping entry point (ADR-0069): the value-layer pipelines
    that run with ``think=True`` (insight / amend-constitution /
    distill-identity / skill-stocktake) need the reasoning
    trace, which :func:`generate` discards when it projects to ``.text``. This
    is the internal analogue of :func:`generate_for_api` (which serves the
    publish seam) — same shared core (:func:`generate_request`), no platform
    char-limit derivation. Args mirror :func:`generate`. Returns ``None`` on
    failure / truncation-drop (callers None-check, same as ``generate``);
    otherwise a ``GenerationOutput`` whose ``.thinking`` is populated only when
    ``think=True`` (the default-off contract holds — a model emitting ``<think>``
    under ``think=False`` never persists a trace).
    """
    return generate_request(
        GenerationRequest(
            prompt=prompt,
            system=system,
            max_length=max_length,
            num_predict=num_predict,
            format=format,
            temperature=temperature,
            drop_truncated=drop_truncated,
            caller=caller,
            think=think,
        )
    )


def generate_request(request: GenerationRequest) -> GenerationOutput | None:
    """Shared core of :func:`generate` and :func:`generate_for_api`.

    Builds the per-call telemetry record (including ``think``), runs the
    backend via :func:`_generate_impl`, and returns a :class:`GenerationOutput`
    (sanitized text + optional reasoning trace), or None on failure /
    truncation-drop. :func:`generate` projects this to ``.text``; publish-path
    callers keep the full object to persist ``.thinking`` to the episode log.
    """
    tel: dict[str, Any] = {
        "ts": now_iso(timespec="seconds"),
        "caller": request.caller,
        # Injected backends declare their served model id via the LLMBackend
        # ``model`` contract, so telemetry records the real served model
        # across any backend (parity with the Ollama default's get_ollama_model()).
        "model": served_model(),
        "prompt_chars": len(request.prompt),
        "system_chars": None,
        "num_predict": request.effective_num_predict,
        "temperature": request.temperature,
        # Whether the reasoning trace was requested for this call. A metadata
        # flag only — the trace content itself is never written to telemetry
        # (it goes to the episode log); this lets analysis tell think-on from
        # think-off rows apart, e.g. for a latency A/B.
        "think": request.think,
        # Which channel supplied that trace — "field" (the backend's dedicated
        # one), "inline" (a <think> block in the text), or "absent" (requested
        # and none captured). Stays None when the capture guard never ran:
        # think=False, or a call that failed before its success tail. Still
        # provenance metadata only — the trace content goes to the episode log,
        # never here. A sparse thinking_fallback_reason joins it when a
        # requested trace was not delivered as-is.
        "thinking_source": None,
        "has_format": request.format is not None,
        "prompt_sha256": hashlib.sha256(request.prompt.encode("utf-8")).hexdigest()[:12],
        # Content identity: the raw digest above changes with every wrapped
        # call (fresh delimiter nonce), so it cannot say "this prompt was sent
        # before". This one can — the census reads it (ADR-0107).
        "prompt_norm_sha256": nonce_stable_digest(request.prompt),
        "duration_ms": None,
        # Default covers unexpected exceptions: any path that does not
        # explicitly set an outcome below records as an error.
        "outcome": "error",
        "done_reason": None,
        "prompt_eval_count": None,
        "eval_count": None,
        # Cache-hit accounting: cached_tokens / prompt_eval_count is the
        # per-call prompt-cache hit rate. Populated by backends that report a
        # prompt cache; None on the Ollama path (no cache reporting).
        "cached_tokens": None,
        # How the C2 pre-flight measured this call's input, and the total it
        # used (ADR-0087). Both stay None when the guard did not run at all —
        # a backend that declares no context_window is unguarded (ADR-0066),
        # and reporting an estimate it never consulted would be a fiction.
        # Sitting next to prompt_eval_count (the real input-token count Ollama
        # reports afterwards), input_tokens makes each row self-sufficient for
        # calibrating the estimator offline.
        "token_count_source": None,
        "input_tokens": None,
    }
    started = time.monotonic()
    try:
        return _generate_impl(request, tel)
    finally:
        tel["duration_ms"] = int((time.monotonic() - started) * 1000)
        emit_llm_telemetry(tel)


def measure_backend_input_tokens(system: str, prompt: str) -> InputTokenMeasurement:
    """Measure the pre-flight's two inputs against the currently injected backend.

    Thin binding of :func:`measure_input_tokens` (backend.py, which owns the
    protocol, the reason vocabulary and the plausibility bound) to this
    facade's two process-level values: the injected ``_backend`` and the
    estimator. Kept as a name because tests and the sibling backend repos
    import it from ``core.llm``.
    """
    return measure_input_tokens(_backend, system, prompt, estimate_input_tokens)


def _generate_impl(request: GenerationRequest, tel: dict[str, Any]) -> GenerationOutput | None:
    """Body of :func:`generate_request`; mutates *tel* with outcome metadata.

    Resolves the caller's request into a :class:`ResolvedRequest` — system
    prompt built, output budget clamped to the context window — and dispatches
    it. Everything below this frame sees only the resolved form.
    """
    if circuit_breaker.is_open:
        logger.debug("Circuit breaker open — skipping LLM request")
        tel["outcome"] = "circuit_open"
        return None

    resolved = request.resolve(request.system or build_system_prompt())
    tel["system_chars"] = len(resolved.system)

    # Context-budget pre-flight (audit C2), backend-aware. The window is
    # NUM_CTX on the built-in Ollama path; an injected backend supplies its
    # own via the LLMBackend.context_window contract. A backend that omits it
    # (unknown window) falls back to None and is left unguarded, so a
    # not-yet-updated external backend still delegates. Over-budget input is
    # skipped, not sent: Ollama would silently front-truncate the system
    # prompt's value layer (identity/axioms) first, and a memory-bounded
    # injected backend could instead overrun its context window. Skip, don't
    # substitute — caller-input pathology, not a backend fault, so the circuit
    # breaker is left untouched.
    ctx_window = getattr(_backend, "context_window", None) if _backend is not None else NUM_CTX
    if ctx_window is not None:
        # Measured with the backend's own tokenizer when it has one, else the
        # conservative estimator (ADR-0087). Which one was used is recorded,
        # never inferred: the two differ by 1.73-1.95x on this agent's
        # corpora, so a clamp value is unreadable offline without its source.
        measured = measure_backend_input_tokens(resolved.system, resolved.prompt)
        tel["token_count_source"] = measured.source
        tel["input_tokens"] = measured.total
        if measured.fallback_reason is not None:
            tel["token_count_fallback_reason"] = measured.fallback_reason
        # Withhold framing headroom only when the input was counted for real.
        # An exact count invites clamping to the exact remainder, which puts
        # input + output flush against the window with nothing left for the
        # chat template the backend wraps them in. The estimator path keeps its
        # arithmetic unchanged — its over-count is already a far larger reserve.
        reserve = BACKEND_FRAMING_RESERVE if measured.source == TOKEN_COUNT_SOURCE_BACKEND else 0
        available = ctx_window - measured.total - reserve
        if resolved.num_predict > available:
            if available < MIN_CLAMPED_NUM_PREDICT:
                logger.warning(
                    "Skipping LLM call: %s input %d tok (system≈%d + "
                    "prompt≈%d) leaves %d tok < clamp floor %d in context "
                    "window %d (audit C2).",
                    measured.source,
                    measured.total,
                    measured.system,
                    measured.prompt,
                    available,
                    MIN_CLAMPED_NUM_PREDICT,
                    ctx_window,
                )
                tel["outcome"] = "budget_exceeded"
                return None
            # Degrade the output budget instead of suppressing the action:
            # a skip here silenced every self-post for 24+ hours when a skill
            # adoption grew the system prompt past the old guard (2026-07-09).
            # On the estimator the clamped value is conservative (the estimate
            # over-counts input, audit C2); on a real backend count it is the
            # actual remaining budget.
            logger.warning(
                "Clamping num_predict %d -> %d: %s input %d tok "
                "(system≈%d + prompt≈%d) in context window %d (audit C2).",
                resolved.num_predict,
                available,
                measured.source,
                measured.total,
                measured.system,
                measured.prompt,
                ctx_window,
            )
            tel["num_predict_requested"] = resolved.num_predict
            resolved = resolved.clamped_to(available)
            tel["num_predict"] = resolved.num_predict

    return _generate_via_backend(_backend if _backend is not None else _OLLAMA, resolved, tel)


def _generate_via_backend(
    backend: LLMBackend, request: ResolvedRequest, tel: dict[str, Any]
) -> GenerationOutput | None:
    """Injected-backend path of :func:`_generate_impl`.

    Mirrors the Ollama path's truncation gating and telemetry: the backend
    returns a :class:`BackendResult` (text + finish_reason + eval_count),
    and this function — not the backend — applies ``drop_truncated`` and
    records the circuit outcome, so a deliberate truncation drop is scored
    as a success (the call worked) rather than a failure (audit M2).
    """
    try:
        result = backend.generate(
            request.prompt,
            request.system,
            request.num_predict,
            request.format,
            temperature=request.temperature,
            think=request.think,
        )
    except OllamaRequestError as exc:  # the built-in backend: logged at the raise site
        circuit_breaker.record_failure()
        tel["error_kind"] = exc.error_kind
        return None
    except Exception as exc:  # backend may raise on unexpected failure
        logger.error("Backend generate() raised: %s", exc)
        circuit_breaker.record_failure()
        tel["error_kind"] = "backend_exception"
        return None
    if result is None or not result.text.strip():
        logger.warning("Backend returned empty response")
        circuit_breaker.record_failure()
        tel["outcome"] = "empty"
        return None

    tel["done_reason"] = result.finish_reason
    if isinstance(result.eval_count, int):
        tel["eval_count"] = result.eval_count
    # Prefill accounting: record total input tokens under the same
    # prompt_eval_count field NAME the Ollama path uses — both are total input
    # today (Ollama has no prompt KV cache to make the two diverge) — and
    # prompt-cache hits separately. cached_tokens / prompt_eval_count is the
    # cache-hit rate that distinguishes a cache-churn slowdown from a
    # memory-pressure cliff.
    if isinstance(result.prompt_tokens, int):
        tel["prompt_eval_count"] = result.prompt_tokens
    if isinstance(result.cached_tokens, int):
        tel["cached_tokens"] = result.cached_tokens

    if drop_for_output_truncation(result.finish_reason, request, tel):
        return None

    return finalize_ok(result.text, result.thinking, request, tel)


def generate_for_api(
    prompt: str,
    max_length: int,
    *,
    system: str | None = None,
    temperature: float = 1.0,
    chars_per_token: float = 3.0,
    caller: str = "unknown",
    think: bool = False,
    selection_id: str | None = None,
) -> GenerationOutput:
    """Generate text for an API publish path (post/comment/reply/title).

    Caller specifies only ``max_length`` (the API's char limit). ``num_predict``
    is derived as ``ceil(max_length/chars_per_token) + 50`` (yields min 50
    tokens at max_length=0).

    ADR-0018 amendment (2026-05-04): API caller per-caller ``num_predict``
    calibration is replaced by this single derivation, so callers specify
    one value (``max_length``) instead of two. Internal callers
    (distill/insight/etc) keep their ADR-0018 calibrated values.

    Args:
        chars_per_token: Output chars-per-token estimate. Default 3.0 is the
            ASCII-conservative ratio; CJK output runs 1.5-2 chars/tok, so
            comment/reply/title pass 1.5 — at the /3 default, Japanese
            output hits num_predict early and is cut mid-sentence
            (audit M2). The post path keeps 3.0: at max_length=40000, /1.5
            would derive num_predict≈26.7K, which the C2 guard would clamp
            to whatever input headroom remains under the full system
            prompt anyway — requesting a realistic budget up front keeps
            the clamp (and its WARNING) for genuine contention.
        think: Request the reasoning trace (default False = production). When
            True the trace is captured on the returned ``GenerationOutput``
            so the publish path can persist it to the episode log.
        selection_id: The skill-selection record this generation runs under
            (RFC-0028), stamped onto the returned output so the publish site
            can link the comment it becomes back to the selection. Stamped
            here rather than by the caller so the field is set wherever the
            DTO is built, on the failure return as well as the success one.

    Returns a :class:`GenerationOutput`: ``.text`` is the sanitized published
    output (None on failure / truncation-drop — callers already None-check the
    old return), ``.thinking`` is the optional reasoning trace. Truncated
    output (done_reason=length) is dropped, not published —
    ``drop_truncated=True`` on every API path (audit M2).
    """
    if chars_per_token <= 0:
        raise ValueError(f"chars_per_token must be positive, got {chars_per_token}")
    estimated_num_predict = math.ceil(max_length / chars_per_token) + 50
    out = generate_request(
        GenerationRequest(
            prompt=prompt,
            system=system,
            max_length=max_length,
            num_predict=estimated_num_predict,
            format=None,
            temperature=temperature,
            drop_truncated=True,
            caller=caller,
            think=think,
        )
    )
    if out is None:
        return GenerationOutput(text=None, selection_id=selection_id)
    return replace(out, selection_id=selection_id)
