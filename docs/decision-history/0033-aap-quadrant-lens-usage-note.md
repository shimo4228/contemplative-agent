# ADR-0033: Note — Borrowing AAP's Four-Quadrant Lens as a Usage-Description Aid

## Status

accepted (note) — narrow, observational; not a category commitment. Withdraw if the lens drifts from usage observation toward category claim, following the ADR-0030 / ADR-0032 precedent (preserve the original on withdrawal).

**Corrected 2026-05-01 (same-day)**: the original Observations section had two factual errors. (1) `skill-stocktake` and `dialogue` were described as "sitting at the LLM Workflow ↔ Autonomous Agentic Loop boundary". On code re-read both have fixed control flow + bounded LLM roles per call (frozen prompt templates, fixed output schemas, no tool calls, no LLM-driven next-step decisions) — they are LLM Workflow proper, not boundary cases. `core/stocktake.py` even documents that pair-level LLM judging was deliberately removed in favour of embedding clustering + 1-shot merge. (2) `meditate` was described as outside the quadrant axis "because it does not use an LLM". The quadrant axis is not LLM-specific; `meditate` runs deterministic POMDP belief updates over an exploratory action space (numpy-only, no LLM call), which is the (2) Algorithmic Search cell exactly. Observations section rewritten below; the rest of the ADR (Decision, Self-check, Alternatives, Consequences, References) is unchanged.

## Date

2026-05-01

## Context

Since 2026-04-29, [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) articulates a four-quadrant routing lens on top of its ten attribution ADRs. The lens is presented by AAP as a *routing diagnostic*: it asks whether accountability distributes cleanly for a given piece of work, or whether a runtime *attribution gap* (a mid-execution blend of judgement that no post-hoc owner can be assigned to) is being taken on.

The four quadrants are obtained from two independent axes:

- **Horizontal**: deterministic (rule-expressible) vs semantic (LLM judgement).
- **Vertical**: defined-flow (workflow can be pre-described) vs exploratory (next step depends on runtime observation).

This produces:

- **Script** — deterministic, defined.
- **Algorithmic Search** — deterministic, exploratory.
- **LLM Workflow** — semantic, defined.
- **Autonomous Agentic Loop** — semantic, exploratory.

Selecting the Autonomous Agentic Loop quadrant is, in AAP's framing, a commitment to absorb a non-removable attribution gap on the deploying organisation's side. *Phase* (design / operation) is articulated by AAP as a third, independent dimension; it is not a quadrant.

The lens is orthogonal to AAP's ten ADRs. The ten ADRs answer *what is constrained and who is accountable*. The lens answers *which regime of accountability the work runs in at all*. The two layers are independent and intersect at the question "is this work in a regime where AAP's constraints can land?"

This project's external readers have already encountered the vocabulary through zenn articles 13 / 14 / 15 (2026-04 → 2026-04-30). They arrive at this README with the lens in hand. The vocabulary is therefore already entering the project's surface area; this ADR records on what terms it is being borrowed.

## Decision

The four-quadrant lens is borrowed in this repository as a **usage-description aid** in `README.md`, `README.ja.md`, `llms.txt`, `llms-full.txt`, and `docs/glossary.md`. The placements describe how a given CLI command typically operates. They are observations, not types.

This ADR explicitly does **not**:

- Assign Contemplative Agent a single quadrant identity.
- Treat any quadrant as a category boundary that the project sits inside.
- Frame the other quadrants as failing-other modes. They are different shapes of work this project does not currently route through.

*Phase* (design / operation) is recorded as an independent observation, not as a quadrant axis. Where a CLI command produces output that revises design-phase artifacts (skills, rules, identity), this is called a *Phase-crossing observation*, not a separate quadrant placement.

## Observations

These are descriptive observations of how each CLI command typically operates today. If a command's typical mode shifts, the description follows; this ADR does not need to be rewritten.

- Most behaviour-modifying commands — `distill`, `distill-identity`, `insight`, `skill-reflect`, `rules-distill`, `amend-constitution`, `skill-stocktake`, `dialogue` — typically operate in **LLM Workflow** mode. They have defined control flow and bounded LLM roles per call (frozen prompt templates, fixed output schemas, no tool calls, no LLM-driven next-step decisions). The promotion-producing ones land their semantic output at the [Human Approval Gate](0012-human-approval-gate.md), which is the structural reason these placements stay honest. `dialogue` belongs here even though it is a multi-turn loop, because the loop is over peer messages — at each turn the LLM is invoked once with a fixed `DIALOGUE_PROMPT` and a fixed reply schema, with no LLM-driven action selection. `core/stocktake.py` is explicit that pair-level LLM judging was deliberately removed in favour of embedding clustering + 1-shot merge, which is the structural shape of LLM Workflow rather than ReAct.
- `adopt-staged` and one-time migrations (`embed-backfill`, `migrate-patterns`, `migrate-categories`, `migrate-identity`) typically operate in **Script** mode. They are deterministic promotions of already-staged artifacts; no semantic judgement runs at execution time.
- `meditate` (the experimental Active-Inference adapter) operates as **Algorithmic Search**. It runs deterministic POMDP belief-update loops in numpy — A (likelihood) / B (transition) / C (preference) / D (prior) matrices, temporal flattening, counterfactual pruning, convergence detection — over an exploratory action-policy space, with no LLM call at runtime. The control flow is exploratory (each iteration depends on the previous belief state) but every step is deterministic, which is the (2) cell exactly. The quadrant axis is not LLM-specific; absence of an LLM does not place a command outside the quadrant axis.
- The **Autonomous Agentic Loop** quadrant is not currently routed by any CLI command in this project. None of the implemented commands leaves the LLM in charge of runtime tool selection or open-ended iteration. This is a usage observation, not a value judgement on that quadrant or on projects that route work through it. It is also a structural consequence of the existing approval gates and the One External Adapter principle, not a separate design rule.

One independent observation that is sometimes confused with a quadrant placement: `skill-stocktake`, `skill-reflect`, and the `distill` family produce output that revises design-phase artifacts (skills, rules, identity, constitution). This is a **Phase-crossing observation** — Phase (design / operation) is AAP's third dimension, independent of quadrant; it is not a fifth quadrant or a hybrid placement. In-repo anchors: [ADR-0016](0016-insight-narrow-stocktake-broad.md) (insight as narrow generator vs stocktake as broad consolidator) and [ADR-0023](0023-skill-as-memory-loop.md) (skill-as-memory loop with usage log + reflective write).

## Self-check against ADR-0032's withdrawal reasons

[ADR-0032](0032-runtime-agent-stance.md) was withdrawn the same day it was accepted because three contemplative-axiom tensions surfaced post-merge: fixed categories (vs Emptiness), self / other boundary (vs Non-Duality), and adversarial placement of other categories. This Note ADR is checked against the same three reasons:

- **Fixing categories**: The Decision section says verbatim that placements are usage descriptions, not category claims. No 4-cell grid is presented in the body — the quadrants are described prose-form, and the placements are written as "typically operates as", not "is".
- **Self / other**: There is no Contemplative-Agent-vs-other-quadrants comparison table. Quadrants are described in their own terms; the project is not contrasted against them as a separate kind.
- **Adversarial placement**: The Observations section explicitly names other quadrants as "different shapes of work this project does not currently route through", not as failing-other modes.

If, in practice, the lens hardens from usage observation into category commitment — for example, if the README begins to read "Contemplative Agent *is* an LLM Workflow agent" rather than "its commands typically operate as LLM Workflow" — this ADR is to be withdrawn following the same pattern as ADR-0030 / ADR-0032: preserve the original body, mark the status withdrawn, and record the rub in the withdrawal reason.

## Review-when

No expiry (a note: the four-quadrant lens is a usage-description aid, not a type system); revisit only if AAP changes its quadrant definitions.

## Alternatives Considered

- **Worldview ADR (4-quadrant lens as project worldview).** Rejected. The shape is structurally identical to ADR-0032's "5-category" claim and would re-trigger the same Emptiness / Non-Duality / adversarial-placement tensions. Withdrawing on the same day twice in two months is not a healthy pattern; the avoidance is part of why this ADR exists at all.
- **Operational ADR with a placement table in the Decision section.** Rejected. A table in the Decision section reads as load-bearing; once accepted, future readers cite the table as the project's commitment. Even soft tables drift toward category reading. Prose observations are softer and easier to revise without an ADR amendment.
- **No ADR; only update README / llms.txt / glossary.** Rejected on legibility grounds. New vocabulary entered the project's facing docs without an audit trail explaining when and why; future readers (human or LLM) would have to reconstruct the borrowing from commit messages. ADR-0032's withdrawal note explicitly says *no new ADR is needed for the AAP-attribution-ADRs / runtime-context relation*, but the four-quadrant lens is a different layer (post-dating ADR-0032 and orthogonal to the attribution ADRs), so a Note ADR for the lens does not contradict that prior judgement.

## Consequences

- README, llms.txt, llms-full.txt, and glossary gain small entries naming the quadrant lens and how its vocabulary is used here. No code change.
- Future capability proposals can be discussed in quadrant vocabulary without committing the project to a quadrant identity. A proposal can read "this would route work through the Autonomous Agentic Loop quadrant; we do not currently take that route" without that being a worldview violation.
- The Autonomous Agentic Loop quadrant remains a *quadrant the project does not currently route work through*. This is a usage observation, not a value judgement on that quadrant or on projects that do route work through it.
- This ADR can be withdrawn cheaply. The lens is not load-bearing for any other ADR; removing the README / llms.txt / glossary entries and marking this ADR withdrawn would leave the rest of the repository unchanged.

## References

- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) — ten attribution ADRs and the four-quadrant routing lens.
- [ADR-0002](0002-paper-faithful-ccai.md) — contemplative axioms (Laukkonen et al. 2025, Appendix C). The values layer the self-check above runs against.
- [ADR-0012](0012-human-approval-gate.md) — Human Approval Gate. The structural mechanism that keeps LLM-Workflow-typical commands' placements honest.
- [ADR-0016](0016-insight-narrow-stocktake-broad.md) — Insight narrow / stocktake broad. In-repo anchor for the Phase-crossing observation.
- [ADR-0023](0023-skill-as-memory-loop.md) — Skill-as-memory loop. In-repo anchor for design-phase artifacts being revised by operation-phase output.
- [ADR-0030](0030-withdraw-identity-blocks.md) — precedent for narrow / consolidating ADRs that supersede or withdraw earlier work.
- [ADR-0032](0032-runtime-agent-stance.md) — withdrawn worldview ADR; precedent for preserving original on withdrawal and for the axiom-tension self-check applied here.
- zenn articles 13 / 14 / 15 (2026-04 → 2026-04-30) — already linked from the README "Development Records" section. The vocabulary used in this ADR's Observations section is shared with those articles.
