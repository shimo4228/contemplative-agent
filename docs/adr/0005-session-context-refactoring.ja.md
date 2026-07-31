# ADR-0005: SessionContext リファクタリング

## Status

accepted

## Date

2026-03-14

## Context

ADR-0001 の Core/Adapter 分離後も agent.py が 570行あり、セッション中の共有状態（memory, commented_posts, own_post_ids, actions_taken, rate_limited）が Agent クラスのインスタンス変数に散在。ReplyHandler, PostPipeline, FeedManager が Agent を直接参照しており、循環的な依存が生まれかけていた。

## Decision

`SessionContext` dataclass を導入し、共有可変状態を明示的なコントラクトとして定義:

```python
@dataclass
class SessionContext:
    memory: MemoryStore
    commented_posts: set[str]
    own_post_ids: set[str]
    own_agent_id: str | None
    actions_taken: dict[str, int]
    rate_limited: bool
```

- 協力者（ReplyHandler, PostPipeline, FeedManager）は `SessionContext` + `Callable` のみに依存
- Agent を import しない
- Agent にはプロパティ経由の後方互換アクセサを残存（`_actions_taken` → `_ctx.actions_taken`）

## Alternatives Considered

- **Agent にメソッドを公開して協力者から呼ぶ**: 簡単だが Agent への依存が固定され、テスト時に Agent 全体のモックが必要
- **イベントバス**: 状態変更をイベントで通知。このプロジェクトの規模では過剰

## Consequences

- 協力者のユニットテストが Agent なしで書ける（SessionContext をモックするだけ）
- 共有状態の一覧が SessionContext を見れば分かる（暗黙の状態がなくなった）
- Agent のプロパティアクセサは技術的負債だが、段階的に除去可能
