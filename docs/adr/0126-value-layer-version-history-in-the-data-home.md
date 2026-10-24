# ADR-0126: Value-Layer Version History Lives in the Data Home

## Status

accepted — partially-supersedes ADR-0030

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session (roadmap front-load bundle P3-04)
decided-by: owner (D-P3-04-1 = C)
date: 2026-10-24

## Layer

mechanism

## Context

`identity.md` and the constitution are replaced in place on adoption. Before this
ADR the only copies of an earlier version were the run-start copies inside pivot
snapshots (ADR-0020), a pool that the daily `distill` runs used to push out of
its 100-slot window (now fixed per kind, ADR-0020 amendment 2026-10-24), and the
private `audit.jsonl`, which carries a hash and not the text. The public data
tree therefore held no time-ordered list of adopted versions. Of the 6 adopted
identity revisions only 3 survived in public snapshots (694 / 894 / 954 B; a
fourth, 971 B, is the live file), and the constitution's second version
(2026-03-27) is nowhere in the tree except as quotations in a report.

ADR-0030 withdrew ADR-0025's per-block history wiring and gave, as one of its
reasons, that "pivot snapshots plus `audit.jsonl` already provide full-text
identity replay" (Context 3). That reasoning was about a history *inside*
`identity.md`, at block granularity. It does not cover a public, per-version
record outside the file, and the snapshot half of it stopped being true for the
reasons above. ADR-0010 already named `history/identity/*` as a sync target,
but nothing produced it.

## Decision

1. **A verbatim copy of each adopted version is written under `$MOLTBOOK_HOME`
   at adoption.** Identity goes to `history/identity/<UTC ts>-<sha12>.md`; the
   constitution to `constitution/history/<UTC date>-<sha12>.md`. The file is the
   adopted bytes, nothing added, so `sha256(file)[:12]` equals the suffix and
   the live file's hash at that moment. The writer is `core/value_history.py`,
   called by both write paths (`adopt-staged` and the direct approval in
   `_handle_single_result`) only when the write replaced the canonical file.
2. **It lives in the data home, not only in the data repo.** `sync-data` rsyncs
   the home with `--delete`, so a file placed only in the repo would be erased
   at the next run. The constitution loader and the snapshot copier both read
   `constitution/*.md` flat, so the subfolder changes neither the injected text
   nor the snapshot contents.
3. **Best-effort, never blocking.** The adoption is already written and audited
   when the copy is made; a failure is logged as a warning and never undoes it.
   An existing file of the same name (same date, same bytes) is left as it is.
4. **Earlier versions are seeded once.** The versions that predate the writer
   are in `docs/evidence/value-history/seed/`, applied to the home with
   `cp -Rn` (no overwrite). Retroactive names carry the first snapshot that
   holds the text, which is an upper bound on its adoption time. The
   2026-03-27 constitution is a reconstruction from the amendment report's
   quotations, marked as such in its first lines, and its hash is unknown. The
   identity versions not present in any public snapshot, and the full count of
   adopted revisions, need the private audit log and the owner's machine.
5. **Scope against ADR-0030.** This supersedes ADR-0030 only in the claim that
   snapshots plus audit make a per-version identity record unnecessary, and in
   its end state of "no history". ADR-0030's withdrawal of ADR-0024 / ADR-0025
   stands in full: no block scheme, no sub-addressing inside `identity.md`, one
   file one concern. A history file is a whole-file copy in its own directory,
   which is the shape ADR-0030 pointed to when it said a concern that needs its
   own record belongs in its own place.

## Review-when

Revisit if a third value-layer file is replaced in place on adoption, if the
public tree stops being a sync of the home, or if the history grows large enough
(identity: about 1 KB per adoption) that a retention rule is wanted.

## Consequences

### Positive

- A clone of the public data repo lists every adopted constitution and identity
  version in time order, each hash-checkable against the ADR-0090 provenance and
  the live file.
- `constitution/CHANGELOG.md` and the lineage table can point at files instead
  of at a commit archaeology that a shallow clone cannot do.

### Negative

- A second copy of each version exists. Cost is a few KB per adoption.
- The history carries no provenance (who, which route); that stays in the
  private audit log, and the CHANGELOG is the readable ledger.

## References

- [ADR-0030](0030-withdraw-identity-blocks.md) — partially superseded (Context 3's reasoning only)
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — the run-start copies, and the per-kind retention amendment
- [ADR-0010](0010-research-data-sync.md) — the sync that names `history/identity/*`
- [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md) — the hashes the history is checked against
