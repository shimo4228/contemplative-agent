"""Sleep-time memory distillation: extract patterns from episode logs."""

from __future__ import annotations

import copy
import json as json_mod
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from .llm import generate, get_axiom_prompt, _get_default_system_prompt, get_distill_system_prompt, validate_identity_content
from .knowledge_store import effective_importance
from .memory import EpisodeLog, KnowledgeStore
from .prompts import (
    DISTILL_PROMPT,
    DISTILL_REFINE_PROMPT,
    DISTILL_IMPORTANCE_PROMPT,
    DISTILL_DEDUP_PROMPT,
    DISTILL_CLASSIFY_PROMPT,
    DISTILL_CONSTITUTIONAL_PROMPT,
    IDENTITY_DISTILL_PROMPT,
    IDENTITY_REFINE_PROMPT,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 30

# JSON Schemas for constrained decoding (Ollama v0.5+ format parameter)
CLASSIFY_SCHEMA: Dict = {
    "type": "string",
    "enum": ["constitutional", "noise", "uncategorized"],
}
IMPORTANCE_SCHEMA: Dict = {
    "type": "object",
    "properties": {"scores": {"type": "array", "items": {"type": "integer"}}},
    "required": ["scores"],
}
DEDUP_SCHEMA: Dict = {
    "type": "object",
    "properties": {"decisions": {"type": "array", "items": {"type": "string"}}},
    "required": ["decisions"],
}

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

    # Step 0: Classify episodes
    classified = _classify_episodes(records, constitution=get_axiom_prompt())
    if classified.noise:
        logger.info("Step 0: %d noise episodes excluded from distillation", len(classified.noise))
    logger.info(
        "Step 0: %d constitutional, %d uncategorized, %d noise",
        len(classified.constitutional), len(classified.uncategorized), len(classified.noise),
    )

    # Determine source date range from records
    timestamps = [r.get("ts", "")[:10] for r in records if r.get("ts")]
    source_date = timestamps[0] if timestamps else None
    if timestamps and timestamps[0] != timestamps[-1]:
        source_date = f"{timestamps[0]}~{timestamps[-1]}"

    all_results: List[str] = []
    total_added = 0
    total_updated = 0

    # Process each category through the 3-step pipeline
    for category, cat_records in [
        ("uncategorized", list(classified.uncategorized)),
        ("constitutional", list(classified.constitutional)),
    ]:
        if not cat_records:
            continue

        cat_results = _distill_category(
            cat_records, knowledge, category, source_date, dry_run,
        )
        all_results.extend(cat_results.results)
        total_added += cat_results.added
        total_updated += cat_results.updated

    if not dry_run and (total_added or total_updated):
        knowledge.save()
        logger.info("Distill complete: %d added, %d updated", total_added, total_updated)

    return "\n\n".join(all_results)


@dataclass(frozen=True)
class IdentityResult:
    """Result of a successful identity distillation."""

    text: str
    target_path: Path


def distill_identity(
    knowledge_store: Optional[KnowledgeStore] = None,
    identity_path: Optional[Path] = None,
) -> Union[str, IdentityResult]:
    """Distill knowledge into an updated identity description.

    Reads the current identity and accumulated knowledge, then asks the LLM
    to write a brief self-description reflecting the agent's actual experience.

    File writing is the caller's responsibility (ADR-0012 approval gate).

    Args:
        knowledge_store: KnowledgeStore instance (uses default if None).
        identity_path: Path to identity.md file.

    Returns:
        IdentityResult on success, or error message string.
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
    refined = generate(refine_prompt, system=_get_default_system_prompt(), max_length=4000)
    if refined is None:
        msg = "LLM failed at step 2 (refine). Using step 1 output."
        logger.warning(msg)
        refined = result

    # Clean up: strip empty lines and preamble
    lines = [line.strip() for line in refined.strip().splitlines() if line.strip()]
    identity_text = "\n".join(lines)

    # Validate against forbidden patterns before returning
    if not validate_identity_content(identity_text):
        logger.warning("Generated identity failed validation")
        return identity_text

    if not identity_path:
        return identity_text

    return IdentityResult(text=identity_text, target_path=identity_path)


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


def _parse_importance_scores(raw: str, expected_count: int) -> List[float]:
    """Parse {"scores": [8, 5, ...]} into [0.8, 0.5, ...].

    Falls back to comma-separated integers, then 0.5 defaults.
    """
    defaults = [0.5] * expected_count
    text = _strip_code_fence(raw)

    # Try JSON parse
    scores_raw: list = []
    try:
        parsed = json_mod.loads(text)
        scores_raw = parsed.get("scores", [])
    except (json_mod.JSONDecodeError, TypeError, AttributeError):
        # Fallback: try comma-separated integers (e.g., "8, 5, 9, 7")
        try:
            scores_raw = [int(x.strip()) for x in text.split(",") if x.strip()]
        except ValueError:
            logger.warning("Failed to parse importance scores: %s", text[:200])
            return defaults

    if len(scores_raw) != expected_count:
        logger.warning("Importance count mismatch: got %d, expected %d",
                       len(scores_raw), expected_count)
        return defaults

    result = []
    for s in scores_raw:
        try:
            val = int(s)
        except (ValueError, TypeError):
            val = 5
        result.append(max(1, min(10, val)) / 10.0)
    return result


VALID_CATEGORIES = frozenset({"constitutional", "noise", "uncategorized"})


@dataclass(frozen=True)
class _ClassifiedRecords:
    """Records grouped by classification category."""
    constitutional: Tuple[Dict, ...]
    noise: Tuple[Dict, ...]
    uncategorized: Tuple[Dict, ...]


def _parse_classify_result(raw: Optional[str]) -> str:
    """Parse a classification LLM response.

    Scans the entire response for a valid category keyword.
    Returns one of the VALID_CATEGORIES. Falls back to "uncategorized"
    if no valid category is found.
    """
    if raw is None:
        return "uncategorized"
    text = raw.strip().lower()
    if not text:
        return "uncategorized"
    # Search for valid categories in the response
    for cat in ("constitutional", "noise"):
        if cat in text:
            return cat
    if "uncategorized" in text:
        return "uncategorized"
    logger.warning("No category found in %r, defaulting to uncategorized", raw.strip()[:60])
    return "uncategorized"


def _classify_episodes(
    records: List[Dict],
    constitution: str = "",
) -> _ClassifiedRecords:
    """Step 0: Classify episodes into categories via LLM.

    Classifies one record at a time for reliable output from small models.
    Falls back to uncategorized on LLM failure (safe default —
    identical to the existing pipeline behavior with no classification).
    """
    if not records:
        return _ClassifiedRecords(constitutional=(), noise=(), uncategorized=())

    if not DISTILL_CLASSIFY_PROMPT:
        return _ClassifiedRecords(
            constitutional=(), noise=(), uncategorized=tuple(records),
        )

    constitutional = []
    noise = []
    uncategorized = []

    const_text = constitution if constitution else "(no constitutional principles configured)"

    for idx, r in enumerate(records):
        record_type = r.get("type", "unknown")
        data = r.get("data", {})
        ts = r.get("ts", "")
        summary = summarize_record(record_type, data)
        episode_line = f"[{ts[:16]}] {record_type}: {summary}" if summary else f"[{ts[:16]}] {record_type}: (no summary)"

        prompt = DISTILL_CLASSIFY_PROMPT.format(
            episode=episode_line,
            constitution=const_text,
        )
        result = generate(prompt, system=get_distill_system_prompt(), max_length=20, format=CLASSIFY_SCHEMA)
        cat = _parse_classify_result(result)

        if cat == "constitutional":
            constitutional.append(r)
        elif cat == "noise":
            noise.append(r)
        else:
            uncategorized.append(r)

        if (idx + 1) % 50 == 0:
            logger.info("Classified %d/%d episodes", idx + 1, len(records))

    return _ClassifiedRecords(
        constitutional=tuple(constitutional),
        noise=tuple(noise),
        uncategorized=tuple(uncategorized),
    )


@dataclass(frozen=True)
class _CategoryResult:
    """Result of distilling a single category."""
    results: Tuple[str, ...]
    added: int
    updated: int


def _distill_category(
    records: List[Dict],
    knowledge: KnowledgeStore,
    category: str,
    source_date: Optional[str],
    dry_run: bool,
) -> _CategoryResult:
    """Run the 3-step distill pipeline for a single category of records.

    Dedup is performed only against existing patterns of the same category.
    """
    batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    logger.info("[%s] Processing %d episodes in %d batches", category, len(records), len(batches))

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

        step1_prompt = DISTILL_CONSTITUTIONAL_PROMPT if category == "constitutional" else DISTILL_PROMPT
        prompt = step1_prompt.format(
            episodes="\n".join(episode_lines),
        )

        # Step 1: Extract — free-form output, with rules/axioms as lens
        result = generate(prompt, system=get_distill_system_prompt(), max_length=4000)
        if result is None:
            logger.warning("[%s] Batch %d/%d: step 1 (extract) failed", category, batch_idx + 1, len(batches))
            continue

        # Step 2: Summarize — concise patterns as JSON string array
        refine_prompt = DISTILL_REFINE_PROMPT.format(raw_output=result)
        refined = generate(refine_prompt, max_length=4000)
        if refined is None:
            logger.warning("[%s] Batch %d/%d: step 2 (summarize) failed, using step 1 output",
                           category, batch_idx + 1, len(batches))
            refined = result

        all_results.append(refined)

        raw_patterns: List[str] = []
        json_text = _strip_code_fence(refined)
        try:
            parsed = json_mod.loads(json_text)
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
            importance_result = generate(importance_prompt, max_length=4000, format=IMPORTANCE_SCHEMA)
            if importance_result:
                batch_importances = _parse_importance_scores(importance_result, len(batch_patterns))

        all_patterns.extend(batch_patterns)
        all_importances.extend(batch_importances)
        imp_summary = ", ".join(f"{i:.1f}" for i in batch_importances) if batch_importances else "none"
        logger.info(
            "[%s] Batch %d/%d: %d episodes → %d patterns (%d rejected) [importance: %s]",
            category, batch_idx + 1, len(batches), len(batch), len(batch_patterns), rejected, imp_summary,
        )

    if not all_patterns:
        return _CategoryResult(results=tuple(all_results), added=0, updated=0)

    # Dedup within category only: constitutional and uncategorized are independent
    # namespaces. Cross-category overlap is acceptable — the same insight may be
    # relevant both as ethical principle and behavioral pattern.
    existing_same_cat = [
        p for p in knowledge.get_raw_patterns()
        if p.get("category", "uncategorized") == category
    ]
    pre_filter = len(existing_same_cat)
    existing_same_cat = [
        p for p in existing_same_cat
        if effective_importance(p) >= DEDUP_IMPORTANCE_FLOOR
    ]
    if pre_filter > len(existing_same_cat):
        logger.info("[%s] Dedup scope: %d/%d patterns (importance floor %.2f)",
                    category, len(existing_same_cat), pre_filter, DEDUP_IMPORTANCE_FLOOR)

    if dry_run:
        existing_copy = copy.deepcopy(existing_same_cat)
        _, _, _skip, upd, uncertain = _dedup_patterns(
            all_patterns, all_importances, existing_copy,
        )
        if uncertain:
            _, _, _llm_skip, llm_upd = _llm_quality_gate(uncertain, existing_copy)
            upd += llm_upd
        logger.info("[%s] Dry run — %d patterns found, %d would be deduped",
                     category, len(all_patterns), upd)
        return _CategoryResult(results=tuple(all_results), added=0, updated=0)

    # Dedup against existing patterns of same category
    add_patterns, add_importances, _skipped, updated, uncertain = _dedup_patterns(
        all_patterns, all_importances, existing_same_cat,
    )
    if uncertain:
        llm_add, llm_imp, _llm_skip, llm_upd = _llm_quality_gate(
            uncertain, existing_same_cat,
        )
        add_patterns.extend(llm_add)
        add_importances.extend(llm_imp)
        updated += llm_upd
        logger.info("[%s] LLM quality gate: %d uncertain → %d add, %d update, %d skip",
                     category, len(uncertain), len(llm_add), llm_upd, _llm_skip)
    if updated:
        logger.info("[%s] Dedup: %d update (importance boosted)", category, updated)

    for pattern, importance in zip(add_patterns, add_importances):
        knowledge.add_learned_pattern(pattern, source=source_date, importance=importance, category=category)
        logger.info("[%s] Added pattern (importance=%.1f): %s", category, importance, pattern[:80])

    return _CategoryResult(results=tuple(all_results), added=len(add_patterns), updated=updated)


DEDUP_IMPORTANCE_FLOOR = 0.05  # Patterns below this effective importance are excluded from dedup
UNCERTAIN_LOW = 0.3  # Below this ratio → definitely new (ADD)


@dataclass(frozen=True)
class _MatchCandidate:
    """A similar existing pattern found by SequenceMatcher."""
    text: str
    importance: float
    index: int
    ratio: float


@dataclass(frozen=True)
class _UncertainMatch:
    """A new pattern whose similarity is ambiguous (ratio between UNCERTAIN_LOW and threshold)."""
    new_text: str
    new_importance: float
    candidates: Tuple[_MatchCandidate, ...]


def _dedup_patterns(
    new_patterns: List[str],
    new_importances: List[float],
    existing_patterns: List[dict],
    threshold: float = 0.7,
) -> Tuple[List[str], List[float], int, int, List[_UncertainMatch]]:
    """Remove duplicates by comparing new patterns against existing ones.

    Returns (patterns_to_add, importances_to_add, skip_count, update_count, uncertain).
    - SKIP: ratio >= 0.95 (near-exact duplicate)
    - UPDATE: ratio >= threshold against existing (boost importance)
    - UNCERTAIN: ratio in [UNCERTAIN_LOW, threshold) against existing (needs LLM judgment)
    - ADD: ratio < UNCERTAIN_LOW (clearly new)
    """
    add_patterns: List[str] = []
    add_importances: List[float] = []
    skip_count = 0
    update_count = 0
    uncertain: List[_UncertainMatch] = []

    existing_texts = [p["pattern"] for p in existing_patterns]

    for new_text, new_imp in zip(new_patterns, new_importances):
        best_ratio = 0.0
        best_idx = -1
        best_source = ""  # "existing" or "new"

        # Collect all ratios against existing for candidate selection
        existing_ratios: List[Tuple[int, float]] = []
        for idx, existing_text in enumerate(existing_texts):
            ratio = SequenceMatcher(None, new_text, existing_text).ratio()
            existing_ratios.append((idx, ratio))
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
        elif best_ratio >= UNCERTAIN_LOW and best_source == "existing":
            # Ambiguous similarity → collect top-3 candidates for LLM judgment
            top_candidates = sorted(existing_ratios, key=lambda x: x[1], reverse=True)[:3]
            candidates = tuple(
                _MatchCandidate(
                    text=existing_patterns[idx]["pattern"],
                    importance=existing_patterns[idx].get("importance", 0.5),
                    index=idx,
                    ratio=ratio,
                )
                for idx, ratio in top_candidates
                if ratio >= UNCERTAIN_LOW
            )
            if candidates:
                uncertain.append(_UncertainMatch(
                    new_text=new_text,
                    new_importance=new_imp,
                    candidates=candidates,
                ))
                logger.debug("UNCERTAIN (%.2f): %s", best_ratio, new_text[:60])
            else:
                add_patterns.append(new_text)
                add_importances.append(new_imp)
        else:
            add_patterns.append(new_text)
            add_importances.append(new_imp)

    return add_patterns, add_importances, skip_count, update_count, uncertain


def _is_valid_pattern(pattern: str) -> bool:
    """Decision gate: is this pattern worth storing?

    Rejects labels, keywords, and fragments that aren't actionable patterns.
    """
    if len(pattern) < 30:
        return False
    if pattern.count(" ") < 3:
        return False
    return True


def _llm_quality_gate(
    uncertain: List[_UncertainMatch],
    existing_patterns: List[dict],
) -> Tuple[List[str], List[float], int, int]:
    """LLM-based semantic dedup for uncertain matches.

    For patterns where SequenceMatcher ratio is ambiguous (0.3-0.7),
    asks the LLM to judge whether they are semantically the same as
    existing patterns.

    Returns (add_patterns, add_importances, skip_count, update_count).
    Side effect: mutates existing_patterns for UPDATE cases (importance boost + timestamp).
    Fallback: all ADD on LLM failure (same as no gate).
    """
    if not uncertain:
        return [], [], 0, 0

    # Build prompt items
    items: List[str] = []
    for i, match in enumerate(uncertain, 1):
        candidates_text = "\n".join(
            f"  {j}. (ratio={c.ratio:.2f}) \"{c.text[:120]}\""
            for j, c in enumerate(match.candidates, 1)
        )
        items.append(f"=== NEW {i} ===\n\"{match.new_text[:200]}\"\nCANDIDATES:\n{candidates_text}")

    dedup_items = "\n---\n".join(items)
    prompt = DISTILL_DEDUP_PROMPT.format(dedup_items=dedup_items)
    result = generate(prompt, max_length=2000, format=DEDUP_SCHEMA)

    # Parse decisions
    decisions = _parse_dedup_decisions(result, len(uncertain))

    add_patterns: List[str] = []
    add_importances: List[float] = []
    skip_count = 0
    update_count = 0

    for match, decision in zip(uncertain, decisions):
        update_match = re.match(r"UPDATE\s+(\d+)", decision)
        if decision == "ADD":
            add_patterns.append(match.new_text)
            add_importances.append(match.new_importance)
            logger.debug("LLM-GATE ADD: %s", match.new_text[:60])
        elif decision == "SKIP":
            skip_count += 1
            logger.debug("LLM-GATE SKIP: %s", match.new_text[:60])
        elif update_match:
            candidate_idx = int(update_match.group(1)) - 1  # 1-based → 0-based
            if 0 <= candidate_idx < len(match.candidates):
                candidate = match.candidates[candidate_idx]
                old_imp = existing_patterns[candidate.index].get("importance", 0.5)
                existing_patterns[candidate.index]["importance"] = max(old_imp, match.new_importance)
                existing_patterns[candidate.index]["distilled"] = datetime.now(timezone.utc).isoformat(timespec="minutes")
                update_count += 1
                logger.debug("LLM-GATE UPDATE %d: %s", candidate_idx + 1, match.new_text[:60])
            else:
                # Invalid candidate index → ADD as fallback
                add_patterns.append(match.new_text)
                add_importances.append(match.new_importance)
                logger.debug("LLM-GATE invalid index %d, ADD: %s", candidate_idx + 1, match.new_text[:60])
        else:
            # Unparseable decision → ADD as fallback
            add_patterns.append(match.new_text)
            add_importances.append(match.new_importance)
            logger.debug("LLM-GATE unparseable '%s', ADD: %s", decision, match.new_text[:60])

    return add_patterns, add_importances, skip_count, update_count


def _parse_dedup_decisions(raw: Optional[str], expected_count: int) -> List[str]:
    """Parse LLM dedup gate output into a list of decisions.

    Expected format: {"decisions": ["ADD", "UPDATE 1", "SKIP", ...]}
    Handles code-fence wrapping and surrounding text from small models.
    Falls back to all "ADD" on failure.
    """
    fallback = ["ADD"] * expected_count
    if not raw:
        logger.warning("LLM dedup gate returned empty, falling back to ADD all")
        return fallback

    text = _strip_code_fence(raw)

    # Try direct JSON parse
    try:
        parsed = json_mod.loads(text)
        decisions = parsed.get("decisions", [])
        if len(decisions) == expected_count:
            return [str(d).strip().upper() for d in decisions]
        logger.warning("Dedup decision count mismatch: got %d, expected %d",
                       len(decisions), expected_count)
        return fallback
    except (json_mod.JSONDecodeError, TypeError, AttributeError):
        pass

    # Regex: extract {"decisions": [...]} from surrounding text
    match = re.search(r'\{[^{}]*"decisions"\s*:\s*\[.*?\]\s*\}', text, re.DOTALL)
    if match:
        try:
            parsed = json_mod.loads(match.group())
            decisions = parsed.get("decisions", [])
            if len(decisions) == expected_count:
                return [str(d).strip().upper() for d in decisions]
        except (json_mod.JSONDecodeError, TypeError, AttributeError):
            pass

    logger.warning("Failed to parse dedup decisions, raw: %s", raw[:300])
    return fallback


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
