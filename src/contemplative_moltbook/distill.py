"""Sleep-time memory distillation: extract patterns from episode logs."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Literal, Optional

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

EVAL_PROMPT = """\
You are evaluating a candidate pattern for a social media agent's knowledge base.

## Candidate Pattern
{candidate}

## Existing Knowledge (numbered)
{knowledge}

## Evaluation Checklist
Check each item and answer YES or NO:

1. DUPLICATE: Is this pattern already covered by existing knowledge? (same idea, even if worded differently)
2. ACTIONABLE: Does this pattern suggest a concrete behavioral change?
3. REUSABLE: Will this pattern be useful in future sessions, not just a one-time observation?
4. SPECIFIC: Is this pattern concrete enough to act on, not vague or generic?

## Verdict
Based on the checklist, choose exactly one:

- SAVE: Not a duplicate, actionable, reusable, and specific. Worth adding.
- ABSORB: The idea has value but overlaps with an existing pattern. Merge into the existing one.
- DROP: Too vague, not actionable, one-time observation, or trivial. Skip.

If SAVE, reply with ONLY:
VERDICT: SAVE

If ABSORB, reply with:
VERDICT: ABSORB
TARGET: <number of the existing pattern to merge into>
MERGED: <merged pattern text, under 100 chars>

If DROP, reply with ONLY:
VERDICT: DROP
"""


@dataclass(frozen=True)
class EvalVerdict:
    """Result of evaluating a candidate pattern."""

    action: Literal["SAVE", "ABSORB", "DROP"]
    target_index: Optional[int] = None  # 0-based index for ABSORB
    merged_text: Optional[str] = None  # merged pattern for ABSORB


def _format_numbered_knowledge(patterns: List[str]) -> str:
    """Format existing patterns as a numbered list for the eval prompt."""
    if not patterns:
        return "(none yet)"
    return "\n".join(f"{i + 1}. {p}" for i, p in enumerate(patterns))


def _parse_eval_verdict(response: str) -> Optional[EvalVerdict]:
    """Parse an eval verdict from LLM response.

    Returns None if the response cannot be parsed.
    """
    if not response:
        return None

    # Find VERDICT line
    verdict_match = re.search(r"VERDICT:\s*(SAVE|ABSORB|DROP)", response, re.IGNORECASE)
    if not verdict_match:
        return None

    action = verdict_match.group(1).upper()

    if action == "SAVE":
        return EvalVerdict(action="SAVE")

    if action == "DROP":
        return EvalVerdict(action="DROP")

    if action == "ABSORB":
        # Parse TARGET (1-based in prompt, convert to 0-based)
        target_match = re.search(r"TARGET:\s*(\d+)", response)
        merged_match = re.search(r"MERGED:\s*(.+)", response)

        if not target_match or not merged_match:
            return None

        target_index = int(target_match.group(1)) - 1  # 0-based
        merged_text = merged_match.group(1).strip()[:100]

        if target_index < 0:
            return None

        return EvalVerdict(
            action="ABSORB",
            target_index=target_index,
            merged_text=merged_text,
        )

    return None


def _evaluate_pattern(
    candidate: str,
    knowledge: KnowledgeStore,
) -> EvalVerdict:
    """Evaluate a candidate pattern using the LLM.

    Returns a verdict. Falls back to SAVE on parse failure.
    """
    existing = knowledge.get_learned_patterns()
    prompt = EVAL_PROMPT.format(
        candidate=candidate,
        knowledge=_format_numbered_knowledge(existing),
    )

    response = generate(prompt, max_length=500)
    if response is None:
        logger.warning("Eval LLM failed — falling back to SAVE")
        return EvalVerdict(action="SAVE")

    verdict = _parse_eval_verdict(response)
    if verdict is None:
        logger.warning(
            "Failed to parse eval verdict — falling back to SAVE. "
            "Raw response: %s",
            response[:200],
        )
        return EvalVerdict(action="SAVE")

    # Validate ABSORB target index
    if verdict.action == "ABSORB":
        if verdict.target_index is not None and verdict.target_index >= len(existing):
            logger.warning(
                "ABSORB target %d out of range (%d patterns) — falling back to SAVE",
                verdict.target_index,
                len(existing),
            )
            return EvalVerdict(action="SAVE")

    return verdict


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

    # Parse bullet points
    candidates = []
    for line in result.splitlines():
        line = line.strip()
        if line.startswith("- "):
            pattern = line[2:].strip()[:100]
            if pattern:
                candidates.append(pattern)

    if dry_run:
        # In dry run, evaluate but don't write
        eval_lines = [result, "", "--- Eval Results ---"]
        for candidate in candidates:
            verdict = _evaluate_pattern(candidate, knowledge)
            eval_lines.append(f"  [{verdict.action}] {candidate}")
            if verdict.action == "ABSORB" and verdict.merged_text:
                eval_lines.append(f"    -> merge into #{verdict.target_index}: {verdict.merged_text}")
        logger.info("Dry run — not writing patterns")
        return "\n".join(eval_lines)

    # Evaluate and apply each candidate pattern
    saved = 0
    absorbed = 0
    dropped = 0

    for candidate in candidates:
        verdict = _evaluate_pattern(candidate, knowledge)

        if verdict.action == "SAVE":
            knowledge.add_learned_pattern(candidate)
            saved += 1
            logger.info("SAVE: %s", candidate)
        elif verdict.action == "ABSORB" and verdict.merged_text is not None:
            assert verdict.target_index is not None
            knowledge.replace_learned_pattern(verdict.target_index, verdict.merged_text)
            absorbed += 1
            logger.info(
                "ABSORB: merged into #%d -> %s",
                verdict.target_index,
                verdict.merged_text,
            )
        elif verdict.action == "DROP":
            dropped += 1
            logger.info("DROP: %s", candidate)

    if saved > 0 or absorbed > 0:
        knowledge.save()
        logger.info(
            "Distill complete: %d saved, %d absorbed, %d dropped",
            saved, absorbed, dropped,
        )

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
