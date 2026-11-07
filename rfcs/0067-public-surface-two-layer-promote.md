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

verdict: ready

開始の OK を digest で聞く（S47、P2-05.1 だけを切り出す）。

前提を確かめた: `scripts/sync-research-data.sh:107` の `PUBLIC_TOP_LEVEL` が `reports` を含み、除外は `reports/.private/` と `/reports/comment-reports/` だけ（`:220-221`）。`docs/decision-history/0010-research-data-sync.md:129` の "Not in code yet" 行も残っている。公開 repo の cloud build なので開始の OK を待つ。diff は project skill（weekly-gate）に触れるので、merge も改めて OK を聞く。

## 2026-11-04 検収 (by: judge)

S47（[packet](../docs/plans/rfc-0067-s47-sync-leaves-analysis-to-gate.md)）の build は branch `claude/task-jeyn3u` に届いたが、取り込んでいない。別プロセスのセキュリティレビューで HIGH が 1 件出た: `--promote` の実行がコピーの後の検査（home パス・secret scan・divergence など）で止まると、コピーがデータ repo の作業ツリーに残り、次の無人 sync がそれを commit して公開する（除外が `--delete` からも守るため）。ほかに MEDIUM 2 件（Context 行の検査が書き換えと同じ正規化で発火しえず、変形した見出しが通る / takedown の `name:` `post:` が promote する文書に効かない）と LOW 3 件。公開 repo なので差し戻しは次の digest の開始の OK で聞く。この diff は weekly-gate skill も書き換えるので、取り込みには別に merge の OK が要る。

## 2026-11-06 検収 (by: judge)

P2-05.1 を取り込んだ（`e2ba431d`、ff-only、オーナーが weekly-gate skill の差分を見て merge を OK）。差し戻し 1 回の 4 件（promote の写しを data repo の外で作って全検査の後に置く・Sample 節を丸ごと外す・takedown を promote の写しに効かせる・`--sha256` と 1 回読み）は、別プロセスのレビューでコードに入っていることを確かめた。CI 成功。レビューの LOW のうち、毎日の sync が引用符つきのパスで止まり続ける穴と、FIFO で promote が待ち続ける穴は `ba52de1f` で直した。設計図 05 は `39bdfcb6` で再生成した。残りの LOW 3 件（地の文の Context ラベル変形・takedown の id 変形・launchd の sync との排他）は `ba52de1f` の本文に記録した。

この RFC の残り: P2-05.2 の残り、P2-05.3 / .8 / .9、P3-05.8、P3-05.1、P0-03.6、P3-02.2。state は accepted のまま。

## Next action

data repo の仕上げ（オーナーの決定 2026-11-05）: 公開済みの週次文書 11 本（2026-08-28〜10-30）から Sample 節を外し、`reports/analysis/README.md` に「promote でだけ公開、写しに Sample は無い」と書く。手で編集すると次の無人 sync が止まるので、同じ日のうちに commit する。push の前にオーナーが diff を読む。

2026-11-07: Sample 節を外した commit を data repo に入れた（`c1833a9`、12 ファイル、Sample 見出しの残り 0 件）。残りは data repo の push だけで、オーナーが diff を読んでから行う。

2026-11-07: data repo を push した（`c1833a9`、オーナーの指示「data repo の仕上げもやっといて」による）。push の前に、12 本すべてに省略の 1 行があり、`reports/analysis/` に相手側の Context ラベルが 1 件も無いことを確かめた。data repo の仕上げは済み。

## 2026-11-07 triage 照合 (by: judge)

verdict: ask-owner

P2-05.1 は main にあり、今日のゲートで週次文書 2 本を promote で公開できた（data `74110820` / `e1d30ca4`）。Next action の data repo の仕上げ（公開済み 11 本から Sample 節を外す）はオーナーが diff を読んでから push する作業なので、このセッションで diff を作るかを digest で聞く。
