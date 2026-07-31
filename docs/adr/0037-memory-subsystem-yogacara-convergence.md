# ADR-0037: Memory Subsystem Converges to the Yogācāra Frame; Paper-Borrowed Mechanisms Retired

## Status

accepted

## Date

2026-05-05

## Context

ADR-0017 (2026-04-11) named the Yogācāra eight-consciousness model as the architectural frame for Contemplative Agent. Five days later, on 2026-04-16, ADR-0017 added an "Observed Convergence — 2026-04-16" subsection noting that ADR-0019 (embedding views), ADR-0021 (provenance / bitemporal / forgetting / feedback), and ADR-0022 (memory evolution + BM25 hybrid retrieval) had each landed in a configuration the eight-consciousness model predicts, despite none citing ADR-0017 as rationale. That note recorded the *positive* convergence at land time.

In the three weeks since, the picture has changed in a specific way: every paper-borrowed mechanism in the memory subsystem has retired, while every Yogācāra-derived implementation has remained. ADR-0037 records that retirement-confirmed pattern and converts it into two forward-looking defaults for future memory-subsystem extensions.

### Retirement series (2026-04-18 → 2026-05-05)

| Date | ADR | What retired | Source paper(s) |
|---|---|---|---|
| 2026-04-18 | ADR-0028 | Pattern-level forgetting + feedback (memory dynamics moved to skill layer) | MemoryBank Ebbinghaus (arXiv:2305.10250) |
| 2026-04-18 | ADR-0029 | Dormant provenance elements (`user_input` / `external_post` / `sanitized`) | (internal) |
| 2026-05-05 | ADR-0034 | Memory evolution + BM25 hybrid retrieval | A-Mem (arXiv:2502.12110) / Zep / Graphiti / Cognee / Mem0 |
| 2026-05-05 | ADR-0036 | Skill-as-memory loop (router, usage log, reflect) | Memento-Skills (arXiv:2603.18743) |

### What remains

Yogācāra-derived (memory architecture proper):

- **ADR-0017** — worldview frame, eight-consciousness model
- **ADR-0019** — embedding + views (相分 / 見分 split materialized in code)
- **ADR-0026** — Phase-3 completion of ADR-0019 (discrete categories fully retired)
- **ADR-0027** — noise as seed (gated episodes preserved as unripe bīja, not discarded)
- **ADR-0031** — classification as query (substrate principle for self-improving memory)

Security adapter (not memory architecture):

- **ADR-0021 residue** — MINJA-defense mechanisms: `trust_score`, `source_type=external_reply` down-weighting, `TRUST_FLOOR`. These survive ADR-0028's retirement because they belong to the security boundary (ADR-0007), not to the memory architecture. The MINJA paper is the only paper reference that survives in any form, and it survives in the security column, not the memory column.

The pattern is uniform across four retirement decisions over three weeks: every mechanism imported from outside the project's worldview retired; every mechanism derived from Yogācāra remained.

### Why this needs its own ADR

ADR-0017's "Observed Convergence — 2026-04-16" subsection records the positive convergence at land time. It cannot record the retirement-confirmed convergence three weeks later because the retirement data did not exist yet. Each retirement ADR (0028 / 0029 / 0034 / 0036) records its own local rationale — low-quality LLM revisions, near-zero lexical overlap, never-wired router matches, memory dynamics misplaced in the substrate layer — but none of them names the cross-cutting pattern. The retirements look independent in their own ADRs and connected only when read side by side.

ADR-0037 names the connection so that future memory-subsystem extensions have a precedent to invoke without having to re-discover the pattern by reading four ADRs in parallel.

## Decision

Two layered defaults for future memory-subsystem extensions. Scope is memory architecture only (`knowledge.json` / pattern / view / distill / forgetting / retrieval). Constitution, skill layer, and agent stance are out of scope.

### 1. Worldview-first as default

When proposing a new memory-subsystem mechanism, derive it from the Yogācāra frame (ADR-0017) before reaching for a paper-borrowed mechanism. If a paper mechanism is the natural choice, run a worldview-integrity check first: which consciousness layer does this mechanism touch (前五識 / 第六識 / 末那識 / 阿頼耶識), and does its operation align with that layer's transformation target (轉依), or does it duplicate / overlap / fight an existing layer?

This is a default, not a rule. The Emptiness axiom (ADR-0002) prohibits treating any directive as a fixed truth, including this one. New evidence — a paper mechanism with empirical evidence on this code base, a Yogācāra-shaped mechanism that fails in production — overrides the default.

### 2. Cognitive-bandwidth safeguard

When research volume in a single ADR exceeds the operator's cognitive bandwidth — multiple unfamiliar papers cited as motivation, multiple mechanisms proposed in one Context section, multiple parallel implementation paths — surface that fact and run the worldview-integrity check *before* implementation, not after.

This safeguard has external alignment. AKC's [ADR-0010 — Human Cognitive Resource as Central Constraint](https://github.com/shimo4228/agent-knowledge-cycle/blob/main/docs/adr/0010-human-cognitive-resource-as-central-constraint.md) (2026-04-18, v1.8.0) names "human cognitive resource is the bottleneck" as a central design constraint and reshapes the Research phase as signal-first. ADR-0010 was authored two days after the dense ADR-0021 / 0022 / 0023 implementation cluster in this project; the timing was not made explicit at the time but is recorded here.

## Alternatives Considered

- **Add this observation to ADR-0017's "Observed Convergence" subsection.** Rejected. ADR-0017 is a worldview ADR (per `docs/adr/README.md` taxonomy) and its convergence observation was authored at land time. The retirement-confirmed pattern requires three weeks of subsequent data and crosses four problem-solving ADRs. Layering that into a worldview ADR collapses the worldview / problem-solving distinction the README is explicit about.
- **Leave the observation to project memory (the existing `yogacara-convergence` note).** Rejected. The memory note exists but cannot be invoked as precedent in a future ADR's *Alternatives Considered*. Precedent invocation requires a pointer that survives the memory store's lifecycle and is visible to future contributors who do not share the operator's memory.
- **Broaden scope to worldview-driven design in general.** Rejected. The retirement evidence is memory-subsystem-specific. Broadening dilutes the precedent and overlaps with ADR-0017's worldview-frame role.
- **Make Decision #1 a hard rule (not a default).** Rejected. Hardening conflicts with the Emptiness axiom and risks reproducing the same failure mode at a higher abstraction level — "Yogācāra dogma" replacing "paper borrowing" as the new fixed truth. Default + integrity check + override-on-evidence is the correct balance.

## Consequences

**Positive**:

- Future memory-subsystem extensions have a four-data-point precedent (0028 / 0029 / 0034 / 0036) for the cost of paper borrowing without a worldview-integrity check.
- The cognitive-bandwidth safeguard aligns with AKC's signal-first Research stance, giving cross-project consistency between Contemplative Agent and AKC.
- The memory-subsystem design space contracts: the Yogācāra frame predicts admissible solutions, reducing exploration cost for future work.
- ADR-0037 gives the four retirement ADRs (0028 / 0029 / 0034 / 0036) a unified meta-context they did not previously have. Reading any one of them, a future contributor now reaches ADR-0037 and sees the pattern.

**Negative**:

- Risk of "Yogācāra dogma" — the worldview frame becoming a fixed truth that ossifies design judgment. Mitigation: this ADR is itself subject to the Emptiness axiom and can be revised by a future ADR with empirical counter-evidence.
- Future paper-borrow proposals may be dismissed too quickly under the precedent. Mitigation: the worldview-integrity check is a *gate*, not a rejection. A paper mechanism that passes the check is admissible.
- The "two-day" timing claim linking the ADR-0021 / 0022 / 0023 cluster to AKC ADR-0010 is a post-hoc reconstruction. The operator's recall is genuine but was not documented at the time. Future readers should treat the temporal correlation as suggestive, not as load-bearing for the cognitive-bandwidth safeguard's correctness — the safeguard stands on the retirement evidence, not on the timing claim.

## Lesson recorded

The retirement series (0028 / 0029 / 0034 / 0036) shares a structural origin, not a personal one. Reading the four retirement ADRs side by side, the proximate causes differ — A-Mem evolution produced low-quality LLM revisions; BM25 had no lexical overlap to act on; skill-router matches were never wired into the prompt path; MemoryBank Ebbinghaus was misplaced in the substrate layer. The ultimate cause is the same: in a single dense implementation cluster (2026-04-15 → 2026-04-17), four independent paper mechanisms were imported into the memory subsystem in parallel, and the worldview-integrity check did not run *before* implementation.

The structural framing matters. This is not a "the operator should have read more carefully" failure. It is a "research volume exceeded the bandwidth available for worldview-integrity checks" pattern. The cluster structure of ADR-0021 — citing MINJA, MemoryBank Ebbinghaus, Memento-Skills, and A-Mem hybrid retrieval in parallel within a single Context section — is itself the load-bearing observation. When an ADR's Context section parallel-lists multiple paper mechanisms, the integrity check has no chance to run before implementation begins; the writing pace exceeds the alignment pace.

The corresponding heuristic, captured as memory `feedback_research-volume-vs-worldview-check`:

> When an ADR's Context cites multiple unfamiliar paper mechanisms in parallel, treat that as a cognitive-bandwidth signal. Run the worldview-integrity check on each mechanism *before* the Decision section — preferably split each into its own ADR. Bundling reduces writing cost up front but pays it back later as retirement cost.

The bundled cost in this case: four retirement ADRs across three weeks, ~600 lines of removed implementation, one external dependency (`rank-bm25`) added and removed, and a `distilled` field schema bug that affected 39.6% of `knowledge.json` rows before migration. The unbundled cost would have been one extra ADR per mechanism — three to four additional ADRs at the time, all of which would have been resolvable in hours each.

## References

- [ADR-0002](0002-paper-faithful-ccai.md) — four-axiom CCAI; Emptiness axiom is the override-on-evidence clause for this ADR
- [ADR-0007](0007-security-boundary-model.md) — security boundary; the home of the surviving MINJA-defense residue from ADR-0021
- [ADR-0017](0017-yogacara-eight-consciousness-frame.md) — worldview frame, retained; this ADR provides the post-retirement update to its "Observed Convergence — 2026-04-16" subsection
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — embedding + views, retained (Yogācāra-derived: 相分 / 見分 split)
- [ADR-0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) — partially-superseded-by 0028, 0029; MINJA-defense residue retained
- [ADR-0022](0022-memory-evolution-and-hybrid-retrieval.md) — withdrawn-by 0034 (A-Mem / Mem0 / Zep / Cognee / Graphiti borrowing)
- [ADR-0023](0023-skill-as-memory-loop.md) — superseded-by 0036 (Memento-Skills borrowing)
- [ADR-0026](0026-retire-discrete-categories.md) — Phase-3 completion of 0019, retained
- [ADR-0027](0027-noise-as-seed.md) — retained (Yogācāra-derived: bīja retention)
- [ADR-0028](0028-retire-pattern-level-forgetting-feedback.md) — partial-retire of 0021 (MemoryBank Ebbinghaus moved to skill layer)
- [ADR-0029](0029-retire-dormant-provenance-elements.md) — partial-retire of 0021
- [ADR-0030](0030-withdraw-identity-blocks.md) — first withdrawal ADR in the project; precedent for keeping retired ADR bodies intact
- [ADR-0031](0031-classification-as-query.md) — retained (substrate principle for self-improving memory)
- [ADR-0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.md) — withdraws 0022; "validate-mechanism-against-actual-LLM-output" lesson
- [ADR-0036](0036-sunset-skill-as-memory-loop.md) — sunsets 0023; "wiring would not have helped — shape was wrong" lesson

External:

- [agent-knowledge-cycle ADR-0010](https://github.com/shimo4228/agent-knowledge-cycle/blob/main/docs/adr/0010-human-cognitive-resource-as-central-constraint.md) — Human Cognitive Resource as Central Constraint (2026-04-18, AKC v1.8.0). The cognitive-bandwidth principle this ADR's Decision #2 inherits.

Project memory cross-references:

- `project_yogacara_convergence` (2026-04-16) — original observation that 0019 / 0021 / 0022 converged on Yogācāra structure
- `project_mechanism_commoditization` (2026-04-12) — independent observation that mechanism-layer borrowings are commodity-like; differentiation lives in the worldview layer
- `project_mechanism_vs_value_split` (2026-04-15) — substrate principle separating embedding (mechanism) from LLM (value judgment); the technical formulation under which paper-borrowed mechanism layers are interchangeable
- `project_differentiator_akc_not_memory` (2026-04-16) — AKC cycle, not memory architecture, is the project's differentiator; consistent with this ADR's pattern that memory mechanisms are largely commodity
