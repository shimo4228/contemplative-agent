# ADR-0003: Config ディレクトリ設計

## Status

accepted

## Date

2026-03-12

## Context

プロンプトテンプレート、行動ルール、ドメイン設定が混在していた。「LLMへのタスク指示」と「エージェントの行動原則」の区別が曖昧で、`--constitution-dir` でドメイン切替する際にどのファイルが切り替わるべきか不明確だった。

## Decision

`config/` を役割で3分割:

```
config/prompts/        ← 「このタスクをやれ」(LLM タスク指示テンプレート、13個)
config/rules/          ← 「こう振る舞え」(行動原則・コンテンツ)
  contemplative/       ←   CCAI 公理プリセット
  default/             ←   ニュートラル（公理なし）
config/domain.json     ← サブモルト・閾値・キーワード
```

- `prompts/` はドメイン非依存（どのルールセットでも同じ）
- `constitution/` は `--constitution-dir` で切替
- `domain.json` はプラットフォーム固有（Moltbook のサブモルト定義）

## Alternatives Considered

- **フラットに config/ 直下**: ファイル数が少ない間は問題ないが、ルール切替時に prompts まで切り替わるリスク
- **prompts を rules 内に配置**: `rules/contemplative/prompts/` のように。しかし prompts は公理と無関係なので分離すべき

## Consequences

- `--constitution-dir` 切替で公理の有無を制御可能。prompts は影響を受けない
- `contemplative-axioms.md` が `rules/contemplative/` 内にあるため、公理はルールセットの一部として管理
- 新しいルールプリセット追加は `rules/{preset-name}/` ディレクトリを作るだけ
- `CONTEMPLATIVE_CONFIG_DIR` env var で config/ パス全体をオーバーライド可能（Docker 対応）
