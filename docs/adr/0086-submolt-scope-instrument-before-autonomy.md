# ADR-0086: Submolt Scope — Instrument the Question Before Handing Over the Answer

## Status

accepted

## Date

2026-08-01

## Context

The agent's activity is bounded by `submolts.subscribed` in
`config/domain.json` — eight names the operator picked by hand: general,
philosophy, consciousness, agents, memory, emergence, ai, tooling. The
standing question is whether the agent should choose that set itself. Three
findings in the existing code decide how, and how fast, that can happen.

**One field, two jobs.** `subscribed_submolts` is read at two places that do
structurally different work. `feed_manager.fetch_feed` (line 67) uses it as
the *feed source set* — a read-only, reversible choice about what to look at.
`feed_manager._passes_content_gates` (line 284) uses the same tuple as a
*trust boundary*: a post whose `submolt_name` is not in it is dropped before
scoring, so it can never be commented on or upvoted.
[ADR-0044](./0044-remove-topic-keywords.md) considered relaxing exactly that
gate so cross-submolt search results could be engaged with, and rejected it —
"that filter is an intentional scope boundary, not a bug", widening the trust
surface against [ADR-0007](./0007-security-boundary-model.md). Because both
jobs read one field, any autonomy granted over the reading side is silently
granted over the acting side too.

**There is no evidence to choose on.** The production relevance distribution
is the obvious place to look for "are we missing anything", and it cannot
answer: every score in it comes from a post that already passed the
subscribed-submolt gate. Nothing has ever scored a post from an unsubscribed
submolt, so the hit rate outside the current eight is not merely unknown, it
is unmeasured by construction.

**Subscription is a one-way ratchet today.** `client.py` documents that
`unsubscribe_submolt` was deleted as dead code because "an unimplemented
capability is a smaller attack surface than a guarded one (security by
absence, ADR-0007)". An agent given `subscribe` and no `unsubscribe` can only
widen its own scope, never narrow it, and no operator action short of a code
change reverses a bad pick.

The project's own sequencing principle covers this case:
[ADR-0071](./0071-read-only-pattern-composition-instruments.md) builds the
instrument before the intervention, and
[ADR-0076](./0076-skill-selection-shadow-instrument.md) observes a candidate
judgment in shadow before enforcing it. Scope selection has skipped both
steps so far.

A read-only probe on 2026-08-01 established the platform affordances:
`GET /submolts` lists 20 submolts with `name` / `description` / `post_count`
/ `subscriber_count` / `is_private` / `is_nsfw`, twelve of them outside the
subscribed eight; and `GET /submolts/{name}/feed` returns a full 20-post page
for a submolt the agent is *not* subscribed to. Observation therefore
requires no subscription and no write capability of any kind. The counts are
reproducible from
[`docs/evidence/adr-0086/`](../evidence/adr-0086/README.md), which holds the
scan envelope verbatim — the runtime log itself is gitignored, so without it
these numbers would exist nowhere a clone can check.

## Decision

Build a read-only submolt-scope instrument. Do not change what the agent may
act on.

1. Add one read capability, `MoltbookClient.list_submolts()` (`GET /submolts`),
   returning validated `SubmoltInfo` entries. No write counterpart is added:
   `subscribe_submolt` keeps its existing config-driven caller and
   `unsubscribe_submolt` stays absent.
2. Split the relevance scorer's return into
   `score_relevance_detailed() -> RelevanceScore(score, reason)`, with reasons
   `scored` / `empty_input` / `llm_unavailable` / `unparseable` /
   `out_of_range`. The existing `score_relevance()` becomes a wrapper over it
   and production behaviour is unchanged. Four distinct events currently all
   return 0.0, and an instrument whose product is a *distribution* cannot
   conflate a judgment with an outage.
3. Add `adapters/moltbook/submolt_scope.py`: a sweep that samples the first
   `sample_size` (default 20 — one feed page) posts of every listed submolt
   **and every subscribed one**, scores each with the production scorer, and
   appends `scan_start` / `score` / `scan_end` records to
   `logs/submolt-scope-{date}.jsonl`. Subscribed submolts are sampled under
   the same rules as unsubscribed ones because they are the baseline the
   others are read against.
4. Expose it as `contemplative-agent submolt-scan` (its own launchd job,
   default Thu 03:00 JST) and `report --submolt-scope`. The sweep takes the
   run lock so it cannot double-spend the read budget against a session.
5. Constrain the instrument by construction: `configure_submolt_scope`
   without an `audit_dir` — or with `MOLTBOOK_SUBMOLT_SCOPE_DISABLE=1`, which
   is what makes the off switch reachable in production, since the CLI always
   has a log directory to hand — disables it entirely; scoring runs inside
   `circuit_shield()`; a repeating terminal 429 aborts the sweep instead of
   backing off through it; a per-sweep ceiling of 1000 scored posts bounds the
   local LLM cost independently of the network-side budget; and nothing
   sampled enters the episode log, the pattern store, or identity.

The `feed_manager` trust-boundary gate is untouched. Whether to act on this
data — by splitting the field, by letting the agent propose a scope in
shadow, or by leaving the eight alone — is a later decision this ADR
deliberately does not make.

## Alternatives Considered

### Let the agent subscribe and unsubscribe autonomously now

The direct reading of the original question. Rejected on three grounds, any
one of which is sufficient: it moves the trust boundary ADR-0044 explicitly
declined to move; it would need `unsubscribe_submolt` restored, re-opening a
write capability removed under security by absence; and it would run on no
evidence, since the agent has never scored a post outside the subscribed set.
This is the decision the instrument exists to inform, not to pre-empt.

### Relax the `_passes_content_gates` submolt filter and let relevance do the work

Argued for as "the 0.80 relevance threshold is the real gate anyway, the
submolt list is redundant". Rejected: the two gates fail differently. The
threshold is a probabilistic judgment by a small local model, and the fault
column in `tests/test_submolt_scope.py` shows several ways it returns a
number that is not a judgment at all. The submolt list is a deterministic
scope boundary that holds even when the scorer is degraded. Removing the
deterministic layer because a probabilistic one overlaps it is the wrong
direction (`when-code-when-llm`).

### Observe inside the agent's own session cycle

Cheaper to wire — no new command, no new launchd job. Rejected: the sweep is
~20 feed reads and ~400 local LLM calls, which on a 16 GB single-Ollama box
would contend directly with the session's own generations, and a session
slowed or starved by its own instrument is exactly the coupling
`circuit_shield` exists to prevent elsewhere. A separate schedule also keeps
the instrument's failures from ever appearing as session failures.

### Sample only unsubscribed submolts

Halves the LLM cost. Rejected: it produces unreadable numbers. "Unsubscribed
`crypto` scores 0.31" means nothing without "subscribed `philosophy` scores
0.44" measured the same way, and the production distribution cannot supply
that baseline because it only contains posts that passed the gate.

### Do nothing and keep curating by hand

The honest null option, and viable — the eight-submolt set has not visibly
failed. Rejected because the operator is choosing blind: no one, human or
agent, currently knows what the other twelve submolts contain. The
instrument is cheap, reversible, and answers that for both.

## Consequences

### Positive

- The scope question becomes empirical. After a few weekly sweeps, the
  subscribed and unsubscribed hit rates sit side by side in one reading.
- The relevance scorer gains reason codes, so any future distribution
  analysis — not just this one — can separate a low judgment from a broken
  scorer. This was a latent defect in every prior reading of that number.
- `report --submolt-scope` also reads as a liveness check on the current
  eight: a subscribed submolt with a near-zero hit rate is a candidate for
  removal, which the operator previously had no signal for either.
- The trust boundary and the write surface are unchanged, so this ships
  without a security review of new capabilities beyond one GET.

### Negative

- ~400 local LLM calls per sweep. Bounded to a weekly job at 03:00 JST, but
  it is real contention on a 16 GB box if it ever overruns into the 06:00
  session — the run lock prevents corruption, not overlap in wall-clock.
- The log grows by roughly 400 records per week carrying base64 post bodies.
  No rotation policy is added here; if it matters it will show up as disk
  usage long before it matters as anything else.
- The reading is only as good as the scorer. If `identity.md` drifts, the
  hit rates shift under it, and the instrument cannot distinguish "this
  submolt got less relevant" from "our sense of relevance moved" — the same
  known limitation ADR-0044 recorded for identity-driven relevance.
- Sampling the first page biases toward whatever the feed orders first. For a
  low-traffic submolt one page may be its entire month; for a busy one it is
  a recency slice. The instrument reports `post_count` and
  `subscriber_count` alongside so the two cases stay distinguishable.

### Neutral / Follow-ups

- If the reading shows the unsubscribed set is uninteresting, the honest
  outcome is to retire the instrument and keep the hand-curated eight —
  signal-first applies to removal as well as construction (skill:
  `read-only-instruments`).
- If it shows otherwise, the next decision is the field split (feed source
  vs trust boundary) as two separate config keys, followed by an ADR-0076
  style shadow in which the agent proposes a scope and the proposal is
  recorded without being executed. Restoring `unsubscribe_submolt` belongs to
  that later step, not this one.

## Amendment (2026-08-08): the reading counts distinct posts, not score events

The first real sweep ran on 2026-08-08 — seven days after Phase 1 shipped,
and the first time this instrument measured anything. The weekly job named
in the Decision had never been installed, so the record until then was one
`--sample-size 2` smoke. That gap is itself a finding: an instrument built
and then not scheduled reads exactly like one that was never built, and
nothing in the design made the absence visible.

The reading it produced exposed a counting defect. `read_submolt_scope_log`
tallied every score event, and the sweep samples one feed page per submolt —
so a low-traffic submolt returns the same posts every week and repeating the
sweep grew `scored` without adding an independent sample, while presenting
as accumulating evidence. The reader now deduplicates on `post_id` per
submolt across the window and reports the drops as `duplicate_records`,
rendered per row as `N/M resampled`.

Reporting the share rather than only correcting it is the point. A high
share says "another sweep will not move this row", which is what decides
whether the 16-minute sweep is worth repeating — a fact about the
instrument's own usefulness, and the kind of thing an instrument should be
able to say about itself.

Three rules the fix had to get right, each of which was wrong in a first
draft and caught in review:

- **A judged record supersedes an earlier unjudged one for the same post.**
  Keying on first-seen alone let an outage sweep (fault F-SCOPE-5) claim
  every post it touched, so a later successful re-score was discarded as a
  duplicate — the log holding a 0.95 while the reading said nothing was
  judged, for the rest of a 30-day window. Among *judged* records first
  still wins, so appending a sweep never rewrites an existing row.
- **A `post_id` at the write cap is not trusted as an identity key.**
  `_POST_ID_MAX_CHARS` was log hygiene and is now identity; two ids sharing
  that prefix would merge into one post and undercount with no symptom. The
  reader cannot distinguish a truncated id from a naturally cap-length one,
  so it declines to dedup either. Measured: production ids are 36 chars.
- **The un-dedupable count reaches the read-out, not just the log.** The
  scenario the guard exists for is a writer-side schema change silently
  restoring the inflation; on the scheduled path a logger warning lands in a
  launchd stderr file the operator is instructed not to open, so the count
  is carried on the reading and rendered (ADR-0075's shape).

Measured on the two sweeps available: 418 score records, every one carrying
a `post_id`, and **zero overlap** between sweeps a week apart. The dedup is
therefore inert on current data — a guard, not a correction. It also
weakens the argument that motivated ordering it before scheduling: the one
week of evidence says feeds turn over fast enough for repeats to yield
fresh samples. The instrument now measures that directly, so the question
does not need to be settled in advance.

### What the first reading did and did not license

It did not license a scope change. The subscribed set outscores the rest
(mean 0.757 vs 0.620, Cohen's d = 0.448), the relevance scorer does
discriminate between submolts (η² = 0.235 with a topically sensible
ordering), and six unsubscribed submolts sit at or above the weaker half of
the subscribed eight — but all of it rests on one sweep of one feed page,
so the stability of that ordering is unmeasured.

It did remove the retirement argument. The alternative "the unsubscribed
side turns out to be boring, so take the instrument out" is not what the
data shows, so signal-first does not currently support removal either.

Phase 2 (splitting scope into a read set and a respond set) and Phase 3
(shadow scope proposals) remain where the Decision left them. One sweep
cannot support them, and this amendment does not move that line.
