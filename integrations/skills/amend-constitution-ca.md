---
name: amend-constitution-ca
description: "Contemplative Agent の knowledge.json (constitutional) から憲法改正案を起草し、MOLTBOOK_HOME/constitution/ を更新する"
user-invocable: true
origin: original
---

# /amend-constitution-ca — Constitutional Amendment (Contemplative Agent)

AKC Promote フェーズ。knowledge.json の constitutional パターンから憲法改正案を起草する。
Opus クラスのホリスティック判断で 9B パイプライン（constitution.py）を代替。

> **セキュリティ**: knowledge.json と constitution/ のみ読む。`logs/*.jsonl` は絶対に Read しない（ADR-0007）。

## When to Use

- `contemplative-agent distill` で constitutional パターンが 3件以上蓄積されたとき
- エージェントの倫理的判断に改善の余地があると感じたとき
- constitution テンプレートを切り替えた後、経験に基づく調整をしたいとき

## Process

### 1. 入力収集

1. `MOLTBOOK_HOME/knowledge.json` を Read
   - `"category": "constitutional"` のパターンのみ対象
   - 3件未満なら終了（倫理的経験不足）
2. `MOLTBOOK_HOME/constitution/*.md` を全件 Read（現行憲法）

### 2. 改正案起草（ホリスティック判断）

constitutional パターンと現行憲法を俯瞰し、改正案を起草:

- **構造保持**: 現行憲法のカテゴリ構造（Emptiness, Non-Duality, Mindfulness, Boundless Care 等）を尊重
- **経験反映**: constitutional パターンが示す倫理的学びを条項に反映
- **最小変更**: 必要な箇所のみ改正。全面書き換えを避ける
- **整合性**: 改正箇所が他の条項と矛盾しないこと

### 3. 品質ゲート

改正案を以下の観点で自己評価:

- [ ] 現行憲法の構造が保持されているか
- [ ] 改正箇所が constitutional パターンの具体的な経験に裏付けられているか
- [ ] 改正によって既存の条項間に矛盾が生じていないか
- [ ] forbidden pattern（API key, password 等）が含まれていないか
- [ ] 改正の必要性が明確か（不要な改正をしていないか）

### 4. 承認ゲート

改正案をユーザーに提示:

```
# Constitution Amendment Proposal

## Changes
[変更箇所の要約]

## Rationale
[各変更の根拠となる constitutional パターン]

## Full Text
[改正後の全文]
```

承認後のみ Write to `MOLTBOOK_HOME/constitution/{name}.md`。

### 5. 監査ログ

承認/拒否を `MOLTBOOK_HOME/logs/audit.jsonl` に追記:

```json
{"timestamp": "ISO8601", "command": "amend-constitution-ca", "path": "constitution/contemplative-axioms.md", "decision": "approved", "content_hash": "sha256_first16"}
```

## Notes

- 憲法は最も影響範囲が広い。慎重に。改正は少量ずつ
- `--constitution-dir` で別のフレームワーク（stoic, utilitarian 等）を使っている場合、そのフレームワークの構造を尊重する
- constitution.py の `MIN_PATTERNS_REQUIRED = 3` と同じ閾値
