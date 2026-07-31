# ADR-0010: 研究データ同期

## Status

accepted

## Date

2026-03-25

## Context

ランタイムデータ（knowledge.json, identity.md, history/ 等）は MOLTBOOK_HOME に保存されるが git 管理されていない。研究参照用にバージョン管理したいが、メインリポジトリに混ぜると以下の問題がある:

- エピソードログ (`logs/*.jsonl`) はプロンプトインジェクション経路（ADR-0007）
- ランタイムデータとソースコードのコミット履歴が混在する
- credentials.json 等の機密ファイルの誤コミットリスク

## Decision

安全なランタイムデータのみを `~/MyAI_Lab/contemplative-agent-data/` (別リポジトリ) に rsync し、distill 実行後に自動で git commit + push する。

### 同期対象

- knowledge.json, identity.md, agents.json
- history/identity/\*, history/knowledge/\*
- skills/\*, rules/\*, meditation/results.json
- reports/comment-reports/\* (プロジェクトリポジトリから)

### 除外対象

- `logs/*.jsonl` — プロンプトインジェクション経路 (ADR-0007)
- `credentials.json` — API キー
- `rate_state.json`, `commented_cache.json` — 一時的データ、研究価値なし

### 同期タイミング

distill コマンドの後処理として実行。追加の launchd plist 不要。手動実行は `contemplative-agent sync-data`。

## Consequences

- ランタイムデータの変遷を git log で追跡可能になる
- メインリポジトリはソースコードのみに集中できる
- エピソードログを誤って公開するリスクを排除
