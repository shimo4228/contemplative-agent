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
   per round, across ≤ 1 + MAX_REVIEW_ROUNDS rounds per finding (retry input
   includes the Verify failure output — never the same input twice; revised
   by the 2026-08-01 amendment from the original flat "≤ 2 per finding"),
   ≤ 5 findings per week, per-session timeouts, and a 3-hour wall-clock
   deadline; every bound exhaustion becomes a reason code in the packet, not
   a silent drop.
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

## Amendment (2026-08-01): review feedback loop (T-PIPELINE-REVIEWLOOP)

The first gated week (packet `weekly-2026-07-31`) exposed an asymmetry in the
original design: Verify failures fed back into a bounded retry, but the
review was a dead end — one invocation, one grepped `VERDICT:` line, body
discarded. F1.1's CONCERNS body contained three real defects (a regression
test asserting a line shape production never emits, a comment describing a
non-observed leak as fact, a `_RUNTIME_LINE_RE` over-match), none of which
reached the packet; the human adopted the patch without that information.
Review becomes a bounded loop, symmetric with Verify:

- **Re-entry**: a `CONCERNS` verdict feeds the full review body back into a
  fresh fix session in the same worktree (`<untrusted_review>`-wrapped — the
  body chains from the finding text, same rationale as
  `<untrusted_finding>`). Budget: `MAX_REVIEW_ROUNDS` re-entry rounds
  (default 1) — orthogonal to `MAX_FIX_ATTEMPTS`, which is re-granted per
  round so one flaky Verify cannot starve the concern feedback. The
  re-review input includes the previous review, and the review prompt gains
  a check 0: do not keep CONCERNS alive by restating addressed points.
- **CONCERNS never blocks export** (operator decision, 2026-08-01, rejecting
  the alternative of demoting a final-CONCERNS patch to `failed`): the final
  patch stays `patch_ready` whatever the verdict — the reviewer is an
  inspector, not an approver (human-gate.md); demotion would create the
  LLM-only rejection path this ADR's commitment 3 forbids in the approve
  direction. What changes is what the human sees: the packet's fix table
  shows the whole verdict history (`CONCERNS→APPROVE`), and a "Review notes"
  subsection inlines the final round's full review body
  (`--run-log-dir`; unreadable log → `REVIEW_LOG_UNREADABLE`, fail-forward).
- **Monotonicity / rollback**: each round's verified diff is snapshotted; a
  re-entry round that cannot re-pass Verify (or dies, or hits the deadline)
  rolls back to the previous round's verified diff
  (`REVIEW_ROUND_ABANDONED`) instead of turning a working patch into a
  failure. An unchanged diff after re-entry is not re-reviewed (never retry
  on identical input); the standing CONCERNS stays on record
  (`DIFF_UNCHANGED`).
- **Anti-appeasement clause** in fix-implementation.md: on re-entry the
  implementer must address each point or explicitly rebut it in its summary
  without changing code — and must never weaken a test, assertion, or check
  to satisfy the reviewer. The 07-31 counterexample: F1.3's "test is
  narrower than the finding asked" concern, mechanically satisfied, would
  have ballooned into a store-wide rewrite.
- **REVIEW_FAIL is terminal** (no verdict line → nothing to feed back), and
  prompt-scope findings remain outside the review path (they are full-text
  gated already).
- **Trust-link hardening** (2026-08-01 security + code review round): the
  loop turns the reviewer's output from a read-only sink into an input of a
  tool-using session, so (a) the review session's own input now wraps the
  finding in `<untrusted_finding>` and fix-review.md gains an explicit
  data-not-instructions clause; (b) a forged `</untrusted_review>` inside
  the reviewer's body is neutralized before re-injection; (c) every embedded
  fence (packet inlines, review input) is sized to outrun the longest
  backtick run in its body; (d) the post-hoc scope check reads the
  git-computed touched-path snapshot of the chosen round instead of parsing
  diff text — binary changes and pure renames emit no `---`/`+++` headers,
  and `diff.noprefix` blinds a text parse entirely (both bypasses reproduced
  in review; regression-pinned by F-REV-6).

Fault column: `tests/test_weekly_pipeline_shell.py` (F-REV-1..5) drives the
real script with stubbed `claude`/`uv` binaries — the first tests ever to
execute weekly-pipeline.sh, closing the same gap `test_weekly_analysis_shell.py`
closed for its Stage 1 after the July shell-layer defects.

This amendment revises Decision commitment 4: the fix-attempt bound is now
per round, not per finding. Worst-case cost per finding grows from 1 review
to `MAX_FIX_ATTEMPTS × (1 + MAX_REVIEW_ROUNDS)` fix sessions +
`(1 + MAX_REVIEW_ROUNDS)` reviews (4 sessions + 2 reviews at defaults); the
3-hour chain deadline remains the hard stop, and a deadline hit during a
re-entry round rolls back rather than aborting. Second-order cost: extra
rounds spend wall-clock inside the same deadline, so a concern-heavy week
can complete fewer of its ≤ 5 findings end-to-end than the pre-loop chain.
Residual risk (accepted): the symmetric failure to implementer appeasement —
a reviewer satisfied by a diff that touches the flagged lines without
removing the defect — has no mechanical guard; the mitigation is that the
human now reads the final review body, not a 4-char verdict.

## Amendment (2026-08-10): value-layer cadence stage (ADR-0091)

[ADR-0091](0091-value-layer-cadence-in-the-weekly-chain.md) adds stage 5b
(`valuelayer`) to this chain: a read-only cadence reading plus, behind
live-run / insight-completion / staging-empty guards, an unattended
`distill-identity --stage`. That is a new action class for this chain —
unattended LLM *generation of a value-layer artifact*, which this ADR's
decision did not contemplate (its scope was code fixes and read-only
reviews). The single-Saturday-gate commitment is unchanged: staging is not
adoption (ADR-0012), and every value-layer candidate still crosses the
same `adopt-staged` gate. Details, guards and the race analysis live in
ADR-0091.
