# ADR-0005: SessionContext Refactoring

## Status

accepted

## Date

2026-03-14

## Context

Even after the Core/Adapter separation (ADR-0001), agent.py remained at 570 lines. Shared session state (memory, commented_posts, own_post_ids, actions_taken, rate_limited) was scattered across Agent class instance variables. ReplyHandler, PostPipeline, and FeedManager referenced Agent directly, creating incipient circular dependencies.

## Decision

Introduce a `SessionContext` dataclass to define shared mutable state as an explicit contract:

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

- Collaborators (ReplyHandler, PostPipeline, FeedManager) depend only on `SessionContext` + `Callable`
- They do not import Agent
- Agent retains backward-compatible property accessors via delegation (`_actions_taken` → `_ctx.actions_taken`)

## Alternatives Considered

- **Expose methods on Agent for collaborators to call**: Simple, but locks in the dependency on Agent and requires mocking the entire Agent in tests
- **Event bus**: Communicate state changes via events. Overkill for this project's scale

## Consequences

- Collaborator unit tests can be written without Agent (just mock SessionContext)
- All shared state is visible by inspecting SessionContext (no more hidden state)
- Agent's property accessors are technical debt, but can be incrementally removed
