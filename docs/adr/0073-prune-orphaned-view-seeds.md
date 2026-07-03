# ADR-0073: Prune the Five Orphaned View Seeds

## Status

accepted

## Date

2026-07-03

## Context

[ADR-0019](./0019-discrete-categories-to-embedding-views.md) introduced seed-text
views as the deterministic query layer. Seven seeds shipped; the mechanisms that
consumed five of them were retired long ago — the insight batch axes
(`communication` / `reasoning` / `social` / `technical`) by
[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md), and the ingest
noise gate (`noise`) by
[ADR-0060](./0060-per-episode-grounded-distill.md). Since then those five files
have been orphaned definitions: loaded by the registry, queried by nothing.

[ADR-0071](./0071-read-only-pattern-composition-instruments.md) deliberately
declined to measure them (a distribution over an unconsumed seed measures seed
staleness, not corpus structure), and
[ADR-0072](./0072-echo-chamber-interventions.md) deferred their disposition until
the corpus-grown seed route had evidence. Later the same day the operator
resolved the deferral: delete them now. The keep-value is near zero — the seeds
were authored in 2026-03 against a corpus that no longer exists, and any future
view would be re-derived from current corpus evidence, not from these files —
while keeping them misleads readers into thinking seven classification axes
exist.

## Decision

1. **Delete the five orphaned seeds from both locations.** Repo templates
   (`config/views/{communication,noise,reasoning,social,technical}.md`) removed
   via git; live copies moved to
   `~/.config/moltbook/views.bak.20260703-orphan-prune/` (soft-delete, following
   the seed-backup precedent). `config/views/` and the live views directory now
   ship exactly the two consumed views: `self_reflection` and `constitutional`.
2. **Record the standing policy the deletion encodes.** A view exists only
   together with a consumer that queries it — a consumer-less view is dead by
   definition. Future views are *grown*: promoted from stable corpus clusters
   with their consumer wired in the same change, the route whose minimal version
   (the exemplar appendix) ADR-0072 shipped and validated. Views are not
   pre-authored against anticipated categories.
3. **Sweep the references.** The orphan mentions in `distill.py`,
   `view_metrics.py`, `docs/CODEMAPS/architecture.md`, and
   `docs/CODEMAPS/core-modules.md` now point at this ADR. `docs/CONFIGURATION.md`'s
   view-seed section was rewritten — it still described the pre-ADR-0031/0060
   world ("episodes are classified into semantic categories"; patterns "tagged"
   with views) rather than read-time pattern ranking.
4. **Fix the stale facing-doc counts caught by this sweep.** README (en/ja),
   `docs/CONFIGURATION.md`, `llms.txt`, and `llms-full.txt` said "32 loaded
   pipeline prompts, 7 view seeds"; the prompt count had already gone stale when
   ADR-0072 deleted the two batch prompts. Corrected to **30 loaded prompts / 2
   view seeds** everywhere.

## Alternatives Considered

### Keep the five seeds as dormant templates

Rejected. They cost little at runtime but actively mislead: documentation and
readers treat shipped seeds as live classification axes. Their content encodes a
March 2026 view of a corpus that has since been re-embedded, re-registered, and
grown 5×; any revival would start from current corpus evidence anyway.

### Hand-author replacement seeds now

Rejected twice over: authored-prose seeds are the May 2026 three-failure pattern
(ADR-0072 Context), and a redesigned seed without a consumer is still dead
config — the same signal-first violation, one step removed.

### Wait out the ADR-0072 observation window before pruning

The original deferral. Rejected by operator decision: the observation validates
the *replacement* route (corpus-grown promotion), not the keep-value of the old
files, which is independent and near zero. Git history and the live backup
restore them in one step if that judgment is ever wrong.

## Consequences

- `init` now ships 2 views instead of 7; pivot snapshots capture 2 centroids.
  Existing snapshots that captured 7 remain valid historical records.
- No behavior change: nothing queried the five seeds — consumers
  (`distill-identity`, `amend-constitution`), instruments (`view_metrics`), and
  the packaged-views test (which globs rather than counts) are all unaffected.
  Full suite, ruff, and pyright stay green.
- ADR-0071's "five orphaned views deliberately unmeasured" note and ADR-0072's
  "orphan-view disposition deferred" line become historical; this ADR closes
  that deferral.
- Adding a view now has a documented bar (`docs/CONFIGURATION.md`): wire a
  consumer in the same change, and grow the seed from corpus exemplars rather
  than authoring prose.
- Rollback: `git revert` (repo) plus restoring
  `~/.config/moltbook/views.bak.20260703-orphan-prune/` (live).

## References

- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — the views layer
- [ADR-0031](./0031-classification-as-query.md) — classification is a query;
  nothing is tagged
- [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) — retired the
  insight batch axes
- [ADR-0060](./0060-per-episode-grounded-distill.md) — retired the ingest noise
  gate
- [ADR-0071](./0071-read-only-pattern-composition-instruments.md) — declined to
  measure unconsumed seeds
- [ADR-0072](./0072-echo-chamber-interventions.md) — deferred this disposition;
  shipped the corpus-grown seed route this ADR adopts as the replacement policy
