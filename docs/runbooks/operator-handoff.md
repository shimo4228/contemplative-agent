# Operator Handoff Checklist

What changes when the **accountable operator** (the one named human who
approves behaviour-modifying changes and answers for the agent) changes.
Rationale: in agent-attribution-practice ADR-0008, changing the accountable
operator is itself a behaviour-modifying change and requires approval from
both the outgoing and incoming operator, and the handoff is explicit and
logged. This checklist is only the rows that are specific to a transfer of
responsibility.

It assumes **no funding, staff or organisation**: a handoff is one named
person to one named person.

## Scope depends on D-P4-03-1

D-P4-03-1 = B (owner, 2026-10-24, as recommended) is the standing decision
(see [continuity.md](continuity.md)).

| Situation | Rows to use |
|---|---|
| B — a named successor with archive-only permission (the standing case) | Only: grant archive permission on the repositories, and write **one** dated record of the grant (row A and row F: a CHANGELOG line). No key changes hands; nothing below it applies. |
| No successor named (A) | Nothing is executed; this runbook only exists. |
| The operation itself is handed over (a transfer of the project, or a future succession) | All rows. |

## Checklist (full handoff)

Each row has a check that can be run or read.

| # | Row | Check |
|---|---|---|
| A | The outgoing and the incoming operator are both named in the record and both approve. | The handoff record names both accounts (see F). |
| B | The `approver` of audit rows switches. The source of truth is the `Accountable operator:` line of `docs/GOVERNANCE.md` (ADR-0116 D3); `MOLTBOOK_OPERATOR` and `--approver` only let a named human sign for themselves, and nothing in the code fills the name in. Update that line in a commit (the old operator stays as a `Registered approver:` line for the versions they signed); from then on each gate decision carries the new name in its `approver` field. | `grep -n 'Accountable operator' docs/GOVERNANCE.md` shows the new account and date, and `scripts/value_layer_approval_join.py` no longer reports the new name as "not in the registry". |
| C | Curator / contact in the data repository's NOTICE and DATACARD. | `grep -n -i 'curator\|contact' NOTICE DATACARD.md` in the data repository names the new person or alias. |
| D | `authors` in `CITATION.cff` and `.zenodo.json` (main and data) — a person who authored a version stays listed on it; the new operator is added, not substituted. | `grep -n 'family-names' CITATION.cff` lists both for versions they touched. |
| E | Footnote for the sibling practice repository: CA's empirical answer to ADR-0008 Open question 5 ("revocation and departure"). Writing it back to that repository is tracked in P3-06 and is not done here. | The footnote text exists in this repository's write-back table (P3-06.7, *planned*). |
| F | **The handoff itself is recorded in the audit log**, as an approval-style row naming both operators, the date and what was granted or revoked. | The `approver` field exists (P1-12, ADR-0116), but `audit.jsonl` has no source value for a handoff and a hand-written row would break the `prev` chain. So the record is the `docs/GOVERNANCE.md` commit of row B (both names, the date, what was granted or revoked, in the commit message) plus a dated CHANGELOG line. An audit source for handoffs is added only when a real handoff needs one. |
| G | Credentials and machine: see the technical steps in `docs/runbooks/machine-rebuild.md` *(planned, P2-04.23)* — re-issuing credentials, backup repository access and re-installing launchd jobs are not repeated here. | One reference line only. |
| H | The outgoing operator's credentials for this project are revoked (use the credential table in `wind-down.md` as the list of locations). | The credential table's checks for the outgoing person's accounts pass. |

## What a handoff does not do

- It does not change the value layer (identity, constitution, skills,
  rules): those change only through the approval gate.
- It does not widen what the agent can reach. A new operator receives the
  authority to approve, not new external surfaces (ADR-0015).
