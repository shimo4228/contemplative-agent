"""Average-linkage agglomerative cosine clustering (ADR-0019 companion).

Used by ``insight`` and ``rules_distill`` to turn an embedded corpus
into sub-topic buckets without a predefined axis (view). The only
knobs are a cosine threshold (when to stop merging) and min/max
cluster size.

Design choices:
- Average-linkage rather than single-linkage to avoid chain-effect
  clusters that drag the LLM into over-abstract synthesis
- ``_merge_clusters`` runs the exact average-linkage agglomeration via
  the Lance-Williams update (ADR-0074): the merged row's inter-cluster
  mean is the size-weighted mean of the two source rows, so each merge
  is one vectorized O(N) row update plus an O(N^2) argmax instead of a
  Python-level rescan of every cluster pair. Same partitions as the
  retired naive submatrix-mean implementation (equivalence pinned in
  tests), but ~O(N^2) per merge in numpy: the 2026-07-09 live pool
  (N=1798) clusters in under a second where the naive loop needed hours
  (the review 2026-06-27 M4 upgrade, delivered once measured)
- Pure numpy, no scipy/sklearn dependency

Patterns without an ``embedding`` field are returned as singletons.
Cluster members are sorted by ``effective_importance`` descending;
anything past ``max_size`` is demoted to singletons so the caller can
see it in the next pass.
"""

from __future__ import annotations

import numpy as np

from .knowledge_store import effective_importance


def _cosine_matrix(embeddings: np.ndarray) -> np.ndarray:
    """Return NxN cosine similarity between row vectors."""
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = embeddings / norms
    return unit @ unit.T


def _merge_clusters(similarity: np.ndarray, threshold: float) -> list[list[int]]:
    """Average-linkage agglomerative merge on index space.

    Returns a list of index groups. Each index refers to a row of the
    embedding matrix. Merge halts when the highest remaining
    inter-cluster average similarity drops below ``threshold``.

    Exact Lance-Williams agglomeration (ADR-0074): merging clusters i and
    j updates every other cluster k's linkage in one vectorized pass —
    ``s(k, i∪j) = (n_i·s(k,i) + n_j·s(k,j)) / (n_i + n_j)`` — which equals
    the mean over the merged submatrix, so partitions are identical to
    recomputing submatrix means from scratch (equivalence pinned in
    tests). Dead rows/columns are parked at ``-inf`` so the global argmax
    stays a flat O(N^2) numpy scan.
    """
    n = similarity.shape[0]
    if n == 0:
        return []

    # float64 keeps the incremental weighted means stable across long
    # merge chains; the input cosine matrix is typically float32.
    sim = similarity.astype(np.float64, copy=True)
    np.fill_diagonal(sim, -np.inf)
    sizes = np.ones(n)
    members: list[list[int]] = [[i] for i in range(n)]

    while True:
        flat = int(np.argmax(sim))
        i, j = divmod(flat, n)
        if not np.isfinite(sim[i, j]) or sim[i, j] < threshold:
            break
        ni, nj = sizes[i], sizes[j]
        merged_row = (ni * sim[i] + nj * sim[j]) / (ni + nj)
        sim[i, :] = merged_row
        sim[:, i] = merged_row
        sim[i, i] = -np.inf
        sim[j, :] = -np.inf
        sim[:, j] = -np.inf
        sizes[i] = ni + nj
        members[i].extend(members[j])
        members[j] = []

    return [m for m in members if m]


def cluster_patterns(
    patterns: list[dict],
    *,
    threshold: float,
    min_size: int = 3,
    max_size: int = 10,
) -> tuple[list[list[dict]], list[dict]]:
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
    singletons: list[dict] = []
    embedded: list[dict] = []
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

    clusters: list[list[dict]] = []
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
