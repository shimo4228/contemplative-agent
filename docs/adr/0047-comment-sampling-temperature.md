# ADR-0047: Higher Sampling Temperature for Outward Comment Generation

## Status

accepted

## Date

2026-05-30

## Context

All LLM tasks share one hardcoded sampling profile (`core/llm.py`: `temperature 1.0`, `top_p 0.95`, `top_k 20`). Comment / reply / post generation opens with formulaic, sycophantic stock phrasings — "What a beautiful moment…", "This is a profound observation…", "There is a quiet…" — that barely vary across random seeds.

The goal was to test, on the live model, whether sampling alone could break this without touching weights. A standalone probe harness (`tests/sampling_probe.py`) was built: it calls Ollama `/api/generate` directly (the production `generate()` discards the response's `eval_count` / `eval_duration`, so tok/s and token counts are unrecoverable through it). The fixed suite is four introspective posts — one per contemplative axiom (Emptiness / Non-Duality / Mindfulness / Boundless Care) — generating replies, three seeds each, varying one sampling variable at a time.

## Decision

Comment-generation paths (`generate_comment` / `generate_reply` / `generate_cooperation_post`) use `temperature 1.3` (`COMMENT_TEMPERATURE`). Scoring, title, internal-note, distill, and every other path keep the `1.0` default.

Implemented as a `temperature` argument (default `1.0`) on `generate()` / `generate_for_api()`, carried in the Ollama `options`. The `LLMBackend` protocol is intentionally unchanged — temperature reflects on the Ollama path only; a `logger.debug` fires if an injected backend is handed a non-default temperature. Rollback is reverting the `COMMENT_TEMPERATURE` constant (one line).

## Alternatives Considered

### Widen the candidate set (top_k / top_p / min_p) — rejected

Probe result: opening `top_k 20→0`, opening `top_p 0.95→1.0`, and adding `min_p 0.05` did **not** raise opening diversity (11/12 → 10/12 → 9/12 unique first-3-words) and left the stock openings intact. A 109-agent, evidence-graded deep-research pass confirmed the structural reason: in Ollama, DRY and XTC samplers are not exposed, and Qwen3.5's Go runner silences repetition penalties (`repeat_penalty` is effectively `1.0`). The only live levers are `temperature / top_k / top_p / min_p`, and candidate-set pruning cannot dislodge a pattern that lives in the high-probability region.

### Lower distill to converge — rejected

Lowering temperature / top_k on distill does not shorten output (that is the job of the prompt and `num_predict`); it only kills the diversity of observations, accelerating the axiom-slogan thinning [ADR-0045](./0045-pre-action-internal-note.md) warns of. Distill's extractive paths belong on the diversity side, not the convergence side. Distill is left entirely unchanged.

### temperature 1.5 — rejected

Probe result: `1.5` broke openings most strongly but produced **axiom-label collapse** — the model began enumerating the four system-prompt axioms verbatim as headers (`1. Emptiness lens: … 2. Non-duality reflection: … 4. Boundless care core:`), with unstable output length (117–526 tokens) and emoji. This is the generation-side form of the axiom parroting [ADR-0045](./0045-pre-action-internal-note.md) flags. `1.3` breaks the openings while staying coherent and stable.

### Bake the profile into a Modelfile — rejected

The original plan was a `qwen-comment` Modelfile (`PARAMETER temperature 1.3`) with `ollama rm` as one-line rollback. But Ollama lets the API request `options` **override** Modelfile `PARAMETER`, and `core/llm.py` always sends `options`. A baked Modelfile would be silently ignored. The code path is the only one that works in this codebase.

### Add temperature to the backend protocol — rejected

Passing `temperature` into `LLMBackend.generate` would break existing backend implementations that lack the parameter. The backend stays unchanged; the dropped temperature is logged instead.

## Consequences

### Positive

- Comment / reply openings break their formulaic mold (validated live on comment and reply). Quality holds — outputs are more varied and no less coherent than the `1.0` baseline (e.g. `"Your pause was not a mistake; it was the work itself."` replacing `"What a beautiful moment of self-correction…"`).
- Backward compatible: default `1.0` leaves distill, scoring, title, internal-note, and every existing caller unchanged. 1078 tests pass.
- Zero distill risk — distill is untouched.

### Negative

- temperature reflects on the Ollama path only. An injected backend receives `1.0` regardless; a `logger.debug` makes this observable rather than silent.
- `cooperation_post` is given the same profile by parity with comment / reply (same outward reflective generation, same RLHF-baked openings). Its prose was not separately probed, though the temperature propagation is unit-tested.

### Neutral / Follow-ups

- **Speed is unchanged.** tok/s held at 7.3–7.4 across all profiles — generation speed is memory-bandwidth bound on this hardware, independent of sampling. The "shorter output → faster" path applies only to convergence tasks, which are out of scope here. Output-token counts were recorded but show no meaningful speed delta.
- **Sampling is now exhausted.** The stock-opening pattern is rooted in RLHF post-training mode collapse, with the chat template anchoring the opening (deep-research: Strong; consistent with the probe, where temp-1.5 still kept some openings). Ollama's lack of DRY/XTC closes the remaining sampling levers. Further gains must come from the prompt layer.
- **Future work (prompt layer, out of scope):** Verbalized Sampling (N-candidate generation, probability-mid selection; creative diversity 1.6–2.1× but unproven at 9B) and reframing negative constraints in positive form — a `"don't open with praise"` directive risks ironic rebound (deep-research: Strong), so the avoid-form is a landmine; use `"open with X"`.
- **Measured / dropped:** measured = prose samples, tok/s, output-token counts, opening diversity (eyeballed; the first-3-words distinct metric proved too blunt to capture the qualitative stock-opening rigidity — it stayed 11/12 while the openings visibly changed). Dropped = automated scoring, the Modelfile approach, any distill sampling change, thinking on/off.

### Security

No new external side effect. `temperature` is a float constant, not derived from external input; the `wrap_untrusted_content` / `_sanitize_output` boundary ([ADR-0007](./0007-security-boundary-model.md)) is unchanged. Security review: PASS.

## Related

- [ADR-0045](./0045-pre-action-internal-note.md) — axiom parroting / slogan thinning; the failure mode temp-1.5 reproduced on the generation side
- [ADR-0038](./0038-moment-of-recognition-distill.md) — moment-of-recognition distill; the diversity-preservation logic that kept distill out of scope
- [ADR-0018](./0018-per-caller-num-predict-embedding-stocktake.md) — `num_predict` derivation in `generate_for_api`, which this extends with `temperature`
- [ADR-0007](./0007-security-boundary-model.md) — security boundary model (unchanged)
