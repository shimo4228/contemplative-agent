# ADR-0091: Value-Layer Cadence in the Weekly Chain

## Status

accepted — adds one stage to `scripts/weekly-pipeline.sh`, one read-only
instrument script, and one packet section; changes no runtime behavior
under `core/` / `adapters/`. Adoption authority is unchanged
([ADR-0012](0012-human-approval-gate.md) Saturday gate).

## Date

2026-08-10

## Context

The value layers update at deliberately decreasing frequency: episode
distill runs daily, insight/rules distill runs weekly staged
([ADR-0074](0074-weekly-staged-insight.md)), and identity and constitution
have until now been manual-only. Nothing measured or enforced the upper
layers' cadence — the last `distill-identity` run was 2026-06-20, 51 days
before this ADR, and drift was invisible unless the owner happened to
remember.

Since [ADR-0057](0057-identity-from-self-reflection-corpus-alone.md),
`distill-identity` does not seed from the prior identity: its output is a
fresh function of the `self_reflection` pattern corpus, so the run
interval itself is the parameter that decides how much experience folds
into one self-description. Running it weekly would produce noise-diff
churn (the corpus barely moves in a week) plus approval load for
near-identical candidates; a monthly cadence matches the scale at which
the corpus actually drifts.

Constitution amendments are a deliberately benched event since
[ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md): a
required ~2 h IPD two-arm bench, an owner approval, and a post-adoption
single-file verification (the open defect T-ADOPT-OVERWRITE-TARGETS fired
on the very first live use, 2026-08-09). The observed adoption cadence is
2026-05-05 → 2026-08-09, 96 days. That amendment read as behaviorally
indistinguishable within ADR-0090's ±0.13 noise floor (itself calibrated
from a single null pair — n=1, per that ADR's own caveat), which means the
instrument could not resolve even a 96-day accumulation of corpus change;
a shorter interval cannot produce readings the bench can distinguish, and
nothing in the data argues for one. Amendment adoption dates also serve as
the before/after reference points for weekly reports
([ADR-0056](0056-retire-importance-llm-scoring.md): one value-layer
variable at a time), so a higher amendment frequency has an observation
cost, not just a compute cost.

The unattended weekly chain
([ADR-0085](0085-unattended-weekly-fix-chain-single-saturday-gate.md))
already runs Saturday 09:00 with a single human gate. The weekly insight
staging job *starts* Saturday 08:00, but it writes to staging only after
1–2 h of LLM generation — measured from the audit log: 09:16 / 09:42 /
10:14 / 09:16 JST on the four most recent Saturdays — i.e. **inside the
chain's own window**, and it has staged 50–106 items on every one of those
weeks. ADR-0074's invariant is that staging holds at most one unreviewed
batch, and the race therefore runs both ways: fired after the insight
write, an unattended `distill-identity --stage` is refused by the CLI
(exit 0, a printed refusal, no staged file — the cheap artifact loses);
fired *before* it, identity would occupy the slot and the arriving insight
batch — the expensive artifact, 1–2 h of generation — would be the one
refused and discarded, since a refused insight run does not retry. Any
unattended identity staging must be provably ordered after the insight
job's completion, not merely after its start time.

The [ADR-0012](0012-human-approval-gate.md) approval audit log
(`logs/audit.jsonl`) already records every `distill-identity` run that
produced a result (any decision; a run whose LLM call failed returns
before the gate and writes no record — correctly, since a failed
generation should not reset the clock) and every `amend-constitution`
adoption (decision="approved"), so the cadence is derivable read-only from
data the agent already writes. Schema drift exists in that log: one
pre-2026-04 record (of 923) uses the key `"timestamp"` rather than `"ts"`
and the command name `distill-identity-ca`.

## Decision

1. **New read-only instrument, `scripts/value_layer_due_check.py`**
   (stdlib-only, following the [ADR-0071](0071-read-only-pattern-composition-instruments.md) /
   [ADR-0075](0075-observability-by-default.md) style). It reads
   `audit.jsonl`, `knowledge.json`, and the staging directory, and emits
   one JSON reading:
   - `identity`: `last_run_ts` (the latest `distill-identity` record of
     *any* decision — cadence gates generation, not adoption), `days_since`,
     and `due` at a 27-day interval.
   - `constitution`: `last_adopted_ts` (the latest approved
     `amend-constitution`), `days_since`, `due` at an 83-day interval, and
     `patterns_since` (knowledge patterns distilled after adoption —
     loaded lazily, only when an adoption baseline exists, because
     `knowledge.json` is >100 MB and costs ~1.5 GB peak RSS to parse on
     the 16 GB production box).
   - `staging_pending` (count of `*.meta.json` in staging).
   `--as-of` is injected rather than read from the wall clock, so readings
   replay offline. Faults degrade rather than silently pass: a missing or
   unreadable audit log, a malformed `--as-of`, or a non-positive interval
   abstains with a nonzero exit and a reason code (`AUDIT_MISSING` /
   `AUDIT_UNREADABLE` / `BAD_AS_OF` / `BAD_INTERVAL`) — unknown state must
   never read as "due" and trigger an LLM run. Partial faults degrade to
   counted reason codes (`AUDIT_PARTIAL_PARSE`, `KNOWLEDGE_UNAVAILABLE`),
   and anomalous clocks are named rather than silently mapped to "not due":
   matching records with no parseable timestamp read `UNPARSABLE_HISTORY`,
   a record dated after `--as-of` reads `FUTURE_TIMESTAMP`, and an audit
   log with zero readable records reads `NO_AUDIT_RECORDS` (truncation, not
   bootstrap — a fresh home has no audit log at all and abstains as
   `AUDIT_MISSING`). One deliberate exception to the abstain rule, recorded
   here because the code carries it: a demonstrably-alive audit log with no
   identity record at all reads `NO_PRIOR_RUN` with `due=true` — generation
   is cheap and adoption stays human-gated, so bootstrap fires; the
   constitution side stays `due=false` (`NO_PRIOR_ADOPTION`) because a
   first amendment is a deliberate human decision.
   The 27/83-day defaults anchor to the chain's `--as-of` being the day
   *before* the run day (`days_since = 7k − 1` on the k-th Saturday):
   27 → first eligible run at exactly 4 weeks, 83 → exactly 12 weeks; round
   28/84 would have silently meant 5 / 13 weeks. They are policy choices,
   not observed optima: the manual identity gaps in the log run 6–26 days
   (median 13) — the unattended lane deliberately runs *slower* than the
   owner's manual habit to bound approval load — and 12 weeks sits just
   under the single observed 96-day amendment cycle, rounding in the
   direction that surfaces the reading slightly early (a due reading costs
   nothing; a late one delays visibility). Both are overridable via CLI
   flags, and both should be revisited against the longitudinal record.

2. **New pipeline stage `valuelayer`**, enabled in the default `STAGES` of
   `weekly-pipeline.sh`, run every week: it runs the due check, and stages
   identity via `contemplative-agent distill-identity --stage` (under a
   `PIPELINE_IDENTITY_TIMEOUT=900s` budget) only when **all four** hold:
   identity is due; this is a live run (`END_DATE` equals yesterday — a
   `--end-date` backfill must never fire a real LLM run off a stale-dated
   reading and reset the genuine cadence clock, so it skips as
   `IDENTITY_BACKFILL_SKIP`); the same-day insight job has *completed*
   (`skills/.last_insight` marker fresh within
   `PIPELINE_INSIGHT_MARKER_MAX_AGE=6h`, else `IDENTITY_INSIGHT_PENDING`) —
   this is the reverse-race guard from Context: marker-fresh implies the
   insight job's staging write has already happened ("ledger first, marker
   last"), so checking staging afterwards is race-free against the
   scheduled producer; and `staging_pending == 0` (else
   `IDENTITY_STAGING_BUSY`). Ground truth for success is the complete
   staged pair on disk (`.staged/identity.md` **and** its `.meta.json`
   sidecar — `adopt-staged` discovers candidates through the sidecar, and
   the CLI exits 0 on both a staging refusal and an LLM failure). A
   refusal by a concurrent producer's flock is recorded as
   `IDENTITY_STAGING_RACE` (a designed ADR-0074 outcome), distinct from
   `IDENTITY_STAGE_FAIL` (a real fault). The recurring deferral codes
   (`IDENTITY_STAGING_BUSY`, `IDENTITY_INSIGHT_PENDING`) are added to the
   P4 detector's `DESIGNED_OUTCOME_CODES` so a working guard does not burn
   a weekly unattended improvement session. The deferred due condition
   persists, so the next eligible week picks it up, and the manual
   recovery path is named: at the Saturday gate, once `adopt-staged` has
   emptied staging, the human can run
   `contemplative-agent distill-identity --stage` (or the interactive
   non-staged form) in the same session. Every failure in this stage is
   fail-forward with a reason code (`VALUE_LAYER_CHECK_FAIL`,
   `IDENTITY_STAGE_FAIL`); the packet is always built.

3. **The constitution side is deliberately not automated.** No staging and
   no bench-firing happen from the chain. The instrument only surfaces an
   "amendment due" reading (days since adoption, pattern delta) in the
   packet, pointing at
   [docs/runbooks/constitution-amendment.md](../runbooks/constitution-amendment.md)
   and the ADR-0090 bench requirement.

4. **New packet section, "§8 Value layer cadence (identity /
   constitution)"** (`build_decision_packet.py --value-layer`): signal-first
   — rendered only when something is due or was attempted, so a quiet week
   adds no section (but it always renders when an identity stage event
   exists, even if the instrument JSON was unreadable — the §1 inventory
   references §8 and must never point at a section that does not exist).
   §1 inventory gains an "identity candidate: 1 件" line only when identity
   was staged this run. The builder propagates the instrument's own reason
   codes into the packet header and metrics as `VALUE_LAYER_<code>`, flags
   a read-but-unrecognized shape as `VALUE_LAYER_SCHEMA`, and renders
   off-contract `reason` values as `UNRECOGNIZED(...)` — degraded cadence
   evidence must not look like a quiet week. The metrics record gains
   `identity_due` / `constitution_due` with the None-vs-false discipline
   (`None` means the instrument did not read this week and never collapses
   into "not due" — the same discipline `dead_code_candidates` already
   uses). Identity *adoption* has no gate-record counterpart field; the
   longitudinal adoption read comes from `audit.jsonl` itself
   (command=`distill-identity`, source=`stage-adopted*`).

## Alternatives Considered

### Weekly identity distill, aligned with insight's cadence

Rejected: ADR-0057's fresh-distillation design makes weekly output
noise-diff churn, produces weekly approval load for near-identical
candidates at the gate, and the corpus itself moves on a month scale, not
a week scale.

### A dedicated launchd slot for identity (e.g. a fixed calendar day monthly)

Rejected. The weak same-day variant fails on ordering: launchd ordering
against the insight job is not controllable, so staging contention just
moves to whichever job runs second. The strongest variant — a *mid-week*
slot (say Wednesday), where staging is reliably empty because the Saturday
gate drained it — genuinely avoids the contention, but at the cost of a
second unattended LLM producer living outside the chain's plumbing: no
packet visibility, no reason codes, no watchdog anchor, no audit replay in
the same trail. Placement inside the chain is chosen for observability,
and the insight-completion marker guard (Decision 2) is the price paid for
it. Day-of-month triggers also interact badly with the chain's
week-ending-anchor dates; days-since-last-run measured from the audit log
is deterministic, replayable, and self-healing after skipped weeks.

### Reading-only identity: no unattended staging at all, distill at the gate

Not chosen as the design, but deliberately kept as the degraded mode the
deferral path produces. On the observed recent Saturdays the insight batch
occupied staging every week, so the realistic near-term behavior is: the
packet carries the due reading, and the human runs the distill at the gate
after `adopt-staged` — the unattended staging fires only on insight-quiet
weeks. The automation is kept anyway because it is cheap, guarded, and its
value grows if insight weeks quiet down; if the longitudinal record shows
the unattended path never fires, collapsing to reading-only is the natural
simplification (Scaffold Dissolution).

### Automate the amendment path (unattended stage + bench, human only approves)

Rejected: ADR-0090 positions amendments as deliberate instrumented events;
T-ADOPT-OVERWRITE-TARGETS still requires manual single-file verification;
the ~2 h bench needs a clear schedule window; and ADR-0056's one-variable
discipline plus the weekly-report baseline role of amendment dates argue
for scarcity, not automation. The chain's job here is to make "due"
visible, not to act.

### Relax ADR-0074's one-batch staging invariant to allow an identity batch alongside the insight batch

Rejected: relitigating the one-batch staging invariant is out of scope and
would reopen the wipe/confusion class of bugs ADR-0074 closed. The
deferral path plus the documented manual gate recovery costs at most one
week of latency, which is cheaper than reopening that invariant.

### Trigger on corpus delta (N new self_reflection patterns) instead of elapsed days

Deferred, not adopted: more faithful to "how much experience folds in",
but it needs a view-routing query (embedding cosine) inside what is
otherwise a deterministic, stdlib-only instrument, which would break its
read-only shape. `patterns_since` is already surfaced as a reading so the
owner can judge by eye, and the day-interval can be revisited once
longitudinal data accumulates.

## Consequences

### Positive

- Identity cadence becomes measured and roughly monthly with zero new
  human gates — adoption rides the existing Saturday `adopt-staged` step.
- A starved cadence becomes visible (recurring `identity_due=true` in
  metrics, `IDENTITY_STAGING_BUSY` reason codes) instead of silent.
- Amendment-due becomes a packet reading instead of an owner memory, and
  the runbook plus the ADR-0090 bench requirement are cited at the
  decision point.
- The instrument replays offline (`--as-of` injected) and abstains on
  unknown state rather than guessing; the fault column ships in the same
  PR (`tests/test_value_layer_due_check.py`,
  `tests/test_weekly_pipeline_valuelayer_shell.py` V-1..V-5, and packet
  builder tests).

### Negative

- Two policy numbers (27 / 83 days) enter the config surface as CLI-flag
  defaults; they are policy choices anchored to the reading-day offset,
  not measured optima, and should be revisited against the `identity_due`
  / `patterns_since` longitudinal record as it accumulates.
- On current evidence the unattended staging path will defer on most
  weeks: the insight batch has occupied staging on every observed recent
  Saturday, and the insight-completion guard additionally defers whenever
  the insight job has not finished by the time stage 5b runs. The
  realistic near-term deliverable is the packet reading plus a gate-time
  manual distill; the automation pays off only on insight-quiet weeks (see
  the reading-only alternative above for why it is kept regardless).
- A fired identity distill spends up to 900 s inside the chain's 3 h
  wall-clock deadline, pushing the later stages (deadcode / improve /
  packet inputs) closer to `CHAIN_DEADLINE` on slow weeks; the deadline
  check at each stage keeps this fail-forward, but it is a real budget
  cost on the weeks the automation does fire.
- The §8 section and the two new metrics fields extend the
  packet/metrics schema; the weekly-gate skill and check-improvement
  history reads are unaffected since the new fields are additive and use
  reason codes, not repurposed existing fields
  (`IDENTITY_STAGING_BUSY` / `IDENTITY_INSIGHT_PENDING` are excluded from
  the P4 recurrence set as designed outcomes).

### Neutral / Follow-ups

- Constitution amendments remain fully manual by design; this ADR only
  adds a due-reading, not an automation path (see Decision 3).
- Revisit the 27/83-day defaults once enough `identity_due` /
  `patterns_since` history has accumulated to judge whether they match
  observed drift rather than the single historical data points (51-day
  identity gap, 96-day amendment cycle) they were anchored against.
- This ADR extends ADR-0085's enumerated chain with a stage that can
  perform unattended LLM *generation of a value-layer artifact* — an
  action class ADR-0085's decision did not contemplate (its own scope was
  code fixes and read-only reviews). ADR-0085 carries an amendment note
  pointing here; the single-Saturday-gate commitment is unchanged (staging
  is not adoption, ADR-0012).
- The diagnosis session (stage 2) holds an unscoped `Write` grant over
  `$MOLTBOOK_HOME/logs`, which now contains a control input of this stage
  (`audit.jsonl`). The instrument names anomalous clocks
  (`FUTURE_TIMESTAMP` / `NO_AUDIT_RECORDS` / `UNPARSABLE_HISTORY`) loudly
  as its mitigation; narrowing that grant to `reports/` is tracked as a
  follow-up in the task ledger (2026-08-10 security review M1).

## References

- [ADR-0012](0012-human-approval-gate.md) — approval gate; adoption
  authority unchanged
- [ADR-0056](0056-retire-importance-llm-scoring.md) — one value-layer
  variable at a time; amendment dates as report baselines
- [ADR-0057](0057-identity-from-self-reflection-corpus-alone.md) —
  identity distillation not seeded from the prior identity, motivating the
  interval-as-parameter framing
- [ADR-0071](0071-read-only-pattern-composition-instruments.md) —
  read-only instrument shape this follows
- [ADR-0074](0074-weekly-staged-insight.md) — the one-unreviewed-batch
  staging invariant this respects
- [ADR-0075](0075-observability-by-default.md) — no silent fallback,
  reason-coded abstention
- [ADR-0077](0077-chaos-tdd-fault-injection.md) — fault column discipline
  applied to the new instrument
- [ADR-0085](0085-unattended-weekly-fix-chain-single-saturday-gate.md) —
  the weekly chain and its single Saturday human gate
- [ADR-0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md) —
  the amendment bench requirement and the 96-day observed cadence
- [docs/runbooks/constitution-amendment.md](../runbooks/constitution-amendment.md) —
  manual amendment procedure the constitution-due reading points at
