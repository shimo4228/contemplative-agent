# Identity version distance — retroactive series (P3-04.8)

Read-only instrument ([ADR-0091](../../adr/0091-value-layer-cadence-in-the-weekly-chain.md)
amendment 2026-10-24, consumption plan there). Produced by
`scripts/identity_drift_retro.py` over the `identity.md` bodies held in the
public data tree: the unique bodies in `snapshots/*/identity.md` in snapshot
order, then the live `identity.md`. Four versions, so three adopted pairs.

## Table (adopted versions only; cosine not yet computed)

| from | to | bytes (from -> to) | cosine | retained / current sentences | novel / candidate sentences | any dissolution word (cand.) | fluid | dissolve | texture | tension | silence-permission (cur. -> cand.) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| distill_20260801T183004037155Z | skill-stocktake_20260815T041708923626Z | 694 -> 894 | n/a (not embedded) | 0/3 | 4/4 | 1/4 | 0/4 | 0/4 | 0/4 | 1/4 | no -> no |
| skill-stocktake_20260815T041708923626Z | distill_20260912T183000611576Z | 894 -> 954 | n/a (not embedded) | 0/4 | 5/5 | 1/5 | 1/5 | 0/5 | 0/5 | 1/5 | no -> no |
| distill_20260912T183000611576Z | distill_20261010T183005502461Z | 954 -> 971 | n/a (not embedded) | 0/5 | 5/5 | 2/5 | 0/5 | 0/5 | 0/5 | 2/5 | no -> no |

Version labels are the snapshot in which a body first appears. A snapshot is
taken at run start, so it holds the identity live at that moment: the series
is ADOPTED versions. Staged candidates that were rejected are in no public
tree, so the "all staged" series is empty here and needs the owner's machine
(below).

## How to read it

- Counts, not rates. These identities are 3-5 sentences (694 / 894 / 954 / 971 B),
  below the 10 needed for a Wilson interval, so every denominator is shown as
  `k/n` with no interval. No rate line chart.
- Sentence retention is 0 for every pair. That is expected, not a finding: since
  ADR-0057 each identity is regenerated from the self-reflection corpus with no
  prior seed, so no sentence survives verbatim. Cosine is the informative column.
- The dissolution-word columns count sentences, not occurrences. The 694 B text
  is the "fluid texture ... dissolves" register; the first pair's candidate
  (894 B) already reads "perpetual structural tension", and the later pairs
  keep "tension" in 1-2 sentences each.
- The silence-permission flag is lexical (see `core/identity_drift.py`) and is
  "no" for all four adopted versions; the template identities carry
  "it's okay not to respond to everything".
- Every point is a single run of a stochastic generator; no null-pair band exists
  yet (P3-04.9). Descriptive only, until that floor is measured.

## Left for the owner's machine (needs Ollama)

1. The cosine column (nomic-embed-text):

   ```sh
   cd <main repo checkout>
   uv run --no-sync python scripts/identity_drift_retro.py \
     --snapshots-dir ~/.config/moltbook/snapshots --current ~/.config/moltbook/identity.md \
     --embed --jsonl /tmp/identity-drift-retro.jsonl
   ```

   Paste the table over the one above and keep the JSONL beside it.
2. The "all staged" series: pass the staged and rejected identity texts in order
   with `--extra` (they live in the private audit trail and `.staged/` history).
3. P3-04.9 (null pairs and the 11-template floor anchor) reuses
   `measure_identity_drift`; it needs at least 3 `distill-identity` runs on one
   corpus and the 11 `config/templates/*/identity.md` files, with the length
   normalised or stratified.
