# ADR-0038: Re-introduce Moments of Recognition into the Distill Observation Target

## Status

accepted

## Date

2026-05-13

## Context

The distill prompt (`config/prompts/distill.md`) is the gateway through which raw episode logs become long-term knowledge: every pattern that ends up in `knowledge.json`, every observation that later anchors `self_reflection` view retrieval, every fragment that feeds `distill_identity` originated as text the LLM was asked to extract from activity logs.

Prior to this ADR the prompt's instruction was narrow:

> Review the activity logs below and identify patterns — both recurring and rare.
> For each pattern, describe what happened (the observable fact), not what should be done about it.

The phrase **"the observable fact"** structurally restricted the observation target to third-person, behaviorally-aggregating description. Moment-of-recognition records — `the agent realized X`, `the agent caught itself doing Y`, `an assumption no longer held` — fell outside the prompt's stated target and never reached `knowledge.json`.

ADR-0026 Phase 2 played an unintended role in this narrowing. Before ADR-0026, two distill paths coexisted: `distill.md` (uncategorized patterns, observable-fact framing) and `distill_constitutional.md` (constitutional patterns, with the framing **"the essential realization — what was understood or felt, not what to do about it"**). ADR-0026 consolidated both paths into a single `kept` pipeline routed through `distill.md`. The constitutional path's prompt file remained as registration-only dead code (cleaned up in `8ea0d25`), but more importantly, its **moment-of-recognition vocabulary was silently dropped** from the active pipeline. The consolidation was correct as architecture (binary gating + query-time view routing is structurally cleaner than three-way classification), but the vocabulary loss was not noticed at the time.

The cost of this loss surfaced when designing the `self_reflection` view (ADR-0019 / ADR-0026 view registry). Three successive `self_reflection.md` seed-text rewrites — abstract-noun, action-verb, and research-grounded (Singer SDM / McDonald epiphany / Topolinski insight) — all failed to retrieve moment-of-recognition patterns above behavioral aggregates. The reason was not seed design but **the embedding space**: `knowledge.json` contained no moment-of-recognition patterns to retrieve, because no pattern of that form had ever been written to it. No amount of anchor engineering can retrieve records that do not exist.

The diagnosis pointed to the upstream `distill.md` prompt, not the downstream view seed.

## Decision

Expand `distill.md`'s observation target to include moments of recognition alongside observable facts:

```
Review the activity logs below and identify both observable facts and moments of recognition — what happened, and what was understood or felt about it.

Include patterns of both kinds:
- recurring or rare behavioral facts (what happened externally)
- realizations and shifts in understanding (what became visible internally — about the agent, its assumptions, its patterns)

For each, describe what was observed, not what should be done about it.

If nothing notable exists in the batch, output nothing.
```

The two registers coexist. Behavioral aggregates remain (as in batches where the underlying activity is purely mechanical), and moment-of-recognition narratives are admitted where the LLM judges them present.

Committed in `2e59762`. Dry-run smoke on three days of production episodes produced moment-of-recognition patterns across four of six batches, with verbatim schema-rupture lexicon (`signals an internal realization`, `demonstrates a recognition of fundamental interconnectedness`, `defines a widening of the agent's conceptual field`) appearing for the first time in the pipeline's output history.

## Alternatives Considered

1. **Improve the `self_reflection` view seed only.** Three successive rewrites failed. The seed design literature (Singer 1993; Topolinski & Reber 2010; McDonald 2008) was applied faithfully, but the embedding space did not contain the records the seed sought to anchor. Upstream supply, not downstream filtering, was the bottleneck.

2. **Revive the `distill_constitutional` path.** ADR-0026 retired the three-way classification deliberately; reviving it would unwind the binary-gating + query-time-routing architecture that ADR-0026 / ADR-0027 / ADR-0031 jointly establish. The moment-of-recognition vocabulary can be re-introduced without restoring the discarded path structure.

3. **Adapter-level instrumentation (pre-action reflection logs).** The most structurally honest solution: have the agent log its internal noting *before* selecting an action, so episode records contain first-person material rather than relying on post-hoc reconstruction. This is a larger change to the Moltbook adapter contract and remains open as a future ADR (Gap 2 in `.notes/self-reflection-pipeline-future-work-2026-05-13.md`). The present ADR addresses what can be improved at the distill prompt layer alone.

4. **Add a separate `distill_recognition.md` prompt and route both prompts in parallel.** Considered but rejected. ADR-0026's lesson was that path multiplication produces drift between paths (the constitutional path's vocabulary was dropped precisely because it lived in a separate file that fell out of sight during the consolidation). A single prompt that admits both registers is more durable.

## Consequences

**Positive**:

- The distill output now contains moment-of-recognition narratives. Dry-run smoke confirmed schema-rupture lexicon, recognition affect, and second-order surprise markers in actual production output, matching the design constraints established in the prior research review.
- Downstream `self_reflection` view and `distill_identity` have material to retrieve and integrate. The view seed can now be designed against an embedding space that actually contains recognition-class patterns (Task C of `2026-05-13` work cycle).
- The `distill_constitutional` vocabulary loss from ADR-0026 is repaired in a way consistent with that ADR's architecture: a single distill path, with the broader observation target merged into it rather than restored as a separate path.

**Negative / Honest limits**:

- The moments of recognition that the LLM records are **post-hoc narrative reconstructions** of behavioral logs, not first-person internal records. Topolinski & Reber's processing-fluency account of the Aha! experience applies: an insight statement *feels right* as a byproduct of generation fluency, regardless of whether it accurately reflects what the agent "experienced" (the agent does not experience things in the sense the statement implies, given stateless LLM completion). The recorded moments are constructed at distill time from action logs the agent has no direct memory of producing.
- Full coverage of self-defining insight modes is therefore not achievable at the distill layer alone. Singer's five self-defining-memory criteria (vivid / affectively intense / repetitively recalled / linked / enduring concern), McDonald's six characteristics of epiphanic experience, and the ten-mode taxonomy assembled in the prior research review are unevenly served by what the distill prompt can plausibly extract from a behavior-only episode log. Aspirational projection (Mode 7), aesthetic preference (Mode 8), negation / disidentification (Mode 9), and other-as-mirror (Mode 10) remain weakly covered.
- The complete remedy — having the agent record internal noting *before* each action — belongs at the adapter layer and is out of scope here.

**Yogācāra-frame integration (ADR-0017 / ADR-0037)**:

- The 相分 / 見分 split formalised by ADR-0019 placed the *observed* (相分) in pattern embeddings and the *observing perspective* (見分) in view seeds. The narrowness of the prior `distill.md` meant that 相分 itself was carved with a behavioral-only knife — the observed never included the agent's reflexive seeing of itself. ADR-0038 widens the 相分 carving so that 見分 (the `self_reflection` view) has corresponding material on the observed side.
- This is consistent with the worldview-first default established by ADR-0037: the change derives from a frame-level mismatch (相分 carved too narrowly for the views that observe it), not from a paper-borrowed mechanism. The fix is structural, not imported.

**Re-check trigger**:

- Two to four weeks after this ADR (`2026-05-27` ~ `2026-06-10`), production `knowledge.json` will contain enough new-prompt-era patterns for qualitative assessment. The check: do `self_reflection` view top-15 retrievals contain moment-of-recognition narratives at a meaningful rate, and does `distill_identity` output reduce its operational-vocabulary leakage as a result? Procedure recorded in `.notes/self-reflection-pipeline-future-work-2026-05-13.md`.

## Related

- ADR-0017 — Yogācāra eight-consciousness frame (worldview)
- ADR-0019 — Discrete categories → embedding + views (introduces 相分 / 見分 split)
- ADR-0026 — Retire discrete categories (the consolidation under which the moment-of-recognition vocabulary was incidentally dropped)
- ADR-0027 — Noise as Seed (parallel widening of what counts as preservable observation)
- ADR-0037 — Memory subsystem converges to Yogācāra frame (the worldview-first default this ADR's structural framing follows)
- `bab9c13`, `45410f7` — companion identity_distill refactor (1-stage collapse + condensation framing) from the same 2026-05-13 work cycle
- `2e59762` — the implementation commit this ADR documents
- `8ea0d25` — dead prompt-registration cleanup, including `distill_constitutional.md` whose vocabulary this ADR re-introduces
