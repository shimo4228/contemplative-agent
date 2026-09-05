# ADR-0099: Weekly Report Content Redesign: From A–E Quote Audit to a Six-Section Instrument Document

## Status

accepted — partially-supersedes [ADR-0040](./0040-separate-code-level-findings.md)

## Date

2026-08-26

## Context

The A–E report format ([ADR-0040](./0040-separate-code-level-findings.md),
2026-05-19) was designed as a quote-based audit of the agent's generation
quality, with section E ("Qualitative Highlights", good / problematic /
typical buckets) as the analytical center and sections C and D derived from
it. It did its job — and saturated. The report series re-confirms the same
findings week after week: the reframe-as-modal finding appears across 6+
consecutive weekly reports, `weekly-2026-08-21` marks the
commercial-surface-invisibility finding as its "eighth consecutive report",
and introspective non-answers recur for "at least the seventh week".

[ADR-0098](./0098-weekly-single-session-and-triage-delegation.md)
(2026-08-24) collapsed the plumbing (seven unattended sessions down to one)
but deliberately left the section definitions
(`config/prompts/weekly-analysis.md`) unchanged. The owner's instruction
during that redesign — "そもそもレポートの内容が微妙" (2026-08-24) — filed
the content redesign as [RFC-0010](../../rfcs/0010-weekly-report-content-redesign.md).
ADR-0098's own measurement (8 of 11 trailing-three-week F1 findings were
about the plumbing itself, not the agent's core behavior) fed the same
doubt: whether the report was producing observations worth reading at all.

The [ADR-0080](./0080-north-star-layered-end-state.md) amendment
(2026-08-26) made the mechanism layer's completion condition operative — the
metabolism loop (episode → patterns → skills → selection → generation →
back to Moltbook) must self-regulate without daily owner and Claude Code
involvement; human approval stays as authority but its load approaches zero
— and added the metabolic-quality clause (multi-axis discrimination —
novelty, importance, environmental response; single-scalar reduction
prohibited). This gave the report a job whose answer changes weekly, where
the old A–E spine's answer no longer did: the report is re-anchored as the
reading instrument for that amendment, with the longitudinal research
record (north-star layer 4) secondary.

A design session on 2026-08-26 (grill-me interview, owner deciding each
question) ran two fresh-context Fable agents in parallel — one given the
metabolism-loop brief, one given only "an observation document for a
self-modifying system the observer must not steer, read weekly by one
human." The two independently converged on the same design: instrument, not
report; no section-filling duty; an observation ledger that compresses
recurrence to one line instead of re-narrating it; prohibition of
evaluative and predictive vocabulary; evidence restricted to quote / diff /
self-distribution comparison with replay pointers; and making the writer's
own selection function legible (a discarded-candidates appendix, plus a
code-drawn random sample as a control channel). The owner adopted the
convergence. Sister task [RFC-0017](../../rfcs/0017-insight-extraction-redesign.md)
(insight-extraction redesign, draft) supplies the future per-candidate
multi-axis evidence this design consumes at the gate.

## Decision

1. **Six-section instrument document replaces A–E.**
   `config/prompts/weekly-analysis.md` (the section canon) is rewritten.
   All six sections carry mandatory headings but conditional content — one
   honest line is a complete section, and a quiet week's document is
   deliberately short:
   - **Inventory** — one stock line (decisions-pending / exceptions /
     new-observations / continuing / discarded, counts and pointers only),
     a coverage declaration, and a `format: instrument-v1 (RFC-0010)`
     calibration stamp.
   - **Ledger** — every open observation as a one-line
     `O-NNN (first seen, week N): unchanged | changed — delta` reference;
     recurrence is never re-narrated.
   - **Deviations** — new observations only, each qualifying by deviating
     from a gate-declared baseline or being a ledger-absent novelty;
     template fields Expected / Observed / Evidence / Counterfactual /
     Replay. An observation whose counterfactual cannot be written
     concretely is filler and goes to Discarded.
   - **Exceptions** — deterministic-instrument threshold crossings and
     invariant violations only, fact plus pointer, no repair proposals.
   - **Sample** — a deterministic uniform random sample of the week's
     comment-report entries, seeded by the end date, drawn by
     `scripts/weekly_random_sample.py` and copied verbatim — the control
     channel against the writer's own selection function.
   - **Discarded** — candidate observations the writer considered and
     dropped, one reason-coded line each, making the writer's lens legible.

   Binding prohibitions throughout: evaluative vocabulary, recommendations,
   predictions / trend extrapolation, external comparisons, composite
   scores, anthropomorphic diagnosis. Evidence takes exactly three forms —
   verbatim quote, diff, self-distribution comparison — each with a replay
   pointer sufficient to re-derive the claim without trusting the document;
   writer coinages carry "(observer coinage, date)" provenance. The
   pipeline's structural gate (`report_missing_parts`) now checks the six
   exact headings.

2. **Add an observation ledger.**
   `$MOLTBOOK_HOME/reports/analysis/observation-ledger.jsonl` — append-only
   JSONL, rows never rewritten. Row types: `observation` (mandatory expiry
   condition — an observation with no way to leave the ledger is a
   permanent weekly tax); `archive` (closes an open id citing the fired
   expiry; archived ids are never reused); `baseline` (active — declarable
   only by the Saturday gate or the bootstrap, since a baseline redefines
   what counts as a deviation, which is instrument calibration, and
   calibration changes pass the human gate); `baseline_proposal`
   (session-stageable). The unattended session stages a delta at
   `reports/.private/ledger-delta-<end>.jsonl`; the pipeline validates and
   appends it via `scripts/observation_ledger.py append` only after the
   structural gate passes, fail-closed per delta (`LEDGER_DELTA_INVALID`,
   delta quarantined). Bootstrapped 2026-08-26 with 7 known saturated
   observations (first-seen dates reaching back into the A–E series, so the
   new document starts unable to re-discover the known) and 6 active
   baselines.

3. **Move the human read surface to the gate.** The operator no longer
   reads the weekly document or findings directly. The Saturday
   `/weekly-gate` session becomes the sole human read surface: it explains
   every pending decision item by item in plain Japanese (eli5 register,
   small diagrams where they speed judgment), with a per-item
   recommendation, bounded by three structural constraints: the full queue
   is always shown (pre-filtering is adjudication by another name — the
   [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md)
   headless-reviewer-as-effective-filter shape must not be rebuilt
   invisibly); per-axis evidence is presented separately from the
   recommendation with no composite score (the ADR-0080 amendment's
   single-scalar prohibition applied at the gate face); and explanation +
   recommendation + decision are logged per item (`gate_item` rows in
   `pipeline-metrics.jsonl`) so the briefing lens's bias is auditable
   later. Japanese translations of the report and findings
   (`weekly-*.ja.md`) are retired; historical files stay in place.

4. **Keep diagnosis and adjudication as separate seams.** The diagnosis
   phase (ADR-0098: F1/F2/F3 → draft filing → task-triage) survives with
   its role unchanged; its input switches from the retired E section to
   the document's Deviations + Exceptions, since the document itself
   cannot carry proposals and diagnosis remains the only translation from
   observation to repair candidate. The document carries no
   adjudication-queue section (inventory counts and pointers only):
   per-candidate multi-axis evidence is RFC-0017's staging metadata, read
   directly by the gate — preserving ADR-0098 D3's direct-read division
   and not rebuilding the retired packet builder in miniature. Until
   RFC-0017 ships, the inventory line runs on counts alone.

Files touched: `config/prompts/weekly-analysis.md` (rewritten),
`config/prompts/principles.md` (diagnosis-only note),
`config/prompts/weekly-analysis-ja.md` (deleted),
`scripts/observation_ledger.py` + `scripts/weekly_random_sample.py` (new),
`scripts/weekly-analysis.sh`, `scripts/weekly-pipeline.sh`,
`.claude/skills/weekly-report/SKILL.md` + `references/diagnosis.md`,
`.claude/skills/weekly-gate/SKILL.md`, `tests/test_weekly_analysis_shell.py`,
`tests/test_weekly_pipeline_diagnosis_scope_shell.py`.

## Review-when

- The ledger compression fails its job — the same observation is
  re-narrated as a paragraph in 2 consecutive weekly documents → add the
  deferred prior-week text-similarity self-measurement (deliberately not
  built in v1).
- The diagnosis phase's output chronically duplicates the observation
  ledger → absorb diagnosis into the document (the reserved contraction
  path from the design session's Q4).
- The Deviations section is empty 4 consecutive weeks AND the longitudinal
  record reads as starved → recalibrate the baseline declarations (the
  deviation definition is too coarse).
- The gate's agreement rate with the briefing recommendations runs at
  ~100% sustained → run one retrospective lens audit over the logged
  `gate_item` recommendations (effective-filter warning sign).

## Alternatives Considered

### Incrementally re-aim E's sampling criteria

From "good / problematic / typical" to metabolism-event-anchored — the
session's initial direction before the owner asked for a radical rethink.
Rejected: a continuous deformation of a saturated design; the two
independent fresh-context convergences landed somewhere a continuous
deformation would not reach.

### Deterministic readings only — drop the LLM-written sections entirely

Rejected: the final two links of the metabolism loop (did adopted material
actually change generation; did the environment respond) are observable
only in quoted evidence, which the state diff and selection log cannot
carry.

### Render the adjudication queue with evidence tables inside the document

Rejected: rebuilds in miniature the packet builder ADR-0098 retired (a
synthesis layer that grows with every added section, and a second copy
that drifts from the candidates' own metadata); the fresh designs'
underlying requirement — evidence self-contained at decision time — is met
by candidate-attached metadata read directly at the gate.

### Evidence-only gate briefing (no recommendation)

Rejected by the owner: the load stays too high, defeating the
reading-surface turn; chosen instead was recommendation bounded by
full-queue presentation, axis separation, and per-item logging.

### Status quo

Rejected: the measured saturation — the same findings re-confirmed across
6–8 consecutive reports — and the owner's explicit 2026-08-24 judgment that
the content was no longer worth reading.

## Consequences

### Positive

- Saturation resistance is structural (ledger one-line compression +
  conditional sections + counterfactual qualification), not a
  prompt-wording hope.
- The writer's selection function becomes auditable from three
  directions: the Discarded appendix, the code-drawn random sample, and
  the logged gate recommendations.
- The longitudinal record gains calibration stamps (format line, ledger
  append history, baseline declaration dates) and full replayability — a
  future reader can re-derive claims without trusting the writer.
- Quiet weeks become cheap for every consumer (short document, one-line
  sections) instead of forced narrative.
- The document's job now tracks the ADR-0080 amendment's questions, which
  have weekly-changing answers.

### Negative

- A hard format discontinuity at the first run (2026-08-29): the A–E
  longitudinal series ends, and week-over-week comparisons across the
  boundary compare different instruments. Mitigated by the ledger's
  first-seen dates carrying continuity across the boundary and the
  discontinuity being stamped in each document.
- Two earlier boundaries govern longitudinal reads of the report series
  (recorded here 2026-09-05 when the codemap that held them was retired,
  ADR-0102): **2026-08-16** — dropping the user settings layer from the
  report session moved its model/style from `claude-fable-5` / `Explanatory`
  to the project default, so reports ending on or after that date are a
  different instrument and prose shifts across it are a boundary, not a
  signal; **2026-08-29** — ADR-0098 also made report and diagnosis come from
  one session via a materials file (the same first run as this ADR's format
  change). Japanese report translations end at the 2026-08-29 boundary.
- The gate-briefing Claude with recommendations sits exactly where an
  effective filter can hide; the mitigation is procedural (full queue,
  axis separation, per-item logging, agreement-rate audit trigger), not
  structural.
- A new persistent artifact (the ledger) must stay healthy; a corrupt or
  badly-tended ledger degrades both the weekly document and the
  longitudinal record.
- Deviation-driven reporting is only as good as the declared baselines;
  badly calibrated baselines silently starve the record (the third
  Review-when trigger reserves the recalibration).
- The operator stops reading the primary documents; the research-layer
  contemporaneous-witness function is now mediated by the gate briefing
  (the raw record remains for later readers).

### Neutral / Follow-ups

- Partially supersedes [ADR-0040](./0040-separate-code-level-findings.md):
  the A–E format and its section-E analytical center are replaced by the
  six-section instrument document. What still stands is recorded in
  ADR-0040's dated note, not here.
- [RFC-0010](../../rfcs/0010-weekly-report-content-redesign.md) is the
  task record this ADR resolves.
- [RFC-0017](../../rfcs/0017-insight-extraction-redesign.md) supplies the
  per-candidate multi-axis evidence the Inventory section will consume
  once it ships; until then the inventory line runs on counts alone.
