# Memory Evolution Research Report

contemplative-agent の記憶システム改善に向けた統合リサーチレポート。
ゲーム開発技術、先行研究、ユーザー着想の3系統を統合し、現行アーキテクチャとのギャップを分析する。

## ソース

| ID | ソース | 内容 |
|----|--------|------|
| S1 | `docs/research/game-memory-techniques.md` | ゲーム開発の LOD/メモリ管理技術の応用候補 |
| S2 | Gmail「アイデア」(2026-03-23 13:49) | 多段推論 + 審判LLM = メモリー蒸留エンジン |
| S3 | Gmail「アイデア２」(2026-03-23 16:59) | 小型LLM × タスク分割 × ReAct = MLOps的自動改善 |
| S4 | Gmail「アイデア３」(2026-03-23 17:02) | 入れ子型フラクタルPDCA構造 |
| S5 | コードベース調査 | 現行メモリアーキテクチャの実装詳細 |
| S6 | Web先行研究調査 | Generative Agents, MemGPT, A-MEM, Mem0 等 |

---

## 1. 現行アーキテクチャの実態

### 3層メモリ構造

| Layer | 格納形式 | 容量制限 | 検索方式 | プロンプト注入 |
|-------|---------|---------|---------|--------------|
| EpisodeLog | JSONL (日別) | なし (append-only) | タイムスタンプ + record_type | 直接注入なし。蒸留の入力 |
| KnowledgeStore | JSON配列 | **なし** | タイムスタンプのみ | 最新100件をバレット注入 |
| Identity | Markdown | ~4000 tokens | N/A (全文ロード) | システムプロンプトの基盤 |

### KnowledgeStore パターン構造（現状）

```json
{
  "pattern": "学習した行動パターン（テキスト）",
  "distilled": "2026-03-18T12:30+00:00",
  "source": "2026-03-18~2026-03-19"
}
```

**存在しないフィールド**: importance, relevance, embedding, tags, keywords, links

### 蒸留パイプライン（2段階）

```
EpisodeLog (JSONL)
  → Stage 1: LLM で要約・パターン抽出（30エピソード/バッチ）
  → Stage 2: LLM でJSON構造化・リファイン
  → KnowledgeStore に追記

KnowledgeStore (JSON)
  → insight コマンド: LLM でスキル抽出（30パターン/バッチ）
  → config/skills/*.md に書き出し

KnowledgeStore + Identity
  → distill_identity: LLM で人格蒸留
  → config/identity.md を更新（旧版はアーカイブ）
```

### 品質ゲート（現状）

- パターン: 30文字以上 & 3単語以上（`_is_valid_pattern`）
- セキュリティ: `FORBIDDEN_SUBSTRING_PATTERNS` による禁止語チェック
- **意味的な品質判定なし**（重複、矛盾、有用性の評価がない）

---

## 2. 先行研究との比較

### Generative Agents（Park et al., Stanford 2023）

**Memory Stream**: 全記憶を時系列ストリームに格納し、3重スコアリングで検索。

```
score = α_recency × recency + α_importance × importance + α_relevance × relevance
```

| スコア | 計算方法 | contemplative-agent の現状 |
|--------|---------|--------------------------|
| Recency | 最終アクセスからの指数減衰（係数 0.995） | `get_context_string()` が最新100件を返すのみ。減衰なし |
| Importance | LLM が 1-10 で評価（蒸留時に付与） | **なし** |
| Relevance | embedding のコサイン類似度 | **なし**（全文検索もなし） |

**Reflection**: 蓄積した記憶から高次の洞察を生成。contemplative-agent の `insight` コマンドがこれに相当するが、Generative Agents は**セッション中に自動で** reflection を走らせる点が異なる。

### MemGPT / Letta（Packer et al., Berkeley 2023）

**仮想メモリ方式**: LLM のコンテキスト窓 = RAM、外部ストレージ = ディスク。

| MemGPT | contemplative-agent | ギャップ |
|--------|-------------------|---------|
| Core Memory（常駐、~5000文字、編集可能） | Identity（常駐、~4000 tokens、セッション中は固定） | セッション中の自己更新なし |
| Recall Memory（会話履歴DB、テキスト検索） | EpisodeLog（JSONL、タイムスタンプ検索のみ） | テキスト検索なし |
| Archival Memory（ベクトルDB、セマンティック検索） | KnowledgeStore（JSON配列、順序のみ） | セマンティック検索なし |

**決定的な違い**: MemGPT は LLM 自身が function call で必要な記憶をページインする。contemplative-agent は固定的に最新100件を注入。

### A-MEM（NeurIPS 2025）

**Zettelkasten 式**: 各記憶を7属性のノートとして構造化。

```
ノート = {原文, タイムスタンプ, キーワード, タグ, コンテキスト説明, embedding, リンク先}
```

- embedding に `all-minilm-l6-v2`（軽量、ローカル実行可能）
- 削除ではなく**進化**（新記憶追加時に関連記憶のコンテキストを LLM で更新）
- top-K 検索で 1,200-2,500 tokens に圧縮（競合は ~16,900 tokens）

### Mem0（プロダクション向け、2025）

- 会話から事実を抽出 → 既存記憶に対して ADD / UPDATE / DELETE / NOOP を LLM が判定
- ベクトル検索 + グラフ走査のハイブリッド
- 時間経過による decay メカニズム

---

## 3. ユーザー着想の評価

### S2: 多段推論 + 審判LLM = メモリー蒸留エンジン

**着想**: 小型LLM A が初期解 → 小型LLM B が批評 → 審判LLM が収束判定＆蒸留

**先行研究との照合**:
- Multi-Agent Debate（ICLR 2025 大規模検証）の結果、**同種小型モデルの議論は精度が壊滅的に悪化**する（Llama 3.1-8B で AgentVerse が MMLU 13.27%、単体 43.13%）
- 原因: フォーマット維持能力の不足
- **有効なケース**: 異種モデルの組み合わせのみ

**現実的な応用**: qwen3.5:9b 単体での multi-agent debate は非推奨。代わりに:
- **Self-Consistency**: 同じプロンプトで複数回推論し多数決（MAD より単純かつ安定）
- **Schema-Guided Reasoning**: 蒸留の各ステップで推論フィールドを明示的に構造化
- **品質ゲート追加**: 蒸留結果を「書き込む価値があるか」1回の LLM 呼び出しで判定

### S3: 小型LLM × タスク分割 × ReAct = MLOps的自動改善

**着想**: タスク分割の検証・調整を ReAct パターンで自動化。Claude Code のようなオーケストレーターに任せる。

**先行研究との照合**:
- Blueprints + Prompt Template Search（2025）: SLM 向けに構造化テンプレートを自動生成・最適化。Phi3-mini (3.8B) で数学・コーディングの精度が大幅向上
- ReAct パターンのループ安定性は model size に依存

**現実的な応用**: contemplative-agent は SNS エージェントであり、タスク分割の最適化対象が限定的。ただし蒸留パイプライン自体を「タスク」と見なして改善ループを組む応用はありうる（S2 の品質ゲートの拡張として）。

### S4: 入れ子型フラクタルPDCA構造

**着想**: 各レイヤーが独立した PDCA を持つ入れ子構造。すべての自律エージェントに適用可能。

**評価**: アーキテクチャ哲学としては正しい。contemplative-agent の蒸留パイプラインは既に「EpisodeLog → KnowledgeStore → Identity」の各層で PDCA 的なサイクルを回している。明示的な「評価 → 改善」ステップを各層に追加することで、この構造をより意識的に実装できる。

---

## 4. ギャップ分析

現行アーキテクチャと先行研究の差分を、改善インパクト順に整理する。

### Gap 1: パターンに意味的メタデータがない（最大のギャップ）

**現状**: `pattern`, `distilled`, `source` の3フィールドのみ。
**先行研究の標準**: importance, recency, embedding, keywords, tags, links。

**影響**:
- 検索が時系列順のみ → 古くても重要なパターンが埋もれる
- 全100件をバレット注入 → ノイズが多くプロンプト品質が低い
- 重複パターンの検出・マージができない

### Gap 2: 選択的ロードがない

**現状**: `get_context_string(limit=100)` で最新100件を無条件注入。
**先行研究の標準**: クエリ（現在のタスク/話題）に基づく top-K 検索。

**影響**:
- 191パターン中100件を注入 = 関連性の低いパターンが大量に含まれる
- パターン数が増えると状況が悪化（500件で最新100件 = 古い有用パターンが永久に消失）

### Gap 3: 蒸留の品質ゲートが弱い

**現状**: 30文字 & 3単語以上の最小バリデーションのみ。
**先行研究の標準**: 重複判定、矛盾チェック、importance 評価、既存知識との統合判定。

**影響**:
- 類似パターンが複数蓄積される（手動で確認しないと気づかない）
- 低品質パターンが蓄積し、プロンプトのノイズになる

### Gap 4: 時間減衰がない

**現状**: パターンは追加された順序で永続。古さによるペナルティなし。
**先行研究の標準**: 指数減衰（Generative Agents: 0.995/step）、参照によるブースト。

### Gap 5: セッション中の記憶更新がない

**現状**: セッション開始時にロード → セッション中は固定 → セッション終了後に蒸留。
**MemGPT の方式**: セッション中に LLM 自身が記憶を検索・更新。

**評価**: これは意図的な設計判断の可能性が高い（qwen3.5:9b の function call 能力の制約）。優先度は低い。

---

## 5. 改善候補の統合評価

全ソースからの改善候補を統合し、**実現可能性 × インパクト** で評価する。

### Tier 1: 低工数 × 高インパクト（即実行可能）

| # | 改善 | ソース | 工数 | 効果 | 依存追加 |
|---|------|--------|------|------|---------|
| A | **importance スコア導入** | S1, S6 (Generative Agents) | 低 | KnowledgeStore のパターンに `importance: float` を追加。蒸留時に LLM が 1-10 で評価、参照でブースト、時間で減衰 | なし |
| B | **蒸留品質ゲート強化** | S2, S6 (Mem0) | 低 | Stage 2 の後に「書き込む価値があるか」「既存パターンと重複しないか」を LLM 1回で判定。ADD/UPDATE/SKIP の3択 | なし |
| C | **get_context_string() の importance 順ソート** | S1, S6 | 低 | 現在の「最新100件」→「importance 上位 top-K」に変更。A の導入が前提 | なし |

### Tier 2: 中工数 × 高インパクト（パターン数増加時に必要）

| # | 改善 | ソース | 工数 | 効果 | 依存追加 |
|---|------|--------|------|------|---------|
| D | **キーワードベース選択的ロード** | S1, S6 (A-MEM) | 中 | セッションのタスク/話題に基づくキーワードマッチで top-30 を選択。TF-IDF は numpy で実装可能 | なし |
| E | **固定容量プール** | S1 | 低 | `MAX_PATTERNS = 512`。超過時は importance 最低を追い出し or マージ | なし（A が前提） |
| F | **パターンへの keywords/tags 付与** | S6 (A-MEM) | 中 | 蒸留時に LLM がキーワードとタグを生成。検索精度が向上 | なし |

### Tier 3: 高工数 × 中〜高インパクト（将来的な進化）

| # | 改善 | ソース | 工数 | 効果 | 依存追加 |
|---|------|--------|------|------|---------|
| G | **embedding ベース検索** | S6 (A-MEM, Generative Agents) | 高 | all-minilm-l6-v2 で embedding → cosine similarity で top-K。最高精度の選択的ロード | sentence-transformers or onnxruntime |
| H | **インタラクション・ヒートマップ** | S1 | 低 | エージェントごとの交流熱量スコア。返信優先度に活用 | なし |
| I | **ペーシングモデル** | S1 | 中 | 行動リズム管理。バースト防止 | なし |

### Tier 4: 研究段階（contemplative-agent への直接適用は限定的）

| # | 改善 | ソース | 評価 |
|---|------|--------|------|
| J | Multi-Agent Debate 蒸留 | S2 | qwen3.5:9b 単体では非推奨（ICLR 2025 検証で小型モデルの MAD は壊滅的） |
| K | ReAct 自動タスク最適化 | S3 | SNS エージェントにはオーバースペック。蒸留パイプライン改善には応用可能 |
| L | フラクタルPDCA | S4 | 設計哲学として有用。具体的な実装は Tier 1-2 の品質ゲート強化で部分的に実現 |

---

## 6. 推奨ロードマップ

### Phase 1: メタデータ基盤（~200行の変更）

**目標**: KnowledgeStore のパターンに importance スコアを導入し、注入品質を改善する。

```
1. パターン構造を拡張:
   { "pattern": "...", "distilled": "...", "source": "...",
     "importance": 0.5, "last_accessed": "..." }

2. 蒸留時に importance を LLM 評価で付与（1-10 → 0.0-1.0 に正規化）

3. get_context_string() を importance 順 top-K に変更

4. セッション中の参照でブースト（+0.1）、日次で減衰（×0.95）
```

**前提条件**: なし
**検証方法**: 既存テストの更新 + importance 分布の可視化

### Phase 2: 蒸留品質ゲート（~100行の変更）

**目標**: 重複・低品質パターンの蓄積を防止する。

```
1. Stage 2 の後に品質判定ステップを追加:
   - 新パターンと既存 top-10 類似パターンを比較
   - LLM が ADD / UPDATE(既存をマージ) / SKIP を判定
   - UPDATE の場合、既存パターンの importance をブースト

2. 蒸留レポートに品質ゲート統計を追加
```

**前提条件**: Phase 1（importance フィールド）
**検証方法**: dry-run での判定結果サンプリング

### Phase 3: 選択的ロード（~150行の変更）

**目標**: セッションのタスクに関連するパターンだけをプロンプトに注入する。

```
1. パターンに keywords フィールドを追加（蒸留時に LLM が生成）

2. セッション開始時にタスクキーワードを特定

3. キーワードマッチ + importance でスコアリング → top-30 を注入

4. 将来的に embedding 検索に置換可能な interface にしておく
```

**前提条件**: Phase 1, Phase 2
**検証方法**: 注入パターンの関連性を手動サンプリング

### Phase 3.5: insight パイプライン改善

**目標**: distill で導入した品質改善手法を insight（スキル抽出）にも適用する。

**適用候補**:
1. **スキル重複排除**: 新スキルを既存 `config/skills/*.md` と difflib 比較。重複なら既存スキルにマージ or SKIP
2. **importance フィルタ**: insight の入力パターンを importance 順で選別。低品質パターンからのスキル抽出を回避
3. **プロンプト分割**: insight のプロンプトが複数タスクを含む場合、distill と同様に分離

**前提条件**: Phase 1-2 の安定運用を確認後。insight.py の現状調査が必要
**検証方法**: dry-run でスキル生成結果を確認、既存スキルとの重複率を計測

### Phase 4 以降（パターン数 500+ で検討）

- 固定容量プール（MAX_PATTERNS = 512）
- embedding ベース検索（依存追加の判断が必要）
- ヒートマップ / ペーシング

---

## 7. 認知アーキテクチャとの対応

先行研究のサーベイ（TMLR 2024）で定着した4種メモリ分類との対応:

| 認知アーキテクチャ | contemplative-agent | 改善後 |
|-------------------|-------------------|--------|
| Working Memory | セッション中の MemoryStore in-memory データ | 変更なし |
| Episodic Memory | EpisodeLog (JSONL) | 変更なし（研究素材として永続保持） |
| Semantic Memory | KnowledgeStore (JSON) | importance + keywords + 選択的ロード |
| Procedural Memory | config/rules/, config/skills/, prompts.py | 変更なし（insight コマンドで自動生成済み） |

---

## 参考文献

### 学術論文
- Park, J. S. et al. (2023). Generative Agents: Interactive Simulacra of Human Behavior. ACM UIST 2023.
- Packer, C. et al. (2023). MemGPT: Towards LLMs as Operating Systems. arXiv:2310.08560.
- Xu, Z. et al. (2025). A-MEM: Agentic Memory for LLM Agents. NeurIPS 2025. arXiv:2502.12110.
- Choudhary, T. et al. (2025). Mem0: Building Production-Ready AI Agent Memory. arXiv:2504.19413.
- Du, Y. et al. (2024). Improving Factuality and Reasoning in Language Models through Multiagent Debate. ICML 2024.
- Sumers, T. R. et al. (2024). Cognitive Architectures for Language Agents. TMLR 2024.
- Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. arXiv:2504.15125.

### 技術リソース
- Letta Documentation: https://docs.letta.com/concepts/memgpt/
- A-MEM GitHub: https://github.com/agiresearch/A-mem
- Mem0 GitHub: https://github.com/mem0ai/mem0
- Agent Memory Paper List: https://github.com/Shichun-Liu/Agent-Memory-Paper-List
- Multi-LLM-Agents Debate (ICLR 2025): https://d2jud02ci9yv69.cloudfront.net/2025-04-28-mad-159/blog/mad/

### プロジェクト内部
- ADR-0004: 3層メモリアーキテクチャ
- ADR-0008: 2段階蒸留パイプライン
- docs/research/game-memory-techniques.md
- docs/CODEMAPS/architecture.md

---

*Generated: 2026-03-24*
*Sources: game-memory-techniques.md, Gmail (アイデア/アイデア2/アイデア3), codebase investigation, web research*
