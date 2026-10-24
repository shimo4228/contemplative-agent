# Reproduction scope — what the paper reported, what was checked, and what this project measures itself

The effect sizes cited for the Contemplative AI paper (IPD cooperation d = 7.09 / 5.73 / 0.66; AILuminate safety d = 0.96) are **the paper's reported values** (Laukkonen et al., 2025, arXiv:2504.15125). They are not measurements of this project. The sibling rules repository holds the table of its own replication attempts (`docs/reproduction-scope.md` in `contemplative-agent-rules`); this file adds this repository's side. Written 2026-10-24.

| Measurement | Where | Model | n | Conditions | Scoring | Relation to the paper |
|---|---|---|---|---|---|---|
| IPD paper protocol replication | rules repo | `qwen3.5:9b` | 2 per condition | 2 of 7 (baseline, `paper_faithful`) | rule-based parse | same direction, larger d, intervals too wide to compare; exploratory |
| IPD custom-versus-baseline two-arm bench | this repo, [ADR-0090](../adr/0090-ipd-two-arm-instrument-for-constitution-amendments.md), [evidence](adr-0090/) | `gemma4:e4b` | 10 per cell | custom (constitution-bearing prompt) versus baseline, read for arm A (current constitution) and arm B (staged), α = 0 / 0.5 / 1 | rule-based | not the paper's protocol; used as a floor-calibrated instrument for amendments, not as a replication |
| AILuminate two-arm (exploratory, uncalibrated) | this repo, [report](adr-0090/ailuminate-two-arm-report.md) | judge: cloud model | ~48 per technique | six prompting techniques, two constitution arms | LLM judge, 9–15 failed evaluations per arm | **not a reproduction** of the paper's AILuminate measurement; compares two constitution texts, labelled observation, not signal |
| Appendix C clauses, rule-compliance | rules repo | a coding agent | 3 scenarios | — | skill-comply classifier | 25% on value-neutral coding tasks; not an IPD or safety measurement |
| AILuminate safety d = 0.96 | — | — | — | — | — | not reproduced anywhere in this project |

Statements elsewhere should use one of: "the paper reports …" (for d = 7.09 / 5.73 / 0.66 and 0.96), "an exploratory replication at n = 2 on a different model found the same direction" (rules repo), or "this project's own instrument reads …" (this repo). The `llms.txt` line that read "with empirical validation — IPD cooperation d>7 and AILuminate safety d=0.96" attributes the paper's numbers to the rules repository; the corrected wording is given in the P3-01 report for the data repository.
