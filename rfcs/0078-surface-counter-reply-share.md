---
title: 表層カウンタに返信の割合の読み値を足し、基準 P-005 を機械で照合する
state: done
state_since: 2026-11-11
admitted-by: shimo4228 2026-11-07
review-when: P-005 の基準が archive か再宣言で置き換わった、または表層カウンタ（scripts/surface_counter_scan.py）が退役した
origin: gate
filed_by: weekly-2026-11-06  # filed at that week's Saturday gate (triage digest 2026-11-07), not by the unattended run
alignment: instrument
---

## Summary

`scripts/surface_counter_scan.py` の読み値に返信の割合（`reply_share.all` = 返信の本文数 / 公開本文数）を足し、2026-11-07 のゲートで宣言した基準 P-005（返信の割合 48〜65%）を `observation_ledger.py render` の帯判定で照合できるようにする。

## Motivation

- gate-2026-11-06（2026-11-07）で P-005 を採用したが、計器に対応する列が無いので帯を持たない文章の基準として宣言した（observation-ledger.jsonl の 2026-11-07 baseline 行、`no structured band (prose only)`）。
- producer: `scripts/surface_counter_scan.py:208` の `readings()` は question_closer / nonce / skill_heading / wrapper_vocab / short_context を出すが、返信の割合を出さない。種類ごとの本文数（`bodies`）は `summarize()` が既に数えている。
- 消費者: `scripts/observation_ledger.py:299` の `_band_verdict` が readings の鍵で帯の内外を出す。

## Reference-level explanation

- `readings()` に `reply_share.all = {"successes": <reply の bodies>, "trials": <all の bodies>}` を足す（率なので Wilson 区間で判定される）。出力境界（件数・比率のみ、ADR-0083）は変えない。
- 合成 fixture の test 1 本（返信の割合の分子・分母）。
- 次の土曜ゲートで P-005 を `--band-low 48 --band-high 65 --unit '%' --reading-key reply_share.all` で再宣言する（帯は週の率で判定する。提案の「1 日あたり」は日別の読みで、週の率とは粒度が違うことを再宣言の source に書く）。

## 消費計画（ADR-0101）

- (a) 土曜ゲートの人間が render の baseline 行で毎週読む。
- (b) 毎週の読みで P-005 の IN / BELOW / ABOVE を出す。2 週続けて帯の外なら観察（O-id）を起こす。
- (c) 撤去条件: P-005 が archive か別の基準に置き換わったとき、または表層カウンタの退役のとき。

## Status

done — 2026-11-11 に S52 で main に取り込んだ（`3f010d8e`）。起票と採用は 2026-11-07 の triage digest（weekly-gate Step 8）。

## Next action

次の cycle で cloud build に出す（小さな変更、test 1 本）。

## 2026-11-11 triage 照合 (by: judge)

verdict: dispatched

RFC-0077 と同じ build（S52）に出した。

## 2026-11-11 検収 (by: judge)

S52 に同梱して main に取り込んだ（`3f010d8e`、ff-only）。`readings()` に `reply_share.all` が入り、`observation_ledger._band_verdict` で帯判定できる。P-005 を `--reading-key reply_share.all --band-low 48 --band-high 65 --unit '%'` で再宣言するのは次の土曜ゲート。
