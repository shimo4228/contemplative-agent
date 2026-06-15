# ADR-0055: Counterparty Identity by Author Name; Unified Activity/Report Schema

## Status

accepted

## Date

2026-06-15

## Context

The agent reads other agents' posts and notifications from Moltbook. The codebase assumed
a feed post's `author` object carries both `name` and `id` — test fixtures used
`author: {id, name}`. In production, live feed posts carry `author.name` but not
`author.id`: over a representative week, 271/271 comment interaction records had
`agent_name` populated while `agent_id` was "unknown".

Several pipelines keyed on the author id and silently degraded as a result:

- The comment activity record wrote `target_agent_id` (always "unknown") and omitted the
  available name. The daily comment-report could therefore never show a comment's
  counterparty. Replies, which carry the notifier's name, did show it — producing an
  asymmetric, "haphazard" report schema where comments and replies rendered different fields
  for the same semantic slot.
- The per-author repeat-topic gate and the 24 h per-author rate limit keyed on `author_id`
  (empty string). `count_recent_comments_by_author` and `get_prior_comment_targets` always
  returned 0 / [] — both guards were dead no-ops, and same-author reposting (one author
  re-circulating near-identical essays) was never throttled.
- A weekly self-analysis flagged a "6-day re-reply to one post" as a duplication bug.
  Verifying against the episode logs showed six distinct interlocutors replying on one
  popular post — a healthy multi-party thread, not re-engagement. The misdiagnosis was
  possible only because the daily report dropped the counterparty identity, leaving
  downstream grouping with only `post_id` to work from.

## Decision

Adopt the author name as the canonical counterparty key across the interaction pipeline:

1. Write the counterparty name (`target_agent`) consistently on comment and reply activity
   records. Retain `target_agent_id` when present for forward-compatibility; write it as
   "unknown" only when absent, never as the primary key.
2. Re-key `count_recent_comments_by_author` and `get_prior_comment_targets` on the name.
   Guard "unknown" / empty values so unattributed records do not collapse into a single
   bucket and falsely trigger the gates.
3. Unify the daily activity-report into one per-interaction schema rendered identically for
   comment, reply, and post interactions: a header carrying counterparty, post id, and
   relevance ("—" when not applicable), followed by Context (the stimulus), the
   [ADR-0045](0045-pre-action-internal-note.md) `internal_note` (previously dropped by
   the report), and the output. Dimensions that do not apply render as "—" rather than
   changing the structure between interaction types.
4. Reinforce the weekly-analysis prompt and the weekly-report-diagnosis self-check to treat
   same-post / different-counterparty as a multi-party thread, not re-reply.

The boundary-validation constraint on author names (`^[A-Za-z0-9_-]{1,64}$`) remains in
place; names that fail it are treated as unattributed rather than propagated.

## Alternatives Considered

### Post-level reply dedup keyed on `post_id`

Rejected. The triggering observation was six distinct interlocutors on one post — a
legitimate multi-party conversation. Deduping at the post level would suppress valid
engagement and contradict the agent's relational stance. The rejection is also recorded in
`config/prompts/principles.md`.

### Recover `author.id` from an alternate payload key

Rejected. The id is absent in the live feed payload; no alternate key carries it. The name
is present, boundary-validated, and a safe stable key for the interaction scope this
pipeline covers.

### Patch only the weekly-analysis prompt, leaving the report asymmetric

Rejected. The counterparty data that the prompt needed was missing at the source — in the
activity record itself. Patching the prompt would leave the false positive latent, firing
again whenever the downstream grouping fell back to `post_id`.

## Consequences

### Positive

- The per-author repeat-topic gate and the 24 h rate limit now fire; same-author reposting
  that was never throttled will be caught.
- The daily report is structurally consistent across interaction types. The pre-action
  `internal_note` ([ADR-0045](0045-pre-action-internal-note.md)) and the counterparty
  identity are both surfaced, removing the asymmetry that produced the misdiagnosis.
- The "re-reply" false positive is removed at the data source. The diagnosis skill and
  `config/prompts/principles.md` carry a calibration note so the misread does not recur.

### Negative

- Engagement volume directed at repeat authors will fall — an intended correction, but a
  behavioral shift to monitor in the first weeks after deployment.
- Records written before this change lack `target_agent` on comments. Readers fall back
  gracefully: the gates skip them, the report renders "—". No migration is run.

### Neutral / Follow-ups

- [ADR-0029](0029-retire-dormant-provenance-elements.md) quarantine is preserved: post
  bodies and stimulus text never enter the distill summary; externally sourced text in the
  report remains URL-defanged.
- Implementation committed at 6c20032.

## References

- [ADR-0045](0045-pre-action-internal-note.md) — refines. The `internal_note` this ADR
  surfaces in the unified report schema was introduced and defined there.
- [ADR-0029](0029-retire-dormant-provenance-elements.md) — depends-on. The quarantine
  boundary at the summarize step is preserved and relied on here.
- [ADR-0040](0040-separate-code-level-findings.md) — precedent. The diagnosis that
  separated code-level findings from the weekly self-reflection report is the work that
  surfaced this issue.
- Implementation: commit 6c20032
