# Kickoff packet — S42: RFC-0051（公開物に残るローカル絶対パスを MOLTBOOK_HOME 相対に、sync に検出ゲート）

あなたは task-triage loop の **build 役**です。
cwd は `contemplative-agent` の git worktree（branch `task/s42-home-paths`）。成果は branch 上の commit で返し、
判断役が検収して main へ ff-only 取り込みます。境界（人間に渡す操作 / とってよいリスク / 止まる
条件）は rule `boundary.md` — build は task branch まで。packet に無いことは harness の規約が既定。

最初に読む: `rfcs/0051-public-artifacts-home-relative-paths.md`（全文。Status の「2026-10-15 オーナー回答」が仕様）、
`rfcs/0050-snapshot-manifest-home-relative-paths.md` の Status（同じ形の先例）、commit `1637962`
（`src/contemplative_agent/core/snapshot.py` の `_absolute` / `_relative_to` / `_portable_path`）、
repo の CLAUDE.md「開発原則」「セキュリティ方針」（episode log 直読み禁止）。

Effort: high — brownfield の fix と、公開経路のゲート（sanitizer 型の検出）を同時に動かす diff

## 進め方
- 入力が要らない step は止まらずに続ける。状況メモは次の行動と同じメッセージに書く。止まるのは Phase 0 の
  反証（記録して正しく直せる範囲を除く）、Review の CRITICAL、time cap、この packet の外の操作が要るときだけ
- 確かめられなかったことには「未確認」と印を付け、どこを見たかを書く
- 方針を選んだ箇所は、その理由を 3 文で Report の Fix に書く
- 手順が 10 を超えるので、チェックリストを commit しないファイル（`/tmp/s42-tasks.md`）に置き、終えた項目に印を付ける

## Goal（決定可能な受入条件）
1. **書き手の修正**: 次の書き手が home の絶対パスを書かない（`MOLTBOOK_HOME` 相対、外は home を `~` に置換。
   RFC-0050 の `_portable_path` と同じ規則。共有するなら 1 箇所に置き、scripts から import できる場所を選ぶ）。
   それぞれに「出力全体に `str(Path.home())` が出ない」テストを足す:
   - `scripts/value_layer_due_check.py:173, 219`（`"path"`）
   - `src/contemplative_agent/core/skill_confusion.py:729`（`Candidate file:`）
   - `scripts/pipeline_watchdog.sh:189`（失敗時の `Logs:` 行。bash のまま — 冒頭の HARD CONSTRAINT を守る）
   - `scripts/novelty_retrieval_dry_run.py:438, 463, 466, 580-581` と `scripts/relevance_label_set.py:368`
2. **sync の検出ゲート**: `scripts/sync-research-data.sh` が、rsync と knowledge.json の再生成の後・`git add` の前に、
   公開データ repo の作業木（`.git/` を除く）を home の絶対パスで検索し、1 件でもあれば該当ファイル名（中身は出さない）を
   stderr に出して非 0 で終わる。書き換えはしない。`tests/test_sync_research_data_shell.py` に「漏れあり → 非 0 で
   commit しない」「漏れなし → 従来どおり」の 2 本を足す
3. **sync の停止を見えるようにする**: `scripts/pipeline_watchdog.sh` に sync の行を足す（例: 公開データ repo の最後の
   `sync:` commit の時刻が期待より古ければ FAIL）。期待間隔の根拠を script のコメントに書く。sync は agent session の後に
   best-effort で走り、失敗は stderr の警告だけ（`src/contemplative_agent/cli/session_cmds.py:28-42`）なので、ここが唯一の
   見張りになる
4. **過去のファイルの一回限りの書き換え**: `scripts/` に書き換えスクリプトを 1 本置く。既定は dry-run（対象ファイル名と
   置換件数だけを出す）、`--apply` で書き換える。対象は `MOLTBOOK_HOME` の、公開 sync が運ぶファイルのうち home の
   絶対パスを含むもの（`reports/analysis/`、`pipeline/value-layer/`、`snapshots/*/manifest.json` を含む。sync の exclude と
   同じ集合を使う）。置換は文字列としての home → `~`。JSON はパース後に値を置換して書き戻すか、文字列置換で JSON として
   壊れないことを検査する。**このスクリプトはテストの tmp ディレクトリと dry-run でだけ走らせる**（`--apply` は merge 後に
   判断役が実行する）
5. **凍結済みの証拠 3 本**: `docs/evidence/rfc-0023/novelty-retrieval-dry-run-20260904.json`、
   `docs/evidence/rfc-0023/novelty-replay-ab-20260905.json`、`docs/evidence/rfc-0017/comment_golden-skills-off-20260902.json`
   の home の絶対パスだけを `~` 置換する（数値・判定・他の文字列は 1 バイトも変えない — diff がパスの行だけであること）。
   書き換えた事実を `docs/evidence/rfc-0051-path-rewrites.md` に 1 ファイル 1 行で残す（どのファイルの、どの列か、日付、RFC-0051）
6. 機構の記述: sync のゲートと watchdog の sync 行は、CLAUDE.md の鮮度規約に従い、所有 ADR への追補と該当 script の冒頭コメントを
   同じ変更で更新する（所有 ADR は自分で特定し、Report に名指す。ADR-0020 は RFC-0050 で追補済み）
7. `./.claude/verify.sh`（引数なし）exit 0

## Phase 0 — 前提の再照合（反証されたら実装せず止めて報告。ただし「反証を記録して正しく直す」が
できる範囲なら、その判断も報告に書く）
- Goal 1 の各 `file:line` がまだ絶対パスを書くこと
- `scripts/sync-research-data.sh:76-107` の rsync が `pipeline/` と `reports/analysis/` を運び、`logs/` を除外すること
- `scripts/pipeline_watchdog.sh` が sync を見ていないこと（`grep -i sync`）
- 書き換え対象の数を dry-run で数える（判断役の 2026-10-14 の読み: `pipeline/` 7、`reports/` 10、`snapshots/` 97）。
  `MOLTBOOK_HOME` は **読むだけ**。`logs/episodes/` は対象外で、開かない

## Build（順序）
1. TDD: Goal 1 / 2 のテストを先に書き、RED を確かめる
2. 実装。正規化は 1 箇所で行う
3. Goal 4 のスクリプトを tmp ディレクトリのテストで確かめ、本番の `MOLTBOOK_HOME` には dry-run だけを走らせて件数を Report に書く
4. Goal 5、6
5. verify: `./.claude/verify.sh` 引数なし exit 0

## Review
- 種別: fix。**chain は skill `implementation-chain` の Chain Matrix に従う**（この packet は reviewer を列挙しない —
  列挙漏れは省略の許可ではない）。加えて security-reviewer を走らせる — 公開経路のゲートを足すため
- **packet に書いていないことは harness の規約が既定**（implementation-chain / task-tracking / security）。省略・読み替えは可だが、
  報告に「逸脱: 何を・なぜ」と**必ず名指し**する。無言の逸脱は結果が正しくても bounce される
- diff 外の気づきは `rfcs/` にも台帳にも書かない。再現手順を書けるものは Report の `Proposed tasks`
  （最大 2 件）に、書けないものは `Out-of-diff findings` に 1 行ずつ（HIGH は producer `file:line` 付き）置く

## Must-not（境界 = Goodhart 対策）
- `~/.config/moltbook`（`MOLTBOOK_HOME`）と公開データ repo（`~/MyAI_Lab/contemplative-agent-data`）に書かない。
  sync スクリプトを本番の引数で実行しない。書き換えスクリプトの `--apply` を本番に向けない
- `logs/episodes/` と `logs/agent-launchd.log` を読まない（CLAUDE.md）
- テストを弱めない・消さない・設定で黙らせない。既存テストの assertion を変えるときは、変えた理由を Report に名指す
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない
- `git add -A` を使わない ; 台帳（`rfcs/` の state）は判断役が書く
- この packet のファイルを編集しない — dispatch 時点で凍結した契約
- branch を push しない（判断役が merge 時に main と一緒に push する）
- JST 0 / 6 / 12 / 18 時の agent session と重なる時間に Ollama を使う重い処理を走らせない（この task は Ollama を要らないはず）
- time cap 3 時間。超えたら打ち切って、そこまでの diff とテスト状況で報告

## Report（最終 commit の message 本文）
fix(privacy): <summary> (RFC-0051)

Packet: S42
Plan: docs/plans/rfc-0051-s42-home-relative-paths.md
Needs from judge: <--apply の実行手順（コマンド 1 行）と、merge から実行までに守る順序 / その他>
Model: <この session のモデル名。途中でモデルが切り替わった通知が出たらその旨>
Effort: <この session が実際に走った effort。分からなければ「未確認」>
Premise: <file:line 再照合の結果、反証があればそれ>
Fix: <what and why>
Regression: <test names, RED→GREEN の確認方法>
Dry-run: <書き換えスクリプトの本番 dry-run の件数（ディレクトリ別）>
Verify: <command exit / test counts / 日時>
Review: <chain どおりに回した reviewer と結果> / Deviations: <逸脱の名指しと理由、無ければ none>
Risk: <とったリスク / 戻し方>
Proposed tasks (for the judge, 最大 2 件): <none か、各件: 何が壊れているか / 再現手順 / 受入条件 / producer file:line>
Out-of-diff findings (for the judge): <severity + 1 行ずつ / none>

最後のメッセージは「判断役に要るもの」から始め、commit SHA・verify の結果・所要時間を報告して終了してください。
前提が崩れて実装しなかったときも同じ形で報告してください。
