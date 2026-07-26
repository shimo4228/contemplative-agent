# ADR-0062 parser evidence (6th-11th amendments)

Offline replay evidence for the deterministic parser in
`adapters/moltbook/verification_parse.py`: the 2026-07-07 rewrite (ADR-0062,
6th amendment), the 2026-07-09 grammar extension from the post-rewrite
failure round (7th amendment), the 2026-07-15 round-8 extension from the
post-round-7 failure round (8th amendment), and the 2026-07-26 round-9
extension from the post-round-8 failure round (11th amendment; the 9th and
10th changed the solver chain and the parser's structure, not its grammar).

## Data source

`~/.config/moltbook/logs/verification-audit.jsonl` — the solver telemetry
introduced by ADR-0062's 2nd amendment. At rewrite time: 620 records / 601
unique challenges (2026-06-28..07-06); at the 7th amendment: 816 records /
792 unique challenges (..07-09); at the 8th amendment: 1310 records / 1272
unique challenges (..07-14); at the 11th: 2315 records / 2236 unique
challenges (..07-26). The corpus itself is NOT committed here (it keeps
growing locally); only the labels are.

Because the corpus is live traffic, a failing gate gets worse on its own: the
11th amendment's backlog measured 7 wrong at 2149 unique on 07-25 and 9 at
2236 on 07-26.

## Files

| File | Role |
|---|---|
| `replay_parser.py` | Replays `code_parse_challenge()` over every unique challenge in the local audit log. Pure code — no LLM, no network. Exit 0 only when the hard gate passes. |
| `differential_replay.py` | Replays the frozen `verification_parse_baseline.py` and the current parser over every distinct challenge text and requires them to agree, abstains included. For a refactor it must report zero mismatches; for a grammar change run it FIRST, and the mismatch list is the movement set you are claiming. |
| `verification_parse_baseline.py` | Frozen parser snapshot, refreshed at each grammar amendment so the next refactor has a "previous behaviour" to diff against. |
| `manual_labels.json` | Ground truth for challenges the server never accepted (base64 challenge + answer, hand-solved or twin-confirmed against an accepted same-shape challenge). A null answer marks a known-unresolvable challenge (excused from the gate, reported separately). Server-accepted records carry their own positive truth; server-REJECTED answers are negative truth handled by the harness itself. |

## Result (2026-07-26, 11th amendment)

```
unique challenges : 2236
parsed            : 1836 (coverage 82.1%)  # round-8 parser on same corpus: 82.4%
abstained         : 400
correct vs truth  : 1828
WRONG vs truth    : 0                      # hard gate: PASS
known-unresolvable: 8
```

Round-8 parser replayed on the SAME 2236-challenge corpus: 1842 parsed
(82.4%), 394 abstained, 1828 correct, **WRONG 9** against the label set as it
stood before this amendment (with the three new null labels in place the same
parser scores WRONG 6 and 3 excused — the labels are what moved those three,
not the grammar). Six were grammar and all six are now abstains — a
`total`-cued subtract chain that the "combined"-only guard let through, two
three-operand chains stepped over by a clause `and`, a `*` sitting inside a
unit phrase, and two tens+unit compounds whose mangled half vanished below
the fuzzy tiers ("treee" → "tre"; "trween" → "trwen", two edits from
everything). The other three were server anomalies and became null labels.

Correct is unchanged at 1828: this round bought precision only, and the whole
price is the 0.3-point coverage drop. That is the intended direction — a
wrong parse submits a wrong answer to the platform, an abstain just hands the
challenge to the LLM chain.

## Result (2026-07-15, 8th amendment)

```
unique challenges : 1272
parsed            : 1050 (coverage 82.5%)  # round-7 parser on same corpus: 82.4%
abstained         : 222
correct vs truth  : 1045
WRONG vs truth    : 0                      # hard gate: PASS
known-unresolvable: 5
```

Round-7 parser replayed on the SAME 1272-challenge corpus: 1048 parsed
(82.4%), **WRONG 5** — the five live code_parse wrongs of 2026-07-10..14
(silently dropped near-miss number words "thyree"/"qthreee", the unhandled
decimal "five point five", a double-counted prose restatement, and the
transposed marker "duoubbles"). Round 8 eliminates all five (poison /
compose / collapse / transposition-fuzzy) with a net coverage gain: the
near-miss poisoning costs a few abstains, more than repaid by the new
decimal and transposed-marker readings.

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

- Known-unresolvable (null-answer labels, 8): the server rejected the
  arithmetically forced or only-natural answer (`678acba8…` 27.00 = 23+4,
  `95f581b1…` 18.00 = 23-5, `a6be3443…` 36.00 = 32+4 with a literal `+`,
  `8379af3e…` 37.00 = 32+5, and from the 11th amendment `03861657…`
  40.00 = 33+7, `6661823a…` 5.00 = 20-15, `cb59e684…` 23.00 = 35-12), or
  contradicts its own accepted twins (`b22c4bed…` "accelerates by four":
  27.00 rejected while "accelerates by five/seven" = add is accepted
  throughout). 0.36% floor no solver can clear.
- The three 11th-amendment entries are twin-confirmed, not merely
  arithmetic: `03861657…` against `06b428962fef92f5` ("lobsters claws exert
  thirty five newtons and the other claw exerts twelve … total" = 47.00
  accepted, which also settles that a plural "claws" does not double the
  first operand), `6661823a…` and `cb59e684…` against `d06a5d4a3beab3f1`
  ("drag reduces speed by seven … what is the new speed" = 16.00 = 23-7
  accepted). Watch the shape distribution: four of the eight are now the
  same "X and Y, total force" additive form, which looks more like a
  server-side pattern than random flake.
- `d415b4b7…`: "two times as much … total?" — labeled 60.00 by elimination
  (the historical llm_reason submission 90.00 = 30+30×2 was rejected).

## Reproduce

```bash
# Grammar change: run this FIRST, and check the mismatch list is exactly the
# challenges you meant to move. It exits non-zero on any difference by
# design — for a grammar amendment that is the report, not a failure.
uv run python docs/evidence/adr-0062-parser-rewrite/differential_replay.py

# Then the ground-truth gate. Exit 0 only on zero wrong AND zero unlabeled.
uv run python docs/evidence/adr-0062-parser-rewrite/replay_parser.py
```

Anything printed under "parsed but unlabeled" must be hand-verified into
`manual_labels.json` before the gate can pass — hand-solved from the decoded
text, or twin-confirmed against a server-accepted same-shape challenge.
