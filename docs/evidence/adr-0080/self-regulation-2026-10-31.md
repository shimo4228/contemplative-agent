# Self-regulation reading — first frozen table (2026-10-31)

First reading of `scripts/self_regulation_reading.py` (P2-01.5), taken read-only on the
owner's Mac after the 2026-10-31 gate had written its `gate_record`, with the script as
committed beside this file (main `c36d9ddd` plus the round-2 columns: agreement, the
(vi) reconciliation and the reading-volume table):

```bash
python3 scripts/self_regulation_reading.py --home ~/.config/moltbook --repo . \
  --end 2026-10-31 \
  --changes ~/MyAI_Lab/contemplative-agent-data/pipeline/value-layer/changes.json
```

This reading is material, not a verdict. The re-read of whether the load instrument is
needed (ADR-0080, Re-read trigger) and `self_regulation_verdict=` are the owner's, in the
`gate_record` of the first gate that reads this file. Below is the script's output,
unedited, except the (vi) line: it was re-taken on the same day after the fix that
counts a week as covered only through its Sunday (W44 ends 11-01, after the 10-30
snapshot, so it is no longer covered); the rows were not re-taken.

---

## Self-Regulation Reading

Columns are read side by side, never summed. `rm_*` are the roadmap's own execution and are outside rulings / gate_min / outside. `agree` / `rm_agree` = gate_item rows whose decision equals the briefing's recommendation (k/n, with the Wilson interval from ten rows; P2-01.9). `-` = source unavailable.

| week | rulings | agree (rec = dec) | gate_min | drafts | outside | repairs | rm_dec | rm_agree | rm_min | rm_files | staged | adopted | archived | empty_sel (judged-empty/judged) | freeze |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-W37 | 6 | 6/7 | - | 2 | 211 | 13 | 0 | 0/0 | - | 0 | 0 | 0 | 3 | 0/599 = 0.0% [0.0–0.6%] | nonfix 61 / quiet 0 |
| 2026-W38 | 75 | 88/96 = 91.7% [84.4–95.7%] | - | 2 | 108 | 7 | 0 | 0/0 | - | 0 | 75 | 0 | 1 | 0/587 = 0.0% [0.0–0.7%] | nonfix 5 / quiet 0 |
| 2026-W39 | 1 | 5/5 | - | 0 | 48 | 12 | 0 | 0/0 | - | 0 | 0 | 0 | 0 | 0/570 = 0.0% [0.0–0.7%] | nonfix 9 / quiet 0 |
| 2026-W40 | 0 | 4/4 | - | 1 | 25 | 5 | 0 | 0/0 | - | 0 | 0 | 0 | 0 | 0/393 = 0.0% [0.0–1.0%] | nonfix 2 / quiet 0 |
| 2026-W41 | 1 | 5/5 | - | 0 | 0 | 5 | 0 | 0/0 | - | 0 | 0 | 0 | 0 | 0/554 = 0.0% [0.0–0.7%] | nonfix 2 / quiet 0 |
| 2026-W42 | 0 | 7/7 | 289 (>127) | 2 | 67 | 4 | 9 | 7/9 | 0 | 14 | 0 | 0 | 0 | 0/661 = 0.0% [0.0–0.6%] | nonfix 5 / quiet 0 |
| 2026-W43 | 0 | 1/1 | 251 (>127) | 0 | 309 | 81 | 5 | 5/5 | 0 | 652 | 0 | 0 | 0 | 0/695 = 0.0% [0.0–0.5%] | nonfix 82 / quiet 0 |
| 2026-W44 | 2 | 20/20 = 100.0% [83.9–100.0%] | 19 | 1 | 32 | 3 | 91 | 89/91 = 97.8% [92.3–99.4%] | 0 | 18 | 0 | 0 | 0 | 0/534 = 0.0% [0.0–0.7%] | nonfix 2 / quiet 0 |

### Reading volume (load series (ii), P2-01.3 / P2-06.1)

Lines of the weekly report the week's gate reads (`reports/analysis/weekly-{report}.md`, each section from its `## ` header to the next) and of its findings file. Read beside the table above, never summed.

| week | report | inventory (pending/exc/new/cont/disc) | Inventory | Ledger | Deviations | Exceptions | Discarded | carried (items/lines) | doc | findings |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-W37 | 2026-09-11 | 2/9/3/8/8 | 46 | 74 | 81 | 81 | 30 | 0/0 | 350 | 198 |
| 2026-W38 | 2026-09-18 | 0/10/0/10/10 | 37 | 68 | 9 | 75 | 22 | 0/0 | 249 | 82 |
| 2026-W39 | 2026-09-25 | 0/11/1/10/10 | 38 | 62 | 22 | 66 | 23 | 0/0 | 245 | 113 |
| 2026-W40 | 2026-10-02 | 0/12/2/11/11 | 37 | 55 | 46 | 81 | 22 | 0/0 | 279 | 144 |
| 2026-W41 | 2026-10-09 | 0/12/2/11/12 | 42 | 73 | 48 | 71 | 22 | 0/0 | 294 | 117 |
| 2026-W42 | 2026-10-16 | 0/14/0/13/11 | 43 | 68 | 8 | 78 | 23 | 0/0 | 258 | 143 |
| 2026-W43 | 2026-10-23 | 0/16/1/13/14 | 41 | 62 | 19 | 76 | 27 | 0/0 | 263 | 126 |
| 2026-W44 | 2026-10-30 | 0/18/0/12/15 | 56 | 59 | 8 | 99 | 26 | 4/1 | 286 | 154 |

Exceptions lines (P2-06.1): 78 (weekly-2026-10-16) → 76 (weekly-2026-10-23) → 99 (weekly-2026-10-30); fell in both of the last two reports: no.

zero-load run: 0 week(s) of rulings + drafts + outside = 0 (N = 8); not a candidate (0 < 8); weeks with no gate_record: 0. Sufficiency is the owner's (`gate_record self_regulation_verdict=`).

adopted = 0 and archived = 0 and identity updates = 0 for 3 consecutive week(s) (threshold 8): metabolism floor not reached (D-P2-01-3 = B: reached files the end-of-run consideration event under P4-01; it does not declare steady state).

(iv) open RFC ledger: 5 · (v) exceptions: 18 (weekly-2026-10-30)

intake — staged 4w: 0, pending: 0, adopted 4w: 0

recommender recorded on ruled gate_item rows in the window: gate 0/145, roadmap 105/105 (the audit's key, D-P2-01-2 = A; values are not printed).

(vi) against changes.json (P2-05.7, last snapshot 2026-10-30): 7 of 7 covered week(s) agree.
