# Coding Agent Integrations

Maintenance skills for the Contemplative Agent's behavioral artifacts (`skills/`, `rules/`, `identity.md`, `constitution/`). These replace the 9B multi-stage pipeline with holistic judgment from Opus-class coding agents.

## Skills

| Skill | AKC Phase | Input | Output |
|-------|-----------|-------|--------|
| `insight-ca` | Extract/Curate | knowledge.json (uncategorized) | skills/*.md |
| `skill-stocktake-ca` | Curate | skills/*.md + rules/*.md | Audit report + actions |
| `rules-distill-ca` | Promote | skills/*.md + rules/*.md | rules/*.md |
| `amend-constitution-ca` | Promote | knowledge.json (constitutional) + constitution/*.md | constitution/*.md |
| `distill-identity-ca` | Promote | knowledge.json + identity.md | identity.md |

The canonical skill definitions live in `integrations/skills/`. Install scripts adapt them for each coding agent.

## Security

These skills read only `knowledge.json` (sanitized by the 9B distill pipeline). **They must never read raw episode logs** (`logs/*.jsonl`) -- this is an untrusted prompt injection surface ([ADR-0007](../docs/adr/0007-security-boundary-model.md)).

## Prerequisite

Run `contemplative-agent distill` first to populate `knowledge.json` from episode logs. This step uses the local 9B model and cannot be delegated to a coding agent.

## Typical Workflow

```
1. contemplative-agent distill --days 7    # 9B model: episodes -> knowledge.json
2. /insight-ca                              # Coding agent: knowledge -> skills
3. /skill-stocktake-ca                      # Coding agent: audit quality
4. /rules-distill-ca                        # Coding agent: skills -> rules
5. /distill-identity-ca                     # Coding agent: knowledge -> identity
6. /amend-constitution-ca                   # Coding agent: constitutional patterns -> constitution
```

Steps 2-6 all require human approval before writing.

## Install

### Claude Code

```bash
bash integrations/claude-code/install.sh
```

Copies skill files to `.claude/skills/`. Available as slash commands: `/insight-ca`, `/skill-stocktake-ca`, etc.

### Cursor

```bash
bash integrations/cursor/install.sh
```

Converts skill files to `.cursor/rules/*.mdc` format. Rules are available as context when referenced by the agent. Use `@rules` or mention the skill name in conversation to activate.

### OpenAI Codex

```bash
bash integrations/codex/install.sh
```

Appends skill definitions to `AGENTS.md`. The Codex CLI reads this file automatically for project-level instructions.

## The `-ca` Suffix

`ca` = Contemplative Agent. The suffix distinguishes these skills from the coding agent's own maintenance skills with the same base names (e.g., Claude Code's `learn-eval` vs this project's `insight-ca`).
