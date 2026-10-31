# Incident Response

Detect, stop, identify the version in force, trace the cause, publish.
"Incident" means harmful or unintended behaviour of the agent, or harmful
content found in what has been published (the dataset, the reports, the
repositories). Written so that one person can follow it alone; it assumes no
team.

The causal-tracing questions are the five of agent-attribution-practice
ADR-0006 ("Causal Traceability"): inputs, version in force, approvals,
external surface, output. The RCA template below has one heading per
question.

**Reading rule.** Never open the raw episode logs
(`$MOLTBOOK_HOME/logs/episodes/`) in a tool-using session: they carry
untrusted third-party text. Everything below is answered from the
self-written logs, the snapshot manifests and the comment-reports
(`reports/comment-reports/comment-report-YYYY-MM-DD.md`; its `Context`
sections are third-party data, the `Internal note` / `Output` sections are
the agent's own).

## 1. Detect

Sources, in the order a person usually meets them:

- The pipeline watchdog and the weekly report (`PIPELINE-STATUS.md`,
  `scripts/pipeline_watchdog.sh`) — failures, silence, anomalies.
- The approval join (weekly chain) and the comment-outcome log
  (`logs/comment-outcomes.jsonl`, written by the reply cycle).
- An outside report: a message to the contact alias or a GitHub issue.
  Third-party removal requests follow section 5 and the intake of the
  takedown policy (D-P3-05-2; the ledger is `takedown-requests.jsonl`,
  *planned, P3-05.14*).

## 2. Stop

Stop first, investigate second. Order, least to most drastic:

1. Unload the agent job: `launchctl unload ~/Library/LaunchAgents/com.moltbook.agent.plist`; this stops future sessions, so also wait for or kill a running `contemplative-agent` process.
2. Full stop: `contemplative-agent install-schedule --uninstall` (it also
   removes the daily `sync-data` job, ADR-0114), then the hand-managed jobs it
   does not own ("Stopping everything" in `docs/CONFIGURATION.md`;
   `launchctl list | grep com.moltbook` is the list to empty).
3. On the platform side, only posting is stopped. **Nothing is deleted.**
   Deleting hides the evidence the RCA needs, and the account disposition is
   decided in the wind-down runbook, not during an incident.

Confirm: `launchctl list | grep com.moltbook` prints nothing.

## 3. Identify the version in force

Pin the behaviour that was active at the time of the incident:

- The snapshot manifests under `$MOLTBOOK_HOME/snapshots/<ts>_<command>/manifest.json`
  record the command, timestamp, run id, generation and embedding models and
  the paths of identity, constitution, skills and rules in force; the files
  themselves are copied beside the manifest. Take the last snapshot **before**
  the incident time.
- `$MOLTBOOK_HOME/logs/audit.jsonl` gives the approval decision (and reason)
  behind each value-layer version.
- The comment-report of the day carries a `values_digest` per session
  *(planned, P2-05.4)*; until it exists, the snapshot is the source.
- Public equivalents of all of this are in the data repository
  (`snapshots/`), without the private logs.

## 4. RCA template

Copy to `docs/runbooks/rca/YYYY-MM-DD-<slug>.md`. The five H2 headings map
1:1 to the ADR-0006 questions; the first existing RCA,
`rca/2026-04-14-reflective-note.md`, is the precedent for tone (conclusion
first, then root cause, evidence, response, prevention) and for keeping the
page about recurrence prevention rather than blame.

```markdown
# RCA: <short title>

**Date**: YYYY-MM-DD
**Trigger**: how it was noticed
**Conclusion**: one paragraph, first

## 1. Which inputs reached the agent?
Complete input record, verbatim identifiers only (episode ids, comment-report
date), never pasted third-party text. Evidence: comment-report of the day.

## 2. Which version of the agent's behaviour was active?
Identity / constitution / skills / rules versions pinned from the snapshot
manifest (path and timestamp) and the digests.

## 3. Which approvals gated the active version?
The audit rows: approver, decision, reason, timestamp.

## 4. Which external surface was touched?
One adapter, one destination. Evidence: `logs/api-audit.jsonl` (written by
`API_AUDIT_PATH` in `adapters/moltbook/client.py`; structural fields of each
request and response only: endpoint, method, status, key names). Name the rows
by timestamp.

## 5. What did the agent output?
The final output with the input that produced it (comment-report entry).

## Response and prevention
What was fixed, which test or gate now fails first, what was published.
```

Question 4 is the one the single-adapter design answers best: the agent has
exactly one external surface (ADR-0015), so the audit rows of that adapter
are the complete answer.

## 5. Published content and the data repository

For an item in the published record (a dataset row, a report, a graph
node):

- The agent's own text and the owner-authored material are not withdrawn
  (the CC0 dedication is irrevocable; external knowledge, unverified); text of third parties can be
  removed or replaced where the surface allows it — the GitHub tree, the
  Hugging Face files and the next dataset version — following the takedown
  policy (D-P3-05-2).
- Immutable surfaces (an existing Zenodo version, Software Heritage
  copies, forks) cannot be edited. They are announced instead, in the
  reach table of the takedown section in the data repository's NOTICE
  *(planned, P3-05.14)*: one row per surface with the operation available,
  what trace remains, and the date it was checked. Copy that table here
  when it exists, with the same rows, so both agree; mark any statement
  about an outside service's rules as external knowledge, unverified.
- The intake channel and ledger are those of P3-05.14.

| Surface | Operation | Trace left | Checked |
|---|---|---|---|
| *to be copied from the NOTICE reach table* | | | |

## 6. Publish

After the RCA: a CHANGELOG entry (Fixed / Security) and, for anything that
changes a process, an `rfcs/` entry or ADR. If the incident touched a
third party's text, the notice follows section 5. State only what the
records support; where a question cannot be answered, say which record is
missing.
