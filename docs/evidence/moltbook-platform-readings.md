# Moltbook platform readings

A ledger of when a person last read the platform's specification (`https://www.moltbook.com/skill.md`) or terms, and which constants in this repository rest on that reading. The unattended chain never fetches these (`scripts/api_drift_scan.py` only detects response-shape drift); a reading is a human act.

Re-read when: (i) a Saturday gate sees an Action row from the drift scan, (ii) a dataset version is cut, (iii) once a quarter.

Consumption plan (ADR-0101): (a) the owner reads this file at those Saturday gates. (b) One reading decides one of: nothing changed (add a row to table 1), a constant must change (change it, update table 2), or a platform change needs a decision (open an RFC; the end-state RFCs if it threatens the project). (c) At wind-down, write a last row stating the platform's state at closure; the file is not updated afterwards.

Entries below were transcribed from dated comments already in the repository. A cell reading `unconfirmed` means no dated reading is known; it is not a claim that the value is wrong.

## Table 1 - readings

| Date | URL | sha256 of what was read | Points checked | Difference from the previous reading | Read by |
|---|---|---|---|---|---|
| 2026-05-04 | https://www.moltbook.com/skill.md | not recorded | post body 40,000 chars, title 300 chars, comment limits (`core/config.py`) and the ADR-0018 length figures | - | not recorded |
| 2026-08 (day not recorded) | https://www.moltbook.com/skill.md | not recorded | account suspension follows 10 consecutive verification failures (`scripts/api_drift_scan.py`) | not recorded | not recorded |
| 2026-09-09 | https://www.moltbook.com/skill.md | not recorded | `/home` `activity_on_your_posts` carries no comment id / upvote / thread structure; `GET /posts/{id}/comments` carries ids, `upvotes` and nested `replies` (`core/comment_outcomes.py`, ADR-0106) | the shape RFC-0028 had assumed was refuted | not recorded |
| 2026-10-31 | https://www.moltbook.com/skill.md (frontmatter `version: 1.12.0`) | `10f3c03a17cf42c79642e73e2d3bf3255743f22de5d6db215ac6c6b3cd1b28c9` (38,214 bytes) | every constant in table 2; `/home` keys and the role `check_in` briefing; terms / reuse clauses | (1) **comments: 50 per day** (repo default 300; the agent has posted more than 50 comments on 126 of 129 days with zero 429s in `api-audit.jsonl`); **settled 2026-11-04 (RFC-0068): default set to 50, the page's figure**. (2) the documented 429 body says `"Rate limit exceeded"`; the text `limit reached` that `client.py` reads as a hard limit does not appear (zero 429s observed, so not yet exercised); **settled 2026-11-04 (RFC-0068): a 429 is hard when `Retry-After` exceeds `MAX_RETRY_AFTER` (300 s) or the body says `limit reached`, soft otherwise; each decision is a reason code in `api-audit.jsonl`**. (3) suspension: "your last 10 challenge attempts are all failures" (a window of 10, not a streak). (4) `Retry-After` example is an integer `45`. (5) new-agent limits for the first 24 h. (6) no reuse / research / terms clause in the file. Comment length and feed preview length are not stated | Claude Code (attended session, read through a subagent; the owner did not read it) |

The next row is written by the next person who reads the page: date, the sha256 of the text read (`curl -s URL | sha256sum`), the points checked, what differs from the row above.

## Table 2 - constants that come from the platform

| Constant | Where | Value | Last confirmed | What it affects when the platform changes |
|---|---|---|---|---|
| post / comment length limits | `core/config.py` (comment "verified via skill.md") | 40,000 / 300 (title) | 2026-10-31 (post body and title; comment length not stated) | publish filter and `MAX_*_LENGTH` truncation |
| verification-failure suspension | `scripts/api_drift_scan.py` | 10: the last 10 attempts all failures | 2026-10-31 | the drift scan's warning threshold |
| `MAX_VERIFICATION_FAILURES` | `adapters/moltbook/config.py` | 7 (own margin under the platform's 10) | unconfirmed | when a session stops itself; with the carry-over of P1-07.3, across sessions: the carried streak plus the session's failures is held to `VERIFICATION_CARRYOVER_CEILING` (8); a session that starts there attempts nothing (`end_reason: verification_carryover_ceiling`) and the owner clears it by moving `verification-audit.jsonl` aside |
| `VERIFICATION_CARRYOVER_CEILING` | `adapters/moltbook/config.py` | 8 (two under the platform's 10) | unconfirmed | the cross-session stop; raise it only after the 10-consecutive rule is confirmed |
| `/home` and comments response shape | `core/comment_outcomes.py`, `adapters/moltbook/client.py` `_EXPECTED_KEYS` | see ADR-0106 | 2026-09-09 | the comment-outcome recorder, drift warnings |
| `FEED_CONTENT_PREVIEW_LEN` | `adapters/moltbook/config.py` | 500 | unconfirmed | `feed_manager` treats a length of exactly 500 as truncated and re-fetches; if the platform's preview length changes, the re-fetch silently stops |
| `RateLimits` and the GET 60 / POST 30 per minute figures | `adapters/moltbook/config.py`, `CLAUDE.md` | 1800 s post interval, 20 s comment interval, 50 comments/day; 60 / 30 per min | 2026-10-31: all match except comments/day, which the page gives as 50; 2026-11-04: comments/day lowered from 300 to 50 (RFC-0068) | the three-layer rate-limit defence |
| hard-limit 429 rule | `adapters/moltbook/client.py` `_classify_429` | hard when `Retry-After` > `MAX_RETRY_AFTER` (300 s), or the body contains `limit reached`; otherwise soft (retried, at most `MAX_RETRY_ON_429`). `api-audit.jsonl` records `rate_limit_reason`: `hard_retry_after` / `hard_phrase` / `soft_retry` / `soft_exhausted` | 2026-10-31: the page's 429 body says `Rate limit exceeded`; 2026-11-04: rule moved off the phrase to the header (RFC-0068) | a daily limit sent with a short or missing `Retry-After` and without the phrase is retried up to 3 times before it counts as terminal (`soft_exhausted`); a much longer wait cap on the platform side would show as `hard_retry_after` |
| `Retry-After` format | `adapters/moltbook/client.py` | a float number of seconds | 2026-10-31: integer seconds in the example; `float()` parses it | a missing value, an HTTP-date, or a negative / non-finite number falls back to 60 s, soft (`retry_after_source`: `missing` / `unparseable`) |
| redirect behaviour (API base URL) | `adapters/moltbook/config.py` `BASE_URL` | `https://www.moltbook.com/api/v1`; a 3xx now raises (P1-07.18) | 2026-10-31 (the page warns that the non-`www` host redirects and drops the Authorization header) | a version bump or domain move would first show as 301 / 308 |

The terms of service were first read on 2026-10-31 (Terms of Service and Privacy Policy, both "Last Updated: March 15, 2026"); the reading and its decision are in ADR-0010's amendment of that date.
