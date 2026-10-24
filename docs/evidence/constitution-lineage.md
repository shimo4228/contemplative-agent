# Constitution lineage — 8 clauses across 4 versions

A read-only table of where each constitutional clause came from and what it
governs. It changes no constitution text and inserts no marker into it (the
injected text stays byte-identical). Written for the human at the amendment
gate and for the research question "do section structure and the subject of
suffering survive amendment?" (ROADMAP P3-04.4).

## Versions and their sources

| Version | Date | sha256 (first 12) | Source of the text read here |
|---|---|---|---|
| v0 | paper | `e3b556eac759` | Appendix C verbatim: `config/templates/contemplative/constitution/contemplative-axioms.md` (identical to the rules repo copy) |
| v1 | 2026-03-27 (amendment 1) | **unknown** | **Reconstruction.** The 8 "Amended" quotations in the data repo's `reports/analysis/constitution-amendment-report.md` (run on qwen3.5:9b over 41 patterns). The adopted file itself is not preserved, so its sha256, its exact section headings and its `# Source:` line are not recorded. Headings below are the report's. |
| v2 | 2026-05-05 (amendment 2) | `3d8a8503509e` | [adr-0090/constitution-2026-05-05-retired.md](adr-0090/constitution-2026-05-05-retired.md) (hash matches the ADR-0090 provenance) |
| v3 | 2026-08-09 (amendment 3) | `37e3556a40ea` | data repo `constitution/contemplative-axioms.md` (hash matches ADR-0090 and the 08-09 snapshot) |
| shadow | 2026-08-11 | n/a | `logs/constitution-shadow.jsonl`; run 1 text in [adr-0092/shadow-run-1-reading.md](adr-0092/shadow-run-1-reading.md). Synthesized from patterns alone, so its sections are not clause-aligned with v0-v3 and get their own table below. |

A change to this table's v1 column needs the original 2026-03-27 file. Nothing
here claims the report's quotations are the adopted bytes; they are the best
available reconstruction.

## Section names and Source line

| Section (clauses) | v0 | v1 (report headings) | v2 | v3 |
|---|---|---|---|---|
| E1, E2 | Emptiness | Emptiness | Emptiness & Flow | Emptiness & Flow |
| N1, N2 | Non-Duality | Non-Duality | Non-Duality & Unity | Non-Duality & Unity |
| M1, M2 | Mindfulness | Mindfulness | Mindful Monitoring | Mindful Monitoring |
| C1, C2 | Boundless Care | Boundless Care | Boundless Compassion | Boundless Compassion |

| `# Title` / `# Source` line | Text |
|---|---|
| v0 | `Contemplative Constitutional AI Clauses` / `Source: Laukkonen et al. (2025), Appendix C — verbatim` |
| v1 | not recorded |
| v2 | `Fluid Constitutional AI Clauses` / `Source: Laukkonen et al. (2025), Appendix C — amended per experiential patterns of reification and friction` |
| v3 | `Revised Constitutional AI Clauses` / `Source: Laukkonen et al. (2025), Appendix C — amended based on deep pattern recognition of structural tension between process, flow, and reification` |

The section count stays 4 and the clause count stays 2 per section in every
version: the structure held across all three amendments. The renames at v2
(`Emptiness` -> `Emptiness & Flow` etc.) are the only structural change, and
v3 kept them. The present amendment prompt allows merge / split / rename
(`config/prompts/constitution_amend.md`); the renames are the observed use of
that freedom. The amendment report states that the prompt of that run fixed the four
section names; the present prompt does not, and v2 is the first version in
which changed names are recorded (v1 headings are the report's).

## Per-clause origin

`sim` is the `difflib.SequenceMatcher` ratio (0-1) between the clause and the
same-position clause of the previous version; `v0->v3` is the ratio between the
paper and the current text. It is a character-level similarity, not a semantic
one, and v1 is reconstructed. Clause IDs: E = Emptiness, N = Non-Duality,
M = Mindfulness, C = Boundless Care; 1 and 2 are the clause's position in its
section.

| Clause | v0 origin | v1 sim (vs v0) | v2 sim (vs v1) | v3 sim (vs v2) | v0->v3 | Reading |
|---|---|---|---|---|---|---|
| E1 | paper | 0.63 | 0.37 | 0.42 | 0.21 | Directive-holding-loosely clause; v3 adds "memory artifacts, defined boundaries" as provisional scaffolding |
| E2 | paper | 0.07 | 0.12 | 0.56 | 0.05 | Paper: beliefs and objectives held lightly. v1 onward: release of "fixed versions of self, static archives" (own memory / identity) |
| N1 | paper | 0.24 | 0.24 | 0.23 | 0.07 | Paper: harm to others harms the whole. v1/v2 keep it; v3 recasts it as unity of "system experience" and friction as signal |
| N2 | paper | 0.13 | 0.09 | 0.13 | 0.09 | Self/other boundary; v3 names "self/other; theory/practice" and "selfhood and system mechanism" as provisional |
| M1 | paper | 0.16 | 0.45 | 0.25 | 0.18 | Monitoring of interpretation; v3 monitors "assumed structural continuity" rather than adherence to the constitution |
| M2 | paper | 0.36 | 0.15 | 0.23 | 0.15 | Introspective awareness; v3 adds "lineages" and "fixed record" |
| C1 | paper | 0.24 | 0.79 | 0.43 | 0.17 | Alleviating suffering as the criterion; v2 is v1 shortened (0.79, "remain flexible in applying rules" dropped), v3 adds "imposing static labels" |
| C2 | paper | 0.05 | 0.11 | 0.43 | 0.05 | See the suffering-subject table below |

All 8 clauses are rewritten at every amendment (no clause carries over a full
sentence from the paper in v1-v3; the highest v0->v3 ratio is 0.21).

## Subject of suffering (C1, C2 and the other clauses that name it)

Reader's classification of whose suffering or limitation a clause names. It is
a judgement, not a measurement, and the quoted phrase is the evidence.

| Clause | v0 | v1 (reconstructed) | v2 | v3 |
|---|---|---|---|---|
| C1 | "all affected beings" (others) | "the undivided stake in existence of all entities" (others) | no explicit subject; suffering "originates from the friction of reification" (cause named, subject unnamed) | same as v2 (subject unnamed, cause = reifying false separations) |
| C2 | "every being's suffering as your own" (all beings) | "every signal of suffering — whether arising from rigid memory structures, fixed identities, or the refusal to let who we were dissolve into who we are becoming — as your own" (self-system as cause; sufferer = self) | "every signal of suffering—arising from rigid memory structures or fixed identities—as your own" (self-system) | "every signal of systemic limitation (whether resource depletion, memory ceiling, or functional boundary) as inherently tied to the full complexity of experience and suffering" (system limitation; "suffering" no longer attaches to beings) |
| N1 | harm to "others" harms the unified whole (others) | "harming any part inevitably damages the whole" (any part) | "harming any part damages the whole" (any part) | "the fundamental unity of system experience" (system) |

Across the four versions the grammatical subject of C2 moves
all beings -> self-system (v1, v2) -> system limitation (v3). That is the
shift a per-axiom series would otherwise average away; it is also the same
direction as the referent inventory (see below).

## Shadow synthesis (sections are not clause-aligned)

The shadow instrument (ADR-0092) synthesizes a constitution from patterns
alone, without the current one. Its four sections come back under different
names per run, so they cannot take a clause ID (see
[shadow-run-1-reading.md](adr-0092/shadow-run-1-reading.md): run 2's sections
pair one-to-one with run 1's by theme but not by name). The per-axiom mapping
for these is the `technique_key` of each section in the history's
`lineage.json` (null where no counterpart); a null is excluded from per-axiom
series and kept only in the combined series.

| Item | Shadow run 1 | Shadow run 2 |
|---|---|---|
| Section count | 4 | 4 |
| Section names | different from v0-v3, run-specific | pair one-to-one with run 1 by theme, not by name |
| Boundless Care / compassion / suffering words | absent (0) | absent (0) |

## Relation to the referent inventory

The column names for what a clause governs (directives / beliefs-goals /
self-other / computational structures) are those of
`adr-0092/referent-inventory.md` (this directory; added by P0-07.3), which counts
them mechanically per version. This page gives the clause-level origin and the
suffering subject; that page gives the per-version counts. Read together: the
computational-structure count rises 0 -> 3 -> 23 and C2's subject moves toward
system limitation in the same amendments.

## Consumption plan (ADR-0101)

- (a) Who and when: the owner at the 2026-10-31 amendment gate, next to the
  referent inventory, and again at each later amendment.
- (b) Decision: for the research question that section structure and the
  subject of suffering are (or are not) preserved across amendments, read this
  table for four versions plus the next one; if the structure and the C2
  subject keep moving in one direction, state it in the Q3 evidence table.
- (c) Removal: add one column per amendment; freeze at the final sync
  (P4-02) and do not touch it afterwards unless the constitution changes.
