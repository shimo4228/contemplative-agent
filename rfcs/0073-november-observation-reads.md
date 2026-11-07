---
title: 挙動を変えた後の 11 月の読みと ADR-0080 追補（2026-11）
state: blocked
state_since: 2026-10-31
decide_by: 2026-11-28
next_check: 2026-11-14
review-when: 次の identity 採用から 7 日と、2026-11-06 / 11-13 の本番週次 2 回が出た
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: instrument
---

## タスク

挙動を変えた後の観察が要るロードマップの行をまとめる。待つ理由は観察（OBS）だけで、コードで先にできる部分は待たずに入れる。

## 詳細

持つ行: P2-06.1、P1-15.2、P1-07.10、P2-01.5、P2-01.3、P1-03.9、P1-03.8。

- P2-06.1: Exceptions の行数が本番週次 2 回で減ったか（構造の確認だけなら 10-30 の 1 回で足りる、という選択肢もある）。
- P1-15.2: enforce 後の母集団（post 単位）で t=0.3 を再読し、identity 採用の前後 ±7 日の gate 率を読む。
- P1-07.10: path ごとに llm-calls が 1,000 行たまったら token 推定器を再較正する（PR2）。
- P2-01.5: 自己調節の読み値のうち使わない列を落とす。
- P2-01.3 / P1-03.8: 追補（2026-11）に読み方の段落を書き、必要なら追補（2026-12）。
- P1-03.9: `scripts/self_regulation_reading.py` の候補行に基礎率を併記する — コードなので待たずに入れる。
- 済の行に残る WAIT（P1-15.3 の投票行、P2-04.9 の late_minutes、P1-01.1 の 4 週の転記）も同じ読みで拾う。

完了: 各読みが記録され、追補が採択されている。

## 2026-11-04 triage 照合 (by: judge)

verdict: dead-band

blocked のまま（照合先が未成立）。

照合先: 次の identity 採用は無い（`audit.jsonl` の `distill-identity` approved の最終は 2026-10-10）、本番週次 11-06 / 11-13 はまだ。本文の「コードで先にできる部分は待たずに入れる」に当たる P1-03.9 の残り（`scripts/self_regulation_reading.py` の候補行・下限行への基礎率の併記と test 1 本、`docs/plans/roadmap-2026-10/STATUS.md:230`）は build に出せる。今回は WIP 3 を RFC-0066 / 0067 / 0068 に使うので、次の cycle で開始の OK に出す。

## 2026-11-07 triage 照合 (by: judge)

verdict: ready

待ちの 1 つが成立した: identity を 2026-11-07 に採用（`audit.jsonl` stage-adopted-names、content_hash `012114a54fb5ac3d`）。P1-15.2 の ±7 日の gate 率は 11-14 以降の週次（weekly-2026-11-13 / 11-20 の relevance face reading）で読める。コードで先にできる P1-03.9（`scripts/self_regulation_reading.py` の候補行・下限行への基礎率の併記と test 1 本）は cloud build に出せる。公開 repo なので開始は digest の OK を待つ。
