# ADR-0047 sampling probe: the fixed axiom suite and the five profile runs (qwen3.5:9b, 2026-05-30)

- `sampling/comment_suite.jsonl` — the four introspective posts, one per axiom, that [ADR-0047](../../adr/0047-comment-sampling-temperature.md) generated replies to. Later reused as the input of the [ADR-0068](../adr-0068/gemma-e4b-think-ab-20260628.md) think A/B and as the seed of `evals/datasets/comment_golden.jsonl` ([ADR-0089](../../adr/0089-llm-behavioral-eval-layer-on-deepeval.md)).
- `sampling/results/{base,temp-13,temp-15,topk-open,topk-open-minp}.json` — one file per sampling profile (`params`, `model`, the suite, every sample). The findings in ADR-0047's body come from them. The probe harness that wrote them was deleted on 2026-08-29; `git show a06c6be^:tests/sampling_probe.py` restores it.

Moved here from `tests/fixtures/sampling/` on 2026-10-31 (P1-04.7): no test read them, and they are the evidence of a decision, not test input. Whether the four posts are real or synthetic is not recorded; `docs/security/threat-model.md` row R5 (b) treats them as real until a manifest says otherwise.
