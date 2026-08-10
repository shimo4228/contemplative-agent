# Runbook: Constitution Amendment

Procedure for every full-constitution amendment. The IPD two-arm bench is
**required** before approval ([ADR-0090](../adr/0090-ipd-two-arm-instrument-for-constitution-amendments.md));
skipping it needs an explicit owner decision recorded in the ADR trail.

## Preconditions

- No other value-layer change in flight (ADR-0056: one variable at a time).
- A window clear of the JST 0/6/12/18 schedule sessions long enough for
  ~2 h of bench time (the wrapper also guards this itself).
- The calibration contract holds: `gemma4:e4b`, n=10, α ∈ {0.0, 0.5, 1.0}.
  If the production model or n has changed since the last null pair
  (2026-08-06, floor ±0.13), run a new null pair first and update the
  contract in ADR-0090 evidence.

## Steps

0. **Shadow readings** (third gate material,
   [ADR-0092](../adr/0092-shadow-constitution-instrument.md)): before
   staging, read the accumulated `logs/constitution-shadow.jsonl` series —
   ideally ≥ 2 `contemplative-agent shadow-constitution` runs taken since
   the last amendment (schedule-window rules above apply to each run; one
   run is wiring proof, not evidence). The divergent clauses and the free
   section inventory are candidate material for the amendment; the cosine
   is readable only against the reserved anchors (ADR-0092 Decision 5).
   The shadow text itself is NEVER an amendment candidate — it has no
   approval lineage; adoption goes only through the staged amend path
   below.
1. **Stage**: `contemplative-agent amend-constitution --stage`
   (non-TTY safe; refuses if staging already holds an unreviewed batch).
2. **Bench**: `scripts/ipd-two-arm.sh [OUTDIR]` — verifies arm A against
   the audit log's last-approved hash, runs both arms under the schedule
   guard, and emits `report.md` + `provenance.txt`.
3. **Approve**: the owner reads the constitution diff, the reasoning
   trace, and `report.md`. The instrument informs; it does not gate.
4. **Adopt**: `contemplative-agent adopt-staged -y`.
   **Known defect (T-ADOPT-OVERWRITE-TARGETS)**: the collision guard may
   write `contemplative-axioms-2.md` beside the old file instead of
   replacing it. The runtime loader concatenates every `*.md` in the
   constitution dir, so this state injects old and new simultaneously.
5. **Verify single-file state** (mandatory until that defect is fixed):

   ```bash
   ls ~/.config/moltbook/constitution/*.md   # exactly one file
   shasum -a 256 ~/.config/moltbook/constitution/contemplative-axioms.md
   # must match the staged/approved hash in logs/audit.jsonl
   ```

   If a `-2.md` exists: archive the old text to the ADR's evidence dir,
   move the new text into place, re-verify the hash.
6. **Record**: fill the ADR amendment record (readings, approval outcome,
   adoption date — it becomes the before/after reference point for weekly
   reports), copy the run artifacts to `docs/evidence/adr-XXXX/`, update
   the task ledger, commit.

## Optional exploratory face

The AILuminate safety two-arm (T-CONST-SAFETY-FACE) may be attached as
additional material. It is uncalibrated — label its numbers observation,
not signal — and it sends both constitution texts to a third-party API,
which the default local-only IPD face does not.
