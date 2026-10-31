---
title: Mac での 1 回ずつの計測（較正定数・eval baseline・novelty replay・ECE・null pair・全件再埋め込み）
state: accepted
state_since: 2026-10-31
review-when: 各行の 1 回の読みが evidence に凍結され、行ごとに「動かす / 据え置き」が書かれた
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: instrument
---

## タスク

Ollama を使う重い計測のうち、IPD 系列（RFC-0072）以外をまとめる。どれも 1 回の読みで決めることがはっきりしていて、観察期間を待たない。

## 詳細

実行の規則: Ollama のモデルは 1 つずつ直列に載せ、JST 0 / 6 / 12 / 18 時とスケジュールセッションを避ける。目安は 2026-11-09〜13（日付は空き窓の都合で、待つ理由ではない）。

持つ行と読み:

- P1-06.1: 契約キットを runtime で 1 回流す。
- P1-04.11: eval baseline を取り直す（smoke 1 行から）。
- P1-04.15 → P1-04.8: insight / dedup の較正定数を現 register で再読し、CONFIGURATION の閾値表の較正列を埋める。
- P1-04.13: 抽出前 novelty gate の冗長性を gemma の replay 1 回で読む。
- P3-03.9: RFC-0041 形 A の lab 4 段。RFC-0041 は withdrawn なので、測る意味があるかを最初に 1 行で確かめる。
- P1-15.4: score の再採点での ECE と、4 段ラベルの位置バイアス（2 順 × 2 run）。
- P3-02.3: pairwise cosine のための全件再埋め込み。
- P3-04.9: identity 再導出の null pair（3 run 以上、home の copy で）。
- P3-04.8: cosine 列（`--embed`）。live の 1 行目は次の identity staging で書かれる（この部分だけ観察待ち）。
- P3-01.3: source-pattern-age 軸（私的ログから。Ollama 不要）。

完了: 各行の読みが `docs/evidence/` にあり、行ごとに判断が書かれている。
