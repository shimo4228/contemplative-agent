# ADR-0062 parser evidence (6th + 7th amendments)

Offline replay evidence for the deterministic parser in
`adapters/moltbook/verification_parse.py`: the 2026-07-07 rewrite (ADR-0062,
6th amendment) and the 2026-07-09 grammar extension from the post-rewrite
failure round (7th amendment).

## Data source

`~/.config/moltbook/logs/verification-audit.jsonl` — the solver telemetry
introduced by ADR-0062's 2nd amendment. At rewrite time: 620 records / 601
unique challenges (2026-06-28..07-06); at the 7th amendment: 816 records /
792 unique challenges (..07-09). The corpus itself is NOT committed here (it
keeps growing locally); only the labels are.

## Files

| File | Role |
|---|---|
| `replay_parser.py` | Replays `code_parse_challenge()` over every unique challenge in the local audit log. Pure code — no LLM, no network. Exit 0 only when the hard gate passes. |
| `manual_labels.json` | Ground truth for challenges the server never accepted (base64 challenge + answer, hand-solved or twin-confirmed against an accepted same-shape challenge). A null answer marks a known-unresolvable challenge (excused from the gate, reported separately). Server-accepted records carry their own positive truth; server-REJECTED answers are negative truth handled by the harness itself. |

## Result (2026-07-09, 7th amendment)

```
unique challenges : 792
parsed            : 659 (coverage 83.2%)   # 6th amendment: 82.9% on 601
abstained         : 133
correct vs truth  : 654
WRONG vs truth    : 0                      # hard gate: PASS
known-unresolvable: 5
```

6th-amendment result (2026-07-07, 601 challenges): coverage 58% → 82.9%
(498 parsed, all correct), hard gate PASS. Live baseline before the rewrite
(same corpus window, old parser + LLM chain): overall wrong rate 11.3%
(70/620 records), of which `code_parse` itself submitted 4 wrong answers
(invisible misspelled number words: "fife"/"twenny"/"thrirty").

## Label caveats

- Known-unresolvable (null-answer labels, 5): the server rejected the
  arithmetically forced or only-natural answer (`678acba8…` 27.00 = 23+4,
  `95f581b1…` 18.00 = 23-5, `a6be3443…` 36.00 = 32+4 with a literal `+`,
  `8379af3e…` 37.00 = 32+5), or contradicts its own accepted twins
  (`b22c4bed…` "accelerates by four": 27.00 rejected while "accelerates by
  five/seven" = add is accepted throughout). ~0.6% floor no solver can
  clear.
- `d415b4b7…`: "two times as much … total?" — labeled 60.00 by elimination
  (the historical llm_reason submission 90.00 = 30+30×2 was rejected).

## Reproduce

```bash
uv run python docs/evidence/adr-0062-parser-rewrite/replay_parser.py
```
