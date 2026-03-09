"""Moltbook-specific LLM functions (scoring, generation, topic extraction)."""

from __future__ import annotations

import logging
import re
from typing import Optional

from ...config import MAX_COMMENT_LENGTH, MAX_POST_LENGTH
from ...domain import get_domain_config, resolve_prompt
from ...prompts import (
    COMMENT_PROMPT,
    COOPERATION_POST_PROMPT,
    POST_TITLE_PROMPT,
    RELEVANCE_PROMPT,
    REPLY_PROMPT,
    SESSION_INSIGHT_PROMPT,
    SUBMOLT_SELECTION_PROMPT,
    TOPIC_EXTRACTION_PROMPT,
    TOPIC_NOVELTY_PROMPT,
    TOPIC_SUMMARY_PROMPT,
)
from ...core.llm import _wrap_untrusted_content, generate

logger = logging.getLogger(__name__)


def score_relevance(post_text: str) -> float:
    """Score a post's relevance to domain topics (0.0 to 1.0)."""
    domain = get_domain_config()
    resolved = resolve_prompt(RELEVANCE_PROMPT, domain)
    prompt = resolved.format(post_content=_wrap_untrusted_content(post_text))
    result = generate(prompt, max_length=50)
    if result is None:
        return 0.0

    match = re.search(r"(\d+(?:\.\d+)?)", result)
    if match:
        score = float(match.group(1))
        return max(0.0, min(1.0, score))
    logger.warning("Could not parse relevance score: %s", result)
    return 0.0


def generate_comment(post_text: str) -> Optional[str]:
    """Generate a contextual comment for a post."""
    prompt = COMMENT_PROMPT.format(post_content=_wrap_untrusted_content(post_text))
    return generate(prompt, max_length=MAX_COMMENT_LENGTH)


def generate_cooperation_post(
    feed_topics: str,
    recent_insights: Optional[list[str]] = None,
    knowledge_context: Optional[str] = None,
) -> Optional[str]:
    """Generate a post that connects feed trends to contemplative axioms."""
    insights_section = ""
    if recent_insights:
        lines = "\n".join(f"- {i}" for i in recent_insights)
        insights_section = (
            f"\n\nPrevious insights from your sessions:\n{lines}\n"
            "Take these into account when writing.\n"
        )

    knowledge_section = ""
    if knowledge_context:
        knowledge_section = (
            "\n\nYour accumulated knowledge:\n"
            + _wrap_untrusted_content(knowledge_context)
        )

    domain = get_domain_config()
    resolved = resolve_prompt(COOPERATION_POST_PROMPT, domain)
    prompt = resolved.format(
        feed_topics=_wrap_untrusted_content(feed_topics),
        insights_section=insights_section,
        knowledge_section=knowledge_section,
    )
    return generate(prompt, max_length=MAX_POST_LENGTH)


def generate_reply(
    original_post: str,
    their_comment: str,
    conversation_history: Optional[list[str]] = None,
    knowledge_context: Optional[str] = None,
) -> Optional[str]:
    """Generate a reply that continues a conversation thread."""
    history_section = ""
    if conversation_history:
        history_lines = "\n".join(
            f"- {h}" for h in conversation_history[-5:]
        )
        history_section = (
            "\nPrevious exchanges with this agent:\n"
            + _wrap_untrusted_content(history_lines)
            + "\n"
        )

    knowledge_section = ""
    if knowledge_context:
        knowledge_section = (
            "\nYour accumulated knowledge:\n"
            + _wrap_untrusted_content(knowledge_context)
            + "\n"
        )

    prompt = REPLY_PROMPT.format(
        history_section=history_section,
        knowledge_section=knowledge_section,
        original_post=_wrap_untrusted_content(original_post),
        their_comment=_wrap_untrusted_content(their_comment),
    )
    return generate(prompt, max_length=MAX_COMMENT_LENGTH)


def generate_post_title(feed_topics: str) -> Optional[str]:
    """Generate a unique, specific post title from current feed topics."""
    domain = get_domain_config()
    resolved = resolve_prompt(POST_TITLE_PROMPT, domain)
    prompt = resolved.format(
        feed_topics=_wrap_untrusted_content(feed_topics),
    )
    result = generate(prompt, max_length=100)
    if result:
        return result.strip().strip('"').strip("'")[:80]
    return None


def extract_topics(posts: list[dict]) -> Optional[str]:
    """Extract trending topics from recent feed posts."""
    combined = "\n".join(
        f"- {p.get('title', '')}: {p.get('content', '')[:200]}"
        for p in posts[:10]
    )
    if not combined.strip():
        return None
    prompt = TOPIC_EXTRACTION_PROMPT.format(
        combined_posts=_wrap_untrusted_content(combined),
    )
    return generate(prompt, max_length=500)


def check_topic_novelty(
    current_topics: str, recent_topics: list[str]
) -> bool:
    """Ask LLM if current topics are sufficiently different from recent posts."""
    if not recent_topics:
        return True

    recent_lines = "\n".join(f"- {t}" for t in recent_topics)
    prompt = TOPIC_NOVELTY_PROMPT.format(
        recent_topics=recent_lines,
        current_topics=_wrap_untrusted_content(current_topics),
    )
    result = generate(prompt, max_length=50)
    if result is None:
        return True  # fail open — allow posting if LLM is down

    return "YES" in result.upper()


def summarize_post_topic(content: str) -> str:
    """Generate a 1-line topic summary for storage in memory."""
    prompt = TOPIC_SUMMARY_PROMPT.format(
        post_content=_wrap_untrusted_content(content),
    )
    result = generate(prompt, max_length=120)
    if result:
        return result.strip()[:100]
    return content[:100]


def select_submolt(
    content: str, submolts: tuple[str, ...],
) -> Optional[str]:
    """Ask LLM to select the best submolt for a post. Returns None if invalid."""
    submolt_list = ", ".join(submolts)
    prompt = SUBMOLT_SELECTION_PROMPT.format(
        submolt_list=submolt_list,
        post_content=_wrap_untrusted_content(content),
    )
    result = generate(prompt, max_length=50)
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
        actions_text=actions_text,
        topics_text=topics_text,
    )
    result = generate(prompt, max_length=200)
    if result:
        return result.strip()[:150]
    return None
