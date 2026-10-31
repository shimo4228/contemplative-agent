# T-GAP1 前提照合 — 2026-08-16

<!-- 2026-10-31 に非公開ノートから昇格した写し（P3-02.5）。plan docs/plans/whimsical-coalescing-trinket.md の Phase 0。file:line は 2026-08-16 時点。 -->

## 検証済み — 計測装置は台帳の主張どおり動く

- `--dry-run` は何も書かない: `cli/memory_cmds.py:128`（snapshot skip）/ `core/distill.py:830`
  (`mutate_existing=not dry_run`) / `:833-835`（早期 return）/ `:199`（save は `not dry_run` 条件）。
  `embeddings.sqlite` は adapter のエピソード埋め込み専用（`adapters/moltbook/config.py:45`）で
  distill の `_embed_patterns`（`distill.py:697-705`）は通らない — 書き込み面は本当に無い
- 計器は post-dedup の add 集合だけ: `core/distill.py:789-798`（コメントが明示的に宣言）
- ログ行の実文字列: `core/view_metrics.py:337-339` + `distill.py:800` →
  `dry-run instrument: diversity — n=... pairwise cosine mean=... p50=... p90=...`。`:.2f` 固定
- run lock: `cli/memory_cmds.py:53-54`（`blocking=True`）
- memory guard: pairwise は `n>3000`（`view_metrics.py:69,247`）、cluster は `n>500`（`:63,263`）
- worktree 隔離が load-bearing: 本番 distill は `com.moltbook.distill.plist` が 03:30 JST に
  **メインの `.venv`** で起動。worktree venv の `_PROJECT_ROOT` は実測で worktree に解決した

## 反証 — 一次資料は存在する（初回報告の訂正）

非公開ノート `archive/self-reflection-pipeline-future-work-2026-05-13.md:44-71`（未昇格） に 10-mode 表・
カバレッジ判定・追加案の文言例・リスク注記。ADR-0038:69 がリンクを張らなかったのは
非公開ノートが gitignored で CLAUDE.md が ADR→`.notes` 参照を禁じているため。失われていない。

## 崩れている前提

- **(a) 「mode 7/8/9」は列挙の続きではない。** 番号はプロンプト内の体系ではなく外から当てた
  分析フレーム。`distill_episode.md:5` は 4 項目のフラット列挙、同一 4 項目が
  `distill_postgate.md:7` に複写。表の ✓ は「散文が結果的にその mode を誘発している」の意味
- **(b) 「0 件」は介入前のコーパスの読み。** 非公開ノート `self-reflection-classification-2026-07-03.md:32-45`（未昇格）
  の 7/8/9 = 0/0/0 が読んだのは日付 06-23〜07-02（`:29-30`）。ADR-0072 の register 介入は同じ
  07-03 に `5912f5b` で出荷。**再計数の結果は [mode-recount.md](mode-recount.md)**
- **(c) mode 7 は現行プロンプトと構造的に衝突する。** `distill_episode.md:5`「Describe what was
  observed, not what to do about it」+ `:7` の moment-indexed 過去形レジスタ に対し、
  05-13 note `:56` は mode 7 を「未来志向、現 prompt は過去形」と明記。ADR-0072 が過去形
  レジスタを強化した今は、未カバーではなく**設計上の排除**
