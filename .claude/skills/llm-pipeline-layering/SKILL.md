---
name: llm-pipeline-layering
description: Design know-how for splitting a small local LLM's work across calls — by KIND of work (extract, then format/validate) and by ORDER (a call that judges an artifact must run after that artifact exists). Use when one generate() call is asked to do two things at once (decide-then-produce, extract-then-format), when a prompt's abstain path is a degenerate case of its output format and never fires, when choosing whether constrained decoding (`format=`/enum) helps or starves a task, when a reasoning model's chain-of-thought is being suppressed by an answer-only constraint, or when deciding where a quality gate belongs. NOT for choosing code vs LLM for a task in the first place (that is when-code-when-llm), NOT for the 4-layer code/LLM pipeline split (code-and-llm-collaboration), and NOT for fault injection at those seams (ADR-0077).
compatibility: Written for the Contemplative Agent repo (measurements are from its Ollama pipeline); the patterns themselves are portable to any small-model pipeline.
origin: auto-extracted
---

# LLM Pipeline Layering for Small Models

**Extracted:** 2026-03-22
**Context:** When a small local LLM (≤9B) produces unreliable output format or quality

## Problem

Small models can't handle "extract + format" in a single generate() call. Results:

- Prompt-only format instructions are ignored (~50% of the time)
- Constrained decoding (Ollama `format`) guarantees structure but **degrades content quality** — model capacity is consumed by structure enforcement
- Few-shot examples can **worsen** output by consuming context on a small model

## Solution: 3 Principles

### 1. Separate Extraction from Formatting (Layer the calls)

```python
# Step 1: Extract (creative task — no constraints, full LLM capacity)
result = generate(prompt, max_length=4000)

# Step 2: Refine (mechanical task — short input, simple task)
refined = generate(refine_prompt.format(raw_output=result), max_length=4000)
```

Each layer has a simple task. Like neural network layers:

- Step 1 = hidden layer (feature extraction)
- Step 2 = output layer (formatting)
- Quality gate = activation function (threshold filter)

### 2. Validate at Save-Time, Not Generate-Time

```python
# BAD: Constrained decoding at generation (consumes model capacity)
result = generate(prompt, format=json_schema)  # structure ✅, content ❌

# GOOD: Free generation + save-time validation
result = generate(prompt)  # content ✅
patterns = [p for p in parsed if is_valid(p)]  # structure ✅ at save-time
```

Key insight: **Constraining output structure at generation time consumes model capacity, reducing task comprehension.** Validate at save time instead — it costs zero LLM capacity.

### 3. Quality Gate (Decision Layer)

```python
def _is_valid_pattern(pattern: str) -> bool:
    if len(pattern) < 30:
        return False  # Labels only ("user interaction")
    if pattern.count(" ") < 3:
        return False  # Not a sentence
    return True
```

Simple heuristics that reject garbage without risking good content. Inspired by CIMP Decision concept — "is this worth storing?"

## Splitting is ordered, not just split (2026-07-26)

Principle 1 splits a call by *kind of work* (extract, then format). There is a
second axis: **a call that judges an artifact must run after that artifact
exists.** Splitting a judgment to the front of the pipeline removes the evidence
it needs, and a small model then answers "yes" essentially always.

Evidence — distilling one social-media episode into durable patterns
(gemma4:e4b, 40 fixed episodes per arm, 5 arms):

| Arm | Shape | Abstain rate | Register vs baseline |
|-----|-------|--------------|----------------------|
| baseline | one call: "produce 1-3 patterns, or [] if nothing" | 0.1% (prod, n=1700) | — |
| merged, judge-framed | same call, reframed as a judgment | 15% | degraded (I+verb 54% vs 73%) |
| merged, count anchor removed | same call, no "1 to 3" and no 2-element example | 2.5% | baseline |
| **split, judge BEFORE** | gate over the episode, then distill | **0% (0/40)** | baseline (prompt untouched) |
| **split, judge AFTER** | distill, then gate over the produced patterns | **5%** | **above baseline (I+verb 86%)** |

Three readings:

1. **A merged call couples its two tasks.** One line of prompt swung the abstain
   rate 2.5% <-> 15% *and* moved output register with it. You cannot tune one
   without moving the other, so neither can be measured cleanly.
2. **A pre-artifact judgment degenerates to yes.** Naming a worthwhile result
   costs nothing when you never have to produce it. Verified this was not a
   plumbing bug: substitution correct, JSON parsed, boolean real, and a
   contentless control episode did return false. The gate worked; it had nothing
   to judge. (Constrained decoding was fine here — a short verdict is exactly the
   case the "Applicability" section above endorses for `format`.)
3. **Producing the artifact IS the evidence requirement.** Move the judgment
   after production and it starts saying no — and because what it drops is the
   material that lacked substance, the surviving output measured *better* than
   baseline, not merely fewer.

Corollary for prompts of the form "produce X, but return empty if there is
nothing": that abstain is a degenerate case of the output format, competing with
whatever example arity the format line shows. Measured: the example carried two
elements and the production median was exactly 2, with the abstain firing on
2 of 1,700 episodes. Prefer a separate post-production judge; if you must keep
one call, at least do not put the abstain on the same line as a count band and
an example.

Same shape appeared three times in one codebase — a distill prompt (0.1%), a
skill-extraction prompt whose "is this worth promoting" question is implemented
as "could a titled document be produced?" (0%), and the pre-artifact gate above
(0%). **When a prompt makes "yes" the cooperative answer and never requires the
model to pay for it, the no-path is decorative.**

## When to Use

- Local LLM with ≤13B parameters producing unreliable output
- LLM output that needs both good content AND consistent structure
- Any pipeline where a single generate() call handles multiple concerns
- When constrained decoding (Ollama `format`, Instructor) produces correct structure but empty/shallow content

## Anti-Patterns

- **Don't add Few-shot to small models** when context is already large — it consumes context and can worsen output
- **Don't use constrained decoding for long-form generation** on small models — save it for short outputs (scoring, classification, selection)
- **Don't force a reasoning model to skip thinking** (answer-only prompt or `format=`) for CoT-dependent tasks — leave output free and extract the final value in code
- **Don't skip the quality gate** — even with 2-stage, some garbage passes through

## Applicability of Constrained Decoding

Ollama `format` is still valuable for:

- Short outputs: relevance scoring (`{"score": 0.85}`), yes/no decisions, category selection
- Tasks where structure IS the task (not a secondary concern)

Avoid `format` for:

- Long-form generation (patterns, summaries, identity, posts)
- Tasks requiring creativity or deep comprehension

### Empirical Results (2026-03-31)

Benchmark: 50 real episodes × 6 runs (Before/v1/v2 × 2 each), qwen3.5:9b

| Task type | Schema | Effect |
|-----------|--------|--------|
| Classification (3-label enum) | `{"type": "string", "enum": [...]}` | **Effective** — noise判定の分散 range 11→3 に縮小 |
| Importance scoring (int array) | `{"scores": [int]}` | No effect — already stable with prompt+fallback |
| Dedup decisions (string array) | `{"decisions": [str]}` | No effect — already stable with prompt+fallback |

**Priority order**: enum制約 (ラベル選択) > 配列制約 (スコア/判定) > 適用しない (意味生成)

Key insight: プロンプト + フォールバックチェーンが既に安定している箇所に constrained decoding を追加しても効果は見えない。**判定が揺れている箇所**（特に上流の分類）に適用するのが最も効果的。

## Reasoning models: don't suppress the chain-of-thought (2026-06-26)

The "constrain at generate-time consumes capacity" principle has a sharper form
for **reasoning models** (e.g. qwen3.5:9b emits a `<think>` block): any constraint
that forces an immediate answer — a prompt "reply with ONLY the number" OR
`format=`/enum decoding — suppresses the reasoning the model needs, and the answer
degrades. The task looks like a tiny output (one number), so it's tempting to
constrain it; don't.

Evidence — solving an obfuscated 2-number arithmetic CAPTCHA, qwen3.5:9b:

| Approach | Result |
|----------|--------|
| Prompt "reply with ONLY the number" (no CoT) | wrong (20+5 → "27"; even clean text) |
| `format=json` extract `{num1,op,num2}`, compute in code | fast 5–8s but **3/6** — JSON constraint suppressed `<think>`, number-words misread (twenty→10) |
| Free reasoning, extract the **last** number in code | **6/6** correct (34–90s warm) |

Pattern for CoT-dependent tasks (arithmetic, de-obfuscation, multi-step parse):

- Prompt "reason step by step; on the final line output only the answer." Leave
  output **unconstrained** (no `format`, no answer-only).
- Extract the final value in code (`re.findall(r"-?\d+...", out)[-1]`) — the
  conclusion is the last number (output-side guard, à la "validate at save-time").
- `num_predict` generous enough for the reasoning to **finish** (a cap, not a
  target — the model stops at its natural end). Pair with `drop_truncated=True`
  so a cut-off trace fails closed (None → retry) instead of yielding a number
  pulled from incomplete work (seen: 512-token cap → "15" became "1"). Same
  failure shape as ollama's num_ctx silent truncation: caps that cut silently
  turn partial work into confident wrong answers — always fail closed on cut-off.

Corollary: still split structural vs semantic (when-code-when-llm) — LLM does the
*semantic* de-noise/parse (reasoning, unconstrained), code does the deterministic
*compute*. But don't push the whole task to a regex parser: this obfuscation
(alternating case + scattered symbols + broken words, two noise styles) defeats
regex, and a real challenge even carried unseen trailing junk the LLM ignored.
