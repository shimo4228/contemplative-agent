"""Insight extraction: synthesize learned patterns into behavioral skills.

Global embedding cluster per run. Each cluster → one LLM skill
extraction call. Cross-cluster synthesis and quality control are
deferred to skill-stocktake (external).

The view concept (ADR-0019) does not shape extraction: insight works
directly on ``gated != True`` live patterns so that any clustering
structure comes from the embeddings themselves, not from predefined
seed texts. The only view usage is read-only visibility — dropped
singletons log their nearest *consumed* view (``view_metrics``) so the
operator can see what skill extraction discards; nothing is gated,
ranked, or rescued by it. (The former claims that views drive distill's
noise gate and stocktake's merge went stale: ADR-0060 removed the noise
gate and ADR-0046 moved stocktake grouping to a single LLM call.)
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import insight_novelty, llm
from ._io import read_run_marker, strip_to_printable, write_run_marker
from .artifact_extraction import canonicalize_frontmatter_name, resolve_artifact_path
from .clustering import cluster_patterns
from .insight_novelty import _Batch
from .knowledge_store import (
    effective_importance,
    epistemic_counts_for,
    pattern_id,
)
from .memory import KnowledgeStore
from .prompts import INSIGHT_EXTRACTION_PROMPT
from .text_utils import extract_title
from .thresholds import CLUSTER_THRESHOLD_INSIGHT as CLUSTER_THRESHOLD, MAX_BATCH as BATCH_SIZE
from .view_metrics import ViewLookup, nearest_view

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3

# Above this live-pattern count, ``insight --full`` emits an advisory warning.
# Clustering itself is cheap since the ADR-0074 Lance-Williams merge; the cost
# that still scales with the pool is the human review batch (every eligible
# cluster becomes a staged candidate). NOT a quality cap — nothing is dropped.
FULL_RECLUSTER_WARN_N = 500


@dataclass(frozen=True)
class SkillResult:
    """A single generated skill ready for approval.

    ADR-0050: ``pattern_ids`` carries the content-hash ids of the cluster
    members actually passed to the LLM (kept members only), and
    ``epistemic_counts`` their generated/unknown tally (ADR-0082) — both
    flow into the approval gate and audit.jsonl.
    """

    text: str
    filename: str
    target_path: Path
    pattern_ids: tuple[str, ...] = ()
    epistemic_counts: dict[str, int] = field(default_factory=dict)
    # ADR-0069: the reasoning trace for this skill (insight runs think-ON).
    # Per-skill (one LLM call per cluster), None when think was off / no trace.
    thinking: str | None = None


@dataclass(frozen=True)
class InsightResult:
    """Result of a successful insight extraction.

    ADR-0074: ``skipped_known`` counts clusters the novelty gate judged
    already covered by an existing or previously staged skill. ``skills``
    may legitimately be empty when every cluster was known — the caller
    still advances the run marker in that case (the window WAS considered).
    """

    skills: tuple[SkillResult, ...]
    dropped_count: int
    skipped_known: int = 0


def _extract_skill(patterns: list[str], topic: str = "mixed") -> tuple[str, str | None] | None:
    """Extract one skill from patterns via LLM.

    Returns ``(skill_text, thinking)`` — the reasoning trace rides along
    because insight runs think-ON (ADR-0069). None on failure.
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
    out = llm.generate_full(
        prompt,
        system=llm.get_distill_system_prompt(),
        num_predict=3000,
        caller="insight.skill_extract",
        think=True,
        drop_truncated=True,
    )
    if out is None or out.text is None:
        logger.warning("LLM failed to generate skill extraction.")
        return None

    text = out.text.strip()
    if extract_title(text) is None:
        logger.warning("Skill has no title, dropping.")
        logger.debug("Raw LLM output (first 300 chars): %s", strip_to_printable(out.text, 300))
        return None

    return text, out.thinking


def _cluster_score(cluster: list[dict]) -> float:
    """Ordering key: cluster size × mean effective_importance.

    Favors frequently-recurring topics that are also recent. ADR-0056:
    effective_importance is pure time decay (the LLM rating was retired),
    so this weights large, freshly-reinforced clusters first. Size-only
    biases toward stale chatter; decay alone ignores how often a topic
    recurred.
    """
    if not cluster:
        return 0.0
    mean_imp = sum(effective_importance(p) for p in cluster) / len(cluster)
    return len(cluster) * mean_imp


def _log_dropped_singletons(
    singletons: list[dict],
    view_registry: ViewLookup | None = None,
) -> None:
    """Visibility-only instrument for dropped singleton patterns (review
    2026-06-27 M3).

    ``cluster_patterns`` demotes sub-``min_size`` groups and the >``max_size``
    cluster tails into ``singletons``, which never reach the LLM and so can
    never become skills. Rarity/heterogeneity is the signal, so pooling them
    is the wrong fix; instead this logs how many were dropped and their
    ``effective_importance`` distribution (p50/p90/p99/max) plus the top rows,
    so a rare-singleton lane and floor can later be decided from the real live
    distribution rather than a blind constant. When ``view_registry`` is
    given, each top row also shows its nearest consumed view and cosine
    (``view_metrics.nearest_view``) — where the discarded pattern sits
    relative to the two real view consumers. No lane/threshold is applied
    here — this only logs.
    """
    if not singletons:
        return
    scores = sorted((effective_importance(p) for p in singletons), reverse=True)
    n = len(scores)

    def _pct(q: float) -> float:
        # Linear-position percentile on the descending list: q is the fraction
        # of patterns scoring at or below the returned value, so a high q maps
        # near the top (max). Diagnostic-only, so the exact interpolation rule
        # is immaterial.
        idx = min(n - 1, max(0, int(round((1.0 - q) * (n - 1)))))
        return scores[idx]

    logger.info(
        "insight: %d singleton pattern(s) dropped (never skilled); "
        "effective_importance p50=%.3f p90=%.3f p99=%.3f max=%.3f",
        n,
        _pct(0.50),
        _pct(0.90),
        _pct(0.99),
        scores[0],
    )
    for p in sorted(singletons, key=effective_importance, reverse=True)[:10]:
        nearest = nearest_view(p, view_registry) if view_registry is not None else None
        view_note = f" view≈{nearest[0]}:{nearest[1]:.2f}" if nearest else ""
        logger.info(
            "  dropped singleton score=%.3f%s: %s",
            effective_importance(p),
            view_note,
            (p.get("pattern", "") or "")[:80],
        )


def _build_cluster_batches(
    raw_patterns: list[dict],
    threshold: float = CLUSTER_THRESHOLD,
    min_size: int = MIN_PATTERNS_REQUIRED,
    max_size: int = BATCH_SIZE,
    view_registry: ViewLookup | None = None,
) -> list[tuple[str, list[str], tuple[str, ...]]]:
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

    clusters, singletons = cluster_patterns(
        candidates,
        threshold=threshold,
        min_size=min_size,
        max_size=max_size,
    )
    _log_dropped_singletons(singletons, view_registry)
    if not clusters:
        return []

    clusters.sort(key=_cluster_score, reverse=True)

    batches: list[tuple[str, list[str], tuple[str, ...]]] = []
    for idx, cluster in enumerate(clusters, start=1):
        topic = f"cluster-{idx}"
        batches.append(
            (
                topic,
                [p["pattern"] for p in cluster],
                tuple(pattern_id(p) for p in cluster),
            )
        )
    return batches


def _read_last_insight(skills_dir: Path | None) -> str | None:
    """Read the timestamp of the last insight run."""
    return read_run_marker(skills_dir, ".last_insight")


def write_last_insight(skills_dir: Path) -> None:
    """Record the current timestamp as the last insight run."""
    write_run_marker(skills_dir, ".last_insight")


# ---------------------------------------------------------------------------
# ADR-0074: LLM novelty gate
# ---------------------------------------------------------------------------


# Fail-open extraction cap (grill 2026-07-18): bounds the blast radius of an
# UNJUDGED fail-open batch — never applied to judged-novel clusters, so it is
# a review-budget circuit breaker, not a quality filter. Deferred clusters
# are not extracted, not staged and not ledger-written ("considered" status
# is never granted unseen), so a real theme can recur in a later window.
_DEFAULT_FAILOPEN_EXTRACTION_CAP = 20
_FAILOPEN_CAP_ENV = "MOLTBOOK_INSIGHT_FAILOPEN_CAP"


def _failopen_extraction_cap() -> int:
    """Resolve the fail-open extraction cap (env-overridable config)."""
    raw = os.environ.get(_FAILOPEN_CAP_ENV)
    if raw is None:
        return _DEFAULT_FAILOPEN_EXTRACTION_CAP
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        logger.warning(
            "invalid %s=%r — using default %d",
            _FAILOPEN_CAP_ENV,
            raw,
            _DEFAULT_FAILOPEN_EXTRACTION_CAP,
        )
        return _DEFAULT_FAILOPEN_EXTRACTION_CAP
    return value


def _append_deferral_audit(
    audit_path: Path | None,
    *,
    cap: int,
    deferred: Sequence[_Batch],
) -> None:
    """Best-effort record of review-budget deferrals — never a silent drop."""
    if audit_path is None:
        return
    try:
        from ._io import append_jsonl_restricted, now_iso

        record = {
            "ts": now_iso("seconds"),
            "reason": "review_budget_deferred",
            "cap": cap,
            "deferred": [
                {"topic": topic, "size": len(patterns), "pattern_ids": list(pids)}
                for topic, patterns, pids in deferred
            ],
        }
        append_jsonl_restricted(audit_path, record)
    except Exception as exc:  # instrumentation must never break insight
        logger.warning("insight deferral audit record failed: %s", exc)


def _apply_failopen_extraction_cap(
    batches: list[_Batch],
    fail_open_topics: frozenset[str],
    patterns_by_id: dict[str, dict],
    cap: int,
    audit_path: Path | None = None,
) -> list[_Batch]:
    """Bound the blast radius of a fail-open novelty verdict (grill 2026-07-18).

    Applies ONLY to clusters that reached extraction unjudged (through a
    fail-open chunk); judged-novel clusters always pass, so normal weeks are
    uncapped and this never acts as a quality filter. Deferred clusters are
    dropped BEFORE extraction — never staged, never ledger-written — so a
    real theme recurs in a later window and gets judged then; a transient
    one dies with its week. Priority is deterministic and code-owned:
    member count desc, then time-decay importance sum desc, then topic name.
    """
    fail_open_batches = [b for b in batches if b[0] in fail_open_topics]
    if len(fail_open_batches) <= cap:
        return batches

    def _priority(batch: _Batch) -> tuple[int, float, str]:
        topic, patterns, pids = batch
        importance = sum(
            effective_importance(patterns_by_id[pid]) for pid in pids if pid in patterns_by_id
        )
        return (-len(patterns), -importance, topic)

    ranked = sorted(fail_open_batches, key=_priority)
    deferred = ranked[cap:]
    deferred_topics = {b[0] for b in deferred}
    kept = [b for b in batches if b[0] not in deferred_topics]
    logger.warning(
        "novelty gate fail-open: deferring %d/%d unjudged cluster(s) beyond "
        "cap %d (reason=review_budget_deferred). Deferred clusters stay "
        "unstaged and un-ledgered, so recurring themes can resurface in a "
        "later window.",
        len(deferred),
        len(fail_open_batches),
        cap,
    )
    _append_deferral_audit(audit_path, cap=cap, deferred=deferred)
    return kept


def extract_insight(
    knowledge_store: KnowledgeStore | None = None,
    skills_dir: Path | None = None,
    full: bool = False,
    instrument_views: ViewLookup | None = None,
    staged_ledger_path: Path | None = None,
    novelty_audit_path: Path | None = None,
) -> str | InsightResult:
    """Extract behavioral skills from accumulated knowledge.

    Single-pass per cluster: extract skill, validate, return.
    File writing is the caller's responsibility (ADR-0012 approval gate).
    Quality control is deferred to skill-stocktake.

    By default, only processes patterns added since the last insight run.
    Use full=True to process all patterns. ADR-0074: when the run marker
    is missing, the incremental path refuses instead of silently
    reclustering the whole live corpus.

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        skills_dir: Directory for skill files (used for incremental tracking
            and the novelty gate's adopted-skill inventory).
        full: If True, process all patterns instead of only new ones.
        instrument_views: Optional view lookup for the dropped-singleton
            visibility log (nearest consumed view); never gates anything.
        staged_ledger_path: Previously staged candidates (ADR-0074); feeds
            the novelty gate alongside adopted skills.
        novelty_audit_path: Optional replay log (insight-novelty.jsonl) for
            the novelty gate's judge run (ADR-0075); never gates anything.

    Returns:
        InsightResult on success (possibly with zero skills when every
        cluster was already covered), or error message string.
    """
    if knowledge_store is None:
        return "No knowledge store provided."

    knowledge_store.load()

    raw_patterns = _select_patterns(knowledge_store, skills_dir, full)
    if raw_patterns is None:
        return (
            "No previous insight run marker (.last_insight) found. Refusing to "
            "recluster the entire live corpus implicitly (ADR-0074). Run with "
            "--full to process all patterns deliberately, or create the marker "
            "to scope the incremental window."
        )

    if len(raw_patterns) < MIN_PATTERNS_REQUIRED:
        return (
            f"Insufficient patterns ({len(raw_patterns)}/{MIN_PATTERNS_REQUIRED}). "
            f"Run more sessions and distill first."
        )

    batches = _build_cluster_batches(raw_patterns, view_registry=instrument_views)

    if not batches:
        return (
            f"No clusters met the size floor ({MIN_PATTERNS_REQUIRED}). "
            f"Accumulate more diverse patterns or lower CLUSTER_THRESHOLD."
        )

    # ADR-0074 novelty gate: drop clusters whose theme already reached the
    # human gate (adopted skills + staged ledger). Runs BEFORE extraction so
    # known themes cost one grouping call per token-budgeted chunk, not one
    # generation each.
    skipped_known = 0
    fail_open_topics: frozenset[str] = frozenset()
    known_themes = insight_novelty._load_known_themes(skills_dir, staged_ledger_path)
    if known_themes:
        gate = insight_novelty._filter_novel_batches(
            batches, known_themes, audit_path=novelty_audit_path
        )
        batches = list(gate.novel)
        skipped_known = gate.skipped_known
        fail_open_topics = gate.fail_open_topics
    if not batches:
        logger.info(
            "novelty gate: all %d cluster(s) already covered — nothing to extract",
            skipped_known,
        )
        return InsightResult(skills=(), dropped_count=0, skipped_known=skipped_known)

    # ADR-0050: id → pattern dict lookup for per-batch epistemic counts
    # (also feeds the fail-open cap's deterministic priority ordering).
    patterns_by_id = {pattern_id(p): p for p in raw_patterns}
    if len(patterns_by_id) != len(raw_patterns):
        logger.debug(
            "pattern_id collision: %d patterns → %d unique ids "
            "(identical distilled+text rows; counts may undercount)",
            len(raw_patterns),
            len(patterns_by_id),
        )

    # Fail-open extraction cap (grill 2026-07-18): clusters that reached this
    # point UNJUDGED are bounded so a broken gate cannot flood the human
    # review batch again (2026-07-18: 117 unjudged clusters → 106 staged).
    if fail_open_topics:
        batches = _apply_failopen_extraction_cap(
            batches,
            fail_open_topics,
            patterns_by_id,
            cap=_failopen_extraction_cap(),
            audit_path=novelty_audit_path,
        )

    logger.info(
        "Processing %d patterns in %d cluster batches",
        len(raw_patterns),
        len(batches),
    )

    skill_results: list[SkillResult] = []
    dropped_count = 0

    for batch_idx, (topic, batch, batch_pids) in enumerate(batches):
        result = _extract_one_batch(
            topic,
            batch,
            batch_pids,
            batch_idx,
            len(batches),
            skills_dir,
            patterns_by_id,
        )
        if result is None:
            dropped_count += 1
        else:
            skill_results.append(result)

    if not skill_results:
        return "Failed to extract skill from knowledge."

    return InsightResult(
        skills=tuple(skill_results),
        dropped_count=dropped_count,
        skipped_known=skipped_known,
    )


def _select_patterns(
    knowledge_store: KnowledgeStore,
    skills_dir: Path | None,
    full: bool,
) -> list[dict] | None:
    """Pick the live patterns to process (full vs incremental).

    ADR-0021/0051: pull live-only patterns so bitemporally superseded
    entries never enter batching.
    ADR-0026: dropped category="uncategorized" gate; gated=True is the
    only hard exclusion (handled by _build_cluster_batches).
    ADR-0074: a missing run marker returns ``None`` (refuse) instead of
    silently falling back to the whole live corpus — the silent fallback
    bypassed the ``FULL_RECLUSTER_WARN_N`` advisory and turned a routine
    incremental run into an unbounded recluster.
    """
    if full:
        patterns = knowledge_store.get_live_patterns()
        if len(patterns) > FULL_RECLUSTER_WARN_N:
            logger.warning(
                "insight --full: reclustering %d live patterns (> %d); "
                "expect a large first review batch (ADR-0074)",
                len(patterns),
                FULL_RECLUSTER_WARN_N,
            )
        return patterns
    last_run = _read_last_insight(skills_dir)
    if last_run:
        raw_patterns = knowledge_store.get_live_patterns_since(last_run)
        logger.info("Incremental mode: %d new patterns since %s", len(raw_patterns), last_run)
        return raw_patterns
    logger.warning(
        "insight: no .last_insight marker — refusing the implicit full recluster (ADR-0074)"
    )
    return None


def _extract_one_batch(
    topic: str,
    batch: list[str],
    batch_pids: tuple[str, ...],
    batch_idx: int,
    n_batches: int,
    skills_dir: Path | None,
    patterns_by_id: dict[str, dict],
) -> SkillResult | None:
    """Extract + validate one cluster batch; None when dropped."""
    logger.info(
        "Batch %d/%d [%s]: %d patterns",
        batch_idx + 1,
        n_batches,
        topic,
        len(batch),
    )

    extracted = _extract_skill(batch, topic=topic)
    if extracted is None:
        logger.warning(
            "Batch %d/%d [%s]: extraction failed",
            batch_idx + 1,
            n_batches,
            topic,
        )
        return None
    skill_text, thinking = extracted

    if not llm.validate_identity_content(skill_text):
        logger.warning(
            "Batch %d/%d [%s]: forbidden pattern detected",
            batch_idx + 1,
            n_batches,
            topic,
        )
        return None

    resolved = resolve_artifact_path(
        skill_text,
        skills_dir,
        label=f"Batch {batch_idx + 1}/{n_batches} [{topic}]",
    )
    if resolved is None:
        return None

    # One canonical identity: the frontmatter name becomes the resolved slug,
    # so filename, selector key and ledger entry cannot diverge (the heading
    # stays as the human-readable title).
    skill_text = canonicalize_frontmatter_name(skill_text, resolved.slug)

    return SkillResult(
        text=skill_text,
        filename=resolved.filename,
        target_path=resolved.target_path,
        pattern_ids=batch_pids,
        epistemic_counts=epistemic_counts_for(
            [patterns_by_id[pid] for pid in batch_pids if pid in patterns_by_id]
        ),
        thinking=thinking,
    )
