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
