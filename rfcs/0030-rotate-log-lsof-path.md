---
id: T-ROTATE-LOG-LSOF-PATH
state: accepted 2026-09-12
state_since: 2026-09-12
origin: gate
---

## タスク

`rotate-log.sh` の open-writer ガードが、repo 自身の launchd PATH によって無人経路でだけ無効化されて
いる。`config/launchd/com.moltbook.backup.plist:22` は
`PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin` を設定していて `/usr/sbin` を含まない。macOS の
`lsof` は `/usr/sbin/lsof`（本ホストに存在を確認）なので、`scripts/rotate-log.sh:63` の
`command -v lsof` は常に失敗し、:69 の警告枝を通って**毎週の rotation が open-writer 検査なしで走る**。
この job からの呼び出し元は `scripts/backup-runtime.sh:55`（`logs/agent-launchd.log` を 8 世代で回す）。
対する `config/launchd/com.moltbook.ollama-restart.plist` は `PATH` を設定せず、継承した PATH が
`lsof` を解決するため同じ script がそちらでは守られている — 週 1 回ペース（Δ +1/window）は
weekly の backup job と一致し、nightly の restart job とは一致しない。

producer: `scripts/rotate-log.sh:69`（警告の発火点） / `config/launchd/com.moltbook.backup.plist:22`（原因）

## 詳細

診断 F1.1（`weekly-2026-09-11-findings.md`）。Source quote は Log Anomaly Sweep の
`warning: rotate-log.sh: lsof not found — rotating without the open-writer check` 6 (Δ +1)。

守られていない不変条件は `scripts/rotate-log.sh:59-62` が自ら書いている:
「grace period を越えて生き残った daemon が、gzip が読んでいる最中に rename 済みの inode へ書き続け、
rotation が守るはずの証拠を、どの path も指さないファイルへ truncate する」。回している対象が
`agent-launchd.log` — CLAUDE.md が「rotation で置き換わるまで読むな」と指定しているファイル自身である
ことも、この検査が効いていることの利害に入る。

選択肢（どちらも検査そのものは変えない）:

- backup job の `PATH` に `/usr/sbin` を戻す（最小差分。`com.moltbook.backup.plist` と installer 側の
  テンプレートを同じ PR で）
- `rotate-log.sh` が `command -v` の miss 時に既知の絶対パスを 1 つ試してから警告枝へ落ちる
  （host 非依存。`tests/test_rotate_log_shell.py` に PATH を剥いだ回帰を置ける）

既存の警告枝は `lsof` を本当に持たない host のための最終手段として残す。

先例: commit `63ac8e8`（T-LOGROT-OLLAMA、2026-08-01 done）が ollama-restart job 向けに
この検査を入れた経緯（review 指摘 iii）を持つ。本件はその後 `backup-runtime.sh` が同じ script を
PATH 制限付き plist 下で再利用したことで開いた隙間で、台帳・ADR に同じ介入の記録は無い
（`rg lsof` は repo 内で script / tests / runbook / CONFIGURATION.md のみ）。

## 2026-09-12 triage 照合（無人 cycle）

`draft` 維持。premise を main HEAD（`347b913`）で再照合し成立（`publish.py::client_error_guard` は message 全文を logger.error へ渡すのみ / `com.moltbook.backup.plist` の PATH に `/usr/sbin` 無し、`/usr/sbin/lsof` 実在）。採否は著者判断（digest に提示）。

## 2026-09-12 決定（著者回答）

`draft` → `accepted`。S11 として dispatch（RFC-0035 と同梱、worktree `task/s11-small-fixes`）。
