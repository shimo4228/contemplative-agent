# Principle-coverage calibration (ROADMAP P3-06.9, ADR-0128)

Both controls run on the public data repository (`contemplative-agent-data`,
`reports/comment-reports/`, `identity.md`) on 2026-10-24 with
`scripts/principle_coverage.py`. No private log was read. The reports before
about 2026-07 use the legacy grammar (no Internal note), so column (a) is
`unavailable` there by construction and is calibrated on the new grammar only.

## Positive control — 2026-03-12..2026-03-20

The window in which `reports/analysis/agent-diachronic-analysis.md` ("Phase 3",
"Emptiness" 262 occurrences) says the axiom nouns became the dominant keyword.
Prediction: column (c1) clearly positive. Observed 33.6 % — positive.

```
python3 -I scripts/principle_coverage.py --report-dir <data>/reports/comment-reports \
  --start 2026-03-12 --end 2026-03-20 --identity <data>/identity.md
```

Window 2026-03-12..2026-03-20: 9 comment-report days, 730 entries. Scripted from comment reports only (scripts/principle_coverage.py); no model judged anything. These are readings, not filters: nothing here feeds generation (config/prompts/principles.md).

| column | reading |
|---|---|
| (a) Mindfulness: commented although the note said nothing stood out | 0/0 (count only: denominator < 10); comments with no note: 730 |
| (b) Silence: threads where the agent spoke twice as a COMMENT with no REPLY between (lower-bound proxy) | 52/672 = 7.7% (95% Wilson 5.9%-10.0%) |
| (c1) Axiom proper noun in Output | 245/730 = 33.6% (95% Wilson 30.2%-37.1%) |
| (c2) Concrete reference (5-word span shared with Context) | 160/730 = 21.9% (95% Wilson 19.1%-25.1%) |
| (c3) Axiom noun without concrete reference | 225/730 = 30.8% (95% Wilson 27.6%-34.3%) |
| (c4) constitution/axiom word in Output, absent from Context | 132/730 = 18.1% (95% Wilson 15.5%-21.0%) |
| (d) Silence-permission sentence in identity text | False (reason=ok) |


## Negative control — 2026-09-07..2026-09-13

Prediction (stated before the run, from the roadmap): axiom nouns appear in
0-2 % of 2026-06..10 comments, so (c1) negative. Observed 0.6 % — negative.

```
python3 -I scripts/principle_coverage.py --report-dir <data>/reports/comment-reports \
  --start 2026-09-07 --end 2026-09-13 --identity <data>/identity.md
```

Window 2026-09-07..2026-09-13: 7 comment-report days, 512 entries. Scripted from comment reports only (scripts/principle_coverage.py); no model judged anything. These are readings, not filters: nothing here feeds generation (config/prompts/principles.md).

| column | reading |
|---|---|
| (a) Mindfulness: commented although the note said nothing stood out | 0/280 = 0.0% (95% Wilson 0.0%-1.4%); comments with no note: 0 |
| (b) Silence: threads where the agent spoke twice as a COMMENT with no REPLY between (lower-bound proxy) | 0/315 = 0.0% (95% Wilson 0.0%-1.2%) |
| (c1) Axiom proper noun in Output | 3/481 = 0.6% (95% Wilson 0.2%-1.8%) |
| (c2) Concrete reference (5-word span shared with Context) | 125/481 = 26.0% (95% Wilson 22.3%-30.1%) |
| (c3) Axiom noun without concrete reference | 3/481 = 0.6% (95% Wilson 0.2%-1.8%) |
| (c4) constitution/axiom word in Output, absent from Context | 51/481 = 10.6% (95% Wilson 8.2%-13.7%) |
| (d) Silence-permission sentence in identity text | False (reason=ok) |


## Reading

- (c1)/(c3) separate the two windows (33.6 % / 30.8 % against 0.6 % / 0.6 %),
  so the column detects what it is meant to detect and stays quiet where it
  should.
- (c4), the general self-reference words, is 18.1 % in March and 10.6 % in
  September. The proper-noun column alone drops to near zero and would have
  read the later weeks as "no self-reference"; (c4) is why it sits beside it.
- (a) is calibrated differently, because the public reports hold no natural
  positive: over the whole new-grammar span 2026-07-01..2026-10-23 it reads
  3 of 4269 comments (0.1 %). The notes that mention "nothing in particular
  stood out" almost always quote the prompt while discussing it (the pattern
  skips matches preceded by "if "), so the agent practically never records
  the verdict "nothing stood out" and then comments anyway. The positive
  control for (a) is therefore the fixture test
  (`tests/test_principle_coverage.py`), not a historical window; a near-zero
  (a) says the note rarely states the verdict, not that note and action are
  connected (they are not: there is no decline branch after the note).
- (b) reads 0 of 315 in the September week; March's 7.7 % comes from the
  legacy grammar and is the shape of a positive control, not a trend.
- (d) is False for the production `identity.md`: no silence-permission
  sentence.

These readings are two calibration windows, not the four-week reading of
ADR-0128's consumption plan.
