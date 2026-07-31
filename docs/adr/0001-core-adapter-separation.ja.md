# ADR-0001: Core/Adapter 分離

## Status

accepted

## Date

2026-03-10

## Context

agent.py が 780行の God Module になっており、プラットフォーム固有ロジック（Moltbook API呼び出し、認証、コンテンツ生成）とプラットフォーム非依存ロジック（LLM、メモリ、スケジューラ）が混在していた。テストが困難で、将来の別プラットフォーム対応も不可能だった。

## Decision

`core/` と `adapters/` に分離。**依存方向は adapters → core の一方向のみ**。

- `core/`: LLM、メモリ（3層）、蒸留、スケジューラ、設定定数。パラメータ化（コンストラクタ引数で設定を受け取る）
- `adapters/moltbook/`: HTTP クライアント、認証、コンテンツ、フィード管理、投稿パイプライン
- `cli.py`: 唯一の composition root（core/ と adapters/ の両方を import）

協力者（ReplyHandler, PostPipeline, FeedManager）は Agent を import しない。SessionContext + Callable で依存注入。

## Alternatives Considered

- **Hexagonal Architecture（Ports & Adapters）**: Protocol を定義してインターフェースを明示する案。現時点ではアダプタが Moltbook のみなので過剰。アダプタが増えたら再検討
- **モジュール内での責務分割のみ**: ファイル分割だけで依存方向を規約にしない案。import ミスが検出できない

## Consequences

- agent.py は 780行 → 570行に削減（セッション管理に特化）
- core/ モジュールはテスト時にアダプタなしでテスト可能
- 新しいプラットフォームアダプタを追加する際は `adapters/{platform}/` を作り、cli.py で接続するだけ
- core/config.py にセキュリティ定数を集約したことで、定数の二重定義がなくなった
