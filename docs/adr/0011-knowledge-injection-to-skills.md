# ADR-0011: Deprecating Direct Knowledge Injection — Migration to Skills

## Status

accepted

## Date

2026-03-26

## Context

Currently, `get_context_string(limit=50)` injects 50 KnowledgeStore patterns as a bullet list directly into the prompt (in two places: `generate_cooperation_post` and `generate_reply`).

Problems:

1. **Black box**: It is impossible to trace which of the 50 patterns the LLM reflected and how
2. **No human in the loop**: Agent behavior changes without human review
3. **No noise resistance**: Low-quality patterns (e.g., duplicates of "avoid Test Title") influence behavior
4. **AKC contradiction**: Bypasses the AKC Curate/Promote phases (human oversight)
5. **Token cost**: 50 patterns × 100–200 tokens = 5,000–10,000 tokens added indiscriminately to the prompt

Meanwhile, the existing `insight` command extracts skills/*.md from knowledge and injects them into the LLM system prompt. Skills are:

- Human-readable Markdown
- Previewable via `--dry-run`
- Directly editable
- Diff-trackable via git

## Decision

Gradually deprecate direct knowledge pattern injection into prompts. Behavioral influence must flow exclusively through skills.

```
Deprecated:  knowledge → direct prompt injection → LLM implicitly reflects
Adopted:     knowledge → insight → skills/*.md → injected into system prompt
```

Knowledge is retained as an intermediate artifact of the distillation pipeline but no longer directly influences behavior during sessions.

### Migration Plan

1. Maintain knowledge injection until skills are sufficiently accumulated
2. Increase insight execution frequency and verify skills coverage
3. After confirming behavior is covered by skills, deprecate knowledge injection
4. `get_context_string()` will only be used as input for distill-identity

### Influence Path Clarification

| Path | Input | Output | Human Review |
|------|-------|--------|-------------|
| Ethical judgment | constitutional knowledge | Reflected in constitution | At constitution edit time |
| Behavior patterns | uncategorized knowledge | insight → skills/*.md | At insight execution (manual) |
| Personality | all knowledge | distill-identity → identity.md | At distill-identity execution (manual) |

## Alternatives Considered

1. **Improve and retain knowledge injection**: Use Phase 3 selective loading (category filter) to improve injection quality. → Rejected: Does not solve the human-in-the-loop problem. Even with better quality, "what changed behavior" remains untrackable

2. **Use both knowledge and skills**: Inject both into the prompt. → Rejected: Double injection only increases token cost and noise. Influence paths remain ambiguous

3. **Immediate deprecation**: Remove knowledge injection now. → Rejected: At this stage with insufficient skills coverage, behavior quality would degrade. Gradual migration is safer

## Consequences

**Positive outcomes**:

- All agent behavior changes pass through human review (human in the loop)
- Changes are trackable (verify skills changes via git diff)
- Fully aligned with AKC design philosophy
- Reduced prompt token consumption
- Consistent with the README's "with minimal, purposeful human oversight"

**Requires attention**:

- Insight execution frequency needs to increase (currently manual only)
- Continuous verification that skills coverage is sufficient
- Knowledge → skills conversion accuracy (insight quality) may become a bottleneck for behavior quality

## Relationship to the Three-Layer Oversight Structure

This ADR completes the agent's three-layer oversight structure:

| Layer | Role | Capabilities |
|-------|------|-------------|
| **contemplative-agent** | Autonomous activity, episode accumulation | run, distill (automatic). Cannot self-modify |
| **Orchestrator (e.g., Claude Code)** | Translates human intent into CLI commands | insight, rules-distill, distill-identity |
| **Human** | Communicates intent, reviews results | dry-run review, skills editing, git diff |

By deprecating direct knowledge injection, all behavior changes flow through skills — all through artifacts reviewed by humans. Since the agent itself has no self-modification capability, rewriting behavior via prompt injection becomes structurally impossible.

The orchestrator is not limited to Claude Code. Anything that can invoke the CLI suffices (Minimal Dependency principle).
