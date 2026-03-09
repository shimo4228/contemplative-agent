"""LLM interface — backward-compatible re-export shim."""

import requests  # noqa: F401 — needed for patch("contemplative_moltbook.llm.requests")

from .core.llm import (  # noqa: F401
    CIRCUIT_COOLDOWN_SECONDS,
    CIRCUIT_FAILURE_THRESHOLD,
    DEFAULT_SYSTEM_PROMPT,
    LOCALHOST_HOSTS,
    _CircuitBreaker,
    _circuit,
    _get_model,
    _get_ollama_url,
    _load_identity,
    _sanitize_output,
    _strip_thinking,
    _wrap_untrusted_content,
    generate,
)
from .adapters.moltbook.llm_functions import (  # noqa: F401
    check_topic_novelty,
    extract_topics,
    generate_comment,
    generate_cooperation_post,
    generate_post_title,
    generate_reply,
    generate_session_insight,
    score_relevance,
    select_submolt,
    summarize_post_topic,
)
