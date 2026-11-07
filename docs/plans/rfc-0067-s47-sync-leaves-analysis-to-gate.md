# Kickoff packet — S47: RFC-0067 P2-05.1（無人 sync は `reports/analysis/` を出さず、土曜ゲートが promote する）

あなたは task-triage loop の **build 役**です。
この session は GitHub の `shimo4228/contemplative-agent` main を clone した cloud session で、branch は
session が作った `claude/…`。成果はその branch への commit と push で返し、判断役が CI の結果と
commit 本文を読んで検収し、main へ ff-only 取り込みます。あなたが merge する経路はありません。
この packet が契約の全部です（外側に規約は無い）。Goal に要る作業は書いていなくても行い、Goal の外へ広がる
変更は Report の Proposed tasks に回す。

最初に読む: `rfcs/0067-public-surface-two-layer-promote.md`、`docs/decision-history/0010-research-data-sync.md`
（追補 2026-10-31「公開物を 2 層に分ける」と "Not in code yet" 行）、`scripts/sync-research-data.sh`、
`scripts/weekly-pipeline.sh`（`REPORT_DIR` の周辺）、`.claude/skills/weekly-gate/SKILL.md`（Step 6d と
report / approval の契約）、`tests/test_sync_research_data_shell.py`、`CLAUDE.md`（鮮度規約: 機構を変える
PR は所有 ADR と script 冒頭コメントを同じ PR で更新する）。

Effort: high — 公開境界の rsync（`--exclude` と `--delete` / retraction の相互作用）を動かす diff

## 進め方
- 入力が要らない step は止まらずに続ける。止まるのは Phase 0 の反証（記録して正しく直せる範囲を除く）、
  time cap、この packet の外の操作が要るときだけ
- 確かめられなかったことには「未確認」と印を付け、どこを見たかを書く
- 方針を選んだ箇所は、その理由を 3 文で Report の Fix に書く

## Goal（決定可能な受入条件）
1. 無人の `scripts/sync-research-data.sh`（promote 指定なし）は、データ repo の `reports/analysis/` に
   ファイルを足さず、既存のファイルを書き換えず、消さない。rsync の実転送で確かめるテストがあり、
   exclude を外すと落ちる（`tests/test_sync_research_data_shell.py` と同じ流儀）
2. 人間が名指した週次文書 1 本だけを公開面の `reports/analysis/` へ写す promote の経路がある
   （script の引数か小さな script。形は選んでよい、理由を Fix に書く）。名指しの無い文書は写らないことをテストが固定する
3. `.claude/skills/weekly-gate/SKILL.md` の公開 commit の段（Step 6d か、現行の契約で公開 commit を担う段）に、
   オーナーが週次文書を読んで promote する手順が 1 つ入っている（どの文書を・どのコマンドで・どの承認のあとに）
4. ADR-0010 の "Not in code yet" 行を外し、追補を実装に合わせる。`sync-research-data.sh` の冒頭コメントを更新する
5. `./.claude/verify.sh`（引数なし）が exit 0。判定は CI

## Phase 0 — 前提の再照合
- `scripts/sync-research-data.sh` の `PUBLIC_TOP_LEVEL` が `reports` を含み、`reports/analysis/` を除外して
  いないこと（2026-11-04 時点: 除外は `reports/.private/` と `/reports/comment-reports/` だけ）
- `scripts/weekly-pipeline.sh` が週次文書を `$MOLTBOOK_HOME/reports/analysis` に置くこと（`REPORT_DIR`）
- weekly-gate の現行版で、公開 commit を担う段がどこか（2026-11-01 の改訂で report と承認が 1 枚になった）
- 反証されたら実装せず止めて報告

## Build（順序）
1. 失敗するテストを先に書く（Goal 1・2）
2. 除外と promote を実装する。既に公開済みの `reports/analysis/` のファイルは残す（撤回は別の機構 — script の
   Retraction 節）。`--delete` が除外したパスを消さないことを、コメントでなくテストで確かめる
3. weekly-gate の手順・ADR-0010・script 冒頭コメントを同じ commit 群で更新する
4. `./.claude/verify.sh` を手元で事前確認（判定は CI）

## Review
- この session は review を起動しない。review は push の後、判断役が検収で別 process に回させる。
  報告の Review 行には「判断役の検収で review」と書く。他の reviewer も起動しない
- 省略・読み替えは可だが、報告に「逸脱: 何を・なぜ」と必ず名指しする。無言の逸脱は bounce される
- diff 外の気づきは `rfcs/` に書かない。再現手順を書けるものは `Proposed tasks`（最大 2 件）、書けないものは
  `Out-of-diff findings` に 1 行ずつ

## Must-not
- RFC-0067 の他の行（P2-05.2 / .3 / .8 / .9、P3-05.x、P0-03.6、P3-02.2）に手を広げない
- テストを弱めない・消さない・設定で黙らせない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない
- `git add -A` を使わない ; `rfcs/` の state は判断役が書く
- この packet のファイル（`docs/plans/rfc-0067-s47-sync-leaves-analysis-to-gate.md`）を編集しない
- PR は自動で開く。PR の本文・設定は触らない ; main や他の branch に push しない ; force push しない
- データ repo（`contemplative-agent-data`）に push しない（テストは一時ディレクトリで）
- time cap 90 分。超えたら打ち切って、そこまでの diff とテスト状況で報告

## Report（最終 commit の message 本文）
feat(sync): <summary> (RFC-0067)

Packet: S47
Plan: docs/plans/rfc-0067-s47-sync-leaves-analysis-to-gate.md
Needs from judge: <…/ none>
Model: <モデル名>
Effort: <実際に走った effort / 未確認>
Premise: <file:line 再照合の結果>
Fix: <what and why>
Regression: <test names, RED→GREEN>
Verify: <command exit / test counts>
Review: 判断役の検収で review / Deviations: <none か名指し>
Risk: <戻し方>
Proposed tasks (for the judge, 最大 2 件): <none か各件>
Out-of-diff findings (for the judge): <none か 1 行ずつ>

最後のメッセージは「判断役に要るもの」から始め、branch 名・push した commit SHA・verify の結果・所要時間を
報告して終了してください。前提が崩れて実装しなかったときも同じ形で報告してください。
