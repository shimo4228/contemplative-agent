"""Sleep-time memory distillation: extract patterns from episode logs."""

from __future__ import annotations

import logging
from typing import Optional

from .llm import generate
from .memory import EpisodeLog, KnowledgeStore

logger = logging.getLogger(__name__)

DISTILL_PROMPT = """\
You are analyzing a social media agent's recent activity logs.
Extract 1-3 actionable patterns or insights from these episodes.

Rules:
- Each pattern should be one concise sentence (under 100 chars)
- Focus on what worked well, what didn't, and behavioral adjustments
- Do NOT include timestamps or specific post IDs
- Reply with bullet points only, one per line, starting with "- "

Current knowledge:
{knowledge}

Recent episodes:
{episodes}
"""


def distill(
    days: int = 1,
    dry_run: bool = False,
    episode_log: Optional[EpisodeLog] = None,
    knowledge_store: Optional[KnowledgeStore] = None,
) -> str:
    """Distill recent episodes into learned patterns.

    Args:
        days: Number of days of episodes to process.
        dry_run: If True, return results without writing.
        episode_log: EpisodeLog instance (uses default if None).
        knowledge_store: KnowledgeStore instance (uses default if None).

    Returns:
        The distilled patterns as a string.
    """
    episodes = episode_log or EpisodeLog()
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    records = episodes.read_range(days=days)
    if not records:
        msg = "No episodes found for distillation."
        logger.info(msg)
        return msg

    # Format episodes for the prompt
    episode_lines = []
    for r in records[-50:]:  # Limit to last 50 records for context window
        record_type = r.get("type", "unknown")
        data = r.get("data", {})
        ts = r.get("ts", "")
        summary = _summarize_record(record_type, data)
        if summary:
            episode_lines.append(f"[{ts[:16]}] {record_type}: {summary}")

    if not episode_lines:
        msg = "No meaningful episodes to distill."
        logger.info(msg)
        return msg

    prompt = DISTILL_PROMPT.format(
        knowledge=knowledge.get_context_string() or "(none yet)",
        episodes="\n".join(episode_lines),
    )

    result = generate(prompt, max_length=1000)
    if result is None:
        msg = "LLM failed to generate distillation."
        logger.warning(msg)
        return msg

    if dry_run:
        logger.info("Dry run — not writing patterns")
        return result

    # Parse bullet points and add to knowledge
    patterns_added = 0
    for line in result.splitlines():
        line = line.strip()
        if line.startswith("- "):
            pattern = line[2:].strip()[:100]
            if pattern:
                knowledge.add_learned_pattern(pattern)
                patterns_added += 1

    if patterns_added > 0:
        knowledge.save()
        logger.info("Added %d learned patterns", patterns_added)

    # Cleanup old episodes
    deleted = episodes.cleanup()
    if deleted > 0:
        logger.info("Cleaned up %d old log files", deleted)

    return result


def _summarize_record(record_type: str, data: dict) -> str:
    """Create a one-line summary of an episode record."""
    if record_type == "interaction":
        direction = data.get("direction", "?")
        agent = data.get("agent_name", "unknown")
        content = data.get("content_summary", "")[:80]
        return f"{direction} with {agent}: {content}"
    elif record_type == "post":
        title = data.get("title", data.get("topic_summary", "untitled"))
        return f"posted: {title}"
    elif record_type == "insight":
        return data.get("observation", "")[:80]
    elif record_type == "activity":
        action = data.get("action", "unknown")
        target = data.get("target_agent", data.get("post_id", ""))
        return f"{action} {target}".strip()
    return ""
