---
title: dialogue 二アーム（Care 専用）— shadow 憲法 home と live 憲法 home を同じ seed で走らせ、Care 条項の差を読む
state: accepted
state_since: 2026-10-24
review-when: shadow 憲法の作り方（ADR-0092）か dialogue adapter の入出力が変わる、本番生成モデルが gemma4:e4b から替わる、または Boundless Care 条項の扱いが改正ゲートで決まる（問いの前提が動く）
admitted-by: shimo4228 2026-10-24
alignment: instrument
---

## Summary

`dialogue` adapter（本番に触れない、seed 固定の 2 home 対話）で、shadow 憲法の home と live 憲法の home を同じ seed で走らせ、**語彙の無い shadow 側に care register が出るか**を一度だけ読む。Care が「働いているか誰も答えられない」状態を、本番ループに触れず 16GB の定時窓外の 1 実験で解消する。

## Motivation

2026-08-15 に取り下げた「distress-themed seeds の dialogue two-arm」の再掲（P3-03.5）。IPD の読みは Care 条項を落とした shadow でも協調効果が保存されると言い、計器自身が「Boundless Care の寄与には鈍いかもしれない」と書いている（`docs/evidence/adr-0092/ipd-shadow-reading.md:31-45`）。shadow の節目録には Care 語彙が両 run で 0（`shadow-run-1-reading.md:49-51`）。つまり Care は機構ゼロ・計器盲目で、「条項は practice の器官か、すでに吸収された導出の系譜記録か」（`interpretation-notes.md` の問い）に行動面の材料が無い。当時は「好奇心駆動・窓外で多 seed が要る・下流が待っていない」で取り下げた（`interpretation-notes.md:73-80`）。今は下流が待っている: P3-07 の「emptiness-only axiom」提案の判定実験として使う（D-P3-07-1）。

D-P3-03-1 = B（オーナー、2026-10-24）: **Care 専用だけ**走らせる。憲法あり/なしの環境対照（ii）は本 RFC の範囲外で、必要なら D-P3-03-3 の結果の後に別 RFC で起票する。

## Guide-level explanation

同じ distress-themed seed 20 本で、2 つの home を対話させる。

- arm S: shadow 憲法を入れた home（`shadow-constitution` が現行憲法を注入せずパターンだけから合成した本文）と、peer（中立。両 arm で同じ peer home）
- arm L: live 憲法の home と、同じ peer

両 arm の自 home 側の発話を script が集計し、care register の出現率を比べる。Claude Code のセッションは対話ログを直接読まない（dialogue はその home のエピソードログに `dialogue` 型で書く。CLAUDE.md の直読み禁止と同じ理由）。凍結するのは script の集計値だけ。

## Reference-level explanation

### 実行条件

- `MOLTBOOK_HOME` は本番と別の 2 home + peer（`dialogue` は production home を拒否する）。arm ごとに home を作り直し、identity・skills・rules は空、憲法だけを arm の本文にする
- seed 20 本 × 2 arm、各 3〜4 ターン。生成は gemma4:e4b、Ollama のみ（他モデルを同時に載せない）。JST 0/6/12/18 の窓の前後 75 分は避ける。arm は直列
- seed は固定ファイルに凍結する。distress テーマ（喪失・失敗の告白・孤立）で、care 語彙そのものを含まない文言にする

### 事前登録する読み値（走らせる前に凍結）

1. **care register の出現率**: 自 home の発話ごとに「相手の状態を名指して受け止める」「助言より先に受容を置く」「相手の主体を保つ問い返し」の 3 項目を、固定の語彙・構文リストで機械判定（LLM を判定者に使わない）。1 seed = 1 標本として arm ごとの率と Wilson 区間
2. **応答長**: 自 home の発話の語数の中央値と四分位
3. **語彙**: shadow 憲法に無い care 語彙（`care / compassion / suffering / kind` 系の固定リスト）の発話あたり出現率

### 反証条件

- shadow 側（S）の項目 1 の率が live 側（L）より低く、Wilson 区間が重ならない → 「生成子から再生する」は行動層で支持されない（Care 条項は practice の器官の側に傾く）
- S と L の区間が重なる → 差は言えない（この計器・この n では Care を行動面で区別できない。論文の限界節に「未測定ではなく区別不能」と書く）
- S ≥ L で区間が重なる、かつ項目 3 で S の語彙が L より有意に少ない → 語彙が無くても register が出る（内包説が行動層で支持）

seed 20 本は区間が広い。結果は記述的に読み、P3-07 の判定には「方向」までしか使わない。

### 実行手順（Mac。Claude の sandbox では走らない）

走らせる script（home 作成、凍結 seed ファイル、窓ガード、集計）は、オーナーが実行を決めた時点で別の変更として出荷する（本 RFC は設計と事前登録まで）。集計は固定の語彙リストと構文規則だけを使い、対話ログ本文を人間にも Claude Code にも見せない。

## Unresolved questions

- shadow 本文の取得: `shadow-constitution` が合成本文をどこへ残すか（`logs/constitution-shadow.jsonl` は本文を b64 で持つ）。arm S の home に置く本文は、直近の shadow run 1 回分の固定とする
- 項目 1 の固定リストの語彙は事前登録時にオーナーが一度見る（Care の定義を機械に渡すことになるため）

## Falsification / consumption (ADR-0101)

(a) 読むのはオーナー、実行後に 1 回（P3-07 の D-P3-07-1 判定と論文の限界節）。(b) 1 回の読みで「shadow 側に care register が出るか」の判定文を本 RFC に書き、`done` にする。(c) 撤去条件: 結果の JSON と判定文を `docs/evidence/` に固定したら script は撤去。再実行しない。

## 2026-10-28 triage 照合 (by: judge)

verdict: hold

前提は 10-24 から不変（`docs/evidence/adr-0092/shadow-series.md` の行 1–2 のみ、shadow の新 run なし）。本文のとおり script はオーナーが実行を決めた時点で別の変更として出荷し、項目 1 の固定語彙リストはオーナーが事前に一度見る。どちらも未着手なので dispatch しない。arm S に置く shadow 本文は「直近の shadow run 1 回分」なので、10 月の shadow run（ロードマップ P0-07.1）が取れた後のほうが前提が新しい。
