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

> **注記（2026-10-15, RFC-0051）**: 現在の動き方はこれではない。distill の後処理は 2026-03-28 に外れた（commit `14b833d`）。sync は手で入れた launchd job `com.moltbook.sync-data`（`contemplative-agent sync-data`）が毎日 05:30 に回し、`install-schedule` の管理外。`cli/session_cmds.py::_run_sync` は失敗を stderr の警告として出すだけで exit 0。下の 2026-10-15 追補を参照。

## Consequences

- ランタイムデータの変遷を git log で追跡可能になる
- メインリポジトリはソースコードのみに集中できる
- エピソードログを誤って公開するリスクを排除

## Amendment（2026-10-15）: commit 前の home パス検出ゲート（RFC-0051）

公開される書き手は、パスを `MOLTBOOK_HOME` 相対で、その外は home を `~` にして書く（`src/contemplative_agent/core/portable_path.py`。RFC-0050 が snapshot の manifest、RFC-0051 が週次の value-layer 読み値・混同対の findings 節・ログ異常の state ファイル・watchdog の status ファイル・証拠 3 本の書き手）。マシンの home パスは OS のユーザー名を含み、修正前は同期されるファイル 114 本が持っていた（`pipeline/` 7、`reports/analysis/` 10、`snapshots/` 97 — 2026-10-15 の公開データ repo の作業木）。

- **ゲート。** `scripts/sync-research-data.sh` は rsync と `knowledge.json` の export の後・`git add` の前に、公開データ repo の作業木（`.git/` を除く）を home パスで、大文字小文字を区別せずに検索する（macOS のファイルシステムは大文字小文字を区別しないので、小文字化した `/users/<user>` も同じユーザーを指す）。git は symlink の先をファイルの中身として保存するので、symlink の先も見る。見つかればファイル名（中身は出さない）を stderr に出し、commit も push もせず非 0 で終わる。書き換えはしない — 直すのは書き手。`HOME` が空か `/`、または検索自体のエラーでも止まる（fail closed）。
- **過去のファイル。** 修正前に書かれたファイルは `scripts/rewrite_home_paths.py` で一度だけ書き換える（既定は dry-run、`--apply` で書く。対象は sync script 自身の exclude から読んだ上の rsync 集合）。それが走るまでゲートは sync を止め続ける。公開データ repo の git 履歴は範囲外（ロードマップの「公開データの版と backfill」）。
- **見える化。** 止まった sync は stderr の警告だけになる（上の注記）ので、`scripts/pipeline_watchdog.sh` に `sync-data` 行を足す（ADR-0085 の 2026-10-15 追補）。

Review-when: sync が rsync の素通しでなくなる（export 時の変換層が入る）、または `MOLTBOOK_HOME` の外から生成物を公開する経路が増える。
