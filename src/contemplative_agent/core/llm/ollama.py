"""Built-in Ollama transport for :mod:`contemplative_agent.core.llm`.

The HTTP half of the local generation path: POST to ``/api/generate``, read
the counters, apply the output-truncation gate (audit M2) and the shared
success tail. It was the tail of the ``core.llm`` facade; it lives here so the
facade is routing, configuration and telemetry, and the transport is one
module a reader can hold whole. Names are unchanged by the move and no alias
was left behind (CLAUDE.md: a rename or move closes in one PR with its callers).

Process-level settings (the configured URL and model, the env override) stay
with the facade's ``configure()``; ``_post_ollama`` resolves them through the
facade at call time, so an env change or a ``configure()`` still takes effect
on the next call.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import requests

from .backend import (
    NUM_CTX,
    SAMPLING_TOP_K,
    SAMPLING_TOP_P,
    GenerationOutput,
    _circuit,
    capture_thinking,
)
from .guard import _sanitize_output
from .request import ResolvedRequest

logger = logging.getLogger(__name__)


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
    from . import _get_model, _get_ollama_url  # the facade owns the settings

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
        capture = capture_thinking(reasoning, text)
        tel["thinking_source"] = capture.source
        if capture.reason is not None:
            tel["thinking_fallback_reason"] = capture.reason
        thinking = capture.trace
    else:
        thinking = None
    return GenerationOutput(text=_sanitize_output(text, request.max_length), thinking=thinking)


def _record_ollama_counters(data: dict, tel: dict[str, Any]) -> int | None:
    """Stamp the Ollama token counters on *tel*; return ``prompt_eval_count``.

    Both counters are recorded here, at one altitude, so "where does this field
    come from" has one answer. isinstance: a non-int value from a proxy or a
    future Ollama build is dropped rather than reaching telemetry or
    :func:`_warn_front_truncation`'s comparison.
    """
    eval_count = data.get("eval_count")
    if isinstance(eval_count, int):
        tel["eval_count"] = eval_count
    prompt_eval = data.get("prompt_eval_count")
    if not isinstance(prompt_eval, int):
        return None
    tel["prompt_eval_count"] = prompt_eval
    return prompt_eval


def _warn_front_truncation(prompt_eval: int | None, system_prompt: str, prompt: str) -> None:
    """Silent front-truncation detector (audit C2).

    If Ollama evaluated far fewer tokens than the chars sent could possibly
    compress to (~6 chars/tok is a generous lower bound even for pure
    English), the input was cut. The 12000-char floor removes the
    false-positive class of small mechanical calls — truncation only matters
    for large prompts. ``prompt_eval`` is None when the response carried no
    usable count (a non-int value from a proxy or a future Ollama build is
    filtered by the caller, which owns the telemetry stamp).
    """
    sent_chars = len(system_prompt) + len(prompt)
    if prompt_eval is not None and sent_chars > 12000 and prompt_eval < sent_chars // 6:
        logger.warning(
            "Possible silent front-truncation: prompt_eval_count=%d for "
            "%d chars sent (system=%d + prompt=%d); the system prompt's "
            "value layer may have been dropped (audit C2).",
            prompt_eval,
            sent_chars,
            len(system_prompt),
            len(prompt),
        )
