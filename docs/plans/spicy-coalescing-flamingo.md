# T-LOGROT-OLLAMA — ollama-serve.log のローテーション

## Context

守りたいのは**エピソードログ（削除禁止の研究材料）のオフサイト退避経路**であって、ログの容量ではない。
今その経路を止めにきているのが `~/.config/moltbook/logs/ollama-serve.log`。

再測定（2026-08-01）:

| 項目 | 値 | 出典 |
|---|---|---|
| `ollama-serve.log` | **96.5 MB**（台帳の 92MB より進行） | `ls -laS ~/.config/moltbook/logs/` |
| 増加率 | 約 2.7 MB/日（34 日で 1,044,145 行） | 別セッション診断 |
| 週次 backup | 月曜 01:00（直近 07/27、手動 08/01 08:08Z） | backup repo の commit 履歴 |
| 現状の push | **既に警告付きで通っている** | `logs/backup-launchd.log` 末尾の `remote: warning: File logs/ollama-serve.log is 75.95 MB ...` |

**実質の締切は「3 日後」ではなく次の定期 backup（8/3 01:00）**。その時点で約 100MB に達し、
GitHub のハード上限に当たって `git push` が落ちる → `scripts/backup-runtime.sh` が
`ERROR: push failed` で終わり、オフサイトコピーが止まる。

原因は診断通り**無ローテーション**（`com.moltbook.ollama-restart` が `>>` で追記し続ける）。
副因の verbosity=4 はこの変更に混ぜない（ADR-0053 Decision 6「パイプラインの変数は一度に一つ」。
台帳行は ADR-0056 を引いているが、原則の正本は ADR-0053 側 — 台帳更新時に直す）。

着手順の制約（macOS 26.6 更新後）は launchd / Ollama に触る変更にのみ効く。そこで
**締切外し（backup 側）と再発防止（launchd 側）を 2 段に割る**。

## Stage A — 締切を外す（macOS 更新を待たない / launchd に触らない）

ollama の server log は llama.cpp の運用ノイズであり、backup が守ると宣言している
「かけがえのない研究データ（episode logs, audit trails）」ではない。再生成可能な運用ログが
オフサイト退避のゲートを人質に取っている状態そのものを解く。

**変更 1: `scripts/backup-runtime.sh`**

- rsync の exclude に `--exclude='/logs/ollama-serve.log*'` を追加（先頭 `/` で転送ルートに
  アンカーする。既存の `credentials.json` 等は非アンカーだが、ここは `logs/` 直下だけを狙う）。
  `*` によりのちの世代（`.1.gz` 等）も同時に対象。
- ヘッダーコメントの `Excluded:` 一覧に理由付きで 1 項目追加（このファイルは除外の根拠を
  すべて列挙する規約になっている）。
- rsync 後に belt-and-suspenders を 1 行（`credentials.json` の `rm -f` と同型・同じ理由）:
  `--exclude` は `--delete` から**退避先のコピーも守ってしまう**ため、既に mirror にある
  96MB のコピーは自然には消えない。`rm -f "$BACKUP_REPO"/logs/ollama-serve.log*` を置けば
  直後の `git add -A` が削除を staging し、以後は自己修復する（手動 `git rm` を残さない）。

**しないこと**: backup repo の履歴書き換え（filter-repo 等）。既存 blob は `.git` に残るが
(293MB)、上限に効くのは**新規 push される blob** なので push は通る。履歴の破壊的書き換えは
本件の必要条件ではなく、可逆性の桁が違う。

**変更 2: `tests/test_backup_runtime_shell.py`（新規・回帰固定）**

`tests/test_weekly_pipeline_shell.py` / `test_weekly_analysis_shell.py` と同じ流儀
（tmpdir に MOLTBOOK_HOME と bare remote を組み、`gh` をスタブして実スクリプトを起動）で:

- `logs/ollama-serve.log` と `logs/ollama-serve.log.1.gz` を置いた HOME を backup しても、
  mirror にそれらが**現れない**
- mirror に予め置いた `logs/ollama-serve.log` が**削除される**（belt-and-suspenders の検証）
- 既存の除外対象（`credentials.json`）と episode log（`logs/2026-01-01.jsonl`）の扱いが
  変わっていない ← 除外パターンの巻き込み事故を止める列

**変更 3: `docs/CONFIGURATION.md`**

backup の段落（`logs/` も含めて mirror する、と書いてある箇所）に例外を 1 文追記。

## Stage B — 再発防止（macOS 26.6 更新後）

**変更 4: `scripts/rotate-log.sh`（新規）**

```
rotate-log.sh <path> <keep-N>
```

- 対象が無い / サイズ 0 なら何もせず exit 0
- `.N` を捨て、`.N-1 → .N` … `.1 → .2` とずらし、本体を `.1` へ `mv` して `gzip`
- **中身を一切読まない**（`head` / `grep` / `tail` を使わない）。verbosity 4 の llama.cpp ログは
  プロンプト断片を含みうるので、ローテーション機構自体を読み取り経路にしない
- `set -euo pipefail` + `shellcheck -S style` clean（`.claude/verify.sh` が全 `*.sh` を検査する）

**変更 5: plist（live + tracked template の両方）**

`pkill` 後・`ollama serve` 起動前にローテートを挟む。既に fd が閉じているので `mv` は安全:

```
pkill ...; pkill ...; sleep 30; \
  {{PROJECT_ROOT}}/scripts/rotate-log.sh {{LOG_DIR}}/ollama-serve.log 7; \
  /usr/local/bin/ollama serve >> {{LOG_DIR}}/ollama-serve.log 2>&1 & ...
```

- `~/Library/LaunchAgents/com.moltbook.ollama-restart.plist`（実体）と
  `config/launchd/com.moltbook.ollama-restart.plist`（追跡テンプレート）を**同じ変更で**更新
  — テンプレート冒頭のコメントがそう定めている。テンプレートには `{{PROJECT_ROOT}}` を追加
- ついでに既存 drift を解消: live には `RunAtLoad true` があるがテンプレートに無い。テンプレート側に足す
- 追加文字列に `&` `<` `>` を含まないので XML エスケープの新規リスクなし（これはローテーションを
  plist にインライン展開しない理由でもある。下の Alternatives 参照）
- 反映は `launchctl unload && launchctl load`（`install-schedule` はこの job を管理しない）

**変更 6: `.notes/TASKS.md`**

- T-LOGROT-OLLAMA を Done へ（実測値と、ADR-0053 が原則の正本である旨を添えて）
- T-LOG-DEBUG-CONTENT に**締切を追記** — `agent-launchd.log` は 74.6MB・週 +10MB で
  2〜3 週後に 100MB。「セキュリティの宿題」だけでなく「push が落ちる期限つき」になった
- verbosity 引き下げ検討を新規行として登録（`observing` — ローテーション 1 週分の効き方を見てから）

**変更 7: `docs/CONFIGURATION.md`** — ollama-restart の段落に「N=7 世代でローテートする」を 1 文。

## なぜこの置き場所か / 何を落としたか

| 候補 | 判定 |
|---|---|
| **`com.moltbook.ollama-restart` から `scripts/rotate-log.sh` を呼ぶ**（採用） | この job が既に毎日 23:55 に走り、`pkill` でファイルを解放し、`>>` でこのログを作っている **= ライフサイクルの所有者**。新しい起動機構も順序調整も要らない。ロジックを `scripts/` の追跡ファイルに置けば diff でレビューでき、pytest（既存の shell テスト流儀）と shellcheck の両方が既に配線済みの検査面に載る |
| plist の `bash -c` にローテーションをインライン展開 | 却下。`&&` / `>` / `[` が入ると XML エスケープが増え、**壊れても静かに壊れる**（hooks の JSON エスケープで同じ失敗をしている領域）。テストからも呼べない |
| `newsyslog`（macOS 標準）/ `logrotate` | 却下。`/etc/newsyslog.d/` は root 権限で repo の外に住み、clone 先に付いてこない。設定が project の可視範囲から消え、`AbandonProcessGroup` な daemon の再起動タイミングとも独立に走る。既存解の採用より**所有者との不整合コストの方が高い** |
| ローテーション専用の launchd job を新設 | 却下。restart job と同時刻に走らせる必要があり、順序保証が無い（走行中に `mv` すると新プロセスが旧 inode に書き続ける）。所有者が既にいるのに 2 つ目の時計を足す形 |
| `>>` を `>` に変える（起動時に切り詰め） | 却下。1 行で済むが世代がゼロになる。23:55 より前に起きた不調の証拠が毎晩消える（Reversibility Gate: 消すのではなく回す） |
| weekly-pipeline / watchdog に相乗り | 却下。粒度が合わない（週次では 19MB 溜まる）し、この 2 つはログのライフサイクルを所有していない |
| backup から外すだけで終える | 部分採用（Stage A）。push は救えるが**ディスク上は無限に増える**（年 1GB）ので再発防止にならない。単独では解にならず、締切外しとしてのみ採る |

Phase 0（外部解の調査）は planning.md の「省略してよい」区分（設定変更・バグ修正）に該当するため
skill 呼び出しは行わず、既存解の検討は上表の `newsyslog` / `logrotate` 行に記録した。新規依存は追加しない
（`mv` / `gzip` のみ）。

## 世代数と圧縮の根拠

- 実測: `head -c 20971520 ollama-serve.log | gzip -6 -c | wc -c` → **20.0MB → 1.98MB（10.6 倍）**
- 日次 2.7MB → 圧縮後 約 0.26MB/世代。**N=7 で常駐 約 1.8MB + 当日分 約 2.7MB**
- 現存の 96.5MB は、初回実行で自動的に `.1.gz`（約 9MB）に畳まれる。手動の前処理は不要
- 圧縮世代は `*.log` に一致しないので `scripts/log_anomaly_sweep.py` の走査対象から外れる。
  sweep が見るべきは現行ファイルなので意図通り

## Verify

Stage A（変更直後）:

1. `bash scripts/backup-runtime.sh` を前景で 1 回 — 完走し、出力に
   `File logs/ollama-serve.log is ... MB` の warning が**出ない**こと
   （`agent-launchd.log` の warning は残る = 想定内。合格条件は ollama 分のみ）
2. `git -C ~/MyAI_Lab/contemplative-agent-runtime-backup ls-files logs/ | grep ollama` が空
3. episode log（`logs/YYYY-MM-DD.jsonl`）と `reports/` が mirror に**残っている**こと ← 除外の巻き込み確認

Stage B（macOS 26.6 更新後）:

4. `bash scripts/rotate-log.sh` を tmpdir の偽ファイルで手動実行 → 世代がずれ、N+1 本目が消える
5. `launchctl unload/load` 後、23:55 の定期実行を 2 晩見る:
   `ls -la ~/.config/moltbook/logs/ollama-serve.log*` で本体が 3MB 前後に**頭打ち**、`.1.gz` 〜 が積む
6. `.claude/verify.sh`（引数なし・全体）が PASS — shellcheck が新規 `.sh` を、pytest が新規テストを見る

## Chain（種別: fix）

Plan 承認 → TDD（Stage A の回帰テストを先に書く）→ 実装 → Review 群
（code-reviewer / security-reviewer / **codex-review** — fix は必須）→ Doc Sync
（CONFIGURATION.md / TASKS.md）→ Verify → 意図確認 → 単一 commit。

ADR は起こさない（アーキテクチャ判断ではなく運用欠陥の修正。「何をバックアップするか」の
方針は `backup-runtime.sh` のヘッダーが既に正本として持っており、そこに追記する）。

## スコープ外（同じ diff に混ぜない）

- **verbosity 4 の引き下げ** — ADR-0053 の一変数規律。ローテーション 1 週分の効き方を見て別途判断
- **`agent-launchd.log`** — T-LOG-DEBUG-CONTENT の管轄。同 task が「ローテーションを先にやるな
  （静的調査の証拠が消える）」と保留しているので触らない。ただし push 締切ができたことを台帳に追記する
- **backup repo の履歴書き換え** — 上限に効くのは新規 blob なので不要
