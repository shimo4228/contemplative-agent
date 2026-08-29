# ADR-0075: Observability by Default — Replayable Audit Logs Ship With the Feature

## Status

accepted (amended 2026-08-29)

Amended 2026-08-29: the by-default obligation is narrowed to resident
production paths — run / distill / insight / publish / verification. Read-only
instruments and one-shot measurement scripts are exempt; frozen results under
docs/evidence/ replace replayable logs for them. Existing logs and their
consumers are unaffected; only the scope of the obligation changes. Decided in
the same owner conversation as ADR-0100 / ADR-0101.

## Date

2026-07-09

## Context

The round-6 and round-7 verification parser repairs
([ADR-0062](./0062-create-time-verification-handshake.md), 4th–7th amendments)
were possible only because `logs/verification-audit.jsonl` already existed
*before* anyone went looking for the failures it eventually explained. The
file held 816 real challenge records — base64 raw challenge + sha256, solver
path taken, submitted answer, verify outcome, sanitized error — accumulated
as an ordinary side effect of running the solver, not as a debugging
exercise. That log turned "the solver keeps failing at the same rate" from
an anecdote into a labeled corpus: server-accepted answers supplied positive
ground truth, server-rejected answers supplied negative ground truth, and a
deterministic offline replay harness with a zero-wrong hard gate made
grammar changes safely testable against every historical challenge at once.

The same instrument-first pattern paid off in several other places already
shipping in this project: LLM call telemetry tagged by caller (the
`num_predict` 3000→5000 retune was justified by measured `done_reason=length`
rates, not intuition); the distill partial-failure summary logs and metrics
no-data markers added in the 2026-07-06 observability round;
`api-audit.jsonl` for API drift monitoring; `audit.jsonl` for the
ADR-0012 approval-gate history. In every case, the log predated the question
it was later used to answer.

The practice, however, is implicit. Nothing in the project's documented
chain requires a new feature to ship with audit instrumentation, so a future
feature — or an agent session implementing one — can add a capability with
no corresponding log, and the project loses the exact repair loop that made
the ADR-0062 amendments possible: no corpus to replay against, no ground
truth to test grammar or heuristic changes on, no way to distinguish "this
fails randomly" from "this fails in a specific, discoverable pattern."

The owner raised this on 2026-07-09, immediately after the round-7 repair
had just demonstrated the value of pre-existing logs on a concrete case.

## Decision

Any feature that performs external I/O, calls an LLM, or makes
non-deterministic or heuristic decisions must ship its audit
instrumentation in the same PR as the feature itself — not as a follow-up.

1. **Storage.** Append-only JSONL under `MOLTBOOK_HOME/logs/`, written via
   the restricted-permission helper (`append_jsonl_restricted`).
2. **Replayability, not just readability.** Records must suffice for
   offline replay: raw inputs preserved (untrusted text stored as base64 +
   sha256, never as free text — a raw log read must not itself become a
   prompt-injection path), the decision path taken, a categorical reason
   code for every abstain/fallback/failure, and the outcome.
3. **No silent fallbacks.** A fallback or abstain without a recorded reason
   code is a defect, not a style choice.
4. **Chain gate.** The Verify step of the implementation chain (harness
   rule `common/planning.md`) asks: "if this feature misbehaves, which log
   answers why, and could we replay it offline?" No answer sends the change
   back to design.

The principle is deliberately layered across three artifacts: CLAUDE.md
carries the one-line principle under 開発原則 (always loaded, shapes every
session); the project skill
[`.claude/skills/replayable-audit-logs`](../../.claude/skills/replayable-audit-logs/SKILL.md)
carries the design know-how (record-schema checklist, replay-harness
pattern, ground-truth discipline, corpus-driven repair loop); this ADR is
the canonical rationale and evaluation criteria.

## Alternatives Considered

### Add logging ad hoc when a bug appears

Rejected. The corpus must predate the failure to be useful as ground truth.
The round-7 repair consumed weeks of records that would not have existed if
logging had started at investigation time instead of at feature-ship time.

### Adopt a structured-logging / observability framework (e.g. OpenTelemetry)

Rejected. This is a single-process local agent with a deliberately minimal
dependency floor (`requests` + `numpy`). Plain JSONL is greppable,
replayable, and dependency-free; a tracing framework would add operational
surface with no matching need.

### Encode as a global harness rule (`~/.claude/rules`)

Rejected. This is project-specific practice tied to this project's I/O and
LLM-call surface; a global rule would leak into unrelated projects that
don't share the same replay-corpus need.

### CLAUDE.md bullet only, no ADR

Rejected. The evidence story (ADR-0062's repair chain) and the evaluation
criteria (the four requirements above) would drift without a canonical
record; repo convention keeps design decisions in ADRs, with CLAUDE.md
holding only the pointer.

## Consequences

### Positive

- Debugging becomes corpus-driven repair: replay harnesses, negative ground
  truth from server rejections, regression fixtures cut from real traffic —
  the ADR-0062 evidence directory is the template for future repairs.
- Features get a definition of observable failure at design time, not
  retrofitted after the first outage.
- Agent sessions can verify behavior claims against logs instead of
  re-running live systems.

### Negative

- Small per-feature overhead: designing a record schema, wiring the writer
  call, and possibly writing a replay script.
- Logs grow over time; one more thing for reviewers to check at the Verify
  gate.

### Neutral / Follow-ups

- Log growth is accepted as a cost, consistent with existing practice:
  JSONL is cheap and episode logs are already retained indefinitely as
  research material (`no-delete-episodes`).
- Security posture is unchanged and reinforced: untrusted content stays
  base64-wrapped in logs, consistent with the episode-log direct-read
  prohibition already documented in CLAUDE.md's セキュリティ方針.
