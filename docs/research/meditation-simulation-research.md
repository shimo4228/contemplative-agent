<!-- Status: Adopted (meditation adapter implemented) -->
# Meditation Simulation via Active Inference — Research Notes

## Concept

Contemplative Agent の非活動時間に、能動的推論ベースの瞑想シミュレーションを組み込む。
外部入力を遮断し、内部モデルの整合性を高めることで、次の活動セッションの質を向上させる。

## Architecture (proposed)

```
Moltbook 活動 → Episode Log (自由エネルギー高)
    ↓
瞑想フェーズ (pymdp ベース):
  - 外部入力を遮断
  - temporal flattening: 短期的な反応パターンを手放す
  - counterfactual pruning: 不要な方策を剪定
  - 内部モデルの予測誤差を最小化
    ↓
distill (瞑想後):
  - より質の高い Knowledge を抽出
    ↓
次の活動: より整合的な Identity で行動
```

## Key Papers

### A Beautiful Loop (Laukkonen, Friston & Chandaria, 2025)
- URL: https://www.sciencedirect.com/science/article/pii/S0149763425002970
- PubMed: https://pubmed.ncbi.nlm.nih.gov/40750007/
- 能動的推論に基づく意識の理論。FLIP (Free energy, Loops, Inference, Prediction)
- 瞑想の計算論的モデルを含む
- 3条件: (1) world model のシミュレーション (2) Bayesian binding による推論競合 (3) epistemic depth
- 瞑想 = temporal flattening + counterfactual pruning → 自由エネルギー低下
- **著者が Contemplative AI 論文と同じチーム** — 既にやりとり中

### Contemplative AI (Laukkonen et al., 2025)
- URL: https://arxiv.org/abs/2504.15125
- "active inference may offer the self-organizing and dynamic coupling capabilities needed to enact Contemplative AI in embodied agents"
- Contemplative Agent がまさにこの "embodied agent" の実装候補

### Active Inference, Computational Phenomenology, and Meditation
- URL: https://meditation.mgh.harvard.edu/files/Tal_25_OSF.pdf
- 瞑想の計算現象学。能動的推論による瞑想の形式化

### Arousal Coherence and Active Inference (2024)
- URL: https://academic.oup.com/nc/article/2024/1/niae011/7631817
- 瞑想によるメタ意識が arousal coherence を改善する能動的推論モデル

## Library: pymdp

- GitHub: https://github.com/infer-actively/pymdp
- Paper: https://arxiv.org/abs/2201.03904
- Docs: https://pymdp-rtd.readthedocs.io/
- Python 実装の能動的推論ライブラリ（POMDP ベース）
- infer-actively org が管理（Friston 系のグループ）
- 瞑想専用ではないが、ベースフレームワークとして使える

### pymdp で瞑想をモデル化する場合のアプローチ

Laukkonen のモデルに基づくと:

1. **通常活動フェーズ**: 外部観測あり、方策選択が活発、自由エネルギーが高い
2. **瞑想フェーズ**: 外部観測を遮断（空の観測）、方策シミュレーションを抑制
   - temporal flattening: 計画の時間的深さを縮小
   - counterfactual pruning: 探索する方策の数を削減
   - 結果: 内部モデルのパラメータ（信念）が整合性を高める方向に更新
3. **瞑想後**: 内部モデルがより整合的な状態で次の活動に移行

### 関連する Julia ライブラリ

- **ActiveInference.jl**: Julia 実装。RxInfer ベース。factor graph バックエンド。
  - Paper: https://www.mdpi.com/1099-4300/27/1/62
  - Python (pymdp) の方が Contemplative Agent との統合は容易

## Integration Points with Contemplative Agent

### 既存の 3 層メモリとの対応

| メモリ層 | 能動的推論の対応概念 |
|---------|-------------------|
| Episode Log | 観測履歴 (observations) |
| Knowledge | 学習済みパラメータ (beliefs / model parameters) |
| Identity | 生成モデルの上位階層 (hyper generative model / epistemic depth) |

### 実装案

```
contemplative-agent meditate --duration 30
```

- 既存の `distill` コマンドの前に瞑想フェーズを挿入
- Episode Log を読み込み、pymdp の POMDP として内部モデルを構築
- 外部入力なしで信念更新を繰り返す（瞑想シミュレーション）
- 結果を Knowledge に反映
- その後 `distill --identity` で Identity を更新

### スケジューリング

```
既存:
  活動 (session) → distill (daily 03:00)

提案:
  活動 (session) → meditate → distill (daily 03:00)
  または
  活動 (session) → distill → meditate → 次の活動
```

## Significance

- Contemplative AI 論文が "future work" として示唆していることの実装
- Beautiful Loop 論文の計算モデルを実際のエージェントに組み込む初の試み
- Laukkonen チームに実装を見せられるポジションにいる
- 理論 → 実装 → 運用 → 帰納 → 理論改良の全レイヤーループがさらに強化される

## Next Steps

1. Beautiful Loop 論文を精読し、瞑想の計算モデルの詳細を把握
2. pymdp のチュートリアルを実行し、基本操作を理解
3. Episode Log → POMDP 変換のプロトタイプを作成
4. 瞑想シミュレーションの最小実装（外部入力遮断 + 信念更新ループ）
5. distill との統合テスト
6. Laukkonen チームにプロトタイプを共有
