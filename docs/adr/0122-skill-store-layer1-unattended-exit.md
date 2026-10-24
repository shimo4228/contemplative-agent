# ADR-0122: The Skill Store's Layer-1 Exit Runs Unattended — Deterministic, Reversible, Reported, With a Right of Return

## Status

accepted — partially-supersedes ADR-0105

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session (roadmap P2-07.1 / P2-07.2 / P2-07.5)
decided-by: owner (D-P2-07-1 = A, D-P2-07-2 = B; both "as recommended", 2026-10-24)
date: 2026-10-24

## Layer

mechanism

## Context

[RFC-0048](../../rfcs/0048-skill-store-self-maintenance.md) splits the skill
store's exit (retirement) into three layers. Layer 1 is the one whose verdict
is fully deterministic: a skill that was never selected in its whole history
and was judged-exposed at least 600 times (ADR-0097 D5, the never-selected
*strict* set). Today the Saturday gate reads the week's candidate file,
explains it, and a person approves `adopt-staged --archive-names`. In the two
readings so far the person's ruling matched the machine's candidate both
times, while the entry side of the loop already runs without a person
(ADR-0111). The north star (ADR-0080, 2026-08-26 addendum) counts a loop that
still needs the owner and Claude Code every week as unfinished.

Two earlier decisions stand in the way, and the roadmap flagged both:

- ADR-0080's "Not gate dissolution" paragraph: the human word at the gate is
  the anchor of the program's attribution practice (ADR-0050). It does not
  name reversibility as an exception condition.
- ADR-0105: "Nothing in the unattended chain touches the store."

Reversibility alone is therefore not a sufficient reason to skip the gate, and
the unattended move must not hide inside the vocabulary of a person's command:
`direct-archive-auto` in `audit.jsonl` is `remove-skill --yes`, a human's CLI.

## Decision

**D1. Layer 1 may run unattended, under three conditions that are all
required.** The owner chose A (D-P2-07-1); the exception text for the ADR-0080
addendum (2026-11) is in `docs/plans/p2-07-layer1-boundary-draft.md` and is
carried by the addendum PR, not by an edit to ADR-0080 here.

1. *Deterministic.* The verdict is code with no model in it: never-selected
   strict (zero selections ever, judged exposure >= 600). The floor is the
   value ADR-0097 fixed; the chain passes it, it is not tunable at run time.
   An LLM verdict never enters layer 1 (RFC-0048 Drawbacks; ADR-0105).
2. *Reversible and with a right of return.* The move is to `skills/.archive/`
   (ADR-0097 D5), and a person restores with `restore-skill` (D4).
3. *Reported.* The names and the count reach the Saturday gate in the same
   week, under an audit source no human command writes (D2).

The reason is not "it can be undone". A skill that was never selected was
never injected into a generation, so no published sentence is attributable to
it and there is no attribution for the human word to anchor. That, plus 2 and
3, is why this is an exception and not a precedent: layer 2 (judgment needed:
confusion pairs, duplicates) and every value-layer *addition* keep the human
word at the gate.

**D2. A new audit source, never a reused one.** `AuditSource` gains
`archive-l1-unattended` (the unattended move) and `direct-restore` (the
return). `direct-archive-auto` is not used by the chain.

**D3. Execution position (design; the stage lands at the 2027-02-27 gate).**
A new weekly stage next to 7b/7c calls the existing archive primitive with
the 7b strict list and the new source. Constraints fixed now: it runs only
after `scripts/layer1_exit_guard.py --require-live` exits 0 (D5); stage 7c's
candidate file must not list a name layer 1 already moved this run; a failed
archive is an audit row with a reason code, never silent (ADR-0075). The
production behaviour change is the stage itself and it is deliberately **not**
in this change, and it does not land until the ADR-0080 addendum (2026-11)
carrying text A has merged: the chain still never calls `--archive-names`, pinned by
`tests/test_layer1_exit_guard.py` (a call is allowed only on a line carrying
`archive-l1-unattended`).

**D4. `restore-skill` ships now.** `contemplative-agent restore-skill NAME
--reason TEXT [--dry-run]` moves `skills/.archive/NAME.md` back, refuses
(with a `rejected` audit row and a reason code) when the archive copy is
missing, is a symlink, or a live skill of that name exists, never overwrites,
and writes one `direct-restore` row. `edit-value` is not built.

**D5. The falsifier is code.** `scripts/layer1_exit_guard.py` reads
`audit.jsonl` and reports `skills_archived_l1`, `skills_archived_l2` and
`restored` per week (the `gate_record` columns, and the restore column of the
P2-01.5 table). RFC-0048's pre-registered stop — two layer-1 archives each
restored within 28 days — sets `halted: true`; `--require-live` turns it into
exit 3, so the stage skips and says why. Re-enabling is a record, never
automatic: the owner appends one row `{"ts", "decision": "approved", "source":
"layer1-reenable", "reason"}` to `logs/audit.jsonl` *(2026-10-24: through
`scripts/layer1_reenable.py`, not by hand — see the addendum)*; layer-1 archives stamped
before the latest such row stop counting toward `halted`. Rows after the
reading's as-of day are ignored, and the weekly window is the 7 calendar days
ending on the as-of day.

**D6. "Saturated" gets an operational definition (D-P2-07-2 = B).**
`scripts/store_state.py` classifies four weeks of three axes into `saturated`
/ `equilibrium` / `growing` and `value_layer_due_check.py --store-axes FILE`
emits it as `store_state` in `value-layer-{end}.json`. Axes: entry =
staged / clusters; exit = archive candidates / store; hub = the hub skill's
selection share. "Below a threshold" means the whole 95% Wilson interval
(`scripts/_stats.py`) is below it; an axis with fewer than 10 pooled trials is
count-only and the state is `undetermined` with a reason. Pre-registered
thresholds (a change is a dated amendment here, never an in-place edit):
saturated = entry upper < 0.05 and exit upper < 0.05 and hub upper >= 0.20;
growing = entry lower >= 0.10 and exit lower < 0.10; equilibrium otherwise.
These sit consistently with ADR-0111's "below ~40 skills" Review-when: the
exit axis denominator is the store size. Writing the weekly axes file from the
chain's existing outputs is part of the 2027-02-27 implementation; until then
the key is simply absent (absent, not null: "not read", not "read, empty").

**Not decided here.** The `gate_record` column names are the harness's; this
repo only produces the numbers (D5). The measurement question "does injection
change the comment" is RFC-0054's, and the design point that would shrink the
store *before* measurement is still not started (RFC-0048 Depends).

## Addendum (2026-10-24): the re-enable row has a writer

The hand-appended row of D5 had a source outside the audit schema's enum and lacked the schema's required `command` / `content_hash`, and a hand-written line breaks the `prev` hash chain (ADR-0012, 2026-10-24 addendum). The owner decided (2026-10-24) to add `layer1-reenable` to `AuditSource` and the schema and stop writing the row by hand. `scripts/layer1_reenable.py --home … --approver … --reason … [--write]` prints the guard's current `halted`, and with `--write` appends the row through `cli/approval.py::log_layer1_reenable` (`command` and `source` `layer1-reenable`, `path` `skills`, `content_hash` of the reason, `channel` headless, the approver, the `prev` link). The guard's reading rule is unchanged.

## Review-when

- Two layer-1 archives are restored within 28 days (the falsifier): layer 1
  stops and all candidates return to layer 2.
- The 2027-02-27 gate reads the first `store_state` weeks and amends or keeps
  the thresholds in D6.
- A selector or injection change makes "never selected" stop meaning "never
  injected" (the attribution argument in D1 would no longer hold).
- Layer 1 retires fewer than one skill in 26 weeks: remove the stage, keep
  `restore-skill`.

### Consumption plan

- `layer1_exit_guard.py`: (a) the Saturday gate reads `halted` beside Step 6c
  and the unattended stage reads it before each call; (b) one reading a week
  decides one thing, halted or not; (c) removed when layer 1 is retired or has
  run 26 weeks with zero restores (the count folds into the census).
- `store_state`: (a) the owner, weekly, beside Step 6c (never-selected), in
  the RFC-0048 / RFC-0042 review-when reading; (b) the 2027-02-27 gate adopts
  or amends the three axes once, then a saturated <-> growing transition is
  read against RFC-0048's design points; (c) removed when entry is stopped
  (D-P0-01-1 B) and layer 1 has stopped retiring, i.e. the store is fixed.

## Alternatives Considered

- **B: candidates only, a person runs `--archive-names`.** Keeps the
  boundary untouched and costs one command a week; rejected by the owner
  because the north-star condition (the loop turning without the owner) stays
  unmet on the exit side.
- **Reuse `direct-archive-auto`.** Rejected: it mixes a person's `--yes` and
  the machine in one source, which is the attribution loss ADR-0080 warns of.
- **Let the model judge more of the exit unattended.** Rejected by ADR-0105
  and RFC-0048 (false-pass bias of the small judge); not re-proposed.
- **A single scalar for saturation.** Rejected: the north star forbids
  collapsing the metabolism axes to one number; the three are reported apart.

## Consequences

- The chain gains one exit that can move files without a person present; the
  guard, the distinct source and `restore-skill` are what keep a person able
  to answer for it.
- ADR-0105's sentence "Nothing in the unattended chain touches the store" is
  retired in part: from the 2027-02-27 stage it holds except for the layer-1
  stage. Until that stage ships, production behaviour is unchanged.
- The freeze stop-list (P1-01.3) carries a dated row for the stage.
- AAP ADR-0005's `--auto` prohibition needs a dated note saying layer 1 is the
  one exception (P3-06.7); the AAP correspondence table is confirmed there.

## References

- [RFC-0048](../../rfcs/0048-skill-store-self-maintenance.md) — the three layers and the falsifier
- `ADR-0105` (`0105-skill-store-exit-confusion-pairs.md`) — partially superseded: the unattended-chain sentence
- `ADR-0097` (`0097-consolidator-dissolution-and-skill-store-exit.md`) — D5 archive, the 600 floor, Review-when
- `ADR-0080` (`0080-north-star-layered-end-state.md`) — "Not gate dissolution"; the addendum text is in `docs/plans/p2-07-layer1-boundary-draft.md`
- `ADR-0101` — consumption plans; `ADR-0075` — audit-by-default; `ADR-0111` — the entrance
