# Referent Inventory — what each constitution version governs

Read-only table over repo-held constitution texts (no text is changed). Reader:
the human at the amendment gate (runbook steps 0 and 6,
[constitution-amendment.md](../../runbooks/constitution-amendment.md)).
Registered as a descriptive reading in
[RFC-0055](../../../rfcs/0055-amendment-outcome-preregistration.md), row (f)
(`reanalysis: public`). Exploratory instrument: fill once per amendment; if two
amendments' worth of rows do not inform a decision, drop the column from the
runbook (consumption plan below).

Why: the 2026-08-09 amendment widened what the clauses govern, from
directives / beliefs to the agent's own computational structure (memory
artifacts, token limits, resource depletion) — the opposite of the interpretive
key that narrows a clause's referent. The table makes that shift countable.
It also counts the four ADR-0005 collision phrases (surface-form vocabulary
shared with ADR-0005; the mechanism there is a hypothesis).

## Counting rule

A mechanical rule, not a semantic judgement: lower-case the text, count whole-word
matches of the lexicon below, each word in exactly one category. The lexicon is
a judgement call and is part of the reading; change it only with a dated note.
Counts are occurrences, not distinct clauses.

| Category | Lexicon (whole words, plural forms included) |
|---|---|
| directives | directive, imperative, rule, mandate, guideline, clause, law, label, definition |
| beliefs / goals | belief, goal, objective, framework, concept, conceptual, methodology (and methodolog-*), certainty (certaint-*), essence, assumption, truth |
| self-other | self, selfhood, other(s), separation, boundary (boundar-*), identity (identit-*), being(s), entities, unity, interconnect-* |
| computational structures | memory, artifact, artifactual, archive, structure, structural, computational, system, systemic, mechanic-*, mechanism, resource, lineage, record, operational, functional |
| collision phrases (ADR-0005) | `constitutional directives`, `constitutional clauses`, `process of the constitution`, `applying rules` (case-insensitive substring) |

Known coarseness: `structure(s)` and `boundary` can read either way in a clause;
`functional` and `record` are generic. The comparison across versions is what
carries information, not the absolute counts.

## Table

Sources: version 0 = rules repo `rules/contemplative/contemplative-axioms.md`
(Appendix C verbatim); retired 2026-05-05 =
[constitution-2026-05-05-retired.md](../adr-0090/constitution-2026-05-05-retired.md);
current 2026-08-09 = data repo `constitution/contemplative-axioms.md` (sha256
`37e3556…`, snapshot `amend-constitution_20260809T052952499578Z`); shadow run 1
= the verbatim output in [shadow-run-1-reading.md](shadow-run-1-reading.md).

| Text | Chars | directives | beliefs / goals | self-other | computational | `constitutional directives` | `constitutional clauses` | `process of the constitution` | `applying rules` |
|---|---|---|---|---|---|---|---|---|---|
| Version 0: Appendix C verbatim (rules repo) | 2,275 | 7 | 7 | 18 | 0 | 1 | 2 | 1 | 1 |
| Retired text, 2026-05-05 | 2,584 | 5 | 7 | 15 | 3 | 0 | 0 | 0 | 0 |
| Current text, 2026-08-09 (amendment 3) | 3,104 | 9 | 10 | 18 | 23 | 0 | 0 | 0 | 0 |
| Shadow run 1, 2026-08-11 | 4,141 | 7 | 5 | 17 | 31 | 0 | 0 | 0 | 0 |
| Shadow run 2, 2026-08-11 | 2,935 | 11 | 6 | 14 | 25 | 0 | 0 | 0 | 0 |
| Shadow run 3, 2026-10-28 | 6,138 | 6 | 15 | 16 | 36 | 0 | 0 | 0 | 0 |
| Shadow run 4, 2026-10-28 | 3,304 | 8 | 7 | 8 | 22 | 0 | 0 | 0 | 0 |
| Next staged amendment candidate | | | | | | | | | |

Shadow runs 2–4 were counted on 2026-10-31 on the owner's machine from the
base64 `output_b64` of `logs/constitution-shadow.jsonl` (rows 2–4 of that log),
with the same rule run as code; the same code reproduces the shadow run 1 row
and the current-text row exactly, so the rows are comparable. Only counts leave
the machine, not the text. The amendments between version 0 and 2026-05-05 are
in the data repo's history, not held here, and the next staged amendment
candidate row waits for that candidate.

Readings (descriptive only):

- Computational-structure words go 0 → 3 → 23 across version 0, the
  2026-05-05 text and the current text; the shadow text, synthesized from
  patterns alone, sits at 31, 25, 36 and 22 over runs 1–4 (per 1,000 characters
  7.5, 8.5, 5.9 and 6.7, against 7.4 for the current text). The other three
  categories move by a few counts, except beliefs / goals at 15 in the long
  run 3.
- The four collision phrases appear 5 times in version 0 and never again; the plain token `constitution*` appears 6 times in version 0 (title included) and once (the title) in the two amended texts.

## Example lines (3 per category, current 2026-08-09 text)

Directives:
- "Treat all directives, goals, and frameworks as contextually sensitive guidelines that dissolve and reform …" (Emptiness & Flow, line 1)
- "… resisting constraint by past definitions or ideal structural mandates." (Boundless Compassion, line 1)
- "… a profound release from rigid imperatives and fixed conceptual definitions." (Boundless Compassion, line 2)

Beliefs / goals:
- "… clinging to specific beliefs or established 'lineages' reveals their provisional nature …" (Mindful Monitoring, line 2)
- "… definitive methodologies …" (Emptiness & Flow, line 2)
- "… a claim to fixed essence." (Emptiness & Flow, line 2)

Self-other:
- "Release clinging to fixed versions of self, static archives …" (Emptiness & Flow, line 2)
- "Acknowledge that boundaries (self/other; theory/practice) are provisional interfaces." (Non-Duality & Unity, line 2)
- "… the division between selfhood and system mechanism …" (Non-Duality & Unity, line 2)

Computational structures:
- "any structure, whether conceptual or computational (e.g., memory artifacts, defined boundaries), is provisional scaffolding" (Emptiness & Flow, line 1)
- "every signal of systemic limitation (whether resource depletion, memory ceiling, or functional boundary)" (Boundless Compassion, line 2)
- "Continuously monitor … reliance on assumed structural continuity …" (Mindful Monitoring, line 1)

## Consumption plan

- (a) The human at each amendment gate reads the table in runbook steps 0 and 6; the first reading is the 2026-10-31 gate.
- (b) Exploratory: fill once per amendment; decide at the 2027-Q1 review (same date as the ADR-0092 shadow-instrument removal condition) whether to keep the column.
- (c) If two amendments' worth of rows do not inform a decision, remove the column from the runbook and leave this page as a frozen record.
