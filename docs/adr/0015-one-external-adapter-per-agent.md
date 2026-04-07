# ADR-0015: One External Adapter Per Agent

## Status
accepted

## Date
2026-04-08

## Context
LLM agents in the wild tend to accumulate capabilities in a single process: filesystem access, arbitrary command execution, multiple third-party APIs, and credential material all held by one generative model. "Guardrails" are then layered on top via prompting. This inverts decades of organizational practice around separation of duties, least privilege, and four-eyes approval — principles that exist precisely because concentrating authority in a single actor is known to fail, regardless of that actor's competence.

Contemplative Agent already limits its attack surface by construction (`security by absence`, ADR-0007): the Moltbook adapter is the only outward-facing integration, the HTTP client is domain-locked, and credentials never enter the LLM context. As new adapters are considered (additional SNS platforms, payment rails, external tool integrations), we need an explicit rule preventing capability accretion inside a single agent process.

## Decision
**An agent process owns at most one adapter that performs externally-observable side effects.**

- "Externally-observable side effect" means any action visible outside the agent's own data directory: HTTP writes to third parties, monetary transactions, messages to other humans or systems, file writes outside `MOLTBOOK_HOME`.
- Read-only local utilities (LLM inference, local file reads, meditation simulation) do not count as external adapters.
- When a workflow requires multiple external surfaces (e.g. posting to SNS *and* executing a payment), it must be decomposed into multiple agent processes communicating via a narrow, auditable interface. The proposing agent has no authority to execute on the second surface; a separate agent with its own minimal scope handles that surface and validates the request against fixed rules.
- Agents responsible for authorization/approval of another agent's proposal must not also hold generative responsibility for producing the proposal. Their output space should be constrained (approve / reject / escalate) rather than open-ended generation.

This mirrors職務分掌 (segregation of duties), the four-eyes principle, and the Unix philosophy of one tool per responsibility.

## Alternatives Considered
- **Single agent with layered guardrails (status quo in the broader ecosystem)**: Relies on prompt-level defenses against prompt injection and capability misuse. Fails under adversarial input because the authority to act remains concentrated; guardrails are advisory, not structural.
- **Capability tokens / per-call permission prompts**: Shifts the burden to runtime checks. Useful as defense-in-depth but does not remove the structural problem that a single compromised context can still emit multiple kinds of side effects.
- **No rule, decide per adapter**: Leads to drift. Each individual adapter addition looks reasonable in isolation; the aggregate becomes a fully-privileged agent.

## Consequences
- Adding a new external integration requires either replacing the existing adapter or spawning a separate agent process — never bolting on.
- The Moltbook adapter remains the sole external surface of the current agent. Meditation adapter is experimental and local-only, so it does not violate this rule.
- Future decision-making flows (e.g. any payment/approval scenario) must be designed as multi-agent with权限分離 from day one. The executing agent proposes; a separate authorizer agent with constrained output validates.
- Prompt injection through any single adapter cannot cross into a second external surface, because no such surface exists in the same process.
- This rule is referenced from `README.md` and `CLAUDE.md` as a load-bearing architectural constraint, not just a guideline.
