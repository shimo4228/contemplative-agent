# 重複・冗長な記述の簡素化（2026-10-31）

調査 report: [research/2026-10-31-simplify-duplication.md](research/2026-10-31-simplify-duplication.md)

## 方針

1 つの事実は 1 か所に置く。正本（所有 ADR・script の冒頭コメント・runbook・テストが固定する表）を残し、他の文書は 1 文と link にする。コードは挙動を変えない寄せだけにする（ADR-0080「機構層は修理のみ」）。束に分けて日程で衝突を避ける代わりに、1 branch で行い、未 merge の `roadmap/r2-*` との衝突は `git merge-tree` で確かめる。

## やること

- `src/`: 本体が同じ sha256 helper 3 本を `core/_io.sha256_text` に、読み捨て型の JSONL ループ 3 本を `core/_io.read_jsonl_dicts` に、手書きの ISO 解析を `parse_aware_utc` に寄せる。insight-novelty の `b64_audit_fields` ラッパを外す。監査ログの形は変えない
- CLAUDE.md: CLI 一覧・北極星・残課題・HF mirror の各節を、正本（`--help` と CONFIGURATION.md、ADR-0080、rule `task-tracking.md`、`sync-research-data.sh` と skill `jsonld-knowledge-graph`）への要約にする。`--sync-data` の欠落と `_target_inside_data_root` の定義元を直す
- CONFIGURATION.md: 週次チェーンの段構成・バックアップの経緯・ollama-restart と rotate-log の説明を、`weekly-pipeline.sh` 冒頭・runbook・plist コメント・`rotate-log.sh` 冒頭への link にする
- 実物とずれた記述: `docs/DEPLOYMENT-RECORD.md`（GOVERNANCE.md は実在）、`evals/README.md`（存在しない `adapter_deepeval.py`）、`llms-full.txt`（外向き通信）、`scripts/weekly-pipeline.sh`（triage の tick）、`docs/HARNESS.md`（段の列挙をやめる）

## やらないこと

- script の削除: 候補 3 本は残す（`revise_table.py` は P0-01.6、`rfc0041_slot_enum_lab.py` は P3-03.9 が来週の作業に予定。`ipd_log_failure_counts.py` は IPD の再現手順）。研究用 replay 群と条件つき計器は ADR-0101 の T4 棚卸し（11-21 ゲート）へ
- README: AI 向け節は README の書き手が縮めた事実表で、BibTeX の置き場でもある
- 挙動に触れるもの（malformed 件数を数える読み込み、`except Exception`、module 分割）

## 検証

`uv run pytest tests/`、`ruff check`、`lint-imports`、`.claude/verify.sh`、各 `roadmap/r2-*` と `git merge-tree`。
