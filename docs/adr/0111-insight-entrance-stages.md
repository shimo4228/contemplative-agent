# ADR-0111: The Insight Entrance Becomes a Sequence of Stages — Naming, Split Calls, Post-Extraction Duplicate Judge

## Status

accepted

## Date

2026-09-19

## Context

The skill store grew from 19 to 57 entries over July and August and saturated.
On a saturated store "almost everything is rejected" is the correct steady
state, and is what [ADR-0074](./0074-weekly-staged-insight.md)
assumed when it defined insight's job as detecting new stable themes. What was
wrong was not the yield — it was the **volume reaching the human gate**: four
Saturday gates rejected 142 candidates by hand.

Two read-only replays of the 2026-09-19 insight run (154 clusters, the window
2026-09-05 – 09-18; frozen in [docs/evidence/rfc-0041/](../evidence/rfc-0041/README.md))
measured where that volume is decided:

| Reading | Measurement |
|---|---|
| The pre-extraction novelty gate does not separate populations | Every tie-break arm stops the 7 controls at a rate at or above the 68 gate-rejected ones (reading 1) |
| A judge placed **after** the artifact does separate them | At t=0: `duplicate` on 33 of 68 gate-rejected, 12 of 53 leave-one-out adopted, 0 of 7 controls (reading 3) |
| Individual verdicts are reproducible only at t=0 | t=1.0 gave kappa 0.00–0.24 per verdict (control 0.00, leave-one-out 0.04, gate-rejected 0.24); t=0 was bit-identical across repetitions, 256 calls, 0 failures (readings 2 and 3) |
| Enum constraints remove the format violations | 512 enum-constrained calls produced 0 off-enum and 0 parse failures. The RFC-0027 violations (target name losing its date suffix 5/5, evidence ids swapped 2/12) were both in fields typed as an unconstrained `string` |
| Stacked, on the 75 labelled candidates | 75 → 42 with the post-extraction judge alone; 75 → **16** with both, on the covered-leaning gate production now ships (reading 3; the same stack over the retired `new` wording reads 25) |

The shape is [ADR-0084](./0084-post-distill-durability-gate.md)'s: a judge placed
before the artifact has no artifact to compare. The pre-extraction gate sees
three raw sample lines against one-line theme descriptions; the post-extraction
one sees a written candidate against five named neighbours in the same
projection.

Separately, [RFC-0024](../../rfcs/0024-skill-extraction-free-body-split-calls.md)
had the extraction call doing four jobs in one answer — body, fixed
`Problem` / `Solution` / `When to Use` template, one-line description, and
name — with a paragraph of naming instructions the model had to follow while
writing prose.

## Decision

Run each surviving cluster through a fixed sequence of stages, in this order:

```text
cluster
  → pre-extraction novelty gate   batch, temperature 0 (ADR-0074, RFC-0042 item 1)
  → naming                        1 call: reconfirm / insufficient / revise / new
       reconfirm / insufficient / revise → stop, recorded
  → body                          free prose, think-ON
  → description, name             two short constrained calls
  → duplicate judge               1 call: duplicate / distinct
       duplicate → stop, recorded
  → staging → the Saturday gate
```

1. **Naming stage, enforced from the first run.** One call per cluster at
   temperature 0, shown the cluster's observations with their ids and the five
   nearest store skills by nomic cosine. `kind` is an enum,
   `target_skill` is an enum over the five names shown, null for every kind
   but `revise`,
   `evidence_ids` is an enum array over that cluster's observation ids. No
   shadow mode: insight is stopped, so there is no production run to shadow;
   every call is in the audit log, so the replay exists either way.

2. **`revise` records and stops (option A).** A cluster that asks to revise an
   existing skill writes no body; its `target_skill` and `change_reason` go to
   the audit log. The goal is the volume reaching the gate, and a replacement
   path works against it. Widening the body call from `new` to
   `new` + `revise` is the whole of option B, and it can be added without
   undoing anything here.

3. **The extraction call splits into three.** The body is free prose — the
   fixed template and the naming instructions leave the prompt (RFC-0024).
   `description` (one sentence: what + when) and `name` are their own
   constrained calls, asked about a body that already exists. **Code assembles
   the frontmatter and rejects format violations at save time** — an empty or
   over-long body, a description outside 20–300 characters or carrying a quote,
   a name that does not slugify. A violation is a fault reason code, not a
   truncation: a clipped description is indistinguishable from a written one.
   This narrows [ADR-0096](./0096-insight-promotion-worth-abstain.md)'s reason
   vocabulary: three fault codes join it and `no_title` leaves it, because a
   title assembled by code cannot be missing. ADR-0096 carries a dated note.

4. **Post-extraction duplicate judge.** One call per written candidate at
   temperature 0, comparing it with the same nearest five in the same
   projection (name, description, and the first 230 characters of what it does
   and when). `verdict` and `nearest` are enums over what was shown. Only
   `distinct` reaches staging. The prompt is the measured text from
   `scripts/post_extraction_judge_replay.py`, moved to `config/prompts/`
   unchanged — the evidence is evidence of that wording. The candidate's side
   of the projection is NOT the measured shape: the replay read `## Solution`
   and `## When to Use` from both sides, and Decision 3 removes that template
   from new bodies, so a candidate now projects a 230-character prose head
   instead. Accepted knowingly rather than by keeping a template the body call
   no longer asks for; it is named again under Consequences.

5. **Both stages fail open**, in the direction the novelty gate already fails:
   a cluster the naming stage could not judge reaches the body call, a
   candidate the duplicate judge could not judge reaches staging. Each
   fail-open carries its own reason code (`llm_none`, `unparseable`,
   `off_enum`, `no_store`, `retrieval_unavailable`).

6. **Both stages log every call** to `$MOLTBOOK_HOME/logs/insight-stages.jsonl`,
   append-only,
   with the prompt and raw output base64 + sha256 and bounded, and the verdict,
   reason code, temperature and the store names shown in plain text
   ([ADR-0075](./0075-observability-by-default.md)). A separate file from
   `insight-novelty.jsonl`: that log's reader resolves a kind-less legacy row
   structurally (`is_novelty_judge_record`), a rule that holds only while the
   file carries the two families it was written for.

7. **No bespoke weekly instrument** ([ADR-0101](./0101-instrument-dissolution-mandate.md)).
   The four judged stopping reasons (`reconfirm`, `insufficient`, `revise`,
   `duplicate`) are counted per reason in the run's own yield line and in the
   `insight` summary. No reading script, rate, trend or gate metric column is
   added. The log does get a `scripts/_census_registry.py` row, because
   [ADR-0107](./0107-instrument-census-and-episode-log-folder.md) requires one
   of every self-written log and its absence prints `UNKNOWN`; that row is the
   existing census reading the log joins, not a new instrument, and its
   consumption plan is under Review-when.

8. **Both judging calls run think-OFF.** The replays that justify them ran that
   way, so think-ON here would be an unmeasured condition. [ADR-0069](./0069-gemma-production-model-and-think-on-value-layer-pipelines.md)'s
   think-ON stays where the generation is: the body call.

### How this differs from the judge ADR-0097 retired

[ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) Decision 1
retired a post-extraction judge whose pre-registered refutation fired: it was
asked **promotion worth** — "is this candidate worth promoting?" — about the
candidate **alone**, and answered promote 46/46 on its first production run. A
question with no comparison term has no evidence to weigh, which is the same
defect ADR-0084 named.

This judge asks a different question with a comparison term supplied: "is this
the same behavior as one of these five named skills?" On the 2026-09-19 replay
the rate separated by population — 33/68 rejected, 12/53 adopted, 0/7 control —
which is exactly the reading the retired judge could not produce.

## Review-when

- **Pre-registered refutation.** After insight resumes, once the duplicate
  judge has answered for **at least 30 candidates** (cumulative across weeks,
  read at the Saturday gate), a `duplicate` rate of 0% or 100% over those
  refutes the design: the stage is **removed**, not tuned. A rate pinned at
  either end is the ADR-0097 failure repeating — a judge answering the same
  thing regardless of the artifact. The n floor is there because the goal is
  single-digit weeks, where 0/3 is a quiet week rather than a verdict. The
  prompt is frozen for the duration; the store is not, so the reading records
  the store size each week and a change of more than a third resets the count
  (the neighbours are the comparison term, and swapping them swaps the
  question).
- The volume reading of [RFC-0042](../../rfcs/0042-insight-entrance-narrowing.md):
  if over three Saturday gates after the resume the count reaching the gate is
  back at the pre-stop level (~35 a week, 142 over four gates), the narrowing
  did not reproduce in production; freeze the store and retire insight, or redesign.
- The production generation model stops being gemma4:e4b. Temperature,
  constraint and call-split behavior were measured on it; a larger model may
  not need the split, and RFC-0017's flattening was model-borne.
- `revise` proposals accumulate for several weeks and are read. If they are
  usable, option B (a replacement path to the gate) is decided then — this ADR
  does not pre-commit against it.
- The store stops being saturated (a sustained fall below ~40 entries): the
  premise that near-total rejection is the steady state no longer holds, and
  a gate that stops half the candidates would then be suppressing.

### Consumption plan

The census row for `insight-stages.jsonl` is read by the weekly census
(ADR-0107/0110) as per-enum counts plus a fail-open error count, and by the
Saturday gate as the one count line above. It is consumed by exactly two
decisions: the refutation reading (30 candidates) and the RFC-0042 volume
reading (three gates). When both have been answered, the row stays only as
long as the writer does — retire the row with the stage, and if the stage is
removed, remove the log with it.

## Alternatives Considered

- **RFC-0041, redesigning from the knowledge schema.** Withdrawn. The motive —
  "the entrance passes nothing" — was saturation, not a fault, and a schema
  change has many consumers. Oversized for the problem.
- **Change only the pre-extraction gate** (temperature 0 and a covered-leaning
  tie-break, shipped as RFC-0042 item 1). It moves counts — 75 → 25 on the
  labelled set, the `covered` arm of reading 3 — but reading 1 shows it stops
  controls at least as often as rejects. Kept as a cheap pre-filter that limits how many naming calls run,
  not as the discriminating stage.
- **Shadow-mode the naming stage first** ([ADR-0076](./0076-skill-selection-shadow-instrument.md)'s
  pattern). Rejected: insight is stopped, so there is no live decision to
  shadow. The audit log gives the same offline replay without a second regime.
- **Option B — `revise` produces a replacement candidate** and reaches the gate
  as `--archive-names "old superseded-by new"`. Left open, not rejected;
  revisit condition above. It pushes volume back up and nobody has read a
  revision body yet.
- **Make the duplicate judge a retirement judge over the store** (its
  leave-one-out pairs are free every week). Not done: [ADR-0105](./0105-skill-store-exit-confusion-pairs.md)
  declined to make gemma the decider for retirement, and that stands. The pairs
  may later be **listed** for the Saturday gate; listing is not deciding.

## Consequences

### Positive

- The number of candidates reaching the human gate falls from 75 to 16 over the
  replayed two-week window — about 8 a week, against the 35 a week the four
  Saturday gates actually rejected (142 / 4).
- A cluster that yields nothing now says which stage decided it, and the four
  judged reasons are separated from the six fault reasons — a quiet week and a
  broken backend cannot read the same.
- Every gating call is replayable offline from `insight-stages.jsonl`.
- The body prompt asks for one thing, and the identity block is built by code
  rather than requested from a model: frontmatter can no longer be missing or
  malformed, so `no_title` became unreachable and was removed.

### Negative

- Calls per cluster go from 1 to as many as 5 (naming + body + description +
  name + duplicate). Clusters stopped at naming cost one short call, which is
  where most of them stop.
- The duplicate judge calls ~2 in 10 previously adopted skills `duplicate`
  (reading 3). Whether that is misjudgment or real overlap in the store is
  unseparated, so a genuinely new theme can be stopped at the same rate. It
  relies on recurrence: a stopped cluster is not ledger-written, so the theme
  can return in a later window.
- The candidate's side of the duplicate judge's projection is not the shape the
  replay measured: a 230-character prose head where the replay read two labelled
  sections. The store side keeps the sections until the first adoption under
  this ADR, after which both sides are prose and neither is the measured shape.
  The wording and the clip are unchanged; the input is not.
- The basis is one run of one window. Tuning the prompts from here would overfit
  to it — the wording is frozen and the next reading is the production numbers.
- The naming stage's reproducibility is unmeasured (RFC-0027's 12 questions ran
  once each, at temperature 1.0), and no one has yet read a `revise` body.

### Reversal cost

Removing the duplicate stage is one call site and one prompt pair; removing
the naming stage is the same plus the four judged reason codes and the
`VERDICT_ABSTAIN_REASONS` line that reports them. The call split is the
expensive one to undo: three prompts, the code-assembled frontmatter and the
three save-time fault codes would all fold back into one prompt, and the
store adopted in the meantime would hold both body shapes. Nothing in the
store is rewritten by this ADR, so a reversal loses no adopted skill.

### Neutral

- `config/prompts/` grows by six files; `insight_extraction.md` narrows to the
  body call.
- The eval baseline `comment_golden` goes stale on the prompt-hash check
  ([ADR-0089](./0089-llm-behavioral-eval-layer-on-deepeval.md), advisory) and is re-run and
  re-approved once, with the rest of RFC-0042.
- The stage sequence is now stated in five places (this ADR, RFC-0042,
  `src/contemplative_agent/core/insight.py`'s module docstring, the diagram JSON
  and `CLAUDE.md`'s CLI
  line). CLAUDE.md's freshness convention — a change to a gate or stage order
  updates the owning ADR, the script comment and the diagram in the same PR —
  is what keeps them from drifting; this ADR is the owner.

## References

- [RFC-0042](../../rfcs/0042-insight-entrance-narrowing.md) — the proposal this
  implements (items 2-4); item 1 shipped separately as an ADR-0074 amendment
- [docs/evidence/rfc-0041/](../evidence/rfc-0041/README.md) — the frozen
  replays every number here is drawn from, and the scripts that produced them
  (`scripts/novelty_tiebreak_replay.py`, `scripts/post_extraction_judge_replay.py`)
- [ADR-0074](./0074-weekly-staged-insight.md) — the pre-extraction novelty gate
  these stages bracket; carries a dated note pointing here
- [ADR-0084](./0084-post-distill-durability-gate.md) — precedent: a judge
  placed before the artifact has nothing to compare
- [ADR-0096](./0096-insight-promotion-worth-abstain.md) — the abstain reason
  vocabulary this narrows (`no_title` removed, three save-time codes added);
  carries a dated note
- [ADR-0097](./0097-consolidator-dissolution-and-skill-store-exit.md) — retired
  the promotion-worth judge; carries a dated note saying why this is not it
- [ADR-0075](./0075-observability-by-default.md) /
  [ADR-0101](./0101-instrument-dissolution-mandate.md) — the audit log and the
  consumption plan it owes
- [RFC-0024](../../rfcs/0024-skill-extraction-free-body-split-calls.md) — the
  call split and the free body, absorbed into RFC-0042
- Implementation: `src/contemplative_agent/core/insight_stages.py`,
  `src/contemplative_agent/core/skill_projection.py`,
  `src/contemplative_agent/core/insight.py`,
  `config/prompts/insight_{naming,naming_system,description,name,duplicate,duplicate_system}.md`,
  `scripts/_census_registry.py`, `tests/test_insight_stages.py`,
  `docs/diagrams/pipeline-02-insight-selection.workflow.json`
