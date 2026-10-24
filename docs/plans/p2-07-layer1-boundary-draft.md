# P2-07.5 — ADR-0080 addendum (2026-11) draft: layer 1 and "Not gate dissolution"

Parked here on purpose. The addendum itself is P1-03.8's single PR (with P1-01 and
P2-01 paragraphs); this file is the paragraph that PR carries for layer 1. Do not edit
ADR-0080 from the P2-07 branch.

Owner decision on record: D-P2-07-1 = **A** (owner, 2026-10-24). Text A below is the one
to merge; text B is kept only so the record shows what was weighed. The design that
follows from A is [ADR-0122](../adr/0122-skill-store-layer1-unattended-exit.md).

## A — adopted (for the addendum, `## Amendment (2026-11)` of ADR-0080)

> **Layer 1 of the skill store's exit is an exception to "Not gate dissolution", on
> three conditions and no others.** The human word at the gate stays the anchor of the
> attribution practice (ADR-0050); reversibility alone is not a reason to skip it. What
> is skipped is narrower: retiring a skill that was never selected in its whole history
> and was judged-exposed at least 600 times, by a rule that is code with no model in it.
> Such a skill was never injected into a generation, so no published sentence is
> attributable to it and there is no attribution for the human word to anchor. The
> exception holds only while (1) the verdict is deterministic, (2) the move is
> reversible and a person keeps a right of return (`restore-skill`), and (3) the names
> and count reach the Saturday gate in the same week under an audit source no human
> command writes (`archive-l1-unattended`). It stops itself when two layer-1 archives
> are restored within 28 days. Every judgment-requiring exit (layer 2) and every
> value-layer addition keeps the human word at the gate. ADR-0105's "Nothing in the
> unattended chain touches the store" is partially superseded by ADR-0122 accordingly.

CLAUDE.md §北極星 sync (same PR as the addendum, per the freshness rule): in the
機構層 bullet, after the sentence on the human approval gates remaining as authority,
add: 「出口の層 1（決定論・可逆・事後報告の archive）だけは無人で動く例外（ADR-0122）。
承認ゲートの溶解ではなく、人間の言葉が錨になる対象（価値層への追加と読みの要る退役）
は変わらない」.

## B — not adopted (for the record)

> **Layer 1 stays with the human word.** The chain lists the strict never-selected
> candidates and explains them with numbers only; a person runs
> `adopt-staged --archive-names`. Reversibility makes the step cheap, not optional.

## Guard-test sketch (both texts)

- Under B: `weekly-pipeline.sh` contains no `--archive-names` call at all.
- Under A (adopted): a call is allowed only on a logical line (continuations joined)
  that carries `archive-l1-unattended`. This is `tests/test_layer1_exit_guard.py::
  test_the_chain_calls_archive_names_only_with_the_layer1_source`; today the chain has
  no call, so it passes vacuously and constrains the stage that lands at the
  2027-02-27 gate.
- The 2027-02-27 stage also runs `layer1_exit_guard.py --require-live` first; exit 3
  (halted) skips the stage with an audit reason.

## Open items for the merger

- `gate_record` (category=roadmap) needs the owner's A on one line; the harness
  writes it, not this repo.
- AAP ADR-0005 dated note (layer 1 is the one `--auto` exception) is P3-06.7; the AAP
  correspondence table check is to be written in the PR description of whichever PR
  revises ADR-0105 / ADR-0122 (CLAUDE.md freshness rule).
- Freeze stop-list (P1-01.3): add a dated row for the layer-1 stage (needs
  D-P1-01-1 additional step B).
