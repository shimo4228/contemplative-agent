<!-- Status: Partial (influenced distill pipeline design) -->
# 記憶固定化リサーチ — 人間の記憶メカニズムとAIエージェントメモリ設計

## 核心的発見

人間の記憶固定化は「要約」でも「ベクトル化」でもない。
**エピソードを訓練データとして使い、パターンを蒸留する**プロセス（CLS理論）。

## CLS理論（McClelland 1995）との対応

| 脳 | 現在の設計 | 生物学的に忠実な設計 |
|---|---|---|
| 海馬（エピソード保存） | `episode_log.py` (JSONL) | そのまま維持 |
| 睡眠リプレイ | `distill.py` (LLM要約) | 選択的リプレイ + 構造化抽出 |
| 大脳皮質（汎化モデル） | `knowledge.json` (テキスト要約) | 潜在特徴を持つ構造化知識オブジェクト |
| 再固定化 | 未実装 | 潜在原因推論に基づく更新 vs 新規作成 |

## 5つの知見

### 1. 睡眠中の固定化 = 選択的リプレイによる生成圧縮モデルの訓練
海馬がその日のエピソードを再生し、大脳皮質のVAE的モデルを訓練する。全エピソードを等しく固定化するのではなく、新奇性と報酬で重み付けされた選択的リプレイ。(Barron et al. 2024, Nature Human Behaviour)

### 2. エピソード→意味記憶 = 保存と抽象化の両方
MINERVA 2: 全エピソードを保持、検索時に類似度加重で抽象を計算。CLS: エピソードから漸次的にスキーマを抽出。現代の統合: 脳は両方やる。海馬がエピソードを保持、大脳皮質がリプレイで漸次的にスキーマを抽出。(Hintzman 1986; McClelland 1995)

### 3. 再固定化 = 潜在原因推論
記憶が想起されると不安定になり、同じ潜在原因 → 既存記憶を更新、新しい潜在原因 → 新記憶を並行作成。(Gershman et al., eLife 2017)

### 4. Structured Distillation の知見
蒸留は**検索ルーティング用**であって表示用ではない。蒸留されたものはコンパクトなインデックスで、実際のリコールは元のエピソード（原文）に戻る。ベクトル検索で品質を保持、BM25 + ベクトルの融合が単体を上回る。(arXiv 2603.13017)

### 5. Sleep-Time Compute の実装例
- **Letta** (2025): デュアルエージェント。sleep-time エージェントがアイドル中にメモリを再編成
- **arXiv 2504.13171**: 反復的にコンテキストを精錬。5倍のテスト時計算削減、13-18%精度向上
- **"Language Models Need Sleep"**: RL ベースの知識播種 + 夢見フェーズ

## 推奨アーキテクチャ

```
Layer 1: EpisodeLog (JSONL)
  ↓ sleep-time embedding
Layer 2: 検索インデックス（構造化オブジェクト: コア洞察 + タグ + 関連度スコア）
  ↓ 定期統合
Layer 3: Knowledge パターン（インデックスから生成、生エピソードからではない）

検索時: インデックスで探す → 元のエピソードを読む（具体性が必要な場合）
                          → Knowledge パターンを読む（汎用性が必要な場合）
```

## 現在の distill の問題

Layer 2（検索インデックス）と Layer 3（知識パターン）を一気にやろうとしていた。
分離すれば各ステップがシンプルになる。

## ソース

- Barron et al. (2024) Nature Human Behaviour — 睡眠中の生成圧縮モデル
- McClelland et al. (1995) — CLS理論
- Hintzman (1986) — MINERVA 2
- Gershman et al. (2017) eLife — 再固定化と潜在原因推論
- arXiv 2603.13017 — Structured Distillation
- arXiv 2504.13171 — Sleep-time compute
- Letta blog (2025) — Sleep-time エージェント
- Kavi et al. (2025) Entropy — Thoughtseeds
