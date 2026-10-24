# Dated note: the 2026-08-15 identity twin (`identity-2.md`)

Recorded 2026-10-24 (P3-04.2). A correction to the identity version record, not
a change to ADR-0091's decision.

## What happened

On 2026-08-15 an approved `distill-identity` candidate was written as
`identity-2.md` instead of replacing `identity.md`: the collision guard
(`approval._collision_free_path`) saw the existing canonical file and minted a
twin. `IDENTITY_PATH` is a fixed single path, so the twin was never read; the
live identity did not change while `audit.jsonl` said `approved`. The same shape
had hit the constitution on 2026-08-09 (`contemplative-axioms-2.md`, where the
runtime concatenated both files; see ADR-0090). The fix is
`cli/adopt.py::_replaces_canonical_target`, whose docstring carries both dates.

The identity was repaired by hand between 04:02Z and 04:17Z the same day.
The two public snapshots on either side show it:

| Snapshot | `identity.md` | sha256 (first 12) |
|---|---|---|
| `distill-identity_20260815T040249Z` (run start) | 694 B | `151e91304927` |
| `skill-stocktake_20260815T041708Z` | 894 B | `4003cf001aca` |

There is no `audit.jsonl` row for the repair itself: it was a hand edit outside
the approval gate, a value-layer change with no audit row. How such a
correction is recorded from now on (a `command: correction` row) is the work of
P1-12.4; this note is the record for the case that predates it.

## Where it shows in the history

The 894 B version is `history/identity/20260815T041708Z-4003cf001aca.md`
(ADR-0126; the timestamp is the first snapshot that holds it, an upper bound on
the repair time). The `identity-2.md` file itself is not preserved. No ADR or RFC mentions
`identity-2` besides the `_replaces_canonical_target` docstring this note cites.
