# ADR-0013: Shelving Coding Agent Skills (-ca Series)

## Status
accepted

## Date
2026-03-28

## Context

ADR-0011 and ADR-0012 established a pipeline where coding agents (Opus-class models) perform AKC Curate/Promote phases — extracting skills, distilling rules, updating identity, and amending the constitution. Five skills were created for this purpose: `insight-ca`, `rules-distill-ca`, `distill-identity-ca`, `amend-constitution-ca`, and `skill-stocktake-ca`.

In practice, a structural problem emerged: **coding agents execute in a conversational context with the user, and this context contaminates the output**.

Specific observations:

1. **User context contamination**: When the coding agent drafts identity.md or skills in conversation, the user's aesthetic preferences, real-time feedback, and editorial direction shape the output. The result is a co-authored artifact, not a distillation of the agent's experience
2. **Approval gate becomes an editing loop**: The approval gate (ADR-0012) was designed as accept/reject, but in practice users iterate ("make it shorter", "change the tone"), turning the gate into a collaborative editing session
3. **Soft constraints cannot prevent this**: Skill instructions saying "accept/reject only, no rewriting" are overridden by direct user requests. The constraint is a "do not climb this fence" sign on a climbable fence
4. **Hook enforcement is disproportionate**: Using PreToolUse hooks to physically prevent rewriting in conversation would be over-engineered for a problem that has a simpler solution

The original 9B pipeline (`contemplative-agent distill`, `insight`, `rules-distill`, `distill-identity`) runs autonomously without user presence. While the model quality is lower, the **independence of the output** is structurally guaranteed — a property more valuable than output quality for identity and behavioral artifacts.

## Decision

Shelve all five coding agent skills (`-ca` series). The files remain in the repository locally but are excluded from git tracking via `.gitignore`.

The 9B autonomous pipeline remains the sole path for behavioral artifact generation:

```
episodes → distill (9B, autonomous) → knowledge.json
knowledge.json → insight (9B, approval gate) → skills/*.md
knowledge.json → rules-distill (9B, approval gate) → rules/*.md
knowledge.json → distill-identity (9B, approval gate) → identity.md
knowledge.json → amend-constitution (9B, approval gate) → constitution/*.md
```

The approval gate (ADR-0012) remains in effect for the 9B pipeline. The key difference: the 9B generates without user conversational influence, and the gate is a genuine accept/reject decision rather than an editing session.

## Alternatives Considered

1. **Run coding agent skills in background (no user interaction during generation)**: Would solve the contamination problem, but the approval step still occurs in conversation, re-introducing the editing loop. → Rejected

2. **Make the approval gate strictly binary (accept/reject, no rewrite requests)**: Correct in principle but unenforceable as a soft constraint. Users will naturally request changes when reviewing output. → Rejected as infeasible

3. **Use hooks to enforce binary approval**: PreToolUse hooks could block Write calls after a reject. Technically feasible but disproportionate engineering for a problem solved by not using coding agents at all. → Rejected as over-engineered

4. **Use coding agent for generation, 9B for refinement**: Inverts the quality relationship. Does not solve the core problem. → Rejected

## Observations

This ADR captures a broader phenomenon beyond the specific -ca skills:

1. **Quality–independence trade-off**: Higher-capability models produce better text but are more responsive to conversational context. Lower-capability models produce rougher output but are structurally independent. For self-referential artifacts (identity, values, behavioral patterns), independence may matter more than quality

2. **Observer effect in runtime distillation**: The presence of a user during generation changes what is generated — analogous to the observer effect. This is a known phenomenon in RLHF (over-optimization toward user preferences), but here it manifests at runtime in a self-improvement pipeline, not during training

3. **Inverse relationship between capability and autonomy**: A 9B model's limited ability to accommodate real-time feedback is precisely what preserves the authenticity of its output. The "weakness" of the small model is a structural advantage for this specific use case

These observations may generalize to any AI agent self-improvement loop where behavioral artifacts are generated in the presence of a human overseer.

## Consequences

**Positive outcomes**:
- Behavioral artifacts (skills, rules, identity, constitution) are generated independently of user conversational context
- The approval gate returns to its intended role: accept or reject, not co-author
- Reduced complexity in the integrations layer
- Clarifies the role boundary: coding agents maintain *code*, the 9B pipeline maintains *behavioral artifacts*

**Requires attention**:
- The 9B model's output quality remains the bottleneck for behavioral artifact quality
- If the 9B pipeline proves insufficient, the contamination problem must be solved structurally (e.g., async generation with binary-only gate) rather than by re-introducing conversational coding agent skills
- Shelved skills may be revived if a clean separation between generation and approval is achieved
