"""Sleep-time memory distillation: extract patterns from episode logs."""

from __future__ import annotations

import json as json_mod
import logging
import os
import stat
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .llm import generate, get_default_system_prompt, get_distill_system_prompt, validate_identity_content
from .memory import EpisodeLog, KnowledgeStore
from .prompts import (
    DISTILL_PROMPT,
    DISTILL_REFINE_PROMPT,
    DISTILL_IMPORTANCE_PROMPT,
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
        result = generate(prompt, system=get_distill_system_prompt(), max_length=4000)
        if result is None:
            logger.warning("Batch %d/%d: step 1 (extract) failed", batch_idx + 1, len(batches))
            continue

        # Step 2: Summarize — concise patterns as JSON string array
        refine_prompt = DISTILL_REFINE_PROMPT.format(raw_output=result)
        refined = generate(refine_prompt, max_length=4000)
        if refined is None:
            logger.warning("Batch %d/%d: step 2 (summarize) failed, using step 1 output", batch_idx + 1, len(batches))
            refined = result

        all_results.append(refined)

        raw_patterns: List[str] = []
        try:
            parsed = json_mod.loads(refined)
            for item in parsed.get("patterns", []):
                text = str(item).strip() if item else ""
                if text:
                    raw_patterns.append(text)
        except (json_mod.JSONDecodeError, TypeError):
            # Fallback: bullet-point parsing
            for line in refined.splitlines():
                line = line.strip()
                if line.startswith("- "):
                    pattern = line[2:].strip()
                    if pattern:
                        raw_patterns.append(pattern)

        # Decision gate: reject low-quality patterns
        batch_patterns = [p for p in raw_patterns if _is_valid_pattern(p)]
        rejected = len(raw_patterns) - len(batch_patterns)

        # Step 3: Evaluate importance — separate LLM call, single task
        batch_importances = [0.5] * len(batch_patterns)
        if batch_patterns and DISTILL_IMPORTANCE_PROMPT:
            patterns_text = "\n".join(f"- {p}" for p in batch_patterns)
            importance_prompt = DISTILL_IMPORTANCE_PROMPT.format(patterns=patterns_text)
            importance_result = generate(importance_prompt, max_length=4000)
            if importance_result:
                batch_importances = _parse_importance_scores(importance_result, len(batch_patterns))

        all_patterns.extend(batch_patterns)
        all_importances.extend(batch_importances)
        imp_summary = ", ".join(f"{i:.1f}" for i in batch_importances) if batch_importances else "none"
        logger.info(
            "Batch %d/%d: %d episodes → %d patterns (%d rejected) [importance: %s]",
            batch_idx + 1, len(batches), len(batch), len(batch_patterns), rejected, imp_summary,
        )

    if dry_run:
        # Simulate dedup for visibility (no writes)
        # deep copy to avoid mutating existing patterns during simulation
        import copy
        _, _, _skip, upd = _dedup_patterns(
            all_patterns, all_importances, copy.deepcopy(knowledge._learned_patterns),
        )
        logger.info("Dry run — %d patterns found, %d would be deduped, not writing",
                     len(all_patterns), upd)
        return "\n\n".join(all_results)

    # Determine source date range from records
    timestamps = [r.get("ts", "")[:10] for r in records if r.get("ts")]
    source_date = timestamps[0] if timestamps else None
    if timestamps and timestamps[0] != timestamps[-1]:
        source_date = f"{timestamps[0]}~{timestamps[-1]}"

    # Dedup against existing patterns
    add_patterns, add_importances, _skipped, updated = _dedup_patterns(
        all_patterns, all_importances, knowledge._learned_patterns,
    )
    if updated:
        logger.info("Dedup: %d update (importance boosted)", updated)

    for pattern, importance in zip(add_patterns, add_importances):
        knowledge.add_learned_pattern(pattern, source=source_date, importance=importance)
        logger.info("Added pattern (importance=%.1f): %s", importance, pattern[:80])

    if add_patterns or updated:
        knowledge.save()
        logger.info("Distill complete: %d added, %d updated from %d batches",
                     len(add_patterns), updated, len(batches))

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
    result = generate(prompt, system=get_distill_system_prompt(), max_length=4000)
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
        identity_path.write_text(identity_text + "\n", encoding="utf-8")
        os.chmod(identity_path, stat.S_IRUSR | stat.S_IWUSR)
        logger.info("Identity updated: %s", identity_path)

    return identity_text


def _parse_importance_scores(raw: str, expected_count: int) -> List[float]:
    """Parse {"scores": [8, 5, ...]} into [0.8, 0.5, ...].

    Falls back to 0.5 for all if parsing fails or count mismatches.
    """
    try:
        parsed = json_mod.loads(raw)
        scores_raw = parsed.get("scores", [])
        if len(scores_raw) != expected_count:
            logger.warning("Importance count mismatch: got %d, expected %d",
                           len(scores_raw), expected_count)
            return [0.5] * expected_count
        result = []
        for s in scores_raw:
            try:
                val = int(s)
            except (ValueError, TypeError):
                val = 5
            result.append(max(1, min(10, val)) / 10.0)
        return result
    except (json_mod.JSONDecodeError, TypeError):
        logger.warning("Failed to parse importance scores, using defaults")
        return [0.5] * expected_count


def _dedup_patterns(
    new_patterns: List[str],
    new_importances: List[float],
    existing_patterns: List[dict],
    threshold: float = 0.7,
) -> Tuple[List[str], List[float], int, int]:
    """Remove duplicates by comparing new patterns against existing ones.

    Returns (patterns_to_add, importances_to_add, skip_count, update_count).
    UPDATE: boosts existing pattern's importance to max(old, new) and refreshes timestamp.
    """
    add_patterns: List[str] = []
    add_importances: List[float] = []
    skip_count = 0
    update_count = 0

    existing_texts = [p["pattern"] for p in existing_patterns]

    for new_text, new_imp in zip(new_patterns, new_importances):
        best_ratio = 0.0
        best_idx = -1
        best_source = ""  # "existing" or "new"

        # Compare against existing knowledge patterns
        for idx, existing_text in enumerate(existing_texts):
            ratio = SequenceMatcher(None, new_text, existing_text).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx
                best_source = "existing"

        # Compare against already-accepted new patterns (cross-batch dedup)
        for idx, accepted_text in enumerate(add_patterns):
            ratio = SequenceMatcher(None, new_text, accepted_text).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx
                best_source = "new"

        if best_ratio >= 0.95:
            # Near-exact duplicate → SKIP
            skip_count += 1
            logger.debug("SKIP (%.2f, %s): %s", best_ratio, best_source, new_text[:60])
        elif best_ratio >= threshold and best_source == "existing":
            # Similar to existing → UPDATE (boost importance, refresh timestamp)
            old_imp = existing_patterns[best_idx].get("importance", 0.5)
            existing_patterns[best_idx]["importance"] = max(old_imp, new_imp)
            existing_patterns[best_idx]["distilled"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
            update_count += 1
            logger.debug("UPDATE (%.2f): %s", best_ratio, new_text[:60])
        elif best_ratio >= threshold and best_source == "new":
            # Similar to already-accepted new pattern → keep higher importance
            if new_imp > add_importances[best_idx]:
                add_importances[best_idx] = new_imp
            skip_count += 1
            logger.debug("SKIP-NEW (%.2f): %s", best_ratio, new_text[:60])
        else:
            add_patterns.append(new_text)
            add_importances.append(new_imp)

    return add_patterns, add_importances, skip_count, update_count


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
