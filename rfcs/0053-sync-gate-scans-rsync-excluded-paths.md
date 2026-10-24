---
id: T-SYNC-GATE-SCANS-RSYNC-EXCLUDED-PATHS
title: sync の home-path ゲートが rsync 除外パス（`reports/.private/`）まで grep し、毎日の公開データ同期を止めている
state: done
state_since: 2026-10-17
origin: gate
admitted-by: unrecorded
filed_by: weekly-2026-10-16  # backfilled from the filing commit; the run time was not recorded
---

## タスク

RFC-0051 の home-path ゲートは公開データ repo の作業木全体を grep する（producer:
`scripts/sync-research-data.sh:136`）。一方、rsync の `--delete` ミラーは `reports/.private/` を除外している
（`scripts/sync-research-data.sh:103`）。除外パスにあるファイルは rsync で更新も削除もされず、
`scripts/rewrite_home_paths.py`（`MOLTBOOK_HOME` 側を書き換える）も届かない。2026-10-15T20:30Z 以降、
毎日の sync はこのパスの 1 ファイルでゲートに止められ、公開データ repo への commit が止まっている
（watchdog の sync-data 行が ❌）。ゲートが探す集合と `git add -A`（`:153`）が公開する集合を揃えるかどうかを
決める。先に前提を確かめる: 指名されたファイルが data repo で tracked / untracked（ignore されていない）/
ignored のどれか。前 2 つならゲートは正しく、直すのは data repo 側。

## 詳細

- 診断: `reports/analysis/weekly-2026-10-16-findings.md` の F1.2
- 観察: `reports/analysis/weekly-2026-10-16.md` の Exceptions 2
- Source quote（`logs/sync-data-launchd.log:13054`）: `Warning: sync failed: ERROR: the home path appears in
  files bound for the public data repo; not committing (RFC-0051):`（2 回、同じ 1 ファイル）
- 直前の成功: `Synced at 2026-10-14T20:30:06Z`（`:13047`）。`reports/PIPELINE-STATUS.md:10`:
  `❌ sync-data — no sync commit since 2026-10-16 05:30`
- RFC-0051（done）は 10-16 の watchdog の sync 行を確認先にしている（`rfcs/0051-public-artifacts-home-relative-paths.md:97`）
- 無人セッションは data repo の `git status` / `.gitignore` を読めないため、ファイルの追跡状態は未確認

## 2026-10-17 triage 照合（無人 cycle）

前提を確認した。指名されたファイルは公開データ repo で **ignored**（data repo の `.gitignore:3` の `.private` に当たる。`git ls-files` で `reports/.private/` 配下の tracked は 0）。`git add -A`（`scripts/sync-research-data.sh:153`）は ignored のファイルを公開しないので、ゲート（`:136` の `grep -r` は作業木全体を探す）が探す集合が公開される集合より広い — ゲートの偽陽性で、直すのはゲートの側。採否はオーナー（digest）。

## 2026-10-17 オーナー回答（triage digest）

`draft` → `accepted`。案 A を採用: ゲートが探す集合を、git が公開しうるファイル（`git ls-files --cached --others --exclude-standard`）に絞る。ignored のファイルは `git add -A` が運ばないので探さない。build は S43（cloud）。

Packet: [S43](../docs/plans/rfc-0053-s43-sync-gate-publishable-set.md)。

## 2026-10-17 S43 merge（判断役の検収）

`2997a79` を ff-only で main へ取り込んだ（cloud session、effort high → high、bounce は rebase 2 回 = gate・rebase。判断役が先に main へ入れた PR #11 と S44 の分）。

- ゲートが探す集合を `git -C "$DATA_REPO" ls-files -z --cached --others --exclude-standard` 1 か所にまとめ、中身の検索と symlink の検査の両方がそれを使う。大文字小文字の無視・`$HOME` の空 / `/` での停止・検索失敗での停止は残る。多数のファイルは `xargs` で分け、grep の「一致なし」と失敗を区別する
- 回帰テストは `tests/test_sync_research_data_shell.py` に 7 本（ignored の日本語名ファイル + symlink では止まらない、untracked で ignore されていないものと tracked のものは止まる、force-add したファイルは探す、作業木から消えた tracked ファイルで壊れない、一覧の失敗で止まる ほか）。既存 3 本は無変更
- CI は tip で success。判断役が macOS の `/bin/bash` 3.2 で同じテストファイルを走らせ 14 本 pass。本番の公開データ repo に同じ探し方を読み取りだけで当てて、該当 0 件
- ADR-0010 に dated amendment（2026-10-17）
- 次の読み: 2026-10-18 05:30 JST の sync が公開データ repo へ commit し、`reports/PIPELINE-STATUS.md` の sync-data 行が ✅ に戻る
