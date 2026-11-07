---
name: measurement-discipline
description: "Measurement traps measured in this repo's instruments and gates. Use when placing a guard or warning field, switching a gate on, freezing labels or a ratchet, or when an automated gate rejects outputs you trust."
user-invocable: true
origin: shimo4228
edition: ca-specific
---

# Measurement Discipline

Four traps this repo has hit with its own instruments and gates. Each comes with the reading it was
measured on. General statistics (how many runs a claim needs, CI half-widths) is ordinary practice
and is not repeated here.

## 1. A guard firing 0% or 100% of the time is a design error

When you place a suspicion field, a warning or a check, measure its firing rate on real data. A
guard that never fires is read as "checked, no problem" — worse than no guard — and one that always
fires gets skipped. With no data to calibrate it, output the raw reading instead of a guard.
(Measured: readers aggregated an `observed` field that stayed 0 and drew the opposite conclusion; retiring that instrument is `read-only-instruments`.)

## 2. Switch reversible changes first, then observe

A change goes enforce-first when it only alters which already-permitted action is taken, its error
direction is on the shrinking side (fewer outward effects; misses can be picked up later), and
removing a setting reverts it. Switch over, run the old path alongside on the same rows, record both
on each row, and decide keep / kill on the day the pre-registered n is reached. The kill switch is
the absence of the setting. A waiting stage that only observes is for changes whose error direction
expands, that change the form of what goes out, that widen the I/O surface, or that cannot be
reverted — design it with `shadow-mode-validation`. Paired rows compare verdicts on the same input only — side effects already taken change
the later input set. Compare the error direction rather than declaring the change reversible.
(Measured 2026-09-26, relevance gate: would-be gate rate 0.22–0.39 vs live 0.58, shrinking side.)

## 3. Buy expensive judgments once; make repeated measurement deterministic and $0

Freeze ceiling-model or human labels once, in the main tree (deleting a worktree has lost row data),
and run later measurement with cheap scorers (temperature 0, logprobs, golden comparison) so the
metric runs on every PR and acts as a ratchet. Measure reproducibility: run the same set twice, take
the run-to-run difference as the noise floor, and place the ratchet line and any threshold outside
it (temperature-0 logprobs gave argmax agreement 0.913 and max |Δp| 0.26 run to run — gemma4:e4b,
2026-09-26). Pin the judgment's inputs (prompt, model, the value layer it references) in a manifest
next to the labels, and expire the labels when an input changes (`evals/` + `check_staleness.py`),
so a legitimate input change is read as staleness, not regression.

## 4. Before fitting outputs to a gate, test the gate against trusted labels

When an automatic gate (an LLM or judge model plus a threshold) rejects outputs a trusted judgment
passes, measure the gate's discriminative power before reshaping outputs to pass it. Collect judged
outputs with both passes and fails, replay the gate with production's input assembly, and save the
raw scores. Read the acceptance rate on each side, the accepted set's precision against the overall
pass rate, and the AUROC. A gate whose accepted-set precision does not beat the overall pass rate is
noise. Compare candidate thresholds and wordings offline on the saved scores. When none beats chance,
take the check out of gating, keep its score as a label, and give the property to a trusted
mechanism (the prompt, a self-check, a separate judgment). For a gate placed against a specific
failure, confirm it catches inputs synthesized with that failure.
(Measured 2026-10-01: a claim-fidelity gate accepted 24 of 120 passes and 10 of 31 fails; precision
0.71 under the overall 0.79, AUROC 0.42–0.68; synthesized subject swaps scored 0.46–0.54 under a 0.6
threshold.)

## How to use

Name the one trap that applies and ask with it ("trap 1 — on what data did you calibrate this
guard's firing rate?").

## Expiry conditions

- Delete a trap when the measurement it came from is refuted
- Retire the skill when design reviews raise these questions without it
