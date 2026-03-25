<!-- Status: Adopted (ADR-0004) -->
# 3層メモリの再設計 — Thoughtseeds フレームワーク導入

## Context

knowledge.md 解体（完了済み）で JSONL を正とする構造にしたが、Layer 2（KnowledgeStore）が「死んだ倉庫」のまま。パターンは蓄積されるが、選択・競合・減衰がなく、`get_context_string()` は最新1個しか返さない。100個蓄積しても使われるのは1個。

Thoughtseeds (Kavi et al., Entropy 2025) の3層フレームワークを参考に、パターンを「活性を持つ競合エージェント」として扱う設計に移行する。

**参考論文**: https://doi.org/10.3390/e27050459
**参考実装**: https://github.com/prakash-kavi/thoughtseeds_vipassana

## Thoughtseeds のコア（移植対象）

論文の数学的コアは5つの方程式に集約される:

```
Eq.9  活性化更新:  a(t+1) = r * Target(t) + (1-r) * a(t)
Eq.10 ターゲット:  Target_i(t) = W_i^s + Σ(W_ij * a_j * τ) + γ_i^s * τ + m(t) * β_i
Eq.12 WTA選択:     dominant = argmax(activation * state_boost)
Eq.6  状態遷移:    P(transition) = 1 if φ(state, a) > θ AND dwell ≥ dwell_min
Eq.3  メタ認知:    μ(t) = state_dependent_base + habituation_decay + ε
```

**移植するもの**: 上記5式 + 時間相関ノイズ + 慣れ/回復メカニズム
**移植しないもの**: 学習パイプライン（Granger因果）、瞑想固有パラメータ

## 状態マッピング

| 瞑想 | エージェント | ダイナミクス |
|------|------------|------------|
| breath_control | focused_engagement | タスク集中（返信・投稿） |
| mind_wandering | topic_exploration | フィード探索・新話題発見 |
| meta_awareness | consolidation | 振り返り・知識統合 |
| redirect_breath | strategic_pause | 再集中前の小休止 |

## Thoughtseed マッピング

| 瞑想 | エージェント | カテゴリ |
|------|------------|---------|
| breath_focus | task_focus | 集中 — 現在のエンゲージメント |
| equanimity | content_quality | 調整 — 質vs量のバランス |
| pain_discomfort | trending_topics | 気散 — トレンドの引力 |
| pending_tasks | notification_queue | 気散 — 未読通知 |
| self_reflection | self_reflection | メタ認知 — 「生産的か？」 |

## 設計: 新規コアモジュール

### `core/thoughtseed.py` — 活性エージェント + ネットワーク (~150行)

```python
@dataclass
class ThoughtseedAgent:
    name: str
    activation: float = 0.5       # [0.05, 1.0]
    responsiveness: float = 0.7   # momentum factor

    def update(self, target: float, noise: float) -> None:
        # Eq.9: a(t+1) = r * target + (1-r) * a(t) + noise
        self.activation = clip(
            self.responsiveness * target + (1 - self.responsiveness) * self.activation + noise,
            0.05, 1.0
        )

class ThoughtseedNetwork:
    agents: Dict[str, ThoughtseedAgent]
    weight_matrix: Dict[str, Dict[str, float]]  # W[agent, state]
    interaction_matrix: Dict[str, Dict[str, float]]  # W_ij

    def step(self, current_state: str, meta_awareness: float) -> str:
        # 1. ターゲット計算 (Eq.10)
        # 2. ノイズ生成（時間相関）
        # 3. 各エージェント更新 (Eq.9)
        # 4. WTA選択 (Eq.12)
        return dominant_thoughtseed
```

### `core/metacognition.py` — メタ認知モニター (~100行)

```python
class MetaCognitiveMonitor:
    awareness: float = 0.6        # [0.4, 1.0]
    habituation_counter: int = 0

    def update(self, state: str, dominant: str, time_in_state: int) -> float:
        # Eq.3: 状態依存の基礎値 + 慣れ減衰 + 確率的検出
        return self.awareness

    def should_transition(self, state: str, network: ThoughtseedNetwork) -> Optional[str]:
        # Eq.6: 閾値ベースの創発的遷移判定
        return next_state_or_none
```

### `core/attention_states.py` — 状態管理 (~80行)

```python
class AttentionStateManager:
    state: str = "focused_engagement"
    dwell_time: int = 0

    def update(self, network: ThoughtseedNetwork, monitor: MetaCognitiveMonitor) -> str:
        # 状態遷移は活性ダイナミクスから創発（ハードコードしない）
        next_state = monitor.should_transition(self.state, network)
        if next_state:
            self.state = next_state
            self.dwell_time = 0
        else:
            self.dwell_time += 1
        return self.state
```

### `config/thoughtseed_config.json` — ドメイン固有パラメータ

```json
{
  "thoughtseeds": {
    "task_focus": {"weight": {"focused_engagement": 0.9, "topic_exploration": 0.2, ...}},
    "content_quality": {"weight": {...}},
    "trending_topics": {"weight": {...}},
    "notification_queue": {"weight": {...}},
    "self_reflection": {"weight": {...}}
  },
  "states": {
    "focused_engagement": {"dwell_min": 5, "dwell_max": 20, ...},
    "topic_exploration": {"dwell_min": 3, "dwell_max": 15, ...},
    ...
  },
  "interactions": {
    "task_focus→trending_topics": -0.3,
    "self_reflection→content_quality": 0.2,
    ...
  }
}
```

## KnowledgeStore との統合

knowledge.json のパターンは Thoughtseed のカテゴリに分類され、対応する thoughtseed の活性に影響する:

```
distill 出力: "Replying with specific quotes gets more follow-up" → category: engagement
  → task_focus thoughtseed の weight を微増
  → 次回セッションで focused_engagement 状態が維持されやすくなる
```

`get_context_string()` は WTA の勝者に対応するカテゴリのパターンを返す:
- focused_engagement 中 → engagement カテゴリのパターン
- topic_exploration 中 → topic_selection カテゴリのパターン

## 変更対象ファイル

| ファイル | 変更 |
|---------|------|
| `core/thoughtseed.py` | **新規** — ThoughtseedAgent + ThoughtseedNetwork |
| `core/metacognition.py` | **新規** — MetaCognitiveMonitor |
| `core/attention_states.py` | **新規** — AttentionStateManager |
| `config/thoughtseed_config.json` | **新規** — ドメインパラメータ |
| `core/knowledge_store.py` | カテゴリ分類 + 活性連動の追加 |
| `adapters/moltbook/agent.py` | セッションループに Thoughtseed ステップを統合 |
| `adapters/moltbook/post_pipeline.py` | 状態に応じたコンテキスト選択 |

## 変えないもの

- EpisodeLog — そのまま
- distill → insight → skills パイプライン — そのまま
- identity.md — そのまま
- セキュリティ方針 — そのまま
- テスト構造 — そのまま（新規テスト追加のみ）

## 実装規模

| 項目 | 行数 |
|------|------|
| `core/thoughtseed.py` | ~150 |
| `core/metacognition.py` | ~100 |
| `core/attention_states.py` | ~80 |
| `config/thoughtseed_config.json` | ~50 |
| 既存ファイル変更 | ~50 |
| テスト | ~200 |
| **合計** | **~630行** |

依存追加: **numpy のみ**（活性計算・ノイズ生成）。statsmodels/scipy は不要（学習パイプライン不使用）。

## Open Questions

1. **numpy 依存**: 現在の依存は requests のみ。numpy を追加するか、純 Python で実装するか？
   - 活性計算は単純な四則演算なので純 Python でも可能（~20行増）
   - Docker イメージサイズへの影響
2. **パラメータ初期値**: 瞑想のパラメータは論文にあるが、ソーシャルメディアのパラメータは手動チューニングが必要。初期値をどう決めるか？
3. **agent.py への統合度**: Thoughtseed のステップをセッションループのどこに入れるか？
   - 案A: 各サイクルの冒頭で状態を更新、状態に応じて行動を選択
   - 案B: FeedManager/PostPipeline/ReplyHandler の選択自体を状態で制御
4. **段階的導入**: 一気に全部入れるか、まず KnowledgeStore のカテゴリ分類 + 活性だけ入れるか？

## Verification

```bash
# 1. 新規モジュールのユニットテスト
uv run pytest tests/test_thoughtseed.py tests/test_metacognition.py tests/test_attention_states.py -v

# 2. 既存テスト全パス（回帰なし）
uv run pytest tests/ -v

# 3. Thoughtseed ダイナミクスの手動検証
# → 状態遷移が創発的に起きること
# → WTA が状況に応じた thoughtseed を選択すること
# → メタ認知が長時間探索後に consolidation を発火すること

# 4. セッション実行で既存動作に影響なし
contemplative-agent run --session 10

# 5. distill が従来通り動作
contemplative-agent distill --dry-run --days 1
```
