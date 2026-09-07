# ADR-0105: The Skill Store's Exit Gains a Second Signal — the Reader's Confusion Pairs

## Status

accepted — partially-supersedes ADR-0097

## Date

2026-09-07

## Context

The skill store has one code-owned exit and it has never fired.
[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) D5 built the never-selected
reading — zero selections across the whole selection history, at or above 600
judged exposures — and weekly stage 7b landed on 2026-08-22 (`4163e43`). It
has produced **two** weekly readings so far (`never-selected-2026-08-28.json`
and `-2026-09-04.json`). As of 2026-09-07 `skills/.archive/` holds 0 files and
the store is at 57 entries.

Two readings is a thin basis and this ADR does not claim otherwise: what it
supports is "the exit as built has not yet listed anything a human acted on",
not "the exit has been measured and found inert". The reason to add the second
signal now is not the archive count but the one below — the mechanism that
could see duplication was removed and nothing replaced it.

The second half of ADR-0097 D3 is why. That decision retired the LLM grouping
/ merge / clean consolidators, and with them the only mechanism that could
say "these two entries are the same entry twice". Its own re-proposal guard
carried an expiry — "the insight production side changes" — and that expiry
fired on 2026-09-02 with RFC-0017. So the question came back with no owner:
who notices that the store holds near-duplicates?

There is a reader who already notices, every day, in a log this repo keeps.
The pass-1 selector emits `rejected_names` — names it asked for that are not
in the catalog — and RFC-0015's 4th reading (window 2026-08-23..09-05, 1,030
judged records) classified every one of them by mechanism against the nearest
real catalog name: wordform variance, a semantically substituted word, or
value-layer text bled into the answer. The rule is frozen twice: in
`scripts/skillsel_reading.py::classify` (the manual instrument the evidence
document is generated from) and in
`core/selection_metrics.py::classify_hallucination` (the weekly reading).
When the reader keeps *misnaming its way into* an entry it rarely chooses,
that is the store telling us its own entries are not distinguishable to the
only consumer they have.

**The judge is code, not the local model.** The 2026-09-07 design session
checked this against the retirement literature as of that date (primary
sources fetched):

- Deterministic gates are the norm: Library Drift (arXiv:2605.19576), ASSAY
  (arXiv:2606.15390), SLIM (arXiv:2605.10923) and SkillOps
  (arXiv:2605.13716) all log an LLM verdict and none of them let it pull the
  trigger.
- The Blind Curator (arXiv:2607.07436, 2026-08) measured what happens when it
  does: once an LLM judge's false-pass bias passes 0.45, retirement stops
  entirely and the aggregate metrics do not show it. Handing this to `gemma`
  would require measuring that bias by fault injection first.
- Contribution-based signals cannot be ported. Library Drift's
  (success − failure)/attempts and ASSAY's masking both need task-level
  ground truth, which this project does not have. What is portable is
  SkillOps' conjunction: low utility **and** duplication — the AND is what
  keeps a genuinely unique capability from being deleted for being quiet.
- Evidence floors are not optional. Library Drift's A4 ablation retired on
  insufficient evidence and collapsed the store to 2 entries, below no-skill
  baseline.

**Merging is worse than archiving, at this budget.** Retain or Consolidate
(arXiv:2607.17545) finds every consolidation operator net-negative under a
loose budget where the raw entries fit — which is this project's pass 1, where
57 catalog lines fit the window. Sequential consolidation degrades (AWM
0.64 → 0.20, arXiv:2605.12978), and SkillCommit (arXiv:2608.15165) measured
similarity-driven merging in ACE at 3 improvements against 24 regressions.
SLIM's inactive set is the archive-shaped precedent, and ADR-0097 D5 already
built it here (`skills/.archive/` plus `superseded_by`).

**A ceiling is not a number.** Skill Shadowing (arXiv:2605.24050) attributes
68% of the loss to mis-selection and non-selection, with context volume at
noise level, and finds small models fail toward abandonment. Library Drift's
cap of 50 has no derivation behind it. The consumer-side reading — the
hallucination rate against catalog size — is the measure this project already
has, and `measurement-discipline` principle 4 forbids substituting a numeric
cap for it. The series, with denominators, from RFC-0015's 4th reading's
whole-history conditioning table (one table, so the rows are comparable):
0.57% at 19 entries (n=1,410), 7.72% at 37 (n=609), 17.38% at 48 (n=581),
20.16% at 45 (n=630), **24.95% at 57 (n=1,094)**. The 4th window's own
summary reports 25.44% (n=1,030) for the same catalog over a shorter span;
the two are different cuts and must not be mixed inside one series. It is not
monotone in entry count — 45 reads
20.16% above 48's 17.38%, and the single-day 50-entry regime reads 34.78% on
n=23 with a CI of [18.8..55.1], which is the datapoint that breaks
monotonicity in corpus tokens too (the evidence document says so in as many
words). Any use of this series has to carry its denominators.

One reading tempers the whole exercise: ContinualSkillBench
(arXiv:2608.03874) puts skill maintenance at 0.602 against plain ICL's 0.605.
The aggregate benefit of curating a store may be near zero. The purpose of
this exit is therefore not performance — it is keeping a store the reader can
tell apart.

## Decision

Weekly stage 7c reads the reader's confusion pairs and writes the week's
archive candidates. Nothing in the unattended chain touches the store.

1. **The rule is code and it has one home per layer.**
   `core/skill_confusion.py` builds the reading; the mechanism split and the
   nearest-name ruler are imported from `core/selection_metrics.py`
   (`classify_hallucination`, `nearest_catalog_name`) rather than copied.
   `scripts/skillsel_reading.py` stays as the manual instrument — it is
   stdlib-only so it can run outside the venv, which the RFC-0015 evidence
   document depends on — and `tests/test_skill_confusion.py` pins the two
   against each other on a fixture per mechanism.

2. **The signal is an AND: no demand AND confusion.** For a store entry, over
   the trailing 14-day window, `confused_as` (rejected-name emissions whose
   nearest catalog entry is this name, under the `wordform` or `semantic`
   mechanism) and `selected_window` (judged records that chose it). The entry
   is a candidate when `confused_as >= selected_window`, `confused_as > 0`,
   and its **whole-history** judged exposure is at or above the floor.
   `value_layer` bleed is not charged to any entry: the reader was reaching
   for the constitution, not for a skill.

3. **The floor is ADR-0097 D5's, shared not re-derived.** 600 judged
   exposures over the whole history, imported as
   `NEVER_SELECTED_EXPOSURE_FLOOR`. Two exit signals with two floors would let
   one week call the same entry both sufficiently evidenced and not. The
   window is likewise D5's dormant cut (14 days), which is also what carries
   the ≥ 600 judged records the consumption plan below reads over.

4. **The pair, and which side is listed.** For each candidate, every rejected
   name charged to it is scored against the catalog a second time with that
   entry removed; the heaviest runner-up is the partner. The side of the pair
   with fewer window selections is the listed one. A candidate whose
   variants resemble nothing else stands alone and is its own listed side. If
   the listed side is below the floor, the pair is still reported and lists
   nothing (`retire_blocked: below_floor`) — this is Library Drift A4's
   failure, refused structurally.

5. **Archive only. No merge, no supersede, no numeric cap.** The pipeline
   writes `weekly-<end>-archive-candidates.txt` — the union of the
   never-selected strict population and the listed sides, deduplicated,
   sorted, one **store filename** per line, which is what `adopt-staged
   --archive-names` addresses. The store is not touched by the chain. The
   Saturday gate passes the file, or does not.

6. **Fail-forward.** A failed stage 7c is `CONFUSION_READING_FAILED` in the
   audit log and removes both artifacts (a JSON without its candidate file
   reads at the gate as a complete reading with an empty half). Everything
   the reading cannot answer abstains with a code from `CONFUSION_REASONS`,
   and a lost log day withholds the pairs rather than reporting none.

## Review-when

### Consumption plan

- **Reader, weekly**: the Saturday gate (`/weekly-gate`), in Step 6c beside
  the never-selected reading. It reads `confusion-pairs-{end}.json` and hands
  `weekly-{end}-archive-candidates.txt` to `adopt-staged --archive-names`, or
  does not.
- **Reader of the deciding measurement, and who takes it**: the ceiling
  reading is *not* produced by stage 7b/7c. It is the hallucination rate from
  `scripts/skillsel_reading.py`, which is a manual instrument. **The gate
  takes it in the same session as the archive**, running that script over the
  trailing fortnight and appending the row (with the catalog size) to
  `docs/evidence/rfc-0014/`. If no archive happens, no
  reading is due — see the premise below. `.claude/skills/weekly-gate/SKILL.md`
  Step 6c carries the instruction; without that wiring the plan could silently
  never complete, which is the failure ADR-0101 exists to prevent.
- **What two readings decide**: whether the catalog-size hypothesis behind the
  ceiling holds. Two windows of ≥ 600 judged records inside the 10–25% band →
  the hypothesis stands and the reading continues. Two outside → catalog size
  is not what the rate tracks, and the next move is not retirement but family
  representation at selection time (Right Family, Wrong Skill,
  arXiv:2606.10388: passing one representative per family moved HSR@3 from
  0.35 to 0.007), which is RFC-0021's Future possibilities.
- **The band, and its weakness, stated plainly.** 10–25% is not derived; it is
  the range RFC-0021's decision line declares. The current 57-entry regime
  (24.95%, or 25.44% on the window cut) sits at or just past its upper edge,
  so "inside the band" is a near-miss question from the start. Against it, RFC-0015's 4th reading measures **daily**
  rates of 18.67%–35.06% inside a window where catalog and corpus never moved.
  Within-window noise therefore straddles both edges, and two window readings
  may not discriminate. That is a known limitation of this plan, not a
  discovery to be made later; if the two readings land inconclusive, the
  honest outcome is "the band cannot answer", not a third reading.
- **Unstated premise, now stated**: "two windows outside the band → catalog
  size is not what the rate tracks" only follows if the catalog *moved*
  between them. With 0 archives to date, a null result is equally consistent
  with "size never changed". So the two readings are due **after archives**,
  not after weeks, and the gate records the catalog size with each.
- **Removal condition**: when the two readings have been taken and the
  decision above is made, the *ceiling question* is closed. The reading itself
  stays only as long as it keeps producing candidates a gate acts on; a year
  in which every week lists nothing already-listed by 7b means the second
  signal adds nothing and stage 7c is removed with its module and its tests.
  (This last clause is this ADR's own tightening — RFC-0021's decision stops
  at "two windows inside the band → continue".)

### Expiry conditions

- Both hallucination-rate windows land outside the 10–25% band → supersede
  toward family representation (arXiv:2606.10388), not a lower floor.
- The selector changes (model, prompt shape, or the two-pass enforcement of
  [ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.md)) → `confused_as`
  is a reading of *that* reader; the pair rule must be re-measured before it
  is trusted, and the 2026-09-07 numbers in RFC-0021 become historical.
- The basis of the 600 floor changes — ADR-0097's own Review-when arm (a
  strict never-selected archive restored more than once) fires, or the
  first-selection latency distribution is re-read — → this ADR's floor moves
  with it, because it is the same number by import.
- An entry archived off a confusion pair is restored → the pair rule listed
  something a human disagreed with; one restoration is data, a second means
  the `>=` comparison is the wrong shape.

## Alternatives Considered

### `gemma` as the retirement judge (proposal B of the design session)

A local-model verdict on "are these two the same skill?", which is what the
retired ADR-0097 D3 grouping did. Not adopted: The Blind Curator
(arXiv:2607.07436) shows the failure is silent — above 0.45 false-pass bias
retirement stops and no aggregate metric reveals it — so adopting this would
require a fault-injection measurement of `gemma`'s bias first, which is a
larger project than the exit. The wider literature already routes the verdict
to a log rather than a trigger.

### Merging a family into one entry

ADR-0097 D6's `adopt-superseding` vocabulary exists and could have carried
this. Not adopted on the measurements above (arXiv:2607.17545 /
arXiv:2605.12978 / arXiv:2608.15165): under a budget where the raw entries
fit, consolidation is net-negative, and this project's pass 1 is exactly that
budget. Archiving is reversible; a merge is a rewrite.

### A numeric cap on the store

Library Drift's 50. Not adopted: the number has no derivation in the paper,
`measurement-discipline` principle 4 rejects caps in place of consumer-side
readings, and Skill Shadowing (arXiv:2605.24050) puts context volume at noise
level against mis-selection. The ceiling here is the hallucination band.

### Supply exhaustion as a third signal

RFC-0021's 2026-09-04 note proposed counting, through RFC-0023's retrieval,
whether episode lines still reach each skill. Kept as a reading, not a
trigger: no skill-library paper retires on a time threshold, and a skill with
supply but no demand is a description problem, not an exit.

### A separate floor for the confusion signal

Rejected in favour of importing ADR-0097 D5's. A second floor is a second
number to justify, and the two signals are ANDed into one file that a human
reads in one sitting.

### Do nothing

The status quo since 2026-08-22: one exit, two weekly readings, 0 archives,
a store at 57 entries and a hallucination rate that has risen with catalog
size across the whole series (0.57% at 19 entries over 1,410 judged records →
24.95% at 57 over 1,094, whole-history conditioning table). Not adopted; but note the weakness this ADR carries
either way — with two readings, "the exit produced nothing" is not yet
distinguishable from "the exit has barely run".

## Consequences

### Positive

- The store has a second exit signal whose judge is code, whose evidence
  floor is shared with the first, and whose output is a file the existing
  approval path already accepts unchanged.
- The confusion reading makes a fact legible that no artifact carried: which
  store entries the only reader of the catalog cannot tell apart. The
  2026-09-07 dry run reproduces **RFC-0021's 2026-09-04 note** (not RFC-0015's
  §4.4 grouping table, which is a different window and different counts) on
  the window that note was taken over, 2026-08-29..09-04: 34 against 35 for
  one entry, and 24 against 30 for the second where the note records 23. One
  off by one, one exact. On the 14-day operating window the same two entries
  read 70 against 78 and 41 against 77 — neither is a candidate there, which
  is the reading the pipeline will actually take.
- Lifting `nearest_catalog_name` out of the rejected-name tally removes the
  possibility of a third copy of the ruler, and the parity test names the two
  places the rule lives.

### Negative / accepted

- **The two rulers can disagree**, in three ways: `SequenceMatcher.ratio()`
  is not symmetric and the manual script takes its operands in the opposite
  order; core passes `autojunk=False` where the script takes the default; and
  core iterates `sorted(catalog_names)` where the script keeps input order.
  Measured
  2026-09-07 over the live log's 54 distinct rejected names: 0 mechanism
  disagreements, 5 nearest-name disagreements, all at similarity 0.37–0.57 —
  far below the 0.90 wordform floor, in the band where "nearest" is a weak
  claim anyway. It is enough to move which of two entries a single emission is
  charged to, and on the 2026-09-05 window it does exactly that. Accepted and
  pinned by test rather than resolved: changing the script's operand order
  would move the frozen numbers in `docs/evidence/rfc-0014/`.
- **A one-emission pair is a candidate.** With `confused_as >= selected` and
  zero selections in the window, a single misnaming makes a candidate. The
  exposure floor is the only thing standing between that and a thin
  retirement. On the 2026-09-05 window the one pair produced is already in the
  never-selected strict population, so the second signal added nothing that
  week — which is the honest reading of its first run.
- **The charge has no similarity floor, and the partner can be the listed
  side.** `classify_hallucination` calls any slug-shaped name with no
  value-layer token `semantic` at any distance, so an emission scoring 0.31 is
  charged to whichever entry is orthographically nearest by noise; and the
  runner-up is accepted at any similarity above 0, so on a real catalog there
  is essentially always a partner — one that may be listed for retirement
  without ever having met the candidate condition itself (it needs only the
  exposure floor and a store file). No floor is imposed because there is no
  derived number to impose (the 0.90 wordform floor answers a different
  question), so the reading reports the evidence instead: every pair carries
  the similarity band of its charged emissions and the partner's best
  similarity, in the JSON and in the findings line. A pair sitting in the 0.3s
  is a pair the gate can discount.
- One more artifact pair per week for the gate to read, against ADR-0101's
  mandate. The consumption plan above is why it is allowed to exist; the
  removal condition is written down.

### Neutral

- Stage 7c takes the never-selected half from stage 7b's JSON, but it walks
  the selection log itself for the confusion half: 7b and 7c are separate
  processes and **the week decodes the log twice**. What sharing
  `_scan_selection_history` buys is agreement, not speed — one definition of
  a judged record, one window cut, one rejected-name normalisation. What
  reading 7b's JSON buys is that a failed 7b leaves 7c with half a union
  named as `CONFUSION_NEVER_SELECTED_MISSING`, in both the JSON and the
  findings section, rather than read as "nothing to list".
- The reading is windowed while the floor is whole-history, which is the same
  two-scope shape the never-selected reading already carries; field names
  carry the scope.

## References

- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) — D3 (partially superseded
  here: the store's exit gains the second signal D3's teardown removed the
  means for), D5 (the never-selected exit and the 600 floor, reused), D6
  (`adopt-superseding`, deliberately not used), D7 (rule promotion, retained).
- [ADR-0099](./0099-weekly-report-instrument-redesign.md) — the prohibition on
  recommending vocabulary the findings section is written under.
- [ADR-0101](./0101-instrument-dissolution-mandate.md) — the consumption plan
  above is its requirement.
- [RFC-0021](../../rfcs/0021-skill-stocktake-family-saturation.md) — the
  2026-09-07 decision section this ADR records, with the source list as of
  that date.
- [RFC-0015 / RFC-0014 4th reading](../evidence/rfc-0014/skillsel-read-4-20260905.md)
  — the mechanism split, the hallucination series, and §4.4's grouping table.
- [The 2026-09-07 dry run](../evidence/adr-0105/dry-run-20260907.md) — the
  commands, the two windows, the parity measurement, and what the reading
  produced against the live log.
