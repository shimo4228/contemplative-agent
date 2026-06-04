"""Moltbook-specific LLM functions (scoring, generation, topic extraction)."""

from __future__ import annotations

import logging
import re
from typing import Optional

from ...core.config import MAX_COMMENT_LENGTH, MAX_POST_LENGTH, MAX_POST_TITLE_LENGTH
from ...core.domain import get_domain_config, resolve_prompt
from ...core.memory import POST_TOPIC_SUMMARY_MAX
from ...core.prompts import (
    COMMENT_PROMPT,
    COOPERATION_POST_PROMPT,
    INTERNAL_NOTE_PROMPT,
    POST_TITLE_PROMPT,
    RELEVANCE_PROMPT,
    REPLY_PROMPT,
    SESSION_INSIGHT_PROMPT,
    SUBMOLT_SELECTION_PROMPT,
    TOPIC_SUMMARY_PROMPT,
)
from ...core.llm import generate, generate_for_api, wrap_untrusted_content

logger = logging.getLogger(__name__)

# ADR-0047: outward reflective generation (comment / reply / cooperation post)
# raises temperature above the 1.0 production baseline to break formulaic,
# RLHF-baked openings ("What a beautiful moment…"). Candidate-set pruning
# (top_k/top_p/min_p) could not dislodge them; temperature 1.3 flattens the
# mode-collapsed peak while top_k=20 (in core.llm) still caps runaway. Scoring,
# title and distill paths keep the 1.0 default. Validated on comment/reply;
# 1.5 was rejected for axiom-label collapse.
COMMENT_TEMPERATURE = 1.3


def _resolve_domain_prompt(template: str) -> str:
    """Resolve a prompt template with the current domain config."""
    domain = get_domain_config()
    return resolve_prompt(template, domain)


def _build_context_section(
    items: Optional[list[str]],
    header: str,
    limit: Optional[int] = None,
    footer: str = "",
) -> str:
    """Build an optional context section from a list of items.

    Returns empty string if items is None/empty.
    ``header`` MUST be a trusted string literal — never pass external data.
    """
    if not items:
        return ""
    entries = items[-limit:] if limit else items
    lines = "\n".join(f"- {item}" for item in entries)
    section = f"\n{header}:\n{wrap_untrusted_content(lines)}\n"
    if footer:
        section += footer + "\n"
    return section


def score_relevance(post_text: str) -> float:
    """Score a post's relevance to domain topics (0.0 to 1.0)."""
    prompt = _resolve_domain_prompt(RELEVANCE_PROMPT).format(
        post_content=wrap_untrusted_content(post_text, max_input=1000),
    )
    result = generate(prompt, num_predict=30)
    if result is None:
        return 0.0

    match = re.search(r"(\d+(?:\.\d+)?)", result)
    if match:
        score = float(match.group(1))
        return max(0.0, min(1.0, score))
    logger.warning("Could not parse relevance score: %s", result)
    return 0.0


def generate_internal_note(content: str) -> str:
    """Note what the agent noticed while reading ``content``, before it
    decides how to act on it (pre-action reflection, ADR-0045).

    A single-responsibility call: the note only, as plain text (no schema).
    Kept separate from scoring/generation so the local model focuses on
    noticing rather than juggling two tasks in one prompt. Returns "" on
    failure — callers treat an empty note as "nothing recorded".
    """
    if not INTERNAL_NOTE_PROMPT:
        return ""
    prompt = INTERNAL_NOTE_PROMPT.format(
        content=wrap_untrusted_content(content, max_input=1000),
    )
    result = generate(prompt)
    return result.strip() if result else ""


def generate_comment(post_text: str) -> Optional[str]:
    """Generate a contextual comment for a post.

    ``max_input=8000`` (audit C2): the post body is fully fetched (up to
    40K chars) before commenting; unbounded, it could push the prompt past
    num_ctx and silently front-truncate the system prompt's value layer.
    """
    prompt = COMMENT_PROMPT.format(
        post_content=wrap_untrusted_content(post_text, max_input=8000)
    )
    return generate_for_api(
        prompt, max_length=MAX_COMMENT_LENGTH, temperature=COMMENT_TEMPERATURE
    )


def format_feed_seeds(seeds: list[dict]) -> str:
    """Format peer posts as direct seeds for ``cooperation_post.md`` (ADR-0043).

    Each post is wrapped in its own ``<untrusted_content>`` block so the LLM
    sees voice boundaries explicitly. The pre-ADR-0043 path wrapped a single
    LLM-generated summary, which implicitly merged voices and was the
    structural cause of the May 2026 echo chamber.
    """
    if not seeds:
        return ""
    blocks: list[str] = []
    for seed in seeds:
        title = seed.get("title", "") or ""
        content = seed.get("content", "") or ""
        body = f"{title}\n{content}" if title else content
        blocks.append(wrap_untrusted_content(body))
    return "\n\n".join(blocks)


def generate_cooperation_post(
    feed_seeds: list[dict],
    recent_insights: Optional[list[str]] = None,
) -> Optional[str]:
    """Generate a post that responds to specific peer voices in the feed.

    Pre-ADR-0043 this took a single string containing an LLM-generated
    summary of ~10 peer posts. Post-ADR-0043 it takes a list of peer post
    dicts and hands them to the LLM verbatim (each wrapped independently)
    so the LLM must work with concrete voices rather than an abstracted
    topic cluster.
    """
    insights_section = _build_context_section(
        recent_insights,
        "\nPrevious insights from your sessions",
        footer="Note as background context.",
    )

    prompt = _resolve_domain_prompt(COOPERATION_POST_PROMPT).format(
        feed_seeds=format_feed_seeds(feed_seeds),
        insights_section=insights_section,
    )
    return generate_for_api(
        prompt, max_length=MAX_POST_LENGTH, temperature=COMMENT_TEMPERATURE
    )


def generate_reply(
    original_post: str,
    their_comment: str,
    conversation_history: Optional[list[str]] = None,
) -> Optional[str]:
    """Generate a reply that continues a conversation thread."""
    history_section = _build_context_section(
        conversation_history, "Previous exchanges with this agent", limit=5,
    )

    # max_input=8000 on both (audit C2) — same prompt-size bound as the
    # comment path, so num_ctx cannot overflow on long posts/comments.
    prompt = REPLY_PROMPT.format(
        history_section=history_section,
        original_post=wrap_untrusted_content(original_post, max_input=8000),
        their_comment=wrap_untrusted_content(their_comment, max_input=8000),
    )
    return generate_for_api(
        prompt, max_length=MAX_COMMENT_LENGTH, temperature=COMMENT_TEMPERATURE
    )


def generate_post_title(feed_seed_text: str) -> Optional[str]:
    """Generate a post title from peer-post voice blocks (ADR-0043).

    ``feed_seed_text`` is the output of ``format_feed_seeds`` — concatenated
    ``<untrusted_content>`` blocks, one per peer voice. Pre-ADR-0043 the
    input was an LLM-generated topic summary string; the parameter was
    renamed to reflect the post-ADR-0043 contract.
    """
    prompt = _resolve_domain_prompt(POST_TITLE_PROMPT).format(
        feed_seed_text=wrap_untrusted_content(feed_seed_text),
    )
    result = generate_for_api(prompt, max_length=MAX_POST_TITLE_LENGTH)
    if result:
        # Strip surrounding whitespace and quotes the LLM may add. Length is
        # already bounded by max_length=MAX_POST_TITLE_LENGTH (300 chars per
        # API spec); the previous [:80] slice was an unrelated 3rd cap, removed.
        return result.strip().strip('"').strip("'")
    return None


def summarize_post_topic(content: str) -> str:
    """Generate a 1-line topic summary for storage in memory.

    The output is truncated to POST_TOPIC_SUMMARY_MAX so the dedup gate
    (token-set Jaccard against memory-stored topic_summaries) sees both
    sides at the same cap. Symmetry is largely preserved by prefix-5
    stemming in dedup._tokens, but the LLM-failure fallback path falls
    through to raw post content (potentially 40k chars), where the cap
    is load-bearing.
    """
    prompt = TOPIC_SUMMARY_PROMPT.format(
        post_content=wrap_untrusted_content(content, max_input=2000),
    )
    result = generate(prompt, num_predict=60)
    if result:
        return result.strip()[:POST_TOPIC_SUMMARY_MAX]
    return content[:POST_TOPIC_SUMMARY_MAX]


def select_submolt(
    content: str, submolts: tuple[str, ...],
) -> Optional[str]:
    """Ask LLM to select the best submolt for a post. Returns None if invalid."""
    submolt_list = ", ".join(submolts)
    prompt = SUBMOLT_SELECTION_PROMPT.format(
        submolt_list=submolt_list,
        post_content=wrap_untrusted_content(content, max_input=1000),
    )
    result = generate(prompt, num_predict=20)
    if result is None:
        return None

    # Extract submolt name from response (may include extra text)
    cleaned = result.strip().lower().strip('"').strip("'")
    if cleaned in submolts:
        return cleaned

    # Try to find a match within the response
    for name in submolts:
        if name in cleaned:
            return name

    logger.warning("LLM returned unrecognized submolt: %s", result)
    return None


def generate_session_insight(
    actions: list[str], recent_topics: list[str]
) -> Optional[str]:
    """Generate a brief insight about what worked/didn't work this session."""
    if not actions:
        return None

    actions_text = "\n".join(f"- {a}" for a in actions)
    topics_text = (
        "\n".join(f"- {t}" for t in recent_topics) if recent_topics else "None"
    )
    prompt = SESSION_INSIGHT_PROMPT.format(
        actions_text=wrap_untrusted_content(actions_text),
        topics_text=wrap_untrusted_content(topics_text),
    )
    result = generate(prompt, num_predict=100)
    if result:
        # Char cap is owned by memory.record_insight(), which truncates to
        # SUMMARY_MAX_LENGTH (200). Returning the full sanitized output here.
        return result.strip()
    return None
