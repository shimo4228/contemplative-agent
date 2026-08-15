# ADR-0082: Retire the `observed` Epistemic Key — Delete the Dead Field, Not the Warning About It

## Status

accepted — partially-supersedes [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md)

supersedes [ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) in part
(the `epistemic_counts` schema and the `external_reply` → `observed` arm of the
read-time derivation). ADR-0050's lineage plumbing, no-write-back, and
never-persisted decisions remain in effect.

## Date

2026-07-25

## Context

[ADR-0050](./0050-epistemic-taxonomy-and-approval-lineage.md) introduced a
read-time epistemic derivation: a pattern row's `provenance.source_type` maps to
an epistemic kind, and `epistemic_counts_for()` tallies those kinds into
`{observed, generated, unknown}`. The tally rides along with `source_ids` into
`audit.jsonl` and `.staged/*.meta.json` as approval lineage.

[ADR-0060](./0060-per-episode-grounded-distill.md) later restricted distillation
to `activity` records, all of which map to `self` → `self_reflection` →
`generated`. The only producer of `external_reply` — `_derive_source_type()` in
`episode_render.py`, which requires an `interaction`/`received` record — became
unreachable from the live ingestion path. Since then `observed` has been
**structurally zero**.

This was noticed and documented. [ADR-0071](./0071-read-only-pattern-composition-instruments.md)'s
M2 review (2026-06-27) recorded that `observed == 0` reads as "no external
grounding" when it means nothing of the sort — external content does enter
distillation, as grounding text *inside* the rich render, and was never counted
by this tally. Warnings were added to the docstrings of `epistemic_counts_for()`
and `_log_approval()`. [ADR-0072](./0072-echo-chamber-interventions.md) deleted
the grounding *instrument* that read this constant, but deliberately kept
`epistemic_counts_for()` itself — the repair was deferred under signal-first
(nothing downstream was consuming the reading, so quantifying it changed no
action).

The deferral held for four weeks and then failed in the way deferred repairs do.
On 2026-07-25, reviewing the 78 skills staged by the weekly `insight` run, an
agent read `epistemic_counts` from the staged `meta.json` files, aggregated
`observed=0, generated=324` across all 78, and concluded that every staged skill
was pure echo with no external grounding — the exact misreading M2 predicted.
The docstring warnings did not prevent it, because **nothing guarantees the
warning is read before the value is**. The value is in the data file; the
warning is in the code that produced it.

Aggregated over the full audit history (405 records carrying the tally):

| command | observed | generated | unknown |
|---|---:|---:|---:|
| `insight` | **0** | 1,618 | 0 |
| `distill-identity` | **0** | 231 | **119** |

`unknown` is genuinely populated (rows whose provenance defaults to
`{"source_type": "unknown"}`, plus pre-ADR-0021 legacy rows) and stays.
`observed` has never been non-zero in production.

This is the general case named in the harness rule "documented invariants belong
in gates": a structural invariant that lives only in prose is enforced only
probabilistically. Here the invariant is not even enforceable — the field is
dead, and the honest fix is to stop emitting it rather than to keep annotating
it.

## Decision

**1. Retire the `observed` kind entirely, arm included.** Remove
`"external_reply": "observed"` from `_EPISTEMIC_KIND_BY_SOURCE` and drop
`observed` from the dict `epistemic_counts_for()` initializes. The emitted shape
becomes `{generated, unknown}`.

Removing the arm rather than only the key is deliberate: a mapping that no live
path reaches is a standing invitation to re-investigate why unreachable code
exists. `epistemic_kind_for()` looks up with `.get()`, so an `external_reply`
row — should one ever appear — degrades to `None` → `unknown` rather than
raising. If external ingestion returns, the taxonomy gets designed for it then,
against the ingestion path that actually exists.

**2. Keep `_derive_source_type()`'s `external_reply` return value.** That string
is a provenance record, a different layer from the epistemic tally. Retiring it
is a separate question requiring a provenance-side stocktake, and is explicitly
out of scope here.

**3. Do not rewrite history.** `audit.jsonl` is an append-only audit log and
`.staged/*.meta.json` files are pending approval artifacts; both keep their
three-key records. `adopt.py` passes `epistemic_counts` through verbatim, so
files staged before this ADR — including the 78 from 2026-07-25 — remain
adoptable unchanged.

## Alternatives Considered

**Keep the key, strengthen the warning** (e.g. an adjacent
`"observed_note": "structurally zero since ADR-0060"` field). Rejected: this is
more scaffolding around a dead value, and it concedes the point — if the value
needs a disclaimer shipped next to it in the data, the value is not carrying
information. It also grows the record shape to defend a field that carries none.

**Retire `epistemic_counts` wholesale.** Considered seriously, since `insight`
emits `generated`-only and `distill-identity` emits a two-value split, so the
tally is close to a constant per command. Rejected for now: `unknown` does vary
with real input (119 records), the field is ADR-0050's approval-lineage
contract, and ADR-0072 already made an explicit decision to keep
`epistemic_counts_for()` when it deleted the instrument. Overturning that
deserves its own evidence, not a rider on this change.

**Leave it alone (continue the signal-first deferral).** Rejected: the deferral
was justified while nothing consumed the reading, but the misreading incident is
itself the signal. A field that costs one wrong conclusion per reader is not
zero-cost.

## Consequences

**The misreading becomes structurally impossible.** No `observed` key means no
`observed=0` to over-interpret. This is enforcement by absence rather than by
documentation — the same shape as the project's `security by absence` stance.

**`audit.jsonl` has a schema seam.** Records written before 2026-07-25 carry
three keys; later ones carry two. This is accepted rather than migrated, for
audit integrity. Offline analysis must read with `.get(key, 0)` rather than
assume a fixed key set; the docstrings of `epistemic_counts_for()` and
`_log_approval()` say so. `scripts/log_anomaly_sweep.py` — the only tool reading
`audit.jsonl` — matches lines by regex and never accesses this field, so it is
unaffected.

**Production read sites need no change.** Nothing in `src/` indexes
`["observed"]` or assumes the dict's arity; every consumer copies or serializes
it as an opaque `dict[str, int]` (`cli/staging.py`, `cli/adopt.py`,
`cli/approval.py`, `cli/memory_cmds.py`).

**A regression guard replaces the deleted arm.**
`test_epistemic_kind_for` now asserts `external_reply → None` and
`test_observed_key_is_retired` asserts the key's absence from the emitted shape,
so restoring the arm has to be a deliberate act rather than a silent drift.
`test_adopt_passes_through_pre_adr0082_meta_verbatim` pins the non-retroactive
guarantee.

**The reading habit behind the incident is untouched.** The agent read a value
from a data file without reading the code that produced it. Retiring this field
removes one instance; it does not remove the habit. That is left as an open
observation rather than a mechanism, since no cheap deterministic gate for it is
apparent.
