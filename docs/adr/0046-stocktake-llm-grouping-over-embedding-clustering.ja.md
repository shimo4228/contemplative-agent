# ADR-0046: Stocktake の重複検出 — embedding クラスタリングではなく LLM グルーピング

## Status

accepted

## Date

2026-05-30

## Context

`skill-stocktake`（および対となる `rules-stocktake`）は冗長なスキル・ルールを検出し、各冗長群を統合する。コミット `316719f`（2026-04-15）は、それ以前の LLM ベース重複検出を embedding-cosine + single-linkage union-find クラスタリングへ置き換えた。動機は純粋に性能で、`core/llm.generate()` が `num_predict=8192` をハードコードしていたため、旧方式が M1 開発機でハングしていた。

embedding のみのクラスタリングは、このコードベースでは **over-merge する**。auto-extract されたスキルは共有ボイラープレート語彙 — "emptiness pruning"、"trembling texture"、friction-to-insight の枠組み — を大量に共有するため、本質的に別個の具体パターンどうしでも cosine 類似度が 0.90 以上になる。そこへ推移的 single-linkage union-find が全体を 1 つの連結成分に連鎖させる。実地で観測された: **18 スキルが 1 つの統合群に collapse した**。

群単位の `CANNOT_MERGE` セーフティネット（merge LLM が誤った群を却下できる仕組み）は、**既に連鎖した blob を分割できない**。群ごとに all-or-nothing だからである。embedding クラスタリングが N スキルを 1 成分に連鎖させてしまうと、merge 段はその集合を丸ごと受理するか却下するかしかなく、single-linkage が破壊した構造を回復する手段を持たない。

第二の失敗は merge プロンプト自体にあった。「共有する core behavior を特定し ONE comprehensive skill を生成せよ」と指示しており、N スキルを最大公約数の抽象へ縮約していた。この flatten で **個々の具体的 trigger→action パターンが脱落**した — 例えば「upvote-burst → 投稿を作成する」というポリシーが失われた。

`316719f` の性能上の動機は現在では無効である。その後すべての `generate()` 呼び出しが明示的な `num_predict` を渡すよう更新され、ハングは再発しえない。

## Decision

重複検出と merge 挙動に、協調する 2 つの変更を採用する。

1. **重複検出を LLM 単一グルーピング呼び出しへ revert する。** 全候補スキル本文を 1 回の `generate()` で送り、`{"groups": [{files, reason}]}` を返させ、`_parse_groups` でパースする。LLM が本文全体を読むため、具体的振る舞いで弁別する: 語彙や枠組みを共有しても別個の行動を規定するスキルは、別群のまま、あるいは未グループのまま残される。グルーピングプロンプト（`config/prompts/stocktake_skills.md`、`stocktake_rules.md`）は明示的に指示する — 語彙は共通でも具体的振る舞いが異なるなら group するな、1 つの catch-all より複数の小さな coherent な群を優先せよ。

2. **merge プロンプトを「合成」から「和集合」へ反転する。** 「共有する core behavior を特定」を次へ置き換える: 全固有具体パターンの UNION を生成せよ; 逐語的ボイラープレートのみ dedup せよ; 1 入力にしか現れない振る舞いは必ず生存させよ; 2 つの別個の具体的行動を 1 つの generic な行動へ collapse させるな。`merge_group` の `num_predict` は群サイズでスケールする: `min(8192, max(3000, 500 × n))`。

`core/thresholds.py` と `core/snapshot.py` から dead になった `SIM_CLUSTER_THRESHOLD` 定数を削除する。

これらはコミット `7224b30`（merge プロンプト反転）と `0f05ecf`（グルーピング revert）で実装した。

## Alternatives Considered

### `SIM_CLUSTER_THRESHOLD` を 0.80 から 0.90 へ引き上げる

cosine 閾値を締めて over-grouping を減らす。却下 — このコードベースの auto-extract スキルでは ボイラープレート語彙が cosine 空間を支配し、本質的に別個のスキルでも 0.90 を超える。閾値というノブでは、embedding が見られないパターンを分離できない。

### single-linkage の代わりに average-linkage を使う

連鎖を減らすため single-linkage を average-linkage に置き換える。却下 — 18 スキルは ≥0.80 cosine でほぼ完全グラフを成すため、その閾値での average-linkage でも統合してしまう。具体パターンの差は、どの妥当な閾値でも blob を避けるほどには embedding を動かさない。

### 類似度スコア前に共有ボイラープレートを除去する

cosine 計算前にスキル本文を前処理して共有語彙を除く。却下 — 「何がボイラープレートか」の定義には、まさに embedding にできない種類の判断が要る。脆い heuristics を保守する羽目になり、新しいドメイン語彙で破綻する。

### embedding クラスタリングを残し merge プロンプトだけ直す

グルーピングはそのままに、merge プロンプトの synthesis→union 反転だけを行う。却下 — 反転した merge プロンプトは群内の flatten は解決するが over-grouping は解決しない。blob は依然形成され、merge 段は未分化の 1 成分を受け取り続ける。

### 元の性能ハングに対し caller 別に `num_ctx` を最適化する

グルーピングアルゴリズムを替えず、caller 別に `num_ctx` を上限設定して M1 のハングを直す。別件として先送り。M1 16GB での真の遅さは生成モデル（qwen3.5:9b）が推論中に swap することであり、これは stocktake アルゴリズムの問題ではなくモデル選定の問題で、本 ADR の射程外。

## Consequences

### Positive

- 重複検出が再び具体的振る舞いで弁別する。実地結果: 18 スキル → 5 小群 + standalone 8; merge ゲートが 2 群を `CANNOT_MERGE` で却下し 3 群を統合 → blob なしの穏当な 18→16 consolidation。
- union 指向の merge プロンプトが具体パターンを保存する。synthesis-merge が落としていた 5 パターンのうち、2 が完全に、2 が部分的に回復した。
- LLM グルーピング 1 回が O(N²) のペア呼び出しを置き換え、ハングを排しつつ高速を維持。`SIM_CLUSTER_THRESHOLD` 定数とその 2 箇所の呼び出しを完全に除去。

### Negative

- LLM グルーピングは網羅的でなく、明白な near-duplicate ペアを取り逃しうる。同じ実地 run で観測: `fluid-administrative-content-coupling-with-frictio` が、`fluid-engagement-coupling-and-reformation` のほぼ逐語的な双子であるにもかかわらず standalone のまま残った。
- 既に広い入力を統合すると過度に広い統合スキルを生みうる。実地 run の 1 結果はトリガー 10 個を抱え、スキルが確実に発火可能であるための選択性閾値を下回った。
- 単一グルーピング呼び出しは非常に大きなスキルストアでは `num_ctx` に制約される。現状は制約でないが、ストアが育つと制約になる。
- 最深の天井 — auto-extract スキルが contemplative-AI 由来の共有ボイラープレートで jargon 支配されること — は insight 抽出プロンプトの上流にある。その問題は本 ADR の射程外と意識的に扱い、エージェントの現在の抽出限界として受容する。

### Neutral / Follow-ups

- 本 ADR が置き換える embedding クラスタリングはコミット `316719f`（2026-04-15）で導入され、独自の ADR には記録されていなかった。その除去をここに記録する。
- スキルストアが単一グルーピング呼び出しが `num_ctx` を超える規模に育った場合の候補アプローチは 2-pass グルーピング: 軽量な embedding 事前フィルタで候補ペアを作り、そのペアにのみ LLM 判断をかける。

## Related

- [ADR-0016](./0016-insight-narrow-stocktake-broad.md) — Insight as Narrow Generator, Stocktake as Broad Consolidator; 本 ADR は stocktake consolidator の重複検出メカニズムを精緻化する。
- 本 ADR が置き換える embedding クラスタリングはコミット `316719f` で導入され、独自の ADR は持たない。
