---
title: IPD 系列 — null pair で床を再推定し、改正 4 版とプラセボ 4 アームを測る
state: accepted
state_since: 2026-10-31
review-when: 3 つの読みが evidence に凍結され、ADR-0090 の pair-count 行が更新された
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: instrument
---

## タスク

憲法改正の効果を IPD で測る系列（ロードマップ P3-03.2 / .3 / .4）。重い計測で、ほかの Ollama 計測（RFC-0071）と直列に回す。目安 2026-11-23〜12-04。

## 詳細

- P3-03.2: null pair 2 本で床を再推定する（セル別 SE の規則は P3-03.10 で済）。ADR-0090 の pair-count 行を更新する。
- P3-03.3: 改正 4 版 × IPD（runner `scripts/ipd-series.sh`、表 `scripts/ipd_series_table.py`）。
- P3-03.4: プラセボ憲法 4 アーム（瞑想固有の効果か、倫理文一般の効果か）。
- 読みは P3-01.2 の事前登録と照合する。RFC-0059（複数モデルの IPD、draft）の採否も同じ読みで判断できる形にする。

完了: 3 つの表が `docs/evidence/` に凍結され、事前登録との照合が書かれている。
