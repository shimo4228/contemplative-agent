# ADR-0016: insight = narrow generator / skill-stocktake = broad consolidator

## Status

partially-superseded-by ADR-0097（「stocktake = 広い統合器」の半分は 2026-08-22 に退役 — 統合は土曜ゲートへ移った。「insight = 狭い生成器」、BATCH_SIZE=10、self-reflection の routing、rarity の撤去は効力を保つ）

## Date

2026-04-11

## Context

insight パイプラインには、それぞれ別の品質問題を解こうとする 3 つの密結合メカニズムが積み重なっていた:

1. **Subcategory バッチング** (`_build_subcategory_batches`): LLM にバッチごとにテーマ的にまとまった入力を与える
2. **2 段階クラスタリング** (`_group_patterns`, `2ced140` で導入): 各 subcat バッチ内で LLM が top-30 パターンをテーマ別にさらに分割し、1 バッチから複数スキルを生成
3. **Rarity スコアリング** (`_score_rarity_existing`, `_score_rarity_batch`, `DISTILL_RARITY_PROMPT`): LLM で新規性を数値化し、`importance * rarity` のソート tiebreaker として使用

2026-04-11 の実測 (214 パターン):

- 7 subcat バッチ → 22 スキル抽出
- ユーザー選別で 6/22 採用 (選別率 27%)
- 選別所感: 「22 スキルはほぼ同内容」— Emptiness 公理が「30 パターンを 1 スキルに凝縮する」プロセスで具体性を溶解している

並行して 2 つの潜在欠陥が顕在化:

- **rarity が 1.0 で固定されるバグ**: `_score_rarity_existing` が比較対象を `rarity is not None` でフィルタしているため、初回実行では比較対象ゼロ → 全パターンが 1.0 になり、以降のループは `rarity is None` しか拾わないので永遠に再計算されない
- **identity 蒸留の入力が曖昧**: `distill_identity` は全 subcat から importance top-50 を取っており、行動規範と自己省察が混在。本来 identity の材料である self-reflection パターンが他の subcat と椅子取りゲームになっていた

均質化問題は sort key の調整では解決できない。原因は Emptiness 憲法公理であり、LLM の synthesis 中に作用するため、事前のソート順をいじってもモデルが下流で溶解する結果は変わらない。

## Decision

insight と skill-stocktake の役割分担を明文化し、それに合わせて insight を簡素化する:

**Insight = narrow generator**: 1 run につき subcat ごとに 1 スキル、その subcat の importance 上位 N パターンを入力とする。subcat 横断の合成なし、バッチ内クラスタリングなし。

**Skill-stocktake = broad consolidator**: subcat 横断の merge、重複検出、交差テーマ発見を担当。スキルファイル空間で動作 (パターン空間ではない)。

具体的変更:

1. **rarity 機能を完全削除**: `_score_rarity_existing` / `_score_rarity_batch` / `DISTILL_RARITY_PROMPT` / `config/prompts/distill_rarity.md` / `KnowledgeStore.add_learned_pattern` の `rarity` 引数 / insight の `_FALLBACK_RARITY` を削除。insight sort key を `importance` 単独に

2. **`_group_patterns` (2段階クラスタリング) を削除**: subcat によるグループ化と冗長で、1 スキルあたりのパターン数を増やすことで Emptiness の溶解力を強めていた

3. **insight の `BATCH_SIZE` を 30 → 10 に縮小**: 入力を小さくすることで具体性を保ち、ナレッジが増えても 1 run あたりの LLM コール数が発散しない

4. **`self-reflection` subcategory を `distill_identity` に routing**: insight から完全除外。`distill_identity` は `KnowledgeStore.get_context_string(category="uncategorized", subcategory="self-reflection", limit=50)` で self-reflection パターンのみを読む。`get_context_string` に `subcategory` パラメータを新規追加

5. **均質化を insight レイヤで解こうとしない**: 憲法公理 (Emptiness) の効果として認め、品質管理は skill-stocktake とユーザー選別に委ねる

## Alternatives Considered

- **rarity を直して残す**: `id(p)` で現バッチを比較対象から除外すれば動作する。却下理由: importance と概念的にオーバーラップする (新規性が高く重要なパターンはそもそも importance が高くつく)、rarity は sort tiebreaker としてしか使われていない、subcat バッチングが既に diversity を提供している

- **cap=30 のまま維持**: 却下理由: checkpoint で選別率 27% だったため、cap を下げる = 「1 スキルあたりのパターン数」を直接下げることが Emptiness 溶解の緩和につながる。cap=10 にすることで `_GROUP_SKIP_THRESHOLD=10` を下回り、2 段階クラスタリング自体が skip される

- **将来のスケールのために `_group_patterns` を残す**: 却下理由: speculative dead code。将来 cross-cluster なテーマ分割が必要になったら、それは skill-stocktake の領域 (skill 空間の global view を持つ) であり、insight の local view ではない

- **subcategory バッチングを廃止して global top-N importance でフラット化**: 却下理由: subcategory は正当な役割を持つ (extraction プロンプトにテーマラベルを渡してスキルを方向づける)。廃止すると LLM が内容からテーマを推論しなければならず、self-reflection の routing も不可能になる

- **insight を変えずに self-reflection を別チャンネルで流す**: 却下理由: self-reflection を insight と identity の両方に流すと出力が重複し、「内的状態 vs 外的行動」の区別が曖昧になる

## Consequences

- **1 run あたりのスキル数が少なく集中的になる**: 最大 6 スキル/run (7 subcat − self-reflection)、各スキルは ≤10 パターンを要約。insight の LLM コール数は ~28 (grouping × 7 + extraction × 22) から ~6 (extraction のみ) に減少

- **identity 蒸留の入力がクリーンになる**: self-reflection は identity へ、行動パターンは skill へ。フィードバックループ (identity が pattern を形作り、pattern が identity を更新) は自己観察データ内に閉じ、行動規範からのドリフトが減る

- **skill-stocktake が重要度を増す**: insight が subcat 揃いのスキルしか出さないため、交差テーマは stocktake 経由でしか発見されない。stocktake を定期実行しないとスキル空間が平坦になる (6 バケット × N run)。`skill-stocktake --stage` + `adopt-staged` ワークフローが標準操作として既にあるので許容範囲

- **knowledge スキーマから rarity が消える**: 既存の `knowledge.json` に `rarity` フィールドがあってもロード時に無視され、次回書き込み時に剥がれる。マイグレーションスクリプト不要

- **均質化問題は明示的に未解決**: 今後の対処は憲法プリセット比較 (Emptiness 以外の公理) や identity 蒸留プロンプトの改善で行う。sort key のエンジニアリングでは解けない

- **`feedback_simplicity` に沿う**: ~130 行のコード削減、LLM パイプラインパス 1 つ削減、プロンプトテンプレート 1 つ削除。同時に設計原則を将来の読み手に対して明文化
