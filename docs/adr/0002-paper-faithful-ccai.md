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

## Review-when

No expiry (worldview ADR: the Appendix C clauses stay verbatim; revisit only if the cited paper's own Appendix C text changes).

## Alternatives Considered

- **Revise and maintain custom interpretations**: Rewrite to align with the paper's intent. However, judging "correct interpretation" is itself subjective and risks introducing bias
- **Use Appendix D Condition 7**: Use the paper's experimental condition 7 prompt verbatim. Retained in the contemplative-agent-rules repository for benchmarking, but Appendix C is better structured per axiom and easier to manage

## Consequences

- Implementation is now defensible when presented to the paper's author team (Laukkonen)
- Axiom additions/modifications simply track paper updates
- Baseline comparisons achievable by switching between contemplative/default via `--constitution-dir`
- 3-way benchmark (baseline, custom, paper_faithful) already conducted in the contemplative-agent-rules repository

> **Note (2026-10-24, deployed form differs from the paper's intervention)**:
> the decision above copies the paper's Appendix C clauses verbatim, but the
> production deployment does not apply them the way the paper's headline
> result does. `_identity_axioms_base` (`core/llm/prompting.py`) only
> concatenates the clauses after the identity text in the system prompt. The
> paper's d>7 result comes from a contemplative pause *before responding*
> (Appendix D, condition 7), kept in the rules repository as the
> `paper_faithful` benchmark variant. So the paper's effect size is not a
> property of this deployment, and the deployed constitution is read on its
> own instruments ([research-questions evidence](../evidence/research-questions.md),
> Q1 limit row iii). No decision above changes.
>
> The interpretive key of the rules repository ([its ADR-0005](https://github.com/shimo4228/contemplative-agent-rules/blob/main/docs/adr/0005-interpretive-key-for-frontier-injection-defense.md), the
> `operator-keyed` variant) is not applied here either. The key serves the
> frontier chat surface, where the verbatim clauses were flagged as prompt
> injection; this deployment injects them into its own system prompt on local
> gemma, where that flag does not arise, and the template copy
> (`config/templates/contemplative/constitution/contemplative-axioms.md`) is
> byte-identical to the rules repository's verbatim text. The key and the
> amended constitution move the referent of "constitutional directives" in
> opposite directions: the key narrows it to the model's task-level working
> conclusions, while the third amendment (2026-08-09, data repository
> `constitution/contemplative-axioms.md` lines 5, 10, 18) widens it to the
> agent's own computational structure ("memory artifacts, defined
> boundaries", "the division between selfhood and system mechanism", "memory
> ceiling, or functional boundary"). That widening is an object of
> observation (paragraph added 2026-10-31).
