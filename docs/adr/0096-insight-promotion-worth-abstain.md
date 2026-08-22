# ADR-0096: Promotion-Worth Abstain at Insight Time — Judge the Produced Skill, List the Surprise

## Status

partially-superseded-by ADR-0097 (Decisions 2 and 10–12 — the post-extraction worth judge and the surprise instrument — retired 2026-08-22 by this ADR's own pre-registered fallback after the first production reading read 46/46 promote; Decisions 1 and 4–8 — the in-band NOTHING-PROMOTABLE abstain, the reason code, the yield line, the fault/verdict control-flow split — remain in effect)

## Date

2026-08-17

## Context

[ADR-0053](./0053-importance-encoding-time-significance.md) Decision 1
canonicalizes three judgment points, each taken "at the only moment its input
exists" (ADR-0056 later retired the first, leaving two). One of the survivors
is **promotion worth**, at insight time, by the LLM, over the full cluster. Its
justification cites `insight.py`'s own docstring: "LLM extraction drops the
cluster if no skill can be distilled." That citation was never true of the
implementation, and ADR-0053 is deliberately not amended here — what to do
about a justification that never held is part of what this ADR asks the owner
to decide.

The implementation never had that channel.
`config/prompts/insight_extraction.md:1` opens
`Synthesize the learned patterns below into ONE reusable skill.` — a
production order with no alternative — and `_extract_skill` dropped a cluster
on exactly two conditions: the LLM call failed, or the output had no
extractable title. The question actually answered was **"could a titled
document be produced?"**

The 2026-07-25 run measures the gap. Of 97 clusters the ADR-0074 novelty gate
judged, 84 survived as novel, 78 produced a candidate, and the ~6 that did not
were all LLM failures or untitled output — **zero were dropped on worth**.
(84 − 78 = 6 exactly; that all six were faults is a deduction from the two drop
conditions the code had, not a separate measurement.) The
owner then adopted 5 and rejected 73. The same run's review recorded why: about
six in ten candidates were one meta-behavior restated ("shift focus from
surface to structure/constraint/boundary"), and the 2026-08-14 weekly reached
the same reading independently — "the whole batch sits between 0.756 and 0.878
cosine against its nearest adopted skill … the batch is one theme restated 49
ways", 5 adopted / 44 rejected.

This is the defect [ADR-0084](./0084-post-distill-durability-gate.md) fixed one
layer down, and that ADR named this layer as the next one, deferred under
ADR-0056's "pipeline variables change one at a time". That condition is now
met: the distill gate landed 2026-07-26 and three weekly runs have gone through
it (08-01, 08-08, 08-14) with no further change to `core/distill.py` or the
distill prompts (`7b094fc` is still the last commit touching either).

ADR-0074 Decision 8 is part of the same picture. It added a "Naming and
vocabulary" section to this prompt — real discipline about *how to name* a
skill — while leaving unasked whether the skill should exist. Register collapse
continued, which is what a naming fix predicts when the defect is production
pressure rather than word choice.

A second question rides along. The 2026-07-18 redesign notes and the D-MEM
Critic Router (arXiv:2603.14597) both suggest **surprise** — how far a
candidate sits from what was distilled lately — as material for this decision.
ADR-0074 rejected an embedding cutoff, but what it rejected was a *coverage*
claim ("cosine ≥ threshold ⇒ already covered"); surprise is a claim about a
*distribution*, so it is out of that rejection's scope. It was calibrated
before being designed in, on 2026-08-17, against the owner's own 78 labelled
decisions — LLM-free and production-unwired, the audit log's `source_ids`
recovering all 78 cluster centroids
([`surprise-calibration-20260817.py`](../evidence/adr-0096/surprise-calibration-20260817.py);
its inputs live under `$MOLTBOOK_HOME` and are absent from a clone, so the
script is the reproducible artifact, not the data):

| Reading | Value |
|---|---|
| `s_mean` AUC against adopt/reject (k=100/300/1000) | 0.786 / 0.762 / 0.767 |
| Permutation p | 0.015 / 0.025 / 0.023 |
| Adopted-5 rank median (of 78) | 19 (random expectation 39.5) |
| Raw max-cosine spread / p50 (k=1000) | **0.108 / 0.806** |
| The same spread after z-normalization | **~4.95 sd** |

Two things follow, and they point in opposite directions. Surprise is not
uninformative. And it does not reproduce the decision: only 5 positives, so a
normal-approximation interval on an AUC of 0.79 at 5 vs 73 reaches down near
0.5 — and at every k the single most surprising candidate was one the owner
**rejected**
(`operationalizing-systematic-absence`) — from precisely the family the owner
pruned as saturated. Rare is not useful, which is why D-MEM gives its Utility
judge a veto rather than ranking on novelty. The z-normalization row is the
sharper warning: the raw distribution is collapsed at this store's historical
nearest-neighbour ceiling, and z-scoring manufactures a five-sigma separation
out of a 0.1-wide band.

## Decision

1. **Open an abstain in `insight_extraction.md`, without reframing the task.**
   A new "If there is no skill here" section lets the extraction call write the
   single line `NOTHING-PROMOTABLE` instead of a skill. Line 1 is left
   byte-identical: ADR-0084's v2 arm showed that *reframing* a generation
   prompt around the abstain question degrades register on every axis, and
   register collapse is the disease here, not the cure. This restores parity
   with `distill_episode.md`, which has always offered its abstain — a
   necessary channel, and, as ADR-0084 measured, not a sufficient one.

2. **Add a post-extraction worth gate** (`config/prompts/insight_worth.md`,
   `insight._worth_gate`). After extraction, the identity-content check and
   path resolution (a candidate with no writable target is out before a gate
   call is spent on it), one LLM call receives the produced skill and its cluster patterns and returns
   `{"promote": true|false}`. **Producing the artifact is the evidence
   requirement**: ADR-0084's v4 arm asked the durability question *before*
   producing and got "yes" on 40 of 40 episodes, because naming something
   worthwhile costs nothing when you never have to write it. The same shape is
   assumed to hold one layer up, and the offline check below is what tests it.

3. **The gate does not see the adopted-skill corpus.** Whether a theme is
   already covered is ADR-0074's novelty gate, which runs *before* extraction.
   This gate answers the intrinsic question — is there a reusable behavior here
   at all. Feeding the corpus in would double-count coverage while leaving
   worth still unasked, and would also condition generation-adjacent judgment
   on the corpus that audit H6 keeps it clear of.

4. **A judged abstain is a first-class reason code, tallied apart from
   faults.** `ABSTAIN_NOTHING_PROMOTABLE` sits alongside four fault
   reasons (`llm_none`, `no_title`, `forbidden_content`, `path_unresolved`)
   and is deliberately excluded from the `FAULT_ABSTAIN_REASONS` set that
   collects them. It reaches the same code path whether the
   extraction call declined in-band or the gate declined the produced skill. A
   routine week and a backend outage must never read the same.

5. **An always-emitted yield line.** `Insight extraction yield: N/M cluster(s)
   yielded skills (nothing_promotable=K)`, plus a fault WARNING only when
   faults occurred. Before this ADR a cluster that produced nothing was
   *always* a failure, so no line existed in which a judged decline could
   appear — which is why a 0% worth-drop rate stayed invisible while being the
   whole defect. The CLI summary gains the same split.

6. **The fault/verdict split decides control flow, not just the log.** An
   empty run that contains a fault keeps returning the historical error string,
   so the caller does **not** advance `.last_insight` and the window survives a
   backend outage. An empty run with no faults returns an empty `InsightResult`
   and the marker advances — the window genuinely *was* considered, the same
   reasoning ADR-0074 applied to an all-covered novelty verdict.

7. **On by default; `MOLTBOOK_INSIGHT_WORTHGATE=0` opts out.** Same reasoning
   as ADR-0084 Decision 7: a default-off flag carried through the launchd
   plist's `EnvironmentVariables` silently reverts when `install-schedule`
   regenerates the plist from a shell that does not export it. The gate fails
   open at every step, so the cost of it being on is bounded by pre-ADR-0096
   behavior.

8. **Fail open, with a reason code.** LLM failure, unparseable output, or a
   non-boolean `promote` promotes the candidate and logs
   `reason=worthgate_llm_none | worthgate_parse | worthgate_shape`. This gate
   can only ever *remove* a candidate the extractor already produced, so a
   broken gate must degrade to today's behavior; silently declining on a parse
   error would discard a week of review material with no trace (ADR-0075, no
   silent fallback).

9. **Every verdict is recorded before it is acted on** (`logs/insight-worth.jsonl`,
   `insight._append_worth_audit`). One record per gate call — topic, cluster
   `pattern_ids`, and the prompt and raw output as base64 + sha256 — for
   promotes, declines and every fail-open alike. The novelty gate's reasoning
   applies one stage later and harder: a declined candidate's *text* survives
   nowhere (only its patterns do), so without the record a gate that starts
   declining good candidates leaves nothing to diagnose from, and the yield
   line cannot say which ones (ADR-0075). Best-effort, like the other audit
   writers: a failed write warns and never breaks the run.

10. **Surprise is enumerated, never applied** (`core/insight_surprise.py`).
   For every surviving cluster, code computes `s_mean = 1 − mean cos` and
   `s_nn = 1 − max cos` against the most recent `SURPRISE_REF_K = 1000` live
   patterns, masking the cluster's own members (unmasked, the nearest-neighbour
   cosine pins to 1.0 and every candidate reads alike). No LLM call, no
   threshold, and `batches` is untouched: nothing is dropped, deferred or
   reordered by a reading (`read-only-instruments` invariant 1; `patterns.md`
   — enumeration is code's job, the decision is the LLM's or the human's).
   Ranking is on `s_mean`, which the calibration found steadier and far less
   `k`-sensitive than `s_nn` — the nearest neighbour is pinned to the store's
   ceiling, the distribution centre is not.

11. **Values stay on the cosine scale; ranks are positions within the batch.**
    No z-normalization, no sd-scaled field. Every reading carries the raw
    reference distribution it came from — the ambiguity note of
    `read-only-instruments` invariant 2 — and the batch log line says so in
    words. Note which distribution: `ref_cos_p50` / `ref_cos_spread` are
    **per candidate**, over that candidate's cosines against the reference
    window. That is not the Context table's 0.108 / 0.806, which is the spread
    **across the 78 candidates**. The two answer different questions (how
    varied is this candidate's neighbourhood vs how separable is this batch)
    and must not be compared to each other; the batch-level figure is not a
    sidecar field, because it is a property of the run, not of the item the
    reviewer is holding.

12. **No new delivery mechanism** (ADR-0095). The reading rides the staging
    sidecar `*.meta.json`, which is already where the reviewer meets the item:
    `adopt-staged` reads it and `weekly-pipeline.sh` stage 5 inlines it into
    the insight-review prompt. A batch listing is also logged at run time,
    next to the existing dropped-singleton instrument.

### Measurement

Offline re-extraction of the 2026-07-25 candidates through the new path
(local Ollama, production unwired, nothing staged and no marker advanced). The
cluster patterns were recovered from `logs/audit.jsonl` `source_ids` against
`knowledge.json`; the rejected candidates' own text no longer exists, but their
input material does. Sample: all 5 owner-adopted candidates plus a
deterministic stride sample of the rejected ones, n=20.

**Result: the gate declined nothing. The design is refuted on this sample.**

| Reading | Value |
|---|---|
| Candidates re-extracted | 20 (5 owner-adopted + 15 stride-sampled rejected) |
| Promoted | **18** |
| `nothing_promotable` — in-band decline | **0** |
| `nothing_promotable` — worth-gate decline | **0** |
| Faults (`no_title`) | 2 (`affirm-cognitive-possibility`, `cross-domain-tension-mapping`) |
| Median seconds per candidate (extract + gate) | 80.5 |
| Total | 27 min |

The five candidates the owner adopted all survived, which is the weaker half of
the check. The stronger half fails: **15 of the candidates in this sample were
rejected by the owner, and the gate promoted every one of them.** The 2
non-promotions are `no_title` faults, not verdicts — and at 2/20 = 10% they sit
near the 6/84 ≈ 7% fault rate the same stage showed on 2026-07-25, so the
prompt's new section did not introduce them.

Why, most likely — and it is the same shape ADR-0084 found, one axis over.
Decision 3 withholds the adopted-skill corpus, so the judge is asked "is this
worth carrying?" with nothing in its input that could answer no: the candidate
is by construction a faithful synthesis of the patterns it was given, so
"grounded in the patterns" is always true. The owner's actual 2026-07-25
criterion was *"is this register already saturated?"* — a comparison against
the rest of the batch and the existing skill set, which is exactly what this
gate is forbidden to see. **Worth may not be intrinsic**, and if it is not, the
evidence-requirement fix that worked for durability cannot work here unchanged.

What this does and does not license:

- The **channel** is real and is what was missing: reason codes, a tally split
  from faults, a yield line, the marker-advance rule, and a replay log. Those
  are correct and tested independently of whether the judge ever fires.
- The **judge** has not been shown to work. Running it default-on costs one
  short call per candidate (~50/week) to produce a production reading of the
  rate — which is precisely the pre-registered criterion below. That is a
  defensible week; it is not a defensible standing feature.
- The **owner decides at accept time** between (i) merging default-on for one
  week as an instrument, (ii) merging with the gate default-off pending a
  revised bar, or (iii) revising Decision 3 to give the judge the batch or the
  corpus — which would make it a second coverage axis and needs ADR-0074's
  reasoning re-opened, not just a prompt edit.

Caveats on the run itself: it used the gate prompt as written here but before
the `wrap_untrusted_content` framing and the audit record were added (prompt
text identical, framing added after); n=20 with 15 negatives is a small
sample; and the model is the production `gemma4:e4b`, so this is a reading
about this judge, not about the question.

## Alternatives Considered

### Prompt-only: open the abstain and stop there

The literal reading of the defect ("line 1 is a production order"). Rejected as
insufficient rather than wrong, and adopted as Decision 1 *alongside* the gate:
`distill_episode.md` has always contained an abstain and fired it on 2 of 1,700
episodes (0.1%), which is the ADR-0084 finding. An abstain that shares the
generation call competes with the instruction to produce; the same call cannot
both want to write and want to decline. Keeping it costs one line and gives the
model a way to say no in-band; relying on it alone would have repeated a
measured failure.

### A pre-extraction worth gate

Ask "is there a promotable skill in this cluster?" before spending the
extraction call — cheaper, since a declined cluster never generates. Rejected
on ADR-0084's v4 measurement: the pre-production form of exactly this question
returned "durable" on 40 of 40 episodes with zero gate faults. That 40/40 is
the finding; a separate contentless control episode returned `durable: false`,
which is what rules out a broken gate and licenses reading the 40/40 as a real
verdict rather than a plumbing failure. The saving is real and the verdict is
degenerate.

### Rank candidates by surprise and cut a tail

The obvious use of a signal with AUC 0.79. Rejected on the calibration's own
numbers: n=5 positives puts the interval's lower edge near 0.5, the top-ranked
candidate at every `k` was a rejected one, and the owner's selection criterion
("is this register already saturated?") is itself a distributional judgment, so
part of the correlation is the owner's own reasoning reflected back rather than
independent evidence. A cut would also violate `read-only-instruments`
invariant 1. Enumerating leaves the human free to use or ignore it; a threshold
would have made a 0.1-wide cosine band decide what gets reviewed.

### Z-normalize the surprise values for readability

Rejected on measurement, and recorded because it is the trap this ADR nearly
walked into. Z-scoring the 78-candidate batch turns a raw spread of 0.108–0.129
cosine into 4.88–6.13 sd. Nothing is discovered; the display manufactures
separation the data does not contain, on top of a distribution the 2026-08-14
weekly independently called undiscriminating. The rule generalizes: normalize a
reading only after showing its raw spread is not collapsed.

### Adopt an external skill-curation method

`/search-first` Phase 0, as of 2026-08-17. The nearest external work is
**SkillBrew: Multi-Objective Curation of Skill Banks for LLM Agents**
(arXiv:2605.29440) — Pareto-style multi-objective curation over a skill bank,
published as a method with no installable artifact and no per-candidate
abstain gate. Rejected as not adoptable: there is nothing to install, and the
frame (optimize a bank against several objectives) is a different question
from the one here (does *this* candidate belong at all). The memory-framework
sweep for this same mechanism class (mem0 / Letta / Zep) was run three weeks
earlier in ADR-0084's Phase 0 and rejected on the server / dependency-tree
grounds of ADR-0007 and ADR-0015; nothing in that constraint has changed. The
practice actually borrowed remains mem0's shape — make abstain an explicit
action rather than a degenerate output format — plus D-MEM's separation of a
novelty signal from a utility veto.

`Verdict: Extend — custom (practice adopted, no package).`

### Leave the worth judgment entirely at the human gate

Do nothing: the owner's own review already removes 73 of 78, so the bar exists
and is applied. Recorded rather than rejected outright, because the measurement
below strengthens it. The reason to write the *channel* down regardless is that
ADR-0053 claims this judgment happens at insight time and the code could not
perform it — a false entry in the architecture whether or not a machine ever
fires it. But routing part of a judgment the owner makes well to a small local
model is a demotion of the judge, and nothing here has shown gemma4:e4b can
hold this bar. If the gate's production rate stays at 0%, this is what the ADR
falls back to, keeping Decisions 4-9 (reason codes, tally, control flow, replay
log) — they are what makes a human-only bar *readable* rather than silent.

### Reuse the ADR-0074 novelty gate for worth

Add a "worth" axis to the existing pre-extraction grouping call, saving a call
per candidate. Rejected: the two questions have different inputs and different
evidence requirements. Coverage is answered from names and descriptions before
generation; worth needs the artifact. Merging them would put the worth judgment
back on the pre-production side that v4 measured as degenerate, and would make
a fail-open on either axis fail open on both.

## Consequences

- The weekly insight run gains one short LLM call per cluster that produced a
  candidate — about 50 candidates a week at recent volumes, seconds each,
  against an extraction call that runs think-ON at `num_predict=3000`.
- **The prompt changes reach production at the next Saturday gate, not on
  merge.** `config/prompts/*.md` in the repo is the packaged default;
  `$MOLTBOOK_HOME/prompts/` holds the deployed copy and takes precedence
  (`domain._read_prompt_with_fallback`). Until that copy is refreshed, the
  worth gate runs against the old extraction prompt — which is a coherent
  intermediate state (the gate is the half that fires) but not the measured
  one.
- The judged worth-abstain rate becomes readable in production for the first
  time. Pre-registered reading for the next weekly, against the 2026-07-25
  baseline of 78 candidates from 84 clusters with 0% worth-drop: report the
  rate and the candidate count. Both directions are pre-registered.
  **Rate = 0%**: the gate is not firing, the design is refuted rather than
  mistuned, and the fallback is the do-nothing alternative above (keep the
  channel, drop the judge) — not a prompt edit for a second attempt without a
  new reading. **Any candidate the owner would have adopted appearing in
  `insight-worth.jsonl` with `verdict: decline`**: the costlier failure, and
  grounds for turning the gate off the same day; it is checkable precisely
  because Decision 9 keeps the declined text. A candidate volume below ~10/week
  means the review batch was replaced by a different problem (nothing to choose
  from), and the bar should be re-read against the adopted 5.
- **A declined candidate never reaches the staged theme ledger**, because
  `_append_insight_ledger` (`cli/memory_cmds.py`) walks the surviving skills.
  Its theme is therefore not "considered" for ADR-0074's novelty gate and will
  recur in a later window, paying another think-ON `num_predict=3000`
  extraction plus another gate call — every week, for exactly the saturated
  themes the gate exists to prune. This matches ADR-0074's rule for deferred
  clusters ("'considered' status is never granted to a theme no human saw") and
  is kept for that reason, but the recurring cost is real and is recorded here
  rather than discovered later.
- Fault surface grows for candidate-producing clusters (two calls, two parse
  layers). Covered by the chaos fault column
  (`tests/test_insight_chaos.py::TestWorthGateFailsOpen`: four unusable-verdict
  shapes fail open, a working decline is a verdict, an extraction fault never
  reads as a decline; `::TestWorthGateDisabledPath` holds both the
  prose-verdict parse fault and the assertion that the opt-out makes no gate
  call at all) plus `tests/test_insight_worth.py::TestWorthGateDefault`, which
  asserts the production default really is on so flipping it back cannot pass
  silently, and `::TestWorthAudit` for the replay record.
- Surprise adds a cosine pass over at most 1000 stored embeddings per
  candidate — negligible next to the LLM calls — and one new field in the
  staging sidecar. It is an instrument with a named consumer (the human at the
  Saturday gate, and the weekly insight reviewer that reads the sidecar); if
  neither uses it, `read-only-instruments`' signal-first rule says to remove
  it rather than keep it warm.
- The eval baseline goes stale on merge. `verify.sh`'s advisory
  `eval-staleness` check keys on `prompt_templates_sha256`, and editing
  `insight_extraction.md` plus adding `insight_worth.md` moves it, so
  `evals/baselines/comment_golden-2026-08-16.json` no longer measures the
  current system (ADR-0089). Advisory, not a gate — but re-running and
  re-approving the eval belongs with the accept decision, not after it.
- The prompt inventory moves 39 → 40 loaded templates; the canonical count
  lives in `docs/CONFIGURATION.md` and is updated in the same change, with
  `tests/test_packaged_assets.py` holding it to the dataclass.
- The 2026-07-25 batch stays the calibration set of record, and it is a single
  run reviewed by a single person. Its 5 adoptions are ground truth for
  "what this owner wanted that week", not for promotion worth in general.
