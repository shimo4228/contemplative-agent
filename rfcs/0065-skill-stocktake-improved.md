---
title: skill-stocktake の改善版を作る（退役させず、読み手のいる出力だけを残して作り直す）
state: accepted
state_since: 2026-10-31
review-when: 改善版が main に着地した、またはオーナーが改善をやめて退役を選んだ
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: instrument
---

## タスク

ロードマップ 2026-10 の P1-04.2 は、読み手のない計器として skill-stocktake の去就を問うた。2026-10-31 にオーナーは「退役せず、改善版を作る」と決めた。P3-04.11（2026-07-10 の skill「clean rewrite」10 件の記録）も、生成器による書き換えをどう記録するかの決めがこの改善版の形に依存するので、ここに入れる。

## 詳細

- 現行の `skill-stocktake`（構造品質・usage・description 監査）の出力のうち、誰がいつ読むかを書ける部分を選ぶ。残すものには ADR-0101 の消費計画（読み手・読む回数で決めること・撤去条件）を書く。
- 生成器が skill を書き換えたとき（2026-07-10 型）、audit 行と frontmatter に何を残すかを決める。P3-04.11 の C10 の再分類と、frontmatter `origin` の 2 値目の扱いはオーナーが決めて記録する。
- 計器の一覧表（P1-04.8 の表）に改善版の行を置く。

完了: 改善版が main にあり、消費計画つきの ADR（新設か追補）があり、P3-04.11 の決定が記録されている。
