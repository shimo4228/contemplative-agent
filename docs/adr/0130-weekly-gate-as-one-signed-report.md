# ADR-0130: The Saturday Gate Is One Signed Report, Decided Item by Item and Approved Once

## Status

accepted — changes how the weekly gate asks (RFC-0010's reading channel, `weekly-gate` Steps 1b–8); the per-item verdicts, the full listing, the per-item recommendation/decision record (RFC-0010 Q7) and ADR-0116's approver and reason-code rules stand

## Date

2026-11-01

## Decided by

proposed-by: Claude Code session (the harness task-triage digest change, harness ADR-0098)
decided-by: repository owner (instruction "weekly-gate も変える", 2026-11-01)
date: 2026-11-01

## Layer

governance

## Context

- The `weekly-gate` skill asked for each decision one at a time: Step 1b "判断は項目単位で仰ぐ", Step 1c and Step 4 "1 件ずつ", Step 5 / 6g three choices per item, Step 8 `AskUserQuestion` one item at a time. The unattended run (`~/.claude/scripts/launchd/weekly-gate-ca-prompt.txt`) wrote every item into the session's closing reply, and the owner read it through Remote Control and answered later.
- On 2026-11-01 the owner moved two harness procedures to one Artifact report with one approval: the stocktake (harness ADR-0097) and the task-triage digest (harness ADR-0098, which already moved this gate's Step 8). The owner then asked for this gate to follow.
- The gate has constraints the harness reports do not:
  - RFC-0010: every queue item is shown; each item carries its eli5 explanation in a fixed order; the assistant's recommendation and the human's decision are recorded per item (`gate_item`), and their agreement rate is the only check that the briefing has not become an effective filter. ADR-0129 row C11 cites that agreement as 45/45: the first gate (2026-08-29, run `gate-2026-08-28`), 48 `gate_item` rows with the 3 `recommendation=none` rows left out (RFC-0010). RFC-0010 records no later reading, and notes that the reading leans high because explainer and decider share one session.
  - ADR-0116 D1/D3: Claude Code is the explainer and the transcriber, never the approver; the approver is a string a human types (`# approver:` in the names FILE); every rejection carries a reason code.

## Decision

1. All of a week's gate decisions go into **one Artifact report** built from `.claude/skills/weekly-gate/templates/gate.html`, backed by the artifact's `db` store, published with the harness `harness-stocktake` report contract. One item per decision, in the Step 1b order as item fields; Step 0 alerts first as a group without choices; all queue items listed. The owner reads once, chooses for every item, types their name into the signature field, and presses approve once. The session executes after that, writes each outcome back, and closes with Step 7.
2. **No default choice.** Every item starts empty; the approve button is enabled only when every item has a choice, every rejection that needs one has a reason code, every choice that needs a note has one, and the signature is not empty. The recommendation is shown in its own box, apart from the evidence.
3. The **signature** is `meta/approval.approver`, typed by the human in the page. The session copies it unchanged to the names FILE's `# approver:` line and to every `gate_item` row's `approver`. Before executing, the session checks the signature against the `Accountable operator:` and `Registered approver:` lines of `docs/GOVERNANCE.md`; an empty or unregistered signature means nothing runs.
4. `gate_item` takes `recommendation` from the item and `decision` from the human's choice in the store, so the agreement rate keeps both sides.
5. The unattended run publishes the report and sends one Slack message with the count, the URL and one-line titles. Approval is acted on when the human next speaks in the session; the button does not wake it.
6. Step 8 (Saturday task-triage) stays a second report, after the gate has run: triage reads the gate's commits and decisions.
7. Without Artifact, the same items go into a Markdown table in the owner's private notes outside the repo (the path is in the weekly-gate skill) and the decisions are taken in the session in one answer.

## Review-when

- RFC-0010's own trigger stands unchanged (agreement stays near 100%). In addition: the owner reverses an approved item afterwards (a re-adopt, a restored deletion, "I missed that"): one approval is not being read item by item; move the value-layer groups (insight, identity) back to one question each (the hybrid in Alternatives).
- The execution check stops on an empty or unregistered signature in two gates, or a `meta/approval` is found that the page did not write (its `at` precedes the last `decisions/*` write, or it appears while no human opened the report): the signature convention is not holding.
- Two consecutive weeks reach the next Saturday with the report unapproved: the phone path to the report, or the notice, does not fit.
- Claude Code or claude.ai offers native batched per-item approval.

## Alternatives Considered

- **Keep one question per item.** Works without Artifact and keeps each answer next to its explanation. But the unattended run already wrote every item into one reply that the owner scrolled on the phone, and answers came back in batches anyway, as they did for the triage digest (harness ADR-0098); the per-item ask served only the leftovers. Rejected.
- **Hybrid: one report for deadcode, docs, rfc, census and baseline; insight and identity one question each.** Keeps the value-layer decisions individually asked. Not taken now because nothing observed yet says the value-layer items are read less carefully in a report than in chat, and the report already forces a choice per item. Held in reserve: it is the fallback named in Review-when 1.
- **Preselect the recommendation and let the owner change only disagreements.** Faster to approve, but an untouched item would pass as the recommendation and the agreement rate would rise for reasons other than agreement. Rejected (Decision 2).
- **Let the session fill the signature from `docs/GOVERNANCE.md`.** A fixed value reads the same whoever pressed the button, which ADR-0116 D3 rejects for environment defaults. Rejected.
- **Fold the triage digest into the gate report.** One report for the whole Saturday, but triage items depend on the gate's commits and decisions, which do not exist until the gate is executed. Rejected (Decision 6).
- **Share the harness template.** The gate needs reason codes, required notes, a signature and no Keep option; a shared template would couple the gate to unrelated harness changes. Rejected; the copy keeps the shared parts (db wiring, approve button) in step by hand.

## Consequences

- The owner decides the gate in one sitting on one page, from the phone or the desktop, without scrolling a long reply.
- The defence against unread approval moves to the page: no defaults, required reason codes and notes, and the signature. If the item text gets worse, one approval becomes a formality; the agreement rate and the Review-when watch for that.
- The session that builds the report has the same `db` write access as the page, so it could write `meta/approval` itself. ADR-0116 D3 now rests on a convention (the skill says the session writes only `items/*` and `meta/run`) plus the registry check before execution, not on a mechanism.
- Decisions are recorded in three places. For value-layer adoptions and rejections `audit.jsonl` wins; for recommendation and decision `pipeline-metrics.jsonl` (`gate_item`) wins; the report store is the human's choice as given and the source both are copied from. Part of the C11 evidence (the page as the owner saw it) is not public.
- The gate now depends on Artifact and its `db`; the fallback is the table of Decision 7.
- Saturday has two reports: the gate, then triage.
- The report URL lives in a pointer file in the owner's private notes outside the repo (the path is in the weekly-gate skill); the decisions themselves stay in the report store, `audit.jsonl` and `pipeline-metrics.jsonl`.
- Reverting is `git revert` of the skill change in this repo and of the prompt change in the harness.

## References

- [RFC-0010](../../rfcs/0010-weekly-report-content-redesign.md) (weekly report content redesign, eli5 reading channel)
- [ADR-0098](0098-weekly-single-session-and-triage-delegation.md), [ADR-0116](0116-approval-gate-records-as-acts-of-responsibility.md), [ADR-0129](0129-value-layer-intervention-channel-registry.md) row C11
- harness `~/.claude/docs/adr/0097-batch-stocktake-report-and-two-decisions.md` (stocktake report) and `~/.claude/docs/adr/0098-task-triage-digest-as-one-approved-report.md` (task-triage digest report)
