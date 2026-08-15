# ADR-0093: Repo-Plane Deterministic Intakes — Docs Consistency and Ledger Condition Watch

## Status

accepted — adds `scripts/docs_consistency_scan.py` (stage 6b) and
`scripts/ledger_condition_scan.py` (stage 6c) to the unattended weekly chain
(ADR-0085), packet sections §9/§10 and metrics fields
`docs_findings` / `ledger_watch_fired` to `build_decision_packet.py`, and the
`watch:` annotation convention to the task ledger. Changes no LLM stage, no
runtime-agent behavior, and no approval boundary.

## Date

2026-08-14

## Context

A structured consideration of Boris Cherny's scheduled-cloud-agent
("routines") maintenance experiment
([evidence](../evidence/adr-0093/cloud-routines-consideration.md), facts
as-of 2026-08-14) concluded that the concept imports nothing into this
project as-is: its proposer/promoter split is the shape Cycle #5 already has
(ADR-0085), its eleven routine types are covered by existing deterministic
gates or contradict the mechanism-layer north star of ADR-0080, and the
assets a cloud clone can see exclude everything the weekly chain actually
needs (episode logs, the local LLM, the gitignored task ledger).

The friction points of that comparison, however, exposed two holes in the
*current* pipeline — both with observed instances, satisfying the
signal-first bar for building an instrument (ADR-0071):

1. **Nobody systematically reads the docs corpus.** Two real instances of
   the defect class exist: ADR-0081 carried a refuted safety argument as
   `accepted` prose until 2026-08-08, and the task ledger cited a
   rules-file clause that no longer existed — both caught *incidentally* by
   a reviewer doing other work. The docs-language policy ("`.ja.md` updated
   in the same PR", "ADRs must not reference the gitignored local notes
   directory",
   CODEMAPS freshness headers) is stated in CLAUDE.md but enforced by
   nothing.
2. **Blocked-task unblock conditions are written once and never re-read.**
   The knowledge-staleness rule requires expiry/unblock conditions on
   proposals; the ledger records them (e.g. T-OLLAMA-TOKENIZE waits on
   ollama/ollama#12030), but no mechanism polls them. A condition can fire
   and the task stays blocked until a human happens to remember.

Both holes are repo-plane (they concern the checkout and the ledger, not
runtime data), and both decompose into a deterministic 80% that needs no
LLM. The weekly chain already has the correct slot for exactly this shape:
the dead-code intake (stage 6, T-DEADCODE-INTAKE) — detection wired straight
to the decision packet, bypassing the diagnosis→fix LLM stages, with all
action reserved to the Saturday human gate.

## Decision

Add two deterministic intakes to `weekly-pipeline.sh`, mirroring the
dead-code stage's contract (JSON artifact under `$MOLTBOOK_HOME/pipeline/`,
the `uv run --no-sync` discipline — no unattended network package
resolution — reason-coded degradation, packet section + metrics field,
action reserved to the gate):

**Stage 6b — docs consistency (`scripts/docs_consistency_scan.py`, 6th
deterministic intake).** Read-only over the repo checkout's self-authored
docs (docs/**, CLAUDE.md, READMEs; symlinks skipped). Findings:
`enja_drift` (an ADR's English canonical committed after its `.ja.md` twin),
`broken_link` (relative Markdown link with no target; fenced blocks and
inline code spans excluded), `notes_ref` (an ADR citing the gitignored local notes directory — broken
in every clone). Readings (no threshold, never findings): age and commits-behind
of every CODEMAPS/CYCLES freshness header, both stamp dialects. Faults
degrade per-check into an `errors` list (`GIT_FAIL`, `FILE_UNREADABLE`)
rendered as `DOCSCAN_PARTIAL`; only an unusable repo root abstains nonzero
(`DOCSCAN_FAIL`). Stateless by design: a finding recurs weekly until fixed —
for repairable defects the nag is the feature (contrast: `api_drift_scan`
flags once because platform drift is not repairable from this side).

**Stage 6c — ledger condition watch (`scripts/ledger_condition_scan.py`, 7th
deterministic intake).** Parses `watch:` backtick-span annotations on
**blocked** ledger rows — `gh-pr owner/repo#N`, `http-status URL CODE`,
`http-post-status URL CODE`, `file-exists PATH` — and reports each
condition's current state. Rows in any other state are out of the contract
by definition: a resolved task's surviving annotation stops polling instead
of alerting forever (2026-08-14 codex review). `http-post-status` targets
are restricted to loopback hosts — an unattended empty-body POST is
state-changing on lazy services, and the only legitimate POST target is the
local Ollama probe (2026-08-14 security review).
`fired=true` means the state moved toward "the unblock condition may now
hold"; acting on it stays a human decision. Security contract: response
bodies never reach the output; the GitHub PR state maps onto the closed
vocabulary {open, closed, merged} and anything else becomes a
`SCHEMA_DRIFT` reason code, so no platform-controlled string can enter the
packet the gate session reads. Requests are timeout-bounded; network faults
degrade per-watch (`UNREACHABLE`, `PARSE_ERROR`, `HTTP_ERROR`), and
`fired=null` (state unknown) renders in the packet rather than passing as
"still blocked". This intake runs in the local chain *because* the ledger is
local and gitignored — the cloud-agent consideration bounced off exactly
this boundary.

**Packet/metrics contract.** §9 renders on findings or a degraded scan; §10
renders on fired watches, faulted watches, or malformed annotations; quiet
weeks add nothing (signal-first, same as §5/§8). Metrics fields follow the
None-vs-0 discipline: `None` = not scanned this week, `0` = scanned clean.

Semantic staleness — a *claim* refuted by later evidence, the LLM-judgment
20% of hole 1 — is explicitly out of scope for the unattended chain. If it
is ever automated, it enters as a human-triggered session first, with
shadow-mode validation (ADR-0076 pattern) before any unattended wiring.

## Alternatives Considered

**Scheduled cloud agents (the trigger idea).** Rejected for the maintenance
role: zero of the eleven routine archetypes import (three have no target
here, four duplicate existing coverage — deterministic gates, the
stocktake commands, or the weekly fix chain — and four cut against
existing disciplines: ADR-0080's "done = it stops moving", chaos-TDD's
deterministic fault catalog, the mutation-testing culture). The full
analysis, including the two candidate shapes that survive as *observation*
roles (an ADR-consistency one-shot; an off-host mirror heartbeat, deferred
signal-first with its cheapest form being a GitHub Actions workflow on the
data repo, not a cloud routine), is preserved as
[evidence](../evidence/adr-0093/cloud-routines-consideration.md).

**LLM-based docs staleness scan in the unattended chain.** Rejected:
unvalidated stochastic judgment on a one-way surface (the packet) violates
the shadow-first discipline (ADR-0076), and the deterministic subset already
covers both observed instances' *detectable* halves.

**External link checkers (lychee, markdown-link-check).** Phase-0
search-first pass, as-of 2026-08-14: they cover only the `broken_link` check
(one of four), add a non-stdlib toolchain dependency to an unattended chain
that deliberately resolves nothing from the network (the `uv run
--no-sync` discipline at the dead-code stage), and cannot express the repo-specific checks
(enja pairing, the notes-dir ban, freshness dialects). A ~40-line stdlib
extractor follows the established scan-script pattern instead.

**Stateful flag-once semantics for docs findings.** Rejected: the
api-drift instrument flags once because the platform's schema is not this
repo's to fix; a docs finding is repairable, so recurring visibility until
repair is the desired pressure, and statelessness removes the
state-promotion machinery (emit-aside, atomic rename) the other intakes need.

**Cron-driven local scans outside the weekly chain.** Rejected: the chain
already owns the Saturday cadence, the packet is the one place the gate
reads, and a second scheduler would add an operational surface for no
added signal.

## Consequences

**Positive:**

- The observed defect class is now instrumented: the first dogfood run found
  22 real findings (2 `enja_drift` — ADR-0053, ADR-0060 — and 20
  `notes_ref` across six ADR pairs) and 0 broken links; these reach the
  2026-08-16 packet as §9 rows for human triage.
- Ledger conditions are polled weekly (3 watches live at adoption:
  ollama#12030 state, the local `/api/tokenize` probe, `cloud.env`
  presence); a fired condition surfaces in §10 instead of waiting on human
  memory.
- Both intakes reuse the dead-code stage's proven contract — detection/action
  separation, reason-coded degradation, signal-first rendering, None-vs-0
  metrics — so the gate's reading model does not grow a new shape.

**Negative:**

- The unattended chain gains a bounded weekly network egress
  (api.github.com, localhost probes). Mitigated by the closed-vocabulary
  mapping and body-free output, but it is a new egress where there was none;
  disabling the stage (`MOLTBOOK_PIPELINE_STAGES` without `ledgerwatch`)
  restores the old posture.
- `notes_ref` cannot distinguish an evidence link (the violation the rule
  targets) from prose *about* the ledger convention; some of the 20 initial
  findings may be judged acceptable mentions at the gate, and stateless
  semantics means an accepted-as-is finding nags weekly. If that becomes
  noise, an allowlist needs its own design pass (deliberately not built
  ahead of the signal).
- The docs scan shells out to git (one `git log --name-only` walk for the
  enja timestamps plus one `rev-list --count` per freshness header —
  measured ~0.5s on the current corpus; an earlier per-file form cost ~190
  subprocesses / ~6s and was collapsed in review; measured during that
  review round — the pre-collapse form is not preserved in history). Still
  weekly-cadence
  work by intent — it is deliberately not in `verify.sh`.
- `watch:` annotations are a convention with exactly one enforcement point
  (the scan's MALFORMED_WATCH errors); a typo'd annotation reports as
  malformed rather than silently unmonitored, but only when the scan runs.
  *Narrowed 2026-08-15:* a whole family of typo did **not** report. `_WATCH_RE`
  needs a closing backtick and at least one argument, and an annotation missing
  either yields no match — which is what a row with no annotation yields, so
  the task sat at `fired 0` for as long as it stayed blocked. Three kinds are
  now named (`unterminated` / `no-argument` / `swallowed`), refused at render
  (`tasks.py::render_row`) and reported by the scan, giving the convention a
  second enforcement point upstream of the weekly cadence.
- **Superseded 2026-08-15: stage 6c's input is the store, not the file.** As
  adopted, this intake parsed `.notes/TASKS.md`, which under ADR-0094 became a
  *projection* of `.notes/tasks/` — and **no stage re-derives it**; sessions
  render by hand. A week whose `tasks.py render` failed never reaches
  `_atomic_write`, so the previous table survives intact and parses cleanly:
  the stage recorded `result=ok watches=N fired=0` over a store it no longer
  described, with none of the new blocked rows in it. "The render is broken"
  arrived at the gate as "nothing fired" — this ADR's own forbidden shape, one
  layer up. Staleness itself predates the finding (a `MalformedTask` anywhere
  in the store aborts `load_store` the same way), but the trigger descended
  from "the store is corrupt" to "one blocked row's `watch:` has a typo" when
  render gained the refusal above.
  The fix re-derives rather than validates: `render_from_store` runs
  `tasks.py render` as a subprocess — a separate process, so not the import
  cycle it would be in-process — and the scan parses its stdout. Measured on
  the live store: exit 0, 186,038 bytes, byte-identical to the file, 0.12s, no
  writes (`render` without `--output` only prints). A store that will not
  render abstains `LEDGER_UNRENDERABLE`, carrying render's own message, which
  already names the offending task and cell.
  A timestamp comparison was built first and rejected on two counts. It
  validates *age*, not *renderability*: a render can begin failing with **no
  store mutation at all** when the render side tightens — which `c16642c` and
  `8265e3c` each did — and every mtime test calls that week fresh, while
  stamping it verified. And its false-stale side would have been the common
  case, since the store routinely runs ahead of the projection between hand
  renders (`claims.py` unions both for exactly that reason), so the stage would
  have failed most weeks until the alarm meant nothing — the original failure
  returning through the alarm-fatigue door. Re-deriving removes the question
  instead of answering it: no cache, so no mtime, no clock, no read/replace
  window, and no list of limits to keep honest.
  Drift in the on-disk file is still reported (`PROJECTION_DRIFT`, one
  `tasks.py render --output` to clear) but never fatal — the reading no longer
  depends on it, and the file is what a human opens. It travels in its own JSON
  key under its own packet code `LEDGERWATCH_DRIFT`: the packet counts every
  `errors[]` entry as an unparseable watch annotation and prints "check
  annotation syntax", so carrying drift there would have delivered a true
  signal under a false name — the same class as the defect above, one field
  over.

**Neutral:**

- Packet section numbers 9 and 10 are now reserved (same reservation scheme
  as §5/§8); the §6 metrics line is unchanged.
- The ledger header documents the annotation grammar; the grammar
  deliberately requires a `T-…` row ID, so prose examples elsewhere in the
  ledger must avoid literal `watch:` spans (observed during adoption: four
  header examples parsed as malformed watches and were rewritten).
  *Refined 2026-08-15:* the constraint turns out to be narrower than this
  bullet states, and only for one of the three kinds above. `` `watch:` ``
  written alone — the `no-argument` kind, which is exactly how this sentence
  and `_HEADER` refer to the annotation — is refused only on blocked rows,
  because nothing in the syntax separates naming a thing from invoking it, and
  one live `ready` row names it. Unterminated and swallowed spans are refused
  on every row; they are broken markup regardless, and re-measuring with the
  kinds separated found zero live instances of either. Prose elsewhere in the
  ledger is therefore free to write `` `watch:` `` but not to leave a span
  hanging open.
- The off-host mirror heartbeat identified in the same consideration is
  *not* built (no observed instance); it is recorded as a deferred ledger
  task with its trigger condition.
