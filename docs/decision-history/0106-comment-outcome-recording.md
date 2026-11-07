# ADR-0106: Record What the Environment Answered — Comment Outcomes, Linked to the Selection

## Status

accepted (amended 2026-09-12, 2026-09-19, 2026-10-03)

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

**D3 amendment (2026-09-19, RFC-0038) — `parent_rejected` is the one reason the
reply path acts on.** The reply write marks its dedup key
(`reply:{post}:{comment}`) handled on that reason, so the target leaves the
reply queue; the other three are conditions of the moment and leave it
retryable, as does the `unverified` exit. This is a read of the failure column,
not of the reaction columns, so D7 ("do not route reactions downstream") is
untouched — and the mark lives in the dedup ledger, which carries no publish
meaning: a reply that went out is what the `published` row plus the activity
episode say, and this path writes neither. "Leaves the queue" is as durable as
the ledger and no more: a cold rebuild of the commented cache reads post ids
out of episodes and no reply keys, so losing the cache file resurrects retired
targets — the hole published reply keys already had.

**D3 amendment (2026-10-03, RFC-0049) — a reply row names its target.** The row
gained `reply_key_sha256` (sha256 hex of the dedup key `reply:{post}:{comment}`)
and `parent_comment_id` (the answered comment's id). The `parent_rejected` rows
after RFC-0038 could not be counted per target, so the two explanations left —
a byte-identical body arriving under fresh comment ids, or a retired key not
surviving into a later session — read the same. Unlike the reason columns,
both ride every status of the reply path (published / unverified / failed /
declined), because the reading counts one target's rows whatever they say;
every other path writes them as explicit nulls, and a row without the keys
predates this amendment. The writer (`record_publish_outcome`) owns what is
recorded: the key only as a digest — its halves are platform-authored ids and
the digest is all a join needs (hashing a commented-cache entry reproduces it)
— and the parent id only when it passes `is_valid_id`, the gate `comment_id`
already has, dropped rather than truncated. The notification path has no parent
(it posts top-level), so its rows carry the digest and a null parent. Behaviour
is unchanged: which of the two explanations holds, and so how the terminal mark
should persist, is decided after these columns are read.

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
`replied_fraction` (named `reply_rate` until 2026-10-24; replied comments
/ injected comments for that skill, not the account-level `reply_rate` of
`core/metrics.py`) / `mean_thread_depth` for the window, plus a fixed
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

**D8 — axis × position table, and the reply rate beside the exit candidates
(addendum 2026-10-24, P2-06.3).** The metabolism-quality requirement of
[ADR-0080](./0080-north-star-layered-end-state.md)'s 2026-08-26 addendum (§B)
asks that intake be told apart on several axes, never one scalar, and leaves the
axis list open. This ADR owns the one place those axes are laid against where
they apply, so a reader does not hunt for a reading that cannot exist:

| Axis | Entry (insight candidate → staging) | Exit (store skill → archive candidate) |
|---|---|---|
| Novelty | Read: novelty gate, naming kind, duplicate verdict (ADR-0096 / ADR-0111) and the surprise reading | Not defined — a stored skill has no novelty against itself; the nearest reading is the confusion-pair similarity (ADR-0105), a different quantity |
| Importance | Not instrumented (the ADR-0056 ablation stands; naming the axis here is not rebuilding it) | Not instrumented, same |
| Environment's reaction | Not defined by construction — a candidate has not been injected into any comment yet | Read: per-skill `reply_rate` / `injected_comments` (D6), shown beside the candidate |
| Selection frequency (not one of the three above; listed because the exit rule uses it) | Not defined — nothing selects a candidate | The ADR-0105 strict rule and the confusion pair. This is what decides |

The list stays open (ADR-0080 §B). No cell is a score and no row is summed.

Stage 7d's tail (`scripts/archive_candidate_context.py`) writes
`weekly-{end}-archive-candidates.context.txt` next to the candidate file: one
line per candidate with `reply_rate`, `injected_comments` and the window's
`observed_publishes`. It is a **sibling file, not a column of the candidate
file**, because `adopt-staged --archive-names` aborts on a line it cannot parse.
It is a display of the D6 distribution at the place the gate meets the
candidate; it is not an input to the archive decision. What decides stays
ADR-0105's strict rule, and the gate may still strike or keep a line for any
reason it writes down. The one-way flow is pinned by
`tests/test_archive_candidate_context.py`: the candidate producer and the
`adopt-staged` / `remove-skill` code do not name the reading, and the context
script never writes the candidate file. If the reading were ever to filter or
rank candidates, that is the D7 case and needs its own ADR.

> **Note (2026-10-31, D-P1-04-2 = A)**: D6's weekly stage 7d and D8's sibling
> file are removed, and the D8 table's Exit × Environment's reaction cell is
> now "not read". D1–D5 and D7 stand. See the Review-when note of the same date.

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

> **Note (2026-10-24, P1-04.5)**: the "≥ 500 judged records" floor is counted
> on `joined_publishes` (the population the selection readings count), while
> reply rates are read over `observed_publishes` (the D5 denominator, about one
> third of the joined population). A rate therefore says nothing about the
> unobserved two thirds. Whether skills separate is read once, over two
> three-week windows (2026-09-12..10-02 and 10-03..10-23), by
> `scripts/comment_outcome_separation.py` against a line fixed in advance: some
> pair of skills with at least 10 pooled observed comments each differs by
> 0.2 or more with non-overlapping Wilson intervals, widened (Bonferroni) for
> the k(k-1)/2 pairs compared. *Amended 2026-10-24, before the first reading:*
> the first wording used plain 95% intervals, which fired in 77% of null
> simulations over about 800 pairs; the correction is a pre-registration
> repair, not a post-hoc change. The reading is a
> distribution and does not flow into adopt / archive (D6, ADR-0051). The
> verdict (remove stage 7d, or file an attribution RFC) is D-P1-04-2 at the
> Saturday gate; recipe and outputs live in
> [`docs/evidence/adr-0106/`](../evidence/adr-0106/README.md).
>
> **Note (2026-10-31, P1-04.5 — the reading, and what the removal took)**: the two
> windows do **not** separate skills. Observed 1,293 of 2,669 joined publishes
> (48%, more than the "about a third" above); 49 skills, 39 with at least 10
> observed comments; no pair meets the line (largest gap 0.351 at n = 10 vs 37,
> intervals overlap); chi-square p = 0.198 and permutation p = 0.528 as context.
> On (ii), the pooled figure over observed comments is 7,132 replied of 8,439
> skill injections (0.845) — a pooled count, not an interval, since a comment
> carrying k skills counts k times. The owner decided A at the 2026-10-31 gate,
> so the instrument is removed: weekly stage 7d
> (`scripts/comment_outcomes_reading.py`, `PIPELINE_COMMENT_OUTCOMES_TIMEOUT`),
> its tail (`scripts/archive_candidate_context.py` and the
> `archive-candidates.context.txt` sibling, D8), the gate's Step 6e, and the
> neighbours' reply-rate column of `scripts/staged_item_axes.py` (the
> [ADR-0111](./0111-insight-entrance-stages.md) note of the same date). All four
> displayed the per-skill distribution this reading found not to separate. The
> weekly JSONs already written stay and end with `comment-outcomes-2026-10-30.json`.
> What stays: the recorder and `logs/comment-outcomes.jsonl` (D1–D5; "the log left
> in place" is read as the log still being written, because
> [RFC-0055](../../rfcs/0055-amendment-outcome-preregistration.md) reading (c) and
> [ADR-0124](./0124-research-questions-operational-definitions.md)'s Q2 axis draw
> on it, and stopping the writer is a change to the production path);
> `read_comment_outcomes(since, until)` for a direct window reading, run the way
> the evidence recipe runs it; D7, pinned by
> `tests/test_comment_outcomes.py::test_no_decision_side_module_reads_the_outcomes`.
> [RFC-0028](../../rfcs/0028-skill-outcome-recording.md) stays `done`: it closed on
> 2026-09-09 when the recorder shipped, which is what its state records; the
> attribution design in its Future possibilities is not taken up. This
> consumption plan is complete.

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
