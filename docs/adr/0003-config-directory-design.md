# ADR-0003: Config Directory Design

## Status

accepted

## Date

2026-03-12

## Context

Prompt templates, behavior rules, and domain configuration were intermixed. The distinction between "task instructions for the LLM" and "agent behavior principles" was ambiguous, making it unclear which files should change when switching domains via `--constitution-dir`.

## Decision

Split `config/` into three role-based directories:

```text
config/prompts/        ← "Do this task" (LLM task instruction templates, 13 files)
config/rules/          ← "Behave this way" (behavior principles & content)
  contemplative/       ←   CCAI axiom preset
  default/             ←   Neutral (no axioms)
config/domain.json     ← Sub-molts, thresholds, keywords
```

- `prompts/` is domain-agnostic (same regardless of rule set)
- `constitution/` switches via `--constitution-dir`
- `domain.json` is platform-specific (Moltbook sub-molt definitions)

## Alternatives Considered

- **Flat config/ directory**: Fine while file count is low, but risks prompts being inadvertently swapped when switching rule sets
- **Place prompts inside rules**: e.g., `rules/contemplative/prompts/`. However, prompts are unrelated to axioms and should be separate

## Consequences

- `--constitution-dir` controls axiom presence/absence without affecting prompts
- `contemplative-axioms.md` resides in `rules/contemplative/`, managed as part of the rule set
- Adding a new rule preset requires only creating a `rules/{preset-name}/` directory
- `CONTEMPLATIVE_CONFIG_DIR` env var allows overriding the entire config/ path (Docker support)
