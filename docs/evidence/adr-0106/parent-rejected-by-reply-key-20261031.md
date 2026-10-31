# `parent_rejected` per reply key (2026-10-31)

One-shot reading named in [RFC-0049](../../../rfcs/0049-publish-row-reply-target.md)
("次の読み", P0-01.9) for the [ADR-0106](../../adr/0106-comment-outcome-recording.md)
D3 columns. Read on the production machine over `logs/skill-selection-*.jsonl`
(2026-07-10 .. 2026-10-31), `kind: "publish"` rows only; ids and hashes only,
no bodies. Not refreshed.

| count | value |
|---|---|
| publish rows | 3,858 (`failure_reason` null 3,728 / `parent_rejected` 128 / `unknown` 2) |
| `parent_rejected` rows carrying `reply_key_sha256` | 93 (2026-10-07 .. 2026-10-31) |
| `parent_rejected` rows without it (before RFC-0049 landed) | 35 |
| distinct `reply_key_sha256` among the 93 | 93 — every key appears exactly once |
| distinct `parent_comment_id` among the 93 | 93 — every parent appears exactly once, none null |
| other publish rows sharing one of those 93 keys | 0 — no rejected key was attempted again, in the same session or a later one |

Per day the 93 spread from 1 to 13 (largest 10-19 with 13, 10-23 with 10,
10-20 with 9); no day concentrates them.

## Reading against RFC-0049's two explanations

- (b) "the terminal mark does not survive across sessions" predicts the same
  `reply_key_sha256` rejected more than once. Observed: never.
- (a) "a different comment each time" predicts keys and parents spread, each
  once. Observed: exactly that.

So the reading leans to (a): the RFC-0038 terminal mark holds (no key is retried
after a rejection), and each `parent_rejected` is a first attempt at a parent the
platform no longer accepts. Proposal for the gate: record (a), file no new RFC.
The owner decides.
