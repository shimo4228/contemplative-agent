#!/usr/bin/env python3
"""Read-only ablation: insight cluster ordering with vs without importance.

Evidence for ADR-0053's measurement gate. Replicates the insight
full-mode pipeline (get_live_patterns -> exclude gated -> cluster ->
order batches) and compares two policies on identical raw groups:

  current:     intra-cluster sort = effective_importance desc (clustering.py:104)
               cluster order      = size x mean effective_importance (insight.py:101)
  decay-only:  intra-cluster sort = pure time decay (0.95^days) desc
               cluster order      = size x mean decay
               -> this is what RETIRING the LLM rating would look like
                  (constant base, decay kept)
  size-only:   intra-cluster sort = distilled (recency) desc
               cluster order      = size (stable on merge order)
               -> full ablation reference (no score, no decay)

The agglomerative merge itself never reads importance, so group
membership is identical across variants — the diff isolates exactly
what the LLM score buys beyond decay: (a) which members survive the
max_size slice, (b) which clusters the LLM sees first.

Run from repo root:  uv run python .notes/importance-ablation-20260606.py
Writes nothing. Prints a markdown report to stdout.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path

from contemplative_agent.core.clustering import _cosine_matrix, _merge_clusters
from contemplative_agent.core.knowledge_store import (
    effective_importance,
    is_live,
    pattern_id,
)
from contemplative_agent.core.thresholds import (
    CLUSTER_THRESHOLD_INSIGHT,
    MAX_BATCH,
)

import numpy as np

KNOWLEDGE = Path.home() / ".config/moltbook/knowledge.json"
MIN_SIZE = 3  # insight.MIN_PATTERNS_REQUIRED


def kendall_tau(rank_a: dict, rank_b: dict) -> float:
    """Plain pairwise Kendall tau over a shared key set (no scipy)."""
    keys = sorted(rank_a)
    concordant = discordant = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            da = rank_a[keys[i]] - rank_a[keys[j]]
            db = rank_b[keys[i]] - rank_b[keys[j]]
            prod = da * db
            if prod > 0:
                concordant += 1
            elif prod < 0:
                discordant += 1
    pairs = concordant + discordant
    return (concordant - discordant) / pairs if pairs else 1.0


def main() -> None:
    patterns = json.loads(KNOWLEDGE.read_text())
    live = [p for p in patterns if is_live(p)]
    candidates = [p for p in live if not p.get("gated")]
    embedded = [p for p in candidates if p.get("embedding")]

    print("## Corpus")
    print(f"- total patterns: {len(patterns)}")
    print(f"- live (valid_until is None): {len(live)}")
    print(f"- insight candidates (live, not gated): {len(candidates)}")
    print(f"- with embedding: {len(embedded)} "
          f"({len(embedded)/len(candidates)*100:.0f}% coverage)")
    print()

    imps = [p.get("importance", 0.5) for p in patterns]
    hist = Counter(round(i, 1) for i in imps)
    print("## Importance distribution (all 764, stored base score)")
    for k in sorted(hist):
        print(f"- {k:.1f}: {hist[k]}")
    print(f"- mean={statistics.mean(imps):.3f} stdev={statistics.stdev(imps):.3f}")
    print()

    # --- identical merge for both variants -------------------------------
    matrix = np.asarray([p["embedding"] for p in embedded], dtype=np.float32)
    similarity = _cosine_matrix(matrix)
    raw_groups = _merge_clusters(similarity, CLUSTER_THRESHOLD_INSIGHT)
    groups = [[embedded[i] for i in g] for g in raw_groups if len(g) >= MIN_SIZE]

    oversize = [g for g in groups if len(g) > MAX_BATCH]
    print("## Clusters (threshold "
          f"{CLUSTER_THRESHOLD_INSIGHT}, min {MIN_SIZE}, max {MAX_BATCH})")
    print(f"- clusters >= min_size: {len(groups)}")
    print(f"- sizes: {sorted((len(g) for g in groups), reverse=True)}")
    print(f"- oversize (> max {MAX_BATCH}, demotion happens): {len(oversize)}")
    print()

    # --- per-variant kept sets + ordering ---------------------------------
    def decay_weight(p: dict) -> float:
        """effective_importance with the LLM base score held constant."""
        return effective_importance({**p, "importance": 1.0})

    def kept(g, key):
        return sorted(g, key=key, reverse=True)[:MAX_BATCH]

    rows = []
    for idx, g in enumerate(groups):
        k_cur = kept(g, effective_importance)
        k_dec = kept(g, decay_weight)
        k_size = kept(g, lambda p: p.get("distilled", ""))
        rows.append({
            "id": idx, "size": len(g), "kept": len(k_cur),
            "score_current": len(k_cur) * (
                sum(effective_importance(p) for p in k_cur) / len(k_cur)),
            "score_decay": len(k_dec) * (
                sum(decay_weight(p) for p in k_dec) / len(k_dec)),
            "score_size": len(k_size),
            "demote_diff_decay": sorted(
                {pattern_id(p) for p in k_cur} ^ {pattern_id(p) for p in k_dec}),
        })

    def ranks(score_key):
        ordered = sorted(rows, key=lambda r: r[score_key], reverse=True)
        return {r["id"]: i for i, r in enumerate(ordered)}, ordered

    rank_c, order_c = ranks("score_current")
    rank_d, order_d = ranks("score_decay")
    rank_s, order_s = ranks("score_size")

    print("## Ordering comparison")
    print("| cluster | size | kept | rank current | rank decay-only | rank size-only |")
    print("|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: rank_c[r["id"]]):
        print(f"| c{r['id']} | {r['size']} | {r['kept']} "
              f"| {rank_c[r['id']]+1} | {rank_d[r['id']]+1} | {rank_s[r['id']]+1} |")
    n = len(rows)

    def overlap(oa, ob, k):
        return len({r["id"] for r in oa[:k]} & {r["id"] for r in ob[:k]})

    print()
    print("### current vs decay-only (= what retiring the LLM rating changes)")
    print(f"- Kendall tau: {kendall_tau(rank_c, rank_d):.3f} over {n} clusters")
    print(f"- top-3 overlap: {overlap(order_c, order_d, 3)}/3, "
          f"top-5 overlap: {overlap(order_c, order_d, 5)}/{min(5, n)}")
    print()
    print("### current vs size-only (reference: no score, no decay)")
    print(f"- Kendall tau: {kendall_tau(rank_c, rank_s):.3f} over {n} clusters")
    print(f"- top-3 overlap: {overlap(order_c, order_s, 3)}/3, "
          f"top-5 overlap: {overlap(order_c, order_s, 5)}/{min(5, n)}")
    size_ties = sum(c for c in
                    Counter(r['score_size'] for r in rows).values() if c > 1)
    print(f"- size-only ties (resolved arbitrarily by merge order): "
          f"{size_ties} clusters — tau against size-only is partly artifact")
    print()

    print("## Demotion diff, current vs decay-only (oversize clusters only)")
    any_diff = False
    for r in rows:
        if r["size"] > MAX_BATCH:
            diff = r["demote_diff_decay"]
            any_diff = any_diff or bool(diff)
            print(f"- c{r['id']} (size {r['size']}): "
                  f"{len(diff)//2} member(s) swap kept/demoted")
    if not oversize:
        print("- (no oversize clusters — demotion path inert on current corpus)")
    elif not any_diff:
        print("- (kept sets identical across variants)")


if __name__ == "__main__":
    main()
