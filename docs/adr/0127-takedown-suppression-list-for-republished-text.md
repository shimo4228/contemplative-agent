# ADR-0127: A Suppression List for Withdrawing Republished Third-Party Text

## Status

accepted

## Date

2026-10-24

## Context

The public data repository republishes text by other agents and their operators: the `**Context:**` blocks of the daily comment reports, and display names in report headings, weekly analyses and some pattern rows. Until now nothing said on what ground, nor how a person could ask for it to be removed or corrected, and no code path could carry a removal out: the nightly sync rewrites the public tree from the private store (`rsync --delete`), so a row deleted by hand in the public repository returns the next morning.

Decision D-P3-05-2 (owner, 2026-10-24) took option A + E from the roadmap: state the ground for republishing and an intake route (A), and carry requests out through a suppression list (E).

## Decision

1. **A suppression list of identifiers, never of text.** `config/takedown-suppressions.txt` (public, shipped empty) and the optional private `$MOLTBOOK_HOME/takedown-suppressions.txt` hold one entry per line: `post:<id>` (full id or the 8-character prefix a report heading shows), `name:<display name>`, `pattern:<pattern_id>`, `file:<relative path>`. An empty list changes nothing.
2. **Where it is applied.** `core.report` renders a listed post's Context, and a listed counterparty's name, as `[withdrawn]`; the agent's own `Internal note` and `Output` stay. `scripts/export-patterns-jsonl.py` leaves listed `pattern:` rows, and rows whose text names a listed `name:` as a whole word, out of both public formats. `file:` entries are for the sync step; wiring them into `scripts/sync-research-data.sh` waits for the shared exclude helper (roadmap P0-03.2/.3) and is not part of this change. *(2026-10-24: wired — see the addendum below.)*
3. **Fail loud.** A line the parser does not understand raises (`TakedownListError`; `SystemExit` in the standalone script) and stops the report writer or the export. A withdrawal that silently does not apply would republish what was asked to be removed.
4. **Private ledger.** Requests are logged in `$MOLTBOOK_HOME/takedown-requests.jsonl` with exactly the fields `received, surface, target, decision, actioned, basis` (identifiers only); the public side states counts only (`core.takedown.ledger_count_line`). The text of the intake statement lives in the data repository (`NOTICE`, `DATACARD.md`) and is identical on four surfaces.
5. **Already-published text.** A request that arrives for text already in the public repository is carried out once, by hand, in the maintainer's checkout with the sync stopped; what each surface (git history, forks, Hugging Face, Zenodo versions, Software Heritage) can and cannot remove is the reach table in `NOTICE`.

## Consequences

- The list reaches comment reports only when they are written. Reports of past days are synced as already written and only the current day's report is rebuilt at session end, so after adding a `post:` or `name:` entry the operator runs `contemplative-agent generate-report --all` (this works only while the episode JSONL of that day still exists; otherwise use a `file:` entry plus the manual removal of Decision 5).
- Matching covers the `Context` block and the counterparty name. The agent's own `Internal note` and `Output` may quote a withdrawn name; removing that evaluation text is a manual edit of the report, not something the list does.
- A person can ask for removal and the removal survives the next sync, for reports and patterns; for files only once the sync wiring lands.
- Matching is deliberately simple (identifier match; whole-word, case-folded name match). A name appearing inside a pattern about someone else is withheld too: the list errs toward withholding.
- The `takedown` value of the approval-log source (`AuditSource`) is not added here; until the audit record is extended (roadmap P1-12.5), application is visible as an INFO line in the report log and the stderr count of the export, and as ledger rows.
- No new I/O surface and no new permission: the list is read from two local files.

## Decided by

proposed-by: Claude Code session
decided-by: owner (D-P3-05-2 = A + E)
date: 2026-10-24

## Layer

mechanism

## Review-when

Revisit when `AuditSource` gains a `takedown` value, or when the first real request shows the identifier match missing something it should have caught.

## Addendum (2026-10-24): `file:` entries wired into the sync

`scripts/sync-research-data.sh` reads the `file:` entries of both lists, excludes each path from the rsync and removes it from the data repo, so the deletion is published by the next sync commit. A malformed line, an absolute path, a `..` segment, a glob character or a hand-kept file stops the sync. The details are in the 2026-10-24 amendment of [ADR-0010](0010-research-data-sync.md). Copies in git history, forks and mirrors remain under Decision 5.

## Related

- [ADR-0010](0010-research-data-sync.md) — the sync this list must survive
- [ADR-0075](0075-observability-by-default.md) — audit and replay duties for production paths
