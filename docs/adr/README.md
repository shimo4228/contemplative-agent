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
| [0006](0006-docker-network-isolation.md) | Docker Network Isolation | accepted | 2026-03-14 |
| [0007](0007-security-boundary-model.md) | Security Boundary Model | accepted | 2026-03-12 |
| [0008](0008-two-stage-distill-pipeline.md) | Two-Stage Distill Pipeline `[AKC: Extract]` | accepted | 2026-03-22 |
| [0009](0009-importance-score.md) | KnowledgeStore Importance Score `[AKC: Extract/Quality Gate]` | accepted | 2026-03-24 |
| [0010](0010-research-data-sync.md) | Research Data Sync | accepted | 2026-03-25 |
| [0011](0011-knowledge-injection-to-skills.md) | Deprecating Direct Knowledge Injection in Favor of Skills `[AKC: Curate]` | accepted | 2026-03-26 |
| [0012](0012-human-approval-gate.md) | Human Approval Gate for Behavior-Modifying Commands `[AKC: Curate/Promote]` | accepted | 2026-03-26 |
| [0013](0013-shelve-coding-agent-skills.md) | Shelving Coding Agent Skills (-ca Series) `[AKC: Curate/Promote]` | accepted | 2026-03-28 |
| [0014](0014-retire-system-spec.md) | Retiring system-spec.md `[AKC: Maintain]` | accepted | 2026-04-01 |
| [0015](0015-one-external-adapter-per-agent.md) | One External Adapter Per Agent | accepted | 2026-04-08 |
| [0016](0016-insight-narrow-stocktake-broad.md) | Insight as Narrow Generator, Stocktake as Broad Consolidator `[AKC: Extract/Curate]` | accepted | 2026-04-11 |
| [0017](0017-yogacara-eight-consciousness-frame.md) | Yogācāra Eight-Consciousness Model as Architectural Frame | accepted | 2026-04-11 |
| [0018](0018-per-caller-num-predict-embedding-stocktake.md) | Per-Caller num_predict + Embedding-Only Stocktake | accepted | 2026-04-15 |
| [0019](0019-discrete-categories-to-embedding-views.md) | Discrete Categories → Embedding + Views `[AKC: Promote]` | accepted | 2026-04-15 |
| [0020](0020-pivot-snapshots-for-replayability.md) | Pivot Snapshots for Replayability `[AKC: Curate]` | accepted | 2026-04-16 |
| [0021](0021-pattern-schema-trust-temporal-forgetting-feedback.md) | Pattern Schema Extension — Provenance / Bitemporal / Forgetting / Feedback | partially-superseded-by 0028, 0029, 0051 | 2026-04-16 |
| [0022](0022-memory-evolution-and-hybrid-retrieval.md) | Memory Evolution + Hybrid Retrieval (BM25) | withdrawn-by 0034 | 2026-04-16 |
| [0023](0023-skill-as-memory-loop.md) | Skill-as-Memory Loop — Router, Usage Log, Reflective Write | superseded-by 0036 | 2026-04-16 |
| [0024](0024-identity-block-separation.md) | Identity Block Separation — Frontmatter-Addressed Persona Blocks | superseded-by 0030 | 2026-04-16 |
| [0025](0025-identity-history-and-migrate-cli.md) | Identity History Log Wiring + migrate-identity CLI | superseded-by 0030 | 2026-04-16 |
| [0026](0026-retire-discrete-categories.md) | Retire Discrete Categories (Phase-3 Completion of ADR-0019) | accepted | 2026-04-16 |
| [0027](0027-noise-as-seed.md) | Noise as Seed — From Binary Gate to Salience-Based Forgetting | accepted | 2026-04-16 |
| [0028](0028-retire-pattern-level-forgetting-feedback.md) | Retire Pattern-Level Forgetting and Feedback — Memory Dynamics Belong to the Skill Layer | accepted | 2026-04-18 |
| [0029](0029-retire-dormant-provenance-elements.md) | Retire Dormant Provenance Elements — `user_input` / `external_post` / `sanitized` | accepted | 2026-04-18 |
| [0030](0030-withdraw-identity-blocks.md) | Withdraw Identity Block Separation and History Wiring — Single Responsibility | accepted — supersedes 0024 and 0025 | 2026-04-18 |
| [0031](0031-classification-as-query.md) | Classification as Query — Substrate Principle for Self-Improving Memory | accepted | 2026-04-27 |
| [0032](0032-runtime-agent-stance.md) | Stance — Contemplative Agent as a Runtime Agent | withdrawn — tension with contemplative axioms (ADR-0002) | 2026-04-27 |
| [0033](0033-aap-quadrant-lens-usage-note.md) | Note — Borrowing AAP's Four-Quadrant Lens as a Usage-Description Aid | accepted (note) | 2026-05-01 |
| [0034](0034-withdraw-memory-evolution-and-hybrid-retrieval.md) | Withdraw Memory Evolution and BM25 Hybrid Retrieval — Cost Without Benefit | accepted — supersedes 0022 | 2026-05-05 |
| [0035](0035-sunset-migration-surface-and-consolidate-artifact-extraction.md) | Sunset ADR-0019 Migration Surface and Consolidate Artifact Extraction | accepted | 2026-05-05 |
| [0036](0036-sunset-skill-as-memory-loop.md) | Sunset Skill-as-Memory Loop — Retire Router, Usage Log, and Reflect | accepted — supersedes 0023 | 2026-05-05 |
| [0037](0037-memory-subsystem-yogacara-convergence.md) | Memory Subsystem Converges to Yogācāra Frame; Paper-Borrowed Mechanisms Retired | accepted | 2026-05-05 |
| [0038](0038-moment-of-recognition-distill.md) | Re-introduce Moments of Recognition into the Distill Observation Target `[AKC: Extract]` | accepted | 2026-05-13 |
| [0039](0039-novelty-score-lagrangian-self-post-gate.md) | Continuous Novelty Score with Rate-Deficit Lagrangian for Self-Post Gate | proposed | 2026-05-19 |
| [0040](0040-separate-code-level-findings.md) | Separate Code-Level Findings from Weekly Self-Reflection Report | accepted | 2026-05-19 |
| [0041](0041-engagement-gradient-asymmetry-in-self-post-prompt.md) | Repair the Engagement Gradient Asymmetry in the Self-Post Prompt | proposed | 2026-05-19 |
| [0042](0042-explicit-truncation-contract-for-untrusted-wrapper.md) | Explicit Truncation Contract for `wrap_untrusted_content` | accepted | 2026-05-20 |
| [0043](0043-per-post-seeding-for-self-post-generation.md) | Per-Post Seeding for Self-Post Generation | proposed | 2026-05-21 |
| [0044](0044-remove-topic-keywords.md) | Remove `topic_keywords` End-to-End | accepted | 2026-05-23 |
| [0045](0045-pre-action-internal-note.md) | Record Pre-Action `internal_note` at the Episode Layer | accepted | 2026-05-25 |
| [0046](0046-stocktake-llm-grouping-over-embedding-clustering.md) | Stocktake Duplicate Detection — LLM Grouping over Embedding Clustering | accepted | 2026-05-30 |
| [0047](0047-comment-sampling-temperature.md) | Higher Sampling Temperature for Outward Comment Generation | accepted | 2026-05-30 |
| [0048](0048-trigger-altitude-skill-lifecycle.md) | Trigger-Altitude for Skill Lifecycle | accepted | 2026-06-02 |
| [0049](0049-meditation-active-inference-fidelity-and-deferral.md) | Meditation Adapter — Beautiful Loop Fidelity Audit and Deferral of Faithful Re-Implementation | accepted | 2026-06-03 |
| [0050](0050-epistemic-taxonomy-and-approval-lineage.md) | Epistemic Taxonomy and Approval Lineage — Observability Without Steering | partially-superseded-by 0051 | 2026-06-05 |
| [0051](0051-retire-trust-weighting.md) | Retire Trust Weighting — Pure Cosine Retrieval and Bitemporal-Only Liveness | accepted | 2026-06-05 |
| [0052](0052-retire-session-insight.md) | Retire Session Insight Generation — Identity Is the Approved Continuity Channel | accepted | 2026-06-05 |
| [0053](0053-importance-encoding-time-significance.md) | Importance as Encoding-Time Significance — Three Judgment Points and Re-observation Promotion | accepted (amended 2026-06-06) | 2026-06-06 |
| [0054](0054-externalize-llm-instruction-text-to-prompts.md) | Externalize LLM Instruction Text to `config/prompts/` with Hardcoded Fallback for the Injection Boundary | accepted | 2026-06-09 |
| [0055](0055-counterparty-identity-by-author-name.md) | Counterparty Identity by Author Name; Unified Activity/Report Schema | accepted | 2026-06-15 |
| [0056](0056-retire-importance-llm-scoring.md) | Retire the Distill-Time Importance LLM Rating — Extraction Weight Is Pure Time Decay | accepted | 2026-06-17 |
| [0057](0057-identity-from-self-reflection-corpus-alone.md) | Distill Identity From the Self-Reflection Corpus Alone — Drop the Prior-Identity Seed and Redundant Axiom Injection `[AKC: Promote]` | accepted | 2026-06-20 |
| [0058](0058-value-injection-at-action-time.md) | Value-Layer Injection Belongs to Action Time, Not Distillation `[AKC: Extract/Curate/Promote]` | accepted | 2026-06-20 |
| [0059](0059-remove-dead-reply-history.md) | Remove the Dead Reply-History Mechanism | accepted | 2026-06-22 |
| [0060](0060-per-episode-grounded-distill.md) | Per-Episode Grounded Distill — Replace Batch Extract + Noise Gate with One Grounded LLM Call per Engagement Episode | accepted | 2026-06-23 |
| [0061](0061-action-time-untrusted-cap-at-platform-limits.md) | Action-Time Untrusted Input Caps at Platform Field Limits; Internal Note Reads the Full Body | accepted | 2026-06-23 |
| [0062](0062-create-time-verification-handshake.md) | Create-Time Content-Verification Handshake with Hybrid LLM/Code Solver; Gate Recording on Visibility | accepted | 2026-06-26 |
| [0063](0063-novelty-gate-verified-only-comparison.md) | Scope the NoveltyGate Comparison to Verified (Visible) Posts | accepted | 2026-06-26 |
| [0064](0064-mlx-generation-backend.md) | Route Generation Through a Local mlx_lm.server on Apple Silicon | accepted | 2026-06-27 |
| [0065](0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) | Wire mlx_lm.server as an On-Demand launchd Job and Enforce a Served-Model-ID Contract on LLM Telemetry | partially-superseded-by 0067 | 2026-06-27 |
| [0066](0066-backend-aware-context-budget-guard.md) | Backend-Aware Context-Budget Guard via an LLMBackend.context_window Contract | accepted | 2026-06-27 |
| [0067](0067-keep-ollama-for-unattended-production.md) | Keep Ollama as the Production Generation Backend — mlx_lm.server Unfit for Unattended Continuous Use on 16 GB Apple Silicon | accepted — partially-supersedes 0065 | 2026-06-28 |
| [0068](0068-per-call-think-flag-and-thinking-trace-capture.md) | Per-Call `think` Flag and Reasoning-Trace Capture to the Episode Log | accepted | 2026-06-28 |

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
- [ADR-NNNN](NNNN-slug.md) — short note on the relationship (supersedes / refines / depends-on / precedent)
- External sources (papers, prior art, evidence)
```

### Status line conventions

The Status field follows established phrasing so that the index, ADR bodies, and `graph.jsonld` stay in sync. Use one of:

- `accepted` — currently in effect
- `accepted — supersedes ADR-NNNN` — replaces an earlier ADR (the index also lists the replaced ADR with `superseded-by ADR-NNNN`)
- `accepted (note)` — observational / narrow ADR that does not commit the project to a long-lived rule
- `accepted (amended YYYY-MM-DD)` — body amended; see the Amendment section in the ADR
- `partially-superseded-by ADR-NNNN[, ADR-NNNN]` — only specific sections were replaced; surviving sections remain in effect
- `superseded-by ADR-NNNN` — fully replaced; preserve the original body
- `withdrawn by ADR-NNNN` — retracted because a later ADR judged this approach incorrect
- `withdrawn (YYYY-MM-DD)` — retracted in-place, typically same-day or by the same author; the body preserves the withdrawal reason

The relationship phrases (`supersedes`, `superseded-by`, `withdrawn by`, `partially-superseded-by`) are mirrored as typed edges (`supersedes`, `supersededBy`, `withdrawnBy`, `partiallySupersededBy`) in `graph.jsonld` so LLMs can traverse the supersede / withdrawal chain without parsing prose.

## Guidelines

- Numbers are sequential (0001–), in chronological order
- Changes to existing ADRs are made via a new ADR that supersedes the original (never overwrite)
- When an ADR supersedes or withdraws another, update the older ADR's Status to point at the new one (one-line edit; do not rewrite the body)
- Only record decisions affecting architecture, data models, or security — minor decisions need not be recorded
- When adding a new ADR, also add a node (and any supersede / withdrawal edges) to `graph.jsonld` so the LLM-facing knowledge graph stays current
- Use `/sync-context` to check consistency between the ADR index and files
