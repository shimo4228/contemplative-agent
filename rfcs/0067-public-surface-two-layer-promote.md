---
title: 公開面を 2 層に分け、LLM が書いた文書は人間が promote する — sync と weekly-gate の実装と公開面の仕上げ
state: accepted
state_since: 2026-10-31
review-when: 無人の sync commit に `reports/analysis/` の差分が出なくなり、下の投影がすべて公開面に出た
admitted-by: shimo4228 2026-10-31
origin: roadmap
alignment: repair
---

## タスク

ADR-0010 の追補「公開物を 2 層に分ける」（D-P2-05-1 = C、D-P2-05-4 = A、2026-10-31）はまだコードになっていない（追補の "Not in code yet" 行）。ロードマップの P2-05 束のコード部分と、data repo 側の仕上げをここにまとめる。

## 詳細

持つ行: P2-05.1、P2-05.2（残り）、P2-05.3、P2-05.8、P2-05.9、P3-05.8、P3-05.1、P0-03.6、P3-02.2。

- P2-05.1: `scripts/sync-research-data.sh` は `reports/analysis/` を出さない。weekly-gate の Step 6d に、人間が週次文書を読んで公開面へ promote する段を置く（protected class、オーナーが merge）。
- P2-05.2 の残り: `pipeline/gate/` と archived 一覧、DATACARD の decision log 節。
- P2-05.3: 計器ログ（shadow 憲法・skill selection・relevance・comment-outcomes）の本文抜き投影。続けて P2-05.8 の `selected_90d` 列、P2-05.9 の comment-report への注入 skill 名と私的ログからの backfill。
- P3-05.8: `MOLTBOOK_HOME` の skill frontmatter の `source_ids` backfill（オーナー）。
- P3-05.1: `docs_consistency_scan.py --data-repo` を週次に配線する。
- P0-03.6: data repo の gitleaks workflow は main にある。残りはメール形の allowlist。
- P3-02.2: `MOLTBOOK_HOME` 側の「Diachronic Analysis」の改題。

完了: 無人実行のあとの data repo の commit に `reports/analysis/` の差分が無く、上の投影が公開面に出て、テストが固定している。
