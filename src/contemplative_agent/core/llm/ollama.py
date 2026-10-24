"""Built-in Ollama transport for :mod:`contemplative_agent.core.llm`.

The HTTP half of the local generation path: POST to ``/api/generate``, read
the counters, apply the output-truncation gate (audit M2) and the shared
success tail. It was the tail of the ``core.llm`` facade; it lives here so the
facade is routing, configuration and telemetry, and the transport is one
module a reader can hold whole. Names are unchanged by the move and no alias
was left behind (CLAUDE.md: a rename or move closes in one PR with its callers).

Process-level settings (the configured URL and model, the env override) stay
with the facade's ``configure()``; ``OllamaBackend`` resolves them through the
facade at call time, so an env change or a ``configure()`` still takes effect
on the next call.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import requests

from .backend import (
    NUM_CTX,
    SAMPLING_TOP_K,
    SAMPLING_TOP_P,
    BackendResult,
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


class OllamaRequestError(Exception):
    """An Ollama call failed; ``error_kind`` is the telemetry fault class.

    Raised by :meth:`OllamaBackend.generate` (already logged at the raise
    site) so the facade can stamp the same ``error_kind`` the pre-backend
    transport did (``bad_url`` / ``timeout`` / ``connection`` / ``http_NNN`` /
    ``request_error`` / ``bad_json``, ADR-0077). Any other exception from a
    backend keeps the generic ``backend_exception``.
    """

    def __init__(self, error_kind: str, message: str) -> None:
        super().__init__(message)
        self.error_kind = error_kind


@dataclass(frozen=True)
class OllamaBackend:
    """The built-in generation backend: local Ollama ``/api/generate``.

    Stateless on purpose. The served model and the base URL are resolved
    through the facade on every call (env override > ``configure()`` > default),
    so ``OLLAMA_MODEL`` / ``OLLAMA_BASE_URL`` and ``configure(ollama_*)`` keep
    taking effect call by call, and one instance is safe to share. It
    implements :class:`~contemplative_agent.core.llm.backend.LLMBackend`, which
    is what lets the conformance kit run against the default path too.
    """

    context_window: int = NUM_CTX

    @property
    def model(self) -> str:
        from . import _get_model  # the facade owns the settings

        return _get_model()

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
        """POST to Ollama; ``None`` for an empty answer, ``OllamaRequestError`` for a fault."""
        from . import _get_ollama_url  # the facade owns the settings

        try:
            base_url = _get_ollama_url()
        except ValueError as exc:
            logger.error("Invalid Ollama URL: %s", exc)
            raise OllamaRequestError("bad_url", str(exc)) from exc

        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": SAMPLING_TOP_P,
                "top_k": SAMPLING_TOP_K,
                "num_predict": num_predict,
                "num_ctx": NUM_CTX,
            },
            "think": think,
        }
        if format is not None:
            payload["format"] = format

        try:
            response = requests.post(
                f"{base_url}/api/generate", json=payload, timeout=(30, 1200), allow_redirects=False
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            logger.error("Ollama request failed: %s", exc)
            raise OllamaRequestError(_classify_request_error(exc), str(exc)) from exc

        try:
            data = response.json()
            raw_text = data.get("response", "")
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("Failed to parse Ollama response: %s", exc)
            raise OllamaRequestError("bad_json", str(exc)) from exc

        if not raw_text.strip():
            return None

        # isinstance: a non-int from a proxy or a future Ollama build is dropped
        # rather than reaching telemetry or the comparison below.
        eval_count = data.get("eval_count")
        prompt_eval = data.get("prompt_eval_count")
        prompt_eval = prompt_eval if isinstance(prompt_eval, int) else None
        _warn_front_truncation(prompt_eval, system, prompt)
        return BackendResult(
            text=raw_text,
            finish_reason=data.get("done_reason"),
            eval_count=eval_count if isinstance(eval_count, int) else None,
            prompt_tokens=prompt_eval,
            thinking=data.get("thinking"),
        )
