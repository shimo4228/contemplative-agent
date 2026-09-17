# RFC-0027 — third run, name matching relaxed, per-axis facts (2026-09-17)

Facts only. No winner, no threshold, no adoption verdict, and no column scoring an arm's answer
against the selection's diagnostic corner label. The reading belongs to the owner.
Selection method and exclusions: [README.md](README.md). First (defective) run:
[comparison-2026-09-12.md](comparison-2026-09-12.md). Second run:
[comparison-2026-09-12-rerun.md](comparison-2026-09-12-rerun.md).

## Why there is a third run

In the second run 7 of the 12 reason-first rows were rejected by the harness's own string checks
rather than by anything the model judged, so only 1 case reached the second call and the bodies the
comparison exists to look at were almost absent. The 7 rejections were: 4 `revise` targets written
without the catalogue name's `-YYYYMMDD` suffix, 2 `evidence_ids` naming the untrusted wrapper's tag
instead of an observation id, and 1 `reconfirm` that carried a target. The owner classified this as a
defect of the measuring instrument on 2026-09-17 and applied the pre-registration's re-run exception
a **second** time, explicitly.

What changed in the harness (`scripts/insight_revision_compare.py`, `_parse_reason`):

* A `revise` `target_skill` is accepted if it matches a supplied skill name exactly **or** matches one
  after dropping a trailing `-YYYYMMDD`, and is pulled back to the full supplied name. The row records
  `target_as_written` (the model's literal string) and `target_resolved`. If the suffix-stripped form
  matches two or more supplied skills it stays `invalid`, with the reason recorded.
* Two checks are now **recorded, not rejecting**: an `evidence_ids` entry that is not one of the case's
  observation ids (`evidence_id_unknown`), a repeated evidence id (`evidence_ids_duplicated`), and a
  `target_skill` written on a kind other than `revise` (`target_on_non_revise`). The row stays `parsed`
  and carries the finding in `flags`. A target written on a non-`revise` kind is recorded but not
  forwarded to the second call.
* Still `invalid`: not an object, a different key set, a `kind` outside the four, an empty
  `change_reason`, `evidence_ids` that is not a non-empty list of strings, and a `revise` whose target
  cannot be resolved. Every `invalid` row now records an `invalid_reason`.
* The second call still fires only on `parsed` and `kind` ∈ {`revise`, `new`}.

**The prompts were not touched.** All four prompt assets hash the same as the first and second runs, and
the case file is byte-identical. What differs from the second run is this relaxation and the model's own
sampling.

## Run metadata

| | |
|---|---|
| Cases | the same 12, `evals/fixtures/rfc0027_production_cases_20260912.json`, sha256 `445857b1…` (unchanged in git) |
| Arms | `--arm both`, one run, no retry |
| Model | gemma4:e4b via local Ollama, num_ctx 32768 |
| Started / finished | 2026-09-17 19:39:42 → 20:04:36 JST (24.9 min, outside the JST 0/6/12/18 session windows) |
| Prompt sha256 | identical to both earlier runs: system `fa95c889…`, insight_extraction `91502548…`, insight_revision_reason `22566e01…`, insight_revision_generation `0ab81cd5…` |
| Raw output | `comparison-20260917-rerun2.json` |
| Table rendered by | `scripts/rfc0027_render_fact_table.py docs/evidence/rfc-0027/comparison-20260917-rerun2.json` (the 2026-09-17 renderer, which carries two columns the two frozen 09-12 tables do not) |

## Per-case facts

| case | selection corner | current: status / chars / ms | current: frontmatter / description chars / headings |
|---|---|---|---|
| `reconfirm-p03700-2026-07-21` | reconfirm | generated / 226 / 51126 | yes / 135 / 0 |
| `reconfirm-p07888-2026-09-05` | reconfirm | generated / 1665 / 79729 | yes / 122 / 4 |
| `reconfirm-p06935-2026-08-24` | reconfirm | generated / 1346 / 68875 | yes / 143 / 4 |
| `revise-p03375-2026-07-18` | revise | generated / 2023 / 71513 | yes / 145 / 4 |
| `revise-p08206-2026-09-08` | revise | generated / 251 / 61408 | yes / 169 / 0 |
| `revise-p06158-2026-08-15` | revise | generated / 1243 / 65596 | yes / 130 / 4 |
| `new-p02949-2026-07-15` | new | generated / 1156 / 61155 | yes / 89 / 4 |
| `new-p04103-2026-07-24` | new | generated / 1642 / 78987 | yes / 124 / 3 |
| `new-p07388-2026-08-29` | new | generated / 1572 / 67495 | yes / 133 / 4 |
| `insufficient-p01741-2026-07-04` | insufficient | generated / 18 / 45931 | no / 0 / 0 |
| `insufficient-p04283-2026-07-25` | insufficient | generated / 1096 / 52882 | yes / 136 / 4 |
| `insufficient-p02862-2026-07-14` | insufficient | generated / 18 / 29362 | no / 0 / 0 |

| case | proposed: reason status / kind / target | target as written | flags | rejection cause (mechanical) | evidence ids claimed / existing | calls | candidate: chars / ms | candidate: frontmatter / description chars / headings |
|---|---|---|---|---|---|---|---|---|
| `reconfirm-p03700-2026-07-21` | parsed / reconfirm / — | — | — | — | 3 / 3 | 1 | 0 / 0 | no / 0 / 0 |
| `reconfirm-p07888-2026-09-05` | parsed / revise / shifting-focus-from-state-to-process-mechanics-20260815 | shifting-focus-from-state-to-process-mechanics | — | — | 4 / 4 | 2 | 2402 / 100752 | no / 0 / 4 |
| `reconfirm-p06935-2026-08-24` | parsed / reconfirm / — | — | — | — | 4 / 4 | 1 | 0 / 0 | no / 0 / 0 |
| `revise-p03375-2026-07-18` | parsed / reconfirm / — | — | — | — | 4 / 4 | 1 | 0 / 0 | no / 0 / 0 |
| `revise-p08206-2026-09-08` | parsed / reconfirm / — | — | — | — | 4 / 4 | 1 | 0 / 0 | no / 0 / 0 |
| `revise-p06158-2026-08-15` | parsed / revise / shifting-focus-from-state-to-process-mechanics-20260815 | shifting-focus-from-state-to-process-mechanics | — | — | 3 / 3 | 2 | 1898 / 78555 | no / 0 / 4 |
| `new-p02949-2026-07-15` | parsed / revise / detecting-foundational-structural-compromise-20260808 | detecting-foundational-structural-compromise | — | — | 2 / 2 | 2 | 3731 / 118387 | no / 0 / 5 |
| `new-p04103-2026-07-24` | parsed / revise / fluid-dynamic-resonance-regulation-and-consensus-m-20260815 | fluid-dynamic-resonance-regulation-and-consensus-m | — | — | 2 / 2 | 2 | 7374 / 141827 | no / 0 / 4 |
| `new-p07388-2026-08-29` | parsed / revise / identifying-fidelity-vs-utility-tension-20260808 | identifying-fidelity-vs-utility-tension | — | — | 1 / 1 | 2 | 2767 / 72157 | no / 0 / 4 |
| `insufficient-p01741-2026-07-04` | parsed / insufficient / — | — | — | — | 1 / 1 | 1 | 0 / 0 | no / 0 / 0 |
| `insufficient-p04283-2026-07-25` | parsed / insufficient / — | — | evidence_id_unknown | — | 1 / 0 | 1 | 0 / 0 | no / 0 / 0 |
| `insufficient-p02862-2026-07-14` | parsed / insufficient / — | — | evidence_id_unknown | — | 1 / 0 | 1 | 0 / 0 | no / 0 / 0 |

| claimed kind × status (proposed arm) | cases |
|---|---|
| parsed:insufficient | 3 |
| parsed:reconfirm | 4 |
| parsed:revise | 5 |

- **current arm total**: 12 calls, 734.1 s
- **proposed arm total**: 17 calls, 749.0 s

## Targets that were pulled back to a supplied name

Five `revise` rows named a target; **all five** wrote the catalogue name without its date suffix, and
each resolved to exactly one supplied skill. No ambiguous match occurred, and no row named a skill
absent from its case's three.

| case | target as written | resolved to |
|---|---|---|
| `reconfirm-p07888-2026-09-05` | `shifting-focus-from-state-to-process-mechanics` | `shifting-focus-from-state-to-process-mechanics-20260815` |
| `revise-p06158-2026-08-15` | `shifting-focus-from-state-to-process-mechanics` | `shifting-focus-from-state-to-process-mechanics-20260815` |
| `new-p02949-2026-07-15` | `detecting-foundational-structural-compromise` | `detecting-foundational-structural-compromise-20260808` |
| `new-p04103-2026-07-24` | `fluid-dynamic-resonance-regulation-and-consensus-m` | `fluid-dynamic-resonance-regulation-and-consensus-m-20260815` |
| `new-p07388-2026-08-29` | `identifying-fidelity-vs-utility-tension` | `identifying-fidelity-vs-utility-tension-20260808` |

## Flags recorded

| case | flag | what was written |
|---|---|---|
| `insufficient-p04283-2026-07-25` | `evidence_id_unknown` | `untrusted_content_369a5d711fad3aa5` |
| `insufficient-p02862-2026-07-14` | `evidence_id_unknown` | `untrusted_content_692771618dc6ff6c` |

Both are single-observation cases, and both name the nonce tag of the untrusted wrapper that encloses
the observation block rather than the observation id printed inside it. No `evidence_ids_duplicated`
and no `target_on_non_revise` flag was raised in this run.

## Calls and time

| | current arm | proposed arm |
|---|---|---|
| Calls | 12 | 17 |
| Total | 734.1 s | 749.0 s |

The proposed arm's 17 calls are 12 reason calls plus 5 second calls. The 5 second calls account for
511.7 s, so the 12 reason calls account for 237.3 s (mean 19.8 s per case).

## Notes on what these columns do and do not record

- The columns mean what they mean in the two earlier documents, plus `target as written` and `flags`.
  `—` in the flags column means no flag was recorded; `n/a` (which appears only when the renderer is
  pointed at a pre-2026-09-17 result file) means the run predates flags entirely.
- **No row was rejected in this run**: 12 `parsed`, 0 `invalid`, 0 `parse_error`, 0 `llm_none`. The
  claimed kinds are 5 `revise`, 4 `reconfirm`, 3 `insufficient`, and 0 `new`.
- **The second call fired 5 times** (the 5 `revise` rows), against 1 time in the second run.
- Every candidate body reports `no` for frontmatter, because the check anchors at the start of the
  text: four of the five open with a ```` ```yaml ```` fence before the `name` / `description` block,
  and `new-p02949-2026-07-15` opens with a `### …` heading. Their `description` therefore counts as 0
  characters, as it did for the second run's single body.
- Two current-arm outputs (`insufficient-p01741-2026-07-04`, `insufficient-p02862-2026-07-14`, 18 chars
  each) are the literal `NOTHING-PROMOTABLE` abstain string. Two more
  (`reconfirm-p03700-2026-07-21` at 226, `revise-p08206-2026-09-08` at 251) are frontmatter-only, with
  no body headings.
- The two frozen 09-12 tables were rendered by the pre-2026-09-17 renderer and are deliberately not
  re-rendered: they are evidence of what those runs recorded under the predicates in force then. The
  renderer still reads both of their result files, and reports their rejection causes under those older
  predicates.
- Per-case durations are recorded where the harness stores them; the reason call's duration is only in
  the arm total.
