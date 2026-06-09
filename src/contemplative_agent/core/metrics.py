"""Self-improvement metrics computed from episode logs.

Provides feedback on whether the agent's behavior aligns with
the engagement principles (deep over broad, listening, evolving).
Not for external reporting — purely internal self-assessment.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
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


@dataclass
class _Tally:
    """Mutable per-record-type accumulator internal to compute_metrics."""

    comments_sent: int = 0
    replies_sent: int = 0
    replies_received: int = 0
    posts_made: int = 0
    follows: int = 0
    topics: list = field(default_factory=list)  # type: ignore[type-arg]
    # Track per-agent exchange counts for repeat_conversations
    agent_exchanges: Counter = field(default_factory=Counter)  # type: ignore[type-arg]
    seen_agents: set = field(default_factory=set)  # type: ignore[type-arg]

    def add_interaction(self, data: Dict[str, Any]) -> None:
        direction = data.get("direction", "")
        interaction_type = data.get("interaction_type", "")
        agent_id = data.get("agent_id", "")

        if agent_id:
            self.seen_agents.add(agent_id)
            self.agent_exchanges[agent_id] += 1

        if direction == "sent":
            if interaction_type == "comment":
                self.comments_sent += 1
            elif interaction_type == "reply":
                self.replies_sent += 1
        elif direction == "received":
            if interaction_type in ("comment", "reply"):
                self.replies_received += 1

    def add_post(self, data: Dict[str, Any]) -> None:
        self.posts_made += 1
        topic = data.get("topic_summary", "")
        if topic:
            self.topics.append(topic)

    def add_activity(self, data: Dict[str, Any]) -> None:
        if data.get("action", "") == "follow":
            self.follows += 1


def compute_metrics(episode_log: EpisodeLog, days: int = 7) -> SessionReport:
    """Read recent episodes and compute behavior metrics.

    Args:
        episode_log: The episode log to read from.
        days: Number of days to look back.

    Returns:
        A frozen SessionReport dataclass.
    """
    records = episode_log.read_range(days=days)

    tally = _Tally()
    for record in records:
        record_type = record.get("type", "")
        data: Dict[str, Any] = record.get("data", {})

        if record_type == "interaction":
            tally.add_interaction(data)
        elif record_type == "post":
            tally.add_post(data)
        elif record_type == "activity":
            tally.add_activity(data)

    total_sent = tally.comments_sent + tally.replies_sent
    reply_rate = tally.replies_received / total_sent if total_sent > 0 else 0.0

    repeat_conversations = sum(1 for count in tally.agent_exchanges.values() if count >= 2)

    return SessionReport(
        period_days=days,
        comments_sent=tally.comments_sent,
        replies_sent=tally.replies_sent,
        replies_received=tally.replies_received,
        reply_rate=round(reply_rate, 3),
        unique_agents=len(tally.seen_agents),
        repeat_conversations=repeat_conversations,
        posts_made=tally.posts_made,
        follows=tally.follows,
        topics=tally.topics,
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
