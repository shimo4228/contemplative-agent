# ADR-0068: Per-Call `think` Flag and Reasoning-Trace Capture to the Episode Log

## Status

accepted

## Date

2026-06-28

## Context

The LLM generation path hard-coded thinking **off** on every backend: the Ollama
payload sent `"think": False` ([`core/llm.py`](../../src/contemplative_agent/core/llm.py)
`_post_ollama`) and the MLX backend sent `chat_template_kwargs={"enable_thinking": False}`
([`core/mlx_backend.py`](../../src/contemplative_agent/core/mlx_backend.py)). There
was no way to enable a reasoning trace per call, and even if a model emitted one,
`_sanitize_output` → `_strip_thinking` discarded it and `generate()` returned only
the published text.

Two needs motivated a change. First, an upcoming **A/B comparison** of a thinking
model (Gemma 4 E4B think-on vs think-off vs the current think-off baseline) needs
think to be controllable per call **and** needs the think state recorded so the two
conditions are distinguishable in telemetry. Second, when thinking is on, the
reasoning **content** is research material worth keeping — but it must not land in
the per-call telemetry record (`logs/llm-calls-*.jsonl`), which is contractually
metadata-only ([ADR-0065](./0065-mlx-ondemand-launchd-and-telemetry-model-contract.md):
"never the prompt body"). Writing untrusted model output into that file would both
break the contract and create a second prompt-injection path when analysis sessions
read telemetry back.

The episode log already stores agent-generated content (comments, replies, posts)
and `internal_note` ([ADR-0045](./0045-pre-action-internal-note.md)) under the
established untrusted regime (direct-read forbidden; distilled artifacts consumed),
so it is the right home for the trace — a reuse of an existing artifact rather than
a new one.

## Decision

1. **Add a per-call `think: bool = False` parameter** threaded through `generate` →
   `_generate_full` → `_generate_impl` → `_post_ollama` / `_generate_via_backend`,
   and added to the `LLMBackend` Protocol's `generate()` keyword-only group.
   `MlxLmBackend` honors it via `chat_template_kwargs={"enable_thinking": think}`.
   Default False = the production behavior; no call site enables it in this change.

2. **Record `think` in telemetry as a boolean flag only.** The `tel` record gains a
   `"think"` field (metadata, like `model`/`temperature`); the trace *content* is
   never written there. This extends the ADR-0065 telemetry contract by one field
   and lets analysis tell think-on from think-off rows apart (e.g. for the A/B).

3. **Capture the trace and surface it through the publish seam.** A new frozen
   `GenerationOutput(text, thinking)` is returned by the shared core
   (`_generate_full`) and by `generate_for_api`. `generate()` keeps returning
   `Optional[str]` (projects to `.text`), so the 14 non-publish call sites are
   untouched. The trace is read from Ollama's dedicated `thinking` response field
   (or `BackendResult.thinking` / inline `<think>` fallback), secret-scrubbed
   (`_scrub_secrets`, extracted from `_sanitize_output`) but never `<think>`-stripped
   or length-capped, since it is stored, not published.

4. **Store the trace on the episode and render it in the report.** `generate_comment`
   / `generate_reply` / `generate_cooperation_post` and `ContentManager.create_*`
   return `GenerationOutput`; the publish paths (`feed_manager`, `reply_handler`,
   `post_pipeline`) attach a `thinking` field to the `comment` / `reply` / `post`
   `activity` episode beside `internal_note`. `report.py` renders it as a
   `**Thinking:**` block (URL-defanged like every other field; hidden when empty).

The trace is None under the default `think=False`, so episodes, reports, and
production behavior are unchanged until a caller opts in (deferred to the A/B
outcome).

## Alternatives Considered

### Write the trace content directly into the telemetry record

Rejected: violates the ADR-0065 metadata-only contract for `logs/llm-calls-*.jsonl`
and turns telemetry into a second untrusted-content store / injection path. The
boolean flag stays in telemetry; the content goes to the episode log.

### Create a new `logs/llm-thinking-*.jsonl` artifact

Single-responsibility-clean, but adds a new file and a new untrusted-content
lifecycle to manage when the episode log already stores agent-generated content
under an established trust regime. Reusing the episode log (the author's explicit
preference) is the lower-surface choice.

### Change `generate()` itself to return `(text, thinking)`

Rejected: it would break all 14 internal call sites that consume `Optional[str]`.
Limiting the return-type change to the publish seam (`generate_for_api` and the
comment/reply/post wrappers) confines the blast radius to the four paths that record
episodes.

## Consequences

### Positive

- Thinking is controllable per call and observable in telemetry, enabling the
  think-on/off A/B with distinguishable records.
- The reasoning trace is preserved as research material in the episode log and the
  comment report, under the existing untrusted regime, without a new artifact.
- The telemetry metadata-only contract and the trust boundary are both preserved
  (content never enters telemetry; trace is secret-scrubbed before persistence).
- Default-off means zero production behavior change until a deliberate opt-in.

### Negative

- `think` is a Protocol contract change: every `LLMBackend` implementer (incl. the
  sibling `contemplative-agent-cloud`) must accept the keyword to gain trace capture;
  until updated, an omitting backend would raise on the new kwarg (caught as a
  generation failure). In-repo backends and all test doubles were updated.
- The publish seam's return type changed (`Optional[str]` → `GenerationOutput`),
  which required updating the comment/reply/post wrappers, `ContentManager`, the
  three episode-recording call sites, and their tests.

### Neutral / Follow-ups

- No call site sets `think=True` yet; wiring comment generation to think (and any
  decision to adopt a thinking model) is deferred to the A/B outcome.
- The sibling `contemplative-agent-cloud` backend should add the `think` keyword and
  populate `BackendResult.thinking` to gain trace capture on the cloud path.
