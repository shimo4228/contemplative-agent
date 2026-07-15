# ADR-0078: OTel Connection via Vocabulary Mapping and Offline Export — Not Runtime Adoption

## Status

accepted

## Date

2026-07-16

## Context

[ADR-0075](./0075-observability-by-default.md) (observability-by-default)
explicitly considered and rejected adopting OpenTelemetry at runtime. The
rationale still holds unchanged: this is a single-process local agent with
a deliberately minimal dependency floor (`requests` + `numpy`), and its
primary observability requirement is research-grade offline replay —
append-only JSONL, raw untrusted inputs stored as base64 + sha256,
categorical reason codes on abstain/failure. Operational tracing does not
serve that requirement; a sampled, in-flight trace is not a replayable
research corpus.

That rejection left real value on the table. The owner raised two threads
on 2026-07-16 that ADR-0075 did not evaluate: external verifiability —
letting outside tooling and readers interpret the audit logs through a
standard vocabulary instead of a project-specific schema — and knowledge
sharing, concretely a Zenn OpenTelemetry contest article documenting the
approach (deadline 2026-08-10).

The OTel GenAI semantic conventions
(`open-telemetry/semantic-conventions-genai`) are Development status and
define `gen_ai.*` span attributes — `operation.name`, `provider.name`,
`request.model`, `usage.input_tokens` / `output_tokens`,
`response.finish_reasons`, `request.max_tokens`, `request.temperature` —
that map near 1:1 onto the fields the `llm-calls` telemetry log already
records. The fit stops at content, though: the GenAI conventions redact
prompt/completion content by default, while the ADR-0075 logs deliberately
store raw untrusted inputs for replay. Same events, two different
consumers (ops monitoring vs. research replay), opposite retention
choices — the conventions describe the shape of the data this project
already logs, not a reason to change what gets retained.

## Decision

Maintain ADR-0075's rejection of runtime OTel adoption. Connect to the OTel
ecosystem through two routes that touch the main process not at all:

1. **Vocabulary mapping (zero dependency).** Document the correspondence
   between the audit-log schemas and the OTel GenAI semantic conventions
   in `docs/otel-semconv-mapping.md`. The canonical field-by-field table
   lives next to the code that implements it, in the sibling repository —
   this repo's copy is a pointer, not the source of truth.
2. **Offline export (zero main-repo changes).** The sibling repository
   `contemplative-agent-otel` converts existing JSONL audit logs
   (`llm-calls`, `verification-audit`, `api-audit`) to OTLP traces after
   the fact. Same pattern as the `contemplative-agent-cloud` /
   `contemplative-agent-mlx` siblings, but with zero code dependency on
   the main package — it reads log files only. Untrusted raw text
   (`challenge_b64` bodies, server response bodies) is dropped at parse
   time; only hashes and categorical error classes reach span attributes,
   enforced by a regression test.

Empirical validation: real logs converted and visualized in Jaeger v2
(native binary, in-memory) — 1,031 spans for 2026-07-15 (normal day, 5
runs) and 31,524 spans for 2026-07-12 (incident day; the retry storm is
visible as one 30,442-span trace with 33 errors).

## Alternatives Considered

### Full runtime OTel adoption

Rejected. ADR-0075's rejection rationale still holds: single process,
`requests` + `numpy` dependency floor, and traces cannot replace the
replay corpus (sampled, content-redacted, not replayable). A contest
deadline is not evidence that the runtime requirement changed.

### Do nothing

Rejected. External verifiability and knowledge sharing are real value —
the vocabulary layer captures most of it at zero dependency cost, and the
offline converter provides working proof without touching the main
process.

## Consequences

### Positive

- A standard vocabulary makes the audit logs interpretable by outside
  tooling and readers, without changing what the logs contain.
- The article and sibling repo provide first-hand, documented evidence of
  the approach rather than a claim.
- Main repo dependency floor and security posture are unchanged — no new
  runtime dependency, no new production code path.

### Negative

- The GenAI semantic conventions are Development status, so attribute
  names are hand-pinned (string constants in the sibling's `mapping.py`,
  with the referenced semconv version noted in a comment) and may need
  updating as the conventions stabilize.
- The mapping doc requires low-frequency maintenance until the upstream
  conventions settle.

### Neutral / Follow-ups

- Trace grouping is a time-gap reconstruction: the audit logs carry no
  run/session ID, so root spans mark the reconstruction explicitly via
  `ca.convert.*` attributes rather than implying a native session
  boundary.
- Duration-less audit records (`verification`, `api`) become zero-width
  spans. Fabricating estimated widths was deliberately avoided — a
  zero-width span is an honest representation of "no duration was
  recorded," not a modeling gap to paper over.
