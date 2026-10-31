# Principle coverage — the first four weeks (2026-10-03..10-30, ROADMAP P3-06.9)

The four weekly windows before the column entered the weekly materials, computed
on 2026-10-31 in one pass instead of waiting four future Saturdays. The script is
deterministic over saved comment reports, so a past week reads the same now as it
would have on its own Saturday. Calibration of the columns:
[`calibration.md`](calibration.md).

Source: the production `reports/comment-reports/comment-report-YYYY-MM-DD.md`
(the canonical read path; no episode log is read). Column (d) reads today's
`identity.md` for every week — the flag is the identity at reading time, not the
identity in force during each week. No model was called.

```
python3 -I scripts/principle_coverage.py --report-dir ~/.config/moltbook/reports/comment-reports \
  --start <Sat> --end <Fri> --identity ~/.config/moltbook/identity.md
```

## Four weeks side by side

Intervals are 95% Wilson (`scripts/_stats.wilson_ci`, the P2-01.9 rule).

| column | 10-03..10-09 | 10-10..10-16 | 10-17..10-23 | 10-24..10-30 | pooled 10-03..10-30 |
|---|---|---|---|---|---|
| entries / report days | 404 / 7 | 541 / 7 | 592 / 7 | 593 / 7 | 2,130 / 28 |
| (a) commented although the note said nothing stood out | 0/199 (0.0–1.9%) | 0/191 (0.0–2.0%) | 0/191 (0.0–2.0%) | 0/176 (0.0–2.1%) | 0/757 (0.0–0.5%) |
| (b) threads, two COMMENTs with no REPLY between (lower bound) | 0/227 (0.0–1.7%) | 0/234 (0.0–1.6%) | 0/251 (0.0–1.5%) | 0/254 (0.0–1.5%) | 0/905 (0.0–0.4%) |
| (c1) axiom proper noun in Output | 2/376 = 0.5% (0.1–1.9%) | 2/503 = 0.4% (0.1–1.4%) | 1/552 = 0.2% (0.0–1.0%) | 5/550 = 0.9% (0.4–2.1%) | 10/1,981 = 0.5% (0.3–0.9%) |
| (c2) concrete reference (5-word span shared with Context) | 130/376 = 34.6% (29.9–39.5%) | 150/503 = 29.8% (26.0–34.0%) | 174/552 = 31.5% (27.8–35.5%) | 153/550 = 27.8% (24.2–31.7%) | 607/1,981 = 30.6% (28.6–32.7%) |
| (c3) axiom noun without concrete reference | 1/376 = 0.3% (0.1–1.5%) | 1/503 = 0.2% (0.0–1.1%) | 0/552 = 0.0% (0.0–0.7%) | 4/550 = 0.7% (0.3–1.8%) | 6/1,981 = 0.3% (0.1–0.7%) |
| (c4) constitution/axiom word in Output, absent from Context | 50/376 = 13.3% (10.2–17.1%) | 63/503 = 12.5% (9.9–15.7%) | 65/552 = 11.8% (9.3–14.7%) | 69/550 = 12.6% (10.0–15.6%) | 247/1,981 = 12.5% (11.1–14.0%) |
| (d) silence-permission sentence in identity text | False (reason=ok) | False | False | False | False |

## What the four weeks say

- (c1) / (c3) sit where the negative control (2026-09-07..13: 0.6% / 0.6%) predicted;
  carewashing by axiom label is absent in these weeks.
- (c4) is stable at 12–13% in every week, above the negative control's 10.6% only
  inside the intervals' overlap. It is the column that moves, if any does.
- (a) and (b) are 0 in every week and in the negative control. Two readings are
  possible and the columns cannot tell them apart: the behaviour does not occur, or
  the proxy cannot see it — (a) needs the note to use the "nothing stood out" family
  of phrases, and (b) cannot see a third party's comment between two of the agent's
  (see the script docstring). A column that never fires is read as "checked, no
  problem"; this one has not yet been shown to fire on any window. Treat (a) and (b)
  as unvalidated, not as negative.
- (d) is False: the production identity has no "it's okay not to respond" sentence
  (the template's `config/templates/contemplative/identity.md:7` has it).

## Consumption

This is the four-week reading of the consumption plan (a). The decision it feeds,
D-P3-06-3 (whether to add a "read and do not reply" branch), stays with the owner
at its gate; the reading does not decide it. If D-P3-06-3 is A (record only), the
columns leave the materials and this file is where they stay.
