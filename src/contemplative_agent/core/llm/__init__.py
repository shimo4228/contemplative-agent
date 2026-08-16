"""Local LLM interface via Ollama REST API.

Package layout (ADR-0079): this ``__init__`` is the permanent facade — the
public import path ``contemplative_agent.core.llm`` is API for the sibling
backends (contemplative-agent-cloud / -mlx) and every internal caller, so
all public symbols are re-exported here regardless of which submodule they
live in. Transport (``requests``), generation, and the transport-side
mutable configuration stay in this module; :mod:`.backend` holds the
backend protocol + circuit breaker, :mod:`.prompting` the system-prompt
assembly (and owns the prompt-side mutable state), :mod:`.guard` the
security guards (SSRF, secret scrubbing, untrusted wrapping).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# Facade re-exports (ADR-0079): the `X as X` redundant-alias form marks each
# name as an intentional part of the public `core.llm` surface — including the
# underscore names that tests and siblings import — so ruff/pyright treat them
# as re-exports rather than unused imports.
from .._io import append_jsonl_restricted, now_iso
from . import prompting as _prompting
from .backend import (
    _DEFAULT_OLLAMA_MODEL as _DEFAULT_OLLAMA_MODEL,
    _DEFAULT_OLLAMA_URL as _DEFAULT_OLLAMA_URL,
    BACKEND_FRAMING_RESERVE as BACKEND_FRAMING_RESERVE,
    CIRCUIT_COOLDOWN_SECONDS as CIRCUIT_COOLDOWN_SECONDS,
    CIRCUIT_FAILURE_THRESHOLD as CIRCUIT_FAILURE_THRESHOLD,
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
    LLMBackend as LLMBackend,
    ThinkingFallbackReason as ThinkingFallbackReason,
    TokenCountingBackend as TokenCountingBackend,
    _circuit as _circuit,
    circuit_reading as circuit_reading,
    circuit_shield as circuit_shield,
)
from .guard import (
    _DEFAULT_MARKER_COMPLETE as _DEFAULT_MARKER_COMPLETE,
    _DEFAULT_MARKER_TRUNCATED as _DEFAULT_MARKER_TRUNCATED,
    _DEFAULT_UNTRUSTED_FRAME as _DEFAULT_UNTRUSTED_FRAME,
    _INJECTION_TOKENS as _INJECTION_TOKENS,
    LOCALHOST_HOSTS as LOCALHOST_HOSTS,
    MAX_THINKING_CHARS as MAX_THINKING_CHARS,
    _extract_inline_thinking as _extract_inline_thinking,
    _sanitize_output as _sanitize_output,
    _sanitize_thinking as _sanitize_thinking,
    _scrub_secrets as _scrub_secrets,
    _strip_thinking as _strip_thinking,
    validate_trusted_url as validate_trusted_url,
    wrap_untrusted_content as wrap_untrusted_content,
)
from .prompting import (
    _DEFAULT_LEARNED_RULES_FRAMING as _DEFAULT_LEARNED_RULES_FRAMING,
    _DEFAULT_LEARNED_SKILLS_FRAMING as _DEFAULT_LEARNED_SKILLS_FRAMING,
    _MD_CACHE as _MD_CACHE,
    SystemBudgetReading as SystemBudgetReading,
    _build_system_prompt as _build_system_prompt,
    _estimate_tokens as _estimate_tokens,
    _load_md_files as _load_md_files,
    build_system_prompt_with_skills as build_system_prompt_with_skills,
    get_distill_system_prompt as get_distill_system_prompt,
    get_identity_system_prompt as get_identity_system_prompt,
    system_prompt_budget_reading as system_prompt_budget_reading,
    validate_identity_content as validate_identity_content,
)
from .request import (
    DEFAULT_NUM_PREDICT as DEFAULT_NUM_PREDICT,
    GenerationRequest as GenerationRequest,
    ResolvedRequest as ResolvedRequest,
)

logger = logging.getLogger(__name__)

# Module-level settings — set by configure() from the adapter. Transport-side
# state only; prompt-side state is owned by .prompting (single owner).
_ollama_base_url: str = _DEFAULT_OLLAMA_URL
_ollama_model: str = _DEFAULT_OLLAMA_MODEL
_backend: LLMBackend | None = None
_telemetry_dir: Path | None = None


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
        telemetry_dir: Directory for per-call telemetry JSONL
            (``llm-calls-{date}.jsonl``). ``None`` (default) disables
            telemetry. Records carry call metadata only, never the prompt
            body (see ``_emit_telemetry``).
    """
    global _ollama_base_url, _ollama_model, _backend, _telemetry_dir
    _prompting.configure_prompting(
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
    if telemetry_dir is not None:
        _telemetry_dir = telemetry_dir


def reset_llm_config() -> None:
    """Reset module-level LLM config and circuit breaker to defaults. Useful for testing."""
    global _ollama_base_url, _ollama_model, _backend, _telemetry_dir
    _prompting.reset_prompting()
    _ollama_base_url = _DEFAULT_OLLAMA_URL
    _ollama_model = _DEFAULT_OLLAMA_MODEL
    _backend = None
    _telemetry_dir = None
    _circuit.reset()


def _get_ollama_url() -> str:
    url = os.environ.get("OLLAMA_BASE_URL", _ollama_base_url)
    return validate_trusted_url(url, source="OLLAMA_BASE_URL")


def _get_model() -> str:
    return os.environ.get("OLLAMA_MODEL", _ollama_model)


def served_model() -> str:
    """The model id actually serving generation, across any backend.

    An injected ``LLMBackend`` declares its served model via the ``model``
    contract; the built-in Ollama path uses ``_get_model()``. Single source of
    truth for per-call telemetry and the snapshot manifest (ADR-0069), so both
    record the same served model regardless of backend.
    """
    return _backend.model if _backend is not None else _get_model()


def _emit_telemetry(record: dict[str, Any]) -> None:
    """Append one telemetry record to ``llm-calls-{date}.jsonl``.

    No-op when ``_telemetry_dir`` is unset. Never raises: a telemetry
    write failure must not break the generation it observes. The record
    carries call metadata only — never the prompt body, which may embed
    untrusted external content and would otherwise become a second
    injection path when telemetry is read back by analysis sessions.
    """
    if _telemetry_dir is None:
        return
    try:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        append_jsonl_restricted(_telemetry_dir / f"llm-calls-{date_str}.jsonl", record)
    except Exception as exc:
        logger.warning("Failed to write LLM telemetry: %s", exc)


def emit_llm_telemetry(record: dict[str, Any]) -> None:
    """Public seam over :func:`_emit_telemetry` for other ``core`` modules.

    ``core.embeddings`` records its own calls on this channel
    (``caller="embed"``). It routes through here rather than writing the file
    itself so that within this channel the no-op condition, the failure
    swallowing, and above all the date rotation have one owner — a second copy
    of the rotation rule would drift the moment either side changed its
    filename or its granularity.

    The metadata-only contract of :func:`_emit_telemetry` binds every caller of
    this seam: whatever text the call embedded stays out of the record.
    """
    _emit_telemetry(record)


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
            scoring/distill paths keep 1.0. Forwarded to an injected
            backend via the ``LLMBackend`` protocol so it honors the same
            per-call temperature.
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
    out = _generate_full(
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
    that run with ``think=True`` (insight / rules-distill / amend-constitution /
    distill-identity / skill-stocktake / rules-stocktake) need the reasoning
    trace, which :func:`generate` discards when it projects to ``.text``. This
    is the internal analogue of :func:`generate_for_api` (which serves the
    publish seam) — same shared core (:func:`_generate_full`), no platform
    char-limit derivation. Args mirror :func:`generate`. Returns ``None`` on
    failure / truncation-drop (callers None-check, same as ``generate``);
    otherwise a ``GenerationOutput`` whose ``.thinking`` is populated only when
    ``think=True`` (the default-off contract holds — a model emitting ``<think>``
    under ``think=False`` never persists a trace).
    """
    return _generate_full(
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


def _generate_full(request: GenerationRequest) -> GenerationOutput | None:
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
        # across any backend (parity with the Ollama default's _get_model()).
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
        _emit_telemetry(tel)


@dataclass(frozen=True)
class _InputTokenMeasurement:
    """How the C2 pre-flight measured this call's input, and with what.

    ``source`` is one of ``TOKEN_COUNT_SOURCE_*``. ``fallback_reason`` is
    populated only when a backend counter existed and its value was
    rejected — a backend with no counter is the default, not a fallback, and
    stamping a reason for it would bury the real faults in noise.
    """

    system: int
    prompt: int
    source: str
    fallback_reason: str | None = None

    @property
    def total(self) -> int:
        return self.system + self.prompt


def _coerce_token_count(value: object, text: str) -> tuple[int | None, str | None]:
    """``(count, None)`` when *value* is usable for *text*, else ``(None, reason)``.

    Rejects ``bool`` explicitly: it is an ``int`` subclass, so a backend
    returning ``True`` would otherwise be read as "1 token". Rejects ``0``
    for text that has content — no real tokenizer charges nothing for a
    non-blank string, and an under-count is the direction that defeats the
    guard rather than tightening it.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None, ("counter_none" if value is None else "counter_type")
    if value < 0:
        return None, "counter_negative"
    if not text.strip():
        # Blank text carries no content to under-report, so any non-negative
        # count is acceptable — including 0. The two checks below are about
        # text that says something.
        return value, None
    if value == 0:
        return None, "counter_degenerate"
    # Shape alone is not enough. A well-typed, positive, wildly-too-small count
    # passes every check above and then tells the guard the input is nearly
    # free — the most likely way this guard gets defeated in practice is not
    # malice but a mis-calibrated tokenizer in a sibling backend. Bound it by
    # tokenization density rather than by a tuned ratio against the estimator:
    # no real vocabulary has 50-character tokens, so a count below this is
    # reporting something that is not tokens.
    if value * MAX_CHARS_PER_TOKEN < len(text):
        return None, "counter_implausible"
    return value, None


def _measure_input_tokens(system: str, prompt: str) -> _InputTokenMeasurement:
    """Measure the pre-flight's two inputs, preferring the backend's tokenizer.

    ``_estimate_tokens`` is a deliberate upper bound (ASCII 3 chars/tok, CJK
    2 tok/char — ADR-0066 §5 hardened it that way when under-counting was the
    only failure that mattered). A 2026-08-01 measurement against Apple's
    ``SystemLanguageModel.token_count`` put its over-count at 1.73-1.95x on
    this agent's own corpora, which on a small-window backend is the
    difference between using the window and refusing to call at all
    (a 4,096 window admits ~1,140 real tokens = 28% of itself). A backend
    that can count for real is therefore preferred — but never trusted
    blindly (ADR-0087).

    Both halves are always attempted and validated afterwards, never
    short-circuited: mixing a measured system prompt with an estimated user
    prompt yields a budget that describes neither, so the two are adopted or
    rejected together. When both fail, the system-side reason is reported —
    a stable choice a replay can predict, rather than whichever ran last.

    A counter fault never touches the circuit breaker: failing to *measure*
    a call is not the call failing, the same reasoning that keeps
    over-budget skips off the breaker.
    """
    counter = getattr(_backend, "count_tokens", None) if _backend is not None else None
    if not callable(counter):
        # No capability (the built-in Ollama path, or a backend that declares
        # no tokenizer). Ollama exposes no /api/tokenize as of 0.30.11 —
        # upstream ollama#12030 is still open — so the estimator is the only
        # pre-flight measure available there.
        return _InputTokenMeasurement(
            system=_estimate_tokens(system),
            prompt=_estimate_tokens(prompt),
            source=TOKEN_COUNT_SOURCE_ESTIMATOR,
        )

    counted: list[int] = []
    reason: str | None = None
    for text in (system, prompt):
        try:
            value = counter(text)
        except Exception as exc:
            # Type only, never str(exc): the argument is the prompt, and a
            # tokenizer that echoes its input in the message would pipe
            # untrusted external content into the log stream (the shape of the
            # 2026-08-01 agent-launchd.log contamination).
            logger.warning("Backend count_tokens() raised %s", type(exc).__name__)
            reason = reason or "counter_exception"
            continue
        count, invalid = _coerce_token_count(value, text)
        if count is None:
            logger.warning(
                "Backend count_tokens() returned an unusable value (%s); "
                "falling back to the token estimator (audit C2).",
                invalid,
            )
            reason = reason or invalid
            continue
        counted.append(count)

    # `len(counted) == 2` is redundant today (every loop iteration either
    # appends or sets a reason) and is kept deliberately: it states the
    # atomicity invariant locally, so a later refactor that lets one half
    # short-circuit cannot silently produce a half-measured budget.
    if reason is None and len(counted) == 2:
        return _InputTokenMeasurement(
            system=counted[0],
            prompt=counted[1],
            source=TOKEN_COUNT_SOURCE_BACKEND,
        )
    return _InputTokenMeasurement(
        system=_estimate_tokens(system),
        prompt=_estimate_tokens(prompt),
        source=TOKEN_COUNT_SOURCE_ESTIMATOR,
        fallback_reason=reason,
    )


def _generate_impl(request: GenerationRequest, tel: dict[str, Any]) -> GenerationOutput | None:
    """Body of :func:`_generate_full`; mutates *tel* with outcome metadata.

    Resolves the caller's request into a :class:`ResolvedRequest` — system
    prompt built, output budget clamped to the context window — and dispatches
    it. Everything below this frame sees only the resolved form.
    """
    if _circuit.is_open:
        logger.debug("Circuit breaker open — skipping LLM request")
        tel["outcome"] = "circuit_open"
        return None

    resolved = request.resolve(request.system or _build_system_prompt())
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
        measured = _measure_input_tokens(resolved.system, resolved.prompt)
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

    if _backend is not None:
        return _generate_via_backend(resolved, tel)

    data = _post_ollama(resolved, tel)
    if data is None:
        return None
    raw_text = data.get("response", "")

    tel["done_reason"] = data.get("done_reason")
    eval_count = data.get("eval_count")
    if isinstance(eval_count, int):
        tel["eval_count"] = eval_count

    if _drop_for_output_truncation(data.get("done_reason"), resolved, tel):
        return None

    _warn_front_truncation(data, resolved.system, resolved.prompt, tel)

    return _finalize_ok(raw_text, data.get("thinking"), resolved, tel)


def _generate_via_backend(request: ResolvedRequest, tel: dict[str, Any]) -> GenerationOutput | None:
    """Injected-backend path of :func:`_generate_impl`.

    Mirrors the Ollama path's truncation gating and telemetry: the backend
    returns a :class:`BackendResult` (text + finish_reason + eval_count),
    and this function — not the backend — applies ``drop_truncated`` and
    records the circuit outcome, so a deliberate truncation drop is scored
    as a success (the call worked) rather than a failure (audit M2).
    """
    backend = _backend
    if backend is None:  # guaranteed by caller; explicit guard survives python -O
        raise RuntimeError("_generate_via_backend called with no backend configured")
    try:
        result = backend.generate(
            request.prompt,
            request.system,
            request.num_predict,
            request.format,
            temperature=request.temperature,
            think=request.think,
        )
    except Exception as exc:  # backend may raise on unexpected failure
        logger.error("Backend generate() raised: %s", exc)
        _circuit.record_failure()
        tel["error_kind"] = "backend_exception"
        return None
    if result is None or not result.text.strip():
        logger.warning("Backend returned empty response")
        _circuit.record_failure()
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

    if _drop_for_output_truncation(result.finish_reason, request, tel):
        return None

    return _finalize_ok(result.text, result.thinking, request, tel)


def _classify_request_error(exc: requests.RequestException) -> str:
    """Coarse transport-fault class for telemetry (ADR-0077).

    Before this, 429 / timeout / connection-refused / bad body all collapsed
    into ``outcome="error"`` and were indistinguishable offline. The class
    is sparse telemetry metadata only — it drives no gate or retry.
    """
    if isinstance(exc, requests.exceptions.HTTPError) and exc.response is not None:
        return f"http_{exc.response.status_code}"
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection"
    return "request_error"


def _post_ollama(request: ResolvedRequest, tel: dict[str, Any]) -> dict | None:
    """POST to Ollama and parse the JSON body; None on any failure.

    Every failure path (bad URL, transport error, unparsable body, empty
    response) records a circuit failure and stamps ``tel["error_kind"]``
    (sparse: present on failure rows only) so telemetry can tell fault
    kinds apart (ADR-0077).
    """
    try:
        base_url = _get_ollama_url()
    except ValueError as exc:
        logger.error("Invalid Ollama URL: %s", exc)
        _circuit.record_failure()
        tel["error_kind"] = "bad_url"
        return None

    url = f"{base_url}/api/generate"
    payload = {
        "model": _get_model(),
        "prompt": request.prompt,
        "system": request.system,
        "stream": False,
        "options": {
            "temperature": request.temperature,
            "top_p": SAMPLING_TOP_P,
            "top_k": SAMPLING_TOP_K,
            "num_predict": request.num_predict,
            "num_ctx": NUM_CTX,
        },
        "think": request.think,
    }
    if request.format is not None:
        payload["format"] = request.format

    try:
        response = requests.post(url, json=payload, timeout=(30, 1200), allow_redirects=False)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Ollama request failed: %s", exc)
        _circuit.record_failure()
        tel["error_kind"] = _classify_request_error(exc)
        return None

    try:
        data = response.json()
        raw_text = data.get("response", "")
    except (json.JSONDecodeError, KeyError) as exc:
        logger.error("Failed to parse Ollama response: %s", exc)
        _circuit.record_failure()
        tel["error_kind"] = "bad_json"
        return None

    if not raw_text.strip():
        logger.warning("Ollama returned empty response")
        _circuit.record_failure()
        tel["outcome"] = "empty"
        return None

    return data


def _drop_for_output_truncation(
    finish_reason: str | None,
    request: ResolvedRequest,
    tel: dict[str, Any],
) -> bool:
    """Output-truncation signal (audit M2); True when the result must drop.

    ``finish_reason == "length"`` means the model hit num_predict
    mid-generation. Not a backend fault — the call succeeded — so the circuit
    breaker records success on the drop path. Shared by the Ollama and
    injected-backend paths; each passes its own reason field.
    """
    if finish_reason != "length":
        return False
    if request.drop_truncated:
        logger.warning(
            "Output truncated at num_predict=%d (finish_reason=length); "
            "dropping instead of publishing a mid-sentence cut "
            "(audit M2).",
            request.num_predict,
        )
        _circuit.record_success()
        tel["outcome"] = "truncated_dropped"
        return True
    logger.warning(
        "Output truncated at num_predict=%d (finish_reason=length); "
        "downstream consumers receive an incomplete generation "
        "(audit M2).",
        request.num_predict,
    )
    return False


@dataclass(frozen=True)
class _ThinkingCapture:
    """Outcome of capturing a requested reasoning trace.

    ``source`` is always set (the dense telemetry value, ``"absent"`` when
    nothing was captured); ``reason`` is set only when the trace was not
    delivered as-is. Both can be populated at once: a wrongly-typed dedicated
    field that then falls back to a usable inline block records the reason
    for the rejection AND the channel that actually supplied the trace.
    """

    trace: str | None
    source: str
    reason: ThinkingFallbackReason | None = None


def _capture_thinking(reasoning: object, text: str) -> _ThinkingCapture:
    """Adopt a reasoning trace, or say why none was adopted (ADR-0068).

    Called only for ``think=True``: the request is what makes a missing trace
    a fallback rather than the default. Two channels are tried in the ADR-0068
    order — the dedicated field, then an inline ``<think>`` block — and the
    first rejection reason wins, so the row explains a channel downgrade
    (``field`` -> ``inline``) as well as an outright absence.

    ``reasoning`` is typed ``object`` rather than ``str | None`` because that
    is the seam's actual guarantee: it arrives from untrusted backend JSON
    (``data.get("thinking")``) or a sibling repo's ``BackendResult``, neither
    of which the type annotation binds at runtime.
    """
    reason: ThinkingFallbackReason | None = None
    raw: str | None = None
    if isinstance(reasoning, str):
        # Emptiness is decided HERE, not by _sanitize_thinking further down: a
        # whitespace-only field is truthy, so leaving the judgment to the
        # sanitizer would let it shadow a usable inline block (the field would
        # win the `if not raw` test, the fallback would be skipped, and the
        # available trace discarded while telemetry reported it blank). The
        # dedicated channel carrying nothing must fall through like an absent
        # one — that is the ADR-0068 Decision 3 order — while still recording
        # that it carried something, which is what trace_blank says.
        raw = reasoning if reasoning.strip() else None
        if raw is None and reasoning:
            reason = TRACE_BLANK
    elif reasoning is not None:
        # Type name only, never the value: the value could BE the trace, i.e.
        # untrusted model output, and this logger's stream is swept by
        # log_anomaly_sweep.py (ADR-0043).
        logger.warning(
            "Backend returned a non-str reasoning trace (%s); ignoring it: reason=%s",
            type(reasoning).__name__,
            TRACE_TYPE,
        )
        reason = TRACE_TYPE

    source = THINKING_SOURCE_FIELD if raw else None
    if not raw:
        # Runs on the raw text, before _sanitize_output strips <think> from
        # the published output — the ordering _finalize_ok's docstring pins.
        raw = _extract_inline_thinking(text)
        if raw:
            source = THINKING_SOURCE_INLINE

    sanitized = _sanitize_thinking(raw)
    if sanitized is None:
        # Both channels have already had their blank cases judged (the field
        # above, the inline block inside _extract_inline_thinking, which strips
        # and returns None for <think>   </think>), so arriving here with no
        # earlier reason means neither carried anything: trace_absent, not
        # trace_blank — blank is a claim about a channel that DID carry.
        reason = reason or TRACE_ABSENT
        # Scoped to this call, deliberately. A run can make several think-ON
        # calls (rules-distill 2, stocktake 4), so one missing trace does not
        # mean the run's reasoning.md is missing — asserting that here would
        # hand the operator a false diagnosis from inside the observability
        # path. Which artifacts a run ended up with is _write_reasoning's to say.
        logger.warning("think=True produced no usable reasoning trace: reason=%s", reason)
        return _ThinkingCapture(None, THINKING_SOURCE_ABSENT, reason)
    return _ThinkingCapture(sanitized, source or THINKING_SOURCE_ABSENT, reason)


def _finalize_ok(
    text: str,
    reasoning: object,
    request: ResolvedRequest,
    tel: dict[str, Any],
) -> GenerationOutput:
    """Shared success tail for both generation paths.

    Records the circuit success, marks the telemetry outcome, and builds the
    think-gated reasoning trace. The trace is captured ONLY when this call
    requested think (default-off contract): a model that emits a trace despite
    think=False must not silently persist it while telemetry records
    think=false. Inline <think> is extracted BEFORE ``_sanitize_output``
    strips it from the published text.

    A failure to capture a requested trace is recorded, never scored: the
    generation itself succeeded, so ``outcome`` stays ok/truncated_kept and
    the circuit breaker is untouched (ADR-0087 Decision 7's reasoning — a
    lost research artifact is not a backend outage).
    """
    _circuit.record_success()
    # A length-capped generation reaching this tail was KEPT (drop_truncated
    # False — the drop path returned earlier). Record it distinctly so
    # telemetry can measure how often consumers received an incomplete
    # generation instead of folding it into "ok" (bug-audit 2026-07-06 M1).
    tel["outcome"] = "truncated_kept" if tel.get("done_reason") == "length" else "ok"
    if request.think:
        capture = _capture_thinking(reasoning, text)
        tel["thinking_source"] = capture.source
        if capture.reason is not None:
            tel["thinking_fallback_reason"] = capture.reason
        thinking = capture.trace
    else:
        thinking = None
    return GenerationOutput(text=_sanitize_output(text, request.max_length), thinking=thinking)


def _warn_front_truncation(
    data: dict, system_prompt: str, prompt: str, tel: dict[str, Any]
) -> None:
    """Silent front-truncation detector (audit C2).

    If Ollama evaluated far fewer tokens than the chars sent could possibly
    compress to (~6 chars/tok is a generous lower bound even for pure
    English), the input was cut. The 12000-char floor removes the
    false-positive class of small mechanical calls — truncation only matters
    for large prompts. isinstance check: a non-int value from a proxy or
    future Ollama build must not TypeError.
    """
    prompt_eval = data.get("prompt_eval_count")
    if isinstance(prompt_eval, int):
        tel["prompt_eval_count"] = prompt_eval
    sent_chars = len(system_prompt) + len(prompt)
    if isinstance(prompt_eval, int) and sent_chars > 12000 and prompt_eval < sent_chars // 6:
        logger.warning(
            "Possible silent front-truncation: prompt_eval_count=%d for "
            "%d chars sent (system=%d + prompt=%d); the system prompt's "
            "value layer may have been dropped (audit C2).",
            prompt_eval,
            sent_chars,
            len(system_prompt),
            len(prompt),
        )


def generate_for_api(
    prompt: str,
    max_length: int,
    *,
    system: str | None = None,
    temperature: float = 1.0,
    chars_per_token: float = 3.0,
    caller: str = "unknown",
    think: bool = False,
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

    Returns a :class:`GenerationOutput`: ``.text`` is the sanitized published
    output (None on failure / truncation-drop — callers already None-check the
    old return), ``.thinking`` is the optional reasoning trace. Truncated
    output (done_reason=length) is dropped, not published —
    ``drop_truncated=True`` on every API path (audit M2).
    """
    if chars_per_token <= 0:
        raise ValueError(f"chars_per_token must be positive, got {chars_per_token}")
    estimated_num_predict = math.ceil(max_length / chars_per_token) + 50
    out = _generate_full(
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
    return out if out is not None else GenerationOutput(text=None)
