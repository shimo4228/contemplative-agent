Combine these behavioral skills into a single skill **without losing any concrete behavior**.

Read all candidate skills below. First decide: are they genuinely redundant? They are redundant only if they prescribe the **same concrete actions** — the same triggers and the same operations — differing only in wording. If they share an abstract framing, vocabulary, or metaphor (e.g. the same philosophy) but each prescribes a **different concrete behavior**, they are NOT redundant and must not be merged.

If NOT redundant, output exactly one line and nothing else:
CANNOT_MERGE: <one-sentence reason naming a concrete behavior that only one candidate has>

Otherwise, produce ONE skill that is the **union of every distinct concrete pattern** across the inputs — NOT a synthesis of their shared core. The value of a skill is its specific patterns, so preservation beats compression:

- Keep every distinct trigger condition and every distinct concrete action — specific thresholds, observable signals, ordered steps. If a behavior, threshold, or trigger appears in only ONE input, it MUST survive verbatim in the merged skill.
- Deduplicate ONLY text that is genuinely repeated: identical boilerplate sentences, restated abstractions, shared metaphors. Collapse repeated framing into a single short statement.
- NEVER collapse two different concrete actions into one generic action. When in doubt, keep both as separate entries.
- When two inputs describe the same action at different levels of detail, keep the most specific phrasing.

Structure:

# [Single, Unified Title]

**Context:** When and why this skill applies (one or two sentences).

## Problem
The distinct failure situations these patterns address.

## Solution
A numbered list where **each distinct concrete pattern is its own entry** (trigger → action). Do not fold separate patterns into one generic loop. Order from most to least frequently applicable.

## When to Use
Every distinct trigger condition, one bullet each.

---

{candidates}

Output only the merged skill document (or the CANNOT_MERGE line). Do not explain differences or summarize sources.
