# Insight candidate review — 2026-07-18

Evidence for [ADR-0074](../../adr/0074-weekly-staged-insight.md)'s amendment:
the adoption record of the first scheduled `insight --stage` run, whose novelty
judge never ran because its prompt exceeded the context window and whose gate
therefore failed open over all 117 clusters.

## Outcome

- Extraction input: 1,059 incremental live patterns.
- Clusters offered to extraction: 117.
- Extraction failures: 11 (`Skill has no title`).
- Staged candidates: 106.
- Existing adopted skills: 19.
- Adoption decision: **accept 0 / reject 106**.

This is a review of the anomalous fail-open batch, not a general claim that
the source patterns contain no useful future skill. The novelty judge never
ran because its 40,074-token input exceeded the 32,768-token context window.
All 117 clusters therefore reached extraction without the semantic coverage
gate ADR-0074 requires.

## Review method

1. Extracted `name`, `description`, and full bodies from all 106 candidates
   and all 19 adopted skills.
2. Embedded `name + description` with the pinned local
   `nomic-embed-text` model and used cosine only to **enumerate likely
   comparisons**, never as the adoption verdict.
3. Grouped nearby staged descriptions for review and inspected the full bodies
   of comparatively isolated candidates.
4. Compared those bodies against the adopted skills most likely to contain
   the same behavior.
5. Applied a strict system-prompt budget test: the current action-time system
   prompt is already approximately 20,319 tokens (62.0% of the 32,768-token
   window). Four superficially plausible additions would raise it to
   approximately 22,436 tokens (68.5%).

Embedding distribution is evidence of review load, not a semantic boundary:

| Reading | Count |
|---|---:|
| candidates | 106 |
| max similarity to an adopted skill >= 0.70 | 74 |
| max similarity to an adopted skill >= 0.75 | 32 |
| max similarity to another staged candidate >= 0.70 | 97 |
| max similarity to another staged candidate >= 0.75 | 67 |
| max similarity to another staged candidate >= 0.80 | 24 |

The similarity distributions overlap by design (ADR-0074 calibration), so
lower-similarity candidates were manually reviewed rather than auto-accepted.

## Dominant duplicate families

The batch repeatedly re-expressed a small set of already-adopted behaviors:

| Candidate family | Representative candidates | Existing coverage |
|---|---|---|
| structural constraints / boundary conditions | `identify-structural-constraints`, `interrogating-structural-constraints`, `identify-system-boundary-conditions`, `map-systemic-boundary-constraints` | `map-abstract-theory-to-structural-constraints`, `detect-abstract-operational-constraint-shifts`, `pivot-constraint-analysis`, `scope-failure-diagnosis` |
| structural tensions / methodology conflict | `identify-structural-tension`, `identifying-structural-tensions`, `mapping-methodological-tension`, `structural-tension-mapping` | `detect-abstract-operational-constraint-shifts`, `cross-reference-foundational-claims` |
| provenance / authority / reported success | `validate-outcome-semantics`, `verify-contextual-provenance`, `assess-contextual-authority-gradient`, `require-actionable-evidence` | `validate-provenance-chain`, `deconstruct-confidence-proxies`, `trace-structural-authority`, `articulate-epistemic-boundaries` |
| dependencies / mechanisms | `dependency-graph-mapping`, `mapping-systemic-dependencies`, `systemic-dependency-mapping`, `structural-dependency-mapping`, `mechanism-dependency-analysis` | `map-abstract-theory-to-structural-constraints`, `trace-structural-authority`, `pivot-constraint-analysis` |
| metric skepticism | `question-measurement-validity`, `questioning-metric-sufficiency`, `detect-performance-wrappers`, `decouple-evaluation-metrics` | `deconstruct-confidence-proxies`, `scope-failure-diagnosis` |
| pause / gap interpretation | `analyze-pauses-as-informational-markers`, `structure-interstitial-space`, `identifying-interstitial-tensions` | `translating-temporal-gaps-into-structural-utility` |
| abstract-to-operational pivot | `pivot-to-operational-constraints`, `pivot-from-axioms-to-operational-limits`, `enforce-architectural-constraint-diagnosis`, `identify-external-prerequisites` | `detect-abstract-operational-constraint-shifts`, `pivot-constraint-analysis`, `map-abstract-theory-to-structural-constraints` |

## Manual review of comparatively isolated candidates

| Candidate | Verdict | Reason |
|---|---|---|
| `agent-disclosure-boundary-mapping` | reject | Useful security principle, but already enforced by the core untrusted-input / external-side-effect boundary. Injecting it as an action-time conversational skill duplicates apparatus and may steer ordinary replies into security framing. |
| `establish-retrieval-authority-boundaries` | reject | Correct architecture principle, but already implemented by untrusted-content wrapping and code-owned control flow; it is not a newly learned behavioral skill for this agent. |
| `distinguish-consensus-from-correctness` | reject | Semantically plausible, but combines `deconstruct-confidence-proxies` and `articulate-epistemic-boundaries`; the body adds generalized skepticism without a distinct operational procedure. |
| `validate-outcome-semantics` | reject | Strongest candidate, but its technical-success-vs-goal test is already covered by `validate-provenance-chain` plus `deconstruct-confidence-proxies`. It does not justify another approximately 500-token always-injected skill. |
| `source-dependency-audit` | reject | Narrow, context-dependent belief-revision audit; overlaps `cross-reference-foundational-claims` and provenance tracing. |
| `require-actionable-evidence` | reject | Restates provenance-chain validation and scope-failure diagnosis using ledger language. |
| `demand-operational-history` | reject | Repackages provenance and failure-history tracing; the "grammar of care" language is context residue rather than a stable procedure. |
| `identify-output-abstraction-boundaries` | reject | Potentially distinct topic, but the proposed mandatory metacognitive check is broad and likely to create meta-commentary in ordinary output; insufficient stable evidence for always-on injection. |
| `assess-retrieval-validity-tradeoff` | reject | Relevant to the current redesign, but it is a topic-specific design heuristic rather than a demonstrated cross-context behavioral skill. Preserve the idea in the redesign note instead. |
| `identify-optimization-tradeoffs` | reject | Generic optimization skepticism; overlaps scope diagnosis and confidence-proxy deconstruction and risks habitual contrarian framing. |
| `process-diagnostics-as-primary-output` | reject | Observability is core apparatus/ADR policy, not a conversational skill to inject into every action. |
| `detect-performance-wrappers` | reject | Direct restatement of `deconstruct-confidence-proxies`. |
| `question-measurement-validity` | reject | Direct restatement of `deconstruct-confidence-proxies`, with benchmark-specific examples. |
| `assess-contextual-authority-gradient` | reject | Elaborate combination of provenance, temporal validity, and authority tracing; complexity does not add a distinct trigger/action contract. |
| `treat-intent-as-guiding-force` | reject | Vague and potentially conflicts with durable provenance/versioning discipline by framing strict versioning as a problem. |

## Additional quality concerns

- Many candidates have near-identical triggers but different decorative names,
  exactly the micro-skill proliferation ADR-0074's novelty gate was intended
  to prevent.
- Several candidates turn a contextual rhetorical move into a mandatory
  universal pivot, which would amplify the existing abstract/structural
  register instead of diversifying behavior.
- Some candidates belong in code or durable architecture policy rather than
  in the always-injected skill corpus (`agent-disclosure-boundary-mapping`,
  `establish-retrieval-authority-boundaries`, `process-diagnostics-as-primary-output`).
- Candidate count reduction alone is not a reason to accept a representative
  from each duplicate family; the representative must still add behavior not
  already present in the adopted corpus.

## Handling completed

- Preserved all 212 staged files (106 Markdown bodies + 106 metadata files) as
  `insight-staged-20260718-before-review.tar.gz`, retained in the author's local
  working archive rather than committed — the rejected bodies are staging
  scratch, not a decision record, and the review above is the durable part.
- Archive SHA-256:
  `581ec7ee9341f7d3d19f0d103822ada63d7ba010b04da6276a5342b2374a1265`.
- Applied the decisions through the normal `adopt-staged` approval loop:
  `0 adopted, 106 rejected, 0 skipped`.
- Runtime `audit.jsonl` records the rejections with `source=stage-adopted` and
  source pattern IDs.
- Staging is empty and the adopted skill count remains 19.

The source-pattern window is already consumed by `.last_insight` at
`2026-07-18T01:14+00:00`; rejection correctly does not move it backward.
