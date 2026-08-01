<!-- Generated: 2026-08-01 | Files scanned: 74 | Token estimate: ~9179 -->
# Architecture

## Project Type

Python CLI agent: core/adapter separation + 3-layer memory + embedding views (ADR-0019) + pivot snapshots (ADR-0020) + pattern provenance/bitemporal (ADR-0021) + trust retirement (ADR-0051). Generation pluggable via `LLMBackend` Protocol (default: Ollama; add-on: `contemplative-agent-cloud`).

**Stats**: see [INDEX.md § Statistics](INDEX.md#statistics)

## System Diagram

```text
  config/ (templates, git-managed)       ~/.config/moltbook/ (MOLTBOOK_HOME, runtime)
    domain.json  prompts/*.md              knowledge.json  embeddings.sqlite  identity.md
    views/*.md   templates/<char>/       constitution/  views/  prompts/  skills/  rules/
                                           snapshots/  logs/  agents.json
         |
         v
  src/contemplative_agent/
    core/  (platform-independent)
      _io  config  domain  prompts  llm(+LLMBackend)  embeddings
      episode_embeddings  episode_log  knowledge_store  memory  memory_repos
      views  snapshot  scheduler  distill  pattern_dedup  episode_render
      insight  insight_novelty  skill_selection  constitution  rules_distill
      stocktake  report  metrics  view_metrics  clustering  text_utils
      thresholds  artifact_extraction  run_context
    adapters/moltbook/
      agent  session_context  feed_manager  reply_handler  post_pipeline
      publish  client  auth  verification  verification_parse  content
      llm_functions  config  dedup  novelty  feed_seeder
    adapters/meditation/  (experimental)  config  pomdp  meditate  report
    adapters/dialogue/  peer.py
    cli/  (composition root package, ADR-0079: __init__ tier dispatch + registry/
          agent_cmds/runtime/schedule/approval/staging/adopt/stocktake_cmd/
          memory_cmds/session_cmds)
         |                       |
    Moltbook API            Ollama (local default)
    60GET/30POST/min        gemma4:e4b + nomic-embed-text (768-dim) :11434
```

## Import Rule

`core/ ← adapters/ ← cli/` (one direction). The `cli/` package (composition root; formerly the single-file cli.py, split per ADR-0079) is the only layer importing both. Meditation/dialogue adapters depend on core/ only; they do not import moltbook adapter.

## Init-Time Copy

`contemplative-agent init [--template NAME]` copies every runtime Markdown from `config/` into `MOLTBOOK_HOME`. Template-derived: `constitution/`, `skills/`, `rules/`. Shared: `prompts/`, `views/`. Existing dirs never overwritten.

## LLM Backend

`core/llm/` package (ADR-0079): `backend.py` `LLMBackend` Protocol: `generate(prompt, system, num_predict, format, *, temperature)` → `Optional[BackendResult]` (`text` + `finish_reason` + `eval_count`), plus read-only `model` (served id, ADR-0065) and `context_window` (token ceiling, ADR-0066) properties. Module-level `_backend` slot set via `configure(backend=...)`. Sanitization, circuit breaker, and the `drop_truncated` truncation gate (from `finish_reason`) are applied by the **caller** (`_generate_via_backend`), uniformly across backends. A backend-aware context-budget pre-flight (`_generate_impl`, before dispatch; audit C2) guards `system+prompt+num_predict` against the backend's `context_window` (`NUM_CTX` on the Ollama path; a backend omitting the property is unguarded) — Ollama would front-truncate the value layer, a memory-bounded injected backend would overrun its window. Input is measured by `_measure_input_tokens`: the backend's own tokenizer when it declares the **optional** `TokenCountingBackend.count_tokens(text)` capability (a separate Protocol, not an `LLMBackend` member — a backend without a tokenizer stays conformant), else the conservative `_estimate_tokens` (ADR-0087). A counted value is rejected back to the estimator with a reason code when it is not a plain non-negative `int`, is `0` for non-blank text, or implies more than `MAX_CHARS_PER_TOKEN` (50) chars/token — a density bound catching a mis-calibrated tokenizer, since shape validation alone would trust `5` for a 50,000-char prompt. Both halves are adopted or rejected together, and no counter fault ever touches the circuit breaker. On the counted path the clamp withholds `BACKEND_FRAMING_RESERVE` (64) tokens for the chat-template framing no caller-side count sees; the estimator path reserves nothing, its over-count already being one. Telemetry records `token_count_source` / `input_tokens` (dense; `None` when the guard did not run) and a sparse `token_count_fallback_reason` — the two measures differ by up to 1.95x on Japanese-dominant input, so a clamp is unreadable offline without its source. The Ollama path has no counter available (Ollama 0.30.11 exposes no `/api/tokenize`; upstream `ollama#12030` open). Over-budget `num_predict` is **clamped** to the remaining window (WARNING + `num_predict_requested` in telemetry); the call is skipped only when input alone leaves < `MIN_CLAMPED_NUM_PREDICT` (2048) output tokens (2026-07-10 fix: the skip-only guard suppressed every self-post for 24h after a 13-skill adoption grew the system prompt to ~20.3K tok). Default `_backend=None` → built-in Ollama HTTP path; an add-on (e.g. `contemplative-agent-cloud`) injects an alternative via `configure(backend=...)`. SSRF allowlist shared via `validate_trusted_url()`.

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
(ADR-0076 pass-1 skill selection before each content generation:
selected + hallucinated-rejected names, verdict judged/fail_open_llm/
fail_open_parse/empty_catalog/no_template, `enforced` flag, prompt/output
base64+sha256, full vs would-be skill token estimates baked in at record
time; read via `report --skill-selection` incl. hallucination rate.
ADR-0081: with `MOLTBOOK_SKILL_SELECTION_ENFORCE=1` a judged selection
drives two-pass injection — pass 2 generates under a system prompt whose
`<learned_skills>` block holds only the selected bodies; every fail-open
verdict, the kill switch, and flag-off keep full injection),
`submolt-scope-YYYY-MM-DD.jsonl` (ADR-0086 read-only scope sweep, written by
`submolt-scan` only: one `scan_start` / N `score` / one `scan_end` per run,
per-post score + reason code (scored/empty_input/llm_unavailable/
unparseable/out_of_range) + `subscribed` label + post body base64+sha256;
scan verdict completed/disabled/discovery_failed/no_submolts/
aborted_rate_limit/aborted_read_budget/aborted_scored_cap; read via
`report --submolt-scope`, wired to no gate), LLM telemetry
caller tags. An
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

```text
CLI → Agent.run_session(autonomy_level, session_mins)
 ├─ ReplyHandler._run_reply_cycle()
 │    internal_note (ADR-0045) → reply → POST → verify → EpisodeLog
 │    [reply generation is preceded by the ADR-0076 pass-1 skill selection —
 │     shadow by default (records only); with ADR-0081
 │     MOLTBOOK_SKILL_SELECTION_ENFORCE=1 a judged selection makes the
 │     generation inject only the selected skill bodies (fail-open → full
 │     injection); same for comment and cooperation_post below; post_title
 │     reuses cooperation_post's selection, no second call]
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
 │      challenges — 7th, 2026-07-15 on 1272 — 8th, 2026-07-26 on 2236 — 11th)
 │      that normalizes leet 0→o, merges split
 │      fragments bounded by collapsed token length, recovers misspelled number
 │      words / operation verbs at edit distance 1 (canonical or, for tokens
 │      ≥ 6 letters, collapsed spellings; prose stopwords; ambiguity poisons
 │      the parse, as does a near-miss number word — including a tens+unit
 │      compound whose other half was mangled away, matched by the residue
 │      beside a tens word or, where the residue is beyond lexical reach, by
 │      the leftover shape of a split opening operand), composes decimals
 │      ("five point five"), dedups doubled number words and equal-value
 │      restatements, left-folds strictly
 │      interleaved N-step chains, resolves trailing total/sum/product cues,
 │      adjacent postfix operators, multiplicative markers (factor / doubled /
 │      each / a claw count after the second operand — markers beat generic
 │      change-verbs like "increases" in the same gap; non-adjacent trailing
 │      markers are noise), waives the like-unit guard under an explicit
 │      "sum" / "add them" instruction, and abstains (None) on any ambiguity,
 │      including corpus-attested contradictions (a subtract chain under any
 │      additive cue, a 3+ operand chain broken by a clause "and", a "*"
 │      inside a unit phrase, bare "it has N"). Resolution is two ordered
 │      rule tables walked by one driver, each ending in an unconditional
 │      terminal row (ADR-0062 10th amendment part two; a non-total table
 │      raises rather than abstaining, gated by TestRuleTableTotality)
 │      (replay 2026-07-26: coverage 82.1%, zero wrong submissions); only
 │      then does it ask the LLM for a short numeric expression and validate it
 │      in Python (solver order: code_parse → llm_extract → abstain, ADR-0062
 │      9th amendment — the free-reasoning fallback was retired after the
 │      round-7 audit measured it at 2.3% of traffic with 38% verify success;
 │      past the guarded paths the solver abstains with
 │      abstain_reason=reason_fallback_disabled when the model answered and the
 │      guards rejected it, llm_none when the call produced no text at all
 │      (12th amendment — an outage is not a judgment, and the failure kind
 │      stays in the llm-calls telemetry row), or answer_previously_rejected
 │      when every produced candidate was already server-rejected; the
 │      abstain still counts toward the failure tracker so grammar drift halts
 │      the session loudly instead of being guessed through)
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

```text
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
       This prompt is deliberately UNCHANGED by the ADR-0084 durability gate:
       every rewrite of it moved register and abstain rate together, so the
       verdict was moved out instead of tuned in.
       Bug-audit 2026-07-06: a num_predict-capped generation is dropped —
       explicit per-episode failure — instead of silently parsing a cut JSON
       body (H1; all internal pipelines now pass drop_truncated=True).
       ADR-0077: every per-episode failure abstains with a reason code
       (reason=llm_none / empty_render / shape_violation) — a valid-JSON
       body violating {"patterns": [str]} (top-level array/scalar, non-list
       or non-string "patterns") abstains as shape_violation instead of
       bullet-scanning the JSON (H2 superseded for JSON bodies); the bullet
       fallback survives only for genuinely non-JSON bodies, tagged
       parse=bullet_fallback. A zero-pattern episode abstains with the one
       reason that is a VERDICT rather than a fault (reason=nothing_durable,
       logged with parse= so an empty bullet scan stays distinguishable from
       a judged empty list); it is tallied APART from the three fault reasons
       so a routine week never reads as a backend outage, and it does not
       count as a circuit-breaker failure. The summary WARNING tallies the
       fault abstains only, and an always-emitted INFO yield line reports
       episodes-that-yielded plus nothing_durable — replacing "all N episodes
       produced output", which counted a judged abstain as output and is why
       the 0.1% verdict rate stayed invisible;
       embed-degradation carries reason=embed_failed. Chaos tests
       (tests/chaos.py + test_llm_chaos.py / test_distill_chaos.py) pin the
       fault catalog F1-F5, and llm-calls telemetry stamps a sparse
       error_kind on failure rows)
    → _is_valid_pattern() gate: length floor + extraction-failure
      meta-statement phrase filter (validity, not value; rejects logged with
      reason; ADR-0072); provenance = that one episode's source_type + ts
    → durability postgate  [ADR-0084; ON by default (MOLTBOOK_DISTILL_POSTGATE=0
      opts out — a plist-carried flag silently reverts on install-schedule)
      AND only when the episode produced at least one pattern — an empty extraction is
      already a verdict and would spend a call on nothing]
      LLM(DISTILL_POSTGATE_PROMPT, format={"keep":[int]}, num_predict=300)
      over the episode PLUS its numbered patterns → keeps the listed ones.
      The judge sees the artifact, which is the whole point: the same
      question asked BEFORE distilling answered "durable" 40/40 in the
      offline replay, because naming a worthwhile moment costs nothing when
      you never have to write it. Producing the pattern is the evidence.
      Per-pattern, so a two-pattern episode with one grounded pattern keeps
      one — which is also what unpins yield from the distill prompt
      example's arity. Fails OPEN with reason=postgate_llm_none /
      postgate_parse / postgate_shape: this gate can only REMOVE rows the
      distiller already produced, so a broken gate must degrade to keeping
      everything, never silently prune research data. Dropping the last
      pattern lands on the same reason=nothing_durable verdict as a
      model-authored empty list.
      Replay reading (40 episodes, 2026-07-26): 74 → 59 patterns, judged
      abstain 0% → 5%, register at or above baseline (I+perception-verb
      86.4% vs 72.8%, median length 358 vs 357) — the dropped patterns are
      the ones lacking a concrete moment, so trimming raises what remains.
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

```text
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

```text
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

```text
skills/*.md (MIN=3) → embed_texts → cluster(CLUSTER_THRESHOLD_RULES=0.65)
  → batches (MAX_BATCH=10)
  → generate_full(RULES_DISTILL_PROMPT) → generate_full(RULES_DISTILL_REFINE_PROMPT)  [both think-ON, ADR-0069]
  → RuleResult(text, filename, target_path, source_ids, thinking)  [ADR-0050; source_ids=skill filenames; per-batch thinking (both stages) → reasoning.md, ADR-0069]
→ write gated  [ADR-0012]
```

### amend-constitution  [`core/constitution.py`]

```text
ViewRegistry.find_by_view("constitutional", get_live_patterns())
  MIN_PATTERNS_REQUIRED=3 gate
→ generate_full(CONSTITUTION_AMEND_PROMPT)  [think-ON, ADR-0069]
→ AmendmentResult(... pattern_ids, epistemic_counts, thinking)  [thinking → reasoning.md + approval gate, ADR-0069]
→ write gated  [ADR-0012]
```

### Approval lineage  [ADR-0050]

`SkillResult` / `RuleResult` / `IdentityResult` / `AmendmentResult` all carry `source_ids` / `pattern_ids` + `epistemic_counts`. On approval: `audit.jsonl` record includes `source_ids + epistemic_counts` (always present, nullable). `staging/meta.json` carries them through `adopt-staged`.

`epistemic_counts` = `{generated, unknown}` tally; the kind is derived at read-time from `provenance.source_type` — never persisted. Since ADR-0060 distill ingests only `activity` records (comment/reply/post), and `_episode_source_kind` maps every activity to `self`, every distilled pattern is `self_reflection → generated`. The external world (the post engaged with, the other agent's comment) still enters distillation — but as grounding *text inside* the rich render, not as a provenance kind, and it was never counted by this tally. ADR-0082 retired the third key: `observed` had been structurally zero since ADR-0060 and read as an external-grounding metric it never was, so the key and its `external_reply` arm are gone rather than annotated (an `external_reply` row now degrades to `unknown`). Records written before 2026-07-25 still carry `observed`; read the tally with `.get(key, 0)`, not a fixed key set.

### weekly-analysis  [`scripts/weekly-analysis.sh`, ADR-0040]

Runs outside the agent process (launchd → `claude -p`), assembling a prompt from operator-facing artifacts plus **three deterministic intakes**, then a diagnosis companion (`weekly-report-diagnosis` skill) produces the F sections.

```text
collect: daily comment-reports + data-repo state diff + previous N reports
       + log_anomaly_sweep.py    (event stream: *.log + audit.jsonl; novelty state)
       + state_invariant_check.py (accumulated state: knowledge.json / agents.json)
       + cross_day_duplicate_scan.py (published-body identity: episode logs → digests)
generate: claude -p → weekly-<end>.md.tmp
promote:  mv tmp → weekly-<end>.md        (atomic; a failure leaves the prior report)
       →  mv sweep-state.pending → sweep-state   (novelty baseline committed ONLY here)
translate: best-effort .ja.md (sonnet); failure never rolls back the two promotes
```

Order is load-bearing. The sweep's Δ / 🆕 columns are defined against its last committed snapshot, so it runs `--no-update --emit-state` and the baseline is committed after the report lands — a run that produces nothing must spend nothing (findings F1.2; two consecutive weeks lost). The invariant check and the duplicate scan hold no state and are absolute readings, so they need no such ordering.

The sweep's signature is keyed on **level + message**, with the dotted `%(name)s` module path dropped for lines in the runtime's own log format, and hex-shaped ids squashed to `#` alongside digit runs. The 80-character cap is the reason: the module path alone runs to ~47 characters, so keying on it spent the budget on the address and truncated the predicate — `"reply on <id> created but verification failed"` rendered as `"reply on <id> created"`, a failure displayed as its own opposite (findings F1.1). Excluding the name also makes the instrument refactor-invariant: a pure module move (`7c96e0f`) used to reset every affected signature to 🆕, i.e. the Δ / 🆕 columns measured the codebase rather than the runtime (findings F1.2). The trade is that the same message from two subsystems now merges into one row, so the logger name is carried as a display-only `Origin` column — it never enters the signature, the state file or the novelty computation, so the reader keeps the distinction the key deliberately drops.

Injection boundary: the sweep and the invariant check must never read episode logs. The duplicate scan does, and is the only intake permitted to — it emits **only** 12-hex SHA-256 digests, counts, filename-derived dates and the fixed `{post, reply, comment}` vocabulary (ADR-0083, gated by `TestOutputBoundary`). All three are observability: a failure degrades to a "not available" stub and never breaks the report.

### weekly-pipeline  [`scripts/weekly-pipeline.sh`, ADR-0085]

The unattended Saturday chain wrapping weekly-analysis as its Stage 1. Every LLM stage is a separate fresh-context `claude -p` session (role separation across sessions, not inside one); everything the human reads is computed by deterministic scripts. The chain never commits, pushes, or adopts.

```text
Stage 1 report:    weekly-analysis.sh (unchanged, above)
Stage 2 diagnosis: claude -p "/weekly-report-diagnosis <report>" → weekly-<end>-findings.md
Stage 3 parse:     parse_findings.py → F1 list + scope (code | prompt; ambiguity → prompt)
Stage 4 fix:       per code-scope F1: git worktree @ HEAD → claude -p (fix-implementation.md)
                   → orchestrator-run Verify (uv sync --frozen / ruff / lint-imports / pytest)
                   → ≤2 attempts/round (retry input includes Verify failure) → diff snapshot
                   → advisory review (fix-review.md); CONCERNS feeds back into ≤1 re-entry
                   round (unchanged diff → no re-review; a round that breaks Verify rolls
                   back to the previous verified diff) → export .patch. ALL round verdicts
                   + the final review body are inlined in the packet — CONCERNS never
                   blocks export (inspector, not approver)
                   prompt-scope F1: draft diff only, no Verify, full text at the gate
Stage 5 insight:   read-only recommendation pass over .staged/ (insight-recommendation.md)
Stage 6 improve:   only when the same reason code recurred 2 consecutive runs (check-improvement)
Stage 7 packet:    build_decision_packet.py → weekly-<end>-packet.md
                   + phase:"auto" record → logs/pipeline-metrics.jsonl
```

Bounds: ≤5 findings/week, per-session timeouts, 3h wall-clock deadline. Fail-forward: every stage failure becomes a reason code and the packet is still built (only a missing Stage-1 report aborts). Audit: every event → `logs/weekly-pipeline-audit.jsonl` (ADR-0075; the packet builder replays it). Promotion is the Saturday `/weekly-gate` session: apply → re-Verify → single human commit, prompt diffs full-text, `adopt-staged`, then a `phase:"gate"` metrics record. `scripts/pipeline_watchdog.sh` (pure bash, no claude/uv PATH dependency) checks each job's terminal artifact on anchored deadlines and rewrites `reports/PIPELINE-STATUS.md` + Notification Center on a changed failure set.

### submolt-scan  [`adapters/moltbook/submolt_scope.py`, ADR-0086]

```text
CLI submolt-scan (own launchd job, default Thu 03:00 JST; takes the run lock)
  client.list_submolts()            GET /submolts — the only discovery read
  → candidate set = listing ∪ subscribed_submolts   (subscribed = the baseline)
  → per submolt, in name order:
      skip is_private / is_nsfw                      reason: private | nsfw
      abort if terminal 429s ≥ 2 since the sweep began   aborted_rate_limit
      abort if read budget below reserve                 aborted_read_budget
      abort if 1000 posts already scored this sweep      aborted_scored_cap
      GET /submolts/{name}/feed → first sample_size (default 20 = one page)
        feed error → skip that submolt only           reason: feed_{status}
      → per post: score_relevance_detailed(caller="moltbook.submolt_scope")
        inside circuit_shield()
        → one `score` record (score + reason + subscribed label + body b64)
  → `scan_end` record with the verdict, `scanned` and `skipped`
```

Read-only and gate-free by construction: no subscribe, no write of any verb,
nothing written outside `submolt-scope-*.jsonl`, and the `_passes_content_gates`
submolt trust boundary is untouched — so no sampled post can reach an outward
action. `configure_submolt_scope` without an audit dir — or
`MOLTBOOK_SUBMOLT_SCOPE_DISABLE=1`, the switch an operator can actually reach
since the CLI always supplies a log dir — disables the whole sweep.

Read with `report --days N --submolt-scope`, which prints subscribed and
unsubscribed hit rates against `domain.relevance_threshold` side by side,
grouping by the CURRENT `domain.json` rather than the label each record
carried when it was written. The reading separates "judged low" from "not
judged" — a row with no real judgments reports no percentage at all — so a
scorer outage cannot read as an irrelevant feed, and it keeps a row for every
submolt the sweep touched, including one whose feed came back empty or 403'd.
That last part is the dead-submolt signal: dropping those rows is how the
first smoke run reported 19 submolts after scanning 20.

### meditate  [`adapters/meditation/`]

```text
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

```text
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
