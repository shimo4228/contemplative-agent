# ADR-0098: Weekly Chain Single-Session Redesign and Repair Delegation to the Task-Triage Loop

## Status

accepted (amended 2026-10-24) — partially-supersedes ADR-0085, ADR-0091, ADR-0093

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

## Amendment (2026-10-24) — the session's repo Read scope is a subtree list, and its project settings are pinned at preflight

Two repairs to the permission contract this ADR set up (roadmap P1-10.5 /
P1-10.13). Neither changes what the session does.

- `weekly-pipeline.sh` grants Read over the repository as an allowlist of
  subtrees (`src docs rfcs config scripts .claude/skills tests`) instead of
  `Read(/$PROJECT_ROOT/**)`. A deny only protects names it spells, so the
  checkout's untracked secret-bearing paths (`.env`, the `.notes` scratch dir, `.venv/`,
  `.claude/settings*`, `.claude/worktrees/`, `.deepeval/`, `evals/results/`) are
  kept out by never being allowed; the two names left inside an allowed subtree
  (`.env*`, `tests/fixtures/benchmark/**`) are denied. Pinned by
  `test_c_scope_6b_*`. Bare `Glob,Grep` allows are unchanged and unmeasured
  (probe: `test_c_scope_9`, opt-in, owner's machine).
- Because `--setting-sources project` loads an untracked
  `.claude/settings.json` (and never `settings.local.json`, which is the `local`
  source), the chain's preflight records that file's presence and sha256 as a
  `project_settings` row of `weekly-pipeline-audit.jsonl` (plus an informational
  `settings_local` flag). When it carries allow rules, hooks or additional
  directories, only the headless report stage is skipped, with reason
  `PREFLIGHT_PROJECT_SETTINGS_WIDEN`; the deterministic intakes keep running
  (the threat is the session, not the chain). Consumption plan: the Saturday
  gate reads the row weekly via PIPELINE-STATUS; one skipped report stage means
  the unattended session's permissions were widened and the rules are removed
  from `settings.json`; the stage is retired if the chain moves to
  `--setting-sources ""`. (`scripts/preflight_project_settings.py`.)

## Note (2026-10-24): the harness dependency boundary (P2-03.1)

ADR-0098 delegates repair to the task-triage loop, which is the owner's harness, not this repository. This note fixes where that boundary sits; D-P2-03-1 = B (owner, 2026-10-24). The full classification is `docs/HARNESS.md`.

- **Taken in (A).** Who filed an unattended draft is recorded in the draft itself (`filed_by:`, `producer:`), numbering and publication are the gate's (`scripts/rfc_inbox.py`), and the ledger's minimum conventions are in `rfcs/README.md`. The chain no longer calls `claims.py`.
- **Documented, not taken in (B).** `task-triage`, `task-stocktake`, `rfc-writer`, `release-doi`, `jsonld-knowledge-graph`, `verify-bootstrap` and the private lease log stay in the harness. Triage is itself a Claude Code session, so taking it in would restate the ADR-0080 amendment (2026-11) rather than add a mechanism; its contract is: reads `rfcs/*.md` with `state: draft`, writes state changes and notes there, a human merges.
- **Cut off (C).** `wiki-harvest`, `wiki-query`, `archify` are owner-private and not read by any code here.
- **Minimum configuration without the harness:** `git`, `uv`, `python3`, Ollama, and the `claude` CLI with a subscription for the weekly session (instruments-only without it). Repair and triage are then manual (`docs/runbooks/harness-less-operation.md`).
- **Requests to the harness** (secret-pattern file, post-freeze PR rules, `next_check:` handling, attribution trailers, hook de-duplication, `release-doi` link) are listed with a due date and an evidence column in `docs/HARNESS.md` section 4.

Consumption plan (ADR-0101): (a) the owner reads the requests table when closing a bundle and fills the evidence column with the harness commit; (b) one reading per bundle decides whether the row is done; (c) a row is removed once its evidence is filled, and the page is retired with the harness boundary (D-P2-03-1 reopened).
