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
([ADR-0020](./0020-pivot-snapshots.md)) at run start; the snapshot directory is a
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

3. **Run the six value-layer pipelines think-ON.** `insight`, `rules-distill`
   (both stages), `amend-constitution`, `distill-identity`, `skill-stocktake`
   (grouping + merge + clean), and `rules-stocktake` (grouping) call a new
   internal `core/llm.generate_full(...) -> Optional[GenerationOutput]` (the
   internal analogue of `generate_for_api`; `generate()` still projects to
   `.text` so the other call sites are untouched) with `think=True`, and carry
   the captured trace on their result objects (`SkillResult` / `RuleResult` /
   `AmendmentResult` / `IdentityResult` / `StocktakeResult`, each gains a
   `thinking` field). think is hard-coded per command (the decision is settled);
   a CLI flag can be added later if A/B is wanted.

4. **Persist the trace to `reasoning.md` in the snapshot directory.** Each
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
   duplication.

6. **Give `skill-stocktake` / `rules-stocktake` a snapshot.** Both handlers now
   call `_take_snapshot(..., think=True)`, fixing the prior omission and giving
   their `reasoning.md` the same home as the other value-layer commands.

The per-merge / per-clean stocktake traces are collected through an optional
`trace_sink` parameter on `merge_group` / `clean_skill_triggers` /
`_find_duplicate_groups` — a backward-compatible side channel that keeps those
functions' string/list return types (and their direct unit tests) unchanged.

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
