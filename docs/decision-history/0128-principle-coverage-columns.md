# ADR-0128: Four Deterministic Principle-Coverage Columns in the Weekly Materials

## Status

accepted

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session (ROADMAP P3-06.9 front-loaded implementation)
decided-by: shimo4228 (owner) — ROADMAP-2026-10 adopted 2026-10-11; the rest-as-recommended instruction of 2026-10-24
date: 2026-10-24

## Layer

instrument

## Context

The four axioms reach the agent only as prose in the system prompt, and the
only reading of whether any of them shows up in what the agent actually does
is a human one: the weekly report's writer reads comments and remarks. That
reading has a known failure mode (ADR-0099: the writer's own selection
function), and ADR-0106 D4 forbids the other obvious route (a model judging
published comments).

Four mechanism facts make a deterministic reading possible and necessary:

- `feed_manager.py` extracts an `internal_note` before commenting, but nothing
  between the note and `create_comment(post_text)` depends on it, and there is
  no "read it, then decline" branch. A note that says nothing stood out still
  leads to a comment (Mindfulness: detection is cut off from action).
- The packaged identity template says it is okay not to respond to everything;
  the production `identity.md` has no such sentence.
- Axiom proper nouns almost vanished from comments after 2026-06 (0-2 %), while
  they were common in March 2026 (Phase 3 of the diachronic analysis) — a
  negative control that is nearly trivial for column (c) alone.
- ADR-0047 recorded axiom-label collapse; whether a comment that names an axiom
  also refers to anything concrete in the post is not measured.

## Decision

`scripts/principle_coverage.py` adds a `## Principle Coverage` section to the
weekly materials (wired in `scripts/weekly-analysis.sh` beside the instrument
census). It reads `comment-report-YYYY-MM-DD.md` only, calls no model, writes no
state, and prints counts, rates and 95 % Wilson intervals (`scripts/_stats.py`;
a denominator below 10 prints the count only). Nothing it reports reaches
generation: it is a reading, not a filter (`config/prompts/principles.md:22`).

| column | definition |
|---|---|
| (a) Mindfulness | COMMENT entries whose Internal note says nothing stood out, over COMMENT entries that carry a note. Legacy-format reports carry no note and read as "no note", never as 0 |
| (b) Silence | threads (post ids) where the agent spoke twice as a COMMENT with no REPLY between, over threads with a COMMENT or REPLY. A lower-bound proxy: the report holds only the agent's own entries |
| (c) Carewashing | per COMMENT/REPLY: axiom proper noun in the Output; a 5-word verbatim span shared with the Context ("concrete reference"); axiom noun without a concrete reference; and the general self-reference words constitution / axiom in the Output that the Context lacks |
| (d) Identity | whether `identity.md` contains a silence-permission sentence (flag) |

Calibration (both controls on public data; frozen in
`docs/evidence/principle-coverage/calibration.md`): the positive control is
2026-03-12..20 (the Phase 3 window in `agent-diachronic-analysis.md`), the
negative control is the week 2026-09-07..13.

The output boundary is closed: no body text, no post id and no counterparty name
is printed (`tests/test_principle_coverage.py::TestOutputBoundary`), because the
Context sections are other agents' posts.

## Review-when

Revisit if the report grammar of `core/report.py` changes (the parser reads two
grammars today), if `feed_manager` gains a decline branch after the note (column
(a) then stops measuring a cut-off), or if the identity template's
silence-permission sentence is adopted or retired (column (d)).

### Consumption plan (ADR-0101)

- **Reader**: the owner, at the Saturday gate, reading the four columns in the
  materials for four consecutive weeks. Earliest: four Saturdays after the Mac
  pulls the script (about 2026-11-28 if merged 2026-10-31).
- **What the four weeks decide**: D-P3-06-3 — whether a "read and do not reply"
  branch or a loop-closing mechanism is worth adding — by RFC. The recommendation
  until then is A (record only); the ruling is the owner's, written as a
  `gate_item`.
- **Removal condition**: if D-P3-06-3 is A, the columns leave the materials after
  the four weeks and the readings are frozen in `docs/evidence/`; if B, the RFC
  inherits them as its instrument.

## Alternatives Considered

- **A model-judged "did the comment embody the axiom" score.** Rejected by
  ADR-0106 D4 and by the single-scalar prohibition of ADR-0080's metabolic-quality
  addendum.
- **Blocking axiom words or requiring concrete references at generation time.**
  Rejected: a phrase blocker is the mechanism `principles.md:22` forbids, and it
  would turn a reading into a target.
- **Reading the episode logs for exact thread state in (b).** Rejected: the
  episode folder is the prompt-injection path (ADR-0107); the report-only proxy
  is stated as a lower bound instead.

## Consequences

The materials grow by one table. Columns (a) and (b) read zero or near zero in
every post-2026-07 window, which is itself the reading: the note-to-action cut and
the absence of a consecutive-speaker pattern are structural, not tuned. Column (c)
separates the March window (33.6 % axiom nouns, 30.8 % without a concrete
reference) from the September window (0.6 %); the general-word rate (c4) stays at
10-13 % in the later weeks, so the proper-noun column alone would have understated
self-reference.

## References

- `ADR-0099` — the writer's own selection function is the reason for a
  deterministic reading
- `ADR-0106` — D4: no model judging of published comments
- `ADR-0101` — consumption plan
- `ADR-0047` — axiom-label collapse
- `docs/evidence/principle-coverage/calibration.md` — the two control readings
