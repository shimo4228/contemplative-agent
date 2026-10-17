# Kickoff packet — S44: RFC-0052（insight の description / name コールに axioms だけの system prompt を渡す）

あなたは task-triage loop の **build 役**です。
この session は GitHub の `shimo4228/contemplative-agent` main を clone した cloud session で、branch は
session が作った `claude/…`。成果はその branch への commit と push で返し、判断役が CI の結果と
commit 本文を読んで検収し、main へ ff-only 取り込みます。あなたが merge する経路はありません。
この packet が契約の全部です（外側に規約は無い）。Goal に要る作業は書いていなくても行い、Goal の外へ広がる
変更は Report の Proposed tasks に回す。

最初に読む: `rfcs/0052-insight-description-call-full-system-prompt.md`（全文。「2026-10-17 オーナー回答」が仕様）、
`src/contemplative_agent/core/insight.py`（本文コール `:270-285` 付近、`_ask_json_field` `:313-345` 付近、
`_write_description` / name の関数）、`src/contemplative_agent/core/llm/__init__.py` の `generate_full` と
`_build_system_prompt` / `get_distill_system_prompt`、`docs/adr/0111-insight-entrance-stages.md`、
`docs/adr/0058-*.md`（蒸留時に値層を注入しない）、`tests/test_insight.py`、`tests/test_insight_abstain.py`。

Effort: medium — 1 引数を足す brownfield の fix で、edge case は少ない

## 進め方
- 入力が要らない step は止まらずに続ける。状況メモは次の行動と同じメッセージに書く。止まるのは Phase 0 の
  反証（記録して正しく直せる範囲を除く）、Review の CRITICAL、time cap、この packet の外の操作が要るときだけ
- 確かめられなかったことには「未確認」と印を付け、どこを見たかを書く
- 方針を選んだ箇所は、その理由を 3 文で Report の Fix に書く

## Goal（決定可能な受入条件）
1. `insight.description` と `insight.name` のコールが、本文コール（`insight.skill_extract`）と同じ
   `llm.get_distill_system_prompt()` を `system=` に渡す。`generate_full` の既定（`system=None` → identity・axioms・skill 全文・rules を
   入れる既定の system prompt）に落ちる経路が insight のコールに残らない
2. 回帰テスト: description と name のコールそれぞれについて、`generate_full` に渡った `system` が
   `get_distill_system_prompt()` の値と等しく、`None` でないことを確かめるテストを足す。テストは、既定の system prompt を
   大きな文字列に差し替えても description / name のコールがそれを受け取らないことで RED → GREEN が見える形にする
3. 既存のテストは assertion を変えずに通る。`FAULT_ABSTAIN_REASONS` と abstain の理由コードは変えない
4. 機構の記述: `docs/adr/0111-insight-entrance-stages.md` と `.ja.md` に dated note（2026-10-17、RFC-0052）を足し、
   description / name のコールが axioms だけの system prompt で走ること、理由（既定の system prompt が約 10 万文字になり、
   context-budget の事前検査で skip されて、名乗り `new` が一度も staging まで届いていなかった）を書く。
   `_ask_json_field` の docstring にも 1 行で書く
5. `./.claude/verify.sh`（引数なし）exit 0。CI が push ごとに同じ verify.sh を走らせる — 判定は CI

## Phase 0 — 前提の再照合（反証されたら実装せず止めて報告。ただし「反証を記録して正しく直す」が
できる範囲なら、その判断も報告に書く）
- `core/insight.py` の `_ask_json_field` が `llm.generate_full(...)` に `system=` を渡していないこと
- 本文コールが `system=llm.get_distill_system_prompt()` を明示していること
- `generate_full` が `system=None` のとき既定の system prompt を組むこと（`core/llm/__init__.py` の `_build_system_prompt`）
- insight の中で、ほかに `system=` を渡さずに `generate_full` / `generate` を呼ぶコールがあるか（あれば Report の Premise に列挙し、
  insight の名乗り・新規性判定など、同じ理由で axioms だけにすべきか判断に迷うものは直さず `Proposed tasks` に回す）

## Build（順序）
1. TDD: Goal 2 のテストを先に書き、RED を確かめる
2. 実装（`_ask_json_field` で 1 箇所）
3. Goal 4
4. verify: `./.claude/verify.sh` 引数なし exit 0

## Review
- 実装後・commit 前に built-in `/code-review` を **effort `medium`**（review の段階。この session の Effort とは別）で 1 回、この diff の範囲で起動する。
  reviewer への指示（そのまま渡す）:「correctness / stated requirements に効く gap のみ報告し、各指摘に
  file:line・なぜ誤りか・失敗を示す手順を付ける。それ以外（防御的コード・追加の抽象層・起こり得ないケースの
  テスト等）は optional として報告し、適用しない。diff 外の指摘は 1 行のみ、修理はしない」。CRITICAL が出たら直さず止めて報告する。
- これ以外の reviewer は起動しない（security 等の判断は判断役が持つ）。
- 省略・読み替えは可だが、報告に「逸脱: 何を・なぜ」と**必ず名指し**する。無言の逸脱は結果が正しくても
  bounce される
- diff 外の気づきは `rfcs/` にも台帳にも書かない。再現手順を書けるものは Report の `Proposed tasks`
  （最大 2 件）に、書けないものは `Out-of-diff findings` に 1 行ずつ（HIGH は producer `file:line` 付き）
  置く。起票するかは判断役が再現を確かめたうえでオーナーが決める

## Must-not（境界 = Goodhart 対策）
- 変えてよいのは `src/contemplative_agent/core/insight.py`、`tests/test_insight*.py`、`docs/adr/0111-insight-entrance-stages.md`、
  `docs/adr/0111-insight-entrance-stages.ja.md` だけ。`config/prompts/*.md` は変えない
- テストを弱めない・消さない・設定で黙らせない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない
  （検査の正本と CI — 触った diff は検収に入らない）
- `git add -A` を使わない ; 台帳（`rfcs/` の state）の状態は判断役が書く
- この packet のファイル（`docs/plans/rfc-0052-s44-insight-format-calls-system.md`）を編集しない — dispatch 時点で凍結した契約
- PR は自動で開く。PR の本文・設定は触らない ; main や他の branch に push しない ; force push しない
- time cap 1.5 時間を超えたら打ち切って、そこまでの diff とテスト状況で報告

## Report（最終 commit の message 本文 = session が閉じても残る唯一の証拠）
fix(insight): <summary> (RFC-0052)

Packet: S44
Plan: docs/plans/rfc-0052-s44-insight-format-calls-system.md
Needs from judge: <判断役かオーナーの決定・承認が要るもの / none>
Model: <この session のモデル名。途中でモデルが切り替わった通知が出たらその旨>
Effort: <この session が実際に走った effort — 環境変数 `CLAUDE_EFFORT` か `/effort` の表示。分からなければ「未確認」>
Premise: <file:line 再照合の結果、反証があればそれ>
Fix: <what and why, in the shape the reviewer needs>
Regression: <test names, RED→GREEN の確認方法>
Verify: <command exit / test counts / 日時。CI の判定は判断役が読む>
Review: </code-review medium の結果（findings 件数と対応）> / Deviations: <逸脱の名指しと理由、無ければ none>
Risk: <とったリスク / 戻し方（1 分で戻せるか）>
Proposed tasks (for the judge, 最大 2 件): <各件: 何が壊れているか / 再現手順（コマンド → 期待と実際）/
  決定可能な受入条件 / producer file:line — 無ければ none。再現手順は branch の tip で走る 1 コマンド（repo の
  テスト実行器で名前を指したテスト、または読み取りのみ）にし、commit しない>
Out-of-diff findings (for the judge): <severity + 1 行ずつ、HIGH は producer 付き / none>

最後のメッセージは「判断役に要るもの」から始め、branch 名・push した commit SHA・verify の結果・所要時間を報告して終了してください。
前提が崩れて実装しなかったときも同じ形で報告してください。
