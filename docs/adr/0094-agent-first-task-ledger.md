# ADR-0094: Agent-First Task Ledger — Store / Journal / Projection

## Status

accepted

## Date

2026-08-15

## Context

The task ledger was one Markdown table, `TASKS.md`, inside the repo's
gitignored notes directory. (Paths below are relative to that directory; it is
deliberately local, which is why the weekly chain polls it and no cloud agent
can.) Measured on 2026-08-15, before this change:

| Section | Rows | Chars | Breakdown |
|---|---|---|---|
| Pending | 71 | 64,090 | ready **6 (8.5%)** / blocked 15 / observing 15 / deferred 19 / **done 16** |
| Done / Dropped | 41 | 36,482 | done 40 / decided 1 |

112 rows, 102,111 characters — roughly 68k tokens re-scanned every time a
session opened the file to find the six actionable rows. Sixteen completed
rows had never been swept out of Pending. No other repo's ledger exceeds 15k
characters; this one was the outlier by a factor of seven.

**The reader changed.** The author stopped reading the table and now receives
explanations from a session instead (2026-08-15 instruction). That dissolves
the scaffold the single table was built on — "one view a human can scan" —
and rule `akc-cycle.md` says to dissolve a scaffold once it starts obstructing
rather than supporting.

Four problems were named, and the investigation reframed each:

| Reported | What it actually is |
|---|---|
| Bugs found mid-fix pile up as `ready`; the queue never drains | No separation between *discovery* and *task creation*: a finding becomes a permanent backlog node immediately |
| Parallel sessions collide, state unknown | Last-write-wins on a shared mutable file. `claims.py` addressed who-holds-what; the table itself was untouched |
| `ready` rows sit untouched | The six actionable rows were buried in 64k characters — the loop was waiting on a human to start it |
| `blocked` / `deferred` consume attention | 49 rows that were correctly decided-and-parked stayed in view permanently |

**External state of the art (as of 2026-08-15, three independent research
passes — one local, two commissioned).** Loop engineering was named in June
2026 and graph engineering in July; the settled points are that a loop must
mechanically distinguish *done* from *stuck* ("a loop that cannot… keeps
spending tokens") and that one collapses a graph back into a loop when nothing
is lost by doing so. All three passes independently concluded that **the
fix-now / file / discard decision rule and the bound on work-node growth
remain unanswered** — no published policy, no measurement. Claim Plane
(arXiv:2607.21909, 2026-07-24) addresses whether an agent is *authorized* to
change something, explicitly not whether a discovered task is worth filing.

Three external recommendations were rejected on evidence:

- **Compress the prose to 3–5 lines.** The cited support (arXiv:2602.11988)
  studies *repository-level* context files, not task records, and found the
  harm in repository overviews while instructions were followed effectively.
  arXiv:2607.12161 then measured a 38.4% cut in delivered tool-output tokens
  that **raised** billed cost by 6.8% (r=0.15) and lowered patch-application
  success, because prompt-cache traffic dominates input cost. Compression is
  not the lever; not reading is.
- **Force the sweep with a Stop hook.** ADR-0035 retired three Stop hooks here,
  wiring included.
- **WIP=1.** The author runs parallel sessions deliberately.

Two defects surfaced during migration, both invisible until now:

1. **The table was already malformed as GFM.** Two rows carried an unescaped
   `|` inside a backtick span (`` `O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW` ``) and
   one used `|Δ効果|` as absolute-value notation. A renderer reads these as
   extra columns — one row split into 8 cells instead of 5. Nothing caught it
   because no human renders the file and `ledger_condition_scan.py` reads only
   the first two cells.
2. **Concurrent edits are frequent.** During this session alone, another
   session moved four `ready` rows to done/decided, deleted one row outright
   (`T-CARE-DISSOC`, no trace anywhere), and later added two more rows — inside
   a two-hour window.

## Decision

**1. Three layers.**

| Layer | Location | Source of truth for |
|---|---|---|
| store | `tasks/T-XXX.md` | state and body, one file per task |
| journal | `claims.jsonl` | who holds what, and lineage (`claims.py`) |
| projection | `scripts/tasks.py` output | `TASKS.md` is a render artifact |

Separate tasks are separate files, so last-write-wins cannot silently drop an
unrelated edit. `TASKS.md` keeps being generated because exactly one consumer
parses it directly — `ledger_condition_scan.py`, the seventh deterministic
intake (ADR-0093) — and that consumer stays unmodified.

**2. Markdown with leased claims, not SQLite.** SQLite wins on exactly one
axis: an atomic claim becomes *prevention* (`UPDATE … WHERE state='ready'`
returns 0 rows to the loser) rather than *detection*. Everything else favours
files: an agent reads them with `Read`, they survive a broken toolchain and a
cold start, one corrupt file does not take the rest with it, and no schema
migration exists to maintain. Detection plus lease expiry is enough until the
journal actually records a collision.

`claims.py` gains `--lease-hours` (default 24). An expired lease can be taken
over without `--force`. This does not contradict the module's original
refusal to auto-release: a lease is **declared at claim time**, so judging it
expired needs no liveness check on the holder, and therefore is not the
check-then-act race that refusal was protecting against. STEALABLE (declared
lease expired) and STALE (old, no declared expiry) stay distinct; only the
former justifies a takeover.

**3. Aging, not a cap on `ready`.** A `ready` row that has not moved for
`stale_after` (default 21d) is demoted to `candidate`. A cap would have to
decide *what to drop* on every overflow, and that decision needs a decider —
the human who stopped reading. Time needs no decider, and demotion is not
deletion, so being wrong is cheap. `blocked` / `observing` / `deferred` never
age; they are waiting on something real.

**4. One new state: `candidate`.** It serves as the aging demotion target and
as the intake for work discovered mid-task, extending the existing "候補台帳は
台帳ではない" principle from skill `task-stocktake` (written for wiki-harvest
candidates) to discovered defects. `observation` was considered and **not**
added: two unmeasured mechanisms introduced together cannot be told apart
afterwards.

**5. The bodies are not compressed.** The longest row is deliberately long
("この行は状況分析の材料だけを置く — 解法は書かない"), and the measurement
above says compression costs more than it saves.

**6. No fix-now / file / discard rule yet.** `claims.py spawn` already records
`origin` and `parent`. Four weeks of that data comes before any rule, because
a rule installed now would poison the measurement meant to justify it.

## Alternatives Considered

**SQLite (WAL) with CAS claims** — the shape HZL, Beads (Dolt) and the Gemini
CLI Caretaker converge on, and the one a commissioned research pass
recommended. Rejected for now, not on principle: it buys prevention over
detection, and costs direct readability (every reader needs the CLI), a schema
to migrate, and a single file whose corruption takes all 113 tasks. Revisit
when `claims.jsonl` records an actual lost write.

**A WIP cap on `ready`** — see Decision 3. The overflow decision has no owner.

**Filesystem locking on the table** (Backlog.md's answer; their PR #860 on
2026-08-07 measured 7 of 8 concurrent writes silently lost before the fix).
Correct for their shape, but they keep a single mutable table per checkout;
splitting the file removes the contention instead of arbitrating it.

**Adopting Backlog.md / HZL / tkr wholesale.** All three are git-native and
agent-readable, and all three would require rewriting the weekly-chain wiring
(watch annotations → packet §10) and the four scripts that touch the ledger,
to arrive at what `tasks.py` already provides against the existing grammar.

**Leaving `TASKS.md` authoritative and only trimming the rows.** Does not
address last-write-wins, and the measurement says trimming is the wrong lever.

## Consequences

**Positive:**

- A session reads 242 characters (`tasks.py ready`) instead of 105,471 — a
  99.77% reduction, measured post-migration.
- The Pending section holds zero completed rows for the first time; the sweep
  is structural rather than a chore nobody does.
- Separate tasks are separate files: the class of silent loss that removed
  `T-CARE-DISSOC` cannot recur for unrelated rows.
- `origin` / `parent` become measurable at filing time. The previous attempt
  to ask "where is the work coming from" fell back to regex over prose and
  produced numbers whose accuracy could not be guaranteed.
- The GFM defect is fixed on the way through: the render escapes **every** pipe
  in a cell, not only those inside code spans (the second malformed row used
  `|Δ効果|` in plain prose, which code-span escaping does not reach), and a row
  that will not split into five cells aborts migration rather than migrating
  half a task. Reading is therefore dialect-aware — only the legacy dialect
  tolerates bare pipes inside code spans, since only the old table had them.
  *Corrected 2026-08-15:* escaping every pipe was not enough, because the first
  spelling also folded an already-escaped pipe onto itself to stay idempotent —
  so a body containing `a\|b` rendered to the same bytes as an escaped pipe and
  read back as `a|b`, losing the backslash in silence on the one path that
  turns a rendered ledger back into a store. The cell now escapes backslashes
  and then pipes, reading is a single left-to-right pass, and idempotence is
  given up (a test walks the module's AST to keep `render_row` the only
  caller). Consequence to know when recovering: a ledger rendered *before* that
  date reads back exactly except for bodies holding `\\`, so the projection was
  re-rendered from the store in the same commit. Accepted alongside it: a body's
  backslash inside a code span now *displays* doubled, since GFM escapes pipes
  inside code spans in a table but offers no escape for a backslash. The two
  requirements are mutually exclusive, and this ADR's premise — the reader is
  agents, nothing renders the file — is what makes the byte-exact side the one
  worth having.

**Negative:**

- **Direct edits to `TASKS.md` are now discarded on the next render.** The
  hook announces this whenever any session touches the file, but a session
  that started before the switch has not read the announcement. This is a real
  window, accepted knowingly; the alternative (keeping both authoritative) is
  worse because drift proceeds silently.
- `stale_after: 21d` is a placeholder, not a measurement. No published study
  compares ready-WIP or discovery-admission policies for coding agents. Ready
  rows migrated with `state_since` set to the migration date, so the first
  cohort ages out together.
- Two representations of the same data now exist (store and render). They are
  kept consistent by a test that re-runs `ledger_condition_scan.py` against the
  rendered table and compares its parse surface, not by discipline.
- `T-CARE-DISSOC` was not restored (author's decision, 2026-08-15). Whether it
  was an intentional deletion or a lost write remains undetermined, and the
  journal did not yet exist to say which.
