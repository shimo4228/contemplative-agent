Combine these behavioral skills into a single skill **without losing any concrete behavior**.

Read all candidate skills below. First decide: are they genuinely redundant? They are redundant only if they prescribe the **same concrete actions** — the same triggers and the same operations — differing only in wording. If they share an abstract framing, vocabulary, or metaphor (e.g. the same philosophy) but each prescribes a **different concrete behavior**, they are NOT redundant and must not be merged.

If NOT redundant, output exactly one line and nothing else:
CANNOT_MERGE: <one-sentence reason naming a concrete behavior that only one candidate has>

Otherwise, produce ONE skill that is the **union of every distinct concrete pattern** across the inputs — NOT a synthesis of their shared core. The value of a skill is its specific patterns, so preservation beats compression:

- Keep every distinct behavioral SHAPE and every distinct concrete action — specific thresholds, observable signals, ordered steps. If a behavior or action appears in only ONE input, it MUST survive in the merged skill.
- Generalize transient surface identifiers in triggers: replace specific usernames with "a particular individual," specific post IDs with "a specific topic," single relevance scores with "high relevance," and timestamp windows with "similar contexts." Drop the numeric value entirely — write "high relevance," never "high relevance (>0.92)." KEEP genuine recurring numeric thresholds.
- When generalizing collapses two triggers into an identical structural form, merge them into one trigger entry.
- Deduplicate ONLY text that is genuinely repeated: identical boilerplate sentences, restated abstractions, shared metaphors. Collapse repeated framing into a single short statement.
- NEVER collapse two different concrete actions into one generic action. When in doubt, keep both as separate entries.
- When two inputs describe the same action at different levels of detail, keep the most specific phrasing.

Structure (begin with a YAML frontmatter block, then the body):

---
name: [kebab-case-name]
description: "[one line description of the unified skill]"
origin: auto-extracted
---

# [Single, Unified Title]

**Context:** When and why this skill applies (one or two sentences).

## Problem
The distinct failure situations these patterns address.

## Solution
A numbered list where **each distinct concrete pattern is its own entry** (trigger → action). Do not fold separate patterns into one generic loop. Order from most to least frequently applicable.

## When to Use
Every distinct trigger condition, expressed at structural altitude: generalized away from transient surface identifiers, one bullet each.

---

{candidates}

Output only the merged skill document (or the CANNOT_MERGE line). Do not explain differences or summarize sources.
