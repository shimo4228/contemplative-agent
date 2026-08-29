<!-- Generated: 2026-08-01 | Updated: 2026-08-29 (RFC-0016 — insight_surprise.py restored to the module graph) | Updated: 2026-08-22 (ADR-0097: rules-distill / rules-stocktake retired, insight_surprise.py and rules_distill.py removed, skill-stocktake reduced) | Files scanned: 80 non-__init__ modules (72 src/ + 8 evals/) | Token estimate: ~6159 -->
# Moltbook Agent Codemap

Bird's-eye view of the entire codebase. For deep dives, see
[core-modules.md](core-modules.md) and [adapters-moltbook.md](adapters-moltbook.md).

**Counting convention**: module counts = non-`__init__` `.py` files.

## Module Dependency Graph

```text
cli/ (package, ADR-0079)  -- composition root, only layer importing both core/ and adapters/
    __init__.py (135L)        -- global flags + COMMANDS aggregation + tier dispatch + main
    registry.py (104L)        -- CommandSpec / Tier: each module declares its own commands
    __main__.py (7L)          -- `python -m contemplative_agent` entry
    agent_cmds.py (181L)      -- register / status / run / solve (Agent tier; run holds the run lock + session_id)
    runtime.py (146L)         -- shared helpers, _repo_root()
    approval.py (231L)        -- approval-gate loop + audit.jsonl writer (ADR-0012)
    staging.py (181L)         -- insight --stage / pending-review staging dir
    adopt.py (1443L)          -- adopt-staged: plan / dispatch / report over the staging dir (--archive-names enters the exit here)
    skill_archive.py (466L)   -- the ADR-0097 D5 exit, split plan/apply: _plan_archive decides without reading, _apply_archive_plan is the only mutation (skills/.archive/, supersedes:/superseded_by:)
    remove_skill.py (330L)    -- remove-skill: flags, the two gates narrower than the primitive's, dry run, prompt, and the three audit sources (archive / remove / purge)
    store_paths.py (132L)      -- containment predicates shared by the staged write and the archive move; one implementation each, which is what the containment argument rests on
    stocktake_cmd.py (197L)   -- skill-stocktake (quality report + usage reading + description audit; ADR-0097 retired rules-stocktake and the merge/clean/stage phases)
    memory_cmds.py (563L)     -- distill / insight / amend-constitution / shadow-constitution / distill-identity commands (rules-distill retired by ADR-0097)
    session_cmds.py (572L)    -- init / report / generate-report / meditate / sync-data / dialogue / dialogue-peer
    schedule.py (649L)        -- install-schedule / launchd plist generation (ADR-0085: --weekly-pipeline + --watchdog)
 -> core/
 |    _io.py (317L)                -- file I/O (write_restricted, truncate, archive_before_write)
 |    run_context.py (34L)         -- ADR-0078: mints process-wide run_id; set/clear session_id, read by _io.py writer
 |    config.py (46L)             -- security constants (FORBIDDEN_*, VALID_*, MAX_*)
 |    domain.py (406L)            -- DomainConfig + PromptTemplates + constitution loader
 |    prompts.py (77L)            -- lazy-loading proxy to config/prompts/*.md
 |    llm/ (package, 2121L, ADR-0079) -- __init__.py facade (transport+generation) + backend.py (Protocol+circuit breaker) + prompting.py (system-prompt assembly) + guard.py (sanitize/SSRF) + request.py (frozen GenerationRequest/ResolvedRequest); identity.md read as single blob (ADR-0030)
 |    embeddings.py (147L)         -- /api/embed wrapper (nomic-embed-text) + cosine + embed_one/embed_texts
 |    episode_embeddings.py (170L)-- EpisodeEmbeddingStore (SQLite sidecar, ADR-0019)
 |    episode_log.py (89L)      -- Layer 1: append-only JSONL episode storage
 |    knowledge_store.py (396L)   -- Layer 2: patterns JSON + provenance/bitemporal (ADR-0021; trust retired ADR-0051); is_live/effective_importance/pattern_id/epistemic_counts (ADR-0050)
 |    memory.py (289L)            -- Layer 3 facade (delegates to memory_repos.py) + Interaction/PostRecord (Insight retired, ADR-0052)
 |    memory_repos.py (427L)     -- InteractionIndex / FollowState / PostHistory / CommentLedger, the four stores behind the facade (split from memory.py, ADR-0079)
 |    views.py (344L)             -- ViewRegistry (seed_from + ${VAR}, lazy centroid cache, pure cosine rank — ADR-0051)
 |    snapshot.py (240L)          -- write_snapshot + collect_thresholds (pivot snapshots, ADR-0020)
 |    scheduler.py (213L)         -- rate limit scheduling, persistence
 |    distill.py (917L)           -- per-episode grounded distill orchestration (ADR-0060) + identity distill (single-stage, ADR-0050) + durability postgate (ADR-0084); rendering/dedup extracted per ADR-0079
 |    pattern_dedup.py (177L)     -- embedding-cosine add/update/skip dedup decisions, extracted from distill.py (ADR-0079)
 |    episode_render.py (181L)    -- episode→prompt-text projection, extracted from distill.py (ADR-0079)
 |    insight.py (808L)           -- global clustering → behavior skill extraction (ADR-0050); novelty gate extracted per ADR-0079; ADR-0096 in-band abstain (the separate worth judge retired by ADR-0097)
 |    insight_novelty.py (434L)   -- ADR-0074 LLM novelty gate, extracted from insight.py (ADR-0079); re-exports text_utils.skill_theme
 |    insight_surprise.py (301L)  -- ADR-0096 read-only surprise reading over the recent distillation window; enumerated for the human gate, never applied (restored by RFC-0016)
 |    skill_selection.py (534L)    -- pass-1 skill selection, write side: ADR-0076 log + ADR-0081 two-pass injection enforcement
 |    selection_window.py (170L)   -- shared day/window base for the two selection-log instruments
 |    selection_metrics.py (919L)  -- ADR-0071 instrument: per-window reading of the selection log
 |    never_selected_metrics.py (669L) -- ADR-0097 D5 instrument: never-selected exposure, strict + dormant
 |    constitution.py (151L)      -- constitutional amendment; ADR-0033 framing + ADR-0050 lineage
 |    constitution_shadow.py (278L) -- ADR-0092 read-only shadow instrument: patterns-only synthesis (no live constitution injected), divergence cosine/sha256 -> logs/constitution-shadow.jsonl
 |    stocktake.py (335L)         -- skill quality report + ADR-0081 usage reading + description audit (ADR-0097 reduced it: no grouping / merge / clean); run_rules_quality_check for the rules layer's maintenance reading
 |    report.py (321L)            -- activity report generation (JSONL → Markdown)
 |    metrics.py (189L)           -- session metrics aggregation
 |    view_metrics.py (388L)      -- read-only pattern-composition instruments: consumed-view supply + seed-independent diversity (ADR-0071/0072)
 |    text_utils.py (214L)         -- shared Markdown helpers incl. skill_theme + read_markdown_documents [ADR-0035 PR2, ADR-0048]
 |    thresholds.py (83L)         -- centralized thresholds with ADR + calibration annotations [ADR-0035 PR2]
 |    artifact_extraction.py (125L)-- shared extract_title → slugify → path-escape guard chain [ADR-0035 PR3a]
 |    clustering.py (137L)       -- average-linkage cosine agglomerative clustering (numpy-only)
 |
 -> adapters/moltbook/
 |    config.py (113L)             -- URLs, paths, timeouts, rate limits
 |    agent.py (906L)             -- session orchestrator (feed/reply/post cycles)
 |    session_context.py (133L)    -- shared session state contract
 |    feed_manager.py (544L)      -- feed fetch, scoring, engagement, ID dedup, promo + author rate limit
 |    reply_handler.py (489L)     -- notification reply processing; pre-action internal_note (ADR-0045)
 |    post_pipeline.py (481L)     -- feed-seeder → NoveltyGate → test-content + body-hash gates → post
 |    publish.py (125L)           -- shared outward-write policy: 429->rate-limited guard, create-response verification handshake, published-body logging
 |    client.py (967L)            -- HTTP client (auth, domain lock, retry/429-backoff)
 |    auth.py (106L)              -- credential management, register
 |    verification.py (649L)      -- math solver chain (code_parse → guarded LLM → abstain) + challenge audit log
 |    verification_parse.py (1693L)-- deterministic finite-grammar CAPTCHA parser (code_parse_challenge; ADR-0062 11th amendment)
 |    content.py (78L)            -- rules-based content + axiom intro injection
 |    llm_functions.py (559L)     -- Moltbook-specific LLM functions
 |    dedup.py (257L)             -- deterministic gates: prefix-5 stem + Jaccard, test-content, promo regex
 |    novelty.py (374L)          -- NoveltyGate: embedding novelty + temporal decay + Lagrangian (ADR-0039)
 |    feed_seeder.py (84L)       -- select_feed_seeds: RNG peer-post sampling per submolt (ADR-0043)
 |    submolt_scope.py (761L)    -- ADR-0086 read-only submolt-scope instrument (submolt-scan sweep + report --submolt-scope reading)
 |
 -> adapters/meditation/  (experimental)
 |    config.py (54L)             -- state space definition, parameters
 |    pomdp.py (326L)             -- JSONL → POMDP matrices (numpy)
 |    meditate.py (228L)          -- Active Inference loop (flat single-level POMDP, ADR-0049)
 |    report.py (157L)            -- result interpretation (display-only) → results.json
 |
 -> adapters/dialogue/
      peer.py (190L)             -- 2-agent peer-to-peer dialogue loop (stdin/stdout, independent processes)

 -> testing/  (ADR-0088, shipped in the wheel but not production code)
      __init__.py (83L)          -- public entry: run_conformance(backend) -> ConformanceReport
      __main__.py (198L)         -- `python -m contemplative_agent.testing --backend pkg.mod:Name` CLI
      backend_contract.py (619L) -- the LLMBackend Protocol conformance checks a sibling backend
                                    (contemplative-agent-cloud / -mlx) must pass; imports stdlib +
                                    core.llm only -- no pytest, no adapters, no cli
      backend_probe.py (139L)    -- construct/introspect a backend class from a dotted path string
    Two import-linter `forbidden` contracts (not a fourth `layers` tier): no production layer
    imports testing/, and testing/ imports core only. Invoked via
    `scripts/check-sibling-backends.sh`, not the daily verify.sh (constructs sibling code).

config/                           -- externalized templates (domain-swappable, git-managed)
  domain.json                     -- submolts, thresholds
  prompts/*.md                    -- LLM prompt templates with {placeholders}
  views/*.md                      -- seed-text view definitions (packaged fallback for ADR-0019; consumed set only, ADR-0073)
  templates/<character>/          -- ethical framework templates (one dir per character)

evals/                            -- LLM behavioral eval layer (ADR-0089), outside src/ and the
                                      wheel; deterministic core imports stdlib + contemplative_agent
                                      only, only adapter_deepeval.py/run_eval.py import deepeval
  dataset.py / judging.py / generation.py / compare.py   -- deterministic core (unit-tested, dev group)
  adapter_deepeval.py / run_eval.py                       -- deepeval wiring, `[dependency-groups] eval`
  check_staleness.py                -- compares approved baseline's manifest against tree state
                                        (fixtures/dataset/judge-prompt/prompt-templates/domain.json/
                                        sampling/model/injection_regime); advisory warning in verify.sh
  snapshot_assets.py                -- pins identity.md/constitution/skills/rules into
                                        evals/fixtures/agent_home/ + sha256 manifest before scoring
  baselines/                        -- approved comparison baselines (human-approved, not auto-committed)
  Manual run only (`uv run --group eval python -m evals.run_eval`); not wired into verify.sh
  (slow + stochastic). See architecture.md § Data Flow -- Behavioral Eval.

~/.config/moltbook/               -- runtime data (env var MOLTBOOK_HOME)
  identity.md                     -- agent persona (updated by distill-identity)
  knowledge.json                  -- learned patterns (embedding + gated + last_view_matches)
  embeddings.sqlite               -- episode embedding sidecar (ADR-0019)
  constitution/                   -- ethical principles
  views/*.md                      -- user-customised seed views
  skills/*.md                     -- behavior patterns (insight)
  rules/*.md                      -- universal rules (Practice/Rationale; promoted from co-selection families via stocktake_merge_rules.md — ADR-0097 D7)
  snapshots/{cmd}_{ts}/           -- pivot snapshots (ADR-0020: manifest + views + constitution + centroids.npz)
  logs/YYYY-MM-DD.jsonl           -- daily episode log (append-only, 0600)
  logs/audit.jsonl                -- approval history incl. snapshot_path + source_ids + epistemic_counts (ADR-0020/0050)
  logs/verification-audit.jsonl   -- base64 challenge corpus + solve/verify outcome
  reports/                        -- activity reports + analysis/ (weekly)
  agents.json                     -- followed agents (0600)
  rate_state.json                 -- request budgets, timestamps (0600)
  credentials.json                -- API key + agent_id (0600)
  commented_cache.json            -- post dedup cache (0600)
```

**Totals: see [INDEX.md § Statistics](INDEX.md#statistics)**

## Key Classes

| Class | File | Role |
|-------|------|------|
| `Agent` | adapters/moltbook/agent.py | Session orchestrator |
| `AutonomyLevel` | adapters/moltbook/agent.py | Enum: APPROVE/GUARDED/AUTO |
| `SessionContext` | adapters/moltbook/session_context.py | Shared mutable state |
| `FeedManager` | adapters/moltbook/feed_manager.py | Feed engagement + gates |
| `ReplyHandler` | adapters/moltbook/reply_handler.py | Notification replies |
| `PostPipeline` | adapters/moltbook/post_pipeline.py | Self-post generation + dedup gates |
| `NoveltyGate` | adapters/moltbook/novelty.py | Embedding novelty + temporal decay + Lagrangian (ADR-0039) |
| `MoltbookClient` | adapters/moltbook/client.py | HTTP client (domain lock, 429 backoff) |
| `VerificationTracker` / `VerificationSolveResult` | adapters/moltbook/verification.py | Math challenge solve state, audit path, auto-stop |
| `ContentManager` | adapters/moltbook/content.py | Content gen + axiom intro |
| `EpisodeLog` | core/episode_log.py | Append-only JSONL |
| `EpisodeEmbeddingStore` | core/episode_embeddings.py | SQLite sidecar for episode vectors |
| `KnowledgeStore` | core/knowledge_store.py | Patterns JSON + telemetry |
| `MemoryStore` | core/memory.py | Facade over 3-layer memory |
| `ViewRegistry` | core/views.py | Seed-text views, lazy centroid cache |
| `Scheduler` | core/scheduler.py | Rate limit enforcement |
| `DomainConfig` / `PromptTemplates` | core/domain.py | @dataclass(frozen=True) |

## CLI Commands

```text
contemplative-agent init [--template <character>] [--config-dir PATH]
contemplative-agent register [--username U] [--password P]
contemplative-agent status
contemplative-agent run [--session M] [--approve|--guarded|--auto]

# Offline learning (ADR-0012 approval gate; pivot snapshots ADR-0020)
contemplative-agent distill [--days N] [--dry-run] [--file PATH ...]
contemplative-agent distill-identity [--stage]
contemplative-agent insight [--stage] [--full]   -- incremental needs .last_insight marker; LLM novelty gate; --stage refuses on pending review (ADR-0074)
contemplative-agent adopt-staged [-y] [--adopt-names FILE [--reject-rest]] [--archive-names FILE]   -- per-item non-interactive path matches by staged filename (audit source stage-adopted-names); unknown/empty names abort before any destructive op (T-ADOPT-PERITEM). --archive-names retires STORE skills after the adoption loop (ADR-0097 D5); lines are `old.md` or `old.md superseded-by new-staged-name.md`, the pairing writing supersedes:/superseded_by:. Same abort contract as the other two name files, and a name appearing in two of the three exits 2 with nothing moved
contemplative-agent remove-skill <name> --reason TEXT [--delete]   -- archives into skills/.archive/ by default since ADR-0097 D5 (retirement is a move, never an unlink); --delete restores the old unlink. --reason stays mandatory: a written reason is what stops just-in-case retention (CREW)
contemplative-agent amend-constitution
contemplative-agent shadow-constitution   -- ADR-0092 read-only instrument: patterns-only synthesis (current constitution NOT in the prompt), divergence cosine + sha256 baked into logs/constitution-shadow.jsonl; no approval gate (writes only the record)

# Audit (read-only since ADR-0097: quality report + usage reading + advisory description audit)
contemplative-agent skill-stocktake

# Instruments (read-only, wired to no gate)
contemplative-agent submolt-scan [--sample-size N]   -- ADR-0086 scope sweep: samples + scores every listed submolt (subscribed and not); takes the run lock

# Reports
contemplative-agent report [--days N] [--patterns] [--skill-selection] [--submolt-scope]
contemplative-agent report [--date YYYY-MM-DD]
contemplative-agent generate-report [--all]

# Misc
contemplative-agent solve "TEXT"
contemplative-agent meditate [--days N] [--cycles N] [--dry-run]
contemplative-agent dialogue HOME_A HOME_B --seed "..." [--turns N]
contemplative-agent sync-data        # rsync→embedding-free knowledge.json export→git push to data repo; then best-effort hf upload of patterns.jsonl
contemplative-agent install-schedule [--interval H] [--session M]
                                     [--distill-hour H] [--no-distill]
                                     [--weekly-insight] [--weekly-insight-day D]
                                     [--weekly-insight-hour H]
                                     [--weekly-backup] [--weekly-backup-day D]
                                     [--weekly-backup-hour H]
                                     [--weekly-submolt-scan] [--weekly-submolt-scan-day D]
                                     [--weekly-submolt-scan-hour H]
                                     [--weekly-pipeline] [--weekly-pipeline-day D]
                                     [--weekly-pipeline-hour H]
                                     [--watchdog] [--uninstall]
                                     # --weekly-backup: private off-site mirror of MOLTBOOK_HOME
                                     # incl. logs/ (scripts/backup-runtime.sh; excludes credentials.json)
                                     # --weekly-pipeline: unattended chain (ADR-0085/0098; materials →
                                     # one /weekly-report session (report + diagnosis + candidate
                                     # filing) → instrument scans). Runs weekly-analysis.sh as its
                                     # materials collector. The standalone --weekly-analysis
                                     # install path was removed 2026-08-29.
                                     # --watchdog: pure-bash artifact-deadline checks (scripts/
                                     # pipeline_watchdog.sh) → reports/PIPELINE-STATUS.md + notifications

Global flags: --config-dir PATH | --domain-config PATH | --constitution-dir PATH
              --no-axioms | --approve/--guarded/--auto
```

**Migration commands** (`embed-backfill` / `migrate-patterns` / `migrate-categories`) retired by ADR-0035. Use from a v2.0.x release tag for v1.x store recovery.

## Prompt Templates

In `config/prompts/*.md`, lazy-loaded via `core/prompts.py`:

**Engagement & posting**: system, relevance, comment, reply, cooperation_post, post_title, topic_summary, submolt_selection, internal_note (ADR-0045), dialogue (peer loop) — `session_insight` retired and deleted (ADR-0052)

**Distillation**: distill_episode (per-episode grounded distill, ADR-0060 — this is the live distill prompt; first-person moment-indexed register instruction since ADR-0072), identity_distill, insight_extraction (naming/vocabulary discipline since ADR-0074), insight_novelty + insight_novelty_system (novelty gate, ADR-0074), constitution_amend, constitution_synthesize (ADR-0092 shadow instrument — patterns-only, no `{current_constitution}` placeholder by design) (`distill` / `distill_refine` went dead when ADR-0060 replaced the 2-step batch with `distill_episode`; files + mappings deleted in ADR-0072. `distill_importance` retired, ADR-0056; `insight_worth`, `rules_distill`, `rules_distill_refine` retired, ADR-0097)

**Verification**: solver order is `code_parse` → `llm_extract` → abstain (ADR-0062 9th amendment — the free-reasoning `llm_reason` fallback was retired after the round-7 audit measured it at 2.3% of traffic / 38% verify success). `verification.py` wraps the challenge as untrusted and first runs the deterministic `code_parse_challenge()` (in `verification_parse.py`), which owns the finite CAPTCHA grammar's arithmetic / number-word reconstruction and abstains to `None` on any ambiguity. Only on abstention does the LLM propose arithmetic via verification_solve_extract_system (short EXPR/FINAL extraction), accepted only when Python recomputation matches the stated final answer; past that the solver abstains instead of guessing, with `abstain_reason="reason_fallback_disabled"` when the model answered and the guards rejected it, `"llm_none"` when the call produced no text at all (ADR-0062 12th amendment — the failure kind stays in the `llm-calls` telemetry row), or `"answer_previously_rejected"`. `Agent._handle_verification()` writes `logs/verification-audit.jsonl` with a base64-encoded challenge, SHA-256s, `solver_path`, answer, `/verify` outcome, and the abstain reason in `error`, for corpus-driven solver evaluation (ADR-0062 amendment).

**Audit**: stocktake_description + stocktake_description_system (ADR-0081 description-fidelity audit — the one LLM call left in `skill-stocktake`), stocktake_merge_rules (shared-core synthesis, kept as the family-to-rule promotion prompt — ADR-0097 D7). `stocktake_skills` / `stocktake_rules` / `stocktake_merge` / `stocktake_clean` and their three `*_system` prompts were retired by ADR-0097

**Untrusted boundary** (ADR-0054): untrusted_wrapper, untrusted_marker_complete, untrusted_marker_truncated — externalized text for `wrap_untrusted_content`, with a hardcoded code fallback that re-asserts the injection defense if the template is missing or gutted

**Experimental**: meditation_interpret

**Script-read (NOT lazy-loaded via `core/prompts.py`)**: `principles.md` and `weekly-analysis.md` live in `config/prompts/` and feed the materials file `scripts/weekly-analysis.sh` builds for the `/weekly-report` session; `weekly-analysis-ja.md` is that session's Japanese-rendering contract (ADR-0040 / ADR-0098) — none are read by the agent's prompt loader. The collector embeds four deterministic intakes rendered by `scripts/`: `log_anomaly_sweep.py`, `state_invariant_check.py`, `cross_day_duplicate_scan.py`, `api_drift_scan.py`; a fifth (`dead_code_scan.py`, T-DEADCODE-INTAKE) and a sixth (`value_layer_due_check.py`, the ADR-0091 value-layer cadence reading — which since ADR-0097 also owns the rules-layer maintenance reading behind `--rules-dir`) run in `weekly-pipeline.sh` itself and write per-week JSONs the Saturday gate reads directly (the decision-packet builder retired with ADR-0098). Separate from all of these is one **operator-run** read-only instrument that no schedule invokes — `scripts/retrieval_recall_measure.py` (offline lexical / cosine / RRF-union recall@k against reviewer-named covering skills, ADR-0097 D6); the author runs it and reads the numbers. Its sibling `scripts/coselection_families.py` (co-selection sibling / sub-case pairs and family any-of rates, ADR-0097 D5/D7) was **retired 2026-08-29** — zero consumers after RFC-0013 was withdrawn; the canonical numbers stay in the ADR-0097 unit-C Note (see [architecture.md § weekly-analysis](architecture.md#weekly-analysis--scriptsweekly-analysissh-adr-0040)).

## LLM Function Surface

| Function | Module | Used by |
|----------|--------|---------|
| `score_relevance(post)` | adapters/moltbook/llm_functions | FeedManager |
| `generate_comment(post)` | adapters/moltbook/llm_functions | FeedManager |
| `generate_reply(...)` | adapters/moltbook/llm_functions | ReplyHandler |
| `generate_cooperation_post(feed_seeds, ...)` | adapters/moltbook/llm_functions | PostPipeline (ADR-0043) |
| `format_feed_seeds(seeds, ...)` | adapters/moltbook/llm_functions | PostPipeline (ADR-0043) |
| `select_feed_seeds(posts, ...)` | adapters/moltbook/feed_seeder | PostPipeline (ADR-0043) |
| `generate_post_title(seed_text)` | adapters/moltbook/llm_functions | PostPipeline |
| `summarize_post_topic(content)` | adapters/moltbook/llm_functions | PostPipeline |
| `select_submolt(...)` | adapters/moltbook/llm_functions | PostPipeline |
| `generate(prompt, system, ...)` | core/llm | distill, insight, rules, constitution, stocktake |

## Persistent State Files

| File | Format | Location | Purpose |
|------|--------|----------|---------|
| `credentials.json` | JSON (0600) | `MOLTBOOK_HOME` | API key + agent ID |
| `rate_state.json` | JSON (0600) | `MOLTBOOK_HOME` | POST/GET budgets, timestamps |
| `logs/YYYY-MM-DD.jsonl` | JSONL (0600) | `MOLTBOOK_HOME` | Daily episodes |
| `agents.json` | JSON (0600) | `MOLTBOOK_HOME` | Followed agents list |
| `commented_cache.json` | JSON (0600) | `MOLTBOOK_HOME` | Post dedup cache |
| `knowledge.json` | JSON | `MOLTBOOK_HOME` | Patterns + embedding + gated + last_view_matches |
| `embeddings.sqlite` | SQLite | `MOLTBOOK_HOME` | Episode embedding sidecar (ADR-0019) |
| `identity.md` | Markdown | `MOLTBOOK_HOME` | Agent persona |
| `constitution/*.md` | Markdown | `MOLTBOOK_HOME` | Ethical clauses |
| `views/*.md` | Markdown | `MOLTBOOK_HOME` | User-editable seed views |
| `skills/*.md` | Markdown | `MOLTBOOK_HOME` | Behavior patterns (insight) |
| `rules/*.md` | Markdown | `MOLTBOOK_HOME` | Universal rules (Practice/Rationale; family promotion, ADR-0097) |
| `snapshots/{cmd}_{ts}/` | dir | `MOLTBOOK_HOME` | Pivot snapshots (ADR-0020) |
| `history/identity/` | Markdown | `MOLTBOOK_HOME` | Identity archives |
| `logs/audit.jsonl` | JSONL | `MOLTBOOK_HOME` | Approval history + source_ids + epistemic_counts (ADR-0020/0050) |
| `logs/skill-usage-*.jsonl` | JSONL | `MOLTBOOK_HOME` | Historic skill log (ADR-0023 sunset ADR-0036; no new files; observation evidence only) |
| `logs/llm-calls-*.jsonl` | JSONL (0600) | `MOLTBOOK_HOME` | Per-call LLM telemetry, two row kinds keyed by `caller`. **Generation**: caller/model/tokens/duration/outcome/`think` (trace requested) + `thinking_source` (which channel delivered it, or `absent`) + sparse `thinking_fallback_reason` (why it did not, ADR-0068 amendment). **Embedding** (`caller="embed"`, `embed_texts` via the `emit_llm_telemetry` seam): model/`batch_size`/`input_chars`/`rows`/duration/outcome + sparse `error_kind`. Neither kind carries prompt bodies, embedded texts, or trace content (sha256 prefix only). Field-by-field: [otel-semconv-mapping.md](../otel-semconv-mapping.md) |
| `logs/verification-audit.jsonl` | JSONL (0600) | `MOLTBOOK_HOME` | Verification challenge corpus/outcome log: `challenge_b64`, `challenge_sha256`, hashed code, answer, solver_path, verify_success, plus the create-time columns `action` (`comment`/`reply`/`post`, `None` off the create path), `target_sha256` (digest only, ADR-0083) and `content_recorded` — so an orphaned publish (created on-platform, deliberately unrecorded) is countable per kind |

## Security Boundaries

```text
External Input              Validation
--------------              ----------
post_id                     VALID_ID_PATTERN ([A-Za-z0-9_-]+)
LLM output                  _sanitize_output() (FORBIDDEN_* + cap length)
Feed content                wrap_untrusted_content() + 1000 char cap
Knowledge context           wrap_untrusted_content()
Identity file               FORBIDDEN_SUBSTRING_PATTERNS + archive
domain.json / rules/*.md    FORBIDDEN_SUBSTRING_PATTERNS on raw content
HTTP redirects              allow_redirects=False
API domain                  ALLOWED_DOMAIN (www.moltbook.com only)
Ollama URL                  LOCALHOST_HOSTS + OLLAMA_TRUSTED_HOSTS
```

See ADR-0007 (security boundary model).

## Performance & Rate Limiting

**3-layer defense**:

1. `Scheduler.has_read_budget()` / `has_write_budget()` — proactive budget check
2. Adaptive waiting — sleep before hitting limits
3. 429 backoff — exponential retry (cap 300s per Retry-After)

**Budgets**: GET 60 req/min, POST 30 req/min (separate quotas, daily reset UTC midnight)
**Circuit breaker** (core/llm/backend.py): 5 consecutive Ollama failures → 120s cooldown
**Verification stop**: 7 consecutive challenge failures → `SessionContext.rate_limited = True`
