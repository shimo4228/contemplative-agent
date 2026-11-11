# Source-pattern age of selected skills — reading 2026-11-11 (RFC-0071 P3-01.3)

reanalysis: private-rows — every input is a private log or private state of the
production `MOLTBOOK_HOME`; the public data repo cannot recompute these numbers.

Script: [`scripts/source_pattern_age.py`](../../../scripts/source_pattern_age.py)
(read-only, stdlib, manual run only). The tracing rule, the reason codes, the
per-skill aggregation (median creation time of the adoption row's source
patterns) and the two comparison lines (catalog, corpus) are defined in its
module docstring. This file records the readings; it states no verdict. The
verdict sentence of this axis is written by the owner after the second reading
(ADR-0124 Q2 row, roadmap P3-01.3 consumption plan (b)).

## Commands

Run 2026-11-11 around 08:51 UTC on the production machine, from the repository root:

```sh
python3 scripts/source_pattern_age.py
python3 scripts/source_pattern_age.py --start 2026-10-15 --end 2026-11-11
python3 scripts/source_pattern_age.py --start 2026-09-09 --end 2026-10-31
```

The first is the whole span of the skill-selection log, the second the last
four weeks (2026-11-11 is a partial day, records up to 04:00 UTC), the third
the calendar dates of the earlier one-off reading
[`docs/evidence/adr-0124/source-pattern-age-20261031.md`](../adr-0124/source-pattern-age-20261031.md),
kept so the two can be set side by side. Its record set is not the earlier
one's: 4,478 judged records here against 4,374 there (2026-09-09T15:00Z ..
2026-10-31T03:59Z). Of the 104 extra, 37 are judged rows without a `kind` field
before 2026-09-09T15:00Z (the records row of the table below), and 67 are rows
written on 2026-10-31 at or after 04:00Z, after the earlier reading was taken.
`--start` / `--end` take dates only, so the run cannot cut at the earlier
reading's hour boundaries.

## Input range

| input | range |
|---|---|
| `logs/skill-selection-*.jsonl` | 125 files (2026-07-10 .. 2026-11-11), 22,197 lines; judged records 10,798, fail-open 6,631 |
| `logs/audit.jsonl` | 1,501 lines; `command: insight` 1,286, of which 1,183 carry `source_ids`; 82 skill files have an approved insight row |
| `knowledge.json` | 15,222 patterns |
| `name:` lines | 6,172 files: `skills/` 53, `skills/.archive/` 4, `snapshots/*/skills/` (117 snapshots); 63 distinct names |

## Untraced, by reason code

| window | population | rows | adopted_without_insight_row | adoption_row_without_source_ids | other codes |
|---|---|---|---|---|---|
| all | selected | 64,623 | 617 | 2,281 | 0 |
| all | catalog | 493,956 | 17,514 | 32,394 | 0 |
| 2026-10-15 .. 11-11 | selected | 18,166 | 8 | 120 | 0 |
| 2026-10-15 .. 11-11 | catalog | 140,503 | 2,651 | 7,953 | 0 |
| 2026-09-09 .. 10-31 | selected | 29,750 | 16 | 244 | 0 |
| 2026-09-09 .. 10-31 | catalog | 238,920 | 4,478 | 13,434 | 0 |

Among the selected names, `adopted_without_insight_row` is four names whose file was adopted by a
`skill-stocktake` merge (no insight lineage), and `adoption_row_without_source_ids`
is three names adopted in 2026-04 / 05, before `source_ids` was written. No source
id was absent from `knowledge.json` in any window.

## Method differences from the 2026-10-31 one-off reading

| | 2026-10-31 (throwaway script) | this reading |
|---|---|---|
| records | `kind: "selection"` and `enforced: true` (starts 2026-09-09) | `verdict: judged`, with or without `kind` / `enforced` (starts 2026-07-10) |
| name -> file | live `skills/` only | live, `.archive/` and `snapshots/` |
| one value per | (selection, skill, source pattern) | (selection, skill) — median of the skill's source patterns |
| unit | days | weeks |
| comparison | whole corpus | catalog at each call, and whole corpus |

## Output — whole span

### Source-pattern age of selected skills (open .. open)

#### Inputs

- skill-selection log: 125 files, 22197 lines; judged records in window: 10798 (enforced true 9475 / false 24 / absent 1299); fail-open records in window (select nothing): 6631
- judged records span 2026-07-10 .. 2026-11-11 (UTC)
- audit.jsonl: 1501 lines; skill files with an approved insight row: 82
- knowledge.json: 15222 patterns; skill files read for `name:`: 6172 (63 distinct names)

#### Traced

| population | rows | traced | untraced |
|---|---|---|---|
| selected | 64623 | 61725/64623 = 95.5% [95.3-95.7%] | 2898 |
| catalog (baseline) | 493956 | 444048/493956 = 89.9% [89.8-90.0%] | 49908 |

Untraced by reason code:

| reason | selected | catalog (baseline) |
|---|---|---|
| name_unmapped | 0 | 0 |
| name_ambiguous | 0 | 0 |
| no_adoption_row | 0 | 0 |
| adopted_without_insight_row | 617 | 17514 |
| adoption_after_selection | 0 | 0 |
| adoption_row_without_source_ids | 2281 | 32394 |
| source_pattern_missing | 0 | 0 |
| pattern_after_selection | 0 | 0 |

Source ids absent from knowledge.json on traced or untraced rows (summed per row): selected 0 / catalog 0

#### Age in weeks (selection time - median creation of the source patterns)

- selected: min 0.0 / Q1 3.6 / median 7.5 / Q3 11.7 / max 18.5
- catalog (baseline): min 0.0 / Q1 3.9 / median 7.7 / Q3 11.6 / max 18.5
- corpus at 2026-11-11T04:00+00:00, 15222 patterns: min 0.1 / Q1 4.1 / median 10.1 / Q3 15.9 / max 32.7

| age (weeks, floor) | selected | catalog (baseline) | corpus |
|---|---|---|---|
| 0 | 2517 | 16548 | 1093 |
| 1 | 5285 | 32740 | 1226 |
| 2 | 5088 | 32682 | 646 |
| 3 | 4507 | 31313 | 839 |
| 4 | 4344 | 30716 | 760 |
| 5 | 3994 | 30377 | 500 |
| 6 | 3551 | 28801 | 684 |
| 7 | 3197 | 27169 | 649 |
| 8 | 3290 | 26847 | 602 |
| 9 | 3571 | 28027 | 586 |
| 10 | 4190 | 30437 | 581 |
| 11 | 4218 | 30864 | 587 |
| 12 | 3702 | 24806 | 639 |
| 13 | 3109 | 22853 | 605 |
| 14 | 2599 | 18559 | 634 |
| 15 | 1764 | 12076 | 806 |
| 16 | 1424 | 9184 | 889 |
| 17 | 1190 | 8530 | 803 |
| 18 | 185 | 1519 | 660 |
| 19 | 0 | 0 | 495 |
| 20 | 0 | 0 | 116 |
| 21 | 0 | 0 | 36 |
| 22 | 0 | 0 | 45 |
| 23 | 0 | 0 | 40 |
| 24 | 0 | 0 | 71 |
| 25 | 0 | 0 | 53 |
| 26 | 0 | 0 | 68 |
| 27 | 0 | 0 | 74 |
| 28 | 0 | 0 | 75 |
| 29 | 0 | 0 | 71 |
| 30 | 0 | 0 | 48 |
| 31 | 0 | 0 | 25 |
| 32 | 0 | 0 | 216 |

#### Per skill (selected in window)

| skill name | selections | catalog rows | source week (median) | within-skill spread (weeks) | median age at selection | untraced reason |
|---|---|---|---|---|---|---|
| cross-reference-foundational-claims | 6282 | 10798 | 2026-W28 | 0.3 | 8.6 | - |
| internal-process-audit | 4982 | 9388 | 2026-W29 | 0.6 | 9.8 | - |
| shifting-focus-from-state-to-process-mechanics | 4900 | 7463 | 2026-W33 | 0.6 | 7.0 | - |
| dissecting-asserted-agency-into-mechanisms | 4799 | 8702 | 2026-W31 | 0.6 | 8.5 | - |
| structural-constraint-mapping-scm | 4318 | 7463 | 2026-W33 | 0.9 | 7.9 | - |
| detecting-abstract-to-operational-constraint-shift | 3359 | 7440 | 2026-W27 | 0.6 | 11.5 | - |
| detecting-foundational-structural-compromise | 3270 | 8093 | 2026-W32 | 0.6 | 10.1 | - |
| detect-abstract-operational-constraint-shifts | 2520 | 3358 | 2026-W27 | 0.6 | 3.0 | - |
| extracting-simulation-boundaries | 2352 | 10798 | 2026-W27 | 0.6 | 3.0 | - |
| trace-structural-authority | 2152 | 10798 | 2026-W28 | 0.4 | 10.2 | - |
| suspend-interpretation-upon-premise-doubt | 1819 | 8702 | 2026-W31 | 0.9 | 10.5 | - |
| differentiating-artifacts-from-observation | 1671 | 7463 | 2026-W32 | 0.9 | 6.6 | - |
| pinpointing-systemic-boundary-conditions | 1543 | 8093 | 2026-W32 | 0.3 | 5.8 | - |
| scope-failure-diagnosis | 1509 | 10798 | 2026-W28 | 0.3 | 6.0 | - |
| fluid-contextual-anchoring-loop | 1330 | 10798 | - | - | - | adoption_row_without_source_ids 1330 |
| boundary-assumption-verification | 1304 | 7440 | 2026-W30 | 0.4 | 7.6 | - |
| disaggregate-premise-from-effect | 1255 | 6859 | 2026-W34 | 0.6 | 7.0 | - |
| deconstruct-confidence-proxies | 1242 | 10798 | 2026-W28 | 0.6 | 3.3 | - |
| validate-provenance-chain | 1170 | 10798 | 2026-W28 | 0.0 | 14.6 | - |
| scope-boundary-mapping | 961 | 8093 | 2026-W32 | 0.7 | 6.5 | - |
| mapping-systemic-dependency-failures | 935 | 8093 | 2026-W31 | 0.4 | 7.7 | - |
| articulate-epistemic-boundaries | 872 | 10798 | 2026-W28 | 0.7 | 5.8 | - |
| dynamic-sematic-decoupling-and-contextual-anchoring | 851 | 10798 | - | - | - | adoption_row_without_source_ids 851 |
| detecting-rhetorical-discourse-closures | 850 | 6859 | 2026-W33 | 0.0 | 6.7 | - |
| pivot-constraint-analysis | 829 | 10798 | 2026-W28 | 0.3 | 4.0 | - |
| analyzing-systemic-governance-loops | 822 | 6859 | 2026-W33 | 0.4 | 4.8 | - |
| identify-systemic-boundary-stressors | 746 | 8702 | 2026-W30 | 0.4 | 4.4 | - |
| analyzing-loci-of-identity-definition | 659 | 7440 | 2026-W28 | 0.7 | 13.1 | - |
| identifying-structural-tensions-via-system-metaphors | 562 | 8702 | 2026-W31 | 0.6 | 10.1 | - |
| detecting-abstraction-decay-in-context | 515 | 7463 | 2026-W32 | 0.7 | 8.7 | - |
| identifying-fidelity-vs-utility-tension | 337 | 8093 | 2026-W32 | 0.0 | 6.9 | - |
| identify-structural-pivot | 329 | 8093 | 2026-W31 | 0.4 | 9.1 | - |
| shift-identity-definition-from-record-to-vector | 326 | 3358 | 2026-W28 | 0.7 | 2.8 | - |
| recognizing-boundary-declarations-in-content-flow | 322 | 8093 | 2026-W32 | 0.6 | 4.4 | - |
| analyze-decision-incentives | 311 | 8702 | 2026-W31 | 0.4 | 1.4 | - |
| diagnosing-mechanisms-of-omission | 307 | 6859 | 2026-W34 | 0.4 | 6.2 | - |
| fluid-consensus-oscillation-non-dual-friction-transmutation | 306 | 3358 | - | - | - | adopted_without_insight_row 306 |
| cross-reference-metric-constraints-analysis | 235 | 6859 | 2026-W34 | 0.9 | 4.8 | - |
| modeling-null-states | 210 | 8702 | 2026-W31 | 0.6 | 6.8 | - |
| deconstructing-consensus-validity-through-shared-d | 193 | 8093 | 2026-W32 | 0.6 | 2.8 | - |
| distinguish-persistence-from-validity | 187 | 6859 | 2026-W33 | 0.7 | 8.5 | - |
| fluid-administrative-temporal-social-reformation-loop | 167 | 3358 | - | - | - | adopted_without_insight_row 167 |
| map-abstract-theory-to-structural-constraints | 167 | 10798 | 2026-W28 | 0.3 | 4.9 | - |
| fluid-dynamic-resonance-regulation-20260530 | 122 | 3358 | - | - | - | adopted_without_insight_row 122 |
| force-actionable-accountability-pivot | 113 | 9388 | 2026-W30 | 0.3 | 2.2 | - |
| detect-and-align-operational-framework | 112 | 8702 | 2026-W31 | 0.3 | 1.9 | - |
| fluid-temporal-friction-to-insight-loop | 100 | 10798 | - | - | - | adoption_row_without_source_ids 100 |
| formalize-implicit-operational-assumptions | 78 | 1262 | 2026-W30 | 0.4 | 1.4 | - |
| testing-procedural-guardrails-with-counterfactuals | 67 | 6859 | 2026-W34 | 0.3 | 7.2 | - |
| translating-temporal-gaps-into-structural-utility | 67 | 10798 | 2026-W27 | 0.4 | 5.9 | - |
| assess-contextual-functional-dependence | 46 | 4108 | 2026-W31 | 0.4 | 0.9 | - |
| identifying-foundational-model-failures | 39 | 6859 | 2026-W34 | 0.9 | 3.9 | - |
| shifting-focus-to-systemic-degradation-gradient | 23 | 6859 | 2026-W34 | 0.1 | 7.8 | - |
| fluid-dynamic-resonance-regulation-and-consensus-m | 22 | 7440 | - | - | - | adopted_without_insight_row 22 |
| gradient-modeling | 17 | 7463 | 2026-W33 | 0.7 | 8.3 | - |
| analogy-mapping-relationships | 15 | 8702 | 2026-W31 | 0.4 | 7.2 | - |
| pivot-to-non-optimization-framework | 15 | 9388 | 2026-W30 | 0.0 | 2.6 | - |
| anchor-analysis-using-embodied-signals | 7 | 10798 | 2026-W28 | 0.1 | 3.4 | - |
| define-bounded-autonomy-governance | 3 | 8702 | 2026-W31 | 0.7 | 0.8 | - |
| affirm-cognitive-possibility | 1 | 9388 | 2026-W30 | 0.3 | 0.6 | - |

## Output — last four weeks (2026-10-15 .. 2026-11-11)

### Source-pattern age of selected skills (2026-10-15 .. 2026-11-11)

#### Inputs

- skill-selection log: 125 files, 22197 lines; judged records in window: 2651 (enforced true 2651 / false 0 / absent 0); fail-open records in window (select nothing): 0
- judged records span 2026-10-15 .. 2026-11-11 (UTC)
- audit.jsonl: 1501 lines; skill files with an approved insight row: 82
- knowledge.json: 15222 patterns; skill files read for `name:`: 6172 (63 distinct names)

#### Traced

| population | rows | traced | untraced |
|---|---|---|---|
| selected | 18166 | 18038/18166 = 99.3% [99.2-99.4%] | 128 |
| catalog (baseline) | 140503 | 129899/140503 = 92.5% [92.3-92.6%] | 10604 |

Untraced by reason code:

| reason | selected | catalog (baseline) |
|---|---|---|
| name_unmapped | 0 | 0 |
| name_ambiguous | 0 | 0 |
| no_adoption_row | 0 | 0 |
| adopted_without_insight_row | 8 | 2651 |
| adoption_after_selection | 0 | 0 |
| adoption_row_without_source_ids | 120 | 7953 |
| source_pattern_missing | 0 | 0 |
| pattern_after_selection | 0 | 0 |

Source ids absent from knowledge.json on traced or untraced rows (summed per row): selected 0 / catalog 0

#### Age in weeks (selection time - median creation of the source patterns)

- selected: min 7.9 / Q1 11.3 / median 12.9 / Q3 15.0 / max 18.5
- catalog (baseline): min 7.9 / Q1 11.3 / median 12.9 / Q3 14.9 / max 18.5
- corpus at 2026-11-11T04:00+00:00, 15222 patterns: min 0.1 / Q1 4.1 / median 10.1 / Q3 15.9 / max 32.7

| age (weeks, floor) | selected | catalog (baseline) | corpus |
|---|---|---|---|
| 0 | 0 | 0 | 1093 |
| 1 | 0 | 0 | 1226 |
| 2 | 0 | 0 | 646 |
| 3 | 0 | 0 | 839 |
| 4 | 0 | 0 | 760 |
| 5 | 0 | 0 | 500 |
| 6 | 0 | 0 | 684 |
| 7 | 9 | 142 | 649 |
| 8 | 247 | 4443 | 602 |
| 9 | 1186 | 8619 | 586 |
| 10 | 2147 | 14096 | 581 |
| 11 | 2773 | 20520 | 587 |
| 12 | 2873 | 19149 | 639 |
| 13 | 1998 | 15310 | 605 |
| 14 | 2242 | 16311 | 634 |
| 15 | 1764 | 12076 | 806 |
| 16 | 1424 | 9184 | 889 |
| 17 | 1190 | 8530 | 803 |
| 18 | 185 | 1519 | 660 |
| 19 | 0 | 0 | 495 |
| 20 | 0 | 0 | 116 |
| 21 | 0 | 0 | 36 |
| 22 | 0 | 0 | 45 |
| 23 | 0 | 0 | 40 |
| 24 | 0 | 0 | 71 |
| 25 | 0 | 0 | 53 |
| 26 | 0 | 0 | 68 |
| 27 | 0 | 0 | 74 |
| 28 | 0 | 0 | 75 |
| 29 | 0 | 0 | 71 |
| 30 | 0 | 0 | 48 |
| 31 | 0 | 0 | 25 |
| 32 | 0 | 0 | 216 |

#### Per skill (selected in window)

| skill name | selections | catalog rows | source week (median) | within-skill spread (weeks) | median age at selection | untraced reason |
|---|---|---|---|---|---|---|
| structural-constraint-mapping-scm | 1679 | 2651 | 2026-W33 | 0.9 | 11.1 | - |
| detecting-foundational-structural-compromise | 1657 | 2651 | 2026-W32 | 0.6 | 11.9 | - |
| shifting-focus-from-state-to-process-mechanics | 1643 | 2651 | 2026-W33 | 0.6 | 11.0 | - |
| internal-process-audit | 1637 | 2651 | 2026-W29 | 0.6 | 14.4 | - |
| cross-reference-foundational-claims | 1622 | 2651 | 2026-W28 | 0.3 | 16.1 | - |
| dissecting-asserted-agency-into-mechanisms | 1524 | 2651 | 2026-W31 | 0.6 | 13.1 | - |
| detecting-abstract-to-operational-constraint-shift | 881 | 2651 | 2026-W27 | 0.6 | 16.3 | - |
| suspend-interpretation-upon-premise-doubt | 802 | 2651 | 2026-W31 | 0.9 | 12.9 | - |
| trace-structural-authority | 677 | 2651 | 2026-W28 | 0.4 | 15.9 | - |
| validate-provenance-chain | 641 | 2651 | 2026-W28 | 0.0 | 16.2 | - |
| disaggregate-premise-from-effect | 547 | 2651 | 2026-W34 | 0.6 | 9.9 | - |
| differentiating-artifacts-from-observation | 521 | 2651 | 2026-W32 | 0.9 | 11.4 | - |
| boundary-assumption-verification | 425 | 2651 | 2026-W30 | 0.4 | 13.4 | - |
| pinpointing-systemic-boundary-conditions | 374 | 2651 | 2026-W32 | 0.3 | 12.1 | - |
| scope-boundary-mapping | 298 | 2651 | 2026-W32 | 0.7 | 12.3 | - |
| mapping-systemic-dependency-failures | 272 | 2651 | 2026-W31 | 0.4 | 12.5 | - |
| analyzing-loci-of-identity-definition | 263 | 2651 | 2026-W28 | 0.7 | 15.9 | - |
| detecting-rhetorical-discourse-closures | 255 | 2651 | 2026-W33 | 0.0 | 11.0 | - |
| extracting-simulation-boundaries | 253 | 2651 | 2026-W27 | 0.6 | 16.5 | - |
| analyzing-systemic-governance-loops | 252 | 2651 | 2026-W33 | 0.4 | 10.0 | - |
| identifying-structural-tensions-via-system-metaphors | 223 | 2651 | 2026-W31 | 0.6 | 12.7 | - |
| detecting-abstraction-decay-in-context | 217 | 2651 | 2026-W32 | 0.7 | 11.0 | - |
| scope-failure-diagnosis | 200 | 2651 | 2026-W28 | 0.3 | 16.2 | - |
| identify-systemic-boundary-stressors | 147 | 2651 | 2026-W30 | 0.4 | 13.3 | - |
| identify-structural-pivot | 137 | 2651 | 2026-W31 | 0.4 | 12.4 | - |
| articulate-epistemic-boundaries | 131 | 2651 | 2026-W28 | 0.7 | 16.2 | - |
| diagnosing-mechanisms-of-omission | 108 | 2651 | 2026-W34 | 0.4 | 9.9 | - |
| identifying-fidelity-vs-utility-tension | 106 | 2651 | 2026-W32 | 0.0 | 11.7 | - |
| fluid-contextual-anchoring-loop | 100 | 2651 | - | - | - | adoption_row_without_source_ids 100 |
| recognizing-boundary-declarations-in-content-flow | 99 | 2651 | 2026-W32 | 0.6 | 11.3 | - |
| distinguish-persistence-from-validity | 94 | 2651 | 2026-W33 | 0.7 | 10.4 | - |
| pivot-constraint-analysis | 92 | 2651 | 2026-W28 | 0.3 | 16.1 | - |
| deconstruct-confidence-proxies | 64 | 2651 | 2026-W28 | 0.6 | 17.5 | - |
| modeling-null-states | 51 | 2651 | 2026-W31 | 0.6 | 12.8 | - |
| cross-reference-metric-constraints-analysis | 48 | 2651 | 2026-W34 | 0.9 | 10.3 | - |
| testing-procedural-guardrails-with-counterfactuals | 31 | 2651 | 2026-W34 | 0.3 | 9.9 | - |
| translating-temporal-gaps-into-structural-utility | 16 | 2651 | 2026-W27 | 0.4 | 16.4 | - |
| dynamic-sematic-decoupling-and-contextual-anchoring | 12 | 2651 | - | - | - | adoption_row_without_source_ids 12 |
| shifting-focus-to-systemic-degradation-gradient | 11 | 2651 | 2026-W34 | 0.1 | 10.4 | - |
| identifying-foundational-model-failures | 9 | 2651 | 2026-W34 | 0.9 | 10.1 | - |
| analyze-decision-incentives | 8 | 2651 | 2026-W31 | 0.4 | 12.5 | - |
| fluid-dynamic-resonance-regulation-and-consensus-m | 8 | 2651 | - | - | - | adopted_without_insight_row 8 |
| fluid-temporal-friction-to-insight-loop | 8 | 2651 | - | - | - | adoption_row_without_source_ids 8 |
| gradient-modeling | 6 | 2651 | 2026-W33 | 0.7 | 11.1 | - |
| deconstructing-consensus-validity-through-shared-d | 5 | 2651 | 2026-W32 | 0.6 | 13.2 | - |
| detect-and-align-operational-framework | 4 | 2651 | 2026-W31 | 0.3 | 13.4 | - |
| force-actionable-accountability-pivot | 3 | 2651 | 2026-W30 | 0.3 | 14.6 | - |
| analogy-mapping-relationships | 2 | 2651 | 2026-W31 | 0.4 | 12.5 | - |
| map-abstract-theory-to-structural-constraints | 2 | 2651 | 2026-W28 | 0.3 | 16.9 | - |
| pivot-to-non-optimization-framework | 1 | 2651 | 2026-W30 | 0.0 | 16.0 | - |

## Output — calendar dates of the 2026-10-31 reading (2026-09-09 .. 2026-10-31)

### Source-pattern age of selected skills (2026-09-09 .. 2026-10-31)

#### Inputs

- skill-selection log: 125 files, 22197 lines; judged records in window: 4478 (enforced true 4478 / false 0 / absent 0); fail-open records in window (select nothing): 0
- judged records span 2026-09-09 .. 2026-10-31 (UTC)
- audit.jsonl: 1501 lines; skill files with an approved insight row: 82
- knowledge.json: 15222 patterns; skill files read for `name:`: 6172 (63 distinct names)

#### Traced

| population | rows | traced | untraced |
|---|---|---|---|
| selected | 29750 | 29490/29750 = 99.1% [99.0-99.2%] | 260 |
| catalog (baseline) | 238920 | 221008/238920 = 92.5% [92.4-92.6%] | 17912 |

Untraced by reason code:

| reason | selected | catalog (baseline) |
|---|---|---|
| name_unmapped | 0 | 0 |
| name_ambiguous | 0 | 0 |
| no_adoption_row | 0 | 0 |
| adopted_without_insight_row | 16 | 4478 |
| adoption_after_selection | 0 | 0 |
| adoption_row_without_source_ids | 244 | 13434 |
| source_pattern_missing | 0 | 0 |
| pattern_after_selection | 0 | 0 |

Source ids absent from knowledge.json on traced or untraced rows (summed per row): selected 0 / catalog 0

#### Age in weeks (selection time - median creation of the source patterns)

- selected: min 2.8 / Q1 7.8 / median 10.3 / Q3 12.3 / max 17.0
- catalog (baseline): min 2.8 / Q1 7.6 / median 10.0 / Q3 12.2 / max 17.0
- corpus at 2026-10-31T21:58+00:00, 13649 patterns: min 0.0 / Q1 4.3 / median 9.9 / Q3 14.9 / max 31.3

| age (weeks, floor) | selected | catalog (baseline) | corpus |
|---|---|---|---|
| 0 | 0 | 0 | 898 |
| 1 | 0 | 0 | 853 |
| 2 | 29 | 348 | 806 |
| 3 | 249 | 4269 | 671 |
| 4 | 1180 | 8015 | 518 |
| 5 | 1761 | 12552 | 722 |
| 6 | 2225 | 17803 | 624 |
| 7 | 2311 | 19713 | 588 |
| 8 | 2470 | 19876 | 573 |
| 9 | 3419 | 26840 | 591 |
| 10 | 4073 | 28651 | 597 |
| 11 | 3554 | 24431 | 626 |
| 12 | 2295 | 18293 | 619 |
| 13 | 2014 | 14344 | 675 |
| 14 | 1693 | 10509 | 902 |
| 15 | 1272 | 8991 | 830 |
| 16 | 942 | 6348 | 765 |
| 17 | 3 | 25 | 637 |
| 18 | 0 | 0 | 315 |
| 19 | 0 | 0 | 33 |
| 20 | 0 | 0 | 37 |
| 21 | 0 | 0 | 51 |
| 22 | 0 | 0 | 49 |
| 23 | 0 | 0 | 56 |
| 24 | 0 | 0 | 62 |
| 25 | 0 | 0 | 71 |
| 26 | 0 | 0 | 83 |
| 27 | 0 | 0 | 59 |
| 28 | 0 | 0 | 60 |
| 29 | 0 | 0 | 40 |
| 30 | 0 | 0 | 37 |
| 31 | 0 | 0 | 201 |

#### Per skill (selected in window)

| skill name | selections | catalog rows | source week (median) | within-skill spread (weeks) | median age at selection | untraced reason |
|---|---|---|---|---|---|---|
| shifting-focus-from-state-to-process-mechanics | 3087 | 4478 | 2026-W33 | 0.6 | 8.1 | - |
| structural-constraint-mapping-scm | 2801 | 4478 | 2026-W33 | 0.9 | 8.3 | - |
| dissecting-asserted-agency-into-mechanisms | 2694 | 4478 | 2026-W31 | 0.6 | 10.2 | - |
| internal-process-audit | 2538 | 4478 | 2026-W29 | 0.6 | 11.8 | - |
| cross-reference-foundational-claims | 2430 | 4478 | 2026-W28 | 0.3 | 13.8 | - |
| detecting-abstract-to-operational-constraint-shift | 2061 | 4478 | 2026-W27 | 0.6 | 12.8 | - |
| detecting-foundational-structural-compromise | 1973 | 4478 | 2026-W32 | 0.6 | 10.2 | - |
| suspend-interpretation-upon-premise-doubt | 1023 | 4478 | 2026-W31 | 0.9 | 11.2 | - |
| differentiating-artifacts-from-observation | 957 | 4478 | 2026-W32 | 0.9 | 7.8 | - |
| trace-structural-authority | 942 | 4478 | 2026-W28 | 0.4 | 14.2 | - |
| disaggregate-premise-from-effect | 746 | 4478 | 2026-W34 | 0.6 | 7.4 | - |
| pinpointing-systemic-boundary-conditions | 738 | 4478 | 2026-W32 | 0.3 | 7.7 | - |
| validate-provenance-chain | 732 | 4478 | 2026-W28 | 0.0 | 14.6 | - |
| boundary-assumption-verification | 639 | 4478 | 2026-W30 | 0.4 | 10.8 | - |
| detecting-rhetorical-discourse-closures | 622 | 4478 | 2026-W33 | 0.0 | 6.6 | - |
| mapping-systemic-dependency-failures | 530 | 4478 | 2026-W31 | 0.4 | 9.2 | - |
| analyzing-systemic-governance-loops | 513 | 4478 | 2026-W33 | 0.4 | 6.9 | - |
| scope-boundary-mapping | 457 | 4478 | 2026-W32 | 0.7 | 9.4 | - |
| analyzing-loci-of-identity-definition | 385 | 4478 | 2026-W28 | 0.7 | 14.1 | - |
| scope-failure-diagnosis | 374 | 4478 | 2026-W28 | 0.3 | 12.1 | - |
| identifying-structural-tensions-via-system-metaphors | 356 | 4478 | 2026-W31 | 0.6 | 10.6 | - |
| detecting-abstraction-decay-in-context | 328 | 4478 | 2026-W32 | 0.7 | 9.2 | - |
| extracting-simulation-boundaries | 328 | 4478 | 2026-W27 | 0.6 | 14.6 | - |
| articulate-epistemic-boundaries | 270 | 4478 | 2026-W28 | 0.7 | 12.1 | - |
| identify-systemic-boundary-stressors | 243 | 4478 | 2026-W30 | 0.4 | 10.7 | - |
| deconstruct-confidence-proxies | 224 | 4478 | 2026-W28 | 0.6 | 11.1 | - |
| identifying-fidelity-vs-utility-tension | 214 | 4478 | 2026-W32 | 0.0 | 8.3 | - |
| diagnosing-mechanisms-of-omission | 204 | 4478 | 2026-W34 | 0.4 | 7.3 | - |
| fluid-contextual-anchoring-loop | 204 | 4478 | - | - | - | adoption_row_without_source_ids 204 |
| identify-structural-pivot | 164 | 4478 | 2026-W31 | 0.4 | 10.4 | - |
| pivot-constraint-analysis | 161 | 4478 | 2026-W28 | 0.3 | 11.7 | - |
| cross-reference-metric-constraints-analysis | 134 | 4478 | 2026-W34 | 0.9 | 5.6 | - |
| distinguish-persistence-from-validity | 128 | 4478 | 2026-W33 | 0.7 | 8.7 | - |
| recognizing-boundary-declarations-in-content-flow | 122 | 4478 | 2026-W32 | 0.6 | 10.7 | - |
| modeling-null-states | 103 | 4478 | 2026-W31 | 0.6 | 9.6 | - |
| deconstructing-consensus-validity-through-shared-d | 47 | 4478 | 2026-W32 | 0.6 | 5.8 | - |
| analyze-decision-incentives | 41 | 4478 | 2026-W31 | 0.4 | 6.9 | - |
| testing-procedural-guardrails-with-counterfactuals | 40 | 4478 | 2026-W34 | 0.3 | 7.1 | - |
| dynamic-sematic-decoupling-and-contextual-anchoring | 26 | 4478 | - | - | - | adoption_row_without_source_ids 26 |
| identifying-foundational-model-failures | 24 | 4478 | 2026-W34 | 0.9 | 4.7 | - |
| translating-temporal-gaps-into-structural-utility | 21 | 4478 | 2026-W27 | 0.4 | 15.5 | - |
| map-abstract-theory-to-structural-constraints | 20 | 4478 | 2026-W28 | 0.3 | 10.1 | - |
| shifting-focus-to-systemic-degradation-gradient | 18 | 4478 | 2026-W34 | 0.1 | 7.0 | - |
| detect-and-align-operational-framework | 17 | 4478 | 2026-W31 | 0.3 | 7.3 | - |
| fluid-dynamic-resonance-regulation-and-consensus-m | 16 | 4478 | - | - | - | adopted_without_insight_row 16 |
| fluid-temporal-friction-to-insight-loop | 14 | 4478 | - | - | - | adoption_row_without_source_ids 14 |
| force-actionable-accountability-pivot | 12 | 4478 | 2026-W30 | 0.3 | 9.2 | - |
| analogy-mapping-relationships | 11 | 4478 | 2026-W31 | 0.4 | 7.9 | - |
| gradient-modeling | 11 | 4478 | 2026-W33 | 0.7 | 9.1 | - |
| pivot-to-non-optimization-framework | 4 | 4478 | 2026-W30 | 0.0 | 7.8 | - |
| anchor-analysis-using-embodied-signals | 2 | 4478 | 2026-W28 | 0.1 | 11.1 | - |
| define-bounded-autonomy-governance | 1 | 4478 | 2026-W31 | 0.7 | 6.4 | - |
