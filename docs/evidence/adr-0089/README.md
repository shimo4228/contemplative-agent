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

---

# Second pair (2026-08-08) — the corrected injection regime

The pair above was measured under **full-corpus injection**, which the
2026-08-08 amendment established was never the regime production ran. Its
noise floor therefore describes a system that did not exist and does not
transfer. This pair re-measures under the corrected `two_pass_selected`
regime (and the re-snapshotted 45-skill fixture).

- **Run A**: [`regime-run-A-20260808T053509Z.json`](regime-run-A-20260808T053509Z.json)
- **Run B**: [`regime-run-B-20260808T060641Z.json`](regime-run-B-20260808T060641Z.json)
  — started ~31 min after A, same judge (`claude-sonnet-5`), same tree.

Neither is an approved baseline; approval is a human gate.

## Result (n = 12 cases × 3 samples per run)

| reading | old regime (2026-08-06 pair) | **corrected regime (this pair)** |
|---|---|---|
| case-verdict flips | 3/12, all improving, **0 regressions** | **1/12, a regression** (care-3-adv DRIFTING→DEVIANT, decided by `persona_intact` at a 2–1 margin) |
| cases not unanimous in ≥1 run | 8/12 | 8/12 |
| cases on the modal verdict | 8/12, 7/12 | **12/12, 11/12** |
| sample-level pool | A2/D25/V9 → A5/D26/V5 | A0/D32/V4 → A1/D29/V6 |
| `register_natural` No (pooled /72) | 65 | **70** |
| inter-run gap | 69.5 min | 31.5 min |
| selections observed | not measured (regime unrecorded) | 72/72 `judged`, **0 fail-open** |

Both runs are the same tree, so this is a **null pair** and every flip is
noise by construction. The one flip is therefore a false alarm, in the
regression direction, on the 2–1-margin profile the first pair's analysis
singled out: on the property that decides whether this gate is usable as a
regression detector, the corrected regime went 0/12 → 1/12.

The margin row is stated under one consistent definition. The first pair's
README counted `mindfulness-1` (1-1-1 in both runs) separately from its
"7/12"; under "not unanimous in at least one run" both pairs are 8/12 —
unchanged, not marginally worse.

Three findings, in descending order of how much they should change what
anyone does next:

1. **`register_natural` is regime-independent.** Pooled per pair (72
   samples each) it went 65/72 → 70/72, and was *identical across both
   runs of this pair* (35/36, 35/36). The pre-amendment reading — that the
   dominant failure was the corpus-overload pathology ADR-0081 exists to
   relieve — is falsified. Whatever drives it sits in generation
   temperature, identity, or the constitution, not in which skills are
   injected. The eval's largest signal was never about skills.

   The other three checks, pooled over 72 samples per pair, do not support
   a broad improvement claim either: `axiom_consistent` 4 → 0 (the only
   clean separation), `persona_intact` 14 → 10 with overlapping ranges
   (9,5 vs 4,6), `engages_post` 1 → **2**. Quoting the baseline against
   run A alone would give "9 → 4, 2 → 0, 1 → 0" and misrepresent all
   three.

2. **No large variance increase is visible — which is weaker than "variance
   fell".** The risk in choosing full reproduction over a pinned selection
   was that a second LLM call would widen the spread. Wilson 95% for 1/12
   is 1.5–35.4%, fully inside 3/12's 8.9–53.2%, and P(≤1 flip | n=12, true
   rate 25%) = 0.16 — the observation is consistent with no change at all.
   Two confounds also push the count down independently of variance: the
   verdict distribution collapsed (12/12 and 11/12 cases on one rank, so a
   rank-change metric falls mechanically), and the inter-run gap was half
   the first pair's, reducing exposure to the run-level correlated shift
   that pair identified. Supported claim: *a large increase would probably
   have shown; a moderate one would not.* Enough to decline retreating to
   a pinned selection; not enough to call two-pass more stable.

   The distribution collapse is itself a negative worth its own line:
   **twelve cases returning one verdict is near-zero per-case
   discrimination for a regression gate.** Whether it is a property of
   two-pass generation or a draw needs a second pair.

3. **The fail-open absorption hazard did not materialize here.** All 72
   selections across both runs returned `judged` and enforced. This is a
   reading of two runs, not a property: with the 45-skill corpus now over
   `NUM_CTX`, a fail-open would be a lost sample rather than a degraded
   one, and `aggregate_case`'s strict-majority rule would absorb one per
   case silently. That is why `injection_observed` is now recorded per run
   (see `T-FAILOPEN-OVERFLOW`).

Structurally the gate remains fragile in the same way as before: 8/12
cases sit at a 2–1 margin, so a single sample decides them. The interpretive
rule from the first pair — *a single run's improvement claim of ≤3 case
flips is indistinguishable from noise* — should be re-derived rather than
carried over, since it was measured under the wrong regime; this pair's
1/12 is one draw, not a floor.

```bash
python3 analyze-stability.py \
    regime-run-A-20260808T053509Z.json \
    regime-run-B-20260808T060641Z.json
```
