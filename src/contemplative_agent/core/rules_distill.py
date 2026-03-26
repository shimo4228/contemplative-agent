"""Rules distillation: synthesize learned patterns into behavioral rules.

Two-stage LLM pipeline (ADR-0008): free-form extraction → structured Markdown.
Human in the loop — this command is never auto-scheduled.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional

from ._io import write_restricted
from .insight import _extract_title, _slugify
from .llm import generate, get_distill_system_prompt, validate_identity_content
from .memory import KnowledgeStore
from .prompts import RULES_DISTILL_PROMPT, RULES_DISTILL_REFINE_PROMPT

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 10
BATCH_SIZE = 30


def _extract_rules(patterns: List[str]) -> Optional[str]:
    """Extract behavioral rules from patterns via 2-stage LLM pipeline.

    Stage 1: Free-form extraction with constitution as lens.
    Stage 2: Refine into structured Markdown.
    """
    prompt = RULES_DISTILL_PROMPT.format(
        patterns="\n".join(f"- {p}" for p in patterns),
    )

    raw = generate(prompt, system=get_distill_system_prompt(), max_length=4000)
    if raw is None:
        logger.warning("Stage 1 (extraction) failed.")
        return None

    refine_prompt = RULES_DISTILL_REFINE_PROMPT.format(raw_output=raw)
    result = generate(refine_prompt, max_length=3000)
    if result is None:
        logger.warning("Stage 2 (refinement) failed.")
        return None

    if _extract_title(result) is None:
        logger.warning("Rules extraction has no title (# line). Dropping.")
        logger.debug("Raw LLM output (first 200 chars): %.200s", result)
        return None

    return result


def _read_last_run(rules_dir: Optional[Path]) -> Optional[str]:
    """Read the timestamp of the last rules-distill run."""
    if rules_dir is None:
        return None
    marker = rules_dir / ".last_rules_distill"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return None


def _write_last_run(rules_dir: Path) -> None:
    """Record the current timestamp as the last rules-distill run."""
    rules_dir.mkdir(parents=True, exist_ok=True)
    marker = rules_dir / ".last_rules_distill"
    marker.write_text(
        datetime.now(timezone.utc).isoformat(timespec="minutes") + "\n",
        encoding="utf-8",
    )


def distill_rules(
    knowledge_store: Optional[KnowledgeStore] = None,
    rules_dir: Optional[Path] = None,
    dry_run: bool = False,
    full: bool = False,
) -> str:
    """Distill universal behavioral rules from accumulated knowledge patterns.

    Two-stage pipeline per batch: free-form extraction → structured Markdown.
    Higher threshold than insight (10 patterns minimum) because premature
    generalization produces platitudes, not principles.

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        rules_dir: Directory to write rule files (e.g. config/rules/learned/).
        dry_run: If True, show result without writing.
        full: If True, process all patterns instead of only new ones.

    Returns:
        The rule contents and summary.
    """
    if knowledge_store is None:
        return "No knowledge store provided."

    knowledge_store.load()

    if full:
        patterns: List[str] = list(knowledge_store.get_learned_patterns(category="uncategorized"))
    else:
        last_run = _read_last_run(rules_dir)
        if last_run:
            patterns = list(knowledge_store.get_learned_patterns_since(last_run, category="uncategorized"))
            logger.info("Incremental mode: %d new patterns since %s", len(patterns), last_run)
        else:
            patterns = list(knowledge_store.get_learned_patterns(category="uncategorized"))
            logger.info("No previous rules-distill run found, processing all %d patterns", len(patterns))

    if len(patterns) < MIN_PATTERNS_REQUIRED:
        return (
            f"Insufficient patterns ({len(patterns)}/{MIN_PATTERNS_REQUIRED}). "
            f"Universal principles require a critical mass of knowledge."
        )

    batches = [
        patterns[i : i + BATCH_SIZE]
        for i in range(0, len(patterns), BATCH_SIZE)
    ]
    if len(batches) > 1 and len(batches[-1]) < MIN_PATTERNS_REQUIRED:
        batches[-2].extend(batches[-1])
        batches.pop()

    logger.info(
        "Processing %d patterns in %d batches", len(patterns), len(batches)
    )

    if not dry_run and rules_dir is not None:
        rules_dir.mkdir(parents=True, exist_ok=True)

    all_results: List[str] = []
    saved_count = 0
    dropped_count = 0

    for batch_idx, batch in enumerate(batches):
        logger.info(
            "Batch %d/%d: %d patterns", batch_idx + 1, len(batches), len(batch)
        )

        rules_text = _extract_rules(batch)
        if rules_text is None:
            logger.warning("Batch %d/%d: extraction failed", batch_idx + 1, len(batches))
            dropped_count += 1
            continue

        if not validate_identity_content(rules_text):
            logger.warning("Batch %d/%d: forbidden pattern detected", batch_idx + 1, len(batches))
            dropped_count += 1
            continue

        if not dry_run and rules_dir is not None:
            title = _extract_title(rules_text) or ""
            slug = _slugify(title)
            if not slug:
                logger.warning("Batch %d/%d: empty slug, dropping", batch_idx + 1, len(batches))
                dropped_count += 1
                continue
            today = date.today().strftime("%Y%m%d")
            filename = f"{slug}-{today}.md"
            file_path = rules_dir / filename

            if not file_path.resolve().is_relative_to(rules_dir.resolve()):
                logger.error("Rule path escape attempt: %s", file_path)
                dropped_count += 1
                continue

            write_restricted(file_path, rules_text)
            logger.info("Rule written: %s", file_path)

        all_results.append(rules_text)
        saved_count += 1

    if not all_results:
        return "Failed to extract rules from knowledge."

    if not dry_run and rules_dir is not None and saved_count > 0:
        _write_last_run(rules_dir)

    summary = f"\n--- Summary: {saved_count} saved, {dropped_count} dropped ---"
    return "\n\n".join(all_results) + summary
