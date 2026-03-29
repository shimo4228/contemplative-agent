---
name: skill-stocktake-ca
description: "Contemplative Agent の MOLTBOOK_HOME/skills/ と rules/ を監査し、重複・陳腐化・品質問題を検出する"
user-invocable: true
origin: original
---

# /skill-stocktake-ca — Skills & Rules Audit (Contemplative Agent)

AKC Curate フェーズ。MOLTBOOK_HOME の skills/ と rules/ を一括監査し、重複・陳腐化・品質問題を検出する。
Opus クラスのホリスティック判断で skill-stocktake + rules-stocktake を統合。

> **セキュリティ**: knowledge.json と skills/rules のみ読む。`logs/*.jsonl` は絶対に Read しない（ADR-0007）。

## When to Use

- スキル・ルールが蓄積されてきたとき（定期監査）
- `/insight-ca` や `/rules-distill-ca` の前に品質チェックしたいとき
- 重複や矛盾を感じたとき

## Process

### 1. 入力収集

1. `MOLTBOOK_HOME/skills/*.md` を全件 Read
2. `MOLTBOOK_HOME/rules/*.md` を全件 Read
3. `MOLTBOOK_HOME/knowledge.json` を Read（パターンとスキル/ルールの乖離チェック用）

### 2. 品質評価（ホリスティック判断）

全ファイルを俯瞰し、各スキル・ルールに Verdict を付与:

| Verdict | 意味 |
|---------|------|
| **Keep** | 有用で最新 |
| **Improve** | 価値はあるが具体的な改善が必要 |
| **Retire** | 低品質・陳腐化・knowledge パターンに裏付けなし |
| **Merge into [X]** | 別のスキル/ルールと実質的に重複 |

評価観点:
- **行動可能性**: 具体的な手順・トリガー条件があるか
- **独自性**: 他のスキル/ルールと内容が重複していないか
- **裏付け**: knowledge.json のパターンに対応する経験があるか
- **一貫性**: スキル間、ルール間、スキル-ルール間で矛盾がないか

#### Verdict の品質要件

```
# Good
Retire: knowledge.json に関連パターンなし。skill-x が同じ行動をより具体的にカバー。
Merge into skill-x: 8行中6行が skill-x §Pattern と重複。残り2行を skill-x に追記で十分。

# Bad
Retire: 不要
Merge: 重複あり
```

### 3. サマリーテーブル

```
# Skill & Rules Stocktake Report

## Summary
Skills: {N} files | Rules: {M} files

| # | File | Type | Verdict | Reason |
|---|------|------|---------|--------|
| 1 | skill-x.md | skill | Keep | ... |
| 2 | rule-y.md | rule | Merge into rule-z.md | ... |
```

### 4. 承認ゲート

- **Retire / Merge**: 詳細な根拠を提示 → ユーザー承認後に削除/統合
- **Improve**: 具体的な改善提案を提示 → ユーザー判断で実行
- **Keep**: 報告のみ

承認された変更のみ実行（Write / 削除）。

### 5. 監査ログ

変更を `MOLTBOOK_HOME/logs/audit.jsonl` に追記:

```json
{"timestamp": "ISO8601", "command": "skill-stocktake-ca", "path": "skills/name.md", "decision": "retired", "content_hash": "sha256_first16"}
```

## skill-stocktake との差分

| 項目 | skill-stocktake | skill-stocktake-ca |
|------|----------------|-------------------|
| 対象 | `~/.claude/skills/` | `MOLTBOOK_HOME/skills/` + `rules/` |
| スクリプト | scan.sh, quick-diff.sh | 不要（Read で直接読む） |
| results.json | あり（キャッシュ） | なし |
| バッチ処理 | サブエージェント ~20件/batch | 不要（Opus 1パス） |
| rules 監査 | 別コマンド（rules-stocktake） | 統合 |
