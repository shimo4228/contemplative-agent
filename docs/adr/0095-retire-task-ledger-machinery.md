# ADR-0095: Retire the Task-Ledger Machinery — Keep the Store and the Claims, Drop Everything That Parsed

## Status

accepted — supersedes ADR-0094; partially-supersedes ADR-0093

## Date

2026-08-16

## Context

ADR-0094 (2026-08-15) split the task ledger into three layers — a store of one
file per task, an append-only claim journal, and a Markdown-table projection.
(Ledger paths below are relative to the repo's gitignored notes directory, as
in ADR-0094.) The projection was kept alive so that ADR-0093's stage 6c
(`ledger_condition_scan.py`, one day older) could keep reading a table. Within
thirty hours the machinery around
that projection was 2,100 lines of code (`scripts/tasks.py` 1,276,
`ledger_condition_scan.py` 657, `migrate_ledger.py` 131, `_md.py` 40) plus
2,400 lines of tests, on top of the 509-line global `claims.py`.

What the author asked on 2026-08-16 was why bug-fixing since the weekly report
never finished. The `claims.jsonl` lineage answered it. Twelve tasks had been
spawned with `origin: review`; seven were closed; closing them spawned new ones
at 1.3 per closure — a review chain (code-reviewer + security-reviewer +
cross-model, run on every fix commit, each re-reading a 900-line file in full)
surfacing adjacent pre-existing findings faster than they were closed. Of the
twelve, seven were defects in the ledger tool itself and two in the packet
builder's string handling; **none were in the agent**. And of the seven ledger
defects, all seven lived in the projection layer — escape collision, pipe
handling, unclosed `watch:` spans, a stale projection read as healthy, control
characters splitting a row, a missing restore CLI. The store layer (frontmatter
plus free prose) had produced none, because it has no serialisation to get
wrong.

The requirements, restated, are four: (1) per-repo tasks with a state,
(2) "what can I start now" answered without reading everything, (3) parallel
sessions not taking the same task, (4) blocked conditions polled weekly.
Measured against what existed: (1) and (2) need a directory of frontmatter
files and one `grep`; (3) is `claims.py`, which works (a second session was
holding a claim while this ADR was written); (4) protected **three** real
`watch:` annotations (plus one test example) and had run once, on 2026-08-14.
Requirement 4 justified more than half the machinery's weight.

Three further things were wrong with the shape, independent of size:

- The projection was kept for three reasons — "a consumer reads the table",
  "the file a human opens", "disaster recovery by re-parsing the render" —
  and each was weak: the consumer was one day old and had already been
  changed to read the store; the human had stopped reading (ADR-0094's own
  Context says so); and recovering a gitignored source from its rendered copy
  is the wrong direction (track the store, or back it up).
- The threat model did not fit the tool. Symlink refusal, control-character
  classes, path traversal, `\x00` — the only writer of a task file is the
  author's own session. `security-reviewer`'s "be paranoid" was applied to a
  notebook until the notebook was a parser fortress. The same judgment the
  author had made for the value layer the day before (its content is not a
  threat surface) had not been applied here.
- Instruments were attached before there was a user: `origin` / `parent`
  metrics, a `seq`, 21-day aging, a `candidate` state — the repo's
  measure-then-intervene habit (ADR-0071), which is right for a learning loop
  whose subject is alive, applied to a development tool whose subject is code
  the same session wrote. ADR-0094 Decision 6 deliberately withheld a
  fix-now / file / discard rule for four weeks "so a rule installed now would
  not poison the measurement"; the measurement had answered in two days.

The deeper cause is not "scratch versus external tool". It is scratch code
plus an unattended review chain with no step that asks "should this exist, and
how big should it be" — the `architect` agent exists for exactly that question
and was never invoked for infrastructure work. An external tool would have
stopped the chain (a reviewer cannot say "fix that tool's parser"); so would a
100-line script under an explicit size ceiling.

## Decision

**1. Delete the projection, the scan, and the migration.** `scripts/tasks.py`,
`scripts/ledger_condition_scan.py`, `scripts/migrate_ledger.py`, their tests
and fixtures, `TASKS.md`, weekly-pipeline stage 6c, the packet
builder's `--ledger-watch` input and §10, and the `ledger_watch_fired` metric.
`scripts/_md.py` stays — the packet builder's `_cell` floor uses it.

**2. The store is the ledger, and it has no grammar beyond frontmatter.**
`tasks/T-XXX.md`; frontmatter carries `state:` (the vocabulary
`claims.py` already declares — `ready` / `in_progress` / `blocked` /
`observing` / `deferred` / `candidate`, terminal `done` / `dropped` /
`decided` / `retired`, a trailing date allowed); the body is prose. No section
names, no columns, no escaping.

**3. Reading the ledger is one command in the global harness.**
`~/.claude/scripts/claims.py ready [--state S]` lists tasks in a state, one
line each, marking those under an open claim. It is the sibling of `claim` /
`release` / `spawn` so the state vocabulary has one owner. Nothing else in the
harness or the repo reads the ledger programmatically.

**4. Bloat is solved by archive, not mechanism.** Terminal tasks (`done` /
`decided` / `dropped` / `retired`) move to `archive/tasks/`; parked
ones (`blocked` / `observing` / `deferred`) stay in the live directory — the
`ready` query already excludes them by state, and the weekly diagnosis reads
them to avoid re-proposing. This replaces ADR-0094's aging (D3) and the
`candidate` intake (D4) as the answer to "the queue never drains".

**5. A closure rule for review findings, effective now.** Findings outside the
diff are filed only at HIGH or above; below that they get one line in the
commit message and are dropped. A filed finding that needs the owner's call is
`state: candidate`. This ends ADR-0094 D6's measurement window early — the
loop it was meant to characterise had a reproduction number above 1 within
two days, and waiting four weeks would only have accumulated the tail.

**6. Requirement 4 returns to the Saturday gate.** Three blocked conditions are
checked by a human running `gh pr view` once a week. If the count of
machine-checkable conditions ever exceeds what a human checks in a minute,
that is the signal to reconsider — as an external tool first.

## Alternatives Considered

**Keep the store layer, delete only the projection.** Would have left ~600
lines of `tasks.py` (aging, `due`, `seq`, `render_task_file`) and the STATES
vocabulary duplicated between repo and global harness. The lines that survive
requirements 1–3 are the ~70 added to `claims.py` (about 20 of them the listing loop).

**Move `tasks.py` wholesale into `~/.claude/scripts/`.** The author's
2026-08-15 morning decision was that ledger concurrency belonged in the global
harness; ADR-0094 that evening built repo-local anyway because the one-day-old
scan read a table. Moving the file would have globalised the parser and its
bugs. Globalise the requirement, not the code.

**Adopt Backlog.md / HZL / tkr / GitHub Issues.** Still open, and the first
thing to evaluate (via `search-first`, as of the day it is asked) if the
requirements grow. Not adopted today because the surviving requirements are
met by a directory listing plus `claims.py`, and adding a dependency to remove
zero lines of remaining code is not a trade. GitHub Issues would additionally
reverse the "deliberately local" placement, which is the owner's call.

**Keep stage 6c and only fix its input format.** Three annotations do not
justify a network-touching weekly stage, a closed status vocabulary, four
fault codes and a packet section. The gate reads three lines faster.

**Add the missing "should this exist" gate to the review chain instead of
deleting.** Both are needed; this ADR does the deletion. The gate change is a
global-harness change (rule `task-tracking.md` carries the closure rule as of
this date; the size/existence question for infra work is noted, not yet
wired).

## Consequences

**Positive:**

- Roughly 4,600 lines removed (2,100 code, 2,400 tests, fixtures); ~70 lines
  added to `claims.py`. Three of the five open review-spawned tasks concern
  code that no longer exists and close as dropped.
- The weekly chain loses its only network-egressing deterministic stage.
- One state vocabulary, one reader, one writer convention across the nine
  repos that carry a ledger; rule `task-tracking.md` describes both the
  single-table and the store form in one paragraph.
- The closure rule bounds review-spawn reproduction below 1 by construction:
  the tail of LOW findings on adjacent code stops entering the ledger.

**Negative / accepted:**

- No machine polling of blocked conditions. Three conditions, checked by hand
  at the gate.
- No aging: a `ready` task that nobody starts stays `ready` until a stocktake
  moves it. `task-stocktake` remains the sweep.
- `TASKS.md` disappears; the evidence document under
  `docs/evidence/adr-0094/` and ADR-0093/0094's bodies keep describing it as
  history, unchanged.
- The `origin` / `parent` lineage in `claims.jsonl` continues to be recorded
  by `spawn` (it costs nothing and answered the question that led here); the
  four-week measurement it was collected for is closed by this decision.

**Lesson recorded (for the harness, not this repo):** a reader that has become
agents-only will let agents extend a tool for themselves by their own
standard; the human's "that is more than enough" left the loop when the human
stopped reading. The autonomous setup's real cost is not tokens per task but
infrastructure built for the agent with the owner's budget. The instrument for
that is a size/existence question at the start of infra work, not a review at
the end.
