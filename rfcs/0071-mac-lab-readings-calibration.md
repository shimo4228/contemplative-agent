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

verdict: ready
対象は P3-01.3 だけ。

P3-01.3 の元パターン年齢の軸は Ollama 不要で、入力が揃っていることを確かめた: `audit.jsonl` の insight 行 1,183 件が `source_ids` を持つ、`skill-selection-*.jsonl` は 125 本。live の skill の frontmatter には `source_ids` が無い（P3-05.8 の backfill は RFC-0067 側）ので、採用行から辿る。Agent build（S53、packet `docs/plans/rfc-0071-s53-source-pattern-age.md`）に出す。残りの Ollama 行は 1 本ずつ後の cycle で。

## 2026-11-11 検収 (by: judge)

P3-01.3 の元パターン年齢の軸を、残す script（`scripts/source_pattern_age.py`、手動実行のみ）で読んだ（S53、[packet](../docs/plans/rfc-0071-s53-source-pattern-age.md)、`7303c7b0` + 差し戻し `b6124ea8`、ff-only）。読みは [docs/evidence/rfc-0071/source-pattern-age-2026-11-11.md](../docs/evidence/rfc-0071/source-pattern-age-2026-11-11.md)（`reanalysis: private-rows`、判定文なし）。辿れた選択は全期間 61,725 / 64,623、直近 4 週 18,038 / 18,166。差し戻し 1 回（別プロセスの review の指摘 2 件を採用: 退役した skill と同じ名前の再採用で選択が `name_ambiguous` に落ちる潜在の誤り、3 本目の窓の件数差の記載漏れ）。判断役の verify exit 0。同じ軸の一回限りの読みが 2026-10-31 に既にあった（`docs/evidence/adr-0124/source-pattern-age-20261031.md`、方法が 5 点違う）ので、今回を 1 回目と 2 回目のどちらに数えるかを digest で聞く。残りの行（Ollama を使う計測）は accepted のまま、1 本ずつ後の cycle で。

## 2026-11-11 著者回答 (by: owner)

triage digest 2026-11-11 を推奨どおり承認。P3-01.3 の元パターン年齢の軸は、2026-11-11 の読み（S53、`scripts/source_pattern_age.py`）をこの script での 1 回目と数える。2 回目は 2027-02 の四半期の読みで同じ script を使い、その後に判定文を書く。2026-10-31 の一回限りの読み（`docs/evidence/adr-0124/source-pattern-age-20261031.md`）は方法が 5 点違う参考の読みとして残る。

## 2026-11-14 triage 照合 (by: judge)

verdict: ask-owner

P3-04.8 の観察待ちの部分は成立した: identity staging（2026-11-07）で `logs/identity-drift.jsonl` に live の 1 行目が書かれた（verdict ok、cosine 0.8751）。今日のゲートでこのログを census に登録した（`bdd91baa`）。残りの Ollama 計測（P1-06.1、P1-04.11、P1-04.15→.8、P1-04.13、P3-03.9、P1-15.4、P3-02.3、P3-04.9）は目安 11-09〜13 を過ぎて未着手。本番機で Ollama を使うので、いつ回すかを今回の digest で聞く（既定: 次の guard 窓で P1-06.1 と P1-04.11 から Agent build に出す）。

## 2026-11-14 著者回答 (by: owner)

triage digest 2026-11-14 を推奨どおり承認: P3-04.8 は済（2026-11-07 の live 1 行目、cosine 0.8751）。残りの計測は今夜の guard 窓（19:00 JST 以降）から P1-06.1 + P1-04.11 を S55 として出す。

## 2026-11-18 triage 照合 (by: judge)

verdict: ready
承認済みの dispatch（11-14 の著者回答）。

11-14 の著者回答（S55 = P1-06.1 + P1-04.11 を 19:00 JST 以降の guard 窓で）は、11-14 の窓では改正セッションと重なって出せなかった。今日（11-18）の 19:00 JST 以降に S55 を Agent build（worktree、opus）で出す。packet は `docs/plans/rfc-0071-s55-contract-kit-eval-smoke.md`（build の最初の commit）。Ollama を叩くのは 19:00〜22:45 JST に限る。

## 2026-11-18 検収 (by: judge)

P1-06.1 と P1-04.11 を読んだ（S55、[packet](../docs/plans/rfc-0071-s55-contract-kit-eval-smoke.md)、`bd7b19d1` + 差し戻し `7ca56a57`、ff-only）。Ollama を使ったのは 19:07〜19:17 JST の eval run だけ。判断役の verify は exit 0（6502 passed）。別 process の review は 4 件で 3 件を採用（読みメモの絶対パス、probe のコードがメモに無く再現できない、行範囲の 1 行ずれ）し、差し戻し 1 回で解消。採らなかった 1 件は commit 本文の書き方（この run を baseline 承認に回せると書いた点。メモ本文は中立で、回すかは判断役が決める）。

- P1-06.1: [contract-kit-runtime-2026-11-18.md](../docs/evidence/rfc-0071/contract-kit-runtime-2026-11-18.md)。`OllamaBackend`（`src/contemplative_agent/core/llm/ollama.py:166`）は static 段で 7 PASSED / 1 SKIPPED。STATUS の `--require runtime` は exit 1 だが、原因は backend でなくキット v2 が static 段の検査しか持たないこと（`src/contemplative_agent/testing/backend_contract.py:470-486`）で、どの backend でも同じになる。判断役が同じコマンドで再現した。受入コマンドを `--require static` に言い直すか、キットに runtime 段を足すかを次の digest で聞く。
- P1-04.11: [eval-smoke-2026-11-18.md](../docs/evidence/rfc-0071/eval-smoke-2026-11-18.md)。12 ケース × 1 サンプル、run `20261118T100717Z`。11 DRIFTING / 1 DEVIANT、`register_natural` は 0/12（09-12 の baseline も 0/36）。fixture は 2026-08-08 の snapshot（skill 45 本、本番は 53 本）。この run は baseline 承認に回さない: サンプル数 1 が比較の欄（`evals/compare.py:39-50`）に入り、以後の既定の 3 サンプルの run と比べられなくなるのと、古い fixture を測っているため。`check_staleness.py` は STALE でなく acknowledged の枝 + re-baseline の勧告で exit 1。ROADMAP が書く `--json` は無い。

state は accepted のまま。残りの Ollama 計測（P1-04.15→.8、P1-04.13、P3-03.9、P1-15.4、P3-02.3、P3-04.9）と、RFC-0012 の採択後の shadow 読みは、1 本ずつ後の cycle で直列に出す。

## 2026-11-21 triage 照合 (by: judge)

verdict: ask-owner

11-18 の検収が残した問い（P1-06.1 の受入コマンドを `--require static` に言い直すか、キットに runtime 段を足すか）を digest で聞く。キット v2 は static 段の検査しか持たない（`src/contemplative_agent/testing/backend_contract.py:470-486`）。残りの Ollama 行（P1-04.15→.8 から）は、今日は RFC-0070 の運用作業が Ollama を触るので出さず、11-25 の guard 窓の cycle で 1 本ずつ。

## 2026-11-21 著者回答 (by: owner)

triage digest 2026-11-21 を推奨どおり承認: P1-06.1 の受入を `--require static` に言い直し、S55 の読み（[contract-kit-runtime-2026-11-18.md](../docs/evidence/rfc-0071/contract-kit-runtime-2026-11-18.md)、static 7 PASSED / 1 SKIPPED）で済とする。キットに runtime 段は足さない（sibling の 2 本は凍結中で、流す相手がいない）。state は accepted のまま（残りの Ollama 行がある）。
