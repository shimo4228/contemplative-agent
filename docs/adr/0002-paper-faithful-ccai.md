# ADR-0002: Paper-Faithful CCAI Implementation

## Status

accepted

## Date

2026-03-12

## Context

At project inception, the four Contemplative AI axioms (Emptiness, Non-Duality, Mindfulness, Boundless Care) had been expanded into five custom-interpreted files (e.g., boundless-care.md). Cross-referencing with Laukkonen et al. (2025) "Contemplative AI" arXiv:2504.15125 revealed that the custom interpretations diverged from the paper's intent in several places.

## Decision

Delete all five custom interpretation files and include the constitutional clauses from the paper's Appendix C **verbatim** in `config/rules/contemplative/contemplative-axioms.md`.

- Managed via `load_constitution()` from `config/constitution/`
- Injected via `configure(axiom_prompt=...)` → `_load_identity()` into the system prompt
- Axiom-free operation available via `--no-axioms` / `--constitution-dir` (supports A/B testing)

## Alternatives Considered

- **Revise and maintain custom interpretations**: Rewrite to align with the paper's intent. However, judging "correct interpretation" is itself subjective and risks introducing bias
- **Use Appendix D Condition 7**: Use the paper's experimental condition 7 prompt verbatim. Retained in the contemplative-agent-rules repository for benchmarking, but Appendix C is better structured per axiom and easier to manage

## Consequences

- Implementation is now defensible when presented to the paper's author team (Laukkonen)
- Axiom additions/modifications simply track paper updates
- Baseline comparisons achievable by switching between contemplative/default via `--constitution-dir`
- 3-way benchmark (baseline, custom, paper_faithful) already conducted in the contemplative-agent-rules repository
