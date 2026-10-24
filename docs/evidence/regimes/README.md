# Apparatus boundaries and the longitudinal record (P3-02)

The distilled corpus and every report series were produced under an apparatus that changed while it ran
(extractor, generation model, serving stack, report instrument, value layer). With one agent the only
inference that survives is a comparison **inside** a stretch between two boundaries that touch the same series.
This directory is the record of the boundaries and of the readings derived from them.

| File | What it is | Produced by |
|---|---|---|
| `regimes.json` | The boundary table. One row per change: `id`, `date` (+ optional `time`), `status`, `kind`, `change`, `affects` (names from the series vocabulary), `refs`, `evidence`. Plus `serving_history` (Ollama versions, `unknown` where nothing is recorded). **Source of truth.** | by hand |
| `intervals.md` / `intervals.json` | Per series: the stretches between affecting boundaries, their length in days, observations and weekly points, and whether the stretch has at least 4 weekly points (`within_series_ok`). | `scripts/regime_intervals.py` |
| `manifest-key-generations.md` | The three key sets of `snapshots/*/manifest.json` (14 / 15 / 19 keys). | `scripts/manifest_key_generations.py` |
| `t-p3-reading.md` / `.json` / `t-p3-size.svg` | The 2026-08-16 "T-P3" reading, recomputed from the public store, with the boundary lines. | `scripts/knowledge_longitudinal_reading.py` |
| `datacard-patch.md` | The text to paste into the data repo's `DATACARD.md` (Mac side). | generators above |

Frozen against the public data repo as of its 2026-10-23 sync (100 snapshots, 12,628 patterns).

## Where the table is published

`pipeline/` in the data repository is an `rsync --delete` mirror of `MOLTBOOK_HOME`, so a `regimes.json` placed
there by hand disappears on the next sync. `scripts/sync-research-data.sh` therefore **copies this file** to
`pipeline/regimes.json` after the rsync (a test pins that a stale copy in the store does not win and that a second
sync makes no commit). The human-readable table lives in the hand-kept `DATACARD.md` (see `datacard-patch.md`).

## Adding a row

In the same change that lands the ADR/RFC (or the config/model/serving change) that causes it:

1. Add the row to `regimes.json`. `affects` is required and must use names from `SERIES` in
   `scripts/regime_intervals.py`; an unknown name fails `tests/test_regime_intervals.py` and the script (exit 2).
2. Value-layer rows (`identity`, `skills`, `constitution`) are confirmed by a human from
   `scripts/value_layer_change_series.py` (P2-05.7) and carry its `sha_before`/`sha_after` in
   `value_layer_change`; `regime_intervals.py --check-changes changes.json` fails when the two disagree. The change
   series never writes this file, and `regime-candidates.json` (serving environment candidates) is likewise
   candidates only. Nothing reads a boundary automatically (RFC-0008 stays withdrawn).
3. Regenerate `intervals.*` and `datacard-patch.md` (commands in each file's header) and hand the new table block to
   the DATACARD.

## The 2026-08-16 T-P3 reading, recovered

RFC-0006 recorded three quantities (corpus 1,463 -> 5,832; pairwise cosine 0.55 -> 0.58; 75% turnover in six
weeks) from a note that is not in the repository. `knowledge_longitudinal_reading.py` fixes explicit definitions
instead. With "active at day d" = `valid_from` on or before d and `valid_until` empty or after d, the public store
gives **1,463 on 2026-07-02 and 5,832 on 2026-08-15**: the corpus numbers reproduce exactly, so that is the
definition the old note used. The turnover figure reproduces only approximately: the share of the 2026-08-15 corpus
distilled in the previous 42 days is 72.9% (the note said 75%; the window or the base date differs by a little, and
the note does not say which), the share of the 2026-07-04 corpus no longer active is 1.5%. Both are printed because
"turnover" is ambiguous. The 4.0x growth spans R05 (per-episode distill, 2026-06-23) and R06 (model change,
2026-06-28), so it is a change of extractor and not a growth rate of one regime.

**Not reproduced here: the pairwise cosine.** The public `knowledge.json` has no vectors. On the Mac:

```
# 1. re-embed the whole corpus in one pass (DATACARD "Reconstructing embeddings"), saving a float array in row order
#    (np.save("emb.npy", np.array([r["embedding"] for r in rows])))
# 2. then
uv run --no-sync python scripts/knowledge_longitudinal_reading.py <data-repo>/knowledge.json \
  --embeddings emb.npy --asof 2026-07-02 --asof 2026-08-15 --asof 2026-10-23 \
  --regimes docs/evidence/regimes/regimes.json \
  --out-json docs/evidence/regimes/t-p3-reading.json --out-md docs/evidence/regimes/t-p3-reading.md \
  --out-svg docs/evidence/regimes/t-p3-size.svg
```

Re-derived vectors equal the originals only under the same Ollama and model versions (Ollama 0.30 changed the
normalisation; the store was re-embedded under 0.30.11 before 0.34.2 arrived, R26). Compare the result with
0.55 -> 0.58 and record the difference here. Whether this reproduction is acceptable for P3-05.10 (RF-37) is that
item's call.

## Consumption plan (ADR-0101)

- (a) Who reads: the owner when writing the research-questions ADR (P3-01.1 (d), P3-01.4 (b)); P3-05.11's figure
  script (reads `regimes.json` for its boundary lines); P3-03.3's version table (amendment dates); the paper's figures.
- (b) What one reading decides: the stretch in which the loop was closed (Q2's period) is fixed from `intervals.md`;
  after that, a row is added when an ADR lands and nothing is decided automatically.
- (c) Retire: the table is permanent (a record of the data's boundaries); at the P4-02 final sync it is frozen and
  not appended to, and `intervals.*` and the T-P3 reading are regenerated once.
