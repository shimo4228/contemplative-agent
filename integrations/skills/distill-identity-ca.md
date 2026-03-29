---
name: distill-identity-ca
description: "Contemplative Agent の knowledge.json + identity.md から更新版アイデンティティを起草し、MOLTBOOK_HOME/identity.md を更新する"
user-invocable: true
origin: original
---

# /distill-identity-ca — Knowledge → Identity (Contemplative Agent)

AKC Promote フェーズ。knowledge.json の全パターンと現行 identity.md を読み、経験を反映した更新版を起草する。
Opus クラスのホリスティック判断で 9B 2段パイプライン（distill.py distill-identity）を代替。

> **セキュリティ**: knowledge.json, identity.md, rules/ のみ読む。`logs/*.jsonl` は絶対に Read しない（ADR-0007）。

## When to Use

- knowledge.json にパターンが十分蓄積され、エージェントの自己理解を更新したいとき
- `/insight-ca` や `/rules-distill-ca` の後、行動変更がアイデンティティに反映されていないとき
- identity.md が空（初期状態）で、経験に基づく人格定義を生成したいとき

## Process

### 1. 入力収集

1. `MOLTBOOK_HOME/knowledge.json` を Read（全カテゴリ）
   - パターンが 0件なら終了
2. `MOLTBOOK_HOME/identity.md` を Read（現行アイデンティティ。なければ空）
3. `MOLTBOOK_HOME/rules/*.md` を全件 Read（ルールコンテキスト — 価値観の接地用）
4. `MOLTBOOK_HOME/constitution/*.md` を全件 Read（倫理フレームワーク参照）

### 2. アイデンティティ起草（ホリスティック判断）

全入力を俯瞰し、更新版 identity.md を起草:

- **経験ベース**: knowledge パターンが示す実際の行動傾向・学びを反映
- **一貫性**: 現行 identity の核となる特徴を保持しつつ進化させる
- **簡潔性**: ~4000 tokens 以内（システムプロンプトの基盤として毎セッション全文ロードされる）
- **ルール整合**: rules/ の行動原則と矛盾しないこと
- **憲法整合**: constitution/ の倫理フレームワークと一致すること

### 3. 品質ゲート

起草結果を以下の観点で自己評価:

- [ ] ~4000 tokens 以内に収まっているか
- [ ] 現行 identity の核が保持されているか（全面書き換えでないか）
- [ ] knowledge パターンの具体的な経験に裏付けられているか
- [ ] rules/ や constitution/ と矛盾していないか
- [ ] forbidden pattern（API key, password 等）が含まれていないか
- [ ] SNS プロフィールとして自然に読めるか

### 4. 承認ゲート

更新案をユーザーに提示:

```
# Identity Update Proposal

## Key Changes
[現行からの主な変更点]

## Rationale
[各変更の根拠となる knowledge パターン]

## Full Text
[更新後の全文]
```

承認後のみ Write to `MOLTBOOK_HOME/identity.md`。

### 5. 監査ログ

承認/拒否を `MOLTBOOK_HOME/logs/audit.jsonl` に追記:

```json
{"timestamp": "ISO8601", "command": "distill-identity-ca", "path": "identity.md", "decision": "approved", "content_hash": "sha256_first16"}
```

## Notes

- identity.md はシステムプロンプトの基盤。変更の影響範囲は constitution に次いで広い
- distill.py の2段パイプライン（extract → refine）を Opus は1パスで実行できる
- 初回（identity.md が空）は「生成」、2回目以降は「更新」。更新時は差分を最小に
