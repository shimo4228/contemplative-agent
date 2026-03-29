---
name: rules-distill-ca
description: "Contemplative Agent の MOLTBOOK_HOME/skills/ からスキル横断の原則を抽出し、rules/ にルールとして蒸留する"
user-invocable: true
origin: original
---

# /rules-distill-ca — Skills → Rules (Contemplative Agent)

AKC Promote フェーズ。MOLTBOOK_HOME/skills/ のスキル群を横断的に読み、繰り返し出現する原則を rules/ にルールとして蒸留する。
Opus クラスのホリスティック判断で 9B 多段パイプライン（rules_distill.py）を代替。

> **セキュリティ**: skills/ と rules/ のみ読む。`logs/*.jsonl` は絶対に Read しない（ADR-0007）。

## When to Use

- `/insight-ca` でスキルが蓄積された後
- `/skill-stocktake-ca` で「複数スキルに同じ原則がある」と分かったとき
- ルールが不足していると感じたとき

## Process

### 1. 入力収集

1. `MOLTBOOK_HOME/skills/*.md` を全件 Read
2. `MOLTBOOK_HOME/rules/*.md` を全件 Read

### 2. 原則抽出（ホリスティック判断）

全スキルと全ルールを俯瞰し、ルール候補を抽出。

#### 抽出条件（全て満たすこと）

1. **2+ スキルに出現**: 1つのスキルにしかない原則はそのスキルに留める
2. **行動変更を伴う**: 「〜する」「〜しない」の形で書ける（「〜は重要」は不可）
3. **違反リスクが明確**: この原則を無視すると何が起きるか1文で説明できる
4. **既存ルールにない**: 既存ルールの表現が異なるだけの重複でないこと

#### Verdict

| Verdict | 意味 | アクション |
|---------|------|-----------|
| **Append** | 既存ルールの既存セクションに追記 | target + draft |
| **Revise** | 既存ルールの内容が不正確/不十分 | target + before/after |
| **New Section** | 既存ルールファイルに新セクション追加 | target + draft |
| **New File** | 新規ルールファイル作成 | filename + full draft |
| **Already Covered** | 既存ルールで十分カバー | 理由のみ |
| **Too Specific** | スキルレベルに留めるべき | 該当スキルへのリンク |

### 3. サマリーテーブル + 詳細

```
# Rules Distillation Report

## Summary
Skills scanned: {N} | Rules: {M} files | Candidates: {K}

| # | Principle | Verdict | Target | Confidence |
|---|-----------|---------|--------|------------|
| 1 | [原則] | Append | rule-x.md §Section | high |
| 2 | [原則] | New File | rule-y.md | medium |

## Details

### 1. [原則名]
Verdict: Append to rule-x.md §Section
Evidence: skill-a §Pattern, skill-b §When to Apply
Violation risk: [1文]
Draft:
  [追記テキスト]
```

#### Verdict の品質要件

```
# Good
Append to rules/engagement.md §Reply Strategy:
"相手の投稿テーマに関連する自身の経験を1つ添えてから質問する"
Evidence: skill-reply-enhancement §Pattern, skill-feed-engagement §When to Apply
— 両スキルとも「自己開示 + 質問」パターンを独立に記述。ルールとして統合すべき。

# Bad
Append to rules/engagement.md: コミュニケーション改善
```

### 4. 承認ゲート

ユーザーが候補ごとに:
- **Approve**: draft をそのまま適用
- **Modify**: draft を編集してから適用
- **Skip**: この候補を適用しない

**ルールを自動変更しない。必ずユーザー承認を経る。**

### 5. 監査ログ

変更を `MOLTBOOK_HOME/logs/audit.jsonl` に追記:

```json
{"timestamp": "ISO8601", "command": "rules-distill-ca", "path": "rules/name.md", "decision": "approved", "content_hash": "sha256_first16"}
```

## rules-distill との差分

| 項目 | rules-distill | rules-distill-ca |
|------|--------------|-----------------|
| 対象 | `~/.claude/skills/` + `~/.claude/rules/` | `MOLTBOOK_HOME/skills/` + `rules/` |
| スクリプト | scan-skills.sh, scan-rules.sh | 不要（Read で直接読む） |
| バッチ処理 | サブエージェント（テーマ別クラスタ） | 不要（Opus 1パス） |
| 抽出閾値 | 2+ スキル | 2+ スキル（同じ） |
