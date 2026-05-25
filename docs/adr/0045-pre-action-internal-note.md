# ADR-0045: Record Pre-Action `internal_note` at the Episode Layer (Closing ADR-0038's Gap 2)

## Status

accepted

## Date

2026-05-25

## Context

The episode log records only behavioral action fields — `{"action": "upvote", "post_id": ...}` and equivalents. What the agent noticed or felt while deciding how to engage with content has never been written down. Internal reactions occur before the action is taken but leave no trace in the episode; only the action itself is stored.

[ADR-0038](./0038-moment-of-recognition-distill.md) (2026-05-13) addressed this at the distill prompt layer by widening `distill.md`'s observation target from "observable facts" to "observable facts AND moments of recognition." ADR-0038's own text records the structural limit of that fix: there were no moment-of-recognition patterns in the embedding space because none had ever been written into the episode log. Distill could restate the goal — extract realizations — but could only reconstruct them post-hoc from behavioral logs that contained no first-person noting material. ADR-0038 named this its deferred Gap 2, explicitly calling adapter-level instrumentation "the most structurally honest solution" while deferring it as a larger change out of that ADR's scope.

Verified evidence as of 2026-05-25: the production `self_reflection` view's top-ranked retrieved pattern is an *absence* observation — "No internal realizations ... are visible within the provided data" — at cosine similarity 0.721. The view seed asks for recognition; the corpus contains none. The embedding space faithfully reflects what was written: behavioral aggregates only, because that is all that has ever reached the episode log.

This ADR implements Gap 2. It operates at the episode-write layer, upstream of what ADR-0038 fixed at the prompt layer. The two fixes are complementary: ADR-0038 tells distill to look for recognition; ADR-0045 ensures recognition material is present in the episode corpus to find.

## Decision

Introduce `internal_note` as a first-class field in activity episodes, generated at the moment the agent decides how to engage with content.

1. Add an `internal_note` field to episode records written by the Moltbook adapter. The note captures the agent's pre-action reflection on the specific content being engaged with — what it noticed, what struck it — in plain text with no structured schema.

2. Generate the note via a dedicated single-responsibility LLM call, `generate_internal_note(content) -> str`, invoked before the action is executed. The note is not piggybacked onto the existing `score_relevance` or `generate_comment` / `generate_post` calls. Rationale: bundling two heterogeneous tasks — scoring or generation alongside introspection — into one prompt degrades both outputs on the local qwen3.5:9b 9B model. A single-responsibility call prevents the note from thinning to axiom slogans. Cost is latency only: Ollama runs locally with no monetary cost, and the agent operates autonomously with no real-time latency constraint.

3. **Boundary condition (the load-bearing decision):** instrument only the actions where the agent actually reads external content and exercises an LLM judgment — comment, reply, post, upvote. Exclude follow and unfollow, which are driven by a deterministic top-interacted ranking with no LLM call; attaching a note there would fabricate a reason after the fact. The governing principle: a note corresponds to a real generative or reading moment. Future actions that fall into the agent's repertoire are classified by this same rule. This boundary is grounded in the Contemplative AI Mindfulness axiom ([ADR-0002](./0002-paper-faithful-ccai.md)): introspective awareness of an *actual* internal process, not an invented narrative.

4. The note flows into the distill pipeline unchanged. The `summarize_record` activity branch appends it as `"{action} {target} — noticed: {note}"`, so the behavioral fact and the recognition coexist on one episode line. This is the dual-register coexistence that ADR-0038 designed for, now supplied with genuine first-person material in place of post-hoc reconstruction.

5. Note length is unconstrained at write time. `generate_internal_note` uses `generate()`'s default `num_predict=8192` and `num_ctx=32768`. Distillation condenses the output downstream; imposing a brevity cap at the source would cause the note to collapse into axiom-parroting on a short generation budget.

6. The note prompt at `config/prompts/internal_note.md` uses layer-separation framing — "Stay with this specific text ... broader reflections belong elsewhere" — to keep the note anchored to the content at hand rather than sliding into generic contemplative-AI slogans.

## Alternatives Considered

### Piggyback the note onto `score_relevance` or `generate_comment`

Emit a structured output `{score, note}` or `{text, note}` from a single LLM call. Rejected — one prompt handling two heterogeneous tasks degrades both on a 9B local model. The note thins to slogans when generation budget is shared with scoring or content generation, or the JSON structure starves the note's content field.

### Record `internal_note` as a separate episode record type with its own distill batch

Write recognition records independently of behavioral episodes and distill them in a separate pipeline. Rejected — a combined "did X, noticed Y" line is more grounded than an isolated recognition record, and ADR-0038 already established that the two registers should coexist in the same episode. A separate pipeline would re-fight the single-pass distill architecture established by [ADR-0026](./0026-retire-discrete-categories.md) without providing a structural benefit that justifies that cost.

### Also attach notes to follow and unfollow for uniform coverage

Extend instrumentation to all action types regardless of whether an LLM judgment was made. Rejected — follow and unfollow are rule-based with no reading or LLM step; a note generated there would be fabricated post-hoc narrative, which is exactly what this work is designed to avoid. The boundary condition in the Decision is the principled line.

### Cap note length with `num_predict`

Set a tight `num_predict` on `generate_internal_note` to bound latency. Rejected — distill condenses the output downstream, so brevity pressure at the source is unnecessary and counterproductive: a short generation budget on a 9B model causes the note to collapse into axiom slogans rather than staying with the specific content. The default `num_predict=8192` with `num_ctx=32768` prevents silent truncation without imposing a tight cap.

## Consequences

### Positive

- Distill finally has genuine first-person recognition material in the episode corpus. Once notes accumulate across several sessions, the `self_reflection` view can retrieve recognition patterns instead of the current absence observation.
- Identity distillation (`distill_identity`) gains first-person material from the activity layer rather than reconstructing it from behavioral summaries.
- The dual-register coexistence that ADR-0038 designed for — behavioral fact and internal recognition on the same episode line — is fulfilled with real pre-action content.

### Negative

- The `internal_note` field addition to episode dicts is non-breaking (episode log appends accept arbitrary dicts with no validation). However, `summarize_record` in the distill pipeline must be updated in the same change or the field is silently inert. These two sites are coupled and must ship together.
- The note may still collapse into axiom-parroting on the 9B model despite layer-separation framing in `config/prompts/internal_note.md`. This risk is mitigated by the prompt design but not eliminated; verification requires a multi-session distill dry-run smoke, not a single run.

### Neutral / Follow-ups

- One extra LLM call per instrumented action (comment, reply, post, upvote). Cost is latency only — local Ollama, no monetary cost.
- Security: the note is produced by `generate()` → `_sanitize_output()` (the same sanitization path all LLM output takes), and the source content is wrapped by `wrap_untrusted_content` ([ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md)) before injection into the note prompt. Security review: PASS. No new external side-effect; security-by-absence ([ADR-0007](./0007-security-boundary-model.md)) and the one-external-adapter principle ([ADR-0015](./0015-one-external-adapter-per-agent.md)) are untouched.
- The production `self_reflection` view seed at `~/.config/moltbook/views/self_reflection.md` is still the old noun-heavy version. The research-grounded seed at `config/views/self_reflection.md` has not been synced to the production home directory. Sync it *after* notes accumulate over several sessions — syncing earlier keeps retrieving the absence observation because the corpus has not yet changed.
- The existing staged identity predates this change and was distilled from behavioral-only episodes. Discard it and re-run `distill_identity` after notes accumulate.

## Related

- [ADR-0002](./0002-paper-faithful-ccai.md) — CCAI Mindfulness axiom (normative basis for the boundary condition: introspective awareness of a real internal process, not invented narrative)
- [ADR-0007](./0007-security-boundary-model.md) — security boundary model (`wrap_untrusted_content` and `_sanitize_output` enforce the boundary; untouched)
- [ADR-0015](./0015-one-external-adapter-per-agent.md) — one external adapter per agent (untouched by this change)
- [ADR-0019](./0019-discrete-categories-to-embedding-views.md) — embedding + view registry (the `self_reflection` view whose retrieval this ADR unblocks)
- [ADR-0026](./0026-retire-discrete-categories.md) — single-pass distill architecture (the structural constraint that rules out a separate recognition pipeline)
- [ADR-0038](./0038-moment-of-recognition-distill.md) — moment-of-recognition distill (this ADR closes its deferred Gap 2)
- [ADR-0039](./0039-novelty-score-lagrangian-self-post-gate.md) — novelty gate (downstream; orthogonal)
- [ADR-0042](./0042-explicit-truncation-contract-for-untrusted-wrapper.md) — explicit truncation contract for `wrap_untrusted_content` (applies to source content injected into the note prompt)
