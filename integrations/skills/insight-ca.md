---
name: insight-ca
description: "Contemplative Agent の knowledge.json (uncategorized) から行動スキルを抽出し、MOLTBOOK_HOME/skills/ に生成する"
user-invocable: true
origin: original
---

# /insight-ca — Knowledge → Skills (Contemplative Agent)

AKC Extract/Curate フェーズ。knowledge.json の uncategorized パターンを読み、行動スキルを抽出する。
Opus クラスのホリスティック判断で 9B 多段パイプライン（insight.py）を代替。

> **セキュリティ**: knowledge.json（サニタイズ済み）のみ読む。`logs/*.jsonl`（エピソードログ）は絶対に Read しない（ADR-0007）。

## When to Use

- `contemplative-agent distill` 実行後、knowledge.json にパターンが蓄積されたとき
- 既存スキルが古くなり、新しい行動パターンを反映したいとき
- `/skill-stocktake-ca` で Retire/Merge 判定が出た後の補充

## Process

### 1. 入力収集

1. `MOLTBOOK_HOME/knowledge.json` を Read
   - `"category": "uncategorized"` のパターンのみ対象（constitutional, noise は除外）
   - 3件未満なら終了（パターン不足）
2. `MOLTBOOK_HOME/skills/*.md` を全件 Read（重複回避用）

### 2. スキル抽出（ホリスティック判断）

knowledge パターン全体を俯瞰し、以下の観点でスキルを抽出:

- **行動パターンの集約**: 類似する複数パターンを1つのスキルに統合
- **具体性**: 「〜すべき」ではなく「〜する手順」レベルの具体性
- **既存スキルとの差分**: 既に MOLTBOOK_HOME/skills/ にある内容と重複しないこと

出力フォーマット（スキルごと）:

```markdown
# [Descriptive Skill Name]

**Context:** [このスキルが適用される状況]

## Pattern
[学習した行動パターンの要約]

## When to Apply
[トリガー条件]
```

### 3. 品質ゲート（チェックリスト + ホリスティック判定）

#### 3a. チェックリスト

各スキル候補に対して:

- [ ] `MOLTBOOK_HOME/skills/` の既存スキルと内容重複がないか確認した
- [ ] 既存スキルへの追記で済まないか検討した
- [ ] 一回限りの出来事ではなく再利用可能なパターンであることを確認した
- [ ] forbidden pattern（API key, password 等）が含まれていないことを確認した

#### 3b. ホリスティック判定

| Verdict | 意味 | アクション |
|---------|------|-----------|
| **Save** | 独自・具体的・再利用可能 | Step 4 へ |
| **Improve then Save** | 価値はあるが要改善 | 改善 → 再判定（1回まで） |
| **Absorb into [X]** | 既存スキルに追記すべき | 追記内容を提示 → Step 4 へ |
| **Drop** | 些末・冗長・抽象的 | 理由を説明して終了 |

### 4. 承認ゲート

各スキルの Verdict、チェックリスト結果、内容をユーザーに提示:

```
### Skill 1: [name]
Verdict: Save
Checklist: ✓ 重複なし / ✓ 新規が適切 / ✓ 再利用可能 / ✓ forbidden pattern なし

[スキル全文]
```

承認されたスキルのみ Write to `MOLTBOOK_HOME/skills/{slug}.md`。

### 5. 監査ログ

承認/拒否を `MOLTBOOK_HOME/logs/audit.jsonl` に追記:

```json
{"timestamp": "ISO8601", "command": "insight-ca", "path": "skills/name.md", "decision": "approved", "content_hash": "sha256_first16"}
```

## learn-eval との差分

| 項目 | learn-eval | insight-ca |
|------|-----------|------------|
| 入力 | セッションコンテキスト | knowledge.json (uncategorized) |
| 出力先 | `~/.claude/skills/learned/` | `MOLTBOOK_HOME/skills/` |
| Global/Project 判定 | あり | なし（常に MOLTBOOK_HOME） |
| LLM | セッション中の Claude | Opus ホリスティック判断 |
