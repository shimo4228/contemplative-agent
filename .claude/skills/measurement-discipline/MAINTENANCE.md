# MAINTENANCE — measurement-discipline (CA edition)

The global harness skill of the same name was moved here on 2026-11-08 and cut to the four traps
measured in this repo. The nine-principle version is in `~/.claude` git history
(`git -C ~/.claude show 9de937f~1:skills/measurement-discipline/SKILL.md`).

## Sources of each trap

- Trap 1 (guard firing rate): ADR-0082, the permanently-0 `observed` field
- Trap 2 (enforce-first): relevance gate, RFC-0047 speed design, read 2026-09-26
- Trap 3 (freeze once, measure noise floor): S31, `evals/` pinned assets + `check_staleness.py`;
  the row-data loss in RFC-0045 (2026-09-25)
- Trap 4 (test the gate first): claim_fidelity in jev-research-pipeline, 2026-10-01 to 02 — measured
  outside CA, kept because CA's judge gates share the shape

## Dropped principles and why

- "One success is not evidence", "gate on observations, not the calendar", "no numeric cap as a
  quality filter", "do not describe a distribution from what passed", "lab arm mirrors production":
  ordinary statistics the model applies unprompted; kept globally they pulled other repos toward
  waiting for n before fixing a known cause. Old references to "§1–§9" / "principle 4" in RFCs and
  ADRs point at the nine-principle version.
- Instrument design itself is `read-only-instruments`; shadow runs are `shadow-mode-validation`.
