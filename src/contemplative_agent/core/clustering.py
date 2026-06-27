"""Average-linkage agglomerative cosine clustering (ADR-0019 companion).

Used by ``insight`` and ``rules_distill`` to turn an embedded corpus
into sub-topic buckets without a predefined axis (view). The only
knobs are a cosine threshold (when to stop merging) and min/max
cluster size.

Design choices:
- Average-linkage rather than single-linkage to avoid chain-effect
  clusters that drag the LLM into over-abstract synthesis
- The O(N^2) cosine matrix is cheap; the real cost driver is the naive
  agglomerative merge in ``_merge_clusters``, which rescans every
  remaining cluster pair (recomputing submatrix means) on each of up to
  N-1 merges — worst case ~O(N^3). Fine for N up to a few hundred (well
  under current corpus sizes), but ``insight --full`` slows as the live
  pool grows (ADR-0060 distills per episode); ``insight`` warns past a
  measured threshold (``FULL_RECLUSTER_WARN_N``). A cached priority-queue
  agglomeration (~O(N^2 log N)) is the upgrade if --full ever becomes
  painful — deferred until measured (review 2026-06-27 M4)
- Pure numpy, no scipy/sklearn dependency

Patterns without an ``embedding`` field are returned as singletons.
Cluster members are sorted by ``effective_importance`` descending;
anything past ``max_size`` is demoted to singletons so the caller can
see it in the next pass.
"""

from __future__ import annotations

from typing import List, Tuple

import numpy as np

from .knowledge_store import effective_importance


def _cosine_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Return NxN cosine similarity between row vectors."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = embeddings / norms
    return unit @ unit.T


def _merge_clusters(
    similarity: np.ndarray, threshold: float
) -> List[List[int]]:
    """Average-linkage agglomerative merge on index space.

    Returns a list of index groups. Each index refers to a row of the
    embedding matrix. Merge halts when the highest remaining
    inter-cluster average similarity drops below ``threshold``.

    Cost: each of up to N-1 merges rescans all remaining cluster pairs and
    recomputes their submatrix means, so this is ~O(N^3) worst case — the
    dominant clustering cost, not the O(N^2) matrix (review 2026-06-27 M4).
    """
    n = similarity.shape[0]
    clusters: List[List[int]] = [[i] for i in range(n)]

    while len(clusters) > 1:
        best_sim = -1.0
        best_i = -1
        best_j = -1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                sub = similarity[np.ix_(clusters[i], clusters[j])]
                s = float(sub.mean())
                if s > best_sim:
                    best_sim = s
                    best_i, best_j = i, j
        if best_sim < threshold or best_i < 0:
            break
        clusters[best_i].extend(clusters[best_j])
        del clusters[best_j]
    return clusters


def cluster_patterns(
    patterns: List[dict],
    *,
    threshold: float,
    min_size: int = 3,
    max_size: int = 10,
) -> Tuple[List[List[dict]], List[dict]]:
    """Group ``patterns`` into cosine clusters.

    Patterns without an ``embedding`` field bypass clustering and are
    returned in ``singletons`` unchanged.

    Returns:
        (clusters, singletons). ``clusters`` contains only groups whose
        size is at least ``min_size``; each cluster is sorted by
        ``effective_importance`` descending and sliced to ``max_size``.
        Any demoted tail or sub-``min_size`` group ends up in
        ``singletons`` flattened.
    """
    singletons: List[dict] = []
    embedded: List[dict] = []
    for p in patterns:
        if p.get("embedding"):
            embedded.append(p)
        else:
            singletons.append(p)

    if not embedded:
        return [], singletons

    matrix = np.asarray([p["embedding"] for p in embedded], dtype=np.float32)
    similarity = _cosine_matrix(matrix)
    raw_groups = _merge_clusters(similarity, threshold)

    clusters: List[List[dict]] = []
    for indices in raw_groups:
        members = sorted(
            (embedded[i] for i in indices),
            key=effective_importance,
            reverse=True,
        )
        if len(members) < min_size:
            singletons.extend(members)
            continue
        kept = members[:max_size]
        demoted = members[max_size:]
        clusters.append(kept)
        singletons.extend(demoted)

    return clusters, singletons
