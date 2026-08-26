# ADR-0098: Weekly Chain Single-Session Redesign and Repair Delegation to the Task-Triage Loop

## Status

accepted — partially-supersedes ADR-0085, ADR-0091, ADR-0093

## Date

2026-08-24

## Context

The unattended weekly chain ([ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.md),
staged upward by [ADR-0090](./0090-ipd-two-arm-instrument-for-constitution-amendments.md) /
[ADR-0091](./0091-value-layer-cadence-in-the-weekly-chain.md) /
[ADR-0093](./0093-repo-plane-deterministic-intakes.md) /
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md)) has reached
`scripts/weekly-analysis.sh` at 774 lines, `scripts/weekly-pipeline.sh` at
1,393 lines, and `scripts/build_decision_packet.py` at 1,987 lines. Most of
that size is armor for running seven unattended `claude -p` sessions in
sequence: inter-stage parsing, per-session containment
(T-CHAIN-PERM-SWEEP), packet rendering, and reason-code accounting.

Over the trailing three weeks, 8 of 11 weekly F1 findings were about the
plumbing itself, not the agent's core behavior. The sharpest case is the
read-only instrument `value_layer_approval_join.py`, which grew from 327 to
998 lines in a self-supply loop: each week's instrument repair produces the
next week's F1 finding. An internal pipeline-substrate survey (2026-08-22)
found this pattern produced almost no findings that bear on the agent
itself.

Full adoption out of the chain is 100% gated on the Saturday human gate, so
preparing unattended fixes ahead of that gate buys no real time — measured
code-facing F1 volume is about one finding per week.

Two prior decisions in this project took the same shape for the same
symptom: [ADR-0095](./0095-retire-task-ledger-machinery.md) retired the
task-ledger machinery down to the store and `claims.py`, and
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) dissolved
three skill consolidators. In both cases, bloat was resolved by removal, not
by adding machinery.

External verification raised two points. A Codex plan-challenge noted that
(1) daily material includes untrusted, externally-authored agent text, so
containment is a trust-boundary matter that must be kept regardless of
whether the session is unattended, and (2) the fate of the
implementer-≠-approver separation needed to be stated explicitly rather than
left implicit. A fresh-context architect agent (Fable) verdict was
build-with-changes: "the right amount of machinery for something read once a
week by one reader is one deterministic instrument set plus one unattended
LLM session plus a human gate", and the value previously assigned to the fix
stage was overestimated — 8 of the 11 diffs it prepared were the plumbing
repairing itself.

## Decision

1. **Collapse the unattended Claude chain from seven sessions to one.** A
   new skill, `/weekly-report` (`.claude/skills/weekly-report/`), runs the
   A–E synthesis, the Japanese translation, the F1/F2/F3 diagnosis, and F1
   ledger-candidate filing in one straight-through session. The prior
   `weekly-report-diagnosis` skill is absorbed and retired.

   > **注記 (2026-08-26, ADR-0099)**: the session's *content* changed under
   > [ADR-0099](0099-weekly-report-instrument-redesign.md) (RFC-0010): the
   > A–E synthesis became the six-section instrument document, the Japanese
   > translation step was retired, and the diagnosis input moved from
   > section E to the document's Deviations + Exceptions. The single-session
   > structure, containment, filing-to-triage path, and everything else in
   > this ADR stand unchanged.

2. **Remove the unattended LLM fix / review / improve / insight-recommendation
   stages.** Diagnosis stops short of repair: findings are filed as
   candidates under the task ledger store (`tasks/T-*.md`) (producer `file:line` required; no
   readiness claim written). Repair runs through the existing task-triage
   loop (`triage-ca`: Wed 17:07 / Sat 14:07) — premise verification, owner
   digest accept/reject, worktree dispatch, human merge. The
   implementer-≠-approver separation moves from a session boundary to this
   chain: the session that writes the report may also diagnose it, but the
   findings stay advisory, and the independent verification layer is
   triage, not the writing session.

3. **Retire `build_decision_packet.py`**, the packet builder. The Saturday
   `weekly-gate` skill reads findings and each instrument's per-week JSON
   (value-layer, dead-code, docs-consistency, never-selected) and the
   ledger directly. Completeness assurance shrinks to a deterministic
   expected-file-existence check at the top of the gate skill.

4. **`weekly-analysis.sh` becomes collection-only** — zero `claude`
   invocations. It writes the former `USER_PROMPT` content to a materials
   file. Instrument baselines (anomaly sweep / api drift / approval join)
   emit to deterministic `.pending` paths; promotion still happens only
   after the pipeline confirms a structurally complete report exists (the
   promote-after-report discipline is unchanged).

5. **Containment shrinks to one set for one session** (`--tools` allowlist,
   `--strict-mcp-config`, `--setting-sources project`, exact-path Edit
   allowlisting, episode-log Read deny); the untrusted-material nonce frame
   is kept. Because the single session carries no Bash, `claims.jsonl`
   spawn records move from session-side logging to a deterministic bash
   step that diffs task files before and after the run.

6. **Structurally cut off the self-supply loop.** Findings about the chain
   or its own instruments are filed the same way as any other finding —
   through triage's worth judgment and the owner digest — removing the
   unattended-adoption path that let the chain repair itself without
   review.

7. **Launch schedule is unchanged** (launchd Sat 09:00,
   `com.moltbook.weekly-pipeline`). The watchdog's packet-deadline check is
   replaced with a findings-deadline check.

Files touched: `scripts/weekly-pipeline.sh`, `scripts/weekly-analysis.sh`,
`.claude/skills/weekly-report/SKILL.md` + `references/diagnosis.md`,
`.claude/skills/weekly-gate/SKILL.md`, `scripts/pipeline_watchdog.sh`,
`tests/test_weekly_*_shell.py`.

## Review-when

- Code-facing F1 findings keep rising (roughly > 3/week for 4 consecutive
  weeks) and triage-mediated repair latency starts causing real harm →
  reconsider reintroducing an unattended fix stage.
- The Saturday session routinely takes > 2h and the owner stops showing up
  → reconsider reviving a pre-computed, packet-equivalent synthesis.
- Unattended autonomy itself (self-repair completing before a human reads
  it) is redefined as a research observation target → this ADR's premise
  ("unattended fix buys no time") no longer holds.
- The filing-to-triage path keeps growing the ledger net (open tasks rise
  monotonically over 4 weeks) → tighten the filing entry conditions
  (self-check before a candidate is written).

## Alternatives Considered

### Replace the plumbing with a workflow tool

(T-PIPELINE-SUBSTRATE S3 investigation) Rejected — only 400–500 of 1,314
lines could be removed, the watchdog cannot be carried over in principle,
and the containment decision that excluded a workflow tool from `--tools`
would have to be reversed.

### Auto-fire from `/loop` or a standing session

Rejected — this revives an unattended Claude presence plus ambient
permissions, weaker than the armor it replaces, and a dying session goes
silent with no signal.

### Shrink individual instruments only (e.g. approval-join 998 → core)

Rejected — insufficient on its own: the structure that lets an unattended
reviewer produce findings about itself every week stays in place.

### Keep a shrunk packet builder

Rejected — the Saturday session is human-attended and can read the files
directly, so the synthesis layer is unnecessary; it is also the bloat
device that grows a Python module and its tests with every added section.

### Status quo (keep the seven-session chain as-is)

Rejected — contradicts the measured self-supply loop (8/11 findings) and
the two precedents, [ADR-0095](./0095-retire-task-ledger-machinery.md) and
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md).

## Consequences

### Positive

- Unattended LLM sessions go from 7 to 1; containment design sets go from
  5 to 1.
- `scripts/weekly-pipeline.sh` shrinks from 1,393 to about 600 lines,
  `scripts/weekly-analysis.sh` from 774 to about 600 lines
  (collection-only).
- Deletes `scripts/build_decision_packet.py` (1,987 lines),
  `parse_findings.py` (166 lines), the four fix / review / improve /
  insight-recommendation prompts, and about 3,400 lines of tests.
- The self-supply loop is structurally closed.
- Repair rides the task-triage loop's existing premise-verification,
  WIP-cap, and human-digest discipline instead of a separate machinery.

### Negative

- Repair latency for real code-facing F1 findings stretches from
  same-night to the next triage cycle (up to 3–4 days).
- Saturday no longer has an "already-applied patch" waiting — proposals
  arrive only as candidates.
- Because the session that writes the report also diagnoses it, diagnosis
  independence now depends on the downstream triage verification layer
  rather than a session boundary.
- The single durable packet document disappears; the week's record is now
  spread across findings plus per-instrument JSON files.

### Neutral / Follow-ups

- Partially supersedes [ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.md)'s
  diagnosis / fix / packet stage structure.
- Partially supersedes [ADR-0091](./0091-value-layer-cadence-in-the-weekly-chain.md)'s
  §8 packet-reading delivery form: the due-reading moves to the gate
  reading value-layer JSON directly; the cadence logic itself is
  unchanged.
- Partially supersedes [ADR-0093](./0093-repo-plane-deterministic-intakes.md)'s
  docs-scan "goes to the packet" step, replaced by "gate reads directly";
  the detection/repair separation is unchanged.
