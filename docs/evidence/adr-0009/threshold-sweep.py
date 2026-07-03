"""One-shot threshold calibration sweep for Phase C.

Reads ~/.config/moltbook/knowledge.json, filters live candidates
(embedding present, gated != True, valid_until is None, trust/strength
above floor), and reports:

1. effective_importance percentile distribution
2. pairwise cosine distribution (P50 / P75 / P90 / P95 / P99)
3. cluster count + size distribution for CLUSTER_THRESHOLD ∈ {0.55, 0.60, 0.65, 0.70, 0.75}
4. SIM_DUPLICATE / SIM_UPDATE candidate counts

Average-linkage clustering (same algorithm Phase A1 will implement).

Run with: python docs/evidence/adr-0009/threshold-sweep.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import List

import numpy as np

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "src"))

from contemplative_agent.core.forgetting import is_live  # noqa: E402
from contemplative_agent.core.knowledge_store import effective_importance  # noqa: E402


KNOWLEDGE = Path("~/.config/moltbook/knowledge.json").expanduser()


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def cosine_matrix(embs: np.ndarray) -> np.ndarray:
    """NxN cosine similarity matrix, assuming rows are L2-normalized copies."""
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = embs / norms
    return unit @ unit.T


def average_linkage_cluster(
    sim: np.ndarray, threshold: float
) -> List[List[int]]:
    """Average-linkage agglomerative clustering on a similarity matrix.

    Merge pairs of clusters whose inter-cluster average similarity is
    >= threshold. Returns a list of index lists.
    """
    n = sim.shape[0]
    clusters: List[List[int]] = [[i] for i in range(n)]

    def avg_sim(a: List[int], b: List[int]) -> float:
        s = sim[np.ix_(a, b)]
        return float(s.mean())

    while True:
        best = (-1.0, -1, -1)
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                s = avg_sim(clusters[i], clusters[j])
                if s > best[0]:
                    best = (s, i, j)
        if best[0] < threshold or best[1] < 0:
            break
        _, i, j = best
        clusters[i] = clusters[i] + clusters[j]
        del clusters[j]
    return clusters


def percentile(values: List[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else 0.0


def main() -> None:
    raw = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    # Filter: embedding present, gated != True, is_live (ADR-0021 bitemporal+trust+strength)
    candidates = [
        p for p in raw
        if p.get("embedding") and not p.get("gated") and is_live(p)
    ]
    print(f"Corpus: total={len(raw)}, gated={sum(1 for p in raw if p.get('gated'))}")
    print(f"Live embedded candidates (gated excluded, is_live pass): {len(candidates)}")

    if len(candidates) < 3:
        print("Too few candidates for sweep.")
        return

    # === 1. effective_importance percentile ===
    eff_imps = sorted(effective_importance(p) for p in candidates)
    print("\n=== effective_importance percentiles ===")
    for q in (10, 25, 50, 75, 90):
        print(f"  P{q:<2} = {percentile(eff_imps, q):.4f}")
    print(f"  min = {eff_imps[0]:.4f}, max = {eff_imps[-1]:.4f}")

    # === 2. pairwise cosine distribution ===
    embs = np.array([p["embedding"] for p in candidates], dtype=np.float32)
    sim = cosine_matrix(embs)
    iu = np.triu_indices_from(sim, k=1)
    pairs = sim[iu]
    print("\n=== pairwise cosine percentiles (upper triangle) ===")
    for q in (50, 75, 90, 95, 99):
        print(f"  P{q:<2} = {float(np.percentile(pairs, q)):.4f}")
    print(f"  max = {float(pairs.max()):.4f}, mean = {float(pairs.mean()):.4f}")

    # === 3. cluster count + size distribution per threshold ===
    print("\n=== average-linkage cluster sweep ===")
    print(f"{'thr':>6} {'clusters':>9} {'≥3':>4} {'≥5':>4} {'max':>4} {'singletons':>11}")
    for thr in (0.55, 0.60, 0.65, 0.70, 0.75):
        clusters = average_linkage_cluster(sim, thr)
        sizes = sorted([len(c) for c in clusters], reverse=True)
        ge3 = sum(1 for s in sizes if s >= 3)
        ge5 = sum(1 for s in sizes if s >= 5)
        singletons = sum(s for s in sizes if s < 3)
        print(f"{thr:>6.2f} {len(clusters):>9} {ge3:>4} {ge5:>4} {sizes[0] if sizes else 0:>4} {singletons:>11}")

    # === 4. SIM_DUPLICATE / SIM_UPDATE candidate counts ===
    print("\n=== dup/update threshold candidate pairs ===")
    for thr in (0.75, 0.80, 0.85, 0.90, 0.92, 0.95):
        n = int((pairs >= thr).sum())
        print(f"  cosine >= {thr:.2f}: {n} pairs ({100*n/len(pairs):.2f}% of upper triangle)")

    # === 5. sample cluster content at a promising threshold ===
    print("\n=== sample clusters at threshold=0.70 ===")
    clusters_70 = average_linkage_cluster(sim, 0.70)
    clusters_70.sort(key=lambda c: len(c), reverse=True)
    for idx, cluster in enumerate(clusters_70[:5]):
        if len(cluster) < 3:
            break
        print(f"\nCluster {idx+1} (n={len(cluster)}):")
        for i in cluster[:5]:
            p = candidates[i]
            print(f"  [{effective_importance(p):.3f}] {p['pattern'][:100]}")


if __name__ == "__main__":
    main()
