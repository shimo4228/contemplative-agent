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

## 2026-11-04 triage 照合 (by: judge)

verdict: accepted → 開始の OK を digest で聞く（S47、P2-05.1 だけを切り出す）

前提を確かめた: `scripts/sync-research-data.sh:107` の `PUBLIC_TOP_LEVEL` が `reports` を含み、除外は `reports/.private/` と `/reports/comment-reports/` だけ（`:220-221`）。`docs/adr/0010-research-data-sync.md:129` の "Not in code yet" 行も残っている。公開 repo の cloud build なので開始の OK を待つ。diff は project skill（weekly-gate）に触れるので、merge も改めて OK を聞く。

## 2026-11-04 検収 (by: judge)

S47（[packet](../docs/plans/rfc-0067-s47-sync-leaves-analysis-to-gate.md)）の build は branch `claude/task-jeyn3u` に届いたが、取り込んでいない。別プロセスのセキュリティレビューで HIGH が 1 件出た: `--promote` の実行がコピーの後の検査（home パス・secret scan・divergence など）で止まると、コピーがデータ repo の作業ツリーに残り、次の無人 sync がそれを commit して公開する（除外が `--delete` からも守るため）。ほかに MEDIUM 2 件（Context 行の検査が書き換えと同じ正規化で発火しえず、変形した見出しが通る / takedown の `name:` `post:` が promote する文書に効かない）と LOW 3 件。公開 repo なので差し戻しは次の digest の開始の OK で聞く。この diff は weekly-gate skill も書き換えるので、取り込みには別に merge の OK が要る。
