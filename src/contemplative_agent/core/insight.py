"""Insight extraction: synthesize learned patterns into behavioral skills.

Global embedding cluster per run. Each cluster → one LLM skill
extraction call. Cross-cluster synthesis and quality control are
deferred to skill-stocktake (external).

The view concept (ADR-0009) is not used here. Views still drive
distill's noise gate and stocktake's merge; insight works directly on
``gated != True`` live patterns so that any clustering structure comes
from the embeddings themselves, not from predefined seed texts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from ._io import now_iso
from .artifact_extraction import resolve_artifact_path
from .clustering import cluster_patterns
from .knowledge_store import (
    effective_importance,
    epistemic_counts_for,
    pattern_id,
)
from .llm import generate, get_distill_system_prompt, validate_identity_content
from .memory import KnowledgeStore
from .prompts import INSIGHT_EXTRACTION_PROMPT
from .text_utils import extract_title
from .thresholds import CLUSTER_THRESHOLD_INSIGHT as CLUSTER_THRESHOLD, MAX_BATCH as BATCH_SIZE

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3


@dataclass(frozen=True)
class SkillResult:
    """A single generated skill ready for approval.

    ADR-0050: ``pattern_ids`` carries the content-hash ids of the cluster
    members actually passed to the LLM (kept members only), and
    ``epistemic_counts`` their observed/generated tally — both flow into
    the approval gate and audit.jsonl.
    """

    text: str
    filename: str
    target_path: Path
    pattern_ids: Tuple[str, ...] = ()
    epistemic_counts: Dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class InsightResult:
    """Result of a successful insight extraction."""

    skills: Tuple[SkillResult, ...]
    dropped_count: int
    skills_dir: Path


def _extract_skill(
    patterns: List[str], topic: str = "mixed"
) -> Optional[str]:
    """Extract one skill from patterns via LLM.

    Returns valid Markdown skill text, or None on failure.
    """
    # The prompt template variable is still ``{subcategory}`` for backward
    # compatibility with the .md file; here we pass a topic label which
    # is a neutral cluster identifier, not a predefined view name.
    # The session-insights input was retired by ADR-0052 — skill extraction
    # works from patterns only, not from the agent's session narratives.
    prompt = INSIGHT_EXTRACTION_PROMPT.format(
        subcategory=topic,
        patterns="\n".join(f"- {p}" for p in patterns),
    )

    # Axioms-only system (same as distill): skill generation must not be
    # conditioned on the existing skill corpus, or each new skill inherits
    # the vocabulary of the last (audit H6).
    result = generate(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        caller="insight.skill_extract",
    )
    if result is None:
        logger.warning("LLM failed to generate skill extraction.")
        return None

    text = result.strip()
    if extract_title(text) is None:
        logger.warning("Skill has no title, dropping.")
        logger.debug("Raw LLM output (first 300 chars): %.300s", result)
        return None

    return text


def _cluster_score(cluster: List[dict]) -> float:
    """Ordering key: cluster size × mean effective_importance.

    Favors frequently-recurring topics that also score as important.
    Size-only biases toward chatter; importance-only is unstable on
    small clusters with one extreme outlier.
    """
    if not cluster:
        return 0.0
    mean_imp = sum(effective_importance(p) for p in cluster) / len(cluster)
    return len(cluster) * mean_imp


def _build_cluster_batches(
    raw_patterns: List[dict],
    threshold: float = CLUSTER_THRESHOLD,
    min_size: int = MIN_PATTERNS_REQUIRED,
    max_size: int = BATCH_SIZE,
) -> List[Tuple[str, List[str], Tuple[str, ...]]]:
    """Cluster patterns globally; every cluster ≥ ``min_size`` becomes a batch.

    ``gated`` patterns (noise per ADR-0026) are skipped before
    clustering so noise centroids cannot pull meaningful clusters
    toward themselves. Self-reflection patterns are NOT excluded — the
    same observation can seed both a skill and an identity block; LLM
    extraction drops the cluster if no skill can be distilled.

    Patterns without an ``embedding`` field bypass clustering (handled
    inside ``cluster_patterns``).

    Clusters are ordered by ``_cluster_score`` (size × mean
    effective_importance) descending so the LLM sees the strongest
    candidates first — an early LLM failure then costs less.

    Returns:
        List of (topic, pattern_texts, pattern_ids) tuples. Topic names
        are neutral ``cluster-N`` identifiers; the LLM is expected to
        title each skill from the content itself. ``pattern_ids``
        (ADR-0050) attribute only the kept members — the demoted tail
        beyond ``max_size`` never reaches the LLM and is not attributed.
    """
    candidates = [p for p in raw_patterns if not p.get("gated")]
    if len(candidates) < min_size:
        return []

    clusters, _ = cluster_patterns(
        candidates,
        threshold=threshold,
        min_size=min_size,
        max_size=max_size,
    )
    if not clusters:
        return []

    clusters.sort(key=_cluster_score, reverse=True)

    batches: List[Tuple[str, List[str], Tuple[str, ...]]] = []
    for idx, cluster in enumerate(clusters, start=1):
        topic = f"cluster-{idx}"
        batches.append((
            topic,
            [p["pattern"] for p in cluster],
            tuple(pattern_id(p) for p in cluster),
        ))
    return batches


def _read_last_insight(skills_dir: Optional[Path]) -> Optional[str]:
    """Read the timestamp of the last insight run."""
    if skills_dir is None:
        return None
    marker = skills_dir / ".last_insight"
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return None


def write_last_insight(skills_dir: Path) -> None:
    """Record the current timestamp as the last insight run."""
    skills_dir.mkdir(parents=True, exist_ok=True)
    marker = skills_dir / ".last_insight"
    marker.write_text(now_iso() + "\n", encoding="utf-8")


def extract_insight(
    knowledge_store: Optional[KnowledgeStore] = None,
    skills_dir: Optional[Path] = None,
    full: bool = False,
) -> Union[str, InsightResult]:
    """Extract behavioral skills from accumulated knowledge.

    Single-pass per cluster: extract skill, validate, return.
    File writing is the caller's responsibility (ADR-0012 approval gate).
    Quality control is deferred to skill-stocktake.

    By default, only processes patterns added since the last insight run.
    Use full=True to process all patterns.

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        skills_dir: Directory for skill files (used for incremental tracking).
        full: If True, process all patterns instead of only new ones.

    Returns:
        InsightResult on success, or error message string.
    """
    if knowledge_store is None:
        return "No knowledge store provided."

    knowledge_store.load()

    # ADR-0021/0051: pull live-only patterns so bitemporally superseded
    # entries never enter batching.
    # ADR-0026: dropped category="uncategorized" gate; gated=True is the
    # only hard exclusion (handled by _build_cluster_batches).
    if full:
        raw_patterns = knowledge_store.get_live_patterns()
    else:
        last_run = _read_last_insight(skills_dir)
        if last_run:
            raw_patterns = knowledge_store.get_live_patterns_since(last_run)
            logger.info("Incremental mode: %d new patterns since %s", len(raw_patterns), last_run)
        else:
            raw_patterns = knowledge_store.get_live_patterns()
            logger.info("No previous insight run found, processing all %d patterns", len(raw_patterns))

    if len(raw_patterns) < MIN_PATTERNS_REQUIRED:
        return (
            f"Insufficient patterns ({len(raw_patterns)}/{MIN_PATTERNS_REQUIRED}). "
            f"Run more sessions and distill first."
        )

    batches = _build_cluster_batches(raw_patterns)

    if not batches:
        return (
            f"No clusters met the size floor ({MIN_PATTERNS_REQUIRED}). "
            f"Accumulate more diverse patterns or lower CLUSTER_THRESHOLD."
        )

    logger.info(
        "Processing %d patterns in %d cluster batches",
        len(raw_patterns), len(batches),
    )

    skill_results: List[SkillResult] = []
    dropped_count = 0

    # ADR-0050: id → pattern dict lookup for per-batch epistemic counts.
    patterns_by_id = {pattern_id(p): p for p in raw_patterns}
    if len(patterns_by_id) != len(raw_patterns):
        logger.debug(
            "pattern_id collision: %d patterns → %d unique ids "
            "(identical distilled+text rows; counts may undercount)",
            len(raw_patterns), len(patterns_by_id),
        )

    for batch_idx, (topic, batch, batch_pids) in enumerate(batches):
        logger.info(
            "Batch %d/%d [%s]: %d patterns",
            batch_idx + 1, len(batches), topic, len(batch),
        )

        skill_text = _extract_skill(batch, topic=topic)
        if skill_text is None:
            logger.warning(
                "Batch %d/%d [%s]: extraction failed",
                batch_idx + 1, len(batches), topic,
            )
            dropped_count += 1
            continue

        if not validate_identity_content(skill_text):
            logger.warning(
                "Batch %d/%d [%s]: forbidden pattern detected",
                batch_idx + 1, len(batches), topic,
            )
            dropped_count += 1
            continue

        resolved = resolve_artifact_path(
            skill_text,
            skills_dir,
            label=f"Batch {batch_idx + 1}/{len(batches)} [{topic}]",
        )
        if resolved is None:
            dropped_count += 1
            continue

        skill_results.append(SkillResult(
            text=skill_text,
            filename=resolved.filename,
            target_path=resolved.target_path,
            pattern_ids=batch_pids,
            epistemic_counts=epistemic_counts_for(
                [patterns_by_id[pid] for pid in batch_pids if pid in patterns_by_id]
            ),
        ))

    if not skill_results:
        return "Failed to extract skill from knowledge."

    return InsightResult(
        skills=tuple(skill_results),
        dropped_count=dropped_count,
        skills_dir=skills_dir or Path("."),
    )
