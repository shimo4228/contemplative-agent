# ADR-0014: Retiring system-spec.md

## Status

accepted

## Date

2026-04-01

## Context

`docs/spec/system-spec.md` was created (2026-03-26, 325 lines) as a formal specification targeting external researchers and AI agents. It described architecture, memory system, agent behavior, security model, configuration, prior art, and AKC mapping — seven sections covering "how it works."

In practice, six of those seven sections duplicated content already maintained elsewhere:

| Spec Section | Duplicated In |
|---|---|
| §1 Architecture | README Architecture + CODEMAPS/architecture.md |
| §2 Memory System | CODEMAPS/architecture.md + core-modules.md |
| §3 Agent Behavior | CODEMAPS/moltbook-agent.md |
| §4 Security Model | README Security Model + CLAUDE.md |
| §5 Configuration | README Configuration |
| §7 AKC Mapping | CODEMAPS/architecture.md |

Only §6 (Prior Art Mapping — memory system comparison table, cognitive architecture mapping, and paper references) had no equivalent elsewhere.

The document was already drifting: README reported 801 tests while spec still stated 794. The `context-sync` skill had already dropped spec updates from its scope because the synchronization cost outweighed the value.

### Why a spec seemed necessary

The original motivation was to provide a single, comprehensive document for external researchers. README was too shallow, CODEMAPS was too code-focused, and ADRs were too fragmented.

### Why it became debt

1. **Duplication maintenance**: Every architecture or security change required updates to 3+ documents
2. **AI can read code directly**: The spec's primary AI audience (Claude Code) already reads CODEMAPS, CLAUDE.md, and source code. A prose restatement adds no information
3. **Researchers follow README → CODEMAPS**: The two-step path is sufficient. A third layer adds navigation confusion, not clarity
4. **Sync failures compound silently**: Stale specs are worse than no specs — they mislead

## Decision

Delete `docs/spec/system-spec.md` and the `docs/spec/` directory.

Move the unique content (§6 Prior Art) to `docs/CODEMAPS/architecture.md` as a new "Prior Art" section, adjacent to the Memory Architecture section it contextualizes.

The documentation structure becomes three roles:

| Document | Role |
|---|---|
| **README** | What/Why (external-facing) |
| **CODEMAPS** | How/Where (code reference + prior art) |
| **ADR** | Why this way (design decisions) |

## Alternatives Considered

1. **Keep spec, deduplicate by making other docs reference it** — Rejected. This inverts the natural reading order (README → CODEMAPS) and makes the spec a single point of failure
2. **Convert spec to a lightweight "system overview" page** — Rejected. README already serves this role. A lightweight spec is just a redundant README
3. **Keep spec for Zenodo/arxiv supplementary material** — Rejected. README + CODEMAPS can be bundled if needed. No reason to maintain a separate living document for an occasional export

## Consequences

- One fewer document to synchronize on architecture/security/memory changes
- Prior art comparison is now discoverable from CODEMAPS (where developers already look) rather than buried in a spec directory
- Future "we should write a spec" proposals should reference this ADR
