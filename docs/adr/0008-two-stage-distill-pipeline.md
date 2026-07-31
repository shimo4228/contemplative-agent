# ADR-0008: Two-Stage Distill Pipeline

## Status

accepted

## Date

2026-03-22

## Context

When the 9B model (qwen3.5:9b) was asked to perform both "extract patterns from episodes" and "format as JSON" in a single generate() call, it either produced hollow content or broken formatting. Distill success rate was 2/10; identity distill output was corrupted every time.

## Decision

Split a single generate() call into two stages:

- **Step 1**: Free-form output (no constraints; full capacity devoted to the creative task)
- **Step 2**: Summarize + format (takes Step 1 output as input; a mechanical transformation task)
- **Step 3**: `_is_valid_pattern()` quality gate (rejects patterns under 30 characters or 4 words)

Identity distill follows the same structure (Step 1 uses `get_default_system_prompt()` to prevent identity double-injection).

## Alternatives Considered

Full trial-and-error record:

1. **Few-shot examples** → Degraded quality (context pressure reduced body text quality) → Reverted
2. **Ollama `format` parameter (constrained decoding)** → Structure was 100% guaranteed but content was hollow → Removed from distill
3. **Quality gate only** → Did not solve the `- ` parser corruption issue
4. **Two-stage + `format`** → Step 2 returned empty responses (`{}` escaping oversight)
5. **Two-stage without `format` + quality gate** → Adopted as the final solution

## Consequences

- Distill success rate: 2/10 → 12/16
- Identity distill: consistently broken → stable 3-paragraph plain text
- Batch size is 30 (50 is too heavy); Ollama timeout is 600s (processing time doubled with two stages)
- `format` parameter remains in generate() but is not used for distill/identity distill
- **Key Insight**: Constrained decoding guarantees structure but sacrifices content quality. Applying control at the wrong stage degrades the target. Control should be applied at save time, not generation time
