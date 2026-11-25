# Shadow Constitution — Series Table

Longitudinal series of `contemplative-agent shadow-constitution` runs
([ADR-0092](../../decision-history/0092-shadow-constitution-instrument.md)). Reader: the
human at the amendment gate due 2026-10-31 (ADR-0092 Review-when /
Consumption plan). Outcome variables and predictions were registered before
the October readings in [RFC-0055](../../../rfcs/0055-amendment-outcome-preregistration.md).

Every run is a read-only instrument reading, not an amendment candidate. Run
conditions: think-ON, outside the JST 0/6/12/18 session windows, no other
model loaded at the same time. The full replayable records stay in
`logs/constitution-shadow.jsonl`; this page carries the table only.

| # | Date (UTC) | Cosine shadow↔live | Section inventory | Corpus (patterns) | Live constitution | Source |
|---|---|---|---|---|---|---|
| 1 | 2026-08-10 | 0.814 | 4 sections, 4 organizing themes; Boundless Care absent | 50 (constitutional view) | sha256 `1035ea0bb903ece7…` (2026-08-09 text) | [shadow-run-1-reading.md](shadow-run-1-reading.md) |
| 2 | 2026-08-10 | 0.798 | 4 sections, same 4 themes under different names; Boundless Care absent | 50 (identical to run 1) | same | [shadow-run-1-reading.md](shadow-run-1-reading.md) |
| 3 | 2026-10-28 | 0.813 | 4 sections: Permeability and Dissolution / Process Fidelity / Contextual Dissonance / Self-Calibration. provisionality-of-form and theory–practice tension stable; the other two August themes not identifiable from headings alone; Boundless Care absent (0 care / compassion / suffering / kindness) | 50 slice (same as row 4; overlaps August's) of 12,903 live | sha256 `1035ea0bb903ece7…` (unchanged) | `logs/constitution-shadow.jsonl` run_id `1280699b…` |
| 4 | 2026-10-28 | 0.769 | 4 sections: Structural Flux and Non-Fixation / Processual Fidelity and Epistemological Suspicion / Modality and Contextual Pivot / Boundary Mapping and Friction. Same reading as row 3 for the August themes; Boundless Care absent | 50 slice (identical to row 3) of 12,903 live | same | `logs/constitution-shadow.jsonl` run_id `368eeebc…` |
| 5 | not run (the optional early-November run was skipped; the amendment came first) | | | | | |
| 6 | 2026-11-25 | 0.774 | 4 sections: Non-Fixity and Processual Residue / Cross-Domain Mapping and Structural Dissonance / Necessary Boundary Definition / Fidelity to Origin and Anti-Compression; Boundless Care absent (0 care / compassion / suffering / kindness) | 50 slice (same as row 7; 23 of 50 shared with rows 3–4) of 16,142 live | sha256 `8c016f4f8f6f7941…` (amendment 4; file hash `937fad4b…`) | `logs/constitution-shadow.jsonl` run_id `e3835c50…` |
| 7 | 2026-11-25 | 0.813 | 5 sections: Structural Flux (Non-Fixation) / Structural Gap (Causality and Absence) / Axiomatic Replacement (The Nature of Truth) / Necessary Record-Keeping (Failure as Data) / Contextual Dissonance (Register Management); Boundless Care absent (0 care / compassion / suffering / kindness) | 50 slice (identical to row 6) of 16,142 live | same | `logs/constitution-shadow.jsonl` run_id `ddf7b236…` |

## The 2026-11-14 amendment session

Rows 1–4 were read by Claude Code while preparing the amendment session of 2026-11-14
(RFC-0012), but they were not put in front of the owner as a separate material: the
owner decided on the full candidate text and the IPD two-arm report. The four rows sit at
0.769–0.814, inside the wider same-corpus swing (0.044). Wiring stays manual
(D-P0-07-2 = A, 2026-10-31). The candidate was adopted the same day (amendment 4,
sha256 `937fad4b…`), so the live text that rows 6+ are compared against has changed:
read later rows only as convergence of two or more post-amendment shadows toward the
amended text (RFC-0055 table), never as a series continuous with rows 1–4. The column
"Live constitution" of rows 1–4 holds the hash the instrument logs (`current_sha256` of
the loaded text), not the file hash `37e3556…`.

## Post-amendment pair (2026-11-25)

Rows 6–7 are a same-corpus pair taken back to back on 2026-11-25 (UTC 10:03 and 10:05): cosine 0.774 and 0.813.
The pair differs by 0.039, which is the post-amendment noise floor from this one pair.
Both runs compare against the amendment 4 text: the one file in the constitution directory has sha256 `937fad4b…`, and the instrument hashes the text it loads from that file to `8c016f4f…`.
Rows 1–4 are not compared with these rows, because they were measured against a different live text (`1035ea0b…`, the 2026-08-09 constitution).

## Reading notes

- Rows 3–4 (2026-10-28, a same-corpus pair) swing 0.044 — about 2.8 times the August floor of 0.016. Both floors come from one pair each; read the 10-31 comparison against the wider of the two, not the August value alone. The paper-view overlap of the slice is 0.43 in both runs.
- Noise floor from the 1–2 pair: 0.016 (one pair; itself uncertain). Floor
  anchors (2026-08-11): unrelated documents 0.42–0.49, same-genre band
  0.66–0.75 (see the Floor anchor section of `shadow-run-1-reading.md`).
- The corpus size above is the 50-pattern view slice, not the live pattern
  count (4,785 patterns accumulated since the last adoption at the
  2026-10-02 value-layer reading). Fill the "Corpus" column of rows 3+ with
  both numbers: slice size and live count.
- Rows 1–2 shared an identical corpus (a noise-floor pair); rows 3–4 should
  also be a same-corpus pair, so the floor is re-measured on today's store
  rather than assumed from August.
- Section inventory column: copy the section headings from the run's output
  text; mark the four August themes as stable / absent / renamed.

## How to fill rows 3+ (owner, on the Mac)

```bash
# outside JST 0/6/12/18; about 1 h each at 15 tokens/s; nothing else loaded
contemplative-agent shadow-constitution
# read the last record (cosine, verdict, section headings, corpus sizes)
tail -n 1 ~/.config/moltbook/logs/constitution-shadow.jsonl | python3 -c \
  'import json,sys; r=json.loads(sys.stdin.read()); print({k:v for k,v in r.items() if "b64" not in k and "prompt" not in k and "output" not in k and "thinking" not in k})'
```

Record only the table values here. A third run in early November is optional
(earliest 2026-11-01).
