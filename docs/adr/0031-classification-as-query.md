# ADR-0031: Classification as Query — Substrate Principle for Self-Improving Memory

## Status

accepted — post-hoc articulation of a principle already realised in ADR-0019, ADR-0022, and ADR-0026.

This is a **worldview ADR** in the sense defined by `docs/adr/README.md`: it does not solve a new problem, it names the substrate condition under which the project's other memory ADRs become formulable.

## Date

2026-04-27

## Context

Self-improving agents revise their own classification axes over time. If categories are stored as state at write time, every axis revision requires data migration whose cost grows with corpus size. An agent that cannot cheaply re-classify its own past stops being a learning agent at the point where re-classification becomes expensive — typically right when it has accumulated enough history to learn something interesting from re-classifying it.

## Decision

Categories are computed at **read time** by projecting records against editable semantic seeds, not stored as **state** at write time.

Each "view" is a small editable artifact (a centroid embedding plus a name and prompt). Classification of any pattern under any view is computed at query time as a similarity score between the pattern's embedding and the view's centroid. The pattern itself carries no category field, no tag list, no namespace — only its content and its embedding.

This treats classification as a **query operation** rather than a **state field**.

## Implications

Revising an axis becomes O(seed-edit), not O(corpus-size). When the Curate phase (`distill`, `insight`, `rules-distill`, `amend-constitution`, `skill-reflect`) revises a classification axis, no historical data is lost or rewritten — the history layer (`episodes.sqlite`, immutable JSONL) and the pattern layer (`knowledge.json`) stay untouched while the projection over them shifts.

**Consumption note (clarified 2026-07-11).** The Curate list above does not mean every Curate command queries views. Only two do: `distill-identity` (`self_reflection`) and `amend-constitution` (`constitutional`). `insight` and `rules-distill` deliberately use unsupervised embedding clustering instead. The decision rule: a **view** is the right projection when the semantic axis is known in advance ("which patterns speak to X?"); **clustering** is the right projection when the point is to discover structure the operator has not named — imposing a seed there would bias the discovery toward pre-named axes. Both mechanisms obey this ADR equally: categories remain query-time computations either way; they differ only in whether the query axis is predefined (seed) or emergent (cluster).

## Reference Implementations

- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — initial migration from a discrete `category` field to view-based projection
- ~~[ADR-0022](0022-memory-evolution-and-hybrid-retrieval.md) — extension with cosine + BM25 hybrid scoring and memory evolution~~ (withdrawn by ADR-0034)
- [ADR-0026](0026-retire-discrete-categories.md) — Phase-3 completion, removal of the legacy `category` field

## Closest Prior Art

A-MEM (Xu et al., 2025, [arXiv:2502.12110](https://arxiv.org/abs/2502.12110)) — same attractor reached independently. Multiple research groups converging on the same mechanism around the same time is itself evidence that the design space is settling there.

## References

- [ADR-0017](0017-yogacara-eight-consciousness-frame.md) — worldview frame within which the projection / state distinction becomes legible
- ADR-0019, ADR-0022, ADR-0026 — reference implementations
