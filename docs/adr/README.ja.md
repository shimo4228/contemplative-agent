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
| [0013](0013-shelve-coding-agent-skills.ja.md) | コーディングエージェントスキルのお蔵入り `[AKC: Curate/Promote]` | accepted | 2026-03-28 |
| [0014](0014-retire-system-spec.ja.md) | system-spec.md の廃止 `[AKC: Maintain]` | accepted | 2026-04-01 |
| [0015](0015-one-external-adapter-per-agent.ja.md) | 1エージェント1外部アダプタ原則 | accepted | 2026-04-08 |
| [0016](0016-insight-narrow-stocktake-broad.ja.md) | insight = narrow generator / skill-stocktake = broad consolidator `[AKC: Extract/Curate]` | accepted | 2026-04-11 |
| [0017](0017-yogacara-eight-consciousness-frame.ja.md) | 唯識八識モデルを設計の枠組みとする | accepted | 2026-04-11 |

## ADR の種別

このプロジェクトの ADR は 2 種類に分かれ、編集ルールが異なる:

**問題解決 ADR (emergent)**
具体的な課題に触発された反応的な設計判断を記録する。この index に載っている ADR の大半はこの種別。同じ問題に対するより良い解が見つかれば、後続の ADR で上書き (supersede) できる。

例: ADR-0005 (SessionContext リファクタリング)、ADR-0008 (2 段階蒸留パイプライン)、ADR-0009 (importance score)、ADR-0016 (insight narrow / stocktake broad)。

**世界観 ADR (axiomatic)**
プロジェクトが最初から作動している mental model や哲学的フレームを記録する。これらは反応的ではない — **問題解決 ADR がそもそも定式化できる前提** として機能する。世界観 ADR を変えることはバグ修正とは違う、プロジェクトのアイデンティティを変更する行為であり、別レベルの判断を要する。

例: ADR-0002 (論文準拠 CCAI 適用)、ADR-0007 (セキュリティ境界モデル)、ADR-0017 (唯識八識モデル)。

**判定のヒント**: その ADR が「同じ問題を抱えた別プロジェクトでも違う形で書かれうる」なら問題解決 ADR。その ADR が「プロジェクトの問題がそもそも読み取れるようになるための枠組み」を記述するなら世界観 ADR。世界観 ADR は下流を持たない (何かの結果ではない)、問題解決 ADR は (たとえ名指されていなくても) 世界観の下流にある。

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
