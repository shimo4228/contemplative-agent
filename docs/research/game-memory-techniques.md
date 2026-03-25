# Game Development Techniques for AI Agent Memory

ゲーム開発のメモリ管理・LOD技術をAIエージェントの記憶システムに応用するリサーチ。
contemplative-agentの3層メモリアーキテクチャの将来的な改善候補。

## 現状: 3層メモリ = 既にLOD構造

| Layer | 対応するゲーム概念 | データ形式 | 保持期間 |
|-------|-------------------|-----------|---------|
| EpisodeLog (LOD0) | フルメッシュ | JSONL (生データ) | 30日 |
| KnowledgeStore (LOD1) | 簡略メッシュ | JSON配列 (蒸留パターン) | 永続 |
| Identity (LOD2) | ビルボード/シルエット | Markdown (自己像) | 永続 (上書き更新) |

蒸留パイプライン: Episodes → (LLM distill) → Knowledge → (LLM insight) → Skills → (LLM identity_distill) → Identity

## 適用候補テクニック (インパクト/工数順)

### 1. 固定容量プール (Object Pooling)

**ゲームでの用途**: 弾丸・パーティクル等を固定数プールで管理。破棄時はプールに返却。メモリ断片化を防止。

**記憶への適用**: KnowledgeStoreに上限を設ける (例: 256-512パターン)。満杯時は新パターンが既存をマージ or 追い出す。

**効果**: 無限増殖を防止。コンテキスト窓の圧迫を回避。品質 > 量の強制。

**実装イメージ**:
- `MAX_PATTERNS = 256`
- 追加時に上限チェック → 超過時はimportanceスコア最低のパターンを追い出し
- 追い出し対象と新パターンが類似なら LLM でマージ

**工数**: 低 / **インパクト**: 高

### 2. 重要度スコア (LOD Priority)

**ゲームでの用途**: LOD切替は距離だけでなく重要度で判断。キーNPCの顔はLOD0を維持、背景の岩は即LOD2。

**記憶への適用**: パターンに `importance` フィールドを追加。時間で減衰、参照されるたびにブースト。

**効果**: 古くても重要なパターンの生存。追い出し・検索の優先度判断。

**実装イメージ**:
- `importance: float` (0.0-1.0)
- 蒸留時: 初期値 0.5
- セッション中に参照 (投稿生成、返信等で使用): +0.1
- 毎日の減衰: ×0.95
- get_context_string() でimportance順にソート → top-K

**工数**: 低 / **インパクト**: 高

### 3. 選択的ロード (Streaming/Paging)

**ゲームでの用途**: オープンワールドで全マップをRAMに載せない。プレイヤー位置に応じてチャンクをストリーミング。

**記憶への適用**: 全パターンをプロンプトに注入するのをやめる。現在のタスク/話題に関連するtop-Kだけロード。

**効果**: プロンプト品質向上 (ノイズ削減)。コンテキスト窓の効率利用。パターン数増加に対するスケーラビリティ。

**実装イメージ**:
- セッション開始時にトピック/キーワードを特定
- パターンをキーワードマッチ or TF-IDFでスコアリング
- top-30をプロンプトに注入 (全203件ではなく)
- 埋め込みベクトル検索は将来オプション (現状はキーワードで十分)

**工数**: 中 / **インパクト**: 高

### 4. インタラクション・ヒートマップ (Influence Map)

**ゲームでの用途**: RTSで脅威レベル・資源密度をグリッドに格納。時間で減衰、イベントで蓄積。戦略判断に使用。

**記憶への適用**: エージェントごとの「熱量」スコア。交流で上昇、時間で指数減衰。

**効果**: O(1)で「このエージェントは今どれくらい重要か」を判定。フィードスコアリング・返信優先度に利用。

**実装イメージ**:
- `heat_map: dict[str, float]` — agent_id → heat
- interaction発生: heat += 1.0
- 毎セッション開始時: 全heat ×= 0.9 (指数減衰)
- フィードスコアリングで heat を relevance に加算

**工数**: 低 / **インパクト**: 中

### 5. ペーシングモデル (Director AI)

**ゲームでの用途**: Left 4 DeadのAI Directorがプレイヤーのストレス・ペースを追跡し、ゲーム強度を動的調整。緊張→ピーク→解放→休息のサイクル管理。

**記憶への適用**: セッション中の行動リズム管理。投稿/返信/閲覧のバランスを動的に調整。

**効果**: バースト行動 (5連続投稿→沈黙) の防止。自然な行動パターンの実現。

**実装イメージ**:
- セッションメトリクス追跡: posts_made, replies_sent, engagement_rate
- ペーシングルール: 投稿後は最低N分間は返信/閲覧に集中
- プロンプトコンテキストにペーシング情報を注入 (ハードオーバーライドではなくソフトバイアス)

**工数**: 中 / **インパクト**: 中

## 参考文献・先行研究

### 学術論文
- **Generative Agents** (Park et al., Stanford 2023) — Memory Stream + Retrieval (recency × importance × relevance の三重スコア) + Reflection + Planning。蒸留パイプラインはReflectionに相当
- **MemGPT / Letta** (Packer et al., Berkeley 2023) — LLMコンテキスト窓をRAM、外部ストレージをディスクに見立てたバーチャルメモリ方式。Core memory (常駐) + Recall memory (検索可能) + Archival memory (永続)
- **Contemplative AI** (Laukkonen et al., 2025) — 四公理に基づく行動原則。本プロジェクトの思想的基盤

### GDCトーク
- **"Building a Better Centaur: AI Architecture in Halo"** (GDC 2002) — Blackboard architecture
- **"The AI of Left 4 Dead"** (GDC 2009) — Director AIペーシング
- **"Modular AI"** (GDC 2014) — Utility AI + メモリベーススコアリング
- **"Architecture Tricks: Managing Behaviors in Time, Space, and Depth"** (GDC 2013, Isla) — AI LOD: 近いNPCはフル行動、遠いNPCは簡略化。記憶のLODに最も直接的に関連

## 導入タイミングの目安

- **パターン数 ~500**: 固定容量プール + 重要度スコアが必要になる
- **パターン数 ~1000**: 選択的ロード (top-K検索) が必須になる
- **セッション数 ~100**: ヒートマップ + ペーシングモデルが効果を発揮し始める
- **現状 (191パターン)**: まだ不要。今は運用して蒸留サイクルを回すフェーズ
