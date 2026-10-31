# Kickoff packet — S46: RFC-0063（census が distill 処理台帳の行を時刻なしとして数える）

あなたは task-triage loop の **build 役**です。
この session は GitHub の `shimo4228/contemplative-agent` main を clone した cloud session で、branch は
session が作った `claude/…`。成果はその branch への commit と push で返し、判断役が CI の結果と
commit 本文を読んで検収し、main へ ff-only 取り込みます。あなたが merge する経路はありません。
この packet が契約の全部です（外側に規約は無い）。Goal に要る作業は書いていなくても行い、Goal の外へ広がる
変更は Report の Proposed tasks に回す。

最初に読む: `rfcs/0063-census-distill-ledger-ts.md`、`CLAUDE.md` の「開発原則」節（Immutability・テストの規約・
改名は 1 PR で閉じる）、`src/contemplative_agent/core/distill_ledger.py`、`scripts/_census_registry.py`（`Entry` の定義と
`distill-processed.jsonl` の登録行、窓の行を集める関数）、`tests/test_distill_ledger.py`、`tests/test_instrument_census.py`。

Effort: high — 既存の計器と書き手の境界を動かす brownfield の fix

## 進め方
- 入力が要らない step は止まらずに続ける。状況メモは次の行動と同じメッセージに書く。止まるのは Phase 0 の
  反証（記録して正しく直せる範囲を除く）、Review の CRITICAL、time cap、この packet の外の操作が要るときだけ
- 確かめられなかったことには「未確認」と印を付け、どこを見たかを書く
- 方針を選んだ箇所は、その理由を 3 文で Report の Fix に書く

## Goal（決定可能な受入条件）
1. `distill-processed.jsonl` の実形の行（`{"episode_id": "<id>", "processed_at": "2026-10-25T19:05:17+00:00", "run_id": "<id>"}`
   と、`run_id` の無い `{"episode_id", "processed_at"}` の 2 形）が、census の窓内に置かれたとき **窓内 1 行**として数えられ、
   `rows_without_ts` に入らないことを示す回帰テストがある（RED→GREEN を Report に書く）
2. 直し方は次のどちらか 1 つを選ぶ（両方はしない）。選んだ理由を Fix に 3 文で書く:
   - (a) 書き手 `record_processed` が行に `ts` も書く。読み手 `read_processed_ids` の挙動は変えない。既存の `ts` 無しの行
     （本番に 407 行以上ある）も census が数えられる必要があるので、(a) を選ぶ場合も **既存行が数えられること**を Goal 1 の
     テストで示す（= 結局 census 側の対応が要るなら (b) を選ぶ方が筋）
   - (b) census の `Entry` に時刻欄名のフィールド（既定 `"ts"`）を足し、`distill-processed.jsonl` の登録行だけ `processed_at`
     を指す。他の登録行の挙動は変えない
3. `./.claude/verify.sh`（引数なし）が exit 0。CI が push ごとに同じ verify.sh を走らせ、判定は CI

## Phase 0 — 前提の再照合（反証されたら実装せず止めて報告。ただし「反証を記録して正しく直す」が
できる範囲なら、その判断も報告に書く）
- 書き手は `{"episode_id", "processed_at"}` だけを書く（`src/contemplative_agent/core/distill_ledger.py:111` 付近の
  `append_jsonl_restricted` 呼び出し）
- census は窓の時刻を `rec.get("ts")` からしか取らない（`scripts/_census_registry.py:370` 付近）
- 登録行は `scripts/_census_registry.py:221` 付近の `Entry("distill-processed.jsonl", "ADR-0060")`
- 台帳を読む本体側のコードは `read_processed_ids` だけで、`episode_id` しか見ない（`grep -rn processed_at src scripts tests`
  で確かめる）

## Build（順序）
1. 失敗するテストを先に書く（Goal 1）。テストは理由コード・構造化レコード（`Reading` の `rows` / `rows_without_ts`）に assert し、
   出力の文言に assert しない
2. 実装。DTO は `frozen=True` のまま。改名・互換 alias は入れない
3. `./.claude/verify.sh` を走らせて事前確認（判定は CI）

## Review
- 実装後・commit 前に built-in `/code-review` を **effort `medium`**（review の段階。この session の Effort とは別）で 1 回、この diff の範囲で起動する。
  reviewer への指示（そのまま渡す）:「correctness / stated requirements に効く gap のみ報告し、各指摘に
  file:line・なぜ誤りか・失敗を示す手順を付ける。それ以外（防御的コード・追加の抽象層・起こり得ないケースの
  テスト等）は optional として報告し、適用しない。diff 外の指摘は 1 行のみ、修理はしない」。CRITICAL が出たら直さず止めて報告する。
- これ以外の reviewer は起動しない（security 等の判断は判断役が持つ）。
- 省略・読み替えは可だが、報告に「逸脱: 何を・なぜ」と**必ず名指し**する。無言の逸脱は結果が正しくても
  bounce される
- diff 外の気づきは `rfcs/` にも台帳にも書かない。再現手順を書けるものは Report の `Proposed tasks`
  （最大 2 件）に、書けないものは `Out-of-diff findings` に 1 行ずつ（HIGH は producer `file:line` 付き）置く

## Must-not（境界 = Goodhart 対策）
- 触ってよいのは `src/contemplative_agent/core/distill_ledger.py`、`scripts/_census_registry.py`、`scripts/instrument_census.py`
  （必要なら）、`tests/test_distill_ledger.py`、`tests/test_instrument_census.py`、新規のテストファイル 1 本まで。docs / ADR は触らない
- テストを弱めない・消さない・設定で黙らせない。既存テストの assert を変える必要が出たら変えずに止めて報告
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない
- `git add -A` を使わない ; 台帳（`rfcs/` の state）の状態は判断役が書く
- この packet のファイル（`docs/plans/rfc-0063-s46-census-distill-ledger-ts.md`）を編集しない — dispatch 時点で凍結した契約
- PR は自動で開く。PR の本文・設定は触らない ; main や他の branch に push しない ; force push しない
- 90 分を超えたら打ち切って、そこまでの diff とテスト状況で報告

## Report（最終 commit の message 本文 = session が閉じても残る唯一の証拠）
fix(census): <summary> (RFC-0063)

Packet: S46
Plan: docs/plans/rfc-0063-s46-census-distill-ledger-ts.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Model: <この session のモデル名。途中でモデルが切り替わった通知が出たらその旨>
Effort: <この session が実際に走った effort — 環境変数 `CLAUDE_EFFORT` か `/effort` の表示。分からなければ「未確認」>
Premise: <file:line 再照合の結果、反証があればそれ>
Fix: <(a) か (b) か、何を・なぜ（3 文）>
Regression: <test names、RED→GREEN の確認方法>
Verify: <command exit / test counts / 日時。CI の判定は判断役が読む>
Review: </code-review medium の結果（findings 件数と対応）> / Deviations: <逸脱の名指しと理由、無ければ none>
Risk: <とったリスク / 戻し方（1 分で戻せるか）>
Proposed tasks (for the judge, 最大 2 件): <各件: 何が壊れているか / 再現手順（コマンド → 期待と実際）/
  決定可能な受入条件 / producer file:line — 無ければ none。再現手順は branch の tip で走る 1 コマンドにし、commit しない>
Out-of-diff findings (for the judge): <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・push した commit SHA・verify の結果・所要時間を報告して終了してください。
前提が崩れて実装しなかったときも同じ形で報告してください。
