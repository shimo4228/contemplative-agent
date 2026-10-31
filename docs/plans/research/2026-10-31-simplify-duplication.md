# 調査 report — コードと文書の重複・冗長（2026-10-31）

種別: 内部調査（repo 内で答えが出る refactor の問い）。plan: [../simplify-duplication.md](../simplify-duplication.md)

## 問い

どの文書・コードが同じことを複数箇所で述べているか。どれを正本に残し、どれを畳めるか。機構層の挙動を変えずにできる範囲はどこまでか。

## 方法

- Explore agent 3 本（文書 / `src/` / `scripts/`・`tests/`・`evals/`）で grep・行数・参照数を集め、主ループが食い違いの主張を実物で照合した
- 未 merge branch が触るファイルは `git diff --stat main...<branch>` で列挙した（`roadmap/r2-adr-ledger`、`r2-chain`、`r2-hygiene`、`r2-readings`、`decide-in-session`、`claude/diagram02-meta-fields`）
- 凍結判定の数え方は `scripts/freeze_reading.py:106-136`（`FROZEN_SET`）と `:446-464`（`quiet_run`）で確認した
- episode log・`agent-launchd.log` は読んでいない。Ollama / LLM は使っていない

## 実物で確認した食い違い

| 記述 | 実物 |
|---|---|
| `docs/DEPLOYMENT-RECORD.md:11-13`「GOVERNANCE.md は まだ無い」 | `docs/GOVERNANCE.md` は存在する |
| `evals/README.md:18` が `adapter_deepeval.py` を載せる | `evals/` に該当ファイルは無い |
| `llms-full.txt:102`「Only adapter-specific traffic … no subprocess」 | README の外向き通信 3 行（週次 `claude -p`、GitHub push、HF upload）と矛盾 |
| `CLAUDE.md:59` の `install-schedule` に `--sync-data` が無い | `src/contemplative_agent/cli/schedule.py:45,440` に実在 |
| `CLAUDE.md:100` `cli/store_paths.py::_target_inside_data_root` | 定義は `src/contemplative_agent/core/_io.py:115` |
| `scripts/weekly-pipeline.sh:19`「task-triage loop (Sat 14:07 tick)」 | triage の tick は水 17:07（CYCLES.md、weekly-gate SKILL） |

## src/

- 集約済み: JSONL 追記 `append_jsonl_restricted`（`core/_io.py:205`）、原子書き込み `write_restricted`、`b64_audit_fields`（`core/_io.py:377`）、`env_get`（`core/env.py:720`）
- 残る同型: `b64_audit_fields` の薄いラッパ 2 本、本体が同一の sha256 helper 3 本、手書きの ISO 解析 1 本、読み捨て型 JSONL ループ 3 本（場所は plan の束 2）
- 寄せてはいけないもの: 切り詰めハッシュ（値の互換）、`identity_drift.py:116` / `skill_selection.py:437`（符号化の違い）、`text_utils.py:283`（naive の扱い）、malformed 件数を出す `comment_outcomes.py` / `selection_window.py`
- 削除候補に見えて消費者がいたもの: `knowledge_store.prune_orphan_vectors` ← `scripts/migrate-knowledge-sidecar.py:71`
- import-linter: `cli → adapters → core`、adapter 間 independence、core 内 `_io` が最下層。新設 helper は `_io.py` に置けば契約に触れない

## scripts/・tests/・evals/

- scripts/ は 96 ファイル約 36,000 行。週次チェーン・同期・バックアップ・IPD 系に常設の消費者がある
- 一回限りと書かれた script の候補 3 本は、確かめると消せなかった: `revise_table.py` は P0-01.6、`rfc0041_slot_enum_lab.py` は P3-03.9 がまだ予定にある（`docs/plans/roadmap-2026-10/STATUS.md`）。`ipd_log_failure_counts.py` は `docs/evidence/adr-0090/series/README.md:100` の再現手順
- r2-hygiene が保守中で残すもの: `distill_window_gap_count.py`（smoke test を追加）、`novelty_replay_ab.py`、`novelty_retrieval_dry_run.py`
- 判断が要るもの（ADR-0101 の T4 へ）: 研究用 replay 群約 9,000 行、`evals/jev_arm.py`、条件つき instrument 10 本、`evals/baselines/` 旧 4 本
- 連動ゲート: `tests/test_reproducing_guide.py` は `scripts/*.py` 全件の `docs/REPRODUCING.md` 掲載を要求する
- 共有 helper が無い重複: JSONL 読み込み 6 本、MOLTBOOK_HOME 解決約 20 本、ISO 週 2 本

## 文書

- 同じ機構の散文が 3 か所以上: 週次チェーンの段構成（6 か所）、外向き通信（5 か所）、install-schedule の macOS 限定（6 か所）、バックアップの経緯（3 か所）、launchd ジョブ表（4 か所）
- 正本の宣言と散文が並存: CLAUDE.md の北極星節（「ADR を追補したら同 PR で同期」）、セキュリティ方針節（「食い違えば threat-model.md が優先」）
- 文書表を固定するテスト: `test_claude_md_tables.py`、`test_adr_status_consistency.py`、`test_adr_index_generated.py`、`test_configuration_doc.py`、`test_cycles_doc.py`、`test_governance_doc.py`、`test_doc_links.py`、`test_reproducing_guide.py`、`test_readme_quickstart.py`
- 規模: CLAUDE.md 225 行、CONFIGURATION.md 760 行、CYCLES.md 279 行、README 214 / 212 行、llms-full.txt 420 行

## 時期の制約

- `freeze_reading.py` は凍結集合（`src/`、`config/`、`weekly-pipeline.sh` ほか）に `fix` 以外の commit がある週を静穏と数えない。静穏窓は 11-28（P1-06.13）と v2.14.0 の後から数える計画なので、`src/` の refactor は 11-27 までに入れる
- `self_regulation_reading.py` の `outside` は `Roadmap:` trailer の無い土曜 commit を数えるので、commit は平日に行う
