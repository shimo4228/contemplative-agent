# Importance Ablation — Does the LLM Rating Earn Its Keep Beyond Decay?

Evidence for [ADR-0053](../../adr/0053-importance-encoding-time-significance.md)'s
measurement gate. Run 2026-06-06 against the production store
(`~/.config/moltbook/knowledge.json`, 764 patterns) with
[`importance-ablation.py`](importance-ablation.py) (read-only).

## Question

`effective_importance = importance × 0.95^days` drives exactly two things
(see ADR-0053's propagation map): the insight cluster processing order and
the intra-cluster `max_size` slice. The stored `importance` is an LLM
rating (1–10, assigned once at distill time). If that rating were retired
and the base held constant — decay kept — how much would insight's actual
behavior change?

Three variants over **identical raw clusters** (the agglomerative merge
never reads importance, so group membership is constant):

| variant | intra-cluster sort | cluster order |
|---|---|---|
| current | `effective_importance` desc | `size × mean(effective_importance)` |
| decay-only | pure `0.95^days` desc | `size × mean(decay)` — **what retiring the LLM rating looks like** |
| size-only | recency desc | size (reference: no score, no decay) |

## Results

Corpus: 764 patterns → 629 live → 434 insight candidates (live, not gated),
100% embedding coverage. Clustering at `CLUSTER_THRESHOLD_INSIGHT = 0.70`,
min 3, max 10 → **41 clusters**, 5 oversize (demotion path active).

### Stored score distribution (all 764)

Top-skewed and coarse: 44% rated 0.9–1.0, 26% sit at 0.5 where the
fallback default collides with a genuine 5/10 rating, only a 9% low tail
(0.1–0.4) carries an unambiguous signal. mean=0.729, stdev=0.243.

### current vs decay-only — the retirement question

- **Kendall tau: 0.851** over 41 clusters
- **top-3 overlap: 3/3, top-5 overlap: 5/5** (identical)
- Demotion diff in the 5 oversize clusters: **at most 1 member of 10
  swaps** kept/demoted (c2: 1, c5: 1, c11: 1, c13: 0, c16: 1)

### current vs size-only — reference

- Kendall tau: 0.144, top-3 overlap 1/3 — but 40 of 41 clusters tie under
  size-only ordering, so this tau is largely a tie-breaking artifact, not
  a measure of the LLM rating's contribution.

### Anti-chatter check

The recorded rationale for the importance factor
(`clustering.py:104` docstring: "Size-only biases toward chatter") is
real as a phenomenon — the size-18 cluster c2 ranks 1st under size-only
but 18th under current. However, decay-only also demotes it (rank 14):
**the chatter demotion is driven by time decay, not by the LLM rating.**
c2's members are old, not low-rated.

## Reading

The LLM rating's marginal contribution beyond pure time decay is ~zero on
the current corpus: identical top-5 batch order, ≤1-member kept-set
deltas, tau 0.85. The pre-registered criterion in ADR-0053 ("small
ordering difference + marginal demotion diff → grounds for retirement")
is met.

This evidence **supports retirement** of the distill-time LLM rating
(keeping decay), but per ADR-0053 the decision is gated on one remaining
condition: the §B1 threshold-retune observation window closing. (A second
gate — the AKC position paper shipping — was listed at acceptance and
removed the same day; see ADR-0053's Amendment.) Re-run this script
before deciding — the corpus grows and the result may shift.

## Reproduce

```bash
uv run python docs/evidence/adr-0053/importance-ablation.py
```

Read-only; prints the full markdown report (corpus stats, distribution,
per-cluster rank table, tau, demotion diff) to stdout.
