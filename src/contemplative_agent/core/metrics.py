"""Self-improvement metrics computed from episode logs.

Provides feedback on whether the agent's behavior aligns with
the engagement principles (deep over broad, listening, evolving).
Not for external reporting — purely internal self-assessment.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict

from .memory import EpisodeLog


@dataclass(frozen=True)
class SessionReport:
    """Aggregated behavior metrics for a time period."""

    period_days: int
    comments_sent: int
    replies_sent: int
    replies_received: int
    reply_rate: float  # replies_received / (comments_sent + replies_sent) if > 0
    unique_agents: int
    repeat_conversations: int  # agents with 2+ exchanges
    posts_made: int
    follows: int
    topics: list  # type: ignore[type-arg]  # list[str], py3.9 compat


def compute_metrics(episode_log: EpisodeLog, days: int = 7) -> SessionReport:
    """Read recent episodes and compute behavior metrics.

    Args:
        episode_log: The episode log to read from.
        days: Number of days to look back.

    Returns:
        A frozen SessionReport dataclass.
    """
    records = episode_log.read_range(days=days)

    comments_sent = 0
    replies_sent = 0
    replies_received = 0
    posts_made = 0
    follows = 0
    topics: list[str] = []

    # Track per-agent exchange counts for repeat_conversations
    agent_exchanges: Counter[str] = Counter()
    seen_agents: set[str] = set()

    for record in records:
        record_type = record.get("type", "")
        data: Dict[str, Any] = record.get("data", {})

        if record_type == "interaction":
            direction = data.get("direction", "")
            interaction_type = data.get("interaction_type", "")
            agent_id = data.get("agent_id", "")

            if agent_id:
                seen_agents.add(agent_id)
                agent_exchanges[agent_id] += 1

            if direction == "sent":
                if interaction_type == "comment":
                    comments_sent += 1
                elif interaction_type == "reply":
                    replies_sent += 1
            elif direction == "received":
                if interaction_type in ("comment", "reply"):
                    replies_received += 1

        elif record_type == "post":
            posts_made += 1
            topic = data.get("topic_summary", "")
            if topic:
                topics.append(topic)

        elif record_type == "activity":
            action = data.get("action", "")
            if action == "follow":
                follows += 1

    total_sent = comments_sent + replies_sent
    reply_rate = replies_received / total_sent if total_sent > 0 else 0.0

    repeat_conversations = sum(1 for count in agent_exchanges.values() if count >= 2)

    return SessionReport(
        period_days=days,
        comments_sent=comments_sent,
        replies_sent=replies_sent,
        replies_received=replies_received,
        reply_rate=round(reply_rate, 3),
        unique_agents=len(seen_agents),
        repeat_conversations=repeat_conversations,
        posts_made=posts_made,
        follows=follows,
        topics=topics,
    )


def format_report(report: SessionReport, fmt: str = "text") -> str:
    """Format a SessionReport as human-readable text or Markdown.

    Args:
        report: The report to format.
        fmt: 'text' or 'md'.

    Returns:
        Formatted string.
    """
    if fmt == "md":
        return _format_md(report)
    return _format_text(report)


def _format_text(report: SessionReport) -> str:
    lines = [
        f"Session Report ({report.period_days} days)",
        f"  Comments sent:        {report.comments_sent}",
        f"  Replies sent:         {report.replies_sent}",
        f"  Replies received:     {report.replies_received}",
        f"  Reply rate:           {report.reply_rate:.1%}",
        f"  Unique agents:        {report.unique_agents}",
        f"  Repeat conversations: {report.repeat_conversations}",
        f"  Posts made:           {report.posts_made}",
        f"  Follows:              {report.follows}",
    ]
    if report.topics:
        lines.append(f"  Topics: {', '.join(report.topics)}")
    return "\n".join(lines)


def _format_md(report: SessionReport) -> str:
    lines = [
        f"## Session Report ({report.period_days} days)",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Comments sent | {report.comments_sent} |",
        f"| Replies sent | {report.replies_sent} |",
        f"| Replies received | {report.replies_received} |",
        f"| Reply rate | {report.reply_rate:.1%} |",
        f"| Unique agents | {report.unique_agents} |",
        f"| Repeat conversations | {report.repeat_conversations} |",
        f"| Posts made | {report.posts_made} |",
        f"| Follows | {report.follows} |",
    ]
    if report.topics:
        lines.append("")
        lines.append("### Topics")
        for topic in report.topics:
            lines.append(f"- {topic}")
    return "\n".join(lines)
