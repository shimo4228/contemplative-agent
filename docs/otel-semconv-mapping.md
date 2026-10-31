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
Three kinds of row share the file. Generation and embedding rows are told
apart by `caller`; decision rows
([ADR-0112](adr/0112-decision-backend-seam-and-shadow-skill-decision.md)) carry
`kind: "decision"`, the one key the other two do not have, and a row without
`kind` is therefore not a decision row. A decision row describes one
`decide()` BATCH rather than one call — `question_count` / `answered_count`
say how many questions it covered and `decision_reason` names the batch
verdict from the closed vocabulary (`answered` only when every question
answered, otherwise the first non-answered reason). Its `num_predict` is
always 1 and its `temperature` always 0, the readout's own settings. The two
kinds by `caller` are: generation rows
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
| `kind` (`"decision"`, absent on generation and embedding rows) | no semconv equivalent → `ca.audit.*` |
| `decision_reason`, `question_count`, `answered_count` (one `decide()` batch, ADR-0112) | no semconv equivalent → `ca.audit.*`; the batch is not a `gen_ai` call and `error.type` would flatten nine named abstains into one |
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

This document is the **canonical table for all three audit logs**: the
`llm-calls` rows above (generation, embedding and decision row kinds), and the
verification-audit and api-audit rows and the exclusion list below
([ADR-0078](adr/0078-otel-connection-via-vocabulary-and-offline-export.md)
addendum of 2026-10-24). The last three were copied once, on 2026-10-31, from
the frozen sibling
[contemplative-agent-otel `docs/mapping.md`](https://github.com/shimo4228/contemplative-agent-otel/blob/main/docs/mapping.md),
which is a frozen copy of the v2.10.0 schema; this repository updates them from
then on, in the same change as the producer.

### `verification-audit.jsonl` → span `captcha solve` (INTERNAL, zero-width)

Written by `adapters/moltbook/verification.py`. The log records no duration, so
the span is zero-width (`end == start`): an estimated width would be fabricated
latency. The challenge text's fields come from `core/_io.py`'s bounded-text
helper (`challenge_sha256` over the full text, `challenge_bytes`,
`challenge_truncated`, `challenge_encoding`, and `challenge_b64`, which is
excluded below).

| audit log field | OTel attribute | Note |
|---|---|---|
| `challenge_sha256` | `ca.audit.challenge_sha256` | |
| `challenge_bytes` | `ca.audit.challenge_bytes` | |
| `challenge_truncated` | `ca.audit.challenge_truncated` | |
| `challenge_encoding` | `ca.audit.challenge_encoding` | |
| `verification_code_sha256` | `ca.audit.verification_code_sha256` | |
| `answer` | `ca.audit.answer` | agent-generated two-decimal string |
| `solver_path` | `ca.audit.solver_path` | `code_parse` / `llm_extract` / `llm_reason` / `none` |
| `solve_success` / `verify_success` | `ca.audit.solve_success` / `ca.audit.verify_success` | |
| `error` (when `verify_success == false`) | `error.type` | classification only (`http_400`, `abstain`, …); the body is dropped |

### `api-audit.jsonl` → span `{method} {endpoint}` (CLIENT, zero-width)

| audit log field | OTel attribute | Note |
|---|---|---|
| `method` | `http.request.method` | stable HTTP semconv |
| `endpoint` | `url.template` | already normalized (`GET /posts/{id}`) |
| `status` | `http.response.status_code` | |
| `transport_error` / `status` | `error.type` | exception class name, or status code as string |
| `rate_remaining` | `ca.audit.rate_remaining` | |
| `success` / `soft_fail` | `ca.audit.success` / `ca.audit.soft_fail` | |
| `retried` / `retry_attempt` / `retry_max` / `retry_after_s` | `ca.audit.retried` / … | 429 retry decisions |
| `drift_missing` | `ca.audit.drift_missing` | schema-drift detection (missing envelope keys) |
| `content_status.*` | `ca.audit.content_status.*` | scalars only (bool / int / float); server strings are dropped |

### Excluded fields

| Field | Reason |
|---|---|
| `challenge_b64` (verification) | Attacker-controlled text. The audit log keeps it (base64 + sha256) because offline replay needs the raw input; a trace viewer does not, and rendering it would move untrusted text across a trust boundary. There is no flag to include it |
| `error` bodies (verification, api) | Server-controlled free text (full response JSON). Reduced to a categorical `error.type` |
| `keys` (api) | Response envelope key listing; low signal for traces (drift already surfaces as `drift_missing`) |
| string values inside `content_status` | Server-controlled free text |

The rule behind the list is the retention difference above: an off-host export
carries hashes and categorical codes only.

> **Consumer lag (2026-08-16, permanent under the freeze).** The frozen converter loads every row of
> `llm-calls-*.jsonl` as one record type with no `caller` discriminator, so it
> currently exports embedding rows as `text_completion` spans and drops
> `batch_size` / `input_chars` / `rows`. Producer and consumer are out of step
> until the converter learns the second row kind; any per-day count taken over
> this file in the meantime must filter on `caller` to avoid mixing the two
> populations.
