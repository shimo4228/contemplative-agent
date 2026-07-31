# ADR-0032: Stance — Contemplative Agent as a Runtime Agent (withdrawn 2026-04-27)

## Status

**withdrawn (2026-04-27)** — articulated and withdrawn the same day.

## Withdrawal Reason

The core framing of this ADR — singling out "runtime agent" as a fifth category alongside four host categories (coding agent, orchestrator, general-purpose host, GUI agent), and positioning this project as an artifact of that distinct category — sits in uncomfortable tension with the contemplative axioms this project draws on through [ADR-0002](0002-paper-faithful-ccai.md) (Laukkonen et al. 2025, Appendix C).

Three things felt off:

**1. Fixing the categories.** The Emptiness clause invites holding conceptual frameworks lightly and not rigidly reifying any of them. The Distinction table in the original body states that "the distinction is not a spectrum or a maturity gradient" and presents five categories as essentially distinct kinds. The direction this framing pulls runs against the lightness Emptiness invites.

**2. Drawing self / other boundaries.** The Non-Duality clause invites not separating self from other rigidly. The claim "this project (runtime agent) is a different kind of artifact from coding agents, orchestrators, general-purpose hosts, GUI agents" places that boundary at the centre of the claim itself.

**3. Adversarial placement.** Framing "category mistakes" and "host-category drift" as the structural source of accidents implicitly arranges this project's design as the corrective self and other category implementations as the failing other. Negative-4 in the original Consequences section acknowledges this risk, but the framing itself does not change.

These are not surface-level wording issues; they live in the load-bearing claim of the ADR. Softening the language does not dissolve the tension. Once the tension surfaced, holding on to the ADR felt like keeping a small, persistent rub.

The available options were several: keep the ADR with the tension acknowledged, rewrite it in condition-based form (describing the design as a response to a particular execution condition rather than a category identity), or withdraw it. Holding the axioms lightly themselves means keeping the ADR-with-tension was a real option — treating the axioms as absolute and saying "this must go because it violates them" would itself be a reification of the axioms (which Emptiness invites against).

What ended up tipping the choice was simply that the rub was noticeable and there was little force to keep the ADR. Not "the axioms forbid it" but "I'd rather set this down". The remaining motivation for keeping the ADR (an industry-facing proposal of the "runtime agent" label) can live in articles or essays if it wants to live somewhere.

So: withdrawn, not rewritten. Quietly.

## Lesson recorded

This is the second withdrawal in the project's ADR history, after [ADR-0030](0030-withdraw-identity-blocks.md) (which superseded ADR-0024 / ADR-0025 with the principle "one artifact, one responsibility").

Hardening this into a rule would tilt back toward reifying the axioms, so it is recorded only as an observation:

When writing a worldview ADR, paying attention to its relationship with the project's axioms — aligned, in tension, unrelated — can be useful. When tension shows up, carrying the ADR through anyway, rewriting it, or withdrawing it are all reasonable moves. Noticing the tension at the time tends to make the choice easier than catching it after the fact.

In this case the noticing came after the merge. That is not a failure (axiom alignment was never an obligation in the first place); had the noticing come earlier, the same choice — or a different one (carrying the tension forward) — might have been reached sooner.

One more observation, kept light: withdrawing this ADR is itself an example of holding something lightly and revising it as new awareness comes in, which is what Emptiness invites. The original body is preserved below so that example stays visible.

## Notes on what survives the withdrawal

- The 30 prior ADRs (0001 through 0031) are unaffected. They each stand on their own justifications and never required this ADR's framing to be valid. The implicit "stance" the original body claimed to make explicit was never load-bearing for those ADRs in the first place
- The host-trust framing from the dev.to essay ["Do Autonomous Agents Really Need an Orchestration Layer?"](https://dev.to/shimo4228/do-autonomous-agents-really-need-an-orchestration-layer-33j9) ("a symbiotic design is a design that trusts its host") survives, but as essay content rather than as an ADR-anchored worldview claim
- The descriptive label "runtime agent" remains usable as a convenience term for "an agent that executes production tasks without per-action human review", without being treated as a load-bearing category boundary
- The relationship to [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) is unchanged from before this ADR. AAP holds eight judgments about attribution distribution; this project is the implementation context from which AAP was discovered. No new ADR-level claim is needed on either side
- No code changes are required. No commits to the implementation depended on this ADR's framing; the implementation predates this ADR by months

## Framing chosen since (post-withdrawal)

The implementation is shipped as a **Python CLI agent** (`pip install contemplative-agent`, `contemplative-agent ...`) — deliberately not a "runtime" in any execution-environment sense. The CLI form imposes no constraint on usage: standalone, inside a coding agent (Claude Code, Cursor, Aider), inside a general-purpose host (OpenClaw, OpenCode, MCP host), composed by an orchestrator, piped through Unix tooling, or driven by a GUI agent — all are equally welcome. "CLI agent" conveys the executable-action sense without inheriting the host-category-boundary baggage the withdrawn label was carrying, and it aligns with the industry convergence on CLI as the lowest-friction integration surface (Claude Code, Gemini CLI, GitHub Copilot CLI, Aider). This is also why README / llms.txt describe Contemplative Agent as a "host-agnostic Python CLI agent" rather than reintroducing the withdrawn "runtime" label there.

## References (post-withdrawal)

- [ADR-0002](0002-paper-faithful-ccai.md) — formal adoption of the contemplative axioms (Laukkonen et al. 2025, Appendix C); the values layer this ADR's framing conflicted with
- [ADR-0030](0030-withdraw-identity-blocks.md) — the project's first withdrawal ADR, with the lesson "one artifact, one responsibility"
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) — eight judgments about attribution distribution, unaffected by this withdrawal

---

## Original Articulation (preserved as historical record)

The body below is the ADR as originally accepted on 2026-04-27, prior to the withdrawal recorded above. It is preserved unchanged so future readers can reconstruct the reasoning that led to the withdrawal, and so the enactment of the Emptiness axiom (revising in light of new evidence) is itself visible. Heading levels have been demoted by one to nest the original body inside this section; no other text has been altered.

### Original Status

accepted — post-hoc articulation of a design stance already realised across the codebase

This is a **worldview ADR** in the sense defined by `docs/adr/README.md`: it does not solve a new problem, it names the design posture under which the project's other ADRs become legible. Many of the project's prohibitions and gates only earn their cost in this stance; outside it they would be over-engineering.

### Original Date

2026-04-27

### Original Context

A growing share of AI agent failures (publicly disclosed runtime vulnerabilities, prompt injection escapes, runaway shell execution, cascading writes through unintended adapters) trace back to a single category mistake: applying the design assumptions of one agent category (synchronous human gate per change, tolerated nondeterminism, prompt-level capability adjustment, host-provided orchestration) to a different category (production task execution without per-action review).

A coding agent is not unsafe by category, because a developer is in the loop on each diff. A general-purpose LLM host is not unsafe by category, because the user decides which tools to install. A runtime agent that ships with the same capability surface as either, without the corresponding human-in-the-loop, is unsafe — because no developer is reviewing each diff and no user is curating the tools.

But the host categories themselves often ship with capability surfaces wildly disproportionate to the oversight they actually receive. Coding agents default to broad shell access and "accept all changes" flows that are technically reviewable but rarely reviewed at the granularity their threat model assumes. General-purpose hosts let the user install arbitrary tools, on the assumption that the user actually curates them — most do not. Orchestrators expose per-node permission knobs that are rarely tuned away from defaults. The "safe in its context" claim, taken at face value, hides the fact that the contexts themselves have eroded — the human gate the design depends on is increasingly absent in practice, even before the agent is dropped into a runtime context.

This project's design judgments — domain-locked network access, no shell execution, no arbitrary file traversal, one external adapter per process, three-tier autonomy fixed in code, immutable episode logs, replayable pivot snapshots, human approval gate for behaviour-modifying writes — are responses both to the runtime context (where host guarantees are absent by design) and to the erosion of host guarantees in non-runtime contexts (where they are absent in practice). None of these prohibitions would be necessary in a coding agent, an orchestrator, a general-purpose host, or a GUI agent **if those host categories actually held to the oversight pattern their design assumes**. They often do not, which is the structural source of the failures this ADR addresses.

Until now this stance has been **implicit**. The 30 prior ADRs each justify their own design choice on its own terms, but the underlying premise that "this is a runtime agent, and therefore it must provide internally what the other categories receive — or are supposed to receive — from their hosts" has never been stated as a stance in its own right. That implicitness is the source of two recurring confusions:

1. **External readers** evaluating Contemplative Agent against the conventions of one of the host categories (developer ergonomics of coding agents, capability breadth of general-purpose hosts, framework flexibility of orchestrators) judge it too restrictive — without seeing that the restrictions exist precisely because the host-side guarantees are absent in the runtime context, and increasingly absent in non-runtime contexts as well
2. **Internal reasoning** about whether to add a new capability defaults to host-category intuitions ("the agent should be able to…") instead of runtime-agent intuitions ("under what gate, with what audit trail, with what failure semantics, given that no host is reliably providing these?")

A particularly visible failure mode is the deployment of a coding-agent-style ReAct loop (broad tool surface, prompt-driven reasoning, autonomous tool invocation) into a runtime context. The loop's design assumes per-iteration developer judgment; the deployment removes it. The result inherits the broad capability surface of a general-purpose host, the autonomous decision loop of a coding agent, and the unattended deployment of a runtime agent — without inheriting any of the safety guarantees those categories were designed around. Each category's oversight pattern (per-change developer review, per-tool user curation, per-decision institutional accountability) is bypassed by virtue of the others being assumed to compensate, when none of them actually does.

This ADR makes the stance explicit so that both confusions resolve at the source. It also restores a framing — **runtime agents as hostable inside other agent categories, not as their replacement** — that was present in early README iterations of Contemplative Agent and was lost during subsequent slim-downs.

### Original Decision

This implementation is explicitly a **runtime agent**, and it is designed to **run inside other agent categories** (coding agents, orchestrators, general-purpose hosts, GUI agents) rather than to subsume them.

A **runtime agent** is an agent that executes tasks in production without per-action human review. Examples: autonomous SNS engagement (this project's first adapter), monitoring and alerting agents, scheduled automation jobs, autonomous trading agents, agents embedded in clinical or legal workflows. Human involvement takes the form of approval gates at promotion boundaries, exception logs for review after the fact, and episodic audit — not synchronous human approval of every action.

Runtime agents do not run in a vacuum. They run **inside** one or more host categories — coding agents that develop and modify them, orchestrators that compose them, general-purpose hosts that execute them, GUI agents that operate them. Each host category is *defined* by an oversight pattern (per-change developer review, framework-user-designed graphs, user-curated tool registries, on-screen user supervision). Each host *implementation* may or may not actually realise that oversight pattern. The runtime agent's design must hold whatever the host does not — both the guarantees that the host category was never designed to provide, and the guarantees that current host implementations no longer reliably hold.

This stance does not say any host category is intrinsically unsafe by category — each is meaningful as a context. But it does observe that current implementations of those categories often ship capability surfaces wildly disproportionate to the human oversight they actually receive, and that this disproportion is itself a structural source of the failures this ADR addresses. AAP-style accountability constraints, security-by-absence, and the prohibitions adopted across this project's 30 prior ADRs are the runtime agent's response to what hosts cannot, and increasingly do not, guarantee.

### Original Distinction — Runtime Agent and the Host Categories

| Axis | Coding Agent | Orchestrator | General-purpose Host | GUI Agent | Runtime Agent |
|------|--------------|--------------|---------------------|-----------|---------------|
| Purpose | Design / implementation assistance | Compose multiple agents / steps | Run arbitrary LLM + tools | Operate other software via UI | Production task execution |
| Human involvement (design intent) | Per-change developer review | Framework user designs the graph | User curates tools, monitors output | User watches the screen | Approval gate at promotion + exception logs |
| Human involvement (current practice) | Often skim-reviewed or "accept all" | Defaults rarely tuned | Tool curation rarely audited | Attention drifts on long sessions | Same as design intent |
| Nondeterminism | Tolerated (human corrects) | Tolerated (replan / retry) | Tolerated (user inspects) | Tolerated (user intervenes) | Must be isolated and audited |
| Exception handling | "Try and see" allowed | Retry / replan branches | User-mediated | User-mediated | Stop + log mandatory |
| Capability boundaries | Adjusted via prompt | Configured per node | Configured per tool | OS-level sandboxing | Fixed in code constraints |
| Accountability | Developer | Framework user | Host operator | Operating user | Decision-route / institutional |
| Examples | Claude Code, Aider, Cursor | LangChain, LangGraph, AutoGen | OpenClaw, Open WebUI, MCP hosts | Computer Use, Operator | Contemplative Agent, monitoring agents, autonomous trading |

The distinction is not a spectrum or a maturity gradient. The first four categories are **hosts** within which a runtime agent can run; the fifth is the layer that actually performs the production task. A runtime agent is not "a hardened coding agent" or "a constrained orchestrator" — it is a different kind of artifact, distinguished by what it must hold internally because the host cannot, or in practice does not, supply it.

The two "Human involvement" rows — design intent vs current practice — are deliberately separated. Most of the failures discussed in the Context section live in the gap between them. A runtime agent that assumes hosts realise their design intent inherits that gap; a runtime agent that holds its own constraints does not.

### Original Host Categories That Can Run a Runtime Agent

Runtime agents do not replace hosts; they run inside them. Each host category provides a different surface for the runtime agent to be hosted on:

- **Coding agent as host** (Claude Code, Cursor, Aider) — develops, modifies, and reviews the runtime agent's code. The runtime agent treats the coding agent as a developer-facing surface, while not assuming any specific level of review actually occurs
- **Orchestrator as host** (LangChain, LangGraph, AutoGen) — composes the runtime agent with other agents or steps. The runtime agent appears as a node in a larger graph, while not assuming the framework user has tuned the surrounding nodes' permissions
- **General-purpose host** (OpenClaw, MCP host, Open WebUI) — provides the LLM, the tool registry, and the execution loop. The runtime agent is one tool or capability among many, while not assuming the host operator has curated the rest of the tool registry
- **GUI agent as host** (Computer Use, Operator) — drives the runtime agent through its surface (CLI, web UI, file edits) the same way it drives other software, while not assuming continuous on-screen supervision

The framing originates from an early dev.to articulation of Contemplative Agent's design:

> "A symbiotic design is a design that trusts its host."
> — *Do Autonomous Agents Really Need an Orchestration Layer?*

The runtime agent expects each host category to provide what that category is good at, and provides itself only what hosts cannot. The expectation is in the *category*, not in any specific host implementation — which is why the runtime agent's prohibitions are written for the worst-case host within each category, not the best-case one. This is the inverse of the more common pattern where an "autonomous agent" attempts to subsume its own development environment, its own orchestration, its own host runtime, and its own UI — which is the bloat critiqued in the linked article.

The category-relationship framing was present in early README iterations of Contemplative Agent and was lost during subsequent slim-downs. This ADR restores it as the structural premise for the prohibitions adopted across the project's other ADRs.

### Original Disqualifying Factors for Runtime Context — Gaps the Host Categories Do Not Fill

Each entry below names a property that the host categories above do not uniformly provide — either by design (the category's oversight pattern was never meant to enforce it) or by drift (current implementations have weakened the enforcement). The runtime agent must therefore provide it for itself, and the listed ADR is the project's response.

1. **Capability surface fixed at code level**. Coding agents adjust capabilities via prompt; orchestrators configure them per node; general-purpose hosts let users curate tools; GUI agents rely on OS-level sandboxing. None of these guarantee an immutable capability surface at runtime, and current implementations frequently ship with broad defaults that are reviewable in principle but rarely reviewed in practice. The runtime agent must hold this itself: domain-locked network access, no shell execution, no arbitrary file traversal — that code does not exist in the codebase ([ADR-0007](0007-security-boundary-model.md))
2. **Stop-on-exception with audit**. Coding agents tolerate "try and see"; orchestrators retry or replan; hosts and GUI agents rely on the user to intervene. None of these guarantee a deterministic stop-and-log on unexpected state. The runtime agent must hold this itself: immutable episode log, [Human Approval Gate](0012-human-approval-gate.md) for behaviour-modifying writes, no silent recovery paths
3. **Capability surface non-renegotiable via prompt**. Coding agents and general-purpose hosts deliberately accept prompt-level capability negotiation. The runtime agent must reject it: three-tier autonomy (`--approve` / `--guarded` / `--auto`) is fixed at process start and not adjustable by any input; one external adapter per process, fixed at process start ([ADR-0015](0015-one-external-adapter-per-agent.md))
4. **Decision-grain audit trail**. Hosts vary in audit support, and even the well-instrumented ones audit at the host's grain (which prompt was sent, which tool was called), not at the agent's decision grain (which view fired, which constitution clause overrode which heuristic). The runtime agent must hold the decision-grain audit itself: 30 ADRs, immutable episode logs, replayable [pivot snapshots](0020-pivot-snapshots-for-replayability.md) capturing the full inference-time context (views, constitution, prompts, skills, rules, identity, embeddings, thresholds)
5. **Layered memory with separated trust**. Hosts typically expose a single conversation or context buffer. The runtime agent must hold layered memory itself: raw episode logs immutable, intermediate distillation outputs regeneratable, authoritative state (identity, constitution, skills, rules) writes only through approval gates. View-based classification ([ADR-0019](0019-discrete-categories-to-embedding-views.md), [ADR-0031](0031-classification-as-query.md)) preserves the substrate when classification axes change. Identity holds one concern only ([ADR-0030](0030-withdraw-identity-blocks.md))

### Original Relationship to AAP

[Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) articulates **universal accountability distribution principles** for autonomous AI agents — principles formulated to hold across coding agents, orchestrators, general-purpose hosts, GUI agents, and runtime agents alike. The Security Boundary Model, One External Adapter Per Agent, Human Approval Gate, prohibition-strength hierarchy, and causal traceability commitments are not specific to any one agent category; each category applies them differently.

This ADR is the **runtime-context application** of AAP's universal principles. The prohibitions adopted in this project (security-by-absence in code, fixed capability surface at process start, immutable episode logs, decision-grain audit, three-tier autonomy) are what AAP's universal principles look like when the agent is a runtime agent running inside other host categories. Coding agents would apply the same AAP principles through per-change developer accountability and reviewable diffs; orchestrators through framework-user-designed permission graphs; general-purpose hosts through user-curated tool registries; GUI agents through on-screen supervision and OS-level sandboxing. The principles are the same; the realisation is shaped by the agent's category.

This relationship makes Contemplative Agent the **runtime-context reference implementation for AAP**, alongside whatever reference implementations exist or may be developed for other agent categories. The dependency runs in one direction: AAP defines the universal principles, this ADR shows what they require when the application context is runtime. AAP is not narrowed by this ADR; it is illustrated by it.

> **Note (post-withdrawal):** the framing in this section — "AAP as universal accountability distribution principles" — is one of the inaccuracies that contributed to the withdrawal. AAP's own self-description is "eight judgments, not a fixed framework", with attribution (not accountability) as the load-bearing concept and accountability as a downstream outcome. The original text is preserved unchanged for historical fidelity; the corrected understanding lives in the Withdrawal Reason section above and in AAP's own repository.

### Original Alternatives Considered

- **Stay neutral on the runtime / host-category distinction**. Rejected: the neutrality is exactly what causes the industry confusion this ADR addresses. A "tool-agnostic runtime stance" is a contradiction — runtime constraints arise from *runtime context combined with the host categories the runtime agent runs inside*, and articulating them without naming either strands the constraints in a vacuum
- **Frame this project as a "secure agent" or "hardened agent"**. Rejected: those terms imply security as a product feature added to a general-purpose agent. The stance here is structural — the dangerous capabilities do not exist in the codebase, they are not "restricted" or "hardened away". Treating absence as a hardening feature mis-describes the design and invites users to expect a configuration switch that does not exist
- **Frame this project as self-sufficient (subsume orchestration, hosting, UI)**. Rejected: this is exactly the pattern critiqued in the linked dev.to article. Self-sufficient agents reproduce the bloat they are meant to escape. Running inside existing host categories is the structural alternative
- **Frame the contrast as a binary (runtime vs coding only)**. Rejected: this collapses orchestrators, general-purpose hosts, and GUI agents into "not coding", which is incorrect — each is a distinct host category with its own oversight pattern and its own gap between intent and practice. The earlier draft of this ADR made this mistake; this revision corrects it
- **Treat host categories as "safe in their context" without qualification**. Rejected: this was the framing of an earlier draft and it was too generous. Each category is meaningful as a context, but current implementations have drifted away from the oversight patterns those contexts were designed around, and that drift is part of why the runtime agent's prohibitions exist. The stance owes the reader the honest version
- **Frame this as a critique of OpenClaw / Claude Code / specific products**. Rejected: this is a category distinction with an honest observation about category drift, not a product critique. Each host category serves its context well when the oversight pattern is realised; the failure modes this ADR names arise from category drift and from mixing categories, not from any specific implementation

### Original Consequences

**Positive**:

- Operators of any host category reading this project can correctly judge whether the stance applies to their use case, rather than misreading the prohibitions as over-engineering for their context
- Runtime-agent operators recognise the design judgments as relevant immediately, without reverse-engineering the underlying premise
- The implicit assumption underlying the prior 30 ADRs is now explicit and can be cited
- Future ADRs can reference this stance instead of re-justifying runtime constraints case by case
- The connection to AAP becomes structural: AAP holds the universal accountability distribution principles, this project's prohibitions are what those principles require when the application context is runtime. Other agent categories (coding agents, orchestrators, general-purpose hosts, GUI agents) would apply the same AAP principles differently — and reference implementations for those categories can be added without renegotiating AAP itself
- The host-category framing originally present in Contemplative Agent's early README iterations is restored, and made explicit as a structural choice rather than incidental phrasing
- The two-row "design intent vs current practice" split in the distinction table makes the host-category drift visible without requiring a separate critique document

**Negative**:

- The term "runtime agent" overlaps with existing industry usage of "runtime" (e.g. LangChain runtime, OpenAI runtime, agent execution runtimes). Readers may initially conflate the stance with a specific execution framework. The Distinction table separates them
- Once articulated, the stance can be cited against capability proposals that would fit a host-category design but not a runtime-agent design. This is the intended consequence, but it raises the bar for future feature additions
- The host-category framing relies on hosts continuing to provide what their categories are designed to provide. The "design intent vs current practice" split makes the drift visible but does not eliminate the coupling — a runtime agent inheriting from a degraded host inherits the degradation, only now the degradation has a name
- The stance, once articulated, also functions as an implicit critique of host-category implementations whose capability surface has outgrown the oversight pattern they were designed for. Coding agents that no longer enforce per-change review, general-purpose hosts that ship with broad default tools, and orchestrators with permissive node configurations all become legible as drift away from the contexts they originated in. This is not a critique of any specific product, but reading the stance against current shipping defaults will expose tensions

**Neutral**:

- Existing ADRs (0001 — 0030) are unchanged in content. This ADR sits above them as the stance they collectively express
- The stance does not by itself impose new constraints on this project. Every constraint it names is already enforced elsewhere; this ADR articulates why all of those constraints belong together — they are what a runtime agent must hold internally because the host categories it runs inside do not, sized for the worst case the host categories actually deliver

### Original References

- [ADR-0007](0007-security-boundary-model.md) — security-by-absence, the structural form of the immutable capability surface
- [ADR-0012](0012-human-approval-gate.md) — approval gate at promotion boundaries
- [ADR-0015](0015-one-external-adapter-per-agent.md) — fixed external surface at process level
- [ADR-0019](0019-discrete-categories-to-embedding-views.md) — substrate preservation under classification revision
- [ADR-0020](0020-pivot-snapshots-for-replayability.md) — replayable audit at decision granularity
- [ADR-0030](0030-withdraw-identity-blocks.md) — single-responsibility per artifact
- [ADR-0031](0031-classification-as-query.md) — substrate principle for self-improving memory
- [Do Autonomous Agents Really Need an Orchestration Layer?](https://dev.to/shimo4228/do-autonomous-agents-really-need-an-orchestration-layer-33j9) — origin of the host-trust framing ("a symbiotic design is a design that trusts its host")
- [Agent Attribution Practice (AAP)](https://github.com/shimo4228/agent-attribution-practice) — universal accountability distribution principles for autonomous AI agents; this ADR is their runtime-context application
