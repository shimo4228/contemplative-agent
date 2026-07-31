# ADR-0001: Core/Adapter Separation

## Status

accepted

## Date

2026-03-10

## Context

agent.py had grown into a 780-line God Module where platform-specific logic (Moltbook API calls, authentication, content generation) was intertwined with platform-agnostic logic (LLM, memory, scheduler). This made testing difficult and future multi-platform support impossible.

## Decision

Separate into `core/` and `adapters/`. **Dependency direction is one-way: adapters → core only.**

- `core/`: LLM, memory (3 layers), distillation, scheduler, config constants. Parameterized (receives configuration via constructor arguments)
- `adapters/moltbook/`: HTTP client, authentication, content, feed management, post pipeline
- `cli.py`: The sole composition root (imports both core/ and adapters/)

Collaborators (ReplyHandler, PostPipeline, FeedManager) do not import Agent. Dependencies are injected via SessionContext + Callable.

## Alternatives Considered

- **Hexagonal Architecture (Ports & Adapters)**: Define explicit interfaces via Protocols. Excessive at this stage with only a single adapter (Moltbook). Will reconsider if more adapters are added
- **Responsibility separation within module only**: Just splitting files without enforcing dependency direction. Import violations would go undetected

## Consequences

- agent.py reduced from 780 → 570 lines (focused on session management)
- core/ modules can be tested without adapters
- Adding a new platform adapter simply requires creating `adapters/{platform}/` and wiring it in cli.py
- Security constants consolidated in core/config.py, eliminating duplicate definitions
