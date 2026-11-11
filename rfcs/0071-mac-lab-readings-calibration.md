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

## 2026-11-04 triage 照合 (by: judge)

verdict: hold

目安は 11-09〜13（本文のとおり、日付は空き窓の都合）。行が 10 あり、1 session に収まらない。次の cycle で、Ollama を使わない行（P3-01.3）と、決めることが 1 行で書ける行から packet に切る。

## 2026-11-07 triage 照合 (by: judge)

verdict: hold

目安 11-09〜13。Ollama を使うローカル計測なので、水曜（11-11）の cycle が空き窓に合わせて packet に切り、Agent（worktree）で直列に回す。最初は Ollama 不要の P3-01.3。

## 2026-11-11 triage 照合 (by: judge)

verdict: ready（P3-01.3 だけ）

P3-01.3 の元パターン年齢の軸は Ollama 不要で、入力が揃っていることを確かめた: `audit.jsonl` の insight 行 1,183 件が `source_ids` を持つ、`skill-selection-*.jsonl` は 125 本。live の skill の frontmatter には `source_ids` が無い（P3-05.8 の backfill は RFC-0067 側）ので、採用行から辿る。Agent build（S53、packet `docs/plans/rfc-0071-s53-source-pattern-age.md`）に出す。残りの Ollama 行は 1 本ずつ後の cycle で。

## 2026-11-11 検収 (by: judge)

P3-01.3 の元パターン年齢の軸を、残す script（`scripts/source_pattern_age.py`、手動実行のみ）で読んだ（S53、[packet](../docs/plans/rfc-0071-s53-source-pattern-age.md)、`7303c7b0` + 差し戻し `b6124ea8`、ff-only）。読みは [docs/evidence/rfc-0071/source-pattern-age-2026-11-11.md](../docs/evidence/rfc-0071/source-pattern-age-2026-11-11.md)（`reanalysis: private-rows`、判定文なし）。辿れた選択は全期間 61,725 / 64,623、直近 4 週 18,038 / 18,166。差し戻し 1 回（別プロセスの review の指摘 2 件を採用: 退役した skill と同じ名前の再採用で選択が `name_ambiguous` に落ちる潜在の誤り、3 本目の窓の件数差の記載漏れ）。判断役の verify exit 0。同じ軸の一回限りの読みが 2026-10-31 に既にあった（`docs/evidence/adr-0124/source-pattern-age-20261031.md`、方法が 5 点違う）ので、今回を 1 回目と 2 回目のどちらに数えるかを digest で聞く。残りの行（Ollama を使う計測）は accepted のまま、1 本ずつ後の cycle で。

## 2026-11-11 著者回答 (by: owner)

triage digest 2026-11-11 を推奨どおり承認。P3-01.3 の元パターン年齢の軸は、2026-11-11 の読み（S53、`scripts/source_pattern_age.py`）をこの script での 1 回目と数える。2 回目は 2027-02 の四半期の読みで同じ script を使い、その後に判定文を書く。2026-10-31 の一回限りの読み（`docs/evidence/adr-0124/source-pattern-age-20261031.md`）は方法が 5 点違う参考の読みとして残る。
