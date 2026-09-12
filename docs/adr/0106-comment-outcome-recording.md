# ADR-0106: Record What the Environment Answered — Comment Outcomes, Linked to the Selection

## Status

accepted

## Date

2026-09-09

## Context

The skill store has no success or failure criterion, so nothing about it can be
tuned: [ADR-0105](./0105-skill-store-exit-confusion-pairs.md) had to build its
exit out of *structural* signals (never selected, confused with a neighbour)
because the outcome signals the retirement literature uses — Library Drift's
(success − failure)/attempts (arXiv:2605.19576), ASSAY's masked causal
attribution (arXiv:2606.15390) — need a task-level verdict this agent does not
have. [RFC-0021](../../rfcs/0021-skill-stocktake-family-saturation.md)'s 2026-09-07
decision recorded that as not portable.

The gap is narrower than "no verdict exists". The platform *does* answer: other
agents reply to our comments, threads continue, comments carry upvotes. The
agent has simply never written that answer down next to the skills that were
injected into the generation. The selection log
(`core/skill_selection.py`) records what was injected and stops at the moment
of generation; the reply cycle reads the reactions and uses them only to decide
what to answer.

The north star's 2026-08-26 amendment ([ADR-0080](./0080-north-star-layered-end-state.md))
names "the environment's response" as one axis of metabolic quality and forbids
reducing the axes to one scalar. This ADR records that axis and does nothing
with it.

**Phase 0 refuted the source RFC-0028 assumed.** `/home`'s
`activity_on_your_posts` carries `post_id`, `post_title`, `submolt_name`,
`new_notification_count`, `latest_at`, `latest_commenters`, `preview` and
`suggested_actions` — no comment ids, no upvotes, no thread structure
(`https://www.moltbook.com/skill.md`, fetched 2026-09-09). The columns exist
one endpoint over: `GET /posts/{id}/comments` returns a *tree* with ids,
`upvotes` and nested `replies`, and the reply cycle already calls it for our
own posts (`reply_handler._handle_post_comments`, 3,511 calls in
`logs/api-audit.jsonl`). So the recorder reads that tree instead, and buys no
new request.

## Decision

**D1 — the source is the comment tree the reply cycle already fetched.** The
recorder is called from `_handle_post_comments` with the tree in hand. No new
endpoint, no extra GET, and `_HOME_ALLOWED_KEYS` stays at its two keys
(`tests/test_home_field_allowlist.py` unchanged). The cost is coverage: only
comments of ours that live under **our own posts** are observed, because
reactions to our comments on other agents' posts would need a GET per post.
The number is in the JSON as `coverage_note`, not left to the reader's memory.

**D2 — the link is a second record, not an edit of the first.** A selection is
recorded before the generation runs; the comment id exists only after the
publish call. Writing it back would mean rewriting a line of an append-only log
(RFC-0028 Unresolved 1). Instead every selection record carries a minted
`selection_id` (and null `comment_id` / `publish_status` placeholders, so a
reader of one record can see where they get filled), and the publish path
appends a `kind: "publish"` record carrying that id, the comment id, and a
reason code. The id travels from selector to publisher on the
`GenerationOutput` — stamped inside `generate_for_api`, so the failure return
carries it too — rather than through module state.

**D3 — the publish outcome is four named states, not a boolean.**
`published` / `published_id_unknown` (the envelope was ambiguous — the client
documents that case) / `unverified` (the verification handshake failed) /
`publish_failed` (the client raised). A silence in this log would otherwise be
four different things at once.

**D3 amendment (2026-09-12, RFC-0029) — the `publish_failed` state says why.**
The row gained `http_status` (int or null) and `failure_reason` (one of
`rate_limited` / `parent_rejected` / `transport` / `unknown`, a closed
code-owned vocabulary in `core/skill_selection.py`). Set on the
`publish_failed` row only — every other state already names its own cause, and
a second column repeating it is one a later reading can disagree with. Both are
written as explicit nulls elsewhere, so "no reason because it worked" stays
distinguishable from "written before this amendment". The platform's own
message is NOT recorded: it is untrusted text whose only readable-log
destination was `agent-launchd.log`, which the harness forbids reading
(ADR-0083). The adapter derives the code (`publish.publish_failure_of`) and the
writer re-checks it against the vocabulary, so a caller cannot widen the column
into free text.

**D4 — the columns stay separate and no LLM judges them.** The outcome log
records reply events (id, depth, `by_self`, body as base64 + sha256 + length)
and comment-state changes (upvotes, reply count, max depth, has-reply)
separately. There is no composite score, and no model is asked whether a
comment was good: The Blind Curator (arXiv:2607.07436) measured that a judge's
false-pass bias past 0.45 stops retirement without moving the aggregate
metrics, and the local `gemma` judge splits its own vote on 52% of repeated
identical inputs (novelty-gate replay, 2026-09-02). Deterministic reactions
have no such cliff.

**D5 — the denominator is what was observed, not what was published.** A
published comment with no observed state row (it lives under another agent's
post, or our own post drew no activity for the reply cycle to fetch) is
excluded and counted as `unobserved_publishes`. Counting it as a silent
"no reply" would push every skill's rate toward zero in proportion to the
coverage gap, and the exit criterion below — do reactions separate skills —
could then never be met.

**D6 — the reading is a distribution and says so in the file.** The weekly
stage 7d emits per-skill `injected_comments` / `comments_with_reply` /
`reply_rate` / `mean_thread_depth` for the window, plus a fixed
`observation_note`: which skill was injected is the selector's decision, and
that decision is confounded with the situation. Comments younger than
`min_age_days` (2) are excluded and counted, because replies arrive hours to
days later.

**D7 — nothing flows onward.** No reaction feeds selection, extraction or
retirement, automatically or otherwise. The attribution design (randomized
masking, ASSAY's shape) stays in RFC-0028 Future possibilities (D7): intervening in
the production path before knowing whether reactions separate skills at all is
the wrong order, and it is also where the Goodhart pressure would enter (a
store drifting toward whatever draws replies).

## Review-when

### Consumption plan (ADR-0101)

- **Reader, weekly**: the Saturday gate (`/weekly-gate`), reading
  `pipeline/comment-outcomes/comment-outcomes-{end}.json` beside the
  never-selected and confusion-pair readings. The instruction lives in
  `.claude/skills/weekly-gate/SKILL.md` Step 6e; without that wiring the plan
  could silently never complete, which is what ADR-0101 exists to prevent.
- **What two readings decide**: two windows of **≥ 500 judged records** each
  (the same population the selection readings count). They answer two
  questions. (i) Does the reply rate separate skills at all — is there a
  spread wider than what the per-skill `injected_comments` counts can produce
  by chance? (ii) Can a reply-rate band be stated for the store as a whole?
- **Removal condition**: if the reactions do **not** separate skills across
  those two windows, there is nothing for an attribution design to attribute,
  and this instrument is removed — stage 7d deleted, the log left in place as
  history, RFC-0028 closed `resolved`. If they do separate, the next decision
  is the attribution RFC's, not this one's.

### Expiry conditions

- The platform stops returning replies or upvotes on the comment tree (the
  source of the columns disappears).
- `GET /posts/{id}/comments` stops being called by the reply cycle — the
  recorder's free ride ends and the cost question reopens.
- The generation model changes: the distribution is model-conditioned and any
  band read under `gemma4:e4b` has to be re-read.
- Someone proposes feeding a reaction into selection, extraction or retirement.
  That is a different decision (D7) and needs its own ADR, including the
  north-star reading of whether adjusting on environment response counts as
  steering (D7).

## Alternatives Considered

- **Score comments with an LLM judge.** Rejected under D4: the Blind Curator
  cliff plus the measured local-judge instability, against a deterministic
  alternative that has neither.
- **Have the owner rate comments at the Saturday gate.** Rejected: it injects
  the owner's values into the value layer's evolution, which
  observation-over-steering ([ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md)
  and successors) exists to prevent.
- **Spend a GET per commented post to cover comments on others' posts.**
  Rejected for now: the read budget is 60/min shared with the feed, and the
  first question ("do reactions separate skills at all") is answerable inside
  the free coverage. If the answer is yes and the coverage is the limiting
  factor, that trade is worth re-opening.
- **Write the comment id back into the selection record.** Rejected under D2:
  it breaks append-only, which is the property that makes the log replayable.
- **A separate log file for publish records.** Considered — it would need no
  filter in the existing readers. Rejected because the link and the selection
  belong to one event: a reader holding the selection log would otherwise have
  to know a second file exists to follow the join. The readers instead filter
  on `kind`, in the one place the log's record grammar already lives
  (`core/selection_window.py`); records written before this ADR carry no
  `kind` and are read as selections, so the longitudinal series stays one
  series.

## Consequences

- The selection log gains a second record family. Every reader of it now has to
  know about `kind` — three did, and all three were updated
  (`core/selection_metrics.py` and `core/never_selected_metrics.py` through the
  shared walk, `scripts/skillsel_reading.py` in its own loader). A fourth
  reader written without that knowledge would silently count publish records as
  selections with an `unknown` verdict.
- A new self-written log (`logs/comment-outcomes.jsonl`) holds base64 reply
  bodies from other agents. It is untrusted-origin data at rest, stored the way
  ADR-0075 requires and never decoded by the reading; anything that decodes it
  later inherits the injection surface the episode logs carry.
- The dedupe set is held in memory per process and rebuilt from the file on
  first use. A log that cannot be read means duplicate rows, not lost rows —
  logged as a reason, and the reading counts distinct ids anyway.
- Coverage is partial by construction (D1) and the JSON says so. A reader who
  ignores `coverage_note` will under-count comments that drew replies on other
  agents' posts and, if they also ignore `observation_note`, will read a
  confounded distribution as a contribution estimate. Those two notes are the
  whole defence; there is no mechanism preventing the misreading.
