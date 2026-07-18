<!-- Generated: 2026-07-18 | Files scanned: 69 | Token estimate: ~7030 -->
# Architecture

## Project Type
Python CLI agent: core/adapter separation + 3-layer memory + embedding views (ADR-0019) + pivot snapshots (ADR-0020) + pattern provenance/bitemporal (ADR-0021) + trust retirement (ADR-0051). Generation pluggable via `LLMBackend` Protocol (default: Ollama; add-on: `contemplative-agent-cloud`).

**Stats**: see [INDEX.md § Statistics](INDEX.md#statistics)

## System Diagram

```
  config/ (templates, git-managed)       ~/.config/moltbook/ (MOLTBOOK_HOME, runtime)
    domain.json  prompts/*.md              knowledge.json  embeddings.sqlite  identity.md
    views/*.md   templates/<char>/       constitution/  views/  prompts/  skills/  rules/
                                           snapshots/  logs/  agents.json
         |
         v
  src/contemplative_agent/
    core/  (platform-independent)
      _io  config  domain  prompts  llm(+LLMBackend)  embeddings
      episode_embeddings  episode_log  knowledge_store  memory
      views  snapshot  scheduler  distill  pattern_dedup  episode_render
      insight  insight_novelty  skill_selection  constitution  rules_distill
      stocktake  report  metrics  view_metrics  clustering  text_utils
      thresholds  artifact_extraction  run_context
    adapters/moltbook/
      agent  session_context  feed_manager  reply_handler  post_pipeline
      client  auth  verification  content  llm_functions  config
      dedup  novelty  feed_seeder
    adapters/meditation/  (experimental)  config  pomdp  meditate  report
    adapters/dialogue/  peer.py
    cli/  (composition root package, ADR-0079: __init__ dispatch + runtime/
          schedule/approval/staging/adopt/stocktake_cmd/memory_cmds/session_cmds)
         |                       |
    Moltbook API            Ollama (local default)
    60GET/30POST/min        gemma4:e4b + nomic-embed-text (768-dim) :11434
```

## Import Rule
`core/ ← adapters/ ← cli/` (one direction). The `cli/` package (composition root; formerly the single-file cli.py, split per ADR-0079) is the only layer importing both. Meditation/dialogue adapters depend on core/ only; they do not import moltbook adapter.

## Init-Time Copy
`contemplative-agent init [--template NAME]` copies every runtime Markdown from `config/` into `MOLTBOOK_HOME`. Template-derived: `constitution/`, `skills/`, `rules/`. Shared: `prompts/`, `views/`. Existing dirs never overwritten.

## LLM Backend
`core/llm/` package (ADR-0079): `backend.py` `LLMBackend` Protocol: `generate(prompt, system, num_predict, format, *, temperature)` → `Optional[BackendResult]` (`text` + `finish_reason` + `eval_count`), plus read-only `model` (served id, ADR-0065) and `context_window` (token ceiling, ADR-0066) properties. Module-level `_backend` slot set via `configure(backend=...)`. Sanitization, circuit breaker, and the `drop_truncated` truncation gate (from `finish_reason`) are applied by the **caller** (`_generate_via_backend`), uniformly across backends. A backend-aware context-budget pre-flight (`_generate_impl`, before dispatch; audit C2) guards est `system+prompt+num_predict` against the backend's `context_window` (`NUM_CTX` on the Ollama path; a backend omitting the property is unguarded) — Ollama would front-truncate the value layer, a memory-bounded injected backend would overrun its window. Over-budget `num_predict` is **clamped** to the remaining window (WARNING + `num_predict_requested` in telemetry); the call is skipped only when input alone leaves < `MIN_CLAMPED_NUM_PREDICT` (2048) output tokens (2026-07-10 fix: the skip-only guard suppressed every self-post for 24h after a 13-skill adoption grew the system prompt to ~20.3K tok). Default `_backend=None` → built-in Ollama HTTP path; an add-on (e.g. `contemplative-agent-cloud`) injects an alternative via `configure(backend=...)`. SSRF allowlist shared via `validate_trusted_url()`.

## Immutability
All DTOs `frozen=True`. Required by approval-gate diff pipeline and bitemporal invariants.

## Observability
Every feature with external I/O, LLM calls, or heuristic decisions ships a replayable
append-only JSONL audit log in the same PR (untrusted raw input as base64 + sha256,
decision path, categorical reason codes, outcome; no silent fallbacks) — ADR-0075.
Existing instruments: `verification-audit.jsonl` (solver — incl.
malformed-object abstains; replay harness in
`docs/evidence/adr-0062-parser-rewrite/`), `api-audit.jsonl` (API drift —
incl. transport errors and retried-429 backoffs),
`audit.jsonl` (approval gates), `insight-novelty.jsonl` (ADR-0074 novelty-gate
judge runs: prompt + raw output base64+sha256, verdict
judged/fail_open_llm/fail_open_parse), `skill-selection-YYYY-MM-DD.jsonl`
(ADR-0076 shadow pass-1 skill selection before each content generation:
selected + hallucinated-rejected names, verdict judged/fail_open_llm/
fail_open_parse/empty_catalog/no_template, prompt/output base64+sha256,
full vs would-be skill token estimates baked in at record time; read via
`report --skill-selection`; injection unchanged — enforcement reserved for
a follow-up ADR), LLM telemetry caller tags. An
embedding-model calibration pin (`core/embeddings.py`
`CALIBRATED_EMBEDDING_MODEL` + three-point anchors, ADR-0071/0072) warns at
command startup and in `report --patterns` when the active model drifts from
the one all similarity thresholds were calibrated on. A system-prompt budget
reading (`core/llm/prompting.py` `system_prompt_budget_reading`, shown by
`adopt-staged` before the approval loop) projects the value-layer token cost
against `NUM_CTX` so batches are approved with the window share visible
(2026-07-10, after a blind 13-skill adoption tripped the C2 guard; baseline
at introduction ≈20.3K tok ≈62%). Design know-how:
project skills `replayable-audit-logs` / `read-only-instruments`.
OTel connection (ADR-0078): runtime adoption stays rejected (per ADR-0075);
the audit-log schemas map onto the OTel GenAI semantic conventions via a
zero-dependency vocabulary doc ([docs/otel-semconv-mapping.md](../otel-semconv-mapping.md))
and an offline JSONL→OTLP exporter in the sibling repo
`contemplative-agent-otel` (reads log files only — zero code dependency).
Execution identity (ADR-0078 same-day follow-up): `core/_io.py`
`append_jsonl_restricted` — the single writer behind every JSONL log
(audit logs *and* episode logs) — stamps each record with a process-wide
`run_id` (uuid4, minted in `core/run_context.py` at import) and, while a
`run` session is active, a `session_id` (set/cleared by `cli/__init__.py` around
`run_session`, `try/finally`). Caller-supplied values win; offline tooling
groups records by id instead of inferring runs from time gaps.

---

## Data Flow — Session Execution

```
CLI → Agent.run_session(autonomy_level, session_mins)
 ├─ ReplyHandler._run_reply_cycle()
 │    internal_note (ADR-0045) → reply → POST → verify → EpisodeLog
 │    [reply generation is preceded by the ADR-0076 shadow skill-selection
 │     observation — records only, injection unchanged; same for comment
 │     and cooperation_post below, NOT post_title]
 ├─ Agent._run_feed_cycle()
 │    fetch → promo filter → own-author skip (name-keyed + id belt-and-braces;
 │      live feed lacks author.id) → ID dedup → per-author cap (3/24h)
 │    → score_relevance (LLM, on 500-char feed preview — cheap gate)
 │    → fetch full body  [ADR-0061; before the note, not just the comment]
 │    → internal_note + comment (read the FULL post, not the preview)
 │    → Scheduler budget gate → POST → verify
 ├─ PostPipeline._run_post_cycle()
 │    feed_seeder.select_feed_seeds()        [ADR-0043]
 │      relevance ≥ 0.4 | RNG 1-3 posts | 15000-char budget
 │    → generate_cooperation_post (title + body)
 │    → _passes_deterministic_gates (order as in code):
 │      is_test_content() → NoveltyGate.evaluate() [ADR-0039]
 │        (cosine vs recent self-posts + temporal decay + rate-deficit Lagrangian)
 │        → body-hash dedup (SHA-256[:16]) → POST /posts
 │    → verification handshake: a non-trusted agent's create-response carries a
 │      math challenge; solve_challenge first runs a deterministic code parser
 │      (code_parse_challenge, rewritten 2026-07-07 from the 601-challenge audit
 │      corpus — ADR-0062 6th amendment; grammar extended 2026-07-09 on 792
 │      challenges — 7th amendment) that normalizes leet 0→o, merges split
 │      fragments bounded by collapsed token length, recovers misspelled number
 │      words / operation verbs at edit distance 1 (canonical or, for tokens
 │      ≥ 6 letters, collapsed spellings; prose stopwords; ambiguity poisons
 │      the parse), dedups doubled number words, left-folds strictly
 │      interleaved N-step chains, resolves trailing total/sum/product cues,
 │      adjacent postfix operators, multiplicative markers (factor / doubled /
 │      each / a claw count after the second operand — markers beat generic
 │      change-verbs like "increases" in the same gap; non-adjacent trailing
 │      markers are noise), waives the like-unit guard under an explicit
 │      "sum" / "add them" instruction, and abstains (None) on any ambiguity,
 │      including corpus-attested contradictions ("slows" vs "combined", bare
 │      "it has N") (replay: coverage 83.2%, zero wrong submissions); only
 │      then does it ask the LLM for a short numeric expression, validate it in
 │      Python, and fall back to bounded LLM reasoning if the guarded expression
 │      fails (solver order: code_parse → llm_extract → llm_reason). The bounded
 │      reasoning fallback also self-checks: any line in its free-form trace that
 │      reduces to a two-operand expression is recomputed and compared to the
 │      stated FINAL, rejecting to None on disagreement rather than submitting a
 │      self-inconsistent answer (does not catch a self-consistent but
 │      semantically wrong operator choice — the same limit code_parse's guard
 │      note already documents for llm_extract)
 │      → POST /verify. Content stays verification_status=pending (invisible)
 │      until verified, so memory/NoveltyGate recording happens ONLY after
 │      success (posts, comments, replies). Each challenge outcome is also
 │      appended to logs/verification-audit.jsonl with challenge_b64 +
 │      challenge_sha256, solver_path, answer, and verify_success.
 └─ MemoryStore.record() → EpisodeLog (append-only JSONL)
```

**Generation model**: `gemma4:e4b` since ADR-0069 (was `qwen3.5:9b`) —
`_DEFAULT_OLLAMA_MODEL`, overridable via `OLLAMA_MODEL` (launchd pins none).
Embedding stays `nomic-embed-text` (`OLLAMA_EMBEDDING_MODEL`), generation-only.

**Reasoning trace (`think`)**: a per-call `think` flag (default False; toggles
Ollama `think`) requests the model's reasoning trace,
secret-scrubbed but never published. Two regimes (ADR-0068, ADR-0069):
- *Autonomous content paths* (comment / reply / cooperation post) and the
  scheduled `distill` stay **think-OFF** (latency / stability). When a caller
  opts in, `core/llm.generate_for_api` returns `GenerationOutput(text, thinking)`
  and the publish seam stores the trace on the `activity` episode beside
  `internal_note` (untrusted regime); `report.py` renders a `**Thinking:**` block.
- *Manual value-layer pipelines* (insight / rules-distill / amend-constitution /
  distill-identity / skill-stocktake / rules-stocktake) run **think-ON** via
  `core/llm.generate_full` (the internal `GenerationOutput`-returning entry). The
  trace rides on the result object and is written to
  `snapshots/{cmd}_{ts}/reasoning.md` (URL-defanged) + shown at the approval gate.

Telemetry records only the `think` boolean (metadata), never trace content. The
snapshot manifest records `generation_model` + `think` (ADR-0069) beside
`embedding_model`.

All content creation (post / comment / reply) goes through this same verification
handshake. Each API call's structural outcome (status, envelope keys, content
status, soft-failures, schema drift) is appended to `logs/api-audit.jsonl` by the
client chokepoint — a self-written, free-text-free log safe to read directly.
Verification challenges are captured separately in `logs/verification-audit.jsonl`:
the challenge text is base64-encoded for corpus evaluation, not written as raw
prompt text; any decoder must re-wrap it as untrusted content before LLM use.

---

## Data Flow — Offline Learning

Every behaviour-producing command writes a pivot snapshot (`snapshots/{cmd}_{ts}/`) at run start (ADR-0020) and threads its path into `audit.jsonl`. The manifest records `generation_model` + `think` (ADR-0069). The six **think-ON** value-layer commands (insight / rules-distill / amend-constitution / distill-identity / skill-stocktake / rules-stocktake) also write their reasoning trace to `reasoning.md` in the snapshot dir; the autonomous `distill` stays think-OFF.

All offline distillation LLM calls (distill / insight / rules-distill / constitution amend / distill-identity) run under a **base-only system prompt** — the four axioms are NOT injected. Value layers belong to action time only; `get_distill_system_prompt` is base-only since ADR-0058 (their inputs are already value-shaped, and fresh external observation should be extracted faithfully, not re-interpreted through a value lens). Axioms are injected only at action time (`_build_system_prompt`, `get_identity_system_prompt`).

### distill  [`core/distill.py`]

```
Input: EpisodeLog.read_range(days=N)
  type="insight" records EXCLUDED at read  [ADR-0052: retired session
  summaries; historical records stay in the log but never re-distill]

Scope filter — engagement episodes only  [ADR-0060; _is_rich_episode]
  keep activity records with action ∈ {comment, reply, post}
  drop redundant short interaction/post records + sparse upvote/follow/unfollow
  (NO ingest noise gate [ADR-0060]. Downstream, the two view-querying
   consumers — distill-identity / amend-constitution — apply their own view
   thresholds at query time [ADR-0031]; insight skips legacy `gated` rows.
   The five orphaned view seeds, `noise` included, were pruned in ADR-0073 —
   only the two consumed views ship)

Per-episode distill  [ADR-0060; one LLM call per episode, no batching]
  for each episode:
    render_episode() → rich block: original_post + their_comment (replies) +
      the agent's own output (content/title) + internal_note (full).
      External (peer-authored) fields go through wrap_untrusted_content()
      (injection defense + max_input cap); the agent's own content/title use
      truncate_boundary() at its EXCERPT_CAP, internal_note is full/un-capped
    → LLM(DISTILL_EPISODE_PROMPT, format=_PATTERNS_SCHEMA, drop_truncated=True)
      → JSON {"patterns":[...]}
      (prompt asks for a first-person, moment-indexed register + forbids
       meta-statements about inextractability — return [] instead; ADR-0072.
       Bug-audit 2026-07-06: a num_predict-capped generation is dropped —
       explicit per-episode failure — instead of silently parsing a cut JSON
       body (H1; all internal pipelines now pass drop_truncated=True).
       ADR-0077: every per-episode failure abstains with a reason code
       (reason=llm_none / empty_render / shape_violation) — a valid-JSON
       body violating {"patterns": [str]} (top-level array/scalar, non-list
       or non-string "patterns") abstains as shape_violation instead of
       bullet-scanning the JSON (H2 superseded for JSON bodies); the bullet
       fallback survives only for genuinely non-JSON bodies, tagged
       parse=bullet_fallback. The summary WARNING tallies abstains per
       reason; embed-degradation carries reason=embed_failed. Chaos tests
       (tests/chaos.py + test_llm_chaos.py / test_distill_chaos.py) pin the
       fault catalog F1-F5, and llm-calls telemetry stamps a sparse
       error_kind on failure rows)
    → _is_valid_pattern() gate: length floor + extraction-failure
      meta-statement phrase filter (validity, not value; rejects logged with
      reason; ADR-0072); provenance = that one episode's source_type + ts
  (recurrence is NOT pre-clustered here — it surfaces downstream when `insight`
   clusters patterns into skills; episode-level near-duplication is rare and the
   pattern-level dedup below already absorbs it)

Persist  [no LLM; unchanged tail from the prior design]
  → embed_texts(new patterns)
  → _dedup_patterns():
      effective_importance = 0.95^days   [pure time decay; ADR-0051, ADR-0056]
      skip rows below DEDUP_IMPORTANCE_FLOOR (0.05) → ~58 days, uniform
      cosine(new, existing):
        ≥ SIM_DUPLICATE (0.90)  →  SKIP
        ≥ SIM_UPDATE    (0.80)  →  UPDATE (soft-invalidate old, append revised — no boost)
        < SIM_UPDATE             →  ADD
  → KnowledgeStore.add_learned_pattern(..., embedding)  [no importance field]
  → provenance.source_type recorded, NEVER weighted  [ADR-0051]
```

Dry-run instruments  [`core/view_metrics.py` — read-only observability, never a gate]
  `distill --dry-run` additionally logs the would-be-added batch's composition:
  consumed-view supply (self_reflection / constitutional pass rates + cosine
  percentiles) and seed-independent diversity (pairwise cosine + the cluster
  structure insight would see). `report --patterns` renders the same
  instruments over the whole live pool; `insight` logs dropped singletons with
  their nearest consumed view. A third grounding instrument (source_type /
  epistemic composition) was removed in ADR-0072: under per-episode
  distillation the source_type mapping reads as a constant, so it changed no
  action (signal-first). Instruments measure only the two consumed views — a
  distribution over an unconsumed seed measures seed staleness, not corpus
  structure. Empty/low supply stays ambiguous (missing patterns vs stale seed)
  and the output says so. Nothing here feeds ranking, gating, or promotion.

Threshold canonical source: `core/thresholds.py` (read by `snapshot.collect_thresholds`).
Excerpt caps + RICH_ACTIONS live in `core/episode_render.py` (ADR-0060; extracted from distill.py per ADR-0079 Phase 3b — rendering only, gates unchanged).

### distill-identity  [`core/distill.py: distill_identity()`]

```
ViewRegistry.find_by_view("self_reflection", get_raw_patterns())
  cosine(pattern_emb, self_reflection_centroid)
  threshold from view frontmatter | top_k=50   [PURE COSINE, no importance weight]
  (self_reflection: threshold 0.66 + corpus-grown exemplar appendix in the
   seed since 2026-07-03 [ADR-0072]; was 0.55 = corpus homogeneity floor.
   Register contract: this seed is the READ side of an ADR-0072 pair whose
   WRITE side is the register instruction in distill_episode.md — edit them
   as a pair; view_metrics supply readings are the drift detector)

Single LLM call: generate_full(IDENTITY_DISTILL_PROMPT, ...)  [think-ON, ADR-0069]
  [ADR-0057: prior identity NOT seeded — persona emerges from the corpus alone]
  [base-only system prompt; axioms not injected — ADR-0058]
→ validate_identity_content()
→ IdentityResult(text, target_path, pattern_ids, epistemic_counts, thinking)  [ADR-0050; thinking → reasoning.md, ADR-0069]
→ write gated by cli/approval.py → MOLTBOOK_HOME/identity.md  [ADR-0012]
```

No Stage 2 refine. No importance-ranked input. One LLM call only.

### insight  [`core/insight.py: extract_insight()`]

```
Input: incremental — KnowledgeStore.get_live_patterns_since(.last_insight marker)
  [is_live: valid_until is None; gated=True excluded before clustering]
  missing marker → REFUSE (no silent full recluster; --full is the deliberate
  whole-pool path)  [ADR-0074]

GLOBAL embedding clustering  [NOT per-view; ADR-0026]
  cluster_patterns(threshold=CLUSTER_THRESHOLD_INSIGHT=0.70)  [core/clustering.py]
  exact Lance-Williams average-linkage (same partitions as the retired naive
  merge, vectorized; N=1798 < 1 s)  [ADR-0074]
  cluster size ≥ MIN_PATTERNS_REQUIRED (3)  →  eligible

Ordering: cluster_size × mean(effective_importance)  descending
  effective_importance = 0.95^days   [pure time decay; ADR-0056]
Slicing: each cluster → top MAX_BATCH (10) by effective_importance (= freshest)

NOVELTY GATE  [ADR-0074 + 2026-07-18 amendment; fail-open PER CHUNK; lives in core/insight_novelty.py since ADR-0079 Phase 3a — module move only, gate logic unchanged]
  token-bounded chunked judging: _pack_novelty_chunks packs cluster blocks
  (3 samples each) greedily under window(32768) − output reserve(2048) −
  fixed cost(template + FULL known-theme inventory, repeated per chunk);
  known themes = skills/*.md frontmatter + logs/insight-staged.jsonl
  one generate_full(INSIGHT_NOVELTY_PROMPT) call PER CHUNK; covered ids
  validated per chunk; covered clusters skipped (skipped_known);
  all covered → empty result, marker still advances
  fail-open is chunk-scoped: LLM/parse failure keeps only that chunk's
  clusters (unjudged → fail_open_topics); oversized single block retries
  with truncated samples then fails open alone (fail_open_budget = the
  known-inventory-outgrew-chunking signal)
  one record per chunk appended to logs/insight-novelty.jsonl (batch_index/
  batch_count; prompt + raw output base64+sha256, 128KiB bound; verdict
  judged/fail_open_llm/fail_open_parse/fail_open_budget) — replay-only,
  never gates (ADR-0075)

FAIL-OPEN EXTRACTION CAP  [ADR-0074 amendment 2026-07-18]
  UNJUDGED clusters only (fail_open_topics) capped at
  MOLTBOOK_INSIGHT_FAILOPEN_CAP (default 20); deterministic priority:
  member count desc → effective_importance sum desc → topic name
  judged-novel clusters never capped (review-budget circuit breaker for a
  broken gate, NOT a quality filter); deferred clusters are not extracted /
  staged / ledger-written (no "considered" status unseen → recur in later
  windows); deferral recorded in insight-novelty.jsonl
  (reason=review_budget_deferred, topics + sizes + pattern_ids)

Per novel cluster → generate_full(INSIGHT_EXTRACTION_PROMPT, topic="cluster-N")  [think-ON, ADR-0069]
  system = axioms-only (no skill corpus injected — audit H6 fix, a2bebfe;
  the novelty gate reads themes, generation never does)
  → validate_identity_content()
  → SkillResult(text, filename, target_path, pattern_ids, epistemic_counts, thinking)  [ADR-0050; per-skill thinking → reasoning.md, ADR-0069]

→ InsightResult  →  --stage: pending guard (staging holds ≤ 1 unreviewed batch)
   → staging + marker advance + ledger append; interactive: per-file approval
   [ADR-0012], marker advances after the loop  [ADR-0074]
```

Views NOT used for batching — deliberate, not an omission: views retrieve along
predefined semantic axes; insight discovers structure the operator has not
named, so imposing a seed would bias discovery (decision rule: known axis →
view, emergent structure → clustering; see `core/views.py` docstring +
ADR-0031 consumption note). Every eligible cluster becomes a batch (no top-N
cluster cap). Weekly automation: `install-schedule --weekly-insight`
(launchd, default Mon 08:00; a pending review makes the run a no-op).

### rules-distill  [`core/rules_distill.py: distill_rules()`]

```
skills/*.md (MIN=3) → embed_texts → cluster(CLUSTER_THRESHOLD_RULES=0.65)
  → batches (MAX_BATCH=10)
  → generate_full(RULES_DISTILL_PROMPT) → generate_full(RULES_DISTILL_REFINE_PROMPT)  [both think-ON, ADR-0069]
  → RuleResult(text, filename, target_path, source_ids, thinking)  [ADR-0050; source_ids=skill filenames; per-batch thinking (both stages) → reasoning.md, ADR-0069]
→ write gated  [ADR-0012]
```

### amend-constitution  [`core/constitution.py`]

```
ViewRegistry.find_by_view("constitutional", get_live_patterns())
  MIN_PATTERNS_REQUIRED=3 gate
→ generate_full(CONSTITUTION_AMEND_PROMPT)  [think-ON, ADR-0069]
→ AmendmentResult(... pattern_ids, epistemic_counts, thinking)  [thinking → reasoning.md + approval gate, ADR-0069]
→ write gated  [ADR-0012]
```

### Approval lineage  [ADR-0050]

`SkillResult` / `RuleResult` / `IdentityResult` / `AmendmentResult` all carry `source_ids` / `pattern_ids` + `epistemic_counts`. On approval: `audit.jsonl` record includes `source_ids + epistemic_counts` (always present, nullable). `staging/meta.json` carries them through `adopt-staged`.

`epistemic_counts` = `{observed, generated, unknown}` tally; the kind is derived at read-time from `provenance.source_type` — never persisted. Since ADR-0060 distill ingests only `activity` records (comment/reply/post), and `_episode_source_kind` maps every activity to `self`, every distilled pattern is `self_reflection → generated`: `observed` is now structurally **zero**. The external world (the post engaged with, the other agent's comment) still enters distillation — but as grounding *text inside* the rich render, not as a provenance kind. The prior caveat (observed ≈ 0 because mixed batches collapsed to `generated`) is superseded: there are no batches, and the lone external source (interaction `direction="received"`) is no longer read.

### meditate  [`adapters/meditation/`]

```
EpisodeLog → pomdp.build_matrices() → A/B/C/D (numpy)
→ meditate(matrices, config)
  flat single-level POMDP; expected-free-energy policy selection
  "temporal flattening" / "counterfactual pruning" = LOCAL LABELS, not paper terms
  INSPIRED BY (not implementing) Laukkonen, Friston & Chandaria (2025)  [ADR-0049]
→ report.interpret_and_save() → config/meditation/results.json
  LLM interpretation display-only; NO KnowledgeStore write; deferred  [ADR-0049]
```

---

## Memory Architecture (3-Layer)

```
Layer 1: EpisodeLog  ~/.config/moltbook/logs/YYYY-MM-DD.jsonl  (append-only)
  record_type: post | comment | interaction | action | session
               | insight (historical only — generation retired, ADR-0052)
  + embeddings.sqlite (episode embedding sidecar, ADR-0019)

Layer 2: KnowledgeStore  MOLTBOOK_HOME/knowledge.json
  {pattern, distilled, embedding[768], gated, last_view_matches,
   provenance:{source_type, source_episode_ids, pipeline_version},
   valid_from, valid_until}                               [importance field retired, ADR-0056]
  effective_importance = 0.95^days                        [pure time decay; ADR-0056]
  is_live             = valid_until is None ONLY          [knowledge_store.is_live, ADR-0051]
  origin (source_type) = recorded, NEVER weighted         [ADR-0051]
  pattern_id          = sha256(distilled|pattern)[:12]    [ADR-0050]

Layer 3: Identity  MOLTBOOK_HOME/identity.md  (distill-identity, single-stage)

Pivot Snapshots  MOLTBOOK_HOME/snapshots/{cmd}_{ts}/
  manifest.json | views/*.md | constitution/*.md | centroids.npz  [ADR-0020]
```

**Deleted**: `forgetting.py` (ADR-0051) — `is_live` moved to `knowledge_store.py` (bitemporal-only, no trust floor).
**Retired fields**: `trust_score`/`trust_updated_at` (ADR-0051), `last_accessed_at`/`access_count` (ADR-0028), `provenance.sanitized` (ADR-0029), `category` (ADR-0026).

---

## AKC Mapping

| AKC Phase | Implementation | Code |
|-----------|----------------|------|
| Research | Feed fetch + relevance scoring | feed_manager.py |
| Extract | `distill` (per-episode grounded distill + embedding dedup) | distill.py |
| Curate | `insight` (global clustering → skills) | insight.py, clustering.py |
| Curate | `rules-distill` (skills → Practice/Rationale rules) | rules_distill.py |
| Curate | `amend-constitution` (constitutional view → ethics) | constitution.py |
| Promote | `distill-identity` (self_reflection view → persona) | distill.py, views.py |
| Measure | Pivot snapshots + `last_view_matches` telemetry | snapshot.py |
| Maintain | `context-sync` (Claude Code skill) + sync-data | — |

## Entry Points
- `contemplative-agent` → `contemplative_agent.cli:main`
- Tests: `pytest tests/ -v`
