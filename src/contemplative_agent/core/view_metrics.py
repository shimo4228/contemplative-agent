"""Read-only pattern-composition instruments (view supply / diversity / grounding).

Observability ONLY: everything here returns distributions and compositions
for a human operator to read. Nothing in this module may be wired into a
gate, a ranking, a promotion decision, or any other behavior-changing path —
that separation is the point (mirrors AKC ADR-0015 Decision 2: visibility
without intervention; rejection write-back and metric-driven ranking were
explicitly rejected there and in ADR-0050/0051).

Three instruments:

- **View supply** — how many patterns clear each *consumed* view's threshold.
  Axes are restricted to views with a real downstream consumer
  (``self_reflection`` → distill-identity, ``constitutional`` →
  amend-constitution). The five orphaned seed files in ``config/views/`` are
  deliberately not measured: a distribution over an unconsumed seed measures
  seed staleness, not corpus structure, and its reading changes no action.
- **Diversity** — seed-independent homogeneity of a pattern set: pairwise
  cosine percentiles plus the cluster-structure summary ``insight`` would
  see. A rising pairwise mean with supply concentrating in
  ``self_reflection`` and grounding turning inward is the echo-chamber
  signature (register collapse), measured without any hand-written axis.
- **Grounding** — provenance composition (``source_type``) and the
  ADR-0050 epistemic tally. Read the epistemic line as a *provenance-kind*
  tally, never as external-grounding presence: after ADR-0060 ``observed``
  is structurally zero (review 2026-06-27 M2, ``knowledge_store``).

Interpretation caveat (review 2026-06-27 / AKC ADR-0016): an empty or thin
view supply is ambiguous — it can mean "no such patterns" or "the seed no
longer matches the corpus". The formatting deliberately says so; a biased
instrument is worse than no instrument.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional, Protocol, Sequence, Tuple

import numpy as np

from .clustering import cluster_patterns
from .embeddings import cosine
from .knowledge_store import epistemic_counts_for
from .thresholds import CLUSTER_THRESHOLD_INSIGHT, MAX_BATCH
from .views import View

logger = logging.getLogger(__name__)

# Views that have an actual querying consumer today (distill.py
# distill_identity / constitution.py amend_constitution). Instruments measure
# only these; see module docstring for why orphaned views are excluded.
CONSUMED_VIEWS: Tuple[str, ...] = ("self_reflection", "constitutional")

# Above this many embedded patterns, cluster stats are skipped: the
# agglomerative merge in clustering.py is ~O(N^3) worst case. Mirrors
# ``insight.FULL_RECLUSTER_WARN_N`` (kept literal here to avoid an import
# cycle — insight imports this module; a test cross-checks the two values).
CLUSTER_STATS_MAX_N = 500

# Above this many embedded patterns, pairwise stats run on a deterministic
# stride subsample instead of the full O(N^2) matrix (python-reviewer
# 2026-07-03 MEDIUM: the matrix is ~N^2*4 bytes and unbounded as the live
# pool grows). Stride keeps repeat runs comparable — no RNG involved.
PAIRWISE_STATS_MAX_N = 3000

_AMBIGUITY_NOTE = (
    "note: distributions only, not gates (observability). Empty/low view "
    "supply is ambiguous — missing patterns or a stale seed; this instrument "
    "cannot tell which."
)


class ViewLookup(Protocol):
    """The structural slice of ``ViewRegistry`` these instruments need."""

    def get(self, name: str) -> Optional[View]: ...

    def get_centroid(self, name: str) -> Optional[np.ndarray]: ...


@dataclass(frozen=True)
class ViewSupply:
    """Cosine-to-seed distribution of a pattern set for one consumed view."""

    view: str
    threshold: float
    total: int  # patterns with an embedding
    passing: int  # cosine >= threshold
    p50: float
    p90: float
    max: float


@dataclass(frozen=True)
class ClusterStats:
    """Cluster-structure summary as ``insight`` would see the set."""

    threshold: float
    clusters: int
    clustered: int
    singletons: int
    largest: int


@dataclass(frozen=True)
class DiversityStats:
    """Seed-independent homogeneity of a pattern set."""

    n: int  # patterns with an embedding
    skipped: int  # patterns without an embedding
    pairwise_mean: float
    pairwise_p50: float
    pairwise_p90: float
    cluster_stats: Optional[ClusterStats]  # None below 2 or above the O(N^3) cap


@dataclass(frozen=True)
class GroundingComposition:
    """Provenance composition (ADR-0050 read-time derivation)."""

    source_types: Tuple[Tuple[str, int], ...]  # count desc, then name
    epistemic: Tuple[Tuple[str, int], ...]  # observed / generated / unknown
    gated: int  # legacy noise flag (ADR-0026)


def _embedding_of(pattern: dict) -> Optional[np.ndarray]:
    """Pattern embedding as float32 vector, or None when absent/malformed.

    Malformed values (non-numeric, ragged nesting) return None instead of
    raising: one corrupt row must never abort the host command — the
    instruments are observability, and observability halting the pipeline
    is the exact failure the design contract forbids (python-reviewer
    2026-07-03 CRITICAL; same degrade-don't-raise idiom as
    ``embeddings.cosine``).
    """
    emb = pattern.get("embedding")
    if emb is None:
        return None
    try:
        arr = np.asarray(emb, dtype=np.float32)
    except (TypeError, ValueError):
        logger.warning(
            "instrument: malformed embedding on pattern %.60r — row skipped",
            pattern.get("pattern", ""),
        )
        return None
    if arr.ndim != 1 or arr.size == 0:
        return None
    return arr


def compute_view_supply(
    patterns: Sequence[dict],
    registry: ViewLookup,
    views: Sequence[str] = CONSUMED_VIEWS,
) -> Tuple[ViewSupply, ...]:
    """Cosine-to-seed supply stats per consumed view.

    Patterns without embeddings are skipped. Views that cannot be resolved
    (missing definition or failed seed embedding) are omitted with a WARNING
    rather than silently reported as zero — an absent axis and an empty axis
    must stay distinguishable.
    """
    embedded = [e for e in (_embedding_of(p) for p in patterns) if e is not None]
    supplies: List[ViewSupply] = []
    for name in views:
        view = registry.get(name)
        centroid = registry.get_centroid(name) if view is not None else None
        if view is None or centroid is None:
            logger.warning(
                "view supply: view %r unavailable (missing definition or "
                "seed embedding failed) — omitted from instruments", name,
            )
            continue
        sims = [cosine(centroid, vec) for vec in embedded]
        if sims:
            arr = np.asarray(sims, dtype=np.float32)
            p50 = float(np.percentile(arr, 50))
            p90 = float(np.percentile(arr, 90))
            top = float(arr.max())
        else:
            p50 = p90 = top = 0.0
        supplies.append(
            ViewSupply(
                view=name,
                threshold=view.threshold,
                total=len(sims),
                passing=sum(1 for s in sims if s >= view.threshold),
                p50=p50,
                p90=p90,
                max=top,
            )
        )
    return tuple(supplies)


def compute_diversity(
    patterns: Sequence[dict],
    *,
    cluster_threshold: float = CLUSTER_THRESHOLD_INSIGHT,
    min_size: int = 3,
    max_size: int = MAX_BATCH,
    cluster_cap: int = CLUSTER_STATS_MAX_N,
) -> DiversityStats:
    """Pairwise-cosine homogeneity plus the cluster structure insight sees.

    Pairwise stats cover every embedded pattern (whole-set homogeneity,
    ``gated`` included). The cluster line mirrors ``insight`` exactly —
    same threshold / min / max AND the same ``gated``-row exclusion
    (``_build_cluster_batches`` filters gated before clustering), so it
    reads as "what insight's clustering would do with this set".

    Rows whose embedding dimension differs from the dominant one (a legacy
    vector from another embedding model) are dropped and counted in
    ``skipped`` — the instrument degrades instead of raising on a ragged
    array (codex review 2026-07-03 P2; ``embeddings.cosine`` treats such
    vectors as dissimilar for the same reason).
    """
    pairs = [
        (vec, p)
        for vec, p in ((_embedding_of(p), p) for p in patterns)
        if vec is not None
    ]
    skipped = len(patterns) - len(pairs)
    if pairs:
        dims = Counter(vec.shape[0] for vec, _ in pairs)
        dominant_dim = dims.most_common(1)[0][0]
        if len(dims) > 1:
            dropped = sum(c for d, c in dims.items() if d != dominant_dim)
            skipped += dropped
            logger.warning(
                "diversity: %d pattern(s) dropped — embedding dim differs "
                "from dominant %d (dims=%s); likely legacy vectors from "
                "another embedding model",
                dropped, dominant_dim, dict(dims),
            )
            pairs = [(vec, p) for vec, p in pairs if vec.shape[0] == dominant_dim]
    vectors = [vec for vec, _ in pairs]
    embedded = [p for _, p in pairs]
    n = len(vectors)
    if n < 2:
        return DiversityStats(
            n=n, skipped=skipped,
            pairwise_mean=0.0, pairwise_p50=0.0, pairwise_p90=0.0,
            cluster_stats=None,
        )

    pairwise_vectors = vectors
    if n > PAIRWISE_STATS_MAX_N:
        stride = -(-n // PAIRWISE_STATS_MAX_N)  # ceil division
        pairwise_vectors = vectors[::stride]
        logger.info(
            "diversity: pairwise stats on a deterministic stride sample "
            "%d/%d (memory guard)", len(pairwise_vectors), n,
        )
    matrix = np.asarray(pairwise_vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = matrix / norms
    similarity = unit @ unit.T
    upper = similarity[np.triu_indices(len(pairwise_vectors), k=1)]

    cluster_stats: Optional[ClusterStats] = None
    if n <= cluster_cap:
        # Mirror insight._build_cluster_batches: gated rows never reach its
        # clustering, so they must not inflate the instrument either
        # (codex review 2026-07-03 P2).
        cluster_input = [p for p in embedded if not p.get("gated")]
        clusters, singletons = cluster_patterns(
            cluster_input,
            threshold=cluster_threshold,
            min_size=min_size,
            max_size=max_size,
        )
        cluster_stats = ClusterStats(
            threshold=cluster_threshold,
            clusters=len(clusters),
            clustered=sum(len(c) for c in clusters),
            singletons=len(singletons),
            largest=max((len(c) for c in clusters), default=0),
        )
    else:
        logger.info(
            "diversity: cluster stats skipped (n=%d > %d, O(N^3) merge guard)",
            n, cluster_cap,
        )

    return DiversityStats(
        n=n,
        skipped=skipped,
        pairwise_mean=float(upper.mean()),
        pairwise_p50=float(np.percentile(upper, 50)),
        pairwise_p90=float(np.percentile(upper, 90)),
        cluster_stats=cluster_stats,
    )


def compute_grounding(patterns: Sequence[dict]) -> GroundingComposition:
    """Provenance composition: source_type tally, epistemic tally, gated count."""
    counter: Counter = Counter()
    for p in patterns:
        provenance = p.get("provenance") or {}
        counter[provenance.get("source_type") or "unknown"] += 1
    epistemic = epistemic_counts_for(list(patterns))
    return GroundingComposition(
        source_types=tuple(sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))),
        epistemic=tuple((k, epistemic[k]) for k in ("observed", "generated", "unknown")),
        gated=sum(1 for p in patterns if p.get("gated")),
    )


def nearest_view(
    pattern: dict,
    registry: ViewLookup,
    views: Sequence[str] = CONSUMED_VIEWS,
) -> Optional[Tuple[str, float]]:
    """Best (view, cosine) among consumed views, or None when unresolvable.

    Visibility helper for dropped-singleton logging (review 2026-06-27 M3):
    shows where a discarded pattern sits relative to the two real consumers.
    Never used to rescue or suppress anything.
    """
    vec = _embedding_of(pattern)
    if vec is None:
        return None
    best: Optional[Tuple[str, float]] = None
    for name in views:
        centroid = registry.get_centroid(name)
        if centroid is None:
            continue
        sim = cosine(centroid, vec)
        if best is None or sim > best[1]:
            best = (name, sim)
    return best


def format_view_supply(supplies: Sequence[ViewSupply]) -> List[str]:
    return [
        (
            f"view supply — {s.view}: {s.passing}/{s.total} pass "
            f"@{s.threshold:.2f} (cosine p50={s.p50:.2f} p90={s.p90:.2f} "
            f"max={s.max:.2f})"
        )
        for s in supplies
    ]


def format_diversity(stats: DiversityStats) -> List[str]:
    lines = [
        (
            f"diversity — n={stats.n} (no embedding: {stats.skipped}) "
            f"pairwise cosine mean={stats.pairwise_mean:.2f} "
            f"p50={stats.pairwise_p50:.2f} p90={stats.pairwise_p90:.2f}"
        )
    ]
    cs = stats.cluster_stats
    if cs is not None:
        lines.append(
            f"diversity — clusters @{cs.threshold:.2f}: {cs.clusters} "
            f"clusters covering {cs.clustered}, singletons {cs.singletons}, "
            f"largest {cs.largest}"
        )
    elif stats.n >= 2:
        lines.append(
            f"diversity — cluster stats skipped (n={stats.n} above cap, "
            f"O(N^3) merge guard)"
        )
    return lines


def format_grounding(grounding: GroundingComposition) -> List[str]:
    source_types = (
        ", ".join(f"{name}={count}" for name, count in grounding.source_types)
        or "none"
    )
    epistemic = ", ".join(f"{name}={count}" for name, count in grounding.epistemic)
    return [
        f"grounding — source_type: {source_types}",
        (
            "grounding — epistemic (provenance kind, NOT external-grounding "
            f"presence; ADR-0060): {epistemic}"
        ),
        f"grounding — gated (legacy noise flag): {grounding.gated}",
    ]


def instrument_lines(
    patterns: Sequence[dict],
    registry: Optional[ViewLookup] = None,
    *,
    views: Sequence[str] = CONSUMED_VIEWS,
    cluster_cap: int = CLUSTER_STATS_MAX_N,
) -> List[str]:
    """All instrument lines for a pattern set (view supply needs a registry)."""
    lines: List[str] = []
    if registry is not None:
        lines.extend(format_view_supply(compute_view_supply(patterns, registry, views)))
    lines.extend(format_diversity(compute_diversity(patterns, cluster_cap=cluster_cap)))
    lines.extend(format_grounding(compute_grounding(patterns)))
    return lines


def format_pattern_report(
    patterns: Sequence[dict],
    registry: ViewLookup,
    *,
    views: Sequence[str] = CONSUMED_VIEWS,
    cluster_cap: int = CLUSTER_STATS_MAX_N,
) -> str:
    """Multi-line pattern-composition report for ``report --patterns``."""
    lines = [f"Pattern Composition ({len(patterns)} patterns)"]
    lines.extend(
        f"  {line}"
        for line in instrument_lines(
            patterns, registry, views=views, cluster_cap=cluster_cap
        )
    )
    lines.append(f"  {_AMBIGUITY_NOTE}")
    return "\n".join(lines)
