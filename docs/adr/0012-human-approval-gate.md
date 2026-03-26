# ADR-0012: 行動変更コマンドの人間承認ゲート

## Status
accepted

## Date
2026-03-26

## Context

オフラインコマンド（insight, rules-distill, distill-identity, amend-constitution）は skills, rules, identity, constitution を書き換え、エージェントの行動に直接影響する。これまでは `--dry-run` で事前確認し、別途本番実行するフローだったが、2つの問題があった:

1. **確率生成の非再現性**: `--dry-run` で見た LLM 出力と本番実行の出力は同一にならない。「プレビュー」として機能しない
2. **承認の非強制**: `--dry-run` を省略して直接実行できるため、Human in the loop が構造的に保証されない

## Decision

行動に直接影響するコマンドに承認ゲートを導入する。生成結果を表示した後、書き込み前に人間の承認を求める。`--auto` フラグは提供しない（AKC の Human in the loop 原則）。

| コマンド | 承認ゲート | `--dry-run` | 理由 |
|---------|-----------|-------------|------|
| **distill** | なし | 残す | 中間成果物（knowledge）への書き込み。行動に直接影響しない |
| **insight** | あり | 廃止 | skills を書き換え。承認しなければ dry-run と同等 |
| **rules-distill** | あり | 廃止 | rules を書き換え |
| **distill-identity** | あり | 廃止 | identity を書き換え |
| **amend-constitution** | あり | 廃止 | constitution を書き換え。最も影響が大きい |

### フロー

```
CLI 実行
  → LLM 生成
  → 結果を stdout に表示
  → "Write to {path}? [y/N]"
  → y: 書き込み / N: 破棄
```

### distill が承認不要な理由

distill は knowledge（中間成果物）にのみ書き込む。ADR-0011 で knowledge 直接注入を廃止したため、knowledge はエージェントの行動に直接影響しない。行動への反映は insight → skills を経由し、そこに承認ゲートがある。

### `--auto` を提供しない理由

AKC（Agent Knowledge Cycle）は人間の監督を前提とした自己改善ループ。行動変更の自動実行を許可すると、エージェントの行動変化が人間の確認なしに起きる経路が生まれる。これは設計思想に反する。

## Alternatives Considered

1. **`--auto` フラグで確認スキップ**: Claude Code がオーケストレーターとして自動実行する場合に必要 → 却下。Claude Code は結果を読んで判断し、承認できる。自動スキップは不要
2. **`--dry-run` を残して承認ゲートも追加**: 2つの確認手段が重複 → 却下。承認しなければ dry-run と同じ結果が得られる。distill だけ `--dry-run` を残す（承認ゲートがないため）
3. **全コマンドに承認ゲート（distill 含む）**: → 却下。distill は launchd で定期自動実行される。中間成果物への書き込みに毎回承認を求めると運用が成り立たない

## Consequences

**良い結果**:
- Human in the loop が構造的に強制される（`--auto` がないため回避不可能）
- 確率生成の非再現性問題が解消（実際の生成結果に対して承認する）
- `--dry-run` の意味が明確化（distill 専用のシミュレーションモード）

**注意が必要**:
- CLI の対話的プロンプトは CI/CD パイプラインでは使えない（そもそも行動変更コマンドを CI で自動実行すべきでない）
- Claude Code がオーケストレーターの場合、承認フローの実装方法を検討する必要がある（stdout の結果を読んで再実行か、別のインターフェースか）
