"""Insight extraction: synthesize learned patterns into behavioral skills.

Global embedding cluster per run. Each cluster → one LLM skill
extraction call, and that call is the only one per cluster: ADR-0097
retired the separate post-extraction worth judge, leaving the in-band
``NOTHING-PROMOTABLE`` abstain (ADR-0096 Decision 1). Quality control after
adoption is the Saturday gate's, not a batch consolidator's (ADR-0097).

The view concept (ADR-0019) does not shape extraction: insight works
directly on ``gated != True`` live patterns so that any clustering
structure comes from the embeddings themselves, not from predefined
seed texts. The only view usage is read-only visibility — dropped
singletons log their nearest *consumed* view (``view_metrics``) so the
operator can see what skill extraction discards; nothing is gated,
ranked, or rescued by it. (The former claims that views drive distill's
noise gate and stocktake's merge went stale: ADR-0060 removed the noise
gate and ADR-0097 retired stocktake's grouping and merge stages.)
"""

from __future__ import annotations

import logging
import os
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

from . import insight_novelty, insight_surprise, llm
from ._io import read_run_marker, strip_to_printable, write_run_marker
from .artifact_extraction import canonicalize_frontmatter_name, resolve_artifact_path
from .clustering import cluster_patterns
from .insight_novelty import _Batch
from .insight_surprise import SurpriseReading
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

# ---------------------------------------------------------------------------
# ADR-0096: promotion-worth abstain reason codes
# ---------------------------------------------------------------------------

# Per-cluster abstain reason codes (ADR-0075: a cluster that produces no
# candidate says why, no silent drop). The first four are faults; see
# ABSTAIN_NOTHING_PROMOTABLE below for the one that is a judgment. Literal-typed
# so a typo at a future call site fails type check instead of silently minting a
# new reason.
InsightAbstainReason = Literal[
    "llm_none",
    "no_title",
    "forbidden_content",
    "path_unresolved",
    "nothing_promotable",
]
ABSTAIN_LLM_NONE: InsightAbstainReason = "llm_none"  # generate_full() returned None
ABSTAIN_NO_TITLE: InsightAbstainReason = "no_title"  # output has no extractable title
ABSTAIN_FORBIDDEN_CONTENT: InsightAbstainReason = "forbidden_content"  # identity-guard hit
ABSTAIN_PATH_UNRESOLVED: InsightAbstainReason = "path_unresolved"  # no writable target path

# The one reason that is a VERDICT, not a failure: the extraction call read the
# cluster and declined in-band (ADR-0096 Decision 1). ADR-0053 canonicalizes
# promotion worth as an insight-time judgment, but until ADR-0096 the
# implementation had no channel for "no" — the prompt opened with a production
# order and the only drops were an LLM failure and a missing title, so the
# question answered was "could a titled document be produced?". ADR-0096's
# separate post-extraction worth JUDGE was retired by ADR-0097 after its own
# pre-registered refutation fired (46/46 promote on the first production run);
# the in-band abstain channel is what remains. Tallied apart from the four
# fault reasons above: a routine week and a backend outage must never read the
# same.
ABSTAIN_NOTHING_PROMOTABLE: InsightAbstainReason = "nothing_promotable"

# Reasons that mean something BROKE (as opposed to a judged abstain). Also the
# control-flow split for an empty run: a fault-bearing run keeps returning an
# error string so the incremental window is NOT consumed, while an all-verdict
# run returns an empty result — the window was genuinely considered.
FAULT_ABSTAIN_REASONS: frozenset[InsightAbstainReason] = frozenset(
    {
        ABSTAIN_LLM_NONE,
        ABSTAIN_NO_TITLE,
        ABSTAIN_FORBIDDEN_CONTENT,
        ABSTAIN_PATH_UNRESOLVED,
    }
)

# The single line the extraction call writes instead of a skill. Matched on the
# first non-empty line so a model that decorates it (bold, fence, trailing
# period) is still read as declining rather than as a titleless fault.
_ABSTAIN_TOKEN = "NOTHING-PROMOTABLE"

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
    # ADR-0096, restored 2026-08-29 (RFC-0016): the read-only surprise reading
    # for this candidate's cluster — material for the reviewer, never a filter.
    # None when the cluster had no usable embedding (a missing reading is
    # honest; an invented one is not).
    surprise: SurpriseReading | None = None


@dataclass(frozen=True)
class InsightResult:
    """Result of a successful insight extraction.

    ADR-0074: ``skipped_known`` counts clusters the novelty gate judged
    already covered by an existing or previously staged skill. ``skills``
    may legitimately be empty when every cluster was known — the caller
    still advances the run marker in that case (the window WAS considered).
    """

    skills: tuple[SkillResult, ...]
    skipped_known: int = 0
    # ADR-0096: per-reason abstain tally — the single source for how many
    # clusters yielded nothing and why. ``fault_count`` is derived from it
    # rather than stored, so a new reason code cannot be counted in one place
    # and missed in another.
    abstained: Counter[InsightAbstainReason] = field(default_factory=Counter)

    @property
    def fault_count(self) -> int:
        """Of those, the ones that broke rather than declined.

        Read through this rather than subtracting the verdict from the total:
        the subtraction silently assumes ``nothing_promotable`` is the only
        non-fault reason, and it is the presentation layer that would report a
        future second verdict as a fault.
        """
        return sum(c for reason, c in self.abstained.items() if reason in FAULT_ABSTAIN_REASONS)


def _is_abstain_verdict(text: str) -> bool:
    """True when the extraction call declined instead of writing a skill.

    Any line that is the token once markdown decoration is stripped counts, not
    only the first: the prompt's abstain instruction lives under a heading, and
    a model that follows the template echoes that heading above its answer
    (code review 2026-08-17). Read as a titleless fault, such a decline would
    preserve the incremental window and, if every cluster declined, turn a
    clean run into an error — the exact fault/verdict confusion the reason
    codes exist to prevent.

    The caller checks for a title FIRST, so a produced skill that happens to
    mention the token stays a skill: misreading a real candidate as a decline
    loses review material, and the title is the stronger signal.
    """
    for line in text.splitlines():
        stripped = line.strip().strip("`*_#> ").strip()
        if stripped.upper().rstrip(".:") == _ABSTAIN_TOKEN:
            return True
    return False


def _extract_skill(
    patterns: list[str], topic: str = "mixed"
) -> tuple[str, str | None] | InsightAbstainReason:
    """Extract one skill from patterns via LLM.

    Returns ``(skill_text, thinking)`` — the reasoning trace rides along
    because insight runs think-ON (ADR-0069) — or an ``ABSTAIN_*`` reason
    code. ADR-0096: the reason code replaces a bare ``None`` so the caller can
    tell a judged decline from a broken call, which is also the difference
    between consuming the incremental window and preserving it.
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
        logger.warning("Insight extraction abstained: reason=%s topic=%s", ABSTAIN_LLM_NONE, topic)
        return ABSTAIN_LLM_NONE

    text = out.text.strip()
    # Title first: a produced skill that merely mentions the token is a skill.
    # Only a titleless output can be a decline, and then the token decides
    # whether it is a verdict or a fault.
    if extract_title(text) is not None:
        return text, out.thinking
    if _is_abstain_verdict(text):
        logger.info(
            "Insight extraction abstained: reason=%s stage=extraction topic=%s",
            ABSTAIN_NOTHING_PROMOTABLE,
            topic,
        )
        return ABSTAIN_NOTHING_PROMOTABLE
    logger.warning("Insight extraction abstained: reason=%s topic=%s", ABSTAIN_NO_TITLE, topic)
    logger.debug("Raw LLM output (first 300 chars): %s", strip_to_printable(out.text, 300))
    return ABSTAIN_NO_TITLE


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
        return InsightResult(skills=(), skipped_known=skipped_known)

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

    # ADR-0096 (b), restored by RFC-0016: read each surviving cluster's
    # distance from the recent distillation window BEFORE extraction, so the
    # listing covers every candidate the reviewer could have seen. Code only,
    # no LLM call, and nothing here reorders or drops a batch: `batches` is
    # untouched.
    surprise_readings = _read_surprise(
        batches,
        patterns_by_id,
        raw_patterns if full else knowledge_store.get_live_patterns(),
    )
    insight_surprise.log_surprise(surprise_readings)

    skill_results: list[SkillResult] = []
    abstained: Counter[InsightAbstainReason] = Counter()

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
        if isinstance(result, str):
            abstained[result] += 1
        else:
            # The reading is attached here rather than threaded through
            # extraction: it is a read-only instrument, and the function that
            # generates and validates a skill has no business holding it.
            skill_results.append(replace(result, surprise=surprise_readings.get(topic)))

    result = InsightResult(
        skills=tuple(skill_results),
        skipped_known=skipped_known,
        abstained=abstained,
    )
    faults = result.fault_count
    if faults:
        logger.warning(
            "Insight extraction summary: %d/%d cluster(s) abstained on a fault (%s); "
            "their clusters yield no candidate this run",
            faults,
            len(batches),
            " ".join(f"{reason}={abstained[reason]}" for reason in sorted(FAULT_ABSTAIN_REASONS)),
        )
    # Always emitted, faults or not: this is the yield reading. Before
    # ADR-0096 a cluster that produced no candidate was only ever a failure,
    # so there was no line in which a judged decline could appear — which is
    # why a 0% decline rate stayed invisible while being the whole defect.
    logger.info(
        "Insight extraction yield: %d/%d cluster(s) yielded skills (nothing_promotable=%d)",
        len(skill_results),
        len(batches),
        abstained[ABSTAIN_NOTHING_PROMOTABLE],
    )

    if not skill_results and faults:
        # Something broke. Keep the historical error string so the caller does
        # NOT advance the run marker — a backend outage must not consume the
        # incremental window.
        return "Failed to extract skill from knowledge."

    # No skills and no faults is a verdict, not a failure: every cluster was
    # read and judged unworthy. The window WAS considered, so this travels the
    # same channel as the novelty gate's all-covered result and the caller
    # advances the marker.
    return result


def _read_surprise(
    batches: Sequence[_Batch],
    patterns_by_id: dict[str, dict],
    reference_patterns: list[dict],
) -> dict[str, SurpriseReading]:
    """Surprise readings for the surviving clusters (ADR-0096, read-only).

    The cluster members are looked up in this run's window (``patterns_by_id``,
    already built by the caller), but the reference window is drawn from the
    whole live store: "far from what was distilled lately" is only meaningful
    against the store's recent history, and an incremental run's own window is
    mostly the candidates themselves.

    Degrades to an empty mapping on any problem — an instrument must never
    crash its host command (``read-only-instruments`` invariant 3).
    """
    try:
        members = {
            topic: [
                patterns_by_id[pid]["embedding"]
                for pid in pids
                if pid in patterns_by_id and patterns_by_id[pid].get("embedding")
            ]
            for topic, _patterns, pids in batches
        }
        # Mask THIS RUN's whole window, not just the cluster's kept members.
        # ``cluster_patterns`` demotes everything past ``max_size`` into
        # singletons, and those rows stay live: they are cosine >= 0.70
        # neighbours of the very centroid being measured and, being the newest
        # rows, they land in the reference window — which would make the
        # largest clusters read as the least surprising for a reason that has
        # nothing to do with surprise. It also restores the calibration's own
        # definition, where the reference was strictly what was distilled
        # BEFORE the run.
        window_ids = set(patterns_by_id)
        return insight_surprise.compute_surprise(
            members,
            reference_patterns,
            exclude={topic: window_ids for topic, _patterns, _pids in batches},
        )
    except Exception as exc:  # instrumentation must never break insight
        logger.warning("insight surprise reading failed: %s", exc)
        return {}


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
) -> SkillResult | InsightAbstainReason:
    """Extract + validate one cluster batch; an ``ABSTAIN_*`` reason when not.

    ADR-0096: every non-yielding path names itself, so the caller can tally
    faults apart from the judged ``nothing_promotable`` verdict (the
    extraction call's in-band decline — the only verdict path left after
    ADR-0097 retired the post-extraction worth judge).
    """
    logger.info(
        "Batch %d/%d [%s]: %d patterns",
        batch_idx + 1,
        n_batches,
        topic,
        len(batch),
    )

    extracted = _extract_skill(batch, topic=topic)
    if isinstance(extracted, str):
        return extracted
    skill_text, thinking = extracted

    if not llm.validate_identity_content(skill_text):
        logger.warning(
            "Batch %d/%d [%s]: abstained reason=%s (forbidden pattern detected)",
            batch_idx + 1,
            n_batches,
            topic,
            ABSTAIN_FORBIDDEN_CONTENT,
        )
        return ABSTAIN_FORBIDDEN_CONTENT

    resolved = resolve_artifact_path(
        skill_text,
        skills_dir,
        label=f"Batch {batch_idx + 1}/{n_batches} [{topic}]",
    )
    if resolved is None:
        return ABSTAIN_PATH_UNRESOLVED

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
