# Kickoff packet — S49: RFC-0066（insight の revise 提案に改訂本文を 5 件だけ作らせる、一回限りの測定）

cwd は `contemplative-agent` の git worktree（Agent の isolation: worktree が切った branch）。成果は branch 上の
commit で返し、判断役が検収して main へ ff-only 取り込みます。境界は rule `boundary.md` — build は task branch まで。
packet に無いことは harness の規約が既定。**measurement variant**: 書いてよいのは一回限りの生成 script 1 本と、
凍結する読み 1 フォルダ（`docs/evidence/rfc-0066/`）と、RFC-0066 本文への「判定基準」節の追記だけ。判定はしない —
判定はオーナーが土曜ゲートで行う。

最初に読む: `rfcs/0066-revise-text-one-shot-measurement.md`、`docs/adr/0111-insight-entrance-stages.md`
（revise を記録して止める option A と option B）、`docs/evidence/adr-0111/revise-table-2026-10-24.md`、
`config/prompts/` の insight 系プロンプト、`CLAUDE.md`（実行機の節: Ollama は gemma 単独、JST 0/6/12/18 時の
スケジュールセッションと重ねない。エピソードログ直読み禁止）。

Effort: harness 既定（Agent build は effort を受け取らない。Report に実際の値）

## 判定基準（オーナーの digest 承認で確定した既定。最初に RFC-0066 本文へ「判定基準（2026-11-04、読みの前）」節として追記し、その commit を出力の前に置く）
- 標本: revise 表の **異なる target skill から 5 件**（同じ target が複数行なら最新の行）。選び方は script に固定する
- 1 件の「使える」= オーナーが既存 skill 本文と改訂本文を並べて読み、(1) 既存の trigger（いつ使うか）を壊さず、
  (2) change reason が本文に反映され、(3) そのまま採用してよいと判断したもの。審判はオーナーで、LLM judge は使わない
- 決め方: 5 件中 3 件以上が「使える」→ 案 B（revise を出口につなぐ）を起票する提案。1 件以下 → ADR-0111 に
  「入れない」を日付つきで残す提案。2 件 → 「入れない」側（決め手不足）

## Goal（決定可能な受入条件）
1. RFC-0066 に判定基準節があり、その commit が出力ファイルの commit より前にある
2. `docs/evidence/rfc-0066/` に、5 件それぞれの target skill 名・既存本文の sha256・改訂本文・生成時の
   モデル名と digest・プロンプトの sha256 がある。オーナーが 1 画面で並べて読める md を 1 本置く
3. 生成は gemma4:e4b（本番と同じ）を Ollama で 5 回。ほかのモデルを載せない
4. 判定欄は空欄のまま（オーナーが土曜ゲートで埋める）

## Phase 0 — 前提の再照合
- revise 表がまだ 21 行で、target skill が `$MOLTBOOK_HOME/skills/` に実在するか（無い target は飛ばして次を取る）
- revise 行の元になった観察（cluster の pattern）を、episode log を直読みせずに取れる経路があるか
  （`logs/insight-stages.jsonl` は自己書き込みの計器ログ。b64 の欄は復号しないで済むなら復号しない）。取れなければ
  change reason だけを入力にし、その旨を Report に書く
- 反証されたら実装せず止めて報告

## Build（順序）
1. `date` と `ollama ps` を確かめ、JST の 0/6/12/18 時の前後 60 分を避ける。スケジュールセッションが走っていれば待つ
2. 判定基準を RFC に追記して commit
3. script（`scripts/` に一回限りと冒頭コメントで宣言。`uv run --no-sync python` 起動）で 5 件を生成し、evidence に凍結して commit
4. `./.claude/verify.sh` exit 0

## Review
- 種別: measurement。chain は skill `implementation-chain` の Chain Matrix に従う
- 省略・読み替えは可だが、報告に「逸脱: 何を・なぜ」と必ず名指しする

## Must-not
- `$MOLTBOOK_HOME` の skills / staging / identity / constitution を書き換えない（生成物は evidence にだけ置く）
- `adopt-staged` や insight の本番コマンドを走らせない
- `~/.config/moltbook/logs/episodes/` と `agent-launchd.log` を読まない
- `.claude/verify.sh`・`.claude/verify.md`・`.github/`・`.claude/settings.json` を変えない ; `git add -A` を使わない
- この packet のファイル（`docs/plans/rfc-0066-s49-revise-text-measurement.md`）を編集しない
- time cap 60 分

## Report（最終 commit の message 本文）
docs(evidence): <summary> (RFC-0066)

Packet: S49
Plan: docs/plans/rfc-0066-s49-revise-text-measurement.md
Needs from judge: オーナーの判定（土曜ゲート）
Model: <この session のモデル名> / 生成: gemma4:e4b <digest>
Effort: <実際の値 / 未確認>
Premise: <再照合の結果>
Fix: <標本の選び方と入力の作り方、3 文>
Verify: <command exit>
Review: <回した reviewer と結果> / Deviations: <none か名指し>
Risk: <戻し方>
Proposed tasks (for the judge, 最大 2 件): <none か各件>
Out-of-diff findings (for the judge): <none か 1 行ずつ>

最後のメッセージは「判断役に要るもの」から始め、commit SHA・verify の結果・所要時間を報告して終了してください。
