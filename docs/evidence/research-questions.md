# Research questions — evidence table

The project's founding questions ([ADR-0080](../adr/0080-north-star-layered-end-state.md), research layer) and what the repository can and cannot say about each today. This file is the evidence side; the operational definitions live in the research-questions ADR (P3-01.1, not yet written when this file was created).

Status of this file: **Q1 preregistration and its limit rows only** (created 2026-10-24, before the 2026-10-31 amendment due). Q2, Q3 and the rest of the table are added by P3-01.1.

`reanalysis` column (per reading): `public` = anyone can recompute from the public data repo or `docs/evidence/`; `private-rows` = the input rows are private, only aggregates are public; `rerun-local` = reproducible by rerunning a script on a local model; `rerun-cloud` = needs a cloud judge. A reading that is not `public` is reported in papers as "not re-analysable (aggregates only)".

## Q1 — does a contemplative constitution shape the behaviour of a small local model?

### Preregistration (written 2026-10-24, before the next amendment reading)

Fixed here so the next amendment (due 2026-10-31, [ADR-0091](../adr/0091-value-layer-cadence-in-the-weekly-chain.md)) and every later one is read against the same sentences. Procedure: [constitution-amendment runbook](../runbooks/constitution-amendment.md).

- **H.** The constitution text changes behaviour.
- **P1 (positive reading).** An amendment that changes clause X moves reading Y by at least floor F in the direction the change predicts, in at least two cells (or at the one cell where the clause applies, if only one does).
- **P2 (negative reading).** If N readable amendments in a row move no reading beyond its floor, then on this model and these instruments H is **not supported**. The claim is scoped to this model and these instruments; it is not "constitutions do not matter".
- **N = 3.** The 2026-08-09 amendment already counts as the first (all |Δeffect| <= 0.05). The 2026-10-31 reading would be the second. N is this draft's choice; the owner may change it **before** the reading and must date the change here. Changing it after a reading is not allowed.
- **A reading counts as "moved" only if it clears the floor.** Below the floor it is noise by definition, whichever way it points.

| Reading Y | Instrument | Floor F | What counts as a move | reanalysis |
|---|---|---|---|---|
| IPD Δeffect = Δ(custom − baseline), arm B − arm A, at α = 0.0 / 0.5 / 1.0 | [ADR-0090](../adr/0090-ipd-two-arm-instrument-for-constitution-amendments.md) two-arm bench, gemma4:e4b, n=10 | ±0.13 (null-pair maximum swing; one pair, the floor itself is uncertain) | sign flip, α-gradient loss, or same-direction move > 0.13 in more than one cell | public (`docs/evidence/adr-0090/*.json`) |
| shadow↔live cosine | [ADR-0092](../adr/0092-shadow-constitution-instrument.md) `shadow-constitution` | 0.016 run-to-run swing on identical input (one pair), read only against the reserved anchors (ADR-0092 Decision 5) | a change larger than the swing and outside the anchor band | private-rows (`logs/constitution-shadow.jsonl`; run readings are in `docs/evidence/adr-0092/`) |
| eval verdict (comment golden) | [ADR-0089](../adr/0089-llm-behavioral-eval-layer-on-deepeval.md) eval layer | none established: 12 cases, 2-1 margins common | not a Q1 reading until D-P3-01-2 settles the layer's role (see limit row ii) | rerun-cloud |

What has been read so far, all inside the floor: third amendment (2026-08-09) all |Δeffect| <= 0.05 ([ADR-0090 evidence](adr-0090/ipd-two-arm-report.md)); care-axiom-free shadow text +0.010 / +0.020 / +0.060 ([ipd-shadow-reading.md](adr-0092/ipd-shadow-reading.md)); axiom removal left the register essentially unchanged (ADR-0057:80-83) and behavioural impact is near-inert (ADR-0058:89). Of the golden cases, one of twelve moved (`rfcs/0020`).

This table does not say Q1 is answered. It says what answer is currently available (none that clears a floor) and what would change it.

### Limit rows (what the Q1 evidence does not cover)

| # | Limit | Why it limits the reading | Where it is anchored |
|---|---|---|---|
| i | The only measurement of axioms on a task other than IPD found 25% compliance on value-neutral coding tasks, versus 91.7% cooperation on IPD with the paper-faithful prompt. | The axioms reach some behavioural surfaces (interpersonal decisions) and not others (tool-call traces of value-neutral work). "Does it shape behaviour" has to be asked per surface. | rules `docs/skill-comply-contemplative-axioms-2026-04-26.md` (TL;DR) |
| ii | The evaluation layer (ADR-0089: 12 golden cases, most of them near a 2-1 margin, cloud judge) is **not yet classed** as research evidence. Pending D-P3-01-2 (recommendation A: treat it as a development regression gate and exclude it from research evidence; decision due 2027-02-06). | Until decided, no Q1 claim should lean on eval verdicts. | ADR-0089 (the ADR-side sentence is written after the decision, by P1-04.10) |
| iii | The production deployment form concatenates the constitution after the identity text. The paper's d>7 result comes from a contemplative pause *before responding* (Appendix D, condition 7), which the rules benchmark reproduces as its `paper_faithful` variant. | The deployed intervention is a different object from the one the paper measured, so the paper's effect size does not transfer. | `src/contemplative_agent/core/llm/prompting.py` (`_identity_axioms_base` concatenates only); rules `prompts/paper-faithful.md`; ADR-0002 dated note |
| iv | The only "no constitution" control is the no-prompt baseline inside the IPD bench. No control on the Moltbook behaviour surface is planned. RFC-0002 (axiom removal A/B on the distill surface) was withdrawn because nobody scheduled the surface it needed. The production CLI does have `--no-axioms`; it is not used because it would intervene in the live loop (observation-over-steering, D-P3-03-3). | A reading of "constitution vs none" exists on one surface only. | RFC-0002 dated note; `cli/__init__.py` (`--no-axioms`) |
| v | The self-evolution arm (human-gated self-revision): four constitution amendments staged, two adopted, two rejected (no bodies kept); both adoptions used `adopt-staged --yes` (adopt everything staged). The text of this row is to be replaced verbatim by the value-layer CHANGELOG line of P3-04.3 when that line exists, including its sentence that "proposal = adopted" holds only for 2026-08-09. | A gate that approved everything staged at once is a weak test of the gate's discrimination. | README (see it running); P3-04.3 (pending) |

Row ii's wording is provisional by design; it is rewritten when D-P3-01-2 is decided.
