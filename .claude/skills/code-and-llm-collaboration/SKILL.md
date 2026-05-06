---
name: code-and-llm-collaboration
description: Design patterns for layering deterministic code and LLM calls in a single pipeline or agent. Use when designing a pipeline that mixes semantic and structural work — distillation, extraction with validation, approval gates, orchestrated multi-step workflows. Catalogs four load-bearing layering patterns (LLM→Code guard, Code filter→LLM, LLM judge + Code enforce, Code orchestrator + LLM worker) with when-to-use, failure modes, and minimal code sketches. Macro-level companion to the micro "which tool for this one task" question.
origin: shimo4228
user-invocable: true
---

# Code and LLM Collaboration

When building a pipeline that mixes semantic work (summarization, classification, extraction) with structural work (validation, filtering, dispatch), the interesting question is **not** "which one should I use?" It is **"in what order, and with what contract between the layers?"**

Code and LLMs work best as layers, each doing the job the other cannot:

- Code is deterministic, cheap, and auditable but cannot understand meaning.
- LLMs handle meaning but are slow, probabilistic, and attackable.

Four layering patterns cover most real pipelines. Each has a characteristic failure mode when layers are skipped or reversed. Recognize which pattern you need, wire it in the correct order, and keep the contract between layers strict.

---

## Pattern 1 — LLM → Code guard

**Shape.** The LLM produces structured output. A code layer validates that output against a schema and enforces constraints before anything downstream consumes it. If validation fails, the pipeline rejects or retries — it does not pass partial output forward.

**When to use.**

- Any time LLM output will be written to a persistent store (database, knowledge file, identity document)
- Any time LLM output will be executed as structured data (tool-call arguments, JSON config, API payload)
- Any time the LLM is allowed to propose changes that a human will review — the guard prevents a human from rubber-stamping an invalid proposal

**Key insight.** The LLM is allowed to be wrong. The guard is not. Treat the LLM as an untrusted but capable proposer, and treat the code layer as the trusted gatekeeper that makes "accept" a deterministic decision.

**Minimal sketch.**

```python
def extract_with_guard(raw_text: str) -> Skill | None:
    proposal = llm.generate(
        prompt=build_extraction_prompt(raw_text),
        format=SKILL_JSON_SCHEMA,  # constrained decoding when available
    )
    if proposal is None:
        return None
    try:
        skill = Skill.model_validate_json(proposal)  # pydantic / dataclass
    except ValidationError as exc:
        logger.warning("LLM proposal rejected: %s", exc)
        return None
    if not passes_forbidden_pattern_check(skill.body):
        logger.warning("LLM proposal contained forbidden pattern — rejected")
        return None
    return skill
```

**Failure modes when skipped.**

- **No guard at all.** LLM hallucinations silently corrupt the knowledge store. You discover it weeks later when a downstream consumer crashes on an unexpected field.
- **Guard is itself an LLM.** Judge-by-LLM is probabilistic. It is appropriate for quality scoring but not for structural acceptance.
- **Guard only checks schema, not content.** A prompt-injection payload that is syntactically valid JSON still passes. Include forbidden-pattern and size checks alongside the schema.

---

## Pattern 2 — Code filter → LLM

**Shape.** Code narrows the input first — by date, event type, size, structural relevance — then the LLM does semantic work on a small, focused subset.

**When to use.**

- Processing large logs or corpora where most items are irrelevant to the current task
- Any pipeline where the LLM cost scales linearly with input size and most of that input adds no signal
- Extraction from noisy streams (episode logs, activity records, chat transcripts)

**Key insight.** LLMs are worst at saying "this doesn't matter" on huge contexts and best at extracting meaning from a short, relevant slice. Do the "doesn't matter" work in code first, then hand the LLM a curated input.

**Minimal sketch.**

```python
def distill(log_path: Path, days: int) -> list[Pattern]:
    cutoff = datetime.now() - timedelta(days=days)
    candidates = [
        event for event in load_events(log_path)
        if event.timestamp >= cutoff
        and event.kind in DISTILL_KINDS
        and len(event.body) >= MIN_BODY_LEN
    ]
    if not candidates:
        return []
    prompt = build_distill_prompt(candidates)
    return llm.extract_patterns(prompt)
```

**Failure modes when skipped.**

- **No filter.** You feed the full log to the LLM, pay 100× the tokens, and the LLM's attention dilutes so the extraction quality drops.
- **Filter is itself an LLM.** You now pay for two LLM passes where one structural filter would do. This is the most common "LLM going wrong" failure in this pattern.
- **Filter is too aggressive.** Over-filtering hides the LLM from context it needs. Tune the filter on a hand-labeled set before trusting it in production.

---

## Pattern 3 — LLM judge + Code enforce

**Shape.** The LLM makes a judgment (accept / reject, score, diff is an improvement / regression). Code then enforces the action based on that judgment — with a human approval gate where the action is high-stakes.

**When to use.**

- Self-updating identity, rules, or configuration
- Constitution / policy changes
- Any change where "is this an improvement?" is genuinely semantic but the *consequence* of the change must be deterministic

**Key insight.** Separate the probabilistic decision (LLM judge) from the deterministic action (code enforcer). Never let the LLM directly mutate durable state. The LLM proposes; code, optionally with a human, disposes.

**Minimal sketch.**

```python
def amend_constitution(current: str, proposal: str) -> None:
    judgment = llm.judge(
        prompt=build_amendment_judgment_prompt(current, proposal),
        format=JUDGMENT_SCHEMA,  # {"verdict": "accept"|"reject", "reason": str}
    )
    if judgment is None or judgment.verdict != "accept":
        logger.info("Amendment rejected: %s", judgment and judgment.reason)
        return
    if not human_approves(current, proposal, judgment.reason):
        return
    write_atomic(constitution_path, proposal)  # deterministic action
```

**Failure modes when skipped.**

- **No enforce layer.** The LLM "decides" and the state mutates in the same call. Prompt injection now has write access to the constitution.
- **No human gate on high-stakes changes.** Identity or ethical-constraint rewrites need a human in the loop. The judge is a filter, not a final authority.
- **Judge prompt leaks the current state as trusted.** If the "current" document is itself compromised, the judge will justify compounding compromises. Wrap both documents as untrusted content in the prompt.

---

## Pattern 4 — Code orchestrator + LLM worker

**Shape.** A deterministic loop or pipeline written in code drives the overall flow. Each step inside the loop calls the LLM to do one focused semantic task. The loop owns termination, retry budgets, state transitions, and error handling. The LLM owns none of those.

**When to use.**

- Multi-step extraction or distillation pipelines
- Agentic workflows with bounded step counts and a clear completion signal
- Any workflow where "did we finish?" or "should we retry?" must be answerable without asking the LLM

**Key insight.** LLMs are poor at owning a loop. They forget to stop, forget what they already did, and make decisions that accumulate rather than converge. Code owns control flow; the LLM owns local reasoning.

**Minimal sketch.**

```python
def distill_two_stage(candidates: list[Event]) -> list[Pattern]:
    stage1 = []
    for batch in chunked(candidates, size=20):
        result = llm.extract_raw(batch)
        if result is None:
            continue
        stage1.extend(result)
    if not stage1:
        return []
    stage2 = llm.consolidate(stage1)
    return validated(stage2)  # code guard — Pattern 1
```

Notice how Patterns 1, 2, and 4 compose naturally: a code orchestrator drives the loop, each step is a filtered-then-LLM call, and the final result passes a code guard.

**Failure modes when skipped.**

- **LLM owns the loop.** "Keep going until you're done" — the LLM either halts early on the wrong signal or runs forever. Always give the orchestrator a hard iteration cap and a deterministic completion check.
- **No per-step error budget.** One failing LLM call takes down the whole run. The orchestrator should handle per-step failure and continue with partial results when appropriate.
- **State lives in the LLM's context instead of the orchestrator.** If you cannot resume the pipeline from disk after a crash, the orchestrator is not actually in control.

---

## How the patterns compose

Real pipelines stack these:

1. Pattern 4 (orchestrator) wraps everything.
2. Inside each step, Pattern 2 (code filter → LLM) narrows the input.
3. Pattern 1 (LLM → code guard) validates each LLM output before it persists.
4. Pattern 3 (judge + enforce) kicks in whenever the pipeline wants to mutate durable state.

The useful question during design is *which layer owns each responsibility*, not *which tool is better*. If a responsibility does not have a clear owner, the pipeline will fail at that seam.

---

## Diagnostic checklist

Use these when reviewing a pipeline design:

1. **Where is the guard?** Every LLM output that reaches persistent state must pass a deterministic schema + content check. If you cannot point at the guard function, it does not exist.
2. **Who owns the loop?** If the answer is "the LLM decides when to stop," rewrite so code owns termination.
3. **Is the filter before or after the LLM?** If filtering is semantic, it is a different LLM call; if it is structural, it belongs in code *before* the LLM sees the data.
4. **Does the judge-write-state path exist?** The LLM must not mutate durable state directly. Insert a code-enforce step — with a human gate if the change is high-stakes.
5. **Can the pipeline resume after a crash from disk state alone?** If no, state is living in the LLM's head and the orchestrator is fiction.
6. **Is every LLM input wrapped as untrusted content?** The orchestrator should never hand raw accumulated state to the LLM without a boundary marker.
7. **Is there a retry budget and a deterministic completion signal?** Every loop needs both; "the LLM will know when it's done" is not a design.

If any answer is "no" or "unclear," there is a seam in the design where the layers are not collaborating — they are colliding.
