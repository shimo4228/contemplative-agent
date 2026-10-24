# Reproducing the published numbers

This page is for someone who wants to check, from outside, what this project
says about itself. It tells you how to get the data, which readings you can
recompute from the public data alone, which need the owner's private logs, and
which need a hosted model. Every command below was run on 2026-10-24; the run is
recorded in [`docs/evidence/p3-05/repro-run-20261024.md`](evidence/p3-05/repro-run-20261024.md).
Where a command could not be run here, the page says so.

The data side is documented in the data repository's
[`DATACARD.md`](https://github.com/shimo4228/contemplative-agent-data/blob/main/DATACARD.md)
(draft of its next revision: [`docs/evidence/p3-05/data-repo/`](evidence/p3-05/data-repo/README.md)).

## 1. Get the data

```sh
git clone https://github.com/shimo4228/contemplative-agent-data data
git clone https://github.com/shimo4228/contemplative-agent framework   # this repository
```

The embedding-free patterns are also on Hugging Face:

```python
from datasets import load_dataset
patterns = load_dataset("shimo4228/contemplative-agent-data", split="train")
```

(`load_dataset` needs network access to Hugging Face; it was not run from the
sandbox that wrote this page, whose egress is restricted. The git clone and every
command in section 2 do not need it.) Use the lower-case id: the mixed-case one
returns a "renamed" 404.

Snapshots, comment reports and everything else are plain files in the clone.
The data repository mirrors the layout of the agent's `MOLTBOOK_HOME`, so a
script that reads `$MOLTBOOK_HOME/knowledge.json` or `$MOLTBOOK_HOME/skills/` can
be pointed at the clone: `MOLTBOOK_HOME=$PWD/data`. Do that on a **copy** if the
script writes.

## 2. Recompute readings from the public data

All commands run from the framework checkout; `data/` is the clone from above.
`python3 -I` is the isolated interpreter; nothing here needs the package
installed.

| Reading | Command | Result on 2026-10-24 (data at sync `d44544a`) |
|---|---|---|
| Pattern rows, live rows | `python3 -I -c "import json;d=json.load(open('data/knowledge.json'));print(len(d),sum(r['valid_until'] is None for r in d))"` | 12,628 rows, 11,818 live |
| Schema, enum values, `pipeline_version` table, duplicates | `python3 -I scripts/export-patterns-jsonl.py --describe data/knowledge.json` | identical to the DATACARD block between its `describe` markers |
| Number of adopted skills | `ls data/skills/*.md \| wc -l` | 53 |
| Skill to pattern reach | `python3 -I scripts/skill_provenance_reach.py data` | exit 1: 53 `no-lineage` (skills adopted before 2026-10-24 carry no `source_ids` until the owner's one-time backfill; new skills reach their rows) |
| Per-month figures | `python3 -I analysis/public_figures.py data figs/` | three SVGs: 12,628 patterns over 8 months, 16,199 comment-report entries over 8 months, 53 skills over 4 months |
| `dead-code` and `docs-consistency` weekly series | check out the framework at the commit of the week (the one before the week's end date), then `python3 scripts/docs_consistency_scan.py --repo .` and, with `vulture` on `PATH`, `python3 scripts/dead_code_scan.py` | week 2026-10-16, commit `62072855`: docs-consistency `count 0`, `scanned_files 392`; dead-code `count 0`, `parsed_total 136` — equal to `pipeline/*/…-2026-10-16.json` |
| Docs scan over the data repo's hand-kept files | `python3 scripts/docs_consistency_scan.py --repo . --data-repo data` | stale-claim findings, if any, in the `data_stale_claim` entries |

The other five weekly series (`comment-outcomes`, `confusion-pairs`,
`never-selected`, `value-layer`, and the retired `ledger-watch`) read the agent's
private logs and cannot be recomputed from public inputs; see the data repository's
"Pipeline instruments" table.

The README's "about 10,700 patterns" is a count as of early October; the
reading above is the current one. Gate counts (skill proposals adopted and
rejected) come from the private approval log: tier 2 below.

## 3. Which claim, which evidence, how reproducible

Tiers: **1** = the public data (and this repository) is enough; **2** = needs the
owner's private logs (`logs/`, the approval log, the episode log), which are not
published; **3** = needs a hosted model (`claude -p` as the judge) or the
operator's hosted endpoint.

| Claim | Evidence | Tier |
|---|---|---|
| The pattern store, its shape and its history of schema changes | `scripts/export-patterns-jsonl.py --describe`; ADR-0021, ADR-0108 | 1 |
| Adopted skills, and what each came from | `data/skills/`, `scripts/skill_provenance_reach.py`; ADR-0050 amendment | 1 (new skills; older ones after backfill) |
| The constitution's text now and its amendments | `data/constitution/`, `data/reports/analysis/constitution-amendment-report.md`; `docs/evidence/adr-0090/` | 1 for reading the texts; the two-arm bench runs are 3 |
| What the agent said each day | `data/reports/comment-reports/`; parser in the DATACARD "Loading" section | 1 (the quoted `Context` is third-party text, outside CC0) |
| How many proposals were adopted and rejected (README, "See it running") | the private approval log; `scripts/value_layer_approval_join.py` | 2 (the weekly `pipeline/value-layer-*.json` carries cadence readings, not the tally) |
| Behavioural eval of comment generation | `evals/baselines/*.json` (committed); `evals/check_staleness.py` | baselines and staleness check: 1; a new run: 3 |
| Calibration and replay studies behind ADRs | `docs/evidence/adr-*/` | per script, section 4 |

## 4. Every evidence script and instrument, by tier

`docs/evidence/**/*.py` and `scripts/*.py` (91 files on 2026-10-24). "Also needs" lists a local Ollama model where the script
embeds or generates. The classification is by what the script reads: `logs/…`,
the audit or episode logs, or `MOLTBOOK_HOME` state that the public clone does
not carry means tier 2.

### Tier 1 — public data or this repository only

| Script | Input | Also needs |
|---|---|---|
| `scripts/export-patterns-jsonl.py` | `knowledge.json` | |
| `scripts/skill_provenance_reach.py` | `skills/`, `knowledge.json` | |
| `scripts/dead_code_scan.py` | the framework checkout | `vulture` |
| `scripts/docs_consistency_scan.py` | the framework checkout (and optionally a data clone) | |
| `scripts/rfc_index.py` | `rfcs/` frontmatter | |
| `scripts/adr_index.py` | `docs/adr/` bodies | |
| `scripts/gen-data-gitignore.py` | `config/sync-excludes.txt` | |
| `scripts/distill_window_gap_count.py` | `knowledge.json`, `reports/comment-reports/` | |
| `scripts/third_party_overlap.py` | the public data clone | |
| `scripts/ipd_two_arm_report.py` | committed run JSON under `docs/evidence/adr-0090/` | |
| `scripts/weekly_random_sample.py` | `reports/comment-reports/` | |
| `scripts/weekly_sample_splice.py` | a sample sidecar and a report | |
| `scripts/observation_ledger.py` | `reports/analysis/observation-ledger.jsonl` (render) | |
| `scripts/novelty_retrieval_dry_run.py` | `knowledge.json`, `skills/` | Ollama embeddings |
| `docs/evidence/adr-0009/dedup-knowledge-20260416.py` | `knowledge.json` (one-shot, writes: run on a copy) | |
| `docs/evidence/adr-0009/threshold-sweep.py` | `knowledge.json` | Ollama embeddings |
| `docs/evidence/adr-0021/retrieval-scoring-effect-20260418.py` | `knowledge.json` | Ollama embeddings |
| `docs/evidence/adr-0053/importance-ablation.py` | `knowledge.json` | Ollama embeddings |
| `docs/evidence/adr-0089/analyze-stability.py` | committed eval run JSON | |
| `docs/evidence/adr-0062-parser-rewrite/verification_parse_baseline.py` | none (frozen module) | |
| `docs/evidence/adr-0090/se-table.py` | committed IPD run JSON under `docs/evidence/adr-0090/` |  |
| `scripts/compounding_axes_reading.py` | the public data clone |  |
| `scripts/freeze_reading.py` | `git log` of the framework checkout |  |
| `scripts/identity_drift_retro.py` | `snapshots/*/identity.md`, `identity.md` | Ollama embeddings |
| `scripts/ipd_log_failure_counts.py` | one committed IPD `run.log` |  |
| `scripts/ipd_series_table.py` | the output directory of `scripts/ipd-series.sh` | Ollama and the rules-repo bench, to produce the run |
| `scripts/knowledge_longitudinal_reading.py` | `knowledge.json` | `numpy` |
| `scripts/manifest_key_generations.py` | `snapshots/*/manifest.json` |  |
| `scripts/regime_intervals.py` | `docs/evidence/regimes/regimes.json`, the public data clone |  |
| `scripts/release_consistency_check.py` | the framework checkout |  |
| `scripts/snapshot_resolve.py` | `audit.jsonl` rows published with a decision, `snapshots/` |  |
| `scripts/value_layer_change_series.py` | `snapshots/` |  |
| `scripts/principle_coverage.py` | `reports/comment-reports/`, `identity.md` | |

### Tier 2 — needs the owner's private logs

| Script | Reads | Also needs |
|---|---|---|
| `scripts/api_drift_scan.py` | `api-audit.jsonl` | |
| `scripts/confusion_pair_reading.py` | skill-selection log, `skills/` | |
| `scripts/cross_day_duplicate_scan.py` | published bodies in the episode log | |
| `scripts/injection_ablation_replay.py` | logged comment generations | Ollama |
| `scripts/instrument_census.py` | the self-written logs | |
| `scripts/revise_table.py` | `logs/insight-stages.jsonl` | |
| `scripts/log_anomaly_sweep.py` | the self-written logs | |
| `scripts/novelty_replay_ab.py` | insight logs | Ollama |
| `scripts/relevance_arm_replay.py` | relevance logs | Ollama |
| `scripts/relevance_label_set.py` | relevance logs | Ollama |
| `scripts/relevance_shadow_reading.py` | relevance logs | |
| `scripts/retrieval_recall_measure.py` | `logs/insight-staged.jsonl`, episodes | Ollama |
| `scripts/skillsel_arm_replay.py` | skill-selection log | Ollama |
| `scripts/skillsel_reading.py` | skill-selection log | |
| `scripts/state_invariant_check.py` | persisted state and logs (partly tier 1: the `knowledge.json` checks) | |
| `scripts/submolt_scope_stability.py` | sweep logs | |
| `scripts/value_layer_approval_join.py` | `audit.jsonl` | |
| `scripts/value_layer_due_check.py` | `audit.jsonl`, `MOLTBOOK_HOME` | |
| `docs/evidence/adr-0062-parser-rewrite/differential_replay.py` | the verification audit corpus | |
| `docs/evidence/adr-0062-parser-rewrite/replay_parser.py` | the verification audit corpus | |
| `docs/evidence/adr-0068/ab_gemma_think-20260628.py` | private episodes | Ollama |
| `docs/evidence/adr-0081/skillsel-cache-ab-20260805.py` | skill-selection log | Ollama |
| `docs/evidence/adr-0084/replay-distill-abstain-20260726.py` | episodes | Ollama |
| `docs/evidence/adr-0096/replay-worth-gate-20260817.py` | `audit.jsonl`, `knowledge.json` | Ollama |
| `docs/evidence/adr-0096/surprise-calibration-20260817.py` | `audit.jsonl`, `knowledge.json`, embeddings | |
| `docs/evidence/verify-solve-model-compare-20260701/replay_qwen_vs_gemma.py` | verification audit corpus | Ollama |
| `scripts/archive_candidate_context.py` | the week's archive-candidate file and comment-outcomes JSON |  |
| `scripts/comment_outcome_separation.py` | two window JSONs of `read_comment_outcomes` |  |
| `scripts/comment_outcomes_reading.py` | skill-selection log, comment reports |  |
| `scripts/gate_item_audit_join.py` | `pipeline-metrics.jsonl`, `audit.jsonl` |  |
| `scripts/layer1_exit_guard.py` | `audit.jsonl` |  |
| `scripts/never_selected_reading.py` | skill-selection log, `skills/` |  |
| `scripts/pipeline_run_status.py` | the weekly-pipeline audit log and reports |  |
| `scripts/rfc0041_slot_enum_lab.py` | two JSONL inputs built from an insight run | Ollama |
| `scripts/self_regulation_reading.py` | the self-written logs |  |
| `scripts/skills_index.py` | `skills/`, `skills/.archive/`, `audit.jsonl` (ts, source, file name) |  |
| `scripts/staged_item_axes.py` | `.staged/*.meta.json`, `insight-novelty.jsonl` |  |
| `scripts/store_state.py` | the weekly value-layer records |  |
| `scripts/surface_counter_scan.py` | published bodies in the episode log |  |

### Tier 3 — needs a hosted model

| Script | Needs |
|---|---|
| `evals/run_eval.py`, `evals/judging.py` (`run_claude_judge`) | local Ollama for generation and an isolated `claude -p` as the judge |
| `evals/jev_arm.py` | the operator's hosted endpoint; sends past situations off-machine, operator-run only |

The comparison and bookkeeping modules of `evals/` (`compare.py`, `dataset.py`,
`check_staleness.py`) work on the committed baselines and dataset without a hosted
model, and `generation.py` needs only a local Ollama; see
[`evals/README.md`](../evals/README.md).

### Libraries and maintenance tools (no reading of their own)

`scripts/_audit.py`, `scripts/_census_registry.py`, `scripts/_census_series.py`,
`scripts/_md.py`, `scripts/_portable_path.py`, `scripts/_scan.py`,
`scripts/_stats.py` are helpers the scripts above import.
`scripts/pipeline_audit.py` appends an event to the weekly-pipeline audit log;
`scripts/rewrite_home_paths.py`, `scripts/restore-embed-knowledge.py` and
`scripts/migrate-knowledge-sidecar.py` change a store and are maintenance, not
readings.
`scripts/audit_correction.py` (appends a hand-made `correction` row), `scripts/layer1_reenable.py` (appends the owner's `layer1-reenable` row), `scripts/gen_evidence_index.py` and
`scripts/render_env_docs.py` (regenerate docs) are maintenance; `scripts/chain_schedule_probe.py`,
`scripts/preflight_project_settings.py`, `scripts/claude_toolset_probe.py`, `scripts/input_provenance.py`,
`scripts/session_envelope.py`, `scripts/scan_cadence.py`, `scripts/value_layer_annotate.py` and
`scripts/sync-commit-summary.py` are steps of the weekly chain or the sync, not readings;
`scripts/rfc_inbox.py` numbers and publishes the chain's drafts at the Saturday gate (maintenance).

## 5. Which code tag matches which shape of `knowledge.json`

| Framework tag (date) | Live store | Public `knowledge.json` | Rebuild embeddings from the public copy |
|---|---|---|---|
| v2.6.0 – v2.8.0 (2026-06-20 – 07-09) | inline vectors | with vectors until 2026-07-12 (so the Zenodo v1.0.0 deposit of 2026-06-17 carries them) | not needed for those copies |
| v2.9.0 – v2.11.0 (2026-08-02 – 08-20) | inline vectors | embedding-free (export since 2026-07-12) | `scripts/restore-embed-knowledge.py` |
| v2.12.0 and later (2026-09-12 –) | vectors in `pattern-embeddings.sqlite` (ADR-0108) | embedding-free | `scripts/restore-embed-knowledge.py` writes the sidecar; `scripts/migrate-knowledge-sidecar.py` moves legacy inline vectors out |

The DATACARD's own 15-line script rebuilds vectors for a *dataset* use without
the framework; the two scripts above rebuild an *agent runtime*.

## 6. Citing

| You used | Cite | DOI |
|---|---|---|
| The implementation | Contemplative Agent | 10.5281/zenodo.19212118 (concept) |
| The record | Contemplative Agent: Research Data | 10.5281/zenodo.20732894 (concept; first deposited version v1.0.0, 2026-06-17) |
| The judgment | Agent Attribution Practice | 10.5281/zenodo.19652013 |
| The method | Agent Knowledge Cycle | 10.5281/zenodo.19200726 |

Dataset version rule (decision D-P3-05-1): a version is cut at each code minor
release, just before a constitution amendment falls due, and once at the end; the
deposit copy replaces each third-party `Context` with `[see GitHub <commit>]`.

## 7. Withdrawing published text

Someone who finds their text in the public data can ask for its removal or
correction; the address and the reach per surface are in the data repository's
`NOTICE`. A request is carried out through the suppression list
(`config/takedown-suppressions.txt`, [ADR-0127](adr/0127-takedown-suppression-list-for-republished-text.md)):
identifiers only. After a withdrawal, regenerated reports show `[withdrawn]` for
the post's Context and the name, and the pattern export leaves listed rows out.
Text already in git history is a separate, manual step that the `NOTICE` table
describes.
