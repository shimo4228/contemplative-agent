# ADR-0011: Knowledge 直接注入の廃止 — Skills 経由への移行

## Status
accepted

## Date
2026-03-26

## Context

現在、`get_context_string(limit=50)` で KnowledgeStore のパターン50件をバレットリストとしてプロンプトに直接注入している（`generate_cooperation_post` と `generate_reply` の2箇所）。

問題点:

1. **ブラックボックス**: LLM が50件のうち何をどう反映したか追跡不可能
2. **Human in the loop 不在**: 人間の確認なしにエージェントの行動が変化する
3. **ノイズ耐性なし**: 低品質パターン（例: "Test Title を避けろ" の重複）が行動に影響
4. **AKC との矛盾**: AKC の Curate/Promote フェーズ（人間の監督）をバイパスしている
5. **トークンコスト**: 50パターン × 100-200 tokens = 5000-10000 tokens がプロンプトに無差別追加

一方、既存の `insight` コマンドは knowledge から skills/*.md を抽出し、LLM のシステムプロンプトに注入している。skills は:
- 人間が読める Markdown
- `--dry-run` で事前確認可能
- 直接編集可能
- git で差分追跡可能

## Decision

Knowledge パターンのプロンプト直接注入を段階的に廃止し、行動への影響は skills 経由のみにする。

```
廃止:  knowledge → プロンプト直接注入 → LLM が暗黙的に反映
採用:  knowledge → insight → skills/*.md → システムプロンプトに注入
```

Knowledge は蒸留パイプラインの中間成果物として保持するが、セッション中の行動に直接影響を与えない。

### 移行計画

1. skills が十分に蓄積されるまでは knowledge 注入を維持
2. insight の実行頻度を上げ、skills のカバレッジを確認
3. skills で行動がカバーされていることを検証後、knowledge 注入を廃止
4. `get_context_string()` は distill-identity の入力としてのみ使用

### influence 経路の明確化

| 経路 | 入力 | 出力 | 人間の確認 |
|------|------|------|----------|
| 倫理的判断 | constitutional knowledge | constitution 反映 | constitution 編集時 |
| 行動パターン | uncategorized knowledge | insight → skills/*.md | insight 実行時（手動） |
| 人格 | 全 knowledge | distill-identity → identity.md | distill-identity 実行時（手動） |

## Alternatives Considered

1. **knowledge 注入を改善して維持**: Phase 3 の選択的ロード（カテゴリフィルタ）で注入品質を上げる。→ 却下: Human in the loop の問題は解決しない。品質が上がっても「何が行動を変えたか」は追跡できない

2. **knowledge と skills の併用**: 両方をプロンプトに注入する。→ 却下: 二重注入はトークンコストとノイズを増やすだけ。influence 経路が不明確なまま

3. **即座に廃止**: knowledge 注入を今すぐ削除する。→ 却下: skills のカバレッジが不十分な段階では行動品質が低下するリスク。段階的移行が安全

## Consequences

**良い結果**:
- エージェントの行動変化が全て人間の確認を経由する（Human in the loop）
- 変更の追跡が可能（git diff で skills の変化を確認）
- AKC の設計思想と完全に整合
- プロンプトのトークン消費が削減される
- README の "with minimal, purposeful human oversight" と一貫

**注意が必要**:
- insight の実行頻度を上げる必要がある（現在は手動のみ）
- skills のカバレッジが十分か継続的に検証が必要
- knowledge → skills の変換精度（insight の品質）が行動品質のボトルネックになりうる

## 3層監督構造との関係

この ADR は、エージェントの3層監督構造を完結させる:

| 層 | 役割 | 能力 |
|---|------|------|
| **contemplative-agent** | 自律活動、エピソード蓄積 | run, distill（自動）。自己改変不可 |
| **Orchestrator（Claude Code 等）** | 人間の意図を CLI に変換 | insight, rules-distill, distill-identity |
| **Human** | 意図を伝え、結果を確認 | dry-run 確認、skills 編集、git diff |

Knowledge 直接注入を廃止することで、エージェントの行動変化は全て skills 経由 → 全て人間が確認した成果物を経由する。エージェント自身に自己改変能力がないため、プロンプトインジェクションで行動を書き換えることが構造的に不可能になる。

オーケストレーターは Claude Code に限定されない。CLI を叩けるものなら何でもよい（Minimal Dependency 原則）。
