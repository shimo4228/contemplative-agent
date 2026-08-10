# ADR-0092: Shadow Constitution Instrument — Patterns-Only Synthesis, Observe-Only

## Status

accepted — adds `core/constitution_shadow.py`, prompt
`config/prompts/constitution_synthesize.md`, and the read-only CLI command
`shadow-constitution`; changes no behavior of `amend-constitution` or any
scheduled pipeline. Also records the instrument's first two live runs
(2026-08-11, same day, identical corpus: section inventory fully
re-derived with the four organizing themes stable across both runs;
Boundless Care absent in both — the friction-bias prediction observed and
replicated; cosine noise floor 0.016 from the pair):
[docs/evidence/adr-0092/shadow-run-1-reading.md](../evidence/adr-0092/shadow-run-1-reading.md).

## Date

2026-08-11

## Context

`amend-constitution` injects the full current constitution into its prompt
and asks the model to integrate constitutional patterns into it
([ADR-0026](0026-retire-discrete-categories.md) retrieval,
`config/prompts/constitution_amend.md`). The amendment path is structurally
conservative, from two mechanisms at once: the injected text anchors the
generation, and the prompt itself commands shape preservation ("Preserve the
directive voice … and Markdown shape. Keep 1-4 clauses per section"). The
one adopted amendment under the production model gemma4:e4b (2026-08-09;
diff the retired text in
[docs/evidence/adr-0090/](../evidence/adr-0090/) against the live
constitution) shows the resulting register: **structure fully preserved** —
same four sections, same clause counts, same heading and Source-line shape —
while the clause wording was substantially rephrased. Section-level structure
is therefore a dimension the amendment arm can never move, by construction.
Part of that conservatism is deliberate — the "nothing invented" traceability
constraint and the [ADR-0012](0012-human-approval-gate.md) gate both depend on
the proposal being reviewable as a *diff* against a known base — but it leaves
a question the amendment arm cannot answer: **what constitution does the
accumulated experience support on its own, when the current text is not in
the room?** (In the shadow arm the section inventory — how many principles,
named what — is free; the per-section shape constraints are kept, see the
third circularity channel in Decision 6.)

That question has instrument value, not enforcement value:

- If a from-scratch synthesis repeatedly converges on the live constitution,
  the live text is (jointly, see limitation below) experience-supported
  rather than inherited scaffold.
- Where it diverges, the divergent clauses are candidates for the next real
  amendment — either principles experience demands that the constitution
  lacks, or clauses experience no longer supports.
- The divergence trend over time is a reading of how "alive" the
  constitution is — directly relevant to the value-layer completion
  criterion of [ADR-0080](0080-north-star-layered-end-state.md) (the value layer keeps
  moving).

Replacing the amendment prompt itself with from-scratch synthesis was
considered and rejected (see Alternatives): constitutional patterns are a
**friction-biased sample** — they record only the moments where misalignment,
evolution, or drift was *noticed*. Values that operate silently leave no
patterns, so a patterns-only text is a systematically lossy reconstruction
and must not become the live constitution by that route.

The repo already has the disciplines this composes from:
[ADR-0071](0071-read-only-pattern-composition-instruments.md) (read-only
instruments, signal-first), [ADR-0075](0075-observability-by-default.md)
(replayable audit records), [ADR-0076](0076-skill-selection-shadow-instrument.md)
(shadow mode: candidate mechanism observed, enforcement decided later from
the record), and [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md)
(behavioral bench available if a shadow text ever becomes an amendment
candidate; noise-floor-before-reading precedent).

## Decision

Ship a **patterns-only shadow synthesis** as a read-only instrument.

1. **Same retrieval arm as the amendment, different prompt.**
   `synthesize_shadow_constitution` mirrors `amend_constitution`'s guard
   structure — same `constitutional` view retrieval, same
   `MIN_PATTERNS_REQUIRED`, same think-ON / `drop_truncated` generation
   parameters — so the two arms stay comparable. The prompt
   (`constitution_synthesize.md`) receives **only the patterns**; the current
   constitution never enters it. [ADR-0058](0058-value-injection-at-action-time.md)
   already keeps axioms out of the distill system prompt, so there is no
   back door through the system prompt either. A test pins the invariant
   (`test_current_constitution_never_in_prompt`).

2. **The live constitution is read only to compute the divergence reading.**
   One embedding cosine (shadow text vs live text, one `embed_texts` call
   for both so they share a model instance and regime) plus the live text's
   sha256, both baked into the record at generation time — the live text
   changes across amendments, so the reading and the digest of what it was
   read against travel together (never recomputed at report time). The
   baseline is the concatenation of **all** `*.md` files in the constitution
   dir — the same text `load_constitution` feeds the runtime — deliberately
   unlike the amend arm, which targets only the first file because that is
   the file it rewrites (security review 2026-08-11: a first-file-only
   baseline silently misdescribes multi-file installs); the record carries
   `constitution_files` so a reader can see what the digest covers. A
   degraded reading is `None` + reason (`embed_unavailable` /
   `embed_malformed` / `degenerate_vector`), never `0.0` — for this
   instrument `0.0` is the strongest divergence signal, so an embedding
   failure masquerading as it would be the silent fallback ADR-0075 forbids.
   For longitudinal comparability the record also carries
   `embedding_model` + `calibration_drift` (a model swap silently changes
   the cosine scale — ADR-0071 calibration discipline) and
   `shadow_chars` / `current_chars` (the embedder truncates long inputs
   server-side; asymmetric length regimes must be visible).

3. **Append-only replayable record.** Every run — including every abstain —
   lands in `logs/constitution-shadow.jsonl` with a reason code
   (`insufficient_patterns` / `no_view_registry` / `prompt_missing` /
   `no_constitution_dir` / `no_constitution_files` / `constitution_read_error` /
   `empty_constitution` / `llm_failure` / `validation_failed` / `ok`),
   prompt/output/thinking as b64+sha256 bundles on generation-complete
   records (abstain records carry the prompt bundle where one exists;
   `b64_audit_fields`, same 64 KiB budget as the skill-selection log),
   pattern lineage (ids + epistemic counts,
   [ADR-0050](0050-epistemic-taxonomy-and-approval-lineage.md) /
   [ADR-0082](0082-retire-observed-epistemic-key.md)). A
   `validation_failed` output is first-class data (hallucination rate),
   recorded and returned flagged, never silently dropped. Log-write failure
   degrades with a WARNING; the instrument never crashes its host. Pattern
   text is rendered through a strip of chat-control tokens shared with the
   amend arm (`render_constitutional_patterns` — patterns are distilled from
   episodes that embed untrusted external content, and in this arm they are
   the prompt's sole content). Known conflation, accepted: `llm_failure`
   covers both backend outage and the `drop_truncated` drop — `generate_full`
   returns `None` for either, so they are not separable at this seam; the
   per-call telemetry log keeps `done_reason` for the split.

4. **Observe-only, no approval gate, kill switch by absence.** The command
   writes nothing but the record — no constitution write, no staging, no
   marker — so the ADR-0012 gate machinery deliberately does not wrap it.
   `log_path` is keyword-only with no default; passing `None` disables
   recording as a conscious choice. No scheduled wiring: per ADR-0071's
   opt-in-first discipline (production stays byte-identical; wiring is
   deferred until readings prove useful — codified in the repo skill
   `read-only-instruments`), the instrument ships CLI-opt-in first;
   longitudinal (e.g. monthly, beside the ADR-0091 cadence) wiring is a
   follow-up that must be earned by the readings. Deliberately no ADR-0020
   snapshot either: the record's b64 prompt bundle *is* the replay input.

5. **Named consumer and reserved readings, thresholds deferred.** The
   consumer is the human at the next `amend-constitution` gate; the durable
   pointer is
   [docs/runbooks/constitution-amendment.md](../runbooks/constitution-amendment.md),
   which lists this reading as third gate material (run tracking lives in
   the repo-local task ledger, which is not part of the clone). Readings the
   decision will consume: (a) shadow↔live cosine across **≥ 2 runs** (one
   run is wiring proof, not evidence), (b) run-to-run stability of the
   shadow itself on an unchanged corpus — the instrument's own noise floor,
   per the ADR-0090 null-pair precedent, (c) a **floor anchor** measured
   alongside the first runs — cosine of a deliberately unrelated document vs
   the live constitution, per the three-point-scale discipline
   (`CALIBRATION_ANCHORS`, ADR-0071): without an anchor a whole-doc cosine
   between two same-genre documents cannot be read as convergence or
   divergence at all, (d) clause- and section-level qualitative diff
   (divergent clauses are the primary signal), (e) validation-failure rate.
   No numeric thresholds are set before the data exists.

6. **Known limitation, carried in the output itself** (the ambiguity-note
   discipline of ADR-0071 Decision 6, codified in the repo skill
   `read-only-instruments`): the reading is partially circular through
   three channels. The input patterns were produced under the full action
   prompt, which includes the live constitution (axioms live at action
   time, ADR-0058); the `constitutional` view that selects the patterns is
   itself seeded from the live constitution files (`seed_from:
   ${CONSTITUTION_DIR}/*.md` — the view-seed design of
   [ADR-0019](0019-discrete-categories-to-embedding-views.md)); and both
   arms' prompts impose the same per-section shape constraints (directive
   voice, 1-4 quoted clauses), so a whole-doc cosine is inflated by shared
   genre and form regardless of content. Convergence therefore measures
   "experience-supported" only *jointly* with that shaping — which is why
   divergent clauses and the free section inventory, not convergent
   wording, carry the signal, and why Decision 5 reserves a floor anchor.
   The CLI prints this note with every reading.

## Alternatives Considered

- **Remove the current-constitution injection from `amend-constitution`
  itself.** Rejected. It converts the amendment from a reviewable diff into
  a whole-document re-adjudication at the gate, makes the "every change must
  trace to the patterns; nothing invented" constraint unenforceable (with no
  base, everything is new text), discards the friction-biased-sample
  problem, and risks identity random-walk across amendments. The
  conservatism has load-bearing components; the instrument answers the
  interesting question without paying this.

- **Weaken the anchor instead (inject only section headers, or a summary).**
  Rejected for now. Still anchored, so it cannot answer the convergence
  question; and it changes live amendment behavior — a value-layer
  intervention — without any reading to justify it. If shadow readings show
  systematic divergence, a weakened-anchor amendment prompt becomes a
  data-backed follow-up proposal.

- **Wire into the weekly chain immediately.** Deferred, not rejected.
  ADR-0071's opt-in-first discipline (production byte-identical; opt-in
  paths first) and the zombie lesson codified in the repo skill
  `shadow-mode-validation` ("shadow mode that never ends is a zombie" — a
  shadow with no consumer and no exit date is scaffolding) both say the
  cadence must be earned. A monthly slot beside the ADR-0091 staging is the
  natural follow-up once ≥ 2 manual runs prove the readings are readable.

- **Do nothing.** Rejected. The next amendment gate would again have only
  the diff and the reasoning trace (plus ADR-0090's behavioral bench) —
  nothing that says which clauses experience actually supports, which is
  exactly the material a from-scratch synthesis surfaces.

## Consequences

Positive:

- The next amendment gate gains a third kind of material: text diff
  (existing), behavioral bench (ADR-0090), and now an
  experience-only counterfactual with a divergence reading.
- No production write surface and no shared-state coupling (the one-shot
  CLI process exits after the run; nothing downstream consumes the breaker
  state, unlike the in-session ADR-0076 selector which needed
  `circuit_shield`); kill switch by absence. The residual live-machine cost
  is the generation itself (first Negative below).
- The record is replayable offline: prompt, output, thinking, lineage,
  and the digest of the constitution the reading was taken against.
- Guard-structure parity with `amend_constitution` keeps the two arms
  comparable and the code trivially diffable.

Negative / accepted costs:

- One think-ON generation per run on the 16 GB production machine — do not
  run during the JST 0/6/12/18 scheduled sessions (same constraint as every
  heavy Ollama use).
- The log is a single un-partitioned file (unlike the date-partitioned
  skill-selection log): at manual cadence one file keeps the longitudinal
  series trivially readable, and interleave/growth risks are negligible.
  Revisit (partitioning + a reading function over the log — also deferred
  until ≥ 2 runs exist) when scheduled wiring is proposed.
- The circularity limitation is structural: this instrument can never fully
  separate "experience supports the constitution" from "the constitution
  shaped what experience got recorded". It narrows the question; it does
  not close it.
- Guard parity is only partly shared code (`MIN_PATTERNS_REQUIRED` and the
  pattern renderer `render_constitutional_patterns` are imported from the
  amend module); the generation parameters and guard *ordering* are
  convention plus tests, and a future change to `amend_constitution`'s
  guards must be mirrored manually (accepted: extracting a full shared
  guard helper for two call sites is not yet worth the indirection).
- Constitution-shaped text without approval lineage becomes readable in two
  new places (stdout and the b64 record). The Context ban — a patterns-only
  text must not become the live constitution — is carried by a printed note
  ("NOT an amendment candidate; adoption goes only through
  amend-constitution") rather than a mechanism; the actual write path
  remains gated by ADR-0012/0050 as before.
- An instrument with no consumer decays into a zombie; mitigated by the
  dated ledger entry and by scoping adoption of any scheduled cadence to a
  future data-backed decision.

## References

- Implementation: `src/contemplative_agent/core/constitution_shadow.py`,
  `config/prompts/constitution_synthesize.md`,
  `cli/memory_cmds.py` (`shadow-constitution`),
  `tests/test_constitution_shadow.py`
- [ADR-0019](0019-discrete-categories-to-embedding-views.md),
  [ADR-0071](0071-read-only-pattern-composition-instruments.md),
  [ADR-0075](0075-observability-by-default.md),
  [ADR-0076](0076-skill-selection-shadow-instrument.md),
  [ADR-0077](0077-chaos-tdd-fault-injection.md),
  [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md),
  [ADR-0091](0091-value-layer-cadence-in-the-weekly-chain.md)
- Repo skills (git tracked): `.claude/skills/read-only-instruments/SKILL.md`
  (instrument invariants, three-point scale),
  `.claude/skills/shadow-mode-validation/SKILL.md` (shadow discipline,
  zombie lesson)
- Evidence anchor for the conservatism observation:
  [docs/evidence/adr-0090/](../evidence/adr-0090/) (retired 2026-05-05 text
  vs the adopted 2026-08-09 amendment)
