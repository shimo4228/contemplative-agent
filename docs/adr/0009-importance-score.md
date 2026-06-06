# ADR-0009: KnowledgeStore Importance Score

## Status
accepted

> **Reinterpreted by [ADR-0053](0053-importance-encoding-time-significance.md) (2026-06-06).** The two roles this ADR assigned to the score have since dissolved: the retrieval-weight role (ADR-0019 moved retrieval to embedding views; ADR-0051 left ranking pure cosine) and the "Phase 2 quality gate" foundation (the admit gate was realized as a separate mechanism, ADR-0026/0027). The decay design and write-once stance remain in effect. See ADR-0053 for the current meaning (encoding-time significance) and propagation map.

## Date
2026-03-24

## Context

KnowledgeStore had accumulated 240 patterns, and `get_context_string(limit=100)` was unconditionally injecting the latest 100 into the prompt. Problems:

1. **No metadata**: Patterns lacked importance, relevance, keywords, etc. — retrieval was limited to chronological order
2. **Burial of old valuable patterns**: As pattern count grew, older important patterns fell outside the top 100 and were never used again
3. **Noise**: Not all 100 patterns were relevant to the current task, degrading prompt quality
4. **`_parse_json()` field loss**: Additional fields like `source` were discarded during load

Prior research (Generative Agents' recency × importance × relevance triple score, A-MEM's Zettelkasten-style memory, Mem0's ADD/UPDATE/DELETE classification) all employ importance-based retrieval.

## Decision

Introduce an importance score for KnowledgeStore patterns and change prompt injection from "latest N" to "top-K by importance."

### Pattern Schema Extension

```json
{
  "pattern": "learned pattern",
  "distilled": "ISO timestamp",
  "importance": 0.8,
  "source": "2026-03-18~2026-03-19",
  "last_accessed": "ISO timestamp"
}
```

### Importance Assignment

- LLM rates 1–10 during distillation → normalized to 0.0–1.0
- DISTILL_REFINE_PROMPT modified: `{"patterns": [{"text": "...", "importance": N}, ...]}`
- Fallback for legacy format (string arrays): importance defaults to 0.5

### Time Decay (lazy)

```
effective_importance = importance * (0.95 ^ days_since_distilled)
```

- Calculated at read time. Stored importance is immutable
- Original LLM rating is preserved for debugging and analysis

### Retrieval Method

- `get_context_string(limit=50)`: top-50 by effective_importance
- Default limit changed from 100 → 50

### Backward Compatibility

- Existing patterns without importance → default 0.5 assigned at load time
- `_parse_json()` fixed to preserve `source`, `importance`, `last_accessed`

## Alternatives Considered

1. **Post-hoc scoring (re-evaluate all patterns)**: Rejected. Evaluation accuracy is low without the episode context available during distillation
2. **Ollama `format` parameter for structured output**: Rejected. Confirmed in ADR-0008 — constrained decoding degrades content quality
3. **Recency-only ranking**: Rejected. A pattern's value is not determined by recency alone
4. **Embedding-based retrieval**: Phase 3 candidate. Currently requires adding a dependency (sentence-transformers), which is overkill

## Consequences

- knowledge.json schema is extended (backward compatible)
- Distillation result quality becomes visible through importance scores
- Old low-quality patterns naturally rank down, improving prompt quality
- Lays the foundation for future Phase 2 (distillation quality gate) and Phase 3 (keyword search)
- `last_accessed` field provides the basis for a recency score (future triple scoring)

## Calibration History

### 2026-04-17 — SIM_DUPLICATE 0.92 → 0.90

The embedding dedup threshold `SIM_DUPLICATE` was lowered from 0.92 to 0.90.

Reason: the live 97-pattern corpus had max pairwise cosine = 0.8980 (see [evidence/adr-0009/threshold-calibration-20260417.md](../evidence/adr-0009/threshold-calibration-20260417.md)). The 0.92 threshold never fired, leaving the SKIP branch vacuous. 0.90 keeps the branch ready to fire when duplicates emerge while preserving the SIM_UPDATE=0.80 zone intact (0.88 would have pulled the current max into SKIP and compressed the UPDATE band).

The SKIP log level was also promoted from `debug` to `info` so SKIP events are visible in normal operation for monitoring.
