# Third-party word overlap in the public data (P0-03.9)

Frozen counts from `scripts/third_party_overlap.py`, run 2026-10-24 against the
public data repo at commit `d44544a` (`python3 scripts/third_party_overlap.py
--data-repo <data repo> --json counts-2026-10-24.json`). Counts only; no text is
printed or stored.

What is counted: items that contain at least one run of n consecutive words
(n = 8, 12, 20; lower-cased `\w+` words) that occurs in third-party text — the
`Context`, `Original post` and `Their comment` blocks of
`reports/comment-reports/*.md` — and never in the agent's own sections of the
same reports (Internal note, Output, Comment, Reply). It is a floor on quoting:
a quote the agent also repeated in its own output is not counted. It is a
heuristic: punctuation and quotation marks are ignored, so expect tens of rows
of movement under a different tokenisation.

| series | n = 8 | n = 12 | n = 20 |
|---|---|---|---|
| `knowledge.json` patterns (of 12,628) | 555 | 371 | 148 |
| `reports/analysis/*.md` files (of 82), whole file | 56 | 46 | 36 |
| the same, before the spliced `## Sample` section | 52 | 42 | 29 |
| unique `snapshots/*/skills/*.md` (of 64) | 0 | 0 | 0 |
| unique `snapshots/*/reasoning.md` (of 12) | 5 | 4 | 1 |

Patterns by month (n = 12): 2026-07 99, 2026-08 103, 2026-09 93, 2026-10 76; none
before 2026-07. Comment-report entries whose Internal note or Output names the
counterparty from the entry heading: 645 of 16,761.

These replace the "no raw quoted context" wording. Suggested sentence for NOTICE /
DATACARD / the dataset card: "Patterns are distilled from episodes that include
third-party posts; 371 of 12,628 patterns share a run of 12 words found only in
third-party text (555 at 8 words, 148 at 20), and 46 of 82 weekly documents do
(12 words), by the method above."
