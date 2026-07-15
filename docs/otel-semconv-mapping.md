# OpenTelemetry GenAI Semantic-Conventions Mapping

How this project's replayable audit logs ([ADR-0075](adr/0075-observability-by-default.md))
correspond to the [OpenTelemetry GenAI semantic conventions](https://github.com/open-telemetry/semantic-conventions-genai).
The project does **not** run OpenTelemetry ([ADR-0078](adr/0078-otel-connection-via-vocabulary-and-offline-export.md)
maintains ADR-0075's rejection); this document is the zero-dependency
vocabulary layer that lets outside tooling and readers interpret the logs
through a standard vocabulary.

> **Status caveat.** The GenAI conventions are **Development** status
> (2026-07). Attribute names here may change before they stabilize.

## Core mapping — `llm-calls-{date}.jsonl`

Written by `core/llm.py:_emit_telemetry` (one record per LLM call).

| audit log field | OTel attribute |
|---|---|
| `model` | `gen_ai.request.model` |
| `prompt_eval_count` | `gen_ai.usage.input_tokens` |
| `eval_count` | `gen_ai.usage.output_tokens` |
| `done_reason` | `gen_ai.response.finish_reasons` |
| `num_predict` | `gen_ai.request.max_tokens` |
| `temperature` | `gen_ai.request.temperature` |
| `error_kind` ([ADR-0077](adr/0077-chaos-tdd-fault-injection.md) fault classes) | `error.type` |
| `ts` + `duration_ms` | span start / end |
| `caller`, `prompt_sha256`, `think`, `cached_tokens`, … | no semconv equivalent → custom `ca.audit.*` namespace |

The fields with no standard equivalent are exactly the research-replay
fields: `caller` keys the replay corpus by pipeline stage, `prompt_sha256`
is a content key without content. What the standard cannot express is a
useful description of what ADR-0075 logs that ops telemetry does not.

## Retention-policy difference (deliberate, both directions)

- GenAI conventions: prompt/completion content is **not recorded by
  default** (opt-in) — traces are consumed by operators in UIs.
- ADR-0075 logs: raw untrusted inputs are **always stored** (base64 +
  sha256) — the replay corpus needs the exact bytes the decision saw.

Same events, different consumers, opposite retention choices. When
converting logs to traces, the conversion therefore drops untrusted bodies
and keeps hashes + categorical codes only.

## Canonical field-by-field table

The full mapping (verification-audit, api-audit, exclusion list and
rationale) lives next to the code that implements and tests it:
[contemplative-agent-otel `docs/mapping.md`](https://github.com/shimo4228/contemplative-agent-otel/blob/main/docs/mapping.md)
— the offline JSONL→OTLP converter ([ADR-0078](adr/0078-otel-connection-via-vocabulary-and-offline-export.md)).
