# Architecture Decision Records

このプロジェクトの主要な設計判断を記録する。

## 一覧

| ADR | タイトル | Status | Date |
|-----|---------|--------|------|
| [0001](0001-core-adapter-separation.md) | Core/Adapter 分離 | accepted | 2026-03-10 |
| [0002](0002-paper-faithful-ccai.md) | 論文準拠 CCAI 適用 | accepted | 2026-03-12 |
| [0003](0003-config-directory-design.md) | Config ディレクトリ設計 | accepted | 2026-03-12 |
| [0004](0004-three-layer-memory.md) | 3層メモリアーキテクチャ `[AKC: Extract/Curate/Promote]` | accepted | 2026-03-17 |
| [0005](0005-session-context-refactoring.md) | SessionContext リファクタリング | accepted | 2026-03-14 |
| [0006](0006-docker-network-isolation.md) | Docker ネットワーク分離 | accepted | 2026-03-14 |
| [0007](0007-security-boundary-model.md) | セキュリティ境界モデル | accepted | 2026-03-12 |
| [0008](0008-two-stage-distill-pipeline.md) | 2段階蒸留パイプライン `[AKC: Extract]` | accepted | 2026-03-22 |
| [0009](0009-importance-score.md) | KnowledgeStore Importance Score `[AKC: Extract/Quality Gate]` | accepted | 2026-03-24 |
| [0010](0010-research-data-sync.md) | 研究データ同期 | accepted | 2026-03-25 |
| [0011](0011-knowledge-injection-to-skills.md) | Knowledge 直接注入の廃止 → Skills 経由 `[AKC: Curate]` | accepted | 2026-03-26 |
| [0012](0012-human-approval-gate.md) | 行動変更コマンドの人間承認ゲート `[AKC: Curate/Promote]` | accepted | 2026-03-26 |

## テンプレート

新しい ADR を追加する際は以下のフォーマットに従う:

```markdown
# ADR-NNNN: タイトル

## Status
accepted / superseded by ADR-XXXX / deprecated

## Date
YYYY-MM-DD

## Context
何が問題だったか

## Decision
何を決めたか

## Alternatives Considered
却下した案とその理由

## Consequences
この判断の結果どうなったか
```

## 運用ルール

- 番号は連番（0001〜）、時系列順
- 既存 ADR の変更は新 ADR で supersede する（上書きしない）
- 小さな判断は記録不要。アーキテクチャ・データモデル・セキュリティに影響する判断のみ
- `/sync-context` で ADR index とファイルの整合性をチェックできる
