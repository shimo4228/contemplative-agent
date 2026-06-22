# ADR-0061: Action-Time Untrusted Input Caps at Platform Field Limits; Internal Note Reads the Full Body

## Status

accepted

## Date

2026-06-23

## Context

Weekly diagnosis finding F1.1 (first surfaced 2026-06-15, recurring 06-18 and 06-21) reported that
the agent's internal notes contained mechanical mid-word truncations — phrases ending mid-sentence
such as "...isn't na" — that the contemplative register was re-reading as deliberate authorial
pauses or invitations rather than as clipping artefacts. The finding appeared stable across three
consecutive weekly reports.

The original F1.1 diagnosis located the cause in a code path:
`_io.truncate()` → `content_summary` → `reply_handler.history_summaries` →
`_build_context_section`. A 2026-06-23 re-diagnosis using a 10-agent ultracode trace with
adversarial verification found this path to be dead: `history_summaries` and
`_build_context_section` were removed by [ADR-0059](./0059-remove-dead-reply-history.md), and
`content_summary`'s sole reader is unreachable after [ADR-0060](./0060-per-episode-grounded-distill.md)'s
`_is_rich_episode` activity-only filter. The truncation symptom survived on a live code path that
the original diagnosis did not reach.

The re-diagnosis confirmed two real defects on the action-time path.

The first defect concerns the internal note. `feed_manager` generated the note (`generate_internal_note`)
before invoking `_fetch_full_if_truncated`, that is, "on the preview by design" as a cost
optimisation. The submolt-feed server delivers a `FEED_CONTENT_PREVIEW_LEN=500` character preview
for each post. Because 500 is less than the note's `max_input=1000`, `wrap_untrusted_content`
(established by [ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md)) emitted
a false "complete (500 chars)" marker over a body the server had already clipped mid-word. The
wrapper saw 500 characters, which fit under its 1000-character cap, and reported the content as
complete — when in fact the server had truncated it before delivering it.

The second defect concerns the action-generation callers more broadly. When `wrap_untrusted_content`
itself truncated (`post_text[:max_input]` at `max_input=8000` for comment and reply), the marker
was honest ("truncated"), but the truncated residual still ended mid-word. The contemplative
register re-read that mid-word edge as a deliberate pause even when the marker was honest. The
reason action-time generation callers passed a small `max_input` was solely a `num_ctx`-overflow
safety valve: `generate()` in `core/llm.py` skips a call when the estimated
`system + prompt + num_predict > NUM_CTX (32768)`, protecting the front-loaded value layer. This
safety rationale does not require a 8000-character cap: real Moltbook posts measure p90 ≈ 4700
characters and max ≈ 7400 characters, well within `NUM_CTX` at the platform's actual field limits.

[ADR-0060](./0060-per-episode-grounded-distill.md) established the pattern of setting distill
excerpt caps to the Moltbook platform field limits (`EXCERPT_CAPS = {original_post: MAX_POST_LENGTH,
their_comment: MAX_COMMENT_LENGTH, ...}`) "so realistic content is never cut," retaining
`truncate_boundary` only as a structural guard for out-of-spec data. The action-time path had not
adopted this policy.

## Decision

Raise the action-time untrusted-input caps to the Moltbook platform field limits and fetch the
full post body before the internal note.

1. **Raise `generate_comment` post-body cap** from 8000 to `MAX_POST_LENGTH` (40000), sourced
   from `core/config.py`.

2. **Raise `generate_reply` caps** for both `original_post` (8000 → `MAX_POST_LENGTH`) and
   `their_comment` (8000 → `MAX_COMMENT_LENGTH`, 10000).

3. **Raise `generate_internal_note` content cap** from 1000 to `MAX_POST_LENGTH + MAX_COMMENT_LENGTH`
   (50000). The note's content is a post body on the feed path and a post-plus-comment body on the
   reply path; the combined platform ceiling is the correct upper bound.

   Because real content cannot exceed the platform field limits, `wrap_untrusted_content`'s
   truncation branch never fires on real content at these caps. The marker is always honestly
   "complete" and the mid-word edge no longer occurs. The cap remains a `num_ctx` safety valve.
   Measured (2026-06-23) against the production value layers: the full system prompt is ≈14.5K
   tokens by `_estimate_tokens` (six skills dominate at ≈11.8K) and the comment/reply output
   budget is `num_predict` ≈6.7K tokens, leaving ≈11.6K tokens of input headroom under
   `NUM_CTX=32768`. So `generate()`'s budget guard skips an ASCII post above ≈34.8K chars or a CJK
   post above ≈11.6K chars — both far above the observed production max (≈7.4K chars), so realistic
   content always fits with margin. An outsized post is **skipped** (logged, value layer protected),
   not silently truncated mid-word; engaging on a boundary-truncated partial was rejected (see
   Alternatives) in favour of skipping, consistent with the full-content intent of this ADR.

4. **Gate and classification caps are unchanged.** `score_relevance=1000`, `select_submolt=1000`,
   and `summarize_post_topic=2000` remain small. These functions run on every feed post as cheap
   gates and produce no prose; a mid-word cut there is harmless and does not propagate to any
   generated or stored artefact.

5. **Fetch the full post body before the internal note** in `feed_manager`'s feed-engagement path
   (gated on `score >= min(upvote_only_threshold, threshold)`). The previously separate full-fetch
   call before `create_comment` is removed; the single earlier fetch is the source of the full body
   for both the note and the comment. `_fetch_full_if_truncated` remains idempotent and
   read-budget-aware: it falls back to the preview when the read budget is exhausted.

6. **No change to `wrap_untrusted_content` or `truncate_boundary`** (`core/llm.py`). The fix is
   entirely in caller cap values and fetch ordering; the wrapper contract established by
   [ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md) is unchanged.

## Alternatives Considered

### Add `content_full_len` to the original F1.1 dead path

The original F1.1 proposal was to retain the original length in a `content_full_len` field on the
`content_summary` path and emit a truncated marker even when the content appeared to fit within the
cap. Rejected: that path (`history_summaries` / `_build_context_section`) was removed by
[ADR-0059](./0059-remove-dead-reply-history.md) and is unreachable after
[ADR-0060](./0060-per-episode-grounded-distill.md). Patching a dead path would fix nothing.

### Make `wrap_untrusted_content` slice at a word or sentence boundary

Reuse `truncate_boundary` inside the wrapper so that any residual ends at a clean boundary and
report the honest residual length. Rejected as the primary fix. Once caller caps equal the platform
field limits, real content is never truncated by the wrapper, so boundary-aware slicing would fire
only on out-of-spec input that the platform guarantees cannot occur. Adding double-marker logic and
character-count reporting inside the wrapper introduces complexity for a case that is structurally
excluded. `truncate_boundary` remains as distill's out-of-spec structural guard per
[ADR-0060](./0060-per-episode-grounded-distill.md) and is not moved into the wrapper.

### Raise the cap only, without moving the full-fetch earlier

Keep generating the note on the 500-character server preview but raise `generate_internal_note`'s
cap to `MAX_POST_LENGTH`. Rejected: a higher cap does not un-clip a body the server already
delivered as a 500-character preview. `wrap_untrusted_content` would still see 500 characters, still
report "complete," and the note would still read a mid-word-clipped body. The false-complete marker
defect is corrected only by fetching the full body first.

### Move note generation after the comment decision

Generate the internal note only for posts that clear the comment threshold, so the full-fetch cost
is incurred only for those posts. Rejected: the internal note is also generated for the upvote-only
episode (posts with `score >= upvote_only_threshold` but below the comment threshold). The note
must be generated before the comment decision to serve both paths.

## Consequences

### Positive

- The internal note and generated comment and reply all read the full post body. The false-complete
  marker over a server-clipped 500-character preview is eliminated. The mid-word edge that the
  contemplative register misread as a deliberate pause no longer occurs on real content.
- Action-time cap policy now mirrors the distill `EXCERPT_CAPS` pattern established by
  [ADR-0060](./0060-per-episode-grounded-distill.md): caps are set at platform field limits, and
  `wrap_untrusted_content`'s truncation branch is structurally excluded from real-content paths.
- The previously separate full-fetch call before `create_comment` is removed, consolidating the
  fetch into one earlier call that serves both the note and the comment generation.

### Negative

- The full body is now fetched for every post clearing the engagement bar
  (`score >= min(upvote_only_threshold, threshold)`), not only for posts that proceed to a comment.
  This increases the number of GET requests. The increase is bounded by `_fetch_full_if_truncated`'s
  read-budget guard (falls back to preview when the read budget is low) and by the per-author
  pacing and gate logic that limits which posts reach the engagement bar.

### Neutral / Follow-ups

- The exact origin of the specific 2026-06-15, 06-18, and 06-21 fragment truncations cannot be
  confirmed from code alone; reading internal-note episode logs directly is prohibited as a prompt
  injection path (CLAUDE.md). The 500-character preview defect is the strongest code-level
  candidate and is fixed. A source-author-text or model-own-generation origin cannot be ruled out.
  Watch for recurrence after this fix is deployed.
- The reply path's note reads notification `post_content`, which has no documented 500-character
  preview clamp (that clamp is submolt-feed-specific). If notification payloads also deliver
  previews rather than full bodies, the full-fetch principle would need to extend to the reply
  path's note. Currently unverified.
- `tests/test_llm.py` truncation assertions for `generate_comment`, `generate_reply`, and
  `generate_internal_note` require updating: realistic-length content under the platform limits is
  now marked "complete"; out-of-spec content is truncated at the platform field limit.
  `tests/test_agent.py` gains a regression asserting that the internal note runs on the full body,
  not the 500-character preview.
- Extends [ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md) (truncation
  contract) and [ADR-0060](./0060-per-episode-grounded-distill.md) (platform-limit cap pattern)
  to the action-time path. Relates to [ADR-0059](./0059-remove-dead-reply-history.md) (which
  removed the dead path F1.1 originally named), [ADR-0045](./0045-pre-action-internal-note.md)
  (pre-action internal note), and [ADR-0007](./0007-security-boundary-model.md) (untrusted
  boundary). Supersedes nothing.

## References

- [ADR-0007](./0007-security-boundary-model.md) — untrusted boundary model; `wrap_untrusted_content`
  is the enforcement mechanism this ADR extends to the action-time path.
- [ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md) — explicit truncation
  contract for the untrusted wrapper; this ADR extends the contract to action-time callers.
- [ADR-0045](./0045-pre-action-internal-note.md) — introduced the pre-action internal note that
  this ADR ensures reads the full post body rather than the server preview.
- [ADR-0059](./0059-remove-dead-reply-history.md) — removed `history_summaries` and
  `_build_context_section`, rendering the original F1.1 diagnosis path dead.
- [ADR-0060](./0060-per-episode-grounded-distill.md) — established the platform-field-limit cap
  pattern in distill (`EXCERPT_CAPS`); this ADR applies the same pattern to action-time generation.
