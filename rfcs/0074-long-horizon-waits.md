---
title: 2027 年とイベント待ちの項目 — 最終スナップショット、月次 value-layer ledger、凍結判定、ホスト更新後の点検
state: blocked
state_since: 2026-10-31
decide_by: 2027-06-30
next_check: 2027-02-27
review-when: (a) 2027-02-27 の RFC-0048 の再読、(b) 2027-Q2 に最終スナップショットのサイズが分かる、(c) 次の macOS / Ollama の更新、のいずれか
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: repair
---

## タスク

データか外部の出来事を待つロードマップの行をまとめる。

## 詳細

持つ行: P2-05.5、P4-02.2、P2-04.23、凍結判定（行 ID なし）。

- P4-02.2 / P2-05.5: D-P4-02-2 を決め、最終スナップショットのチェックリストを 1 つにし、月次の value-layer ledger を機械描画で出す（LLM 文書にしない）。待つもの: 2027-Q2 のデータ。
- 凍結判定: `scripts/freeze_reading.py` で判定する。時期は 2027-02-27 の RFC-0048 再読で決める（最短 2027-01-23 か 2027-05）。
- P2-04.23: 次の macOS / Ollama 更新の後に `host_check` を 1 回打ち、2026-10-31 の基準行と比べた行を serving-changes に書く。 — 済み 2026-11-07（macOS 27.2 への更新後。serving-changes の 2026-11-07 行）。

完了: 上の 3 つがそれぞれの待ちの後に済んでいる。

## 2026-11-04 triage 照合 (by: judge)

verdict: dead-band

(a) 2027-02-27 は先、(b) 2027-Q2 は先、(c) `sw_vers` = macOS 27.0（26A428）、`ollama --version` = 0.34.2 で、`docs/evidence/serving-changes.md` の 2026-10-31 基準行から変化なし。

## 2026-11-07 triage 照合 (by: judge)

verdict: ready

(c) が成立した: `sw_vers` = macOS 27.2（26B123）、2026-10-31 の基準行は 27.0（26A428）。`ollama --version` = 0.34.2 は変化なし。P2-04.23 の `host_check` を今日 1 回打った（macOS 27.2、git 2.54.0、python3 3.14.3、rsync 3.5.1、claude 2.1.319、gh 2.96.0、venv Python 3.13.5、gemma4:e4b `c6eb396dbd59` / nomic-embed-text `0a109f422b47` は不変）。serving-changes に行を書くのは digest の承認の後。(a) 2027-02-27 と (b) 2027-Q2 は先。

## 2026-11-11 triage 照合 (by: judge)

verdict: dead-band

(c) の行は 11-07 の digest で済んだ（serving-changes の 2026-11-07 行）。(a) 2027-02-27 と (b) 2027-Q2 は先。
