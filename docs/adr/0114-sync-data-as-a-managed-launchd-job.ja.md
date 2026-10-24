# ADR-0114: 公開研究データ同期を launchd の管理対象ジョブにする

## Status

accepted — partially-supersedes ADR-0010（Sync Timing:「distill コマンドの後処理。launchd plist は不要」）

## Date

2026-10-24

## Context

ADR-0010 は同期を「distill コマンドの後処理として走り、追加の launchd plist は不要」と書いた。これは 2026-03-28 に distill の hook を外した時点（commit `14b833d`）で成り立たなくなった。それ以降 data repo には毎日 05:30 JST に、手で入れた launchd ジョブ `com.moltbook.sync-data` から `sync:` commit が 1 件入っている。`install-schedule` はこのジョブを知らず、`--uninstall` で止まらず、再 install でも復元されず、watchdog の `sync-data` 行は「手で入れたもの」と書いていた。ADR-0010 は存在しない機構を説明したままだった（2026-10-15 の注記は乖離を記録しただけで直していない）。

## Decision

D-P2-04-1 = A（owner、2026-10-24）: launchd の日次ジョブを経路とし、installer が持つ。

1. `config/launchd/com.moltbook.sync-data.plist` が毎日 05:30 に `contemplative-agent sync-data` を走らせる（03:30 の distill の後、00:00 と 06:00 の agent セッションの間。watchdog の行がこの時刻に anchor している）。時刻は watchdog と同じくテンプレートに固定。
2. `install-schedule --sync-data` で入る。他の optional job と同じく宣言的: フラグ無しの実行は install 済みの sync-data を外し、`--uninstall` も外す。したがって手で入れた既存ジョブは、次の `install-schedule ... --sync-data` で管理下のものに置き換わり、フラグを省いた実行で消える。
3. 同期は distill の成否と独立に走る。失敗は非 0 終了（`cli/session_cmds.py::_run_sync`、P2-04.2）で launchd に記録され、watchdog の `sync-data` 行が commit の到達を独立に確かめる。
4. 何を公開するかは script のもので installer のものではない: 対象と除外の正本は `scripts/sync-research-data.sh`。本 ADR は公開範囲を変えない。
5. 公開面（D-P2-05-1 = C、owner、2026-10-24）: data repo は 2 層 — script が機械的に写す mirror 層と、rsync が除外し上書きしない手書き層（`DATACARD.md`・`README*.md`・`llms.txt`・`graph.jsonld`・`CITATION.cff`）— で、commit 前の scan（home パス検出ゲート）が最後の防壁。ファイルごとの除外表と除外の allowlist 化は P2-05.1 / P0-03 の仕事で、script を変えるものであり本決定ではない。

ADR-0010 の Sync Targets と Exclusions はそのまま。置き換わるのは Sync Timing だけ。

## Review-when

- 同期が launchd を離れる（別のスケジューラ、ホスト型ジョブ）。
- `install-schedule` が唯一の宣言的 installer でなくなる。

### Consumption plan（ADR-0101）

本 ADR は計器を足さず、既存のジョブを installer の下へ移すだけ。健全性の読み手は変わらない: watchdog の `sync-data` 行を土曜ゲート Step 0(c) が読む。

## Consequences

- 完全停止は `install-schedule --uninstall` と `launchctl list | grep com.moltbook` の確認で済み、sync-data に手動の工程は要らない（docs/CONFIGURATION.md「Stopping everything」）。
- 現行機の一回きりの移行: まず手で入れた live の plist を退避する（`cp ~/Library/LaunchAgents/com.moltbook.sync-data.plist ~/sync-data.plist.hand`。installer は削除か上書きをし、その内容は repo に無い）。次に望む構成の全フラグに `--sync-data` を足して `install-schedule` を実行し、次の 05:30 の前に退避したものと install 後の plist を diff する（特に `EnvironmentVariables`。テンプレートの PATH は `/opt/homebrew/bin` を `/usr/bin` より前に置くので、`rsync` / `git` / `hf` / credential helper が手で入れた plist と別の実体に解決されうる）。次の 05:30 の `sync:` commit が入ったことを確認する。以後フラグを省いた実行はジョブを外すので、フラグは owner が本番宣言として扱う行（P2-04.22）に入れておく。
