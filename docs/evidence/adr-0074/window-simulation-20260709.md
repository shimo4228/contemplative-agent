# ADR-0074 Evidence: Window Simulations and Novelty Calibration (2026-07-09)

All measurements on the live store (`~/.config/moltbook/knowledge.json`,
read-only), 2026-07-09. Pool: 2,182 total patterns, 1,993 live, 1,798 live
non-gated with embeddings. Inflow 2026-07-02..08: 100 / 49 / 93 / 97 / 99 /
105 / 89 patterns/day.

## Naive merge cost (defect 2)

`cluster_patterns` (pre-ADR-0074 naive submatrix-mean agglomeration),
threshold 0.70, min 3, max 10:

| N | naive merge | Lance-Williams (same partitions) |
|---|---|---|
| 293 (3-day window) | 17.2 s | < 0.1 s |
| 1,127 (14-day window) | not run (extrapolates to hours) | 0.7 s |

Equivalence: identical partitions verified on the 3-day window (26 clusters,
same size distribution) and pinned in `tests/test_clustering.py`
(`TestMergeEquivalenceADR0074`) against an in-test port of the naive
implementation on seeded blob / homogeneous / mixed-scale data.

## Window simulations (defect 4: candidate volume)

Exact average-linkage, threshold 0.70, min 3, max 10:

| window | N | clusters ≥ 3 (= skill candidates/run) | demoted tail | sub-min singletons |
|---|---|---|---|---|
| 3d (07-06..09) | 293 | 26 | 0 | 209 |
| 7d (07-02..09) | 632 | 65 | 4 | 377 |
| 14d (06-25..09) | 1,127 | 118 | 47 | 615 |

7 days sits between the `min_size` sensitivity floor (a theme needs 3
patterns inside one disjoint window ⇒ ~0.4 patterns/day detectable) and the
`MAX_BATCH=10` truncation regime that bites at 14 days.

## Theme recurrence

Adjacent windows A = 07-05..09 (32 clusters) and B = 07-01..04 (38 clusters):
every A cluster has a B counterpart at centroid cosine ≥ 0.70 — 32/32, match
range 0.795–0.90. Standing themes reappear in every window; windowed
extraction plus recurrence replaces singleton rescue.

## Novelty calibration: embeddings cannot separate same-theme from distinct-theme

| comparison | same-theme (A→B best match) | distinct-theme (intra-A) |
|---|---|---|
| centroid cosine | min 0.795 / p25 0.827 / med 0.837 | med 0.830 / p90 0.885 / max 0.902 |
| member-mean cross-sim | min 0.646 / med 0.679 / max 0.709 | med 0.619 / max 0.698 (0 of 496 pairs ≥ 0.70) |

Centroid level: full overlap (vapor-dominated centroids concentrate near the
corpus mean direction). Member level: distributions touch at the 0.65–0.71
boundary — 28/32 same-theme matches fall *below* the 0.70 clustering
threshold, indistinguishable from distinct-theme pairs. No usable threshold
exists at either level ⇒ theme coverage is a semantic judgment (LLM gate),
consistent with ADR-0036 (similarity ≠ applicability) and ADR-0046
(stocktake grouping revert).

## Corpus-wide connectivity (context)

Pairwise over all 1,798: mean 0.555, p90 0.640, p99 0.708; 21,978 pairs
(1.36%) ≥ 0.70. Single-linkage at 0.70 yields one giant component of 1,659
patterns (92%) — the echo-homogeneity backdrop against which average-linkage
still resolves ~30 standing themes per window.

Method: scripts in the session scratchpad (Lance-Williams simulation +
percentile analysis); reproducible from `knowledge.json` embeddings with
numpy only.
