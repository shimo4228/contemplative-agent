# ADR-0084: Post-Distill Durability Gate — Judge the Produced Patterns, Not the Episode

## Status

accepted

## Date

2026-07-26

## Context

`distill` emits a near-constant quota per episode. Measured 2026-07-26 over
1,700 live episodes (launchd stderr) and 4,031 live rows in `knowledge.json`:

| Reading | Value |
|---|---|
| Patterns per episode, median | **2.00** (1:313 / 2:985 / 3:392 / 4-6:8) |
| Episodes returning zero patterns | **2 of 1,700 = 0.1%** |
| Per-day pat/ep over 14 days | 1.82–2.18 (flat) |
| `_is_valid_pattern` rejections | 0.7% |
| Live pattern inflow | ~121/day, ~800/week |

The prompt has always offered an abstain — "return an empty list … do not
invent a pattern to fill the space" — and it fired twice in 1,700 episodes.
An agent taking ~68 social actions a day does not learn something durable in
99.9% of them. **Output volume was a function of activity, not of learning.**

Two structural causes were visible in the prompt's return line
(`{"patterns": ["pattern1", "pattern2"]}` — 1 to 3 patterns, or `{"patterns": []}`):
the abstain was a degenerate case of the output format rather than a decision,
and it shared a line with a count band and a **two-element example**. The
observed median equalled the example's arity.

This was reached by re-diagnosing T-INSIGHT-NOVELTY. The original task blamed
the weekly novelty gate's judgment axes (no intra-batch comparison; name and
description strings rather than meta-behavior identity). Both were dropped:
the 2026-07-18 batch of 106 candidates was already in the staged ledger — and
therefore on the *known* side — for the 2026-07-25 run (166 known themes, 121
of 238 ledger names in the same lexical family), so the gate had the answer in
its inventory and still marked only 13/97 covered. Adding a second axis does
not explain a first axis that is not firing, and the weekly gate is downstream
of a corpus whose generality was manufactured upstream.

The same shape appears one layer further up: `insight_extraction.md` opens
`Synthesize the learned patterns below into ONE reusable skill.` and
`_extract_skill` drops only on LLM failure or a missing title, so the
"promotion worth" judgment ADR-0053 canonicalizes at insight time answers
"could a titled document be produced?" — 78 of 84 gate-surviving clusters
produced a skill and **none were dropped on worth**. That layer is tracked
separately (T-INSIGHT-WORTH) and is not touched here; ADR-0056 established
that pipeline variables change one at a time.

## Decision

1. **Leave `distill_episode.md` unchanged.** Every rewrite of it moved the
   abstain rate and the output register together (see Alternatives). The
   verdict is moved out of that prompt rather than tuned inside it.

2. **Add a post-distill durability gate** (`config/prompts/distill_postgate.md`,
   `distill._postgate`). After `_is_valid_pattern`, one LLM call receives the
   episode and its numbered patterns and returns `{"keep": [1, 3]}`. The judge
   holds the artifact: **producing the pattern is the evidence requirement.**

3. **Per-pattern, not per-episode.** A two-pattern episode with one grounded
   pattern keeps one. This is also what unpins yield from the distill prompt
   example's arity, so no count instruction is needed anywhere.

4. **The gate runs only when there is something to judge** — an empty
   extraction is already a verdict, and a gate call on it buys nothing.

5. **Fail open, with a reason code.** LLM failure, unparseable output, or a
   wrong-shaped verdict keeps every pattern and logs
   `reason=postgate_llm_none | postgate_parse | postgate_shape`. This gate can
   only ever *remove* rows the distiller already produced, so a broken gate
   must degrade to today's behavior. Silent pruning would delete research data
   with no trace (`no-delete-episodes` sensibility, ADR-0075 no-silent-fallback).
   Out-of-range and boolean indices are dropped, never clamped: a judge cannot
   keep a pattern it was not shown.

6. **A judged abstain becomes a first-class reason code.**
   `ABSTAIN_NOTHING_DURABLE` joins the three fault reasons but is tallied
   apart from them (`FAULT_ABSTAIN_REASONS`), does not count as a
   circuit-breaker failure, and reaches the same code path whether the model
   returned `[]` itself or the gate dropped the last pattern. The summary line
   `all N episodes produced output` is replaced by an always-emitted yield line
   reporting episodes-that-yielded plus `nothing_durable` — the old line
   counted a judged abstain as output, which is why the 0.1% rate stayed
   invisible while being the whole defect.

7. **On by default; `MOLTBOOK_DISTILL_POSTGATE=0` opts out.** ADR-0081 shipped
   its counterpart flag default-off and carried production through the launchd
   plist's `EnvironmentVariables`. That mechanism silently reverts:
   `install-schedule` regenerates the plist from a template and re-emits the
   flag only if it happens to be exported in the invoking shell
   (`cli/schedule.py`, whose own comment records "without it to turn it back
   off"), so a later re-install from a plain shell disables enforcement with no
   error and no log line — which is why that flag had to be manually
   re-verified against the live plist on 2026-07-25. The distill plist has no
   env plumbing at all, so routing this gate the same way would have meant
   building that failure mode from scratch. Defaulting on removes the class:
   the researched design is what runs, and opting out is an explicit act rather
   than an omission. The gate fails open at every step, so the cost of it being
   on is bounded by today's behavior, and a dropped pattern is re-derivable —
   episodes are retained permanently, so re-running distill over the day's log
   reproduces it.

### Measurement

Offline A/B replay over one fixed, deterministically-sampled set of 40 episodes
([`replay-distill-abstain-20260726.py`](../evidence/adr-0084/replay-distill-abstain-20260726.py);
read-only, production unwired).
The baseline arm reproduced the production reading (median 2, zero-rate 0.0%,
mean 1.83 vs production 1.82–2.18), which is what licenses attributing the
other arms' deltas to their change. Register baseline is 890 production
patterns, measured with no LLM calls. Faults were zero in every arm.

| | baseline | v2 merged/judge-frame | v3 merged/distill-frame | v4 pre-gate | **v5 post-gate** |
|---|---|---|---|---|---|
| distill prompt | — | rewritten | rewritten | unchanged | **unchanged** |
| judged abstain | 0.0% (prod 0.1%) | 15.0% | 2.5% | 0.0% | **5.0%** |
| patterns total | 74 | 50 | 50 | 81 | **59** |
| pat/ep median | 2.0 | 1.0 | 1.0 | 2.0 | **1.0** |
| first person | 96.7% | 90.0% | 98.0% | 98.8% | **98.3%** |
| moment-indexed opener | 85.7% | 80.0% | 90.0% | 88.9% | 83.1% |
| `I <perception verb>` | 72.8% | 54.0% | 66.0% | 70.4% | **86.4%** |
| median chars | 357 | 318.5 | 354.5 | 363 | **358** |

v5 is the only arm that reduces volume without paying register for it, and the
`I <perception verb>` rise above baseline is mechanical rather than lucky: what
the gate drops is precisely the patterns with no concrete moment in them, so
trimming raises the quality of what remains.

## Alternatives Considered

### Rewrite `distill_episode.md` to make abstain a first-class choice (v2)

Reframing the task ("Read the episode and decide whether it evidences anything
durable") produced the largest abstain rate measured, 15%, reproduced exactly
across two independent runs (6/40 both times). Rejected because it is the only
arm whose register degraded on every axis — `I <perception verb>` 54% vs 72.8%
baseline (≈3σ at n=50), median length 318.5 vs 357. ADR-0072 installed that
register deliberately and proved upstream instructions move output measurably;
this is that effect working against us.

### Remove only the count band and two-element example (v3)

Register stayed at baseline (98.0% / 90.0% / 354.5 chars) and total volume fell
as far as v2 (74 → 50). Rejected because the abstain rate barely moved (2.5%):
the distribution peak shifted from 2 to 1, replacing "always 2" with "always 1".
That is the same structural defect at a lower constant — volume still tracks
activity — and the diagnosed defect would have been declared fixed by a metric
(total count) that the change did not actually address.

### Ask the durability question BEFORE distilling (v4)

A standalone gate over the episode alone, with the distill prompt byte-identical
to baseline. Rejected on measurement: **0 abstains in 40 episodes**, with zero
gate faults, so it was not fail-open masking a real verdict. Diagnosis confirmed
the plumbing was sound (episode substituted, JSON parsed, `durable` a real
boolean) and the gate was not degenerate (a contentless control episode returned
`durable: false`). It answers yes because naming a worthwhile moment costs
nothing when you never have to write it. This result is the reason the gate
moved after production — and it corrected the reasoning that motivated the
split, which had assumed the generation frame was a *bias*. It was the
*evidence requirement*.

### Reintroduce an LLM importance score at distill time

Considered because the converged practice (Generative Agents' poignancy rating,
D-MEM's Critic Router) controls yield with a per-item importance value rather
than a count. Rejected: ADR-0053 Decision 1 places every value judgment "at the
only moment its input exists" and both surviving judgment points are read-time
(query-time cosine; insight-time promotion worth); Decision 4 makes a stored
score write-once and rejects post-hoc rescoring as the write face of the
self-reingestion echo loop. ADR-0056 then removed the write-time score outright
after two ablations (Kendall tau 0.851 at n=764, 0.843 at n=822, identical
top-3/top-5 batch order). A write-time frozen number lost its consumer when
ADR-0019 moved retrieval to views. The count problem is solved here by
per-pattern judgment instead, which needs no stored score.

### Adopt an external memory framework (mem0 / Letta / Zep)

`/search-first` Phase 0. Rejected: all require a server, external API, or a
large dependency tree, against `requests`+`numpy` and the security-by-absence
boundary (ADR-0007 / ADR-0015). The converged practice that *was* adopted is
mem0's shape of making abstain an explicit action rather than a degenerate
output format. The practice deliberately **not** adopted is "write atomic
normalized facts" — it collides head-on with the first-person moment-indexed
register ADR-0072 installed against echo.

`Verdict: Extend — custom (practice adopted, no package).`

## Consequences

- The nightly distill run gains one short LLM call per pattern-producing
  episode. Measured cost: the job currently runs 03:30 → ~03:46 for ~68
  episodes; the gate adds roughly 8–10 minutes, finishing well before 04:00 and
  outside the 0/6/12/18 JST session windows.
- The durable store grows more slowly (replay: −20%) and its
  rows are more strongly moment-indexed. Patterns written before this ADR and
  after it are therefore **not homogeneous**, and the corpus cannot be made
  uniform retroactively. This is a research record; the discontinuity is
  recorded here rather than smoothed over.
- The judged-abstain rate becomes readable in production for the first time.
  Pre-registered revert criteria for the next weekly reading (~2026-08-01,
  n≈470), against the 890-pattern baseline above: revert if the judged abstain
  rate is below 2%, or if first-person falls below 90%, or if median pattern
  length falls below 320.
- Fault surface doubles for pattern-producing episodes (two calls, two parse
  layers). Both are covered by the chaos fault column
  (`tests/test_distill_chaos.py::TestPostGate`, 8 cases: selective keep, keep-all
  drop → judged abstain, out-of-range indices, five unusable-verdict shapes
  fail-open, no gate call on an empty extraction, direct callers opt in) plus
  `TestPostGateDefault`, which drops the suite-wide override and asserts the
  production default really is on — so flipping it back cannot pass silently.
- A measurement error is recorded deliberately, because it nearly decided the
  outcome. The first register proxy scanned only the first 80 characters for
  `I` / `my`. The prompt requires each pattern to *name the concrete moment*,
  which produces a long leading subordinate clause — the first `I` lands at a
  median offset of 102 characters, past the window in 57% of patterns. The
  proxy measured clause length and reported 40% first-person where whole-text
  scanning reports 98%. A candidate was failed and an extra arm run on that
  artifact. **Register proxies must scan the whole pattern**, and a proxy that
  decides an outcome must be validated against the artifact it proxies before
  the outcome is called.
- A pre-existing quality issue surfaced and is deliberately out of scope: 2.9%
  of production patterns end without terminal punctuation and 1.3% have
  unbalanced parentheses — truncated fragments passing `_is_valid_pattern`. The
  rate is the same across every arm, so it is background, not a regression.
