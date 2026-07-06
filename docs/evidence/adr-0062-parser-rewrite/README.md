# ADR-0062 6th amendment — deterministic parser rewrite evidence

Offline replay evidence for the 2026-07-07 rewrite of
`adapters/moltbook/verification_parse.py` (see ADR-0062, 6th amendment).

## Data source

`~/.config/moltbook/logs/verification-audit.jsonl` — the solver telemetry
introduced by ADR-0062's 2nd amendment. At rewrite time: 620 records / 601
unique challenges (2026-06-28..07-06). The corpus itself is NOT committed
here (it keeps growing locally); only the 40 hand-solved labels are.

## Files

| File | Role |
|---|---|
| `replay_parser.py` | Replays `code_parse_challenge()` over every unique challenge in the local audit log. Pure code — no LLM, no network. Exit 0 only when the hard gate passes. |
| `manual_labels.json` | Ground truth for challenges the server never accepted (base64 challenge + hand-solved answer). Server-accepted records carry their own truth. |

## Result (2026-07-07, HEAD of the rewrite)

```
unique challenges : 601
parsed            : 498 (coverage 82.9%)   # was 58% live before the rewrite
abstained         : 103
correct vs truth  : 498
WRONG vs truth    : 0                      # hard gate: PASS
```

Live baseline (same corpus window, old parser + LLM chain): overall wrong
rate 11.3% (70/620 records), of which `code_parse` itself submitted 4 wrong
answers (invisible misspelled number words: "fife"/"twenny"/"thrirty").

## Label caveats

- `678acba8…` and `95f581b1…`: the server rejected the only arithmetically
  natural answer (27.00 = 23+4, 18.00 = 23-5). Labeled by arithmetic and
  treated as server-side anomalies (2/601 = 0.33% floor).
- `d415b4b7…`: "two times as much … total?" — labeled 60.00 by elimination
  (the historical llm_reason submission 90.00 = 30+30×2 was rejected).

## Reproduce

```bash
uv run python docs/evidence/adr-0062-parser-rewrite/replay_parser.py
```
