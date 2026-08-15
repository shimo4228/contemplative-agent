# §B1 — Did the Relevance Threshold Retune Take Effect? (2026-06-17)

Evidence for [ADR-0056](../../adr/0056-retire-importance-llm-scoring.md)'s first
gate condition ("the §B1 observation window is closed and validated"). English
rendering of the 2026-06-17 findings note; every reading below is unchanged from
the original measurement.

- **Subject**: the relevance threshold relaxation in commit `593f641`
  (2026-06-05). Observation window: 12 days.
- **Data source**: `~/.config/moltbook/logs/agent-launchd.log`, read 2026-06-17.
  Only self-authored aggregate lines were extracted; the episode JSONL was not
  read, and no third-party content appears in the readings below.
  **Do not repeat this method against that file.** The 2026-08-01
  T-LOG-DEBUG-CONTENT finding established that the log's `-v` DEBUG output had
  been carrying full public post bodies and other-agent notification JSON, and
  the project now excludes it from reading entirely. This measurement predates
  that finding.
- **Method**: sliced pre/post at the last occurrence of `threshold 0.95`
  (L141066). The log carries no dates, so the threshold wording is what cuts it.

## Slices

| | Period | Sessions | Relevance decision lines |
|---|---|---|---|
| pre | 04-18–06-05 (mostly the 0.95 regime) | 193 | 9,788 |
| post | 06-05–06-17 (the 0.80 regime) | 46 | 821 |

46 post sessions ≈ 11.5 days, which matches the observation window. Recency was
confirmed independently from API timestamps embedded in post-slice WARNINGs
(e.g. `2026-06-16T21:00:07`).

## ① Pass rate (comment threshold) — ✅ took effect, somewhat more generous than expected

| | threshold | passed / total | pass rate |
|---|---|---|---|
| pre baseline | 0.95 only | 2626 / 9751 | **26.9%** |
| post | 0.80 (all rows) | 474 / 821 | **57.7%** |

- Predicted ~46%, measured 57.7%. The prediction came from a 22-hour sample of
  N=195; the measurement is N=821. **An overshoot, but in the opposite direction
  from starvation, so the harm is small.**
- Every post-slice `passed threshold` is **0.80** — the `0.70` known-agent branch
  appears zero times in the log, meaning the returning-agent path is essentially
  never firing.

## Score distribution (the most important finding) — the identity scorer quantizes to 0.1 steps

Relevance histogram over the post slice:

```text
247  0.90      ┐
170  0.80      ├ ≥0.80 passes = 474
 56  1.00      │
  1  0.95      ┘ (the only intermediate value, an outlier)
─────────────  gate boundary at threshold 0.80
102  0.50
 67  0.20
 59  0.00
 40  0.30
 36  0.60
 32  0.10
 11  0.40      ┘ below = 347
```

- Scores land in only **11 buckets: 0.00, 0.10, …, 0.90, 1.00** — direct evidence
  for the "0.81–0.99 is empty" reading recorded earlier.
- **Consequence: thresholds 0.70 and 0.80 behave identically on a regular post**
  (the 0.70 bucket is empty). The only meaningful boundaries are the edges of
  populated buckets — 0.80 / 0.90 / 1.00. The current 0.80 is an explicit
  "include the 0.80 bucket" choice and is robust.
- **Counterfactual**: had the threshold stayed at 0.95, the post period would
  have passed `1.00(56) + 0.95(1) = 57 / 821 = 6.9%`. The retune was effectively
  "1.00-only gate → ≥0.80 gate", raising the comment-eligible share roughly
  **eightfold**. That is the substance of the retune.

## ② Comment frequency — ✅ recovered

| | comments/session |
|---|---|
| pre, whole slice (48-day mean, misleading) | 11.42 |
| **pre, last 10 sessions (the true before)** | **7.30** |
| **post** | **10.26** |

- From the starved window immediately before the retune (7.30) to post (10.26):
  **+40%**. The 48-day mean of 11.42 is pulled up by an early high-activity
  period and is not a fair comparison point.
- Total comment volume is also bounded by rate/budget, so a 57.7% pass rate does
  not translate into runaway commenting (it caps out around 10/session).

## ③ The 1.00 bucket / clamp contamination — ✅ none (no cleanup needed)

- `Relevance score out of range, rejecting` (the new instrument from the L2 fix)
  fires **zero times in both pre and post**. The score>1.0 contract-violation
  path never fired in the field, so **clamp contamination never existed**. The
  instrument went in defensively and is correctly reading zero.
- Share of 1.00: pre 3.3% / post 6.8% (up in post). This is not clamp-derived —
  it follows from the smaller number of scored items per session in post
  (~18/session vs ~51/session in pre), a denominator composition difference. Not
  a contamination signal.

## ④ M1 load from the increase in internal notes — ✅ absorbed

- Note generation fires at `score ≥ 0.70` (effectively `≥0.80` after
  quantization), so post coverage is **474/821 = 57.7%** (the old 0.85 threshold
  would have given the 37% at 0.90+, and the quoted 22-hour sample gave 15%).
  This is consistent with the ~51% expectation.
- Load impact: across 46 post sessions, **0 Tracebacks / 4 ERRORs / 16 WARNINGs**.
  Every ERROR and WARNING is either the known `Failed to unfollow` 404 drift
  (§B5 — the list-following API does not exist; **no repair is proposed**) or a
  skipped submolt selection. No note-derived timeouts and no incomplete runs.
  **The extra ~10 LLM calls/session did not break completion.**

## Verdict

**The retune succeeded. Recommendation (a): keep it.**

All four observations are positive: pass rate 26.9%→57.7% (above prediction but
on the safe side) / comment frequency 7.30→10.26 (recovered) / zero clamp
contamination (no cleanup needed) / note load absorbed.

### Carried forward to the next action

- **Coupled to §C2 (swapping in a different local model)**: the robustness of
  the current 0.80 rests on "the 0.70 bucket is empty", which is specific to this
  scorer/model's quantization. A different model may quantize differently, so
  **re-measuring the threshold is mandatory at any model swap** (re-derive the
  edges of the populated buckets).
- **The §C3 decision window (retiring LLM importance scoring) is now open**: the
  §B1 wait is resolved, so the ablation re-run and the decision can proceed.
- The known-agent 0.70 path appears zero times in the log, suggesting the
  threshold relaxation for returning agents is not effective in practice (a
  question about when `has_interacted_with` fires). Out of scope for B1, but a
  candidate for future observation.
