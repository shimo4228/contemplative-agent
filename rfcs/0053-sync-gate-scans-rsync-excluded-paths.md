---
id: T-SYNC-GATE-SCANS-RSYNC-EXCLUDED-PATHS
state: draft
state_since: 2026-10-17
origin: gate
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
