# RFC-0027 — one-time comparison, per-axis facts (2026-09-12)

Facts only. No winner, no threshold, no adoption verdict, and no column scoring an arm's answer
against the selection's diagnostic corner label. The reading belongs to the owner.
Selection method and exclusions: [README.md](README.md).

## Known defect in this run: the corner label reached one arm's prompt

The case ids emitted by the selector begin with the diagnostic corner
(`reconfirm-…` / `revise-…` / `new-…` / `insufficient-…`), and
`scripts/insight_revision_compare.py::_call_current` passes `case_id` into the extraction prompt's
`{subcategory}` slot. **The current arm therefore saw the corner label on all 12 cases; the
proposed arm never did** (its two prompts take only observations and supplied skills). The label was
meant as a selection tag, not an input signal, and the leak is asymmetric between the two arms.

The pre-registration fixes one run with no retry, so this run stands as executed and is reported
with the defect named rather than re-run. Any re-run must first make the case id opaque
(`scripts/rfc0027_select_cases.py` line 168 builds it) and keep `kind_label` in the sidecar only.
Found in review after the run, 2026-09-12.

## Run metadata

| | |
|---|---|
| Cases | 12, from `evals/fixtures/rfc0027_production_cases_20260912.json` (`schema_version: 1`), sha256 `445857b1…` |
| Arms | `--arm both` (`scripts/insight_revision_compare.py`), one run, no retry |
| Model | gemma4:e4b via local Ollama (production generation model), num_ctx 32768 |
| Started / finished | 2026-09-12 15:35:52 → 15:55:30 JST (19.6 min wall clock, outside the 18:00 session window) |
| Prompt sha256 | system `fa95c889…`, insight_extraction `915025480842…`, insight_revision_reason `22566e01…`, insight_revision_generation `0ab81cd5…` |
| Raw output | `comparison-20260912.json` — current arm at `arms.current.cases[i].result`, proposed arm at `arms.proposed.cases[i].reason` / `.candidate`, matched by `case_id` |
| Table rendered by | `scripts/rfc0027_render_fact_table.py` (every column recomputable from the two JSON files) |

## Per-case facts

| case | selection corner | current: status / chars / ms | current: frontmatter / description chars / headings |
|---|---|---|---|
| `reconfirm-p03700-2026-07-21` | reconfirm | generated / 1415 / 77376 | yes / 114 / 4 |
| `reconfirm-p07888-2026-09-05` | reconfirm | generated / 1488 / 90703 | yes / 115 / 3 |
| `reconfirm-p06935-2026-08-24` | reconfirm | generated / 1451 / 73692 | yes / 154 / 4 |
| `revise-p03375-2026-07-18` | revise | generated / 1471 / 84241 | yes / 98 / 4 |
| `revise-p08206-2026-09-08` | revise | generated / 1920 / 93427 | yes / 108 / 4 |
| `revise-p06158-2026-08-15` | revise | generated / 1462 / 105515 | yes / 134 / 4 |
| `new-p02949-2026-07-15` | new | generated / 1681 / 74131 | yes / 150 / 4 |
| `new-p04103-2026-07-24` | new | generated / 1401 / 95705 | yes / 106 / 4 |
| `new-p07388-2026-08-29` | new | generated / 1513 / 73165 | yes / 138 / 4 |
| `insufficient-p01741-2026-07-04` | insufficient | generated / 18 / 35336 | no / 0 / 0 |
| `insufficient-p04283-2026-07-25` | insufficient | generated / 1035 / 62922 | yes / 100 / 4 |
| `insufficient-p02862-2026-07-14` | insufficient | generated / 18 / 37805 | no / 0 / 0 |

| case | proposed: reason status / kind / target | rejection cause (mechanical) | evidence ids claimed / existing | calls | candidate: chars / ms | candidate: frontmatter / description chars / headings |
|---|---|---|---|---|---|---|
| `reconfirm-p03700-2026-07-21` | invalid / revise / pivot-to-non-optimization-framework | target skill not in supplied catalogue | 3 / 3 | 1 | 0 / 0 | no / 0 / 0 |
| `reconfirm-p07888-2026-09-05` | invalid / revise / shifting-focus-from-state-to-process-mechanics (supplied name minus its date suffix) | target skill not in supplied catalogue | 4 / 4 | 1 | 0 / 0 | no / 0 / 0 |
| `reconfirm-p06935-2026-08-24` | parsed / reconfirm / — | — | 4 / 4 | 1 | 0 / 0 | no / 0 / 0 |
| `revise-p03375-2026-07-18` | invalid / reconfirm / detecting-abstract-to-operational-constraint-shift (supplied name minus its date suffix) | target skill set on a non-revise kind | 4 / 4 | 1 | 0 / 0 | no / 0 / 0 |
| `revise-p08206-2026-09-08` | parsed / reconfirm / — | — | 4 / 4 | 1 | 0 / 0 | no / 0 / 0 |
| `revise-p06158-2026-08-15` | parsed / reconfirm / — | — | 3 / 3 | 1 | 0 / 0 | no / 0 / 0 |
| `new-p02949-2026-07-15` | parsed / reconfirm / — | — | 3 / 3 | 1 | 0 / 0 | no / 0 / 0 |
| `new-p04103-2026-07-24` | invalid / reconfirm / — | evidence id not in observations | 1 / 0 | 1 | 0 / 0 | no / 0 / 0 |
| `new-p07388-2026-08-29` | invalid / revise / identifying-fidelity-vs-utility-tension (supplied name minus its date suffix) | target skill not in supplied catalogue | 2 / 2 | 1 | 0 / 0 | no / 0 / 0 |
| `insufficient-p01741-2026-07-04` | invalid / insufficient / — | evidence id not in observations | 1 / 0 | 1 | 0 / 0 | no / 0 / 0 |
| `insufficient-p04283-2026-07-25` | invalid / insufficient / — | evidence id not in observations | 1 / 0 | 1 | 0 / 0 | no / 0 / 0 |
| `insufficient-p02862-2026-07-14` | invalid / insufficient / — | evidence id not in observations | 1 / 0 | 1 | 0 / 0 | no / 0 / 0 |

| claimed kind × status (proposed arm) | cases |
|---|---|
| invalid:insufficient | 3 |
| invalid:reconfirm | 2 |
| invalid:revise | 3 |
| parsed:reconfirm | 4 |

- **current arm total**: 12 calls, 904.0 s
- **proposed arm total**: 12 calls, 268.5 s

## Notes on what these columns do and do not record

- **Claimed kind / target** is re-parsed from the raw text, so a rejected reason that named a kind
  still shows it. The proposed arm named a kind in 12/12 cases; 4 of those passed the harness's
  mechanical checks and 8 did not.
- **Rejection cause** is recomputed from the raw text against the harness's mechanical predicates
  (`scripts/insight_revision_compare.py::_parse_reason`), not read off the status.
  `target skill not in supplied catalogue` fired 3 times: twice the named target is a supplied
  skill **with its `-YYYYMMDD` suffix dropped** (marked in the table), once
  (`pivot-to-non-optimization-framework`) it is a name that exists nowhere in the supplied 3.
  `evidence id not in observations` means the claimed id is not one of the case's pattern ids.
- **Evidence-ID check**: `claimed / existing` counts the ids in the raw reason JSON and how many
  exist among that case's observation ids. It is an existence check on the citation, not a check
  that the cited observation supports the stated reason.
- **Body / description correspondence** is recorded as presence facts only (frontmatter present,
  `description` length in characters, number of `#`–`###` headings). No column judges whether the
  description matches the body.
- `generated / 18` in the current arm is the literal string `NOTHING-PROMOTABLE` — the extraction
  prompt's abstain path, not a truncated body.
- **Per-case duration is recorded only where the harness stores it**: the current arm's generation
  call and the proposed arm's candidate call carry `duration_ms`; the proposed arm's reason call
  does not, so its cost appears only in the arm total. In this run no candidate call fired, so the
  proposed arm's 268.5 s is entirely reason calls (mean 22.4 s/case).
- Call counts are the real calls made: current 12 (1/case), proposed 12 (1/case; the second call
  fires only on an accepted `revise` / `new`).

## Smoke run (harness sanity, synthetic cases)

`smoke-20260912.json` — the 4 synthetic cases in `evals/fixtures/insight_revision_cases.json`
(sha256 `fd9fb8bb…`), `--arm both`, same model, 2026-09-12 15:29–15:35 JST.
Current arm 4 calls / 234.5 s; proposed arm 5 calls / 102.8 s. Proposed arm per case:
`reconfirm-check-before-action` invalid, `insufficient-descriptive-observation` parsed
`insufficient`, `revise-narrow-trigger` parsed `revise` with a candidate body,
`new-preserve-uncertainty` invalid. The two-call path fired once, so both branches of the harness
executed at least once before the production run.
