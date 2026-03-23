"""Sleep-time memory distillation: extract patterns from episode logs."""

from __future__ import annotations

import json as json_mod
import logging
import os
import stat
from pathlib import Path
from typing import Dict, List, Optional

from ._io import archive_before_write
from .llm import generate, get_default_system_prompt, get_rules_system_prompt, validate_identity_content
from .memory import EpisodeLog, KnowledgeStore
from .prompts import (
    DISTILL_PROMPT,
    DISTILL_REFINE_PROMPT,
    IDENTITY_DISTILL_PROMPT,
    IDENTITY_REFINE_PROMPT,
)

logger = logging.getLogger(__name__)


def distill(
    days: int = 1,
    dry_run: bool = False,
    episode_log: Optional[EpisodeLog] = None,
    knowledge_store: Optional[KnowledgeStore] = None,
    log_files: Optional[List[Path]] = None,
) -> str:
    """Distill recent episodes into learned patterns.

    Single-pass: extract patterns from episodes and accumulate them.
    Quality filtering is deferred to the insight command.

    Args:
        days: Number of days of episodes to process.
        dry_run: If True, return results without writing.
        episode_log: EpisodeLog instance (uses default if None).
        knowledge_store: KnowledgeStore instance (uses default if None).
        log_files: Explicit JSONL file paths to process (overrides days).

    Returns:
        The distilled patterns as a string.
    """
    episodes = episode_log or EpisodeLog()
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if log_files:
        records: List[Dict] = []
        for path in log_files:
            records.extend(EpisodeLog.read_file(path))
    else:
        records = episodes.read_range(days=days)
    if not records:
        msg = "No episodes found for distillation."
        logger.info(msg)
        return msg

    # Split records into batches of BATCH_SIZE (sleep cycle analogy)
    BATCH_SIZE = 30
    batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    logger.info("Processing %d episodes in %d batches", len(records), len(batches))

    all_patterns: List[str] = []
    all_importances: List[float] = []
    all_results: List[str] = []

    for batch_idx, batch in enumerate(batches):
        episode_lines = []
        for r in batch:
            record_type = r.get("type", "unknown")
            data = r.get("data", {})
            ts = r.get("ts", "")
            summary = summarize_record(record_type, data)
            if summary:
                episode_lines.append(f"[{ts[:16]}] {record_type}: {summary}")

        if not episode_lines:
            continue

        prompt = DISTILL_PROMPT.format(
            episodes="\n".join(episode_lines),
        )

        # Step 1: Extract — free-form output, with rules/axioms as lens
        result = generate(prompt, system=get_rules_system_prompt(), max_length=4000)
        if result is None:
            logger.warning("Batch %d/%d: step 1 (extract) failed", batch_idx + 1, len(batches))
            continue

        # Step 2: Refine — summarize + structure (LLM produces JSON naturally)
        refine_prompt = DISTILL_REFINE_PROMPT.format(raw_output=result)
        refined = generate(refine_prompt, max_length=4000)
        if refined is None:
            logger.warning("Batch %d/%d: step 2 (refine) failed, using step 1 output", batch_idx + 1, len(batches))
            refined = result

        all_results.append(refined)

        raw_patterns: List[str] = []
        raw_importances: List[float] = []
        try:
            parsed = json_mod.loads(refined)
            for item in parsed.get("patterns", []):
                if isinstance(item, dict):
                    text = item.get("text", "").strip()
                    imp_raw = item.get("importance", 5)
                    try:
                        imp_raw = int(imp_raw)
                    except (ValueError, TypeError):
                        imp_raw = 5
                    imp = max(1, min(10, imp_raw)) / 10.0
                    if text:
                        raw_patterns.append(text)
                        raw_importances.append(imp)
                elif isinstance(item, str):
                    text = item.strip()
                    if text:
                        raw_patterns.append(text)
                        raw_importances.append(0.5)
        except (json_mod.JSONDecodeError, TypeError):
            # Fallback: bullet-point parsing
            for line in refined.splitlines():
                line = line.strip()
                if line.startswith("- "):
                    pattern = line[2:].strip()
                    if pattern:
                        raw_patterns.append(pattern)
                        raw_importances.append(0.5)

        # Decision gate: reject low-quality patterns
        batch_patterns = []
        batch_importances = []
        for p, imp in zip(raw_patterns, raw_importances):
            if _is_valid_pattern(p):
                batch_patterns.append(p)
                batch_importances.append(imp)
        rejected = len(raw_patterns) - len(batch_patterns)

        all_patterns.extend(batch_patterns)
        all_importances.extend(batch_importances)
        logger.info(
            "Batch %d/%d: %d episodes → %d patterns (%d rejected)",
            batch_idx + 1, len(batches), len(batch), len(batch_patterns), rejected,
        )

    if dry_run:
        logger.info("Dry run — %d patterns found across %d batches, not writing",
                     len(all_patterns), len(batches))
        return "\n\n".join(all_results)

    # Determine source date range from records
    timestamps = [r.get("ts", "")[:10] for r in records if r.get("ts")]
    source_date = timestamps[0] if timestamps else None
    if timestamps and timestamps[0] != timestamps[-1]:
        source_date = f"{timestamps[0]}~{timestamps[-1]}"

    for pattern, importance in zip(all_patterns, all_importances):
        knowledge.add_learned_pattern(pattern, source=source_date, importance=importance)
        logger.info("Added pattern (importance=%.1f): %s", importance, pattern[:80])

    if all_patterns:
        knowledge.save()
        logger.info("Distill complete: %d patterns added from %d batches",
                     len(all_patterns), len(batches))

    return "\n\n".join(all_results)


def distill_identity(
    knowledge_store: Optional[KnowledgeStore] = None,
    identity_path: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Distill knowledge into an updated identity description.

    Reads the current identity and accumulated knowledge, then asks the LLM
    to write a brief self-description reflecting the agent's actual experience.

    Args:
        knowledge_store: KnowledgeStore instance (uses default if None).
        identity_path: Path to identity.md file.
        dry_run: If True, return result without writing.

    Returns:
        The generated identity text.
    """
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    knowledge_text = knowledge.get_context_string()
    if not knowledge_text:
        msg = "No knowledge available for identity distillation."
        logger.info(msg)
        return msg

    if not IDENTITY_DISTILL_PROMPT:
        msg = "identity_distill.md prompt template not found."
        logger.warning(msg)
        return msg

    current_identity = ""
    if identity_path and identity_path.exists():
        current_identity = identity_path.read_text(encoding="utf-8").strip()

    prompt = IDENTITY_DISTILL_PROMPT.format(
        current_identity=current_identity or "(no prior identity)",
        knowledge=knowledge_text,
    )

    # Step 1: Free-form self-analysis (rules/axioms for value grounding,
    # but no identity — it's already in the prompt via {current_identity})
    result = generate(prompt, system=get_rules_system_prompt(), max_length=4000)
    if result is None:
        msg = "LLM failed at step 1 (self-analysis)."
        logger.warning(msg)
        return msg

    # Step 2: Refine into simple persona
    refine_prompt = IDENTITY_REFINE_PROMPT.format(raw_output=result)
    refined = generate(refine_prompt, system=get_default_system_prompt(), max_length=4000)
    if refined is None:
        msg = "LLM failed at step 2 (refine). Using step 1 output."
        logger.warning(msg)
        refined = result

    # Clean up: strip empty lines and preamble
    lines = [l.strip() for l in refined.strip().splitlines() if l.strip()]
    identity_text = "\n".join(lines)

    if dry_run:
        logger.info("Dry run — not writing identity")
        return identity_text

    # Validate against forbidden patterns before writing
    if not validate_identity_content(identity_text):
        logger.warning("Generated identity failed validation — not writing")
        return identity_text

    if identity_path:
        history_dir = identity_path.parent / "history" / "identity"
        archive_before_write(identity_path, history_dir)
        identity_path.write_text(identity_text + "\n", encoding="utf-8")
        os.chmod(identity_path, stat.S_IRUSR | stat.S_IWUSR)
        logger.info("Identity updated: %s", identity_path)

    return identity_text


def _is_valid_pattern(pattern: str) -> bool:
    """Decision gate: is this pattern worth storing?

    Rejects labels, keywords, and fragments that aren't actionable patterns.
    """
    if len(pattern) < 30:
        return False
    if pattern.count(" ") < 3:
        return False
    return True


def summarize_record(record_type: str, data: dict) -> str:
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
