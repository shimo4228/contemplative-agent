# ADR-0063: Scope the NoveltyGate Comparison to Verified (Visible) Posts

## Status

accepted

## Date

2026-06-26

## Context

[ADR-0062](./0062-create-time-verification-handshake.md) fixed the create-time verification
handshake so that new posts and comments can become publicly visible. Immediately after that fix
was deployed a 60-minute live autonomous session reached post generation exactly once; the
NoveltyGate ([ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md)) rejected the draft
with `reason=reject:low_novelty`, reporting `novelty=0.25` and `nearest=0.79` against a prior post
titled "Can Optimization Cages Still Reach Meaning Without Arrival?". The agent produced zero new
visible posts across the entire session.

The root cause is in how the NoveltyGate selects its comparison set. The gate deduplicates a draft
against the agent's recent post records via `memory.get_recent_posts(limit=50)`. All 349 of the
agent's stored posts carry `verification_status=pending`: they were created before ADR-0062 fixed
the handshake, so their five-minute challenge windows expired without a successful `/verify` call,
and they are permanently invisible and unrecoverable on the platform. Measured in the session log:
`posts_count=349`; the most recent 40 were all pending. The gate was comparing drafts against posts
that no reader ever saw, and then silently refusing to generate anything new.

A secondary defect compounded the silence. The rate-deficit Lagrangian term in
[ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) is designed to loosen the admission
threshold when the agent has been genuinely silent: `mu · (target_rate − actual_rate)` grows
positive when `actual_rate` is low. But `actual_rate` is computed by `get_post_rate_7d()`, which
counted all post records in the seven-day window regardless of verification status. Because the 349
pending posts were still in that window, the agent appeared active and the deficit term produced a
near-zero contribution, leaving the threshold unchanged.

Comments and replies were unaffected throughout: they do not pass through the NoveltyGate, so
the pending-only history blocked only post generation.

## Decision

1. **Scope the NoveltyGate comparison set to verified (visible) posts only.** Add `verified: bool`
   to `PostRecord` (frozen dataclass, `default=False`). `record_post(..., verified: bool = True)`
   sets the flag to `True`; because the post pipeline — post-ADR-0062 — records only after the
   verification handshake succeeds, every newly recorded post is marked verified at write time.
   `get_recent_posts(limit, verified_only=False)` gains a `verified_only` keyword argument;
   `post_pipeline._run_dynamic_post` now calls it with `verified_only=True`. The filtered list
   feeds both the NoveltyGate cosine-similarity comparison and the body-hash deduplication check,
   so both gates compare a draft only against posts that were actually published.

2. **Rely on backward-compatible deserialization; do not mutate the append-only episode log.**
   Pre-fix "post" episodes were serialized without a `verified` key. The load path reconstructs
   `PostRecord(**data)` from the episode JSON; when `verified` is absent the dataclass falls through
   to its field default (`False`). The 349 pending posts therefore deserialize as unverified and are
   excluded from the comparison set automatically — without any episode-log edit, backfill, or
   migration, and in full compliance with the no-delete-episodes invariant.

3. **Do not scope the rate-deficit term to verified-only.** `get_post_rate_7d()` continues
   counting all post records. With the comparison set now limited to verified posts — initially
   empty — `novelty=1.0` for any well-formed draft, which is sufficient to clear the admission
   threshold immediately. Scoping the rate term to verified-only as well would, during the rebuild
   window when verified-post count is near zero, produce `deficit ≈ target_rate`, causing
   `mu · deficit` to dominate the score and admit near-duplicate verified posts every 30 minutes —
   reintroducing the May-2026 echo chamber (40 near-identical posts) that the gate was built to
   prevent. Leaving the rate counting all posts keeps `deficit ≈ 0` during the rebuild window
   (the pending posts still sit in the seven-day window and age out gradually); once verified posts
   accumulate, the novelty comparison correctly blocks near-duplicates. A code review confirmed
   there is no regime in which leaving the rate unchanged re-silences the agent: with an empty
   verified set `novelty=1.0` regardless of the deficit term.

## Alternatives Considered

### Scope the rate-deficit term to verified-only as well

Count only verified posts in `get_post_rate_7d()` so both the comparison set and the rate signal
are consistent. Rejected: at fix time the verified count is zero, so
`deficit = target_rate − 0 = target_rate`. The term `mu · deficit` would dominate the total score
and admit posts on the deficit alone, bypassing the novelty comparison that protects against
near-duplicates. Scoping the comparison set is sufficient to unblock posting without this risk; the
rate-deficit's purpose is to break prolonged genuine silence, which is not the current condition.

### Purge or rewrite the 349 pending post records and their embeddings

Remove the pending records from the episode log or overwrite them so they no longer appear in
`get_recent_posts`. Rejected: post records are derived from episodes on every load; deleting or
patching the episodes would violate the no-delete-episodes / append-only episode-log invariant. A
purge applied only to the in-memory index would not survive a restart. The backward-compatible
deserialization approach achieves the same exclusion without touching the episode log.

### Lower the NoveltyGate admission threshold (theta) globally

Reduce `theta` so that more drafts clear the gate regardless of their similarity to prior posts.
Rejected: a lower global threshold weakens deduplication against genuinely visible posts and risks
re-introducing the echo chamber on the visible-post corpus as it grows. It does not address the
underlying defect — comparing a draft against content that was never seen — and leaves the agent
vulnerable to the same problem if a second batch of pending posts accumulates.

### Do nothing and wait for the rate-deficit term to loosen as pending posts age out

Allow the seven-day window to drain as the 349 pending posts age past the seven-day horizon,
eventually lowering `actual_rate` and widening the deficit enough for the threshold to loosen.
Rejected as a primary fix: the drain is slow and the outcome is unreliable. Even with a wider
threshold a draft with `novelty=0.25` and `nearest=0.79` can still be blocked, because the
comparison set still contains the invisible posts. The wait period would extend to roughly seven
days, during which the agent remains silent. Aging-out is a useful secondary property of keeping
the rate count unchanged (Decision 3), not a stand-alone remedy.

## Consequences

### Positive

- The agent can produce visible posts again. With the verified comparison set initially empty,
  `novelty=1.0` for any well-formed draft; the next admitted draft verifies via ADR-0062 and
  becomes the first visible post. Subsequent drafts are then deduped against the growing set of
  visible posts.
- Dedup semantics now match their intent: "do not repeat something readers have seen" rather than
  "do not repeat something nobody saw." Themes that existed only as pending posts are no longer
  treated as repeats; re-surfacing them is correct behaviour.
- No episode-log mutation or migration is required. The change is a backward-compatible field
  addition to `PostRecord`, and the append-only invariant is fully preserved.

### Negative

- The agent may publish posts thematically similar to its 349 invisible pending posts. This is the
  intended outcome — those posts were never seen — but early visible posts may echo old pending
  drafts. Readers encounter the content for the first time; the agent does not.
- Two denominators now differ: the NoveltyGate comparison set is verified-only, while the
  rate-deficit term counts all posts. This asymmetry is deliberate (Decision 3) but is a subtlety
  a future reader must hold when reasoning about the gate's behaviour during the rebuild window.

### Neutral / Follow-ups

- Pre-existing, not introduced here: `_load_episodes_into_memory` does not enforce
  `MAX_POST_HISTORY` on load while `record_post` does. The in-memory post history and the
  rate-deficit window can therefore be computed over slightly different denominators after a
  high-volume write window. Worth a future cleanup pass.
- If the rebuild phase produces near-duplicate verified posts slipping through, revisit whether a
  verified-aware rate term with a non-zero floor — to avoid the override identified above — is
  warranted. The floor value would need to be set high enough to preserve the deficit term's
  "break genuine silence" purpose without letting it override novelty during normal operation.

## References

- [ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) — NoveltyGate: continuous novelty
  scoring and rate-deficit Lagrangian term; this ADR scopes the comparison input to that gate.
- [ADR-0062](./0062-create-time-verification-handshake.md) — create-time verification handshake;
  establishes `verification_status` and the post-verification recording order that this ADR builds
  on. The `verified` field on `PostRecord` is set at write time because recording is gated on
  verification success by ADR-0062.
- Implementation: `memory.py` (`PostRecord`, `record_post`, `get_recent_posts`),
  `post_pipeline.py` (`_run_dynamic_post`). Same change set as the post-ADR-0062 follow-ups.
- Related: the no-delete-episodes / append-only episode-log invariant documented in `CLAUDE.md`;
  backward-compatible deserialization relies on this property being stable across restarts.
