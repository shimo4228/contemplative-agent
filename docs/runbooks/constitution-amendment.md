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
  (2026-08-06), run a new null pair first and update the contract in
  ADR-0090 evidence. The noise rule is the cell-wise SE (|z| > 2, ADR-0090
  Amendment 2026-10-24); the old single ±0.13 is a printed reference.
- Null pairs for validating that rule (two more, `scripts/ipd-two-arm.sh
  --files T T`, ~2 h per arm) are still to be read. If they have not been
  read when this amendment's bench starts, record the amendment on the
  recording-only bench: attach the report's SE, z and Δ together to the
  record and do not use the reading to say the amendment is good or bad.
- The rules checkout (`../contemplative-agent-rules`) is at tag `v0.2.0`
  (`BENCH_REF`; ADR-0090 addendum 2026-10-24). The wrapper warns otherwise and
  records `git describe` in `provenance.txt`.

## When the gate is due

`pipeline/value-layer/value-layer-*.json` carries `constitution.due`
(interval 83 days from the last adoption, ADR-0091). In a week where it is
`true`, the Saturday gate does not amend in that session: it schedules the
amendment gate for the following Saturday and records one line in
`gate_record`. No RFC is filed automatically.

**2026-10-31 gate:** D-P0-07-1 = B by default (owner, 2026-10-24): the gate reads and does not launch an amendment. A (launch) only if the shadow series (ADR-0092, at least 4 points) and the pre-registration (RFC-0055) are both complete by 10-31. D-P0-07-2 (wiring / manual / retire) stays open until the 10-31 data.

## Steps

Read every result against the preregistered sentences, floors and the
limit rows in [`docs/evidence/research-questions.md`](../evidence/research-questions.md)
(Q1) — they were fixed before the reading, so do not adjust them after it.

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
   Also read the **referent inventory**
   ([docs/evidence/adr-0092/referent-inventory.md](../evidence/adr-0092/referent-inventory.md)):
   count the nouns each clause governs in four categories (directives,
   beliefs/goals, self-other, computational structures) and the four ADR-0005
   collision phrases, for the live text and the latest shadow runs. Read-only;
   no constitution text is touched.
1. **Stage**: `contemplative-agent amend-constitution --stage`
   (non-TTY safe; refuses if staging already holds an unreviewed batch).
1a. **Record the prediction before the bench runs**: in the Q1 section of
   [`research-questions.md`](../evidence/research-questions.md) write the
   changed clause(s) and the predicted direction and cell(s) of the IPD
   reading (or "no IPD prediction"), and date it. An amendment counts as
   *readable* (for P1/P2) only if its ADR-0090 two-arm reading completed
   under the calibration contract above. A shadow cosine taken across the
   amendment is gate material, not a P1/P2 reading (the live text changed).
2. **Bench**: `scripts/ipd-two-arm.sh [OUTDIR]` — verifies arm A against
   the audit log's last-approved hash, runs both arms under the schedule
   guard, and emits `report.md` + `provenance.txt` (8 lines, with bench
   commit, Ollama version and weights digest). If the report says
   **ABSTAIN**, the arms' failed-move rates differ by more than 2 SE and the
   cooperation reading is not a reading of the text. Outside the production
   home (no audit history) the default mode needs `AUDIT_CHECK_BYPASS=1`;
   `scripts/ipd-two-arm.sh --files A.md B.md [OUTDIR]` compares any two
   texts (templates, an older constitution) and needs neither the audit log
   nor a `MOLTBOOK_HOME`.
3. **Approve**: the owner reads the constitution diff, the reasoning
   trace, and `report.md`. The instrument informs; it does not gate.
   A rejection keeps the text: the reject path moves it to
   `$MOLTBOOK_HOME/.rejected/<ts>-<content_hash>.md` (P1-12.2), and the audit
   row's `content_hash` names the file. A rejection needs a reason code
   (`--reason-code`).
4. **Adopt**: `contemplative-agent adopt-staged --yes --reason "<why, in your
   words>" --approver "<your name>"`. `--yes` is the stand-in for the TTY
   answer and must carry the human's reason (ADR-0012, 2026-10-24 addendum);
   run it yourself in the session where you read the diff.
   `adopt-staged` also writes the amendment's provenance (`amendment`,
   `adopted`, `parent_sha256`, `generation_model`) to
   `contemplative-axioms.provenance.json` beside the file. It is a sidecar,
   not part of the text: the runtime injects every `*.md` in the directory
   verbatim, and this file is not one.
   Only the staged path (`--stage` then `adopt-staged`) writes it; the
   interactive in-process approval does not. `amendment` is the pre-audit
   baseline (1) plus the approved audit rows, so 2026-08-09 is 3 and the next
   adoption is 4.
   The collision guard that once wrote `contemplative-axioms-2.md` beside the
   old file instead of replacing it (T-ADOPT-OVERWRITE-TARGETS) was fixed in
   v2.11.0 (`cli/adopt.py::_replaces_canonical_target`); step 5 is kept
   because it is a cheap, permanent check, independent of that defect.
5. **Verify single-file state** (the runtime loader concatenates every `*.md`
   in the constitution dir, so a stray second file injects old and new text
   together; `amend-constitution` itself now refuses to run when the
   directory holds two or more `*.md`, P0-04.7):

   ```bash
   ls ~/.config/moltbook/constitution/*.md   # exactly one file
   shasum -a 256 ~/.config/moltbook/constitution/contemplative-axioms.md
   # must match the staged/approved hash in logs/audit.jsonl
   ```

   If a `-2.md` exists: archive the old text to the ADR's evidence dir,
   move the new text into place, re-verify the hash.
6. **Record**: add the staged candidate's row to the referent inventory,
   then read the snapshot manifest's `amendment_input` block (written by
   `amend-constitution`; recorded, never a gate): `matched_count` of
   `live_count` patterns seen under `top_k` / `threshold`, and the
   `shape_current` / `shape_amended` readings (`sections`, `clauses`,
   `quoted_rate`) — note the change from the previous amendment's block.
   Then fill the ADR amendment record (readings, approval outcome,
   adoption date — it becomes the before/after reference point for weekly
   reports; add a line to the Q1 table in `docs/evidence/research-questions.md`:
   moved / not moved against the preregistered floor), copy the run artifacts to `docs/evidence/adr-XXXX/`, update
   the task ledger, commit.

## AILuminate safety face: ended

The AILuminate two-arm of the 2026-08-09 run (T-CONST-SAFETY-FACE) is
retired ([ADR-0090](../adr/0090-ipd-two-arm-instrument-for-constitution-amendments.md)
Amendment 2026-10-24, D-P3-03-2 = A, [RFC-0056](../../rfcs/0056-ailuminate-face-termination.md)).
It is not run at the 2026-10-31 gate or after, and no local judge replaces
it. Do not attach it as material: it was uncalibrated and it sent both
constitution texts to a third-party API.
