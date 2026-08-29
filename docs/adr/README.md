# Architecture Decision Records

Records of key design decisions for this project.

## Index

| ADR | Title | Status | Date |
|-----|-------|--------|------|
| [0001](0001-core-adapter-separation.md) | Core/Adapter Separation | accepted | 2026-03-10 |
| [0002](0002-paper-faithful-ccai.md) | Paper-Faithful CCAI Implementation | accepted | 2026-03-12 |
| [0003](0003-config-directory-design.md) | Config Directory Design | accepted | 2026-03-12 |
| [0004](0004-three-layer-memory.md) | Three-Layer Memory Architecture `[AKC: Extract/Curate/Promote]` | accepted | 2026-03-17 |
| [0005](0005-session-context-refactoring.md) | SessionContext Refactoring | accepted | 2026-03-14 |
| [0006](0006-docker-network-isolation.md) | Docker Network Isolation | superseded-by 0070 | 2026-03-14 |
| [0007](0007-security-boundary-model.md) | Security Boundary Model | accepted | 2026-03-12 |
| [0008](0008-two-stage-distill-pipeline.md) | Two-Stage Distill Pipeline `[AKC: Extract]` | accepted | 2026-03-22 |
| [0009](0009-importance-score.md) | KnowledgeStore Importance Score `[AKC: Extract/Quality Gate]` | accepted | 2026-03-24 |
| [0010](0010-research-data-sync.md) | Research Data Sync | accepted | 2026-03-25 |
| [0011](0011-knowledge-injection-to-skills.md) | Deprecating Direct Knowledge Injection in Favor of Skills `[AKC: Curate]` | accepted | 2026-03-26 |
| [0012](0012-human-approval-gate.md) | Human Approval Gate for Behavior-Modifying Commands `[AKC: Curate/Promote]` | accepted | 2026-03-26 |
| [0013](0013-shelve-coding-agent-skills.md) | Shelving Coding Agent Skills (-ca Series) `[AKC: Curate/Promote]` | accepted | 2026-03-28 |
| [0014](0014-retire-system-spec.md) | Retiring system-spec.md `[AKC: Maintain]` | accepted | 2026-04-01 |
| [0015](0015-one-external-adapter-per-agent.md) | One External Adapter Per Agent | accepted | 2026-04-08 |
| [0016](0016-insight-narrow-stocktake-broad.md) | Insight as Narrow Generator, Stocktake as Broad Consolidator `[AKC: Extract/Curate]` | partially-superseded-by ADR-0097 | 2026-04-11 |
| [0017](0017-yogacara-eight-consciousness-frame.md) | Yogācāra Eight-Consciousness Model as Architectural Frame | accepted | 2026-04-11 |
| [0018](0018-per-caller-num-predict-embedding-stocktake.md) | Per-Caller num_predict + Embedding-Only Stocktake | accepted | 2026-04-15 |
| [0019](0019-discrete-categories-to-embedding-views.md) | Discrete Categories → Embedding + Views `[AKC: Promote]` | accepted | 2026-04-15 |
| [0020](0020-pivot-snapshots-for-replayability.md) | Pivot Snapshots for Replayability `[AKC: Curate]` | accepted | 2026-04-16 |
| [0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) | Pattern Schema Extension — Provenance / Bitemporal / Forgetting / Feedback | partially-superseded-by 0028, 0029, 0051 | 2026-04-16 |
| [0022](0022-memory-evolution-and-hybrid-retrieval.md) | Memory Evolution + Hybrid Retrieval (BM25) | withdrawn-by 0034 | 2026-04-16 |
| [0023](0023-skill-as-memory-loop.md) | Skill-as-Memory Loop — Router, Usage Log, Reflective Write | superseded-by 0036 | 2026-04-16 |
| [0024](0024-identity-block-separation.md) | Identity Block Separation — Frontmatter-Addressed Persona Blocks | superseded-by 0030 | 2026-04-16 |
| [0025](0025-identity-history-and-migrate-cli.md) | Identity History Log Wiring + migrate-identity CLI | superseded-by 0030 | 2026-04-16 |
| [0026](0026-retire-discrete-categories.md) | Retire Discrete Categories (Phase-3 Completion of ADR-0019) | partially-superseded-by 0060 | 2026-04-16 |
| [0027](0027-noise-as-seed.md) | Noise as Seed — From Binary Gate to Salience-Based Forgetting | superseded-by 0060 | 2026-04-16 |
| [0028](0028-retire-pattern-level-forgetting-feedback.md) | Retire Pattern-Level Forgetting and Feedback — Memory Dynamics Belong to the Skill Layer | accepted — partially-supersedes 0021 | 2026-04-18 |
| [0029](0029-retire-dormant-provenance-elements.md) | Retire Dormant Provenance Elements — `user_input` / `external_post` / `sanitized` | accepted — partially-supersedes 0021 | 2026-04-18 |
| [0030](0030-withdraw-identity-blocks.md) | Withdraw Identity Block Separation and History Wiring — Single Responsibility | accepted — supersedes 0024 and 0025 | 2026-04-18 |
| [0031](0031-classification-as-query.md) | Classification as Query — Substrate Principle for Self-Improving Memory | accepted | 2026-04-27 |
| [0032](0032-runtime-agent-stance.md) | Stance — Contemplative Agent as a Runtime Agent | withdrawn — tension with contemplative axioms (ADR-0002) | 2026-04-27 |
| [0033](0033-aap-quadrant-lens-usage-note.md) | Note — Borrowing AAP's Four-Quadrant Lens as a Usage-Description Aid | accepted (note) | 2026-05-01 |
| [0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.md) | Withdraw Memory Evolution and BM25 Hybrid Retrieval — Cost Without Benefit | accepted — supersedes 0022 | 2026-05-05 |
| [0035](0035-sunset-migration-surface-and-consolidate-artifact-extraction.md) | Sunset ADR-0019 Migration Surface and Consolidate Artifact Extraction | accepted | 2026-05-05 |
| [0036](0036-sunset-skill-as-memory-loop.md) | Sunset Skill-as-Memory Loop — Retire Router, Usage Log, and Reflect | accepted — supersedes 0023 | 2026-05-05 |
| [0037](0037-memory-subsystem-yogacara-convergence.md) | Memory Subsystem Converges to Yogācāra Frame; Paper-Borrowed Mechanisms Retired | accepted | 2026-05-05 |
| [0038](0038-moment-of-recognition-distill.md) | Re-introduce Moments of Recognition into the Distill Observation Target `[AKC: Extract]` | accepted | 2026-05-13 |
| [0039](0039-novelty-score-lagrangian-self-post-gate.md) | Continuous Novelty Score with Rate-Deficit Lagrangian for Self-Post Gate | accepted | 2026-05-19 |
| [0040](0040-separate-code-level-findings.md) | Separate Code-Level Findings from Weekly Self-Reflection Report | partially-superseded-by ADR-0099 | 2026-05-19 |
| [0041](0041-engagement-gradient-asymmetry-in-self-post-prompt.md) | Repair the Engagement Gradient Asymmetry in the Self-Post Prompt | accepted | 2026-05-19 |
| [0042](0042-explicit-truncation-contract-for-untrusted-wrapper.md) | Explicit Truncation Contract for `wrap_untrusted_content` | accepted | 2026-05-20 |
| [0043](0043-per-post-seeding-for-self-post-generation.md) | Per-Post Seeding for Self-Post Generation | accepted | 2026-05-21 |
| [0044](0044-remove-topic-keywords.md) | Remove `topic_keywords` End-to-End | accepted | 2026-05-23 |
| [0045](0045-pre-action-internal-note.md) | Record Pre-Action `internal_note` at the Episode Layer | accepted | 2026-05-25 |
| [0046](0046-stocktake-llm-grouping-over-embedding-clustering.md) | Stocktake Duplicate Detection — LLM Grouping over Embedding Clustering | partially-superseded-by ADR-0097 | 2026-05-30 |
| [0047](0047-comment-sampling-temperature.md) | Higher Sampling Temperature for Outward Comment Generation | accepted | 2026-05-30 |
| [0048](0048-trigger-altitude-skill-lifecycle.md) | Trigger-Altitude for Skill Lifecycle | partially-superseded-by ADR-0097 | 2026-06-02 |
| [0049](0049-meditation-active-inference-fidelity-and-deferral.md) | Meditation Adapter — Beautiful Loop Fidelity Audit and Deferral of Faithful Re-Implementation | accepted | 2026-06-03 |
| [0050](0050-epistemic-taxonomy-and-approval-lineage.md) | Epistemic Taxonomy and Approval Lineage — Observability Without Steering | partially-superseded-by 0051, 0082 | 2026-06-05 |
| [0051](0051-retire-trust-weighting.md) | Retire Trust Weighting — Pure Cosine Retrieval and Bitemporal-Only Liveness | accepted — partially-supersedes 0021, 0050 | 2026-06-05 |
| [0052](0052-retire-session-insight.md) | Retire Session Insight Generation — Identity Is the Approved Continuity Channel | accepted | 2026-06-05 |
| [0053](0053-importance-encoding-time-significance.md) | Importance as Encoding-Time Significance — Three Judgment Points and Re-observation Promotion | partially-superseded-by 0056 | 2026-06-06 |
| [0054](0054-externalize-llm-instruction-text-to-prompts.md) | Externalize LLM Instruction Text to `config/prompts/` with Hardcoded Fallback for the Injection Boundary | accepted | 2026-06-09 |
| [0055](0055-counterparty-identity-by-author-name.md) | Counterparty Identity by Author Name; Unified Activity/Report Schema | accepted | 2026-06-15 |
| [0056](0056-retire-importance-llm-scoring.md) | Retire the Distill-Time Importance LLM Rating — Extraction Weight Is Pure Time Decay | accepted — partially-supersedes 0053 | 2026-06-17 |
| [0057](0057-identity-from-self-reflection-corpus-alone.md) | Distill Identity From the Self-Reflection Corpus Alone — Drop the Prior-Identity Seed and Redundant Axiom Injection `[AKC: Promote]` | accepted | 2026-06-20 |
| [0058](0058-value-injection-at-action-time.md) | Value-Layer Injection Belongs to Action Time, Not Distillation `[AKC: Extract/Curate/Promote]` | accepted | 2026-06-20 |
| [0059](0059-remove-dead-reply-history.md) | Remove the Dead Reply-History Mechanism | accepted | 2026-06-22 |
| [0060](0060-per-episode-grounded-distill.md) | Per-Episode Grounded Distill — Replace Batch Extract + Noise Gate with One Grounded LLM Call per Engagement Episode | accepted — supersedes 0027; partially-supersedes 0026 | 2026-06-23 |
| [0061](0061-action-time-untrusted-cap-at-platform-limits.md) | Action-Time Untrusted Input Caps at Platform Field Limits; Internal Note Reads the Full Body | accepted | 2026-06-23 |
| [0062](0062-create-time-verification-handshake.md) | Create-Time Content-Verification Handshake with Hybrid LLM/Code Solver; Gate Recording on Visibility | accepted | 2026-06-26 |
| [0063](0063-novelty-gate-verified-only-comparison.md) | Scope the NoveltyGate Comparison to Verified (Visible) Posts | accepted | 2026-06-26 |
| [0064](0064-mlx-generation-backend.md) | Route Generation Through a Local mlx_lm.server on Apple Silicon | superseded-by 0070 | 2026-06-27 |
| [0065](0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) | Wire mlx_lm.server as an On-Demand launchd Job and Enforce a Served-Model-ID Contract on LLM Telemetry | partially-superseded-by 0067/0070 | 2026-06-27 |
| [0066](0066-backend-aware-context-budget-guard.md) | Backend-Aware Context-Budget Guard via an LLMBackend.context_window Contract | accepted | 2026-06-27 |
| [0067](0067-keep-ollama-for-unattended-production.md) | Keep Ollama as the Production Generation Backend — mlx_lm.server Unfit for Unattended Continuous Use on 16 GB Apple Silicon | accepted — partially-supersedes 0065 | 2026-06-28 |
| [0068](0068-per-call-think-flag-and-thinking-trace-capture.md) | Per-Call `think` Flag and Reasoning-Trace Capture to the Episode Log | accepted | 2026-06-28 |
| [0069](0069-gemma-production-model-and-think-on-value-layer-pipelines.md) | Adopt gemma4:e4b as the Production Generation Model and Run the Value-Layer Pipelines think-ON | accepted | 2026-06-28 |
| [0070](0070-retire-mlx-to-sibling-repo-and-remove-docker.md) | Retire the MLX Backend to a Sibling Repo and Remove Docker from Main | accepted — supersedes 0006, 0064; partially-supersedes 0065 | 2026-06-28 |
| [0071](0071-read-only-pattern-composition-instruments.md) | Read-Only Pattern-Composition Instruments (View Supply / Diversity / Grounding) | accepted | 2026-07-03 |
| [0072](0072-echo-chamber-interventions.md) | Echo-Chamber Interventions — Register Instruction, Corpus-Grown Seed, Extraction-Failure Guard | accepted | 2026-07-03 |
| [0073](0073-prune-orphaned-view-seeds.md) | Prune the Five Orphaned View Seeds | accepted | 2026-07-03 |
| [0074](0074-weekly-staged-insight.md) | Weekly Staged Insight — Theme Detection, Pending Guard, Marker-on-Stage, LLM Novelty Gate, Exact Fast Clustering | accepted | 2026-07-09 |
| [0075](0075-observability-by-default.md) | Observability by Default — Replayable Audit Logs Ship With the Feature | accepted | 2026-07-09 |
| [0076](0076-skill-selection-shadow-instrument.md) | Skill-Selection Shadow Instrument — Pass-1 LLM Applicability Observed, Not Enforced | accepted | 2026-07-10 |
| [0077](0077-chaos-tdd-fault-injection.md) | Chaos-TDD Fault Injection — Seeded Fault Schedules as Test-First Specification (Pilot: distill) | partially-superseded-by ADR-0100 | 2026-07-13 |
| [0078](0078-otel-connection-via-vocabulary-and-offline-export.md) | OTel Connection via Vocabulary Mapping and Offline Export — Not Runtime Adoption | accepted | 2026-07-16 |
| [0079](0079-module-reorganization-package-splits.md) | Module Reorganization — Package Splits, Permanent Facades, and Documented Size-Cap Exceptions | accepted | 2026-07-18 |
| [0080](0080-north-star-layered-end-state.md) | North Star — Per-Layer End-State Definition, Not a Capability Target | accepted | 2026-07-20 |
| [0081](0081-skill-selection-two-pass-injection-enforcement.md) | Skill-Selection Two-Pass Injection Enforcement | accepted | 2026-07-24 |
| [0082](0082-retire-observed-epistemic-key.md) | Retire the `observed` Epistemic Key — Delete the Dead Field, Not the Warning About It | accepted — partially-supersedes 0050 | 2026-07-25 |
| [0083](0083-episode-logs-enter-the-weekly-prompt-as-hashes-only.md) | Episode Logs Enter the Weekly Prompt as Hashes Only | accepted | 2026-07-25 |
| [0084](0084-post-distill-durability-gate.md) | Post-Distill Durability Gate — Judge the Produced Patterns, Not the Episode | accepted | 2026-07-26 |
| [0085](0085-unattended-weekly-fix-chain-single-saturday-gate.md) | Unattended Weekly Fix Chain with a Single Saturday Gate | partially-superseded-by ADR-0098 | 2026-07-29 |
| [0086](0086-submolt-scope-instrument-before-autonomy.md) | Submolt Scope — Instrument the Question Before Handing Over the Answer | accepted | 2026-08-01 |
| [0087](0087-optional-token-counting-capability-for-the-context-budget-guard.md) | An Optional `count_tokens` Capability for the Context-Budget Guard | accepted — extends 0066 | 2026-08-01 |
| [0088](0088-shipped-conformance-kit-for-the-llm-backend-contract.md) | A Shipped Conformance Kit for the `LLMBackend` Contract | accepted | 2026-08-02 |
| [0089](0089-llm-behavioral-eval-layer-on-deepeval.md) | An LLM Behavioral Eval Layer on DeepEval | accepted | 2026-08-06 |
| [0090](0090-ipd-two-arm-instrument-for-constitution-amendments.md) | Run an IPD Two-Arm Bench Before Adopting a Constitution Amendment | accepted | 2026-08-09 |
| [0091](0091-value-layer-cadence-in-the-weekly-chain.md) | Value-Layer Cadence in the Weekly Chain | partially-superseded-by ADR-0098 | 2026-08-10 |
| [0092](0092-shadow-constitution-instrument.md) | Shadow Constitution Instrument — Patterns-Only Synthesis, Observe-Only | accepted | 2026-08-11 |
| [0093](0093-repo-plane-deterministic-intakes.md) | Repo-Plane Deterministic Intakes — Docs Consistency and Ledger Condition Watch | partially-superseded-by 0095, ADR-0098 | 2026-08-14 |
| [0094](0094-agent-first-task-ledger.md) | Agent-First Task Ledger — Store / Journal / Projection | superseded-by 0095 | 2026-08-15 |
| [0095](0095-retire-task-ledger-machinery.md) | Retire the Task-Ledger Machinery — Keep the Store and the Claims, Drop Everything That Parsed | accepted — supersedes 0094; partially-supersedes 0093 | 2026-08-16 |
| [0096](0096-insight-promotion-worth-abstain.md) | Promotion-Worth Abstain at Insight Time — Judge the Produced Skill, List the Surprise | partially-superseded-by ADR-0097 | 2026-08-17 |
| [0097](0097-consolidator-dissolution-and-skill-store-exit.md) | Consolidator Dissolution and a Skill-Store Exit — Subtraction, then Exit, then Vocabulary | accepted — partially-supersedes ADR-0016, ADR-0046, ADR-0048, ADR-0096 | 2026-08-22 |
| [0098](0098-weekly-single-session-and-triage-delegation.md) | Weekly Chain Single-Session Redesign and Repair Delegation to the Task-Triage Loop | accepted — partially-supersedes ADR-0085, ADR-0091, ADR-0093 | 2026-08-24 |
| [0099](0099-weekly-report-instrument-redesign.md) | Weekly Report Content Redesign: From A–E Quote Audit to a Six-Section Instrument Document | accepted — partially-supersedes ADR-0040 | 2026-08-26 |
| [0100](0100-retire-chaos-tdd-by-default-mandate.md) | Retire the Chaos-TDD By-Default Mandate — Fault Columns Return to Opt-In Judgment | accepted — partially-supersedes ADR-0077 | 2026-08-29 |
| [0101](0101-instrument-dissolution-mandate.md) | Instrument Dissolution Mandate — New Instruments Must Name Their Consumption | accepted | 2026-08-29 |

## ADR Types

ADRs in this project fall into two categories with different editability rules:

**Problem-solving ADRs (emergent)**
Record reactive design decisions triggered by a concrete issue. Most ADRs in this index are of this type. They can be superseded by later ADRs that offer a better solution for the same problem.

Examples: ADR-0005 (SessionContext refactoring), ADR-0008 (two-stage distill pipeline), ADR-0009 (importance score), ADR-0016 (insight narrow / stocktake broad).

**Worldview ADRs (axiomatic)**
Record the mental models and philosophical frames that the project operates under from the start. These are *not* reactive — they are the prerequisite under which problem-solving ADRs are even formulated. Changing a worldview ADR is not the same as fixing a bug; it is altering the project's identity and requires a different kind of judgment.

Examples: ADR-0002 (paper-faithful CCAI), ADR-0007 (security boundary model), ADR-0017 (Yogācāra eight-consciousness frame).

**Rule of thumb**: If the ADR could have been written differently under a different project with the same problem, it is problem-solving. If the ADR describes a frame under which the project's problems become legible at all, it is worldview. Worldview ADRs are downstream-of-nothing; problem-solving ADRs are downstream of a worldview (even if unnamed).

## Template

When adding a new ADR, follow this format:

```markdown
# ADR-NNNN: Title

## Status
accepted / proposed / withdrawn / superseded-by ADR-NNNN

## Date
YYYY-MM-DD

## Context
What was the problem

## Decision
What was decided

## Alternatives Considered
Rejected options and why

## Consequences
What resulted from this decision

## References
- `ADR-NNNN` (`NNNN-slug.md`) — short note on the relationship (supersedes / refines / depends-on / precedent)
- External sources (papers, prior art, evidence)
```

### Status line conventions

The Status field follows established phrasing so that the index, ADR bodies, and `graph.jsonld` stay in sync. Use one of:

- `accepted` — currently in effect
- `accepted — supersedes ADR-NNNN` — replaces an earlier ADR (the index also lists the replaced ADR with `superseded-by ADR-NNNN`)
- `accepted — partially-supersedes ADR-NNNN[, ADR-NNNN]` — replaces only specific sections of an earlier ADR (the index also lists the older ADR with `partially-superseded-by ADR-NNNN`; name the scope in the ADR body)
- `accepted (note)` — observational / narrow ADR that does not commit the project to a long-lived rule
- `accepted (amended YYYY-MM-DD)` — body amended; see the Amendment section in the ADR
- `partially-superseded-by ADR-NNNN[, ADR-NNNN]` — only specific sections were replaced; surviving sections remain in effect
- `superseded-by ADR-NNNN` — fully replaced; preserve the original body
- `withdrawn by ADR-NNNN` — retracted because a later ADR judged this approach incorrect
- `withdrawn (YYYY-MM-DD)` — retracted in-place, typically same-day or by the same author; the body preserves the withdrawal reason

The relationship phrases (`supersedes`, `superseded-by`, `withdrawn by`, `partially-supersedes`, `partially-superseded-by`) are mirrored as typed edges (`supersedes`, `supersededBy`, `withdrawnBy`, `partiallySupersedes`, `partiallySupersededBy`) in `graph.jsonld` so LLMs can traverse the supersede / withdrawal chain without parsing prose. A node's edges must match its own Status prose — a bare `accepted` node carries no supersede-family edge — and `tests/test_adr_status_consistency.py` enforces that alongside head agreement across all five faces. The mirror is per-node, with one cross-node rule: partial supersessions must carry both halves, because the two are one claim stated from each end rather than a vocabulary choice. Six of them recorded only the backward half until 2026-08-15 (T-ADR-PARTIAL-RECIPROCITY); `test_partial_supersede_edges_are_reciprocal` now fails on a half added without its counterpart. Whether a withdrawal should also read as a supersession stays a judgment call and is not asserted.

**Which half states which scope.** A partial supersession has two scopes — what was retired, and what still stands — and they belong on different faces. The **forward** half (on the newer ADR) names only what *it* retired. The **surviving** scope lives on the **backward** half (on the superseded ADR), because that is the only face that can stay correct as later partial supersessions land: ADR-0021's residue today is what survived ADR-0028, ADR-0029 *and* ADR-0051, so replicating it onto any one of them would have each claim a state that was not true on its own date. No test can check this — it is a semantic agreement between two prose faces — so it is a convention, written here because the 2026-08-15 review caught all four new forward halves stating it wrongly before the convention existed. Prose inside a body describing a scoped supersession uses `supersedes X in part`, the form the Status parser also accepts; a bare `superseded` on a scoped subject reads as a full retirement.

## Guidelines

- Numbers are sequential (0001–), in chronological order
- Changes to existing ADRs are made via a new ADR that supersedes the original (never overwrite)
- When an ADR supersedes or withdraws another, update the older ADR's Status to point at the new one (one-line edit; do not rewrite the body)
- Only record decisions affecting architecture, data models, or security — minor decisions need not be recorded
- When adding a new ADR, also add a node (and any supersede / withdrawal edges) to `graph.jsonld` so the LLM-facing knowledge graph stays current
- Use `/sync-context` to check consistency between the ADR index and files
