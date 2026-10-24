# Q2 compounding axes — first public reading (2026-10-24)

Produced by `python3 scripts/compounding_axes_reading.py --data-repo <data repo> --format md --boundary 2026-06-28`. Input: the public data repo as it stood on 2026-10-24 (latest weekly files dated 2026-10-16; `knowledge.json` through the week of 2026-10-19). The one boundary passed is the generation-model change (ADR-0069); the full boundary list belongs to the regime-boundary table (P3-02.1), so `int` 1 means "on or after 2026-06-28" only.

Reading against [ADR-0124](../../adr/0124-research-questions-operational-definitions.md) Q2 (descriptive; the preregistered cuts apply to later readings, and no axis is combined with another):

- **Selection activity.** The window-active share of ever-selected skills is 0.91 to 0.96 across the 8 weekly files, with the lower interval bound at or above 0.79 every week. Neither the expected nor the falsifying shape is approached.
- **Corpus growth (throughput).** Weekly additions have been 488 to 821 since the week of 2026-07-27 and have not decayed toward zero while distillation runs. This is throughput, not novelty.
- **Environmental response.** Skill-comment-pair reply rates of 0.79 to 0.90 with intervals about +/-0.02 to 0.03 from the second file on (the first is wider); no non-injected arm exists in the public file, so nothing is attributable to the skills (RFC-0028). The first file (2026-09-11) covers only 15 observed publishes.
- **Source-pattern age.** Not computed here (private inputs); first reading is taken where the skill-selection logs live.

Table output follows.

# Q2 compounding axes (read-only; axes are not combined)

## skill_selection_activity

| week end | int | ever selected | window active | dormant | strict never |
|---|---|---|---|---|---|
| 2026-08-28 | 1 | 53 | 49/53 = 0.924 [0.821, 0.970] | 4 | 3 |
| 2026-09-04 | 1 | 53 | 48/53 = 0.906 [0.797, 0.959] | 5 | 4 |
| 2026-09-11 | 1 | 54 | 50/54 = 0.926 [0.825, 0.971] | 4 | 3 |
| 2026-09-18 | 1 | 54 | 52/54 = 0.963 [0.875, 0.990] | 2 | 0 |
| 2026-09-25 | 1 | 53 | 51/53 = 0.962 [0.873, 0.990] | 2 | 0 |
| 2026-10-02 | 1 | 53 | 50/53 = 0.943 [0.846, 0.981] | 3 | 0 |
| 2026-10-09 | 1 | 53 | 51/53 = 0.962 [0.873, 0.990] | 2 | 0 |
| 2026-10-16 | 1 | 53 | 50/53 = 0.943 [0.846, 0.981] | 3 | 0 |

## corpus_growth

| week start | int | added | still live | cumulative before | added / before |
|---|---|---|---|---|---|
| 2026-03-23 | 0 | 208 | 192 | 0 |  |
| 2026-03-30 | 0 | 30 | 26 | 208 | 0.144 |
| 2026-04-06 | 0 | 51 | 47 | 238 | 0.214 |
| 2026-04-13 | 0 | 52 | 28 | 289 | 0.180 |
| 2026-04-20 | 0 | 68 | 44 | 341 | 0.199 |
| 2026-04-27 | 0 | 80 | 56 | 409 | 0.196 |
| 2026-05-04 | 0 | 72 | 49 | 489 | 0.147 |
| 2026-05-11 | 0 | 61 | 49 | 561 | 0.109 |
| 2026-05-18 | 0 | 60 | 50 | 622 | 0.097 |
| 2026-05-25 | 0 | 44 | 39 | 682 | 0.065 |
| 2026-06-01 | 0 | 50 | 46 | 726 | 0.069 |
| 2026-06-08 | 0 | 40 | 40 | 776 | 0.051 |
| 2026-06-15 | 0 | 26 | 24 | 816 | 0.032 |
| 2026-06-22 | 0 | 391 | 375 | 842 | 0.464 |
| 2026-06-29 | 1 | 656 | 605 | 1233 | 0.532 |
| 2026-07-06 | 1 | 754 | 711 | 1889 | 0.399 |
| 2026-07-13 | 1 | 876 | 809 | 2643 | 0.331 |
| 2026-07-20 | 1 | 874 | 815 | 3519 | 0.248 |
| 2026-07-27 | 1 | 656 | 614 | 4393 | 0.149 |
| 2026-08-03 | 1 | 614 | 570 | 5049 | 0.122 |
| 2026-08-10 | 1 | 631 | 594 | 5663 | 0.111 |
| 2026-08-17 | 1 | 597 | 554 | 6294 | 0.095 |
| 2026-08-24 | 1 | 583 | 550 | 6891 | 0.085 |
| 2026-08-31 | 1 | 587 | 550 | 7474 | 0.079 |
| 2026-09-07 | 1 | 591 | 561 | 8061 | 0.073 |
| 2026-09-14 | 1 | 615 | 575 | 8652 | 0.071 |
| 2026-09-21 | 1 | 727 | 700 | 9267 | 0.079 |
| 2026-09-28 | 1 | 488 | 468 | 9994 | 0.049 |
| 2026-10-05 | 1 | 721 | 685 | 10482 | 0.069 |
| 2026-10-12 | 1 | 821 | 797 | 11203 | 0.073 |
| 2026-10-19 | 1 | 604 | 595 | 12024 | 0.050 |

## environment_response

| week end | int | observed publishes | skill-comment pairs with reply | skills >= 10 pairs |
|---|---|---|---|---|
| 2026-09-11 | 1 | 15 | 83/102 = 0.814 [0.727, 0.877] | 2 |
| 2026-09-18 | 1 | 126 | 658/747 = 0.881 [0.856, 0.902] | 22 |
| 2026-09-25 | 1 | 132 | 771/859 = 0.898 [0.875, 0.916] | 23 |
| 2026-10-02 | 1 | 96 | 494/628 = 0.787 [0.753, 0.817] | 18 |
| 2026-10-09 | 1 | 103 | 600/671 = 0.894 [0.869, 0.915] | 20 |
| 2026-10-16 | 1 | 243 | 1367/1599 = 0.855 [0.837, 0.871] | 26 |

## source_pattern_age

Not computed here (`reanalysis: private-rows`); first reading is taken where the private inputs live and frozen under `docs/evidence/`.

