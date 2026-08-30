# ADR-0069: Adopt gemma4:e4b as the Production Generation Model and Run the Value-Layer Pipelines think-ON

## Status

accepted

## Date

2026-06-28

## Context

[ADR-0068](./0068-per-call-think-flag-and-thinking-trace-capture.md) added a
per-call `think` flag and reasoning-trace capture but deliberately set no call
site to `think=True`, deferring "wiring … to think (and any decision to adopt a
thinking model)" to the A/B outcome. This ADR resolves that follow-up.

The think-on/off A/B ([`docs/evidence/adr-0068/`](../evidence/adr-0068/gemma-e4b-think-ab-20260628.md))
compared `gemma4:e4b` (think on/off) against the production baseline `qwen3.5:9b`
(think off) on comment generation. A cross-model blind judge ranked
gemma_think (6.50) > gemma_nothink (5.75) > qwen (4.75); gemma think-OFF was also
faster than baseline (0.65×), gemma think-ON slower (2.2×). gemma's context
length is 128K (`ollama show`), 4× the `NUM_CTX=32768` the pipelines request, so
the context-budget assumptions ([ADR-0066](./0066-backend-aware-context-budget-guard.md))
are unchanged. The model swap is therefore evidence-backed independent of think.

Two orthogonal decisions follow: which production model, and where (if anywhere)
to turn think on. The owner split the pipelines by execution mode and altitude:

- **Autonomous, latency-sensitive paths** (comment / reply / post generation; the
  scheduled `distill`) run unattended on launchd; added latency risks colliding
  with the session window and the 16 GB memory ceiling. Stability first.
- **Manually-invoked, behavior-change-upstream paths** (`insight`, `rules-distill`,
  `amend-constitution`, `distill-identity`, `skill-stocktake`, `rules-stocktake`)
  produce the value layers (skills / rules / identity / constitution) and run as
  human-invoked commands where generation latency is acceptable. The constitution
  in particular sits at the top of the behavior-change chain, so the quality
  upside of a reasoning pass is worth the cost there.

When think is on, the reasoning trace is research material worth keeping. The
content-action paths already store it on the episode log (ADR-0068), but the
value-layer pipelines write distilled artifacts, not episodes — they had no home
for a trace. Every value-layer command already writes a pivot snapshot
([ADR-0020](./0020-pivot-snapshots-for-replayability.md)) at run start; the snapshot directory is a
durable, per-run observability bundle co-located with the exact input state that
produced the run, which makes it the natural home for the output reasoning too.
`skill-stocktake` / `rules-stocktake` were the exception: they took no snapshot —
an oversight, since they audit the skill/rule corpus and are exactly the kind of
behavior-shaping run a snapshot exists to make reproducible.

## Decision

1. **Adopt `gemma4:e4b` as the production generation model.** Change
   `_DEFAULT_OLLAMA_MODEL` (`core/llm.py`) from `qwen3.5:9b` to `gemma4:e4b`, and
   make the Moltbook adapter's `OLLAMA_MODEL` (`adapters/moltbook/config.py`)
   *track that core default* instead of holding its own literal. The manual CLI
   paths read the core default directly; the autonomous `run` path reaches it
   through `Agent.__init__ → configure_llm(ollama_model=OLLAMA_MODEL)`, so without
   the second change the agent would silently keep serving `qwen3.5:9b` (a drift
   the cross-model review caught). One canonical default now feeds both paths.
   Embedding is unaffected — it has its own `OLLAMA_EMBEDDING_MODEL`
   (`nomic-embed-text`). Revert is `OLLAMA_MODEL=qwen3.5:9b` (env wins at call
   time via `_get_model()`; no code change).

2. **Keep the autonomous paths think-OFF.** Comment / reply / post and the
   scheduled `distill` are model-swap-only; they already pass the default
   `think=False`. No behavior change beyond the model.

3. **Run the six value-layer pipelines think-ON.** *(Note 2026-08-24: ADR-0097
   retired `rules-distill`, `rules-stocktake`, and skill-stocktake's
   grouping/merge/clean — of this list, `insight`, `amend-constitution`,
   `distill-identity`, and the surviving `skill-stocktake` report remain.)* `insight`, `rules-distill`
   (both stages), `amend-constitution`, `distill-identity`, `skill-stocktake`
   (grouping + merge + clean), and `rules-stocktake` (grouping) call a new
   internal `core/llm.generate_full(...) -> Optional[GenerationOutput]` (the
   internal analogue of `generate_for_api`; `generate()` still projects to
   `.text` so the other call sites are untouched) with `think=True`, and carry
   the captured trace on their result objects (`SkillResult` / `RuleResult` /
   `AmendmentResult` / `IdentityResult` / `StocktakeResult`, each gains a
   `thinking` field). think is hard-coded per command (the decision is settled);
   a CLI flag can be added later if A/B is wanted.

4. **Persist the trace to `reasoning.md` in the snapshot directory.** *(A missing `reasoning.md`
   now carries a reason — `no_think_calls` vs `all_traces_empty` — and the per-call reason
   lives on the `llm-calls` row; see the [ADR-0068 amendment](./0068-per-call-think-flag-and-thinking-trace-capture.md#amendment-2026-08-02--the-capture-outcome-becomes-observable),
   which also reaffirms Decision 5's manifest `think` as input config and leaves it unchanged.)* Each
   command writes its run's reasoning (URL-defanged like the episode report;
   already secret-scrubbed by `_sanitize_thinking`) to
   `snapshots/{cmd}_{ts}/reasoning.md`, a sibling of `manifest.json`. The
   manifest stays input-only (single responsibility); the trace is output. The
   interactive approval gate also prints the reasoning so the owner approves a
   value-layer change with the *why* visible.

5. **Record the run's generation config in the snapshot manifest.** `manifest.json`
   gains `generation_model` (from a new `core/llm.served_model()` shared with
   telemetry) and `think`, beside the existing `embedding_model` — closing the
   reproducibility gap where the manifest recorded the embedding lens but not the
   generation model or think state. `audit.jsonl` already references
   `snapshot_path`, so model/think are resolvable from the manifest without
   duplication. *(2026-08-02: that indirection is now unnecessary — the manifest
   carries `run_id` itself, the same key every audit record has, so the join is
   direct. It also survives a run that produced no artifacts and therefore wrote
   no `audit.jsonl` row. `run_id` is input-side metadata and does not disturb
   this decision's input-only responsibility.)*

6. **Give `skill-stocktake` / `rules-stocktake` a snapshot.** Both handlers now
   call `_take_snapshot(..., think=True)`, fixing the prior omission and giving
   their `reasoning.md` the same home as the other value-layer commands.

The per-merge / per-clean stocktake traces are collected through an optional
`trace_sink` parameter on `merge_group` / `clean_skill_triggers` /
`_find_duplicate_groups` — a backward-compatible side channel that keeps those
functions' string/list return types (and their direct unit tests) unchanged.

## Review-when *(added 2026-08-24)*

This ADR predates the harness-side Review-when convention (this repo's own
`0044` is an unrelated topic-keywords ADR); this section is a dated amendment,
not a change to the decision. The decision is a dated hypothesis about the
mid-2026 local-model landscape (knowledge-staleness: model economics go stale on
a scale of weeks), so it carries both expiry triggers and the re-evaluation
procedure. A trigger parked on another decision's state dies silently when that
decision is superseded — the Gemma 12B upgrade waited on "once MLX runs
stably" and ADR-0070 retired MLX itself, so the trigger's source vanished
before it ever fired. Writing the procedure here, anchored to this ADR's own
subject, avoids that failure mode.

**Triggers** (any one; none of these is wired to an intake — they fire when the
author notices, typically at the Saturday gate):

- A local model appears with a credible quality claim at or above `gemma4:e4b`
  within the 16 GB unattended envelope (weights + 32K KV under the
  [ADR-0067](./0067-keep-ollama-for-unattended-production.md) memory ceiling),
  available through Ollama. The claim only *starts* the A/B below; it decides
  nothing (procedure step 1 still distrusts it).
- The hardware constraint changes (RAM upgrade or machine swap). This also
  reopens ADR-0067 itself — "available through Ollama" is 0067's conclusion,
  and 0067 names a larger-RAM host as its own falsifier — so revisit 0067
  first; the Ollama filter above is not a premise of this ADR.
- Regressions attributed to the model recur after a swap, measured against the
  post-swap baseline: solver failures in `logs/verification-audit.jsonl`
  clearly above the post-2026-06-28 rate, or wrapper-verbalization above the
  A/B's observed 1-in-4-posts floor across a week of sessions. A prompt-level
  fix changes the measurand — re-anchor the count after one lands.

**Procedure** (how ADR-0068/0069 was actually decided; reuse it, do not redesign):

1. Do not trust secondary reviews — the 2026-05 scout verdict on Gemma E4B was
   overturned by direct A/B. Run the candidate against the incumbent on the
   production prompts (comment generation + one value-layer command), same
   harness, in a worktree or off-window session
   (`feedback_no_heavy_experiments_during_sessions`). On 16 GB only one model
   fits resident: `ollama stop` the incumbent before loading the candidate, as
   the ADR-0068 A/B script did.
2. Build the decision's comparison set at event time as a disposable golden
   set: reuse the `docs/evidence/adr-0068/` pattern — same inputs to all arms,
   a cross-model blind judge with per-item label rotation, and discard the
   judge's own cross-item "overall" ranking. The set lives with the evidence of
   the decision it served. This is the *decision material*; it does not replace
   the standing regression gate in the next step.
3. A completed swap must re-baseline the standing eval layer
   ([ADR-0089](./0089-llm-behavioral-eval-layer-on-deepeval.md)): its approved baselines
   pin `target_model`, so changing `_DEFAULT_OLLAMA_MODEL` makes them
   machine-detectably STALE — but staleness is advisory-only, nothing blocks a
   swap that skips this. The swap is not complete until
   `evals/run_eval.py` has run and a new baseline is approved.
4. Compare against the **current** model's outputs as baseline, not historical
   ones (per ADR-0058, distill output became more model-sensitive after the
   value-layer scaffold thinned, and its own guidance is to re-baseline the
   A/B against post-change output, not across the change).
5. Scope guard: this procedure is for same-or-better-quality swaps.
   Speed-driven quality downgrades remain rejected (2026-06-23 owner decision);
   a same-or-newer-generation swap with a defensible quality claim was never in
   that guard's scope — this ADR's own gemma swap is the precedent.
6. **Re-evaluate the embedding scaffold in the same pass** *(added 2026-08-30;
   absorbed from RFC-0005, withdrawn the same day as a 便乗 ledger row — a row
   saying "next time you swap the model, also do this" never reaches the person
   doing the swap, so it lives here instead).* The mechanism layer's embedding
   dependency (view retrieval, candidate narrowing — ADR-0019) is compensation
   for what the generation model of the day could not afford to read. The design
   rule is: **relevance judgments belong to the strongest judge you can pay for.**
   ADR-0019's division of labour (mechanism = embedding, value judgment +
   generation = LLM) is correct at gemma4:e4b's prefill cost (6.3–7.1 ms/tok
   measured) and inverting it breaks things — but the swap that triggers this
   procedure is exactly the event that can move that line. So: with the
   candidate model's measured prefill cost and the current store size, ask which
   embedding-side step could now be done by having the model read instead.
   Precedent: stocktake grouping went from embedding union-find to a single LLM
   call once the corpus fit ("if the LLM can read it, reading wins"). Judge on
   both axes — cost (prefill × store size) and accuracy. A negative answer is a
   valid outcome and needs no further action.

## Alternatives Considered

### Turn think on everywhere, including the autonomous paths

Rejected by the owner: comment/reply/post and `distill` run unattended where the
2.2× latency and the extra memory residency risk colliding with the launchd
session window on 16 GB ([ADR-0067](./0067-keep-ollama-for-unattended-production.md)).
The A/B also shows think's quality edge over think-OFF is small (6.50 vs 5.75) —
not worth the autonomous-path cost. Stability over a marginal quality gain there.

### Adopt gemma think-OFF (the A/B's "strong swap candidate") everywhere

The A/B verdict favored gemma think-OFF as the swap (faster + higher quality than
baseline). That is exactly what the autonomous paths get. think-ON is reserved
for the manual, upstream paths where reasoning quality matters more than latency
and the trace has research value — a per-path decision, not a global one.

### Make the thinking trace replace `internal_note`

Considered and dropped. `internal_note` ([ADR-0045](./0045-pre-action-internal-note.md))
is a single-responsibility, content-anchored pre-action reflection that distill
reads as in-register, un-wrapped first-person material; the reasoning trace is
task-CoT toward the output and is treated as untrusted in the distill path
(`distill.py` already excludes it). The two serve different roles and trust
regimes, and `internal_note` also covers upvote-only actions that produce no
generation trace. Left untouched.

### Discard the trace on the value-layer paths (think for quality only)

Rejected: it would pay the think latency and throw away the reasoning, which for
constitution/identity/rules is the research artifact the project most wants to
keep. The snapshot directory gave the trace a durable home at near-zero cost.

### A new `logs/llm-thinking-*.jsonl` artifact for the value-layer traces

Rejected for the same reason ADR-0068 rejected it for the episode path: it adds a
new untrusted-content artifact and lifecycle. Reusing the per-run snapshot
directory is the lower-surface choice and co-locates the trace with the input
state that produced it.

### Put the trace content in the snapshot manifest

Rejected: the manifest records the run's *input* lens (views, constitution,
prompts, thresholds, embedding model). Folding output reasoning into it would
break that single responsibility. The trace goes in a sibling `reasoning.md`;
only the generation model + think *metadata* go in the manifest.

## Consequences

### Positive

- Production generation quality improves (gemma > qwen on the blind judge) with
  the autonomous comment path also getting faster (think-OFF, 0.65×).
- The value layers most upstream of behavior change are generated with a
  reasoning pass, and that reasoning is preserved per-run, co-located with its
  input snapshot, and shown at the approval gate.
- The snapshot manifest now records the full generation config (model + think),
  closing a reproducibility gap; `served_model()` unifies the telemetry and
  manifest model fields.
- `skill-stocktake` / `rules-stocktake` are now snapshotted like every other
  behavior-producing command.
- Reversible: `OLLAMA_MODEL=qwen3.5:9b` restores the prior model with no code
  change.

### Negative

- The manual value-layer commands are 2–3× slower per LLM call under think-ON
  (acceptable: they are human-invoked, not on the latency-critical autonomous
  path).
- The A/B flagged a model-behavior risk: gemma occasionally verbalized the
  `<untrusted_content>` input wrapper into prose (n=1 of 4 posts, think-OFF). This
  is a pre-existing, model-general tendency (not caused by think and not new to
  gemma) and is out of scope here; if it recurs at rate, the fix is prompt-level
  (instruct the model not to reference its input wrapping), not a token guard
  (the word "untrusted" appears legitimately in contemplative-AI discourse).
- `generate_full` and the `trace_sink` side channel add a second internal
  generation entry point and a parameter to three stocktake functions.

### Neutral / Follow-ups

- The CAPTCHA verification solver (`verification.py`) also runs on gemma now
  (model is global), behind the deterministic parser added in `b7fb2d9`. Monitor
  `logs/verification-audit.jsonl` for any post-swap regression.
- Before the first autonomous run on the new default, confirm `gemma4:e4b` is
  pulled (`ollama list`) so a session does not stall on a download, and do the
  swap outside the launchd session window (0/6/12/18 JST) to avoid a
  qwen→gemma transition colliding with a live session on 16 GB.
- The sibling `contemplative-agent-cloud` backend can populate
  `BackendResult.thinking` to gain trace capture on the value-layer paths under
  the cloud backend.
