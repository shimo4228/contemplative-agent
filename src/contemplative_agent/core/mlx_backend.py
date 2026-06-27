"""MLX generation backend: route ``generate()`` through a local mlx_lm.server.

On Apple Silicon, mlx_lm.server (Apple's MLX runtime) generates ~1.8x faster
and at ~3.4 GB less resident memory than Ollama for the same Qwen3.5 9B
weights (evidence: ``docs/evidence/adr-0064/``). This backend speaks the
OpenAI ``/v1/chat/completions`` shape mlx_lm.server exposes and returns a
:class:`~contemplative_agent.core.llm.BackendResult` that the core
``generate()`` path sanitizes, truncation-gates, and circuit-breaks
uniformly with the Ollama path.

Only *generation* is routed here. mlx_lm.server has no embeddings endpoint,
so embeddings stay on Ollama via ``OLLAMA_BASE_URL`` (``core.embeddings``).
The backend is opt-in: ``cli.py`` injects it via ``configure(backend=...)``
only when ``LLM_BACKEND=mlx``; unset keeps the default Ollama path, so the
switch is fully reversible by clearing one env var.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import requests

from .llm import BackendResult, validate_trusted_url

logger = logging.getLogger(__name__)

# mlx_lm.server has no token-constrained structured-output mode (no Ollama
# ``format=`` / OpenAI ``response_format``), so a ``format`` schema is
# rendered into a prompt instruction instead. The single caller that passes
# ``format`` (distill) parses JSON then falls back to bullet lines
# (``distill._parse_refined_patterns``), absorbing any drift.
_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a JSON value conforming to this JSON Schema. "
    "Emit no prose and no markdown fences — just the JSON:\n{schema}"
)

# Same connect/read budget as the Ollama path (``core.llm._post_ollama``):
# a cold M1 prefill can run for minutes, so the read timeout is generous.
_TIMEOUT = (30, 1200)


@dataclass(frozen=True)
class MlxLmBackend:
    """``LLMBackend`` implementation backed by a local mlx_lm.server.

    Args:
        base_url: Server origin, e.g. ``http://localhost:8080``. Validated
            per call against the shared localhost / ``OLLAMA_TRUSTED_HOSTS``
            allowlist (SSRF guard), so only local / trusted hosts are
            reachable.
        model: Served model id, e.g. ``mlx-community/Qwen3.5-9B-4bit``.
    """

    base_url: str
    model: str

    def __post_init__(self) -> None:
        # Fail fast at construction (cli.py startup) on a misconfigured
        # MLX_BASE_URL, rather than letting the first generate() trip the
        # circuit breaker with an opaque error. generate() re-validates per
        # call so a runtime OLLAMA_TRUSTED_HOSTS change is still enforced.
        validate_trusted_url(self.base_url, source="MLX_BASE_URL")

    def generate(
        self,
        prompt: str,
        system: str,
        num_predict: int,
        format: Optional[Dict],
        *,
        temperature: float = 1.0,
    ) -> Optional[BackendResult]:
        """Generate via mlx_lm.server.

        Returns a :class:`BackendResult`; the caller
        (``core.llm._generate_via_backend``) applies sanitization, the
        ``drop_truncated`` gate (from ``finish_reason``), and circuit
        accounting. A transport error or unparsable body raises, so the
        caller scores a circuit failure; this method never sanitizes.
        """
        url = validate_trusted_url(self.base_url, source="MLX_BASE_URL")

        user_content = prompt
        if format is not None:
            user_content += _JSON_INSTRUCTION.format(
                schema=json.dumps(format, ensure_ascii=False)
            )

        messages: List[Dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_content})

        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": num_predict,
            "temperature": temperature,
            "stream": False,
            # Thinking off per request — parity with the Ollama think:False
            # default. mlx_lm.server forwards chat_template_kwargs into the
            # tokenizer chat template (Qwen reads enable_thinking).
            "chat_template_kwargs": {"enable_thinking": False},
        }

        response = requests.post(
            f"{url.rstrip('/')}/v1/chat/completions",
            json=payload,
            timeout=_TIMEOUT,
            allow_redirects=False,
        )
        response.raise_for_status()
        return _parse_completion(response.json())


def _parse_completion(data: Dict) -> BackendResult:
    """Map an OpenAI chat-completion body to a :class:`BackendResult`.

    Raises ValueError on a structurally unexpected body so the caller
    records a circuit failure rather than silently returning empty text.
    """
    try:
        choice = data["choices"][0]
        text = choice["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Malformed mlx_lm.server response: {exc}") from exc
    finish_reason = choice.get("finish_reason")
    usage = data.get("usage") or {}
    eval_count = usage.get("completion_tokens")
    if not isinstance(eval_count, int):
        eval_count = None
    return BackendResult(
        text=text, finish_reason=finish_reason, eval_count=eval_count
    )
