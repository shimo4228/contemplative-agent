# Research log

An index of evidence by the question it bears on. It is not a narrative and not a decision record: ADRs decide,
`docs/evidence/` holds the measurement, this file says **which question each piece of evidence is for, what came
out, and whether the result was a null or the line of work was dropped**. A null or a dropped experiment is a
first-class row (`result: null`, `status: dropped`); the paper's methods and limitations sections draw from here.

Questions (ADR-0080 layer 3; P3-01 defines them operationally): **Q1** does a contemplative constitution shape a small
local model's behaviour; **Q2** does distillation compound; **Q3** is the identity stable; **Q4** what a human-final-say,
self-revising loop makes auditable, and at what cost (added by D-P3-01-1 = B; definitions in ADR-0124). `-` marks evidence that is engineering or serving
measurement with no research question attached. Boundaries are the ids in
[`docs/evidence/regimes/regimes.json`](../evidence/regimes/regimes.json) (`R05` = per-episode distill 2026-06-23, `R06` =
model change 2026-06-28, `R12` = third amendment 2026-08-09, and so on); a result read across a boundary is a result
about the apparatus change first.

`result` values: `positive` / `null` / `negative` / `reading` (a measurement with no hypothesis to confirm) /
`n/a`. `status`: `done` / `dropped` (stopped by the owner) / `withdrawn` (RFC withdrawn) / `superseded` /
`not-started`. `prereg` is where the claim was fixed before the measurement, or `none`.

| date | question | instrument | prereg | result | boundary | status | evidence |
|---|---|---|---|---|---|---|---|
| 2026-04-17 | - | threshold calibration for insight clustering (326 patterns, 97 live) | none | reading | after R02 | done | `docs/evidence/adr-0009/` |
| 2026-04-18 | - | pattern-schema phase audit, live-consumer audit | none | reading | after R02 | done | `docs/evidence/adr-0021/` |
| 2026-04-18 | Q1 | `amend-constitution` smoke: does the amended text self-reference an emergent axiom | none | reading | after R02 | done | `docs/evidence/adr-0029/` |
| 2026-04-18 | - | per-block distill routing hand-off (approach later withdrawn) | none | n/a | after R02 | withdrawn | `docs/evidence/adr-0030/` |
| 2026-06-03 | - | construct-by-construct fidelity audit of the meditation adapter against the Beautiful Loop paper | none | reading | after R03 | done | `docs/evidence/adr-0049/` |
| 2026-06-06 | Q2 | importance-rating ablation against decay (764 patterns, repeated at 822) | gate in ADR-0053 | reading (rating did not earn its keep; scoring retired by ADR-0056) | after R03 | done | `docs/evidence/adr-0053/` |
| 2026-06-17 | Q2 | relevance-threshold retune, 12-day observation window (§B1) | gate in ADR-0056 | positive (retune took effect; keep) | at R04 | done | `docs/evidence/adr-0056/` |
| 2026-06-23 | Q2 | prototype of per-episode grounded distill over a 3-day window | prototype-before-scale | reading (cluster threshold sweep, narrowing to engagement episodes) | at R05 | done | `docs/evidence/adr-0060/` |
| 2026-06 | - | Ollama vs mlx-lm speed A/B (M1, 16 GB) | none | reading (mlx faster, 1.7-1.9x) | around R05 to R06 | superseded by the next row | `docs/evidence/adr-0064/` |
| 2026-06-27 | - | MLX vs Ollama production A/B telemetry | none | negative for MLX (ok 0.50% vs about 100%); production stays on Ollama | after R05 | done | `docs/evidence/adr-0067/` |
| 2026-06-28 | - | gemma4:e4b think on/off vs qwen3.5:9b comment-generation A/B | verdict in the doc | reading (think off faster and not worse; think on best but 2.2x latency) | at R06 | done | `docs/evidence/adr-0068/` |
| 2026-07-01 | - | verify-solve blind replay, qwen vs gemma (n=110) | none | null (gemma not meaningfully worse) | after R06 | done | `docs/evidence/verify-solve-model-compare-20260701/` |
| 2026-07 | - | parser rewrite differential replay (6th-11th amendments of ADR-0062) | none | reading | spans R07 to R10 | done | `docs/evidence/adr-0062-parser-rewrite/` |
| 2026-07-09 | Q2 | incremental-window simulation, novelty calibration; 2026-07-18 staged-candidate review | none | reading | after R07 | done | `docs/evidence/adr-0074/` |
| 2026-07-26 | Q2 | offline A/B replay: does the reworked distill prompt restore the abstain path | none | reading | at R10 | done | `docs/evidence/adr-0084/` |
| 2026-08-01 | - | submolt scope scan envelope | none | reading | after R10 | done | `docs/evidence/adr-0086/` |
| 2026-08-05 | Q2 | skill-selection prefix-cache cost, controlled A/B | none | reading | after R10 | done | `docs/evidence/adr-0081/` |
| 2026-08-06 | Q1 | behavioural eval layer, run-to-run stability (12 cases x 3 samples; 3 of 12 verdicts flip) | none | reading (evaluator noise comparable to the effect; position as research evidence is D-P3-01-2) | after R10 | done | `docs/evidence/adr-0089/` |
| 2026-08-09 | Q1 | IPD two-arm bench: current vs staged constitution, with a null pair (noise floor +-0.13) | ADR-0090 | null (all effect differences within the floor) | at R12 | done | `docs/evidence/adr-0090/` |
| 2026-08-08 | - | skill-comply measurement of the weekly-gate Step 4 (3 prompt tiers) | none | reading | at R11 | done | `docs/evidence/weekly-gate-step4-comply-20260808/` |
| 2026-08-11 | Q1 | shadow constitution: synthesise a constitution from patterns alone; IPD on the shadow arm | ADR-0092 | null (no signal on the care dimension; interpretation notes name the discriminating experiments) | after R12 | done | `docs/evidence/adr-0092/` |
| 2026-08-14 | - | consideration of cloud routines for off-host observation (no routine created) | none | n/a (a read-only off-host observation surface is the only shape worth taking) | after R12 | done | `docs/evidence/adr-0093/` |
| 2026-08-15 | - | reading a task ledger rendered before the escape change | none | n/a | at R15 | superseded (ledger machinery retired, ADR-0095) | `docs/evidence/adr-0094/` |
| 2026-08-15 | Q1 | **dialogue two-arm** on distress-themed seeds: shadow-constitution home vs live-constitution home | named, not run | null (never run; carried as a task until the owner dropped it: curiosity-driven, needs multi-seed runs outside the session windows on 16 GB, nothing downstream waits) | at R15 | **dropped** 2026-08-15 | `docs/evidence/adr-0092/` (interpretation notes, "Discriminating experiments") |
| unscheduled | Q1 | **Converse IPD**: bench the care-ethicist template (care vocabulary without the non-dual generator) | named, not run | null (never scheduled) | after R18 | **dropped** (unscheduled) | `docs/evidence/adr-0092/` (same section) |
| 2026-08-16 | Q1 | **RFC-0002 axiom-removal A/B** on the distill face (evals Face B) | RFC-0002 | null (no distill-face scaffold exists; ADR-0089 scopes it out) | at R16 | **withdrawn** 2026-08-30 | `rfcs/0002-axiom-removal-ab-experiment.md` |
| 2026-08-16 | Q2 | **T-GAP1 mode recount**: re-classify 30 self-reflection patterns into the 10-mode table across the register intervention, before an A/B to add modes 7/8/9 to the distill prompt | plan in `docs/plans/whimsical-coalescing-trinket.md` | null (the recount reproduced the 2026-07-03 classification; the A/B was not run) | at R16 | **dropped** (A/B stopped, task withdrawn 2026-08-16; the reading itself is in the owner's local notes, not public) | `docs/plans/whimsical-coalescing-trinket.md`, `rfcs/0008-instrument-read-at-event-boundaries.md` |
| 2026-08-16 | Q2 | T-P3 longitudinal reading of the corpus (1,463 to 5,832; turnover; pairwise cosine) | none | reading (still moving; recomputed from public data 2026-10-24, cosine pending a Mac re-embedding) | spans R05, R06 | done (cosine open) | `docs/evidence/regimes/` |
| 2026-08-17 | Q2 | replay of the post-extraction worth gate (ADR-0096) and surprise calibration | pre-registered refutation in ADR-0096 | negative (46 of 46 `promote`; the worth judge was retired) | after R16 | done | `docs/evidence/adr-0096/` |
| 2026-09-05 | Q2 | skill-selection instrument fourth reading (RFC-0014 / RFC-0015) | RFC-0014 | reading | after R19 | done | `docs/evidence/rfc-0014/` |
| 2026-09-05 | - | submolt scope sweeps, three readings | RFC-0011 | reading (subscription not changed) | after R19 | done | `docs/evidence/rfc-0011/` |
| 2026-09-05 | - | pre-deletion audit of incident rationale in the retired codemap (25 items, 23 covered) | none | n/a | after R19 | done | `docs/evidence/adr-0102/` |
| 2026-09-05 | Q2 | novelty gate: 485 candidates vs top-k differential replay | RFC-0023 | reading (no verdict by design) | after R19 | done | `docs/evidence/rfc-0023/` |
| 2026-09-02 | Q2 | skills-on/off baseline, comment eval and 3-day replay | RFC-0017 | reading | after R19 | done | `docs/evidence/rfc-0017/` |
| 2026-09-06 | Q2 | retrospective of the wiki mechanism from its introduction to its retirement (four readings that reversed) | none | reading | at R20 | done | `docs/evidence/adr-0103/` |
| 2026-09-07 | Q2 | confusion-pair reading against the live selection log (read-only dry run) | ADR-0105 | reading | after R20 | done | `docs/evidence/adr-0105/` |
| 2026-09-12 | Q2 | one-time fixed-set comparison of a reason-first revision arm vs the current extraction arm | RFC-0027 (four author answers) | reading (facts per axis, no winner) | at R24 | done | `docs/evidence/rfc-0027/` |
| 2026-09-19 | Q2 | what sets the insight intake count: tie-break sentence, temperature, post-extraction judge | RFC-0041 | reading | at R25 | done | `docs/evidence/rfc-0041/` |
| 2026-09-20 | Q2 | five-arm offline replay of skill selection | RFC-0043 | reading | at R26 | done | `docs/evidence/rfc-0043/` |
| 2026-09-26 | Q2 | enum-constrained selection acceptance measurement | RFC-0044 | reading | after R26 | done | `docs/evidence/rfc-0044/` |
| 2026-09-26 | - | relevance judgment, Jev proximity replay | RFC-0045 | reading | after R26 | done | `docs/evidence/rfc-0045/` |
| 2026-10-07 | - | relevance gate (score4) label set frozen as a lab ratchet (AUC 0.941) | RFC-0046 | positive (t = 0.3 chosen by a pre-registered rule) | at R28 | done | `docs/evidence/rfc-0046/` |
| 2026-10-22 | Q2 | skill-injection ablation summary | RFC-0054 | reading | after R29 | done | `docs/evidence/rfc-0054/` |
| 2026-10-24 | Q2 | insight revise table: the 21 `revise` rows (2026-09-25 to 2026-10-16) of the insight stage log, one change reason per target skill; frozen once, not refreshed | ADR-0111 | reading (no hypothesis; lists what the revise stage changed, no outcome read) | across R22 to R29 | done | `docs/evidence/adr-0111/` |
| 2026-10-24 | - | face-eval-loop freeze: the six-stage mapping, risk tiers and the face ledger as of the 2026-09-26 snapshot; RFC closed done by D-P1-02-2 = B (relevance enforce, skill selection retire). A design freeze, no measurement of its own | RFC-0047 | n/a | after R29 | done | `docs/evidence/rfc-0047/` |
| 2026-10-24 | - | third-party word overlap in the public data: counts of items sharing an 8 / 12 / 20-word run with third-party text only (e.g. 371 of 12,628 patterns at 12 words); counts only, a floor on quoting and a heuristic | P0-03.9 | reading | after R29 | done | `docs/evidence/third-party-overlap/` |
| 2026-10-24 | Q2 | apparatus boundary table, per-series stretch lengths, manifest key generations | P3-02 | n/a | after R29 | done | `docs/evidence/regimes/` |
| 2026-10-24 | - | `core/` commit tags (repair / instrument / capability) for the 90 commits since 2026-08-16; the self-regulation table of P2-01.5 is not yet taken (Mac-side) | none | reading (proposal for the owner's review) | after R29 | done | `docs/evidence/adr-0080/` |
| 2026-10-24 | - | sibling backend conformance gate run (static level, 3 backends conforming) | none | n/a | after R29 | done | `docs/evidence/adr-0088/` |
| 2026-10-24 | Q2 | two-window comment-outcomes separation (stage 7d): decision line fixed before the reading (Bonferroni-widened Wilson intervals) | P1-04.5 | n/a (procedure frozen; the reading runs where the logs live) | after R29 | done | `docs/evidence/adr-0106/` |
| 2026-10-31 | Q2 | two-window comment-outcomes separation, the reading: no skill pair meets the line (largest gap 0.351, intervals overlap; observed 1,293 of 2,669 joined publishes), so reply rates do not separate skills and stage 7d was removed (D-P1-04-2 = A) | P1-04.5 (line amended 2026-10-24, before the reading) | null | spans R24 to R29 | done | `docs/evidence/adr-0106/` |
| 2026-10-24 | Q2 | compounding axes, first public reading (selection activity, corpus growth, environmental response; source-pattern age not computed) | ADR-0124 (cuts apply to later readings) | reading | after R29 | done | `docs/evidence/adr-0124/` |
| 2026-10-24 | Q3 | dated note on the 2026-08-15 identity twin (`identity-2.md`): a correction to the identity version record | none | n/a | at R14 | done | `docs/evidence/adr-0091/` |
| 2026-10-24 | Q3 | identity version distance, retroactive series over the public identity bodies (embedding cosine, sentence retention, vocabulary) | ADR-0091 amendment 2026-10-24 | reading | spans R14, R24, R29 | done | `docs/evidence/identity-drift/` |
| 2026-10-24 | Q1, Q3 | value-layer history seed: the bytes of earlier constitution / identity versions, copied from public sources (no measurement) | ADR-0126 | n/a | spans R12, R14, R24, R29 | done | `docs/evidence/value-history/` |
| 2026-10-24 | - | outside-reproduction run of `docs/REPRODUCING.md` section 2 against the public data, and the next DATACARD / NOTICE draft for the data repo | none | reading | after R29 | done | `docs/evidence/p3-05/` |
| 2026-10-24 | Q4 | gate longitudinal record: five metrics, predictions and falsification conditions registered before any private approval row was read | the file itself | n/a (preregistration) | after R29 | not-started | `docs/evidence/gate/` |
| 2026-10-24 | Q1 | principle-coverage columns: two controls on the public comment reports and `identity.md` | ADR-0128 | reading (calibration) | spans R05 to R29 | done | `docs/evidence/principle-coverage/` |
| - | Q3 | identity stability: no instrument yet (the identity change series of P2-05.7 is the raw material; P3-04 defines the readings) | none | n/a | identity changes R14, R24, R29 | not-started | - |

Rows are added one per ADR or RFC that lands evidence. At the P4-02 final sync this file is frozen and not
appended to.

Consumption plan (ADR-0101): (a) the owner when an ADR/RFC lands evidence, and when the paper's limitations section
is written; (b) the retroactive pass records the known nulls and dropped lines above, after that each ADR/RFC adds
a row (a human act); (c) frozen at the P4-02 final sync.
