# ADR-0115: Where Authority Sits Between the Judge Role and the Owner — Merge Is the Judge's, Admission and Push Are the Owner's

## Status

accepted

## Date

2026-10-24

## Decided by

proposed-by: session (roadmap P1-13)
decided-by: owner
date: 2026-10-24

## Layer

governance

## Context

Two statements about who may land a change disagreed, and the disagreement was never decided.

- `docs/CYCLES.md` said, for Cycle #5, "implemented diffs merge on the human's word. Every promotion stays human", and row #6 of the master table named the gate "pre-commit diff approval".
- Since 2026-09-15 the harness side (Agent Knowledge Cycle ADR-0028) lets the task-triage loop's judge role merge task output that falls outside a protected class. The repository's own history shows it working that way: `fdbc27e` (2026-09-19) records a fast-forward merge of an implementer's worktree after the judge's acceptance check, and `82b169e` (2026-09-26) records the owner's merge and push of another session followed by the judge's after-the-fact acceptance. Both carry the owner's name as author. Of the 233 commits since 2026-09-15, none is a revert.

[ADR-0098](./0098-weekly-single-session-and-triage-delegation.md) moved repairs to the triage loop and made triage "the independent verification layer", but its subject is the weekly chain; where a merge or a push may happen was outside its scope. [ADR-0080](./0080-north-star-layered-end-state.md) says the load falls toward zero while the authority stays with a human, and does not say what a human's authority consists of at the level of a git operation. The owner's principle is that the human is the orchestrator: an AI orchestrator would dissolve the answerability that the approval gate ([ADR-0012](./0012-human-approval-gate.md)) exists to keep. A document that says "every promotion stays human" while a judge role merges is a false statement in the lineage that [Agent Attribution Practice](https://github.com/shimo4228/agent-attribution-practice) draws its worked example from.

The three-week record (no revert) is one run, not evidence of safety (the standard the owner applied to insight in D-P0-01-1).

## Decision

Take option C of D-P1-13-1 (decided as recommended by the owner, 2026-10-24): the judge role may merge, the owner admits and pushes.

1. **The judge role may merge task output that is outside the protected classes.** The merge is a git operation on a local branch. It does not publish anything.

2. **Protected classes are never merged by the judge role.** They are the files whose content changes what the agent is, what it is allowed to do, or what this document says it is allowed to do:
   - rules, identity, constitution and skills (the value layer, tracked templates included);
   - ADRs (both languages);
   - `config/prompts/` (the fixed apparatus the value layer is observed through);
   - `.claude/` (skills, hooks, `verify.sh`);
   - `scripts/weekly-*` and the watchdog (the unattended chain);
   - the assertions of `verify.sh`, CI workflows and tests that pin a boundary (dependency floor, egress, import direction, surface snapshots). Adding a test is not protected; weakening or deleting an assertion is;
   - documents that describe behaviour or authority: the README gate paragraph, `docs/CYCLES.md`, `docs/CONFIGURATION.md`, `docs/GOVERNANCE.md` itself, `docs/runbooks/*`, `CLAUDE.md`. A judge role must not be able to move its own authority line by merging a prose edit, so these are protected on the same footing as code.

3. **The owner holds two authority points that the judge role does not hold.**
   - **Admission**: whether a candidate (a filed RFC draft, a finding, a proposed change) enters the work queue at all. The judge verifies premises and says `adopt` or `reject` in the triage digest; the owner's reply admits it. Admission is the point where a new pattern crosses from findings to design: findings, then triage, then the human gate, then a route to design, and the person who bears the gap between the plan and what happened is the owner (the phase-crossing rule of Agent Attribution Practice ADR-0010).
   - **Push**: whatever leaves the machine for the public repository, the data mirror or a registry. The Saturday `/weekly-gate` session remains where unattended output is checked for sensitive content before it is committed for publication (CLAUDE.md, the section on the task ledger).

4. **Withdrawal condition.** If two merges made by the judge role are reverted for substance (not for a conflict or a rebase) within three months of this ADR or of any later re-adoption, the judge role's merge authority returns to the owner for every class, and the owner re-decides. Counting is by commit subject and trailer (`Revert`), read at the Saturday gate.

5. **Attribution.** The judge role's commits are distinguishable from the owner's by trailers (`Co-Authored-By` for AI-written commits, a session trailer for unattended ones; the vocabulary is defined in the harness commit template), so the record can be read for who did what; the commit author field alone cannot, as every commit here carries the owner's name.

`docs/CYCLES.md` is updated in the same change: row #6's gate reads "merge by the judge role outside the protected classes; admission and push by the owner", the sentence at the end of the Cycle #5 paragraph is rewritten to the same placement, and the FRESHNESS header is refreshed.

## Review-when

- A judge-merged commit is reverted for substance twice within three months (Decision 4), or the owner finds a merge of a protected class made by the judge role. Either returns merge authority to the owner at once.
- The record reaches 12 weeks with the judge role merging. Read the revert count and the share of merges that touched a protected class by mistake, then decide whether the protected list is too wide (it blocks routine work) or too narrow.
- The owner's weekly load of admission decisions rises enough that admission itself becomes the bottleneck, which is the signal to revisit what the judge may admit, not to dissolve the human point.
- The harness commit template or the harness ADR that grants the judge role its merge changes. This ADR names the placement; the grant lives there.

## Alternatives Considered

- **A. Allow the judge role to merge and push, with the protected list only.** Rejected for now. It removes the owner from the one act the public record is built on, and the supporting evidence (233 commits, no revert) is three weeks of one run. If chosen later, the scope of the human gate belongs in an ADR-0080 amendment, not a new ADR.
- **B. Return to human merge for everything.** Rejected. It would make the owner the throughput limit for edits that have no authority consequence (a test for a bug, a typo outside the protected classes) and contradicts the north-star aim of lowering the owner's load while keeping the authority.
- **Leave the text as it was.** Rejected: the lineage would keep a sentence that the history contradicts.

## Consequences

- `docs/CYCLES.md` and the harness-side ADR describe one placement. A dated note on the harness ADR records the repository's exception (push stays with the owner); that file is outside this repository and is a follow-up for the harness side.
- `docs/GOVERNANCE.md` (roadmap P1-12.7) takes its authority table from this ADR.
- The protected list is long on purpose: this repository is the agent itself, and the documents that describe its behaviour are part of its behaviour.
- The attribution trailers that make judge merges readable in the log depend on the harness commit template, which this repository does not own.

## References

- [`ADR-0012`](./0012-human-approval-gate.md) — the approval gate for value-layer proposals; unchanged.
- [`ADR-0080`](./0080-north-star-layered-end-state.md) — load toward zero, authority stays human; this ADR says what the authority is at the git level.
- [`ADR-0098`](./0098-weekly-single-session-and-triage-delegation.md) — repairs travel through the triage loop, triage is the verification layer; merge and push placement was out of its scope.
- [`ADR-0101`](./0101-instrument-dissolution-mandate.md) — the Review-when readings above are read at the Saturday gate and carry their own removal condition.
- Agent Knowledge Cycle ADR-0028 (harness side, 2026-09-15) — the grant of merge to the judge role and the protected classes; AAP ADR-0010 — the phase-crossing rule.
- Decision record: D-P1-13-1 = C (owner, 2026-10-24).
