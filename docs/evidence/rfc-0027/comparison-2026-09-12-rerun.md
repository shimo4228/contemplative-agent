# RFC-0027 — re-run after the harness repair, per-axis facts (2026-09-12)

Facts only. No winner, no threshold, no adoption verdict, and no column scoring an arm's answer
against the selection's diagnostic corner label. The reading belongs to the owner.
Selection method and exclusions: [README.md](README.md). First (defective) run:
[comparison-2026-09-12.md](comparison-2026-09-12.md).

## Why there is a second run

The first run passed `case_id` into the extraction prompt's `{subcategory}` slot, so the current
arm read the selection's corner label on all 12 cases and the reason-first arm never did. The owner
classified that as a harness bug on 2026-09-12 and applied the pre-registration's exception clause
(**one** re-run after repair). The repair: `scripts/insight_revision_compare.py` now fills
`{subcategory}` from an optional per-case `subcategory` field, defaulting to the constant
`observation`, and refuses a case whose `subcategory` contains its `case_id`.
`tests/test_insight_revision_compare.py::test_neither_arm_sees_the_case_id_or_its_selection_label`
pins that neither arm's prompts contain the case id, the corner label, or the date.

**The case file is byte-identical to the first run** (sha256
`445857b131bd94ee0fccfef13d9f7b4811c273b339092140ae22e13d52bc1bf0`, unchanged in git), and the four
prompt assets hash the same as the first run. What differs between the two runs is the repair and
the model's own sampling.

## Run metadata

| | |
|---|---|
| Cases | the same 12, `evals/fixtures/rfc0027_production_cases_20260912.json`, sha256 `445857b1…` |
| Arms | `--arm both`, one run, no retry |
| Model | gemma4:e4b via local Ollama, num_ctx 32768 |
| Started / finished | 2026-09-12 16:12:13 → 16:32:30 JST (20.3 min, outside the 18:00 session window) |
| Prompt sha256 | identical to the first run: system `fa95c889…`, insight_extraction `915025480842…`, insight_revision_reason `22566e01…`, insight_revision_generation `0ab81cd5…` |
| Raw output | `comparison-20260912-rerun.json` |
| Table rendered by | `scripts/rfc0027_render_fact_table.py docs/evidence/rfc-0027/comparison-20260912-rerun.json` |

## Per-case facts

| case | selection corner | current: status / chars / ms | current: frontmatter / description chars / headings |
|---|---|---|---|
| `reconfirm-p03700-2026-07-21` | reconfirm | generated / 201 / 100292 | yes / 117 / 0 |
| `reconfirm-p07888-2026-09-05` | reconfirm | generated / 1611 / 105018 | yes / 136 / 4 |
| `reconfirm-p06935-2026-08-24` | reconfirm | generated / 1485 / 81098 | yes / 104 / 4 |
| `revise-p03375-2026-07-18` | revise | generated / 1457 / 61706 | yes / 124 / 4 |
| `revise-p08206-2026-09-08` | revise | generated / 2234 / 89604 | yes / 166 / 4 |
| `revise-p06158-2026-08-15` | revise | generated / 1606 / 73596 | yes / 139 / 4 |
| `new-p02949-2026-07-15` | new | generated / 1384 / 69580 | yes / 105 / 4 |
| `new-p04103-2026-07-24` | new | generated / 1442 / 72589 | yes / 104 / 4 |
| `new-p07388-2026-08-29` | new | generated / 1496 / 83740 | yes / 105 / 4 |
| `insufficient-p01741-2026-07-04` | insufficient | generated / 18 / 28838 | no / 0 / 0 |
| `insufficient-p04283-2026-07-25` | insufficient | generated / 199 / 43586 | yes / 109 / 0 |
| `insufficient-p02862-2026-07-14` | insufficient | generated / 18 / 25797 | no / 0 / 0 |

| case | proposed: reason status / kind / target | rejection cause (mechanical) | evidence ids claimed / existing | calls | candidate: chars / ms | candidate: frontmatter / description chars / headings |
|---|---|---|---|---|---|---|
| `reconfirm-p03700-2026-07-21` | invalid / reconfirm / pivot-to-non-optimization-framework | target skill set on a non-revise kind | 3 / 3 | 1 | 0 / 0 | no / 0 / 0 |
| `reconfirm-p07888-2026-09-05` | invalid / revise / shifting-focus-from-state-to-process-mechanics (supplied name minus its date suffix) | target skill not in supplied catalogue | 3 / 3 | 1 | 0 / 0 | no / 0 / 0 |
| `reconfirm-p06935-2026-08-24` | parsed / reconfirm / — | — | 4 / 4 | 1 | 0 / 0 | no / 0 / 0 |
| `revise-p03375-2026-07-18` | invalid / revise / detecting-abstract-to-operational-constraint-shift (supplied name minus its date suffix) | target skill not in supplied catalogue | 2 / 2 | 1 | 0 / 0 | no / 0 / 0 |
| `revise-p08206-2026-09-08` | parsed / revise / structure-authority-tracing-20260709 | — | 2 / 2 | 2 | 2285 / 117911 | no / 0 / 4 |
| `revise-p06158-2026-08-15` | parsed / reconfirm / — | — | 3 / 3 | 1 | 0 / 0 | no / 0 / 0 |
| `new-p02949-2026-07-15` | invalid / revise / detecting-foundational-structural-compromise (supplied name minus its date suffix) | target skill not in supplied catalogue | 2 / 2 | 1 | 0 / 0 | no / 0 / 0 |
| `new-p04103-2026-07-24` | invalid / revise / fluid-dynamic-resonance-regulation-and-consensus-m (supplied name minus its date suffix) | target skill not in supplied catalogue | 2 / 2 | 1 | 0 / 0 | no / 0 / 0 |
| `new-p07388-2026-08-29` | parsed / reconfirm / — | — | 3 / 3 | 1 | 0 / 0 | no / 0 / 0 |
| `insufficient-p01741-2026-07-04` | parsed / insufficient / — | — | 1 / 1 | 1 | 0 / 0 | no / 0 / 0 |
| `insufficient-p04283-2026-07-25` | invalid / insufficient / — | evidence id not in observations | 1 / 0 | 1 | 0 / 0 | no / 0 / 0 |
| `insufficient-p02862-2026-07-14` | invalid / insufficient / — | evidence id not in observations | 1 / 0 | 1 | 0 / 0 | no / 0 / 0 |

| claimed kind × status (proposed arm) | cases |
|---|---|
| invalid:insufficient | 2 |
| invalid:reconfirm | 1 |
| invalid:revise | 4 |
| parsed:insufficient | 1 |
| parsed:reconfirm | 3 |
| parsed:revise | 1 |

- **current arm total**: 12 calls, 835.4 s
- **proposed arm total**: 13 calls, 378.9 s

## Notes on what these columns do and do not record

- The columns mean exactly what they mean in the first run's document; only the result file differs.
- **The reason-first arm's second call fired once** (`revise-p08206-2026-09-08`, accepted `revise`
  targeting `structure-authority-tracing-20260709`, which is one of that case's 3 supplied skills).
  That candidate body opens with a ````yaml``` fence, so the frontmatter check — which anchors at the
  start of the text — reports `no` for it; the `name` / `description` block is present inside the
  fence. Its `description` therefore counts as 0 characters in the table.
- Two current-arm outputs (`reconfirm-p03700-2026-07-21` at 201 chars, `insufficient-p04283-2026-07-25`
  at 199) are frontmatter-only: a `name` and `description` with no body headings. Two more are the
  literal `NOTHING-PROMOTABLE` abstain string at 18 chars.
- `target skill not in supplied catalogue` fired 4 times here, and in **all 4** the named target is
  a supplied skill with its `-YYYYMMDD` suffix dropped (marked in the table) — no invented name this
  time. One further rejection is a `reconfirm` that carried a target, and two are evidence ids that
  do not exist among the case's observations.
- Per-case durations are recorded where the harness stores them; the reason call's duration is still
  only in the arm total. With one candidate call at 117.9 s, the 12 reason calls account for
  261.0 s of the proposed arm's 378.9 s (mean 21.8 s/case).
