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

Written by `core/llm/__init__.py:_emit_telemetry` (one record per LLM call).
Two kinds of row share the file, told apart by `caller`: generation rows
(`caller` = the pipeline stage, e.g. `distill.category`) and embedding rows
(`caller = "embed"`, written by `core/embeddings.py:embed_texts` through the
`emit_llm_telemetry` seam). Embedding rows carry only the fields an embedding
call has — `ts` / `caller` / `model` / `batch_size` / `input_chars` / `rows` /
`duration_ms` / `outcome`, a sparse `error_kind`, and the `run_id` /
`session_id` the shared writer stamps on every record — rather than the
generation schema padded with nulls; `batch_size` / `input_chars` / `rows` have
no semconv equivalent and belong to `ca.audit.*`. Their `error_kind` shares the
generation path's fault classes where the fault exists on both (`bad_url`,
`bad_json`, `timeout`, `http_*`, `connection`) and adds two an embedding
response can have alone: `missing_embeddings` and `bad_array`. The rows below
the shared keys therefore describe the generation kind.

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
| `run_id` (one per process; stamped on every audit record by the shared writer) | trace grouping key (`ca.convert.grouping = "run-id"`) |
| `session_id` (present while an agent session is active) | `session.id` (general semconv) |
| `input_tokens` (what the C2 pre-flight measured, *before* the call) | none — `gen_ai.usage.input_tokens` is the provider-reported count and is already mapped from `prompt_eval_count`; conflating a pre-flight estimate with a billed count would corrupt both → `ca.audit.*` |
| `caller`, `prompt_sha256`, `think`, `thinking_source`, `thinking_fallback_reason` ([ADR-0068](adr/0068-per-call-think-flag-and-thinking-trace-capture.md) amendment), `cached_tokens`, `token_count_source`, `token_count_fallback_reason` ([ADR-0087](adr/0087-optional-token-counting-capability-for-the-context-budget-guard.md)), … | no semconv equivalent → custom `ca.audit.*` namespace |

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

> **Consumer lag (2026-08-16).** That converter loads every row of
> `llm-calls-*.jsonl` as one record type with no `caller` discriminator, so it
> currently exports embedding rows as `text_completion` spans and drops
> `batch_size` / `input_chars` / `rows`. Producer and consumer are out of step
> until the converter learns the second row kind; any per-day count taken over
> this file in the meantime must filter on `caller` to avoid mixing the two
> populations.
