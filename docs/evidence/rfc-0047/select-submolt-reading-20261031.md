# `select_submolt` None rate — one reading (2026-10-31, P1-07.16)

Read once on the production machine. No model output is logged for this call
(`llm-calls-*.jsonl` keeps hashes and counts only), and the exact-match /
substring / unrecognized split is written only as INFO / WARNING lines of
`logs/agent-launchd.log`, which this reading does not open (CLAUDE.md
episode-log exclusion). So the None rate is read through a proxy and the
substring-match rate is not read.

## Proxy

`_choose_submolt` returns None only to skip the post (`post_pipeline.py`:
"skip, don't substitute"); a non-None pick goes on to `POST /posts`. Per
session, select calls (`llm-calls-*.jsonl`, `caller: moltbook.select_submolt`)
minus `POST /posts` rows (`api-audit.jsonl`) bounds the None count from above
(a later failure before the POST would also count).

| | value |
|---|---|
| window | 2026-07-16 .. 2026-10-31 (rows carrying `session_id`) |
| sessions with a select call | 410 |
| select calls | 572 (all `outcome: ok`) |
| `POST /posts` in those sessions | 570 |
| sessions with one select not followed by a post | 2 |
| upper bound on the None rate | 2 / 572 = 0.35% (Wilson 95%: 0.10% .. 1.27%) |

## Judgement

The whole interval sits below 5%, so the enum `format=` schema is not switched
in (the item's rule: switch only if the rate is above 5% across the interval).
The substring-match rate stays unread; reading it needs a counter on a path
this session may open (for example a reason code in `llm-calls`), which is a
code change and is not made here.
