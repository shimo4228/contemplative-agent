# ADR-0072: Echo-Chamber Interventions — Register Instruction, Corpus-Grown Seed, Extraction-Failure Guard

## Status

accepted

## Date

2026-07-03

## Context

[ADR-0071](./0071-read-only-pattern-composition-instruments.md), landed earlier the
same day, measured a fixed `--days 2` dry-run window (UTC 2026-07-02/03, 63
engagement episodes, 3 runs) with its new read-only instruments. The fresh-batch
pairwise cosine mean held at 0.60 across all three runs — the most robust of the
instruments — against a corpus pairwise mean of 0.554 and an unrelated-text floor of
0.33–0.46. The signal reads as an echo chamber forming *now*, and forming worse than
the historical pool it feeds.

The `self_reflection` view ([ADR-0019](./0019-discrete-categories-to-embedding-views.md))
— the only consumer of the distilled corpus that feeds `distill-identity` — showed
its pass threshold (0.55) sitting exactly at the corpus homogeneity floor (p50 =
0.554), passing 76% of 1,463 patterns; `top_k=50` was doing all the real selection,
not the threshold. A qualitative classification of the view's top 30 patterns
(labeled §B3 in the cycle's working notes) found only 8/30 in a first-person,
moment-of-recognition register against 21/30 in a third-person analytical register
("The agent identifies…"). This located the echo's substance: not vocabulary
repetition, but a distillation *register* — the grammatical person and narrative
stance the LLM defaults to when writing a pattern.

Two secondary findings sharpened the intervention scope. One extraction-failure
artifact — text describing the model's inability to find a pattern, rather than an
observation about the world — had itself been stored as a pattern, ranked 16th in the
`self_reflection` view. And the grounding instrument added in ADR-0071 (M2) read
`source_type = 100% self_reflection` on every fresh batch, a constant with no
variance across runs — a signal-first violation, since a reading that never changes
is an instrument whose output changes no action.

This is not the first attempt at the seed side of the problem: three seed redesigns
in May 2026 failed before the upstream distill prompt itself was fixed, because the
register material a redesigned seed would need to select for did not yet exist in the
corpus. The standing branch condition from that history — redesign the seed only once
stable recognition-register generation is confirmed — was satisfied by the §B3
classification above.

The live distillation prompt is `config/prompts/distill_episode.md`
([ADR-0060](./0060-per-episode-grounded-distill.md)). The pre-ADR-0060 batch prompts,
`distill.md` and `distill_refine.md`, have had zero consumers since that ADR shipped,
but both files and their `PromptTemplates` loader mappings remained live in the tree
— dead files with live wiring.

At the 2026-07-03 checkpoint the operator scoped the work: implement interventions 1
(seed and threshold), 2 (register instruction), and 6 (failure guard); delete the M2
grounding instrument rather than repair it; delete the dead batch-distill prompts
alongside it. Singleton rescue (§A1) is deferred — its premise is shaken, because
importance has been pure decay since
[ADR-0056](./0056-retire-importance-llm-scoring.md), so an importance floor would only
mean "rescue the newest," when the real defect is that singletons never re-enter
clustering; that is a re-cluster-lane redesign for a future cycle. Orphan-view
disposition and longitudinal instrument wiring, both flagged as follow-ups in
ADR-0071, are deferred as well.

## Decision

Ship three interventions against the echo-chamber baseline ADR-0071 measured, plus a
fourth item that deletes scaffolding the investigation showed was no longer earning
its keep.

1. **Add a register instruction to `distill_episode.md` — the upstream fix.** The
   prompt text was drafted by `gemma4:e4b` itself, following the standing discipline
   that the model executing a prompt writes it. Two additions, kept to one concept —
   register:
   - A new paragraph instructing the model to write patterns "in a first-person,
     moment-indexed register," naming "the concrete moment where the recognition
     happened — what was noticed, when it became visible, and what that observation
     revealed about the agent's internal process or interaction."
   - An extension to the empty-list clause: the model must "not generate patterns
     describing the lack of context or generalizable material in the episode."

   Gap-1 modes (aspirational / aesthetic / negation) were deliberately left out of
   this change — May 2026's lesson was that wording expansions overshoot. A new
   regression test pins `DISTILL_EPISODE_PROMPT.format(episode="x")` to not raise: a
   single unescaped brace in this paragraph would `KeyError` and take down the entire
   distill run at `distill.py:517`.

2. **Add an extraction-failure guard to `_is_valid_pattern` in `distill.py` — the
   backstop.** A conservative, multi-word, task-referential phrase list
   (`_EXTRACTION_FAILURE_PHRASES`) rejects any candidate pattern whose text narrates
   the extraction task itself rather than an observation about the world. The list
   shipped with 8 phrases: "events appear isolated", "the episode does not contain",
   "the episode lacks", "the episodes lack", "unable to extract a pattern", "cannot
   extract a pattern", "no generalizable pattern", "nothing generalizable". Two
   phrase categories from the initial draft — bare context phrases ("lack sufficient
   context", "insufficient context to") and "identify a pattern" variants — were
   removed after codex-review flagged them as false-positive risks: a genuine
   first-person recognition can legitimately use that wording ("I noticed I lack
   sufficient context before making a claim"), and that case is now a TDD negative
   test. Matching is `lower()` containment; single words like "isolated" are excluded
   to protect genuine self-observations under the same TDD discipline. Rejects are
   logged at `INFO` with the matched phrase and a 60-character excerpt. This is a
   validity check for malformed task narration, not a value filter — no branch in the
   guard judges content quality. The sanctioned failure signal remains the empty
   list; the guard only catches what escapes it, and the prompt clause in item 1 is
   the actual source-side fix.

3. **Grow the `self_reflection` view seed with an appendix, and recalibrate its
   threshold — a data-only change.** The design changed from replacing the seed to
   appending 4 A-register exemplars to the existing abstract register-description
   text, after a plan-critique found that a verbatim-exemplars-only seed risks topic
   capture (`nomic-embed-text` is content-word dominated); the appendix keeps the
   register-description signal, and rollback is a one-line deletion of the appendix.
   The 4 exemplars were chosen from the §B3 A-group for maximal topic spread:
   reasoning-order (justification forms downstream of a choice), belief-formation (an
   execution log revealing a defended-but-unexamined framing), motivational
   hesitation (oscillating between validation-seeking and exploration), and felt
   mirror-experience (dissolution of boundaries while reading a text).

   Calibration was run fresh rather than carried over — the old 0.33–0.52 control
   floor belonged to the old seed's embedding geometry, not the new one. The
   candidate seed was embedded and its full cosine distribution computed over the
   1,463 live patterns plus 3 fresh off-topic controls (paris/recipe/tcp:
   0.398–0.456). A control run with the *current* (pre-change) seed reproduced the
   ADR-0071 baseline exactly (1108/1463 pass @0.55, p50 0.580, p90 0.641, max 0.770),
   confirming method parity between the two calibration runs.

   The threshold rule was: the highest value that decisively excludes the new
   control floor and still keeps the pass count at or above 3×`top_k` (150). The
   distribution gave @0.64 = 338, @0.66 = 193, @0.68 = 88; **0.66** was chosen (193
   passing = 13.2%, down from 76% pre-change; floor margin +0.20 over the new
   controls).

   The change was applied to the live `~/.config/moltbook/views/self_reflection.md`
   (backed up to `~/.config/moltbook/self_reflection.md.bak.20260703-preADR0072`,
   following the 2026-05-25 backup precedent) and to the repo template
   `config/views/self_reflection.md` in the same change, keeping the two in sync.
   Byte-equivalence was verified by reloading the view registry and reproducing
   `passing=193`.

4. **Delete scaffolding that no longer earns its keep (AKC Curate).**
   - The M2 grounding instrument added in ADR-0071 — `compute_grounding`,
     `format_grounding`, `GroundingComposition`, its wiring, and its tests — is
     removed outright rather than repaired. Under per-episode distill
     ([ADR-0060](./0060-per-episode-grounded-distill.md)), `_derive_source_type` maps
     the record's *type* (post/activity → self), and the adapter renders external
     content *inside* activity episodes rather than as separate `external_reply`
     records, so `external_reply` is structurally near-impossible to produce. The
     instrument was reading a constant — a signal-first violation. What it depends on
     is kept: `provenance.source_type` (data), `epistemic_counts_for` (the
     `knowledge_store` /
     [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) identity-approval
     wiring), and `_derive_source_type` itself (the write-time origin record) all
     survive; only the read-time instrument built on top of them is deleted. The
     one-time baseline finding it produced — grounding fully inward,
     `external_reply=0` — is preserved in the cycle notes and in this ADR rather than
     in a live instrument.
   - The dead batch-distill prompts, `config/prompts/distill.md` and
     `distill_refine.md`, are deleted along with the `PromptTemplates.distill` /
     `.distill_refine` fields and loader lines (`domain.py`) and the `DISTILL_PROMPT`
     / `DISTILL_REFINE_PROMPT` mappings (`prompts.py`). The vestigial
     `_parse_refined_patterns` is renamed `_parse_patterns`. Test fixtures that had
     used `distill.md` as their home-directory-override vehicle were moved to
     `distill_episode.md`.
   - The deletion extends to the `evals/` promptfoo harness (step1/step2 configs,
     `distill_prompts.py`, asserts, fixtures, the c1/c2 experiment YAMLs, and its
     README): codex-review found the harness's prompt module imports
     `DISTILL_PROMPT`/`DISTILL_REFINE_PROMPT` directly, which would `ImportError` the
     moment those mappings were removed, and that the whole suite regression-tested
     the ADR-0060-retired batch pipeline under pre-[ADR-0058](./0058-value-injection-at-action-time.md)
     axiom injection — it was dead scaffolding testing a pipeline that no longer
     runs. The §C1 axiom-ablation experiment idea the harness once served survives as
     a tracked pending item, to be rebuilt against `distill_episode` when that
     experiment actually runs.

## Alternatives Considered

### Repair the M2 grounding instrument instead of deleting it

An `external_fields_present` read-time aggregation, or a persisted field, was the
correct design direction in isolation — but no current decision consumes the
reading. Building it now would front-run a need that does not exist (signal-first).
The sketch is preserved in this ADR's Decision rather than as a live instrument;
build it when a consumer does.

### Replace the view seed with exemplars only

Dropping the existing abstract register-description text and keeping only the 4
exemplars was rejected: `nomic-embed-text` is content-word dominated, so an
exemplars-only seed risks topic capture — selecting on what the exemplars are *about*
rather than their register. It also loses the register-description signal entirely,
and rollback would mean restoring lost seed text rather than deleting an appendix.

### A stricter threshold (0.68 or above)

Rejected: at 0.68 only 88 patterns pass, below 3×`top_k` (150) — the view would
starve its consumer the first time the corpus distribution drifted.

### Add the remaining Gap-1 modes (aspirational, aesthetic, negation) to the prompt in the same change

Rejected: bundling additional register modes into this change risks the same
overshoot that May 2026's earlier wording expansions produced. One concept —
register — per change.

### An LLM judge for the extraction-failure guard

Rejected: the failure register is stereotyped enough for a conservative phrase list
to catch reliably, and a judge would add stochasticity to what is a validity gate,
not a content-quality decision (`when-code-when-llm`: enumerate structurally, decide
semantically only when needed).

## Consequences

Post-change dry-runs reused the exact fixed window ADR-0071's baseline used —
`--days 2`, UTC 2026-07-02/03, 63 rich episodes, episode-count parity checked before
and after each run. All figures below are dry-run reads (nothing was actually
invalidated). Readings, one row per run:

| Run | Found | Skipped | Soft-invalidate | Pairwise mean (p50 / p90) | Supply `self_reflection` | Supply `constitutional` |
|---|---|---|---|---|---|---|
| Baseline (3 runs, pre-change) | 133–142 | — | 24–31 | 0.60 (×3 runs) | — | — |
| Post-change run 1 | 144 | 2 | 6 | 0.60 (p50 0.60, p90 0.67) | 31/142 = 22% @0.66 (p50 0.63, p90 0.68, max 0.76) | 132/142 = 93% @0.55 |
| Post-change run 2 | 140 | 2 | 5 | 0.60 (p50 0.60, p90 0.66) | 28/138 = 20% @0.66 (p50 0.62, p90 0.68, max 0.76) | 131/138 = 95% @0.55 |
| Post-change run 3 | 132 | 2 | 9 | 0.60 (p50 0.60, p90 0.66) | 27/130 = 21% @0.66 (p50 0.62, p90 0.68, max 0.74) | 127/130 = 98% @0.55 |

The readings below are co-primary — no single metric drives a revert decision on its
own.

### Positive

- **Register shift confirmed qualitatively.** New patterns read "When I read '…', I
  noticed …" — first-person, moment-indexed, quote-anchored — replacing the
  third-person "The agent identifies …" register the §B3 classification found in
  21/30 of the pre-change top-30.
- **The soft-invalidate collapse (24–31 → 5–9 across the three runs) corroborates the shift.** New-register
  patterns diverge from the legacy third-person pool, producing fewer 0.80–0.90
  near-duplicate matches — an independent, dedup-derived signal pointing the same
  direction as the qualitative read.
- **The compounding mechanism — the corpus-grown seed and threshold recalibration —
  is confirmed.** New-batch supply against the recalibrated `self_reflection` view is
  22%, above the corpus's 13.2%, and the new batch's max cosine (0.76) reaches into
  the seed's own exemplar band (0.73–0.81): patterns produced under the new prompt
  rank into the view's top band, so the A-register share of `distill-identity`'s
  input grows going forward even though the existing corpus cannot be rewritten.
- **Net removal, not addition, of scaffolding.** The dead batch prompts, their loader
  wiring, the M2 grounding instrument, and the entire `evals/` promptfoo harness are
  all deleted in the same change — each was either unconsumed or reading a constant.
- **The seed change is data-only and independently verifiable.** Byte-equivalence
  between the live view file and the repo template was confirmed by reloading the
  registry and reproducing `passing=193`; security-reviewer separately confirmed the
  appendix adds no new prompt-injection surface, since the exemplars are
  embedding-only and never reach `generate()`.

### Negative

- **The register axis rotated rather than diversified.** Pairwise cosine mean is
  unchanged at 0.60 post-change; a new uniform scaffold ("When X, I noticed Y")
  appears to be forming in its place. Recorded as a next observation target rather
  than a failure of this change's own goal — the goal of the register instruction was
  register, not embedding diversity — but the echo-chamber signal itself is not yet
  resolved.
- **The immediate top-30 composition is honestly flat.** The 4 appended exemplars
  occupy ranks 1/2/4/14 by construction (excluded from the composition count); the
  remaining 26 items' A/B/C/D mix is roughly unchanged (~2–3 A-register items),
  because the corpus holds only ~6 A-register items in total. Re-seeding reorders
  existing material; it cannot manufacture material that was never distilled.
- **The legacy extraction-failure artifact is still live in the view, at rank 23.**
  No manual soft-invalidate lever exists to remove it retroactively; it will decay or
  be superseded naturally, and the new guard only prevents future recurrences, not
  this one.
- **Guard firings were zero in all measured runs**, and the one reject observed was
  an unrelated length reject. Zero firings are ambiguous between "the upstream prompt
  clause is working" and "no failure episodes happened to occur in this window" — the
  guard's unit tests, not production firing counts, remain its primary verification.
- **The 4 seed exemplars hold quasi-permanent top seats in `distill-identity`'s
  top-50 input.** They were already in the top-30 before this change, so no new
  material entered the pipeline, but their rank is now pinned by construction.
  Flagged as an ossification risk: if the same four exemplars still dominate after
  several weeks, the seed needs revisiting.

### Neutral / Follow-ups

- `distill-identity`'s input register will shift gradually as new first-person
  patterns accumulate under the recalibrated view; its output remains
  owner-approval-gated ([ADR-0012](./0012-human-approval-gate.md)), so the first
  post-change identity revision is human-checked regardless of the shift's direction.
- Longitudinal notes for future readings: `self_reflection` supply-passing
  percentage is not comparable across the threshold change (0.55 → 0.66) — a lower
  pass rate reflects the new threshold, not corpus shrinkage; and `insight`'s
  dropped-singleton `nearest_view` cosines are discontinuous starting 2026-07-03,
  since the seed geometry changed.
- Rollback is independent per intervention: the prompt paragraph, the seed appendix
  plus threshold, and the guard's phrase tuple each revert on their own; the three
  deletions revert by `git revert`.
- Singleton rescue (§A1), orphan-view disposition, and longitudinal instrument wiring
  remain deferred, as scoped in Context.
- Reviews: security-reviewer PASS (3 informational LOWs — the known lower/replace
  bypass class is inapplicable to a detect-and-reject single-step filter; the
  reject-log excerpt matches the pre-existing logging convention; seed exemplars are
  embedding-only and never reach `generate()`); python-reviewer MEDIUM, all 4
  findings fixed pre-merge (a stale `distill()` docstring, stale `--patterns` help
  text, a dead `_pat` source_type param, and the "insufficient context to" phrase the
  codex narrowing had already removed); codex-review MEDIUM, all findings fixed (a P2
  `evals` `ImportError` resolved by deleting the dead harness, a P2 phrase
  false-positive fixed with a TDD negative case, and a P3 missing-ADR finding
  resolved by this document).
- Operational: the production launchd schedule was stopped for the duration of the
  work (user-approved, the same Step 0 discipline as
  [ADR-0071](./0071-read-only-pattern-composition-instruments.md)) and restored
  after.

## References

- [ADR-0071](./0071-read-only-pattern-composition-instruments.md) — read-only
  instruments and the same-day baseline this ADR's interventions were chosen from
- [ADR-0060](./0060-per-episode-grounded-distill.md) — per-episode grounded distill;
  `distill_episode.md` is the prompt this ADR extends
- [ADR-0058](./0058-value-injection-at-action-time.md) — axiom-free distillation; the
  deleted evals harness regression-tested pre-ADR-0058 axiom injection
- [ADR-0056](./0056-retire-importance-llm-scoring.md) — importance as pure decay;
  shakes the premise of an importance-floor singleton rescue
- [ADR-0052](./0052-retire-session-insight.md) — session insight retirement
- [ADR-0051](./0051-retire-trust-weighting.md) — prior rejection of metric write-back
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — epistemic tally
  wiring the M2 deletion keeps
- [ADR-0031](./0031-classification-as-query.md) — classification/threshold at query
  time
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — the views layer
  whose `self_reflection` seed and threshold this ADR recalibrates
- [ADR-0012](./0012-human-approval-gate.md) — owner-approval gate on identity
  revisions
- AKC ADR-0015 — Decision 2, visibility without intervention
  (github.com/shimo4228/agent-knowledge-cycle)
- AKC ADR-0016 — a systematically biased instrument is worse than none
  (github.com/shimo4228/agent-knowledge-cycle)
