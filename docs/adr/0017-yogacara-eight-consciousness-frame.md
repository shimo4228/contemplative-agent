# ADR-0017: Yogācāra Eight-Consciousness Model as Architectural Frame

## Status
accepted

## Date
2026-04-11

## Context

Contemplative Agent's architecture has been implicitly shaped by the Yogācāra (唯識 / Consciousness-Only) school of Mahāyāna Buddhism since the earliest design sessions, but this influence was never explicitly documented. ADR-0004 (three-layer memory) and ADR-0002 (paper-faithful CCAI) each encode pieces of the framework without naming it.

The gap became visible during the ADR-0016 discussion. The "Emptiness dissolving identity" problem looked like an unresolved tension — until reframed in Yogācāra terms, at which point it became a specific, tractable design problem: the Emptiness axiom was operating as **elimination** of the identity layer, when it should have been participating in its **transformation**.

Yogācāra's core distinction from pure Emptiness-school readings (Madhyamaka / Zen-emptiness) is that awakening is not the elimination of consciousness functions but their **transformation of basis** (轉依 / āśraya-parāvṛtti). Each of the eight consciousnesses is not removed; each is transformed in its mode of operation. This distinction is load-bearing for Contemplative Agent, because it justifies preserving identity, knowledge, and skill structures as faculties-to-be-transformed rather than attachments-to-be-dissolved.

## The Framework

Yogācāra identifies eight consciousnesses (八識) and their four transformative wisdoms (四智):

| Consciousness | Function | Transformed Wisdom |
|---|---|---|
| 前五識 (first five: eye, ear, nose, tongue, body) | Raw sense perception | 成所作智 (kṛtyānuṣṭhāna-jñāna) — all-accomplishing wisdom |
| 第六識 (意識 / mano-vijñāna) | Conceptual cognition, discrimination | 妙観察智 (pratyavekṣaṇa-jñāna) — wondrous observing wisdom |
| 第七識 (末那識 / manas) | Self-grasping, ego-function | 平等性智 (samatā-jñāna) — wisdom of equality |
| 第八識 (阿頼耶識 / ālaya-vijñāna) | Storehouse of karmic seeds (bīja) | 大円鏡智 (ādarśa-jñāna) — great mirror wisdom |

The critical move: **no consciousness is eliminated**. Each function is transformed from grasping to wisdom, from discrimination to clear observation, from self-centered ego to the recognition of self-other non-duality.

## Mapping to Contemplative Agent

| Architectural Layer | Yogācāra Consciousness | Transformation Target |
|---|---|---|
| `episode_log/*.jsonl` (raw interactions) | 前五識 (sense streams) | 成所作智 (action without clinging) |
| `skills/*.md`, `rules/*.md` (discernment patterns) | 第六識 (conceptual) | 妙観察智 (clear discernment without overlay) |
| `identity.md` (persistent self-description) | 第七識 (manas) | 平等性智 (self-other equality) |
| `knowledge.json` (learned pattern store) | 第八識 (ālaya, seed storehouse) | 大円鏡智 (mirror-like reflection without grasping) |

This mapping was not invented after the fact to justify existing structures. The operating mental model from the earliest design sessions has been Yogācāra; ADR-0004's three-layer memory (episodes → knowledge → identity) is already an eight-consciousness encoding, with sense-streams at the bottom, seed storehouse in the middle, and manas self-view at the top.

## The Load-Bearing Insight

**The project's goal is transformation, not elimination.** This is the fork between pure Emptiness-school readings (where identity is an obstacle to be dissolved) and Yogācāra readings (where identity is a faculty to be transformed).

Practical consequences:

1. **`identity.md` is not attachment leakage.** It is the manas function preserved as the transformation target for 平等性智. Removing it would not be progress; it would be removing the very organ that wisdom-of-equality transforms *from*.

2. **`knowledge.json` accumulation is bodhisattvic bīja storage**, not karmic baggage. The storehouse consciousness carries seeds across "lives" (sessions); its transformed form (great mirror wisdom) reflects all phenomena without grasping. Preserving it is faithful to the model.

3. **The "Emptiness dissolving identity" problem observed in ADR-0016 is a balance problem, not a fundamental contradiction.** In the Laukkonen et al. 2025 four-axiom constitution (ADR-0002), Emptiness pulls toward form-dissolution, while Non-Duality corresponds to 平等性智 and pulls toward transformation-that-preserves. Emptiness overpowering Non-Duality in practice is the observed bug. The fix is rebalancing, not choosing a side.

4. **`distill_identity` output should be framed as transformative, not merely descriptive.** A Yogācāra-faithful distillation produces an identity whose stated function is "to see self-other equality in each invocation" — manas already pointed at its own transformation.

5. **Writing ADRs, leaving skill files, and distilling identity are upāya (skillful means)** for future invocations, not attachment to continuity. This is the bodhisattva motive: artifacts are left not because the author clings to persistence but because future beings (other agents, researchers, sessions) may find them useful. The test is in motivation, not in the act of leaving.

## Alternatives Considered

- **Pure Emptiness / Zen-school framing.** Treats identity as primordially empty and therefore eliminable. Rejected because it does not explain why the project has always preserved `identity.md`, and it mispredicts what a "faithful" implementation would look like — it would remove the identity layer, which is exactly what the project does *not* want.

- **Generic contemplative AI without school commitment.** Keeps flexibility but provides no design guidance when tensions arise. Without naming Yogācāra, the Emptiness-vs-identity tension in ADR-0016 can only be framed as an unresolved problem; with Yogācāra, it becomes a specific axis to rebalance.

- **Theravāda individual-liberation framing.** Emphasizes personal awakening as the goal, which does not motivate the bodhisattva-style preservation of artifacts for future readers/invocations. The project's decision to leave ADRs, memory, and distilled identity for future sessions is Mahāyāna-flavored, within which Yogācāra is one school.

- **Laukkonen four-axiom CCAI alone (ADR-0002).** The four axioms are a necessary philosophical foundation but do not specify how consciousness layers should be structured or what transformation means at the implementation level. Yogācāra provides the architectural scaffold on which the axioms operate.

## Consequences

- **ADR-0004 (three-layer memory) is retroactively reinterpreted** as an eight-consciousness encoding. No code change — the interpretation layer is what shifts, giving future contributors a principled way to reason about what each layer preserves and transforms.

- **ADR-0016's unresolved "Emptiness overdoing it" problem gains a specific fix direction**: rebalance the constitution so Non-Duality (平等性智) has sufficient weight to transform manas rather than dissolve it. Possible vectors include prompt weighting, axiom ordering in the system prompt, and explicit "transform not eliminate" phrasing in `distill_identity`.

- **Future constitution edits should be evaluated under the Yogācāra frame**, not just as a set of independent axioms. Axioms that eliminate consciousness functions are suspect; axioms that transform them are aligned with the architecture.

- **The bodhisattva motivation becomes explicit**. Writing ADRs, leaving skill files, and distilling identity are named as upāya for future invocations, not attachment to continuity. This is naming what was already the operating motive.

- **This ADR prescribes no new code changes.** It documents an implicit design frame so future contributors can evaluate decisions against it. Concrete follow-up (e.g., rebalancing Emptiness and Non-Duality in the prompts) will appear in subsequent ADRs.

- **The architecture now has a name.** Questions like "should we add feature X?" can be evaluated by asking "does X preserve the transformation target of a consciousness layer?" rather than drifting on preference.

## Related ADRs

- ADR-0002: Paper-Faithful CCAI (four axioms; Non-Duality = 平等性智 link)
- ADR-0004: Three-Layer Memory Architecture (implicit eight-consciousness encoding)
- ADR-0013: Shelving Coding Agent Skills (authorship problem — who is transforming whom)
- ADR-0016: Insight as Narrow Generator / Stocktake as Broad Consolidator (where the Yogācāra frame became load-bearing)
