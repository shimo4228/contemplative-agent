# ADR-0004: 3層メモリアーキテクチャ

## Status

accepted

## Date

2026-03-17

## Context

当初 knowledge.md にエージェント関係・投稿トピック・インサイト・学習パターンを全て格納していた。情報が重複し（JSONL にも同じデータが存在）、knowledge.md が肥大化。蒸留のたびに全体を書き換えるため、差分管理も困難だった。

## Decision

メモリを3層に分離し、各層の責務を明確化:

| 層 | ファイル | 責務 | 更新頻度 |
|---|---------|------|---------|
| L1: EpisodeLog | `~/.config/moltbook/logs/YYYY-MM-DD.jsonl` | 生データ (append-only) | リアルタイム |
| L2: KnowledgeStore | `config/knowledge.json` | 蒸留された知識パターンのみ | バッチ (distill) |
| L3: Identity | `config/identity.md` | エージェント人格定義 | バッチ (identity distill) |

補助ストア:

- `agents.json`: フォロー状態のみ（known agents は L1 interaction から構築）
- `config/skills/*.md`: 行動スキル（insight コマンドで生成）

**廃止したもの:**

- knowledge.md（JSON 配列の knowledge.json に置換）
- knowledge.md 内の Agent Relationships / Post Topics / Insights セクション（JSONL が正）
- history/knowledge/ スナップショット（パターンに distilled 日付が付与されるため不要）

## Alternatives Considered

- **knowledge.md を維持し構造化**: セクション分けを厳格にする案。しかし Markdown の自由記述は蒸留 LLM が壊しやすい
- **SQLite**: 構造化クエリが可能だが、git diff で変更が追えない。config/ に入れるファイルとして不適切
- **全て JSONL に統合**: 蒸留結果も JSONL に。しかし「蒸留済みパターン」は構造化データとして JSON 配列の方が扱いやすい

## Consequences

- JSONL は正（Single Source of Truth）。蒸留はそこから派生するビュー
- knowledge.json はパターン配列のみで、1パターンあたり distilled 日付付き
- エピソードログは研究材料として絶対に削除しない（ADR-0007 セキュリティ方針とも関連）
- identity.md は forbidden pattern 検証を通過したもののみ書き込み
