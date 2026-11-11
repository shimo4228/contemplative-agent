---
title: insight の revise 提案に改訂本文を一度だけ数件作らせ、使えるかを測る
state: accepted
state_since: 2026-10-31
review-when: 測定が evidence に凍結され、結論（案 B を起票する / ADR-0111 に「入れない」を残す）が記録された
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: instrument
---

## タスク

ロードマップ P0-01.6。insight の revise 提案（2026-10 時点で消費者がいない）は、改訂本文まで作らせれば出口につなげられるかもしれない。これを一回限りの測定で確かめる。

## 詳細

- 凍結済みの revise 表（`docs/evidence/adr-0111/revise-table-2026-10-24.md`）から数件を選び、本番モデル（gemma4:e4b）に改訂本文を作らせる。Ollama を使うので JST 0 / 6 / 12 / 18 時とスケジュールセッションを避け、ほかのモデルと同居させない。
- 「使える / 使えない」の基準は、出力を読む前にこの RFC に追記して固定する。
- n は問いに要る最小にする（skill `measurement-discipline`）。

完了: 出力と判定が `docs/evidence/` に凍結され、案 B（revise を出口につなぐ）を起票するか、ADR-0111 に「入れない」を日付つきで残すかが決まっている。

## 2026-11-04 triage 照合 (by: judge)

verdict: ready

開始の OK を digest で聞く（S49、ローカルの計測）。

Ollama を使うのでローカル（Agent worktree）。「使える」の基準は著者が決める項目なので、既定案（異なる target skill から 5 件、審判はオーナー、5 件中 3 件以上で案 B を起票する提案）を置き、承認の後に基準をこの RFC に追記してから生成する。

## 判定基準（2026-11-04、読みの前）

オーナーが 2026-11-04 の triage digest で承認した既定。生成の前にここへ固定し、出力を読んだ後に変えない。

- 標本: 凍結済みの revise 表（`docs/evidence/adr-0111/revise-table-2026-10-24.md`、21 行）から、**異なる target skill の 5 件**。同じ target が複数行あるときは最新の行を使う。選び方は生成 script（`scripts/rfc0066_revise_text_once.py`）に固定する
- 1 件の「使える」: オーナーが既存 skill 本文と改訂本文を並べて読み、次の 3 つをすべて満たすと判断したもの — (1) 既存の trigger（いつ使うか）を壊さない (2) change reason が本文に反映されている (3) そのまま採用してよい。審判はオーナーで、LLM judge は使わない
- 決め方: 5 件中 3 件以上が「使える」→ 案 B（revise を出口につなぐ）を起票する提案。1 件以下 → ADR-0111 に「入れない」を日付つきで残す提案。2 件 → 「入れない」側（決め手不足）
- 判定はオーナーが土曜ゲートで行う。evidence の判定欄は空欄で凍結する

## 2026-11-04 検収 (by: judge)

S49（[packet](../docs/plans/rfc-0066-s49-revise-text-measurement.md)）を main に取り込んだ（判定基準 `6518ecd7`、出力 `b8e4c3f9`）。判定基準の commit は出力より前にある。[docs/evidence/rfc-0066/](../docs/evidence/rfc-0066/README.md) に 5 件の既存 skill 全文と gemma4:e4b の改訂本文が並び、判定欄は空。標本は凍結表 21 行から異なる target を新しい順に 5 件で、5 件とも revised（辞退 0、失敗 0）。生成は 19:06〜19:15 JST、ほかのモデルは載っていなかった。オーナーが土曜ゲートで判定欄を埋めると、判定基準節の決め方で結論が出る。

## 2026-11-07 triage 照合 (by: judge)

verdict: ask-owner

判定欄（`docs/evidence/rfc-0066/README.md` の 5 件）はまだ空。オーナーが判定を埋めると、判定基準節の決め方で結論が出る。digest で埋めてもらう。

## 2026-11-11 triage 照合 (by: judge)

verdict: ask-owner

判定欄（`docs/evidence/rfc-0066/README.md:17` と各件の判定行 5 つ）はまだ空。11-07 の digest から持ち越し。今回の digest で再び聞く。

## 2026-11-11 digest (by: judge)

判定欄の問いは答えが無く、据え置いた。次の digest に持ち越す。
