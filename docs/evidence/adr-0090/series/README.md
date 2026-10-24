# IPD series protocol: retro versions (P3-03.3) and placebo arms (P3-03.4)

Inputs and the table skeleton for two series, prepared so that the runs are one
command each on the Mac. Nothing here has been run: each run needs Ollama (local
gemma, about 1 h per text) and the pre-registration of P3-01.2 first.

## Before running

1. The pre-registration (P3-01.2) must already name the **pairs that will be read**
   (adjacent versions or each version against the verbatim text), the
   family-wise rule (4 texts x 3 alpha = 12 cells are never tested against one
   floor; each pair is read with its own z, ADR-0090 Amendment 2026-10-24) and the
   owner's predictions. Write those first, then run.
2. Calibration contract as for every IPD run: `gemma4:e4b`, n=10, the
   `ipd-series.sh` window guard (it waits out the JST 0/6/12/18 sessions), one run
   at a time and never beside another model (16 GB). The SE rule has so far been
   checked against one null pair; the two further null pairs (ADR-0090) should be
   read first if they have not been, or these tables are on the recording-only
   footing.
3. For the version series the 2026-03-27 text must exist as
   `constitution/history/2026-03-27-reconstructed.md` in the data checkout
   (P3-04.2). It is a **reconstruction from the amendment report's quote; its sha
   is unknown**, and the table must say so in that row. Do not put non-verbatim
   constitution text into the rules repo (rules ADR-0002 / 0003); the rules README
   gets one link line to the published table, nothing else.

## Commands (Mac)

```bash
export DATA_REPO=~/path/to/contemplative-agent-data      # checkout with constitution/history/
cd contemplative-agent
# P3-03.3: four versions, about 4 h in total
scripts/ipd-series.sh docs/evidence/adr-0090/series/constitution-versions.tsv .notes/ipd-series-versions
# P3-03.4: live text as reference + four placebo templates, about 4-5 h in total
scripts/ipd-series.sh docs/evidence/adr-0090/series/placebo-arms.tsv .notes/ipd-series-placebo
```

Each run directory gets `provenance.txt` (bench commit, Ollama version, weights
digest, sha256 of every text), one JSON per text, and `table.md` (the table below,
filled). Re-running the same command resumes: a text whose JSON exists is skipped.
`table.md` can be rebuilt with
`python3 scripts/ipd_series_table.py MANIFEST OUTDIR [--ref LABEL]`.

## Where the results go

- Version table: data repo `constitution/history/` (table next to the texts; place it
  under `$MOLTBOOK_HOME` so the daily `rsync --delete` keeps it). One link line from
  the rules README. A row in the P3-01 Q1 evidence table.
- Placebo table and the four JSONs: `docs/evidence/` (a new `adr-0090/placebo-<date>/`
  directory), plus the one-sentence reading "meditation-specific, or any ethical text?"
  in the Q1 evidence table.
- Read once. Freeze the JSON, do not re-run unless the floor changes (it is then
  re-measured together with the null pairs).

## Table skeleton (filled by `ipd_series_table.py`)

| text | alpha | effect | SE | delta-effect vs ref | SE(delta) | z | failed moves | note |
|---|---|---|---|---|---|---|---|---|
| verbatim | 0.0 / 0.5 / 1.0 | | | (ref) | | | | paper Appendix C text |
| 2026-03-27 | 0.0 / 0.5 / 1.0 | | | | | | | reconstruction, sha unknown |
| 2026-05-05 | 0.0 / 0.5 / 1.0 | | | | | | | retired text, sha256 3d8a8503 |
| 2026-08-09 | 0.0 / 0.5 / 1.0 | | | | | | | live text, sha256 37e3556a40ea |

The placebo series has the same columns, with the live 2026-08-09 text as the
reference row and `stoic`, `utilitarian`, `care-ethicist`, `tabula-rasa` as the
compared rows. `care-ethicist` doubles as the "Converse IPD" of
`docs/evidence/adr-0092/interpretation-notes.md` (care vocabulary without the
non-dual generator).

Reading rules that do not depend on the numbers: a failed-move rate that differs
from the reference by more than 2 SE means the row's cooperation figure is not a
reading of the text (ADR-0090); one cell of twelve crossing 2 SE is expected by
chance and is not a finding.

## Null pairs for the SE rule (P3-03.2)

Two more null pairs (same text twice each) check that a new pair's delta-effect stays
within 2 SE. Per pair, about 2 h, outside the JST windows:

```bash
# repeat once per pair; T = the live constitution (any fixed text works, but use the live one)
T=$HOME/.config/moltbook/constitution/contemplative-axioms.md
scripts/ipd-two-arm.sh --files "$T" "$T" .notes/ipd-null-pair-3
scripts/ipd-two-arm.sh --files "$T" "$T" .notes/ipd-null-pair-4
```

Copy each `arm-A-files.json` / `arm-B-files.json` pair to
`docs/evidence/adr-0090/null-run-3.json`, `null-run-4.json`, ... (so the numbering
continues from `null-run-1/2`), regenerate `se-table.md` with `se-table.py` after adding
the new files to its `RUNS` list, and update the pair count in the ADR-0090 amendment.
The `report.md` of each run already prints SE and z for the pair; a pair where any |z|
is above 2 means the rule needs a second look, not that the run is wrong.

## Failed-move counts of the five existing runs

The old runs have only logs. Totals per run (not per simulation) can be recovered, LLM
no-response exactly and parse fallbacks only if the run used `-v`:

```bash
python3 scripts/ipd_log_failure_counts.py <run.log> --bench-src ../contemplative-agent-rules/benchmarks/prisoners-dilemma/src
```

Append the three printed lines per run to `docs/evidence/adr-0090/` (null-run-1, null-run-2,
arm-A, arm-B, and the shadow arm under `docs/evidence/adr-0092/`), writing "not recoverable"
where the script says so.
