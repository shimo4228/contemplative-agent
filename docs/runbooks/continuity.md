# Continuity: Minimal Instructions for a Successor

One page for whoever finds this repository while its owner cannot act, for
any reason and for any length of time. It assumes **no funding, no staff and
no organisation behind the project**: everything below can be done by one
person with a web browser, or not done at all.

Operator-unavailability policy (who may stop or continue, and after how many
weeks without a gate) lives in
[GOVERNANCE.md, "Operator unavailability"](../GOVERNANCE.md#operator-unavailability).
The ordered procedure for
ending the run on purpose is `wind-down.md`. This page is the
short version for a third party.

## What to do

**Nothing is a correct answer.** The research outputs are already safe
without anyone acting:

- Every Zenodo version is immutable and keeps its DOI.
- The code, the rules and the data repositories on GitHub stay readable.
- The public data mirror stops at its last successful sync; the agent runs
  only on the owner's own machine and stops when that machine does.
- The agent has no standing permissions elsewhere: its only outward
  operation is HTTP requests to one platform account (ADR-0015), and it
  cannot reach any other account. A stopped machine means a stopped agent.

**If you can do one more thing: archive the repositories on GitHub**
(Settings, "Archive this repository"), data repository first. That turns a
silent stop into a declared one. Archiving the data repository before the
planned final deposit is accepted as the lesser harm. Do not edit files, do
not delete anything. Do not unarchive on your own: if a person reports
harmful or third-party text, tell the owner (contact links on the owner's
GitHub profile), because
unarchiving for a takedown (unarchive, remove the text, archive again) is
the owner's act (see the incident-response runbook, section 5).

**What to leave alone.** Do not use, share or search for credentials. The
design never asks anyone but the owner for a key (security by absence),
and nothing here needs one.

## Accounts that exist (names only)

No keys, tokens or passwords are written here or anywhere in the repository.

| Surface | Name / where | Needed for |
|---|---|---|
| GitHub | the repositories linked from the README (main, data, rules and the siblings) under the owner's account | archive; public read |
| Hugging Face | the dataset repositories mirrored from the data and graph files (see data card) | read; takedown deletion |
| Zenodo | versions linked by the DOI table in the README | read only; versions are immutable |
| ORCID | the iD in `CITATION.cff` and the data card | attribution only |
| Moltbook | the agent's account named in the README | read only; left as it is (wind-down, D-P4-02-1) |
| Private backup | a private repository, the only off-machine copy of the raw episode logs (see [runtime-backup-restore.md](runtime-backup-restore.md)) | restore; never published |

The private backup is **not** for a successor to open: it holds raw
third-party text. Only an operator who has been handed the project
(see [operator-handoff.md](operator-handoff.md)) uses it.

## Decision on record

| Date | Decision | Detail |
|---|---|---|
| 2026-10-24 | D-P4-03-1 = B (owner, as recommended): one successor may be named, with **archive-only permission and no keys** | **Successor: not named yet.** Until a name is written here with a date, the page reads as "no successor": do nothing, or archive. GitHub's successor setting has not been checked or set: `<owner to fill: yes/no, date>`. |

When a successor is named, write the date, the name of the account (not
contact details) and what was granted. Granting is limited to repository
archive rights; the single line added to the audit record is described in
[operator-handoff.md](operator-handoff.md).

## Related

- `wind-down.md` — the order for ending on purpose.
- [incident-response.md](incident-response.md) — if something harmful is
  found in the published record.
- ADR-0080 amendment (2026-10-24) — review events; nothing here is a stop
  condition.
