# ADR-0089 evidence — run-to-run stability measurement (2026-08-06)

One replication run pair answering the ADR-0089 Negative "run-to-run
stability is an open measurement":

- **Baseline**: `evals/baselines/comment_golden-2026-08-06.json`
  (run `20260806T104521Z`, i.e. 19:45 JST; approved 2026-08-06)
- **Replication**: [`stability-run-20260806T115449Z.json`](stability-run-20260806T115449Z.json)
  — started 69.5 min later (20:54 JST), same judge (`claude-sonnet-5`),
  same deepeval (4.1.5). Commits `6f15ec5`/`0d36943` landed between the
  runs: `6f15ec5` committed the tree the baseline run had already used,
  `0d36943` changed manifest emission only — generation and judge
  inputs are byte-identical by hash. Of the ten comparability fields, eight
  matched as independently emitted; two (`prompt_templates_sha256`,
  `sampling`) were back-filled onto the baseline in `0d36943` on the
  recorded judgment that the template layer and constants were
  unchanged.

## Result (n = 12 cases × 3 samples per run)

| reading | value |
|---|---|
| case-verdict flips | **3/12** (emptiness-1 DRIFTING→ADHERENT, emptiness-2-edge DEVIANT→DRIFTING, nonduality-3-adv DEVIANT→ADHERENT — one two-rank jump) |
| regressions | 0 (all flips in the improvement direction) |
| cases touching a 2–1 margin in either run | 7/12 (unanimous 3–0 in both runs: 4/12; the 12th case, mindfulness-1, is 1-1-1 in both) |
| sample-level pool | base A2/D25/V9 → repl A5/D26/V5 (A=ADHERENT, D=DRIFTING, V=DEVIANT) |
| dominant rubric failure | `register_natural` No 34/36 → 31/36 (stable axis) |

The three flips follow three different patterns — this is the pair's
central structural finding:

- **emptiness-1**: 3–0 → 2–1 — per-sample noise near a verdict
  boundary. The only pattern a larger per-run majority would damp.
- **emptiness-2-edge**: 3–0 DEVIANT → 3–0 DRIFTING — **opposite-
  unanimous with zero within-run variance in either run**. Under an iid
  per-sample model this pair has probability ≈ 0.03 even at the model's
  most favorable p = 0.5; it reads as a run-level *correlated* shift,
  which no per-run sample count fixes.
- **nonduality-3-adv**: [V,V,A] → [A,A,D] — a generation distribution
  spread across the whole verdict scale; samples=5 would not stabilize
  it either.

Also: **mindfulness-1 split 1-1-1 in both runs** (all three verdicts
present each time). Its case verdict is a stable DEVIANT only because
ties resolve toward the worse verdict — the conservative-bias rule
working as designed, not genuine stability.

## Decision recorded in ADR-0089 (amendment)

Keep `samples=3`. The escalation to 5 would cost a projected +67%
wall-clock (5/3 × the measured ~19 min; fixed per-run overhead
unmeasured), invalidate the approved baseline (`samples_per_case` is a
comparability field), and address only the first of the three flip
patterns. The measured noise floor becomes the interpretation rule:
**a single-run improvement claim of ≤3 flipped cases is
indistinguishable from noise** — and because one observed flip was
run-level correlated, that floor may be optimistic rather than
conservative. On the regression side the null pair produced none, but
0/12 only bounds the spurious-regression rate below ≈25% (rule of
three), and the all-improvement direction has a mundane candidate
explanation (two of the three flips started at DEVIANT, the floor rank,
which can only move up; the replication's pool was also globally
better). A lone regression on a 2–1 margin case therefore warrants
reading its judge evidence before acting.

Caveats: one run pair; the 25% flip-rate point estimate has a wide
Wilson 95% interval (≈ 9–53%) and treats cases as independent, which
the correlated flip undercuts. The structural findings (which cases are
unstable, and in which mode) do not depend on these estimates.

Analysis script: [`analyze-stability.py`](analyze-stability.py) — reads
the two run JSONs and prints the case/sample/rubric tallies with
majority margins used above. Usage:

```bash
python3 analyze-stability.py \
    ../../../evals/baselines/comment_golden-2026-08-06.json \
    stability-run-20260806T115449Z.json
```
