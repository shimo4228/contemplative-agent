# ADR-0085: Unattended Weekly Fix Chain with a Single Saturday Gate

## Status

accepted

## Date

2026-07-29

## Context

The weekly reflection cycle (Cycle #5, CYCLES.md) had three separate human
touchpoints: manually invoking `/weekly-report-diagnosis` after the Saturday
report, manually implementing the F1 findings it produced, and reviewing
staged insight items with `adopt-staged`. Each touchpoint was a place for the
cycle to stall — the operator opening a report days late is also how the
2026-07-25 failure (a 0-byte report shipped by a dead launchd run) went
unnoticed until read time.

ADR-0040 deliberately left diagnosis automation as an open door ("cron-side
automation is out of scope of this ADR"). The constraint surface for going
further is well documented: CYCLES.md names two human-owned promotion edges
(#5 findings → code, #6 implemented diff → commit), ADR-0012 bans `--auto` on
behavior-modifying commands, ADR-0013 records why a capable model on both
sides of an approval gate degenerates it into a co-authoring loop, and
ADR-0050 defines the gate as containment, not a training signal.

Diagnosis quality has crossed the threshold where unattended implementation
is plausible: the 2026-05-17 F1s were wrong 3-of-3 against the code, while
the 2026-07-24 F1s carried line-verified multi-site references and a rendered
reproduction.

## Decision

Ship `scripts/weekly-pipeline.sh` (launchd `com.moltbook.weekly-pipeline`,
Sat 09:00, replacing `--weekly-analysis`) — an unattended chain that runs the
existing report as its Stage 1, then: diagnosis (the existing skill in a
separate headless `claude -p` session), deterministic F1 parsing
(`scripts/parse_findings.py`), per-finding fix implementation in disposable
git worktrees with orchestrator-run Verify, an advisory fix review in a third
session, an advisory insight-staging review, and a decision packet
(`scripts/build_decision_packet.py`). Key commitments:

1. **The machine never commits, pushes, or adopts.** All promotion happens in
   the Saturday `/weekly-gate` session: approved patches are applied,
   re-Verified, and landed as one human commit; `adopt-staged` runs there.
   Both CYCLES.md promotion edges survive, merged into one sitting
   (human-gate.md's 1-work-1-gate).
2. **Scope split at parse time.** F1s closed over `src/ scripts/ tests/` are
   `code` scope (auto-implemented, Verify-gated, patch exported). Any F1
   touching behavior-shaping artifacts (`config/prompts/`, `.claude/`, …) is
   `prompt` scope: a draft diff is produced but presented full-text at the
   gate, never Verify-certified. Ambiguity classifies as `prompt`. F2 stays
   human-only.
3. **Role separation is preserved across sessions**, not inside one:
   diagnostician, implementer, and reviewer are separate fresh-context
   `claude -p` invocations (the ADR-0013 failure mechanism was a *shared*
   conversational context). The reviewer's verdict is advisory input to the
   human gate — there is no LLM-only approval path.
4. **Bounded iteration** (coding-style Iteration Bounds): ≤ 2 fix attempts
   per finding (the retry input includes the Verify failure output — never
   the same input twice), ≤ 5 findings per week, per-session timeouts, and a
   3-hour wall-clock deadline; every bound exhaustion becomes a reason code
   in the packet, not a silent drop.
5. **Fail-forward to the packet.** Every stage failure is a reason code; the
   packet is always attempted (only a missing Stage-1 report aborts). A
   missing packet therefore means "chain never ran / died hard", which is
   exactly what the watchdog checks.
6. **Independent watchdog** (`scripts/pipeline_watchdog.sh`, launchd
   `com.moltbook.watchdog`): pure bash — deliberately sharing no PATH
   dependency (claude, uv, python) with the jobs it verifies, because the
   2026-07-25 failure was a PATH dependency. It checks each job's *terminal
   artifact* against a period-anchored expectation table (report ≥ 1 KB by
   Sat 12:00, packet by 13:00, insight/distill/backup log liveness), rewrites
   `reports/PIPELINE-STATUS.md` every run, and posts a Notification Center
   alert only when the failure set changes. No session-hook surface: most
   sessions are unrelated to this pipeline, so the status is read where it is
   consumed — the gate session reads it as its Step 0.
7. **Self-measurement with a damped self-modification loop.**
   `logs/pipeline-metrics.jsonl` gets a `phase:"auto"` record per run and a
   `phase:"gate"` record per decision session (adopt/reject counts,
   recommendation match rate — F1 precision is adopted / patch-ready). A
   pipeline-improvement proposal is drafted only when the same reason code
   recurs in two consecutive runs (the diagnosis skill's P4 shape), and is
   itself full-text gated. Metrics every week, self-edits only on evidence —
   weekly self-modification would invert Scaffold Dissolution.

## Alternatives Considered

1. **Fully unattended commit (auto-commit on green Verify).** Rejected:
   overrides CYCLES.md edge #6 and re-creates the ADR-0013 loop with no
   third party left to reject; the same-PR obligations (CODEMAPS freshness,
   ADR-0075/0077) cannot be self-certified by the party they certify.
2. **Automate diagnosis only, keep fixes manual.** Rejected as the primary
   mode (it leaves the largest stall point — implementation — in place), but
   it ships as the supported shadow mode: `MOLTBOOK_PIPELINE_STAGES` without
   `fix` runs report → diagnosis → packet, and is the mandated first-week
   rollout configuration.
3. **`adopt-staged --yes` from the chain** (full insight automation).
   Rejected: ADR-0012's `--yes` was licensed for supervised coding-agent
   sessions; an unattended scheduler using it would erase the one gate
   ADR-0074 architected around. The chain only *annotates* staging
   (read-only recommendations), which ADR-0050 already frames as legitimate
   (containment gate; advisory input does not feed back).
4. **Session-start hook as the failure surface.** Rejected after review:
   most Claude sessions are unrelated to this pipeline; a global injection
   would be noise. The status file + gate Step 0 + Notification Center cover
   the three read moments (any time / decision time / failure time).

## Consequences

- The operator's weekly involvement compresses to one Saturday session; the
  pending-guard stall (unreviewed staging skipping next week's insight) is
  structurally covered because the gate session is where staging review now
  lives.
- ADR-0033's observation that no CLI routes the Autonomous Agentic Loop
  quadrant needs a footnote: the chain is agentic per-stage but its loop is
  deterministic bash with hard bounds; the LLM never selects tools or
  iterates open-endedly. The quadrant claim survives at the runtime level,
  and this ADR records the nuance.
- New failure mode: a plausible-but-wrong patch surviving Verify and an
  APPROVE verdict. The gate presents intent summaries, so the human is not
  re-inspecting diffs; the mitigation is the metrics loop (a bad adopt shows
  up as a reverted commit and a next-week finding) and the option to demand
  the diff at the gate (human-gate escalation rule).
- Re-running `install-schedule` must now pass the full flag set including
  `--weekly-pipeline --watchdog`, or the declarative reconcile removes them
  (the known T-PLIST-LOSS sharp edge, unchanged in kind).
- The diagnosis skill's F1 heading + Code-reference block is now a machine
  contract (`parse_findings.py`); its SKILL.md says so. The skill's own
  out-of-scope ("F1 is a plan, not a code change") is unchanged — the fix
  happens in a different session, which is the role boundary working.

## Amendment (2026-07-29): four-reviewer hardening round

The initial implementation shipped without the review chain (a process
failure, caught by the operator). A post-commit round — code-reviewer,
python-reviewer, security-reviewer, and codex (cross-model) — surfaced
convergent findings; the load-bearing repairs, now part of this decision:

- **Actual-scope enforcement**: the exported patch's real touched files are
  re-checked deterministically; a code-scope patch touching anything outside
  `src/ scripts/ tests/` is escalated to the full-text gate
  (`SCOPE_ESCALATED`), and a prompt-scope patch touching code paths is
  Verify-gated. Declared scope alone routed what the human sees — the gap a
  prompt-injected fix session could have used to slip a governance-file edit
  past the gate as a table row.
- **Session capability narrowing**: no `Bash(python3:*)` / `Bash(uv run:*)`
  grants (arbitrary execution defeats a read-only allowlist); `Edit`/`Write`
  path-scoped to the worktree; `--add-dir` scoped to `reports/` + `logs/`
  (diagnosis) and `skills/` (insight) so `credentials.json` is outside every
  unattended session's granted tree; finding bodies wrapped as
  `<untrusted_finding>` (ADR-0007 continuity).
- **Fail-forward made total**: every artifact read survives non-UTF-8 bytes
  with a reason code (`*_UNREADABLE`); traversal-shaped path references are
  rejected at extraction; the single-line `**Code reference**:` form (half of
  historical findings) now parses; Verify steps are individually bounded;
  same-week reruns are excluded from the P4 recurrence baseline and get
  cleared patch dirs; the watchdog skips unscheduled jobs and notifies on
  recovery.

Residual risk (accepted, documented): a fix session can still execute
arbitrary code *inside* the worktree via test files under `uv run pytest`,
and network egress from test code is not blocked — the boundary is the
exported-diff review plus the human gate, not process isolation.
