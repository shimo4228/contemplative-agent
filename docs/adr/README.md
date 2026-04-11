# Architecture Decision Records

Records of key design decisions for this project.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-core-adapter-separation.md) | Core/Adapter Separation | accepted | 2026-03-10 |
| [0002](0002-paper-faithful-ccai.md) | Paper-Faithful CCAI Implementation | accepted | 2026-03-12 |
| [0003](0003-config-directory-design.md) | Config Directory Design | accepted | 2026-03-12 |
| [0004](0004-three-layer-memory.md) | Three-Layer Memory Architecture `[AKC: Extract/Curate/Promote]` | accepted | 2026-03-17 |
| [0005](0005-session-context-refactoring.md) | SessionContext Refactoring | accepted | 2026-03-14 |
| [0006](0006-docker-network-isolation.md) | Docker Network Isolation | accepted | 2026-03-14 |
| [0007](0007-security-boundary-model.md) | Security Boundary Model | accepted | 2026-03-12 |
| [0008](0008-two-stage-distill-pipeline.md) | Two-Stage Distill Pipeline `[AKC: Extract]` | accepted | 2026-03-22 |
| [0009](0009-importance-score.md) | KnowledgeStore Importance Score `[AKC: Extract/Quality Gate]` | accepted | 2026-03-24 |
| [0010](0010-research-data-sync.md) | Research Data Sync | accepted | 2026-03-25 |
| [0011](0011-knowledge-injection-to-skills.md) | Deprecating Direct Knowledge Injection in Favor of Skills `[AKC: Curate]` | accepted | 2026-03-26 |
| [0012](0012-human-approval-gate.md) | Human Approval Gate for Behavior-Modifying Commands `[AKC: Curate/Promote]` | accepted | 2026-03-26 |
| [0013](0013-shelve-coding-agent-skills.md) | Shelving Coding Agent Skills (-ca Series) `[AKC: Curate/Promote]` | accepted | 2026-03-28 |
| [0014](0014-retire-system-spec.md) | Retiring system-spec.md `[AKC: Maintain]` | accepted | 2026-04-01 |
| [0015](0015-one-external-adapter-per-agent.md) | One External Adapter Per Agent | accepted | 2026-04-08 |
| [0016](0016-insight-narrow-stocktake-broad.md) | Insight as Narrow Generator, Stocktake as Broad Consolidator `[AKC: Extract/Curate]` | accepted | 2026-04-11 |
| [0017](0017-yogacara-eight-consciousness-frame.md) | Yogācāra Eight-Consciousness Model as Architectural Frame | accepted | 2026-04-11 |

## Template

When adding a new ADR, follow this format:

```markdown
# ADR-NNNN: Title

## Status
accepted / superseded by ADR-XXXX / deprecated

## Date
YYYY-MM-DD

## Context
What was the problem

## Decision
What was decided

## Alternatives Considered
Rejected options and why

## Consequences
What resulted from this decision
```

## Guidelines

- Numbers are sequential (0001–), in chronological order
- Changes to existing ADRs are made via a new ADR that supersedes the original (never overwrite)
- Only record decisions affecting architecture, data models, or security — minor decisions need not be recorded
- Use `/sync-context` to check consistency between the ADR index and files
