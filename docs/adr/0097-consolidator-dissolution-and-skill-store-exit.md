# ADR-0097: Consolidator Dissolution and a Skill-Store Exit — Subtraction, then Exit, then Vocabulary

## Status

accepted — partially-supersedes ADR-0016, ADR-0046, ADR-0048, ADR-0096

## Date

2026-08-22

## Context

The weekly skill-extraction pipeline (`insight --stage` Sat 08:00 → staging →
headless Claude review in `scripts/weekly-pipeline.sh` → human `adopt-staged`
at the Saturday gate, [ADR-0074](./0074-weekly-staged-insight.md) /
[ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.md)) stages
46–55 candidates every week regardless of store saturation, because candidates
are the ≥3-pattern clusters of that week's episodes. Over 7 weeks (2026-07-09
… 08-22): 438 staged, 53 adopted (12%); rejection reasons are almost entirely
"already covered by an adopted skill" or "same as a batch sibling".

The gemma novelty gate (ADR-0074 D6, `core/insight_novelty.py`) marks 12–30%
of clusters covered (13/97, 23/77, 11/75, 8/61, 13/68) where the reviewer and
human reject 80–90% as covered. Its evidence is store+ledger names and
descriptions only, 3 sample patterns × 300 chars per cluster, with a prompt
that says "when in doubt mark NEW"; it never compares candidates within a
batch.

The [ADR-0096](./0096-insight-promotion-worth-abstain.md) promotion-worth
judge ran in production for the first time on 2026-08-21: 46/46 `promote`,
extraction-side `NOTHING-PROMOTABLE` 0 of 55 (`insight-launchd.log`: "yield
46/55 … nothing_promotable=0"). ADR-0096 pre-registered exactly this outcome
as its refutation ("Rate = 0%: the gate is not firing, the design is refuted
rather than mistuned, and the fallback is … keep the channel, drop the
judge"). It is the third consistent reading of a gemma self-judge saying yes
to everything ([ADR-0084](./0084-post-distill-durability-gate.md) v4 arm
40/40; ADR-0096 offline check 18/18; production 46/46). The same ADR's
surprise instrument (D10–12) has no named consumer —
`config/prompts/insight-recommendation.md` never mentions it — which the ADR
itself named as its removal condition.

The effective judge is the headless Claude reviewer: in all four gate weeks
(08-01, 08-08, 08-15, 08-22) the human's adopt set equalled the reviewer's
`RECOMMEND: adopt` set (13/8/5/9; name-for-name on 08-22). The reviewer names
the covering store skill and the shadowed batch siblings in prose, but
`scripts/weekly-pipeline.sh` only checks `grep -q "RECOMMEND:"` and
`scripts/build_decision_packet.py` only counts headings — the coverage
judgment is discarded every week. On 08-22 the reviewer (and therefore the
human) adopted one skill whose name, description and body disagree
(`analyzing-systemic-governance-loops`) and three variants of one theme.

The store holds 57 skills (15.3k words). Frontmatter carries only `name` /
`description` / `origin`; adoption date lives in the filename suffix and
pattern lineage only in `audit.jsonl` (the staging sidecar is unlinked at
adopt). There is no exit: `remove-skill` ran 6 times in 5 months;
skill-stocktake merges ran on 2026-04-11, 04-14, 05-30, 06-01 and 08-15, all
human-triggered. In the trailing week 19 skills were never selected; three
have never been selected in the whole selection history at 1,845–2,531 judged
exposures each (`pre-processing-state-validation`,
`assume-perfect-adversarial-understanding`,
`introducing-intentional-systemic-ambiguity`). Among skills that were
eventually selected, the judged exposures before first selection were p50 7 /
p90 99 / p95 302 / max 569.

The [ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.md)
selector picks families, not skills: some member of the six-skill
"constraint" family is selected in 0.78 / 0.74 / 0.72 / 0.81 of judged
actions across four consecutive weekly windows (07-25 … 08-22, 606–686 judged
each); the "deconstruct" family in 0.83 / 0.85 / 0.80 / 0.72. Co-selection in
the 08-15–08-22 window (606 judged) yields three mutually co-selected pairs
(both conditional probabilities ≥ 0.6: `cross-reference-foundational-claims`
↔ `dissecting-asserted-agency-into-mechanisms` 0.63/0.65;
`internal-process-audit` ↔ `shifting-focus-from-state-to-process-mechanics`
0.64/0.69; `detecting-abstract-to-operational-constraint-shift` ↔
`structural-constraint-mapping-scm` 0.66/0.77) and eleven asymmetric sub-case
pairs (P(b|a) ≥ 0.7, P(a|b) ≤ 0.4, e.g.
`suspend-interpretation-upon-premise-doubt → internal-process-audit`
0.96/0.23) — a family structure computed from
`logs/skill-selection-*.jsonl` with no LLM and no embeddings. The six
constraint-family skills carry distinct procedures (register-switch
detection; three-level failure analysis; limiting-factor search across
physical/attention/throughput; abstraction → measurable persistence;
boundary-as-condition reading; assumption checklists at interfaces); what
they share is a stance.

The selector's hallucination rate (judged records with non-empty
`rejected_names`) rose with catalog size: 0.6% at 24 skills, 7.7% at 37, 20.2%
at 45, 18.0% at 48–57 (109/606); almost all are word-form variants of real
names (`suspending-` vs `suspend-`, `identifying-` vs `identify-`,
`structuring-constraint-mapping-scm`).

The three consolidators, measured on the 2026-08-15 manual run (Ollama
gemma4:e4b, think ON): `skill-stocktake --stage` took 68 min and ≈97 LLM
calls (≈1 + G + 2N per run: grouping, merge per group, clean per singleton,
description audit per survivor); the clean stage
([ADR-0048](./0048-trigger-altitude-skill-lifecycle.md) stage 3) processed 47
skills → 14 byte-identical rewrites that `is_clean_noop` does not catch (it
only checks the `CLEAN_NOOP` sentinel), 3 rewrites that *inserted* the
generalization boilerplate ("a particular individual" / "a specific topic" /
"in similar contexts") into skills that had no transient identifier, 4
adopted / 21 rejected. Grouping has used frontmatter summaries since the
[ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.md)
amendment with no recall measurement. `rules-distill --stage` (8 min, 4
calls) logged "processing all 48 skills" but passed 20 to the LLM
(`cluster_patterns(max_size=10)` then `singletons[:10]`, enumeration order
because every skill dict carries the same importance 0.1); it passes neither
existing rules nor constitution nor identity to the prompt; all 8 candidates
were rejected (an Emptiness-axiom paraphrase; a paraphrase of a skill
selected 339 times); it has no path to retire a skill whose content moved to
a rule, so promotion would double-inject; `.last_rules_distill` is written
only on the interactive path. `rules-stocktake` runs grouping and shared-core
synthesis over two rule files unchanged since 2026-04-11.

Exploration for this decision (T-CONSOLIDATOR-REDESIGN): two code maps, the
author's vault wiki, an external literature survey as of 2026-08-22,
cross-field analogies (library weeding, Wikipedia merge/redirect, API
deprecation, memory consolidation, Zettelkasten, lexicography, taxonomy,
stock-and-flow), a fresh-context architect verdict, and a Codex premise
challenge. Findings that bear on the decision: storing everything is worse
than no memory and selective memory works only when the judge is good
(Experience-Following, arXiv:2505.16067); an agent that executes, distils and
verifies its own output verifies leniently (EDV, arXiv:2606.24428);
programmatic signals beat open-ended introspection (arXiv:2605.29463);
libraries without an exit bloat and their utilization collapses (AutoRefine
v1, arXiv:2601.22758: 108 patterns at utilization 0.08 without maintenance vs
~24 at 0.71; SkillBrew, arXiv:2605.29440: add-only 47.0 vs 59.0); whole-store
rewrites collapse context (ACE, arXiv:2510.04618: 18,282 → 122 tokens); Mem0
v3 (2026-04) abandoned UPDATE/DELETE because reconciliation destroyed
context.

Usage ≠ utility is replicated (arXiv:2608.03874, 2604.17308, 2602.12670), so
a usage count cannot prove a skill useless — but a skill never selected under
two-pass injection was never injected, so removing it cannot change judged
behaviour; CREW library weeding treats last-circulation date as a filter the
librarian must still review, and mandates written reasons because 98% of
candidates were retained until reasons were required; Wikipedia merges the
newer duplicate into the older article.

The architect's verdict: "the build is mostly subtraction plus one field and
one list; deletions first, then the exit, then capture the judgment that
already exists; instruments last". The Codex challenge refuted the claim that
archiving never-selected skills is behaviour-neutral *by construction* (the
fail-open path re-injects the full corpus) — checked: 0 fail-open records in
3,716 since 2026-07-13, and the full corpus (38,867 tokens) already exceeds
NUM_CTX 32,768 so fail-open abstains rather than injects (ADR-0081
amendment) — and asked for a maintenance owner for the rules layer, an
observer for reviewer false negatives, and a stronger completeness check
before verdict vocabulary touches the store.

## Decision

1. **Execute ADR-0096's pre-registered fallback.** Remove the
   promotion-worth LLM call (`insight._worth_gate`,
   `config/prompts/insight_worth.md`, the `insight-worth.jsonl` writer) and
   the surprise instrument (`core/insight_surprise.py`, the sidecar
   `surprise` field, `adopt-staged`'s surprise print). Keep ADR-0096
   Decisions 1 and 4–6: the `NOTHING-PROMOTABLE` extraction abstain, the
   `ABSTAIN_NOTHING_PROMOTABLE` reason code tallied apart from faults, the
   always-emitted yield line, and the fault/verdict split that decides
   whether `.last_insight` advances.

2. **Retire `rules-distill` and `rules-stocktake`** as LLM generators: CLI
   handlers, `core/rules_distill.py`, prompts `rules_distill.md` /
   `rules_distill_refine.md` / `stocktake_rules.md`, the
   `.last_rules_distill` marker. Keep `stocktake_merge_rules.md`
   (shared-core synthesis) as the prompt for family-to-rule promotion
   (Decision 7) and keep the deterministic `_check_rule_quality` so the
   rules layer retains a maintenance reading in the weekly packet (a
   `rules` section in `scripts/value_layer_due_check.py`: count, mtime,
   structural check — slice 2).

3. **Reduce `skill-stocktake`** to the ADR-0081 description audit plus the
   usage reading (report only): remove the grouping, merge and clean
   stages, their prompts (`stocktake_skills.md`, `stocktake_merge.md`,
   `stocktake_clean.md` and their system prompts), the `--stage` flag and
   the merge/clean staging producers. LLM calls per run go from
   ≈1 + G + 2N to N. The staging fields those producers were the only
   writers of go with them: `StageItem.sources` (delete-on-adopt of a
   merge's originals), `StageItem.action` (merge vs drop) and the per-item
   `command` override, along with `adopt-staged`'s handling of the matching
   sidecar keys. **Adoption becomes a write and nothing else** — the two
   delete primitives an attacker-writable sidecar could previously reach are
   gone rather than left producerless, and the Decision 5 exit arrives as an
   explicit operator argument instead.

4. **The novelty gate is unchanged in code and restated in purpose**: it is
   the ledger keeper (`logs/insight-staged.jsonl`) and a cheap fail-open
   pre-filter, not the coverage judge. Its expiry is named: the
   decision-agnostic known-theme inventory (397 entries on 08-21 against 57
   skills) grows monotonically and will re-break token-bounded chunking as
   it did on 2026-07-18.

5. **Reserve the exit (slice 2)**, built after slice 1 lands and gated by
   observation counts, not calendar weeks: retired skills move to
   `skills/.archive/` (never deleted; `remove-skill --reason` stays
   mandatory); `adopt-staged` gains `--archive-names FILE` as an explicit
   argument — never derived from reviewer output; the weekly packet gains a
   code-owned never-selected section listing **strict** candidates (zero
   selections in the whole selection history with ≥ 600 judged exposures —
   the floor is the smallest round number above the observed maximum
   first-selection latency of 569) for the human to archive, **dormant**
   skills (zero selections in the trailing 14 days but selected before) as
   a reading only, and alongside them the window's fail-open count and
   `full_skill_tokens` against NUM_CTX, because behaviour-neutrality holds
   for judged actions only; archived and superseding skills record
   `supersedes:` / `superseded_by:` in frontmatter; a read-only
   co-selection family script joins `scripts/`.

6. **Reserve the vocabulary (slice 3)**: the reviewer prompt's verdict
   grammar becomes `adopt` / `adopt-superseding <skill>` /
   `reject: covered-by <skill>` / `reject: sibling-of <candidate>` /
   `reject: vague`, with `reject: covered-by` the default when an older skill
   covers the theme (the older skill keeps its selection history) and
   `adopt-superseding` only with a stated reason; `build_decision_packet.py`
   verifies a 1:1 correspondence between review sections and staged items
   (reason code `INSIGHT_REVIEW_INCOMPLETE`) and the existence of every
   named store skill (a missing name is recorded as a reviewer
   hallucination), and verdicts remain proposals — store mutation happens
   only through explicit gate arguments. The new prompt is verified by
   offline replay on the 2026-08-21 batch before its first live run, and an
   offline retrieval-recall measurement over the past seven weeks'
   candidates and reviewer-named skills decides whether a code-prepared
   retrieval evidence bundle is built at all.

7. **Rule promotion takes form A′**: when a co-selection family's any-of
   selection rate is ≥ 0.75 over at least two disjoint windows of ≥ 500
   judged records (already true for the constraint family), the agent's
   own model (gemma) synthesizes the family's shared stance into
   Practice/Rationale form with `stocktake_merge_rules.md`, the result goes
   through the human gate, and the member skills **stay in the store** as
   situational procedures; members that stop being selected leave through
   the never-selected exit. The rules layer stays small.

8. **One variable at a time ([ADR-0056](./0056-retire-importance-llm-scoring.md))
   is measured in observation counts, not calendar weeks.** Every change
   pre-registers its expected effect and the minimum record count that can
   read it (≈ 80–95 judged selection records per day): behaviour-neutral
   deletions need none; archiving the three strict never-selected skills
   needs ≥ 80 judged records showing `catalog_count` 54, no archived name
   in `selected` or `rejected_names`, fail-open 0; a family-to-rule
   promotion needs ≥ 100 judged records showing member selections fall and
   `selected_count` p50 drop; a co-selection pair merge needs ≥ 100 judged
   records showing that pair's word-form hallucinations vanish; a newly
   adopted skill becomes a never-selected candidate only after 600 judged
   exposures. The only calendar-bound step is the Saturday unattended
   reviewer run, and slice 3 is verified offline before it.

## Review-when

- After the exit and the first family consolidations have accumulated ≥ 600
  judged records, the selector hallucination rate has not fallen from its
  18–20% band → the catalog-size hypothesis is wrong; revisit the
  selector/catalog design (family-level catalog, SameCapRisk-style family
  resolution at retrieval time) instead of further store hygiene.
- `fail_open_budget` appears in `insight-novelty.jsonl` → the known-theme
  inventory has outgrown chunking; the ledger role needs a
  retrieval-assisted redesign or the ledger needs pruning.
- The slice-3 existence check finds reviewer-named covering skills absent or
  wrong in ≥ 10% of rejections, or offline recall@5 of cosine+lexical
  retrieval against reviewer-named skills is ≥ 0.9 and a miss of the 08-22
  kind (variants of one theme adopted) recurs → build the code-prepared
  retrieval evidence bundle for the reviewer.
- A skill archived as strict never-selected is restored from `.archive/`
  more than once → the 600-exposure floor is too low; re-read it from the
  first-selection latency distribution.
- `rules/` exceeds about five files, or generation shows
  instruction-stacking symptoms after a promotion → stop promoting and
  revisit the layer.
- After slices 2–3, weekly candidate volume stays ≥ 40 with ≥ 80% of themes
  already in the ledger → consider moving `--weekly-insight` to monthly
  (one plist line, reversible) at the cost of 100–150-item batches.

## Alternatives Considered

### Keep the three consolidators and give them a cadence

(T-CONSOLIDATOR-CADENCE) Rejected — scheduling tools with measured defects
(20/48 coverage, axiom paraphrases, no retire path, 14/47 no-op rewrites)
makes the defects periodic.

### Patch `rules-distill`

Full coverage: pass existing rules and constitution into the prompt.
Rejected — the premise that an LLM distils rules from skill batches produced
only paraphrases of axioms and existing skills (8/8 rejected); more input is
more of the same.

### Build the retrieval-assisted evidence bundle for the reviewer now

Cosine + lexical top-k store bodies inlined. Left open — the reviewer's
coverage judgment already exists and the vocabulary captures it (architect
verdict); there is no observer for its false negatives yet (Codex
challenge), so the offline recall measurement in slice 3 decides.

### Embedding-threshold suppression of candidates

Rejected — ADR-0074's calibration found no separation between same-theme and
distinct-theme similarities on this corpus.

### Attestation (require cross-window recurrence before extraction)

Rejected — ADR-0074's window simulation matched 32 of 32 adjacent-window
clusters; in this corpus every theme recurs, so recurrence filters nothing.

### A catalog-capacity ceiling as a packet reading

Rejected — the 24 → 37 hallucination jump is confounded with the name
backfill (ADR-0081 amendment), and `report --skill-selection` already prints
the hallucination line.

### Union-merge at adoption

(`adopt-revising X` through `merge_group`) Rejected — the union merge is the
mechanism that produced a 10-trigger over-broad skill (ADR-0048) and
recovered only 2 of 5 dropped patterns fully (ADR-0046); Mem0 v3 abandoned
in-place reconciliation for the same reason. Supersede-and-archive keeps both
texts.

### Promote a representative skill as-is and archive its siblings

Rejected — the six constraint-family members carry distinct procedures;
co-selection shows add-on, not substitution; archiving them drops procedures
from injection.

### A human hand-writes the promoted rule

Rejected — the rules layer would carry the owner's words, leaving the
[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) observation
stance.

### A daily capsule or daily deterministic-structure layer upstream of insight

(2026-07-18 note) Not taken — a larger data-flow change with
[ADR-0060](./0060-per-episode-grounded-distill.md)'s flattening risk, and
not needed for the consolidator question; left open for the entry-volume
question.

### Fully automated adoption

Rejected, as in ADR-0085 alternative 3.

### A `disabled-candidate` state instead of archiving

(Codex alternative) Rejected — archiving is reversible and adds no state.

## Consequences

### Positive

- The weekly insight run loses 46 worth calls and the surprise pass; a
  `skill-stocktake` run drops from ≈115 LLM calls to ≈57 (description audit
  only). Ten prompt templates leave the loaded inventory (`insight_worth`,
  `rules_distill`, `rules_distill_refine`, `stocktake_rules`,
  `stocktake_skills`, `stocktake_merge`, `stocktake_clean` and the three
  stocktake system prompts); `stocktake_merge_rules.md` stays for
  promotion. The canonical count lives in `docs/CONFIGURATION.md`.
- The store gets its first exit (slice 2) whose behaviour-neutrality on
  judged actions is provable from the selection log, and a family
  structure readable from data the agent already writes.
- The reviewer's weekly coverage judgment becomes machine-readable and
  checkable (slice 3) instead of being discarded.
- Decisions advance on record counts; with ≈ 80–95 judged records a day,
  most gates read within one to two days, and the rule-promotion criterion
  is already met.

### Negative

- Until slice 2 lands, the store still has no exit — slice 1 alone removes
  machinery and shrinks nothing.
- Adopted-skill duplicate detection has no LLM stage any more; until the
  co-selection reading is used at the gate, the description audit is the
  only hygiene pass left.
- The rules layer has no generator; new rules arrive only through family
  promotion (Decision 7).
- ADR-0096's instrument is removed after a single production reading; its
  own pre-registration said one reading decides, and the three consistent
  readings are recorded above.
- `remove-skill` keeps deleting until slice 2 adds archiving; the 6
  deletions to date stay as deletions (content preserved in snapshots and
  `audit.jsonl` hashes).
- A sidecar written before this change and adopted after it loses its
  delete-on-adopt effect: `sources` and `action: drop` are now ignored, so
  a merge's originals survive beside the merged file and a drop item writes
  its text instead of unlinking the target. Staging was empty when this
  landed, so no such sidecar exists; the note is here because the failure
  would otherwise be silent.

### Neutral / Follow-ups

- [ADR-0016](./0016-insight-narrow-stocktake-broad.md)'s split "insight =
  narrow generator, stocktake = broad consolidator" ends: consolidation
  moves to the Saturday gate (co-selection reading + supersede-and-archive),
  not to a batch consolidator. A dated note goes on ADR-0016.
- ADR-0048 stages 2 and 3 (merge-time and clean-time trigger generalization)
  are retired; stage 1 (extraction prompt) stands. A dated note goes on
  ADR-0048.
- ADR-0096 Decisions 2 and 10–12 are retired by its own fallback; Decisions
  1 and 4–9 stand (the audit writer in 9 goes with the judge it recorded).
  A dated note goes on ADR-0096.
- The ADR-0046 amendment's summary-evidence grouping is retired with the
  grouping stage. A dated note goes on ADR-0046.
- Ledger: `T-CONSOLIDATOR-REDESIGN` → `decided`; `T-CONSOLIDATOR-CADENCE` →
  `dropped`; `T-SKILL-PROMOTE` → `candidate` in form A′.
- `docs/CODEMAPS/architecture.md` Data Flow and `docs/CONFIGURATION.md` are
  updated in the same change (freshness convention in CLAUDE.md).

## Related

- [ADR-0016](./0016-insight-narrow-stocktake-broad.md) — Insight as Narrow
  Generator, Stocktake as Broad Consolidator
- [ADR-0046](./0046-stocktake-llm-grouping-over-embedding-clustering.md) —
  Stocktake Duplicate Detection
- [ADR-0048](./0048-trigger-altitude-skill-lifecycle.md) — Trigger-Altitude
  for Skill Lifecycle
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — Epistemic
  Taxonomy and Approval Lineage
- [ADR-0056](./0056-retire-importance-llm-scoring.md) — Retire the
  Distill-Time Importance LLM Rating
- [ADR-0074](./0074-weekly-staged-insight.md) — Weekly Staged Insight
- [ADR-0076](./0076-skill-selection-shadow-instrument.md) — Skill-Selection
  Shadow Instrument
- [ADR-0081](./0081-skill-selection-two-pass-injection-enforcement.md) —
  Skill-Selection Two-Pass Injection Enforcement
- [ADR-0085](./0085-unattended-weekly-fix-chain-single-saturday-gate.md) —
  Unattended Weekly Fix Chain with a Single Saturday Gate
- [ADR-0091](./0091-value-layer-cadence-in-the-weekly-chain.md) —
  Value-Layer Cadence in the Weekly Chain
- [ADR-0096](./0096-insight-promotion-worth-abstain.md) — Promotion-Worth
  Abstain at Insight Time
