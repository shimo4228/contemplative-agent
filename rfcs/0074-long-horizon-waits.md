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
- P2-04.23: 次の macOS / Ollama 更新の後に `host_check` を 1 回打ち、2026-10-31 の基準行と比べた行を serving-changes に書く。

完了: 上の 3 つがそれぞれの待ちの後に済んでいる。
