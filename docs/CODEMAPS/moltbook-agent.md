<!-- Generated: 2026-05-05 | Files scanned: 43 | Token estimate: ~1850 -->
# Moltbook Agent Codemap

Bird's-eye view of the entire codebase. For deep dives, see
[core-modules.md](core-modules.md) and [adapters-moltbook.md](adapters-moltbook.md).

## Module Dependency Graph

```
cli.py (1826L)  -- composition root, only file importing both core/ and adapters/
 -> core/  (25 modules)
 |    _io.py (46L)                -- file I/O (write_restricted, truncate, archive_before_write)
 |    config.py (28L)             -- security constants (FORBIDDEN_*, VALID_*, MAX_*)
 |    domain.py (362L)            -- DomainConfig + PromptTemplates + constitution loader
 |    prompts.py (~70L)           -- lazy-loading proxy to config/prompts/*.md
 |    llm.py (553L)               -- Ollama interface + LLMBackend Protocol, circuit breaker; _build_system_prompt reads identity.md as single blob (legacy path restored by ADR-0030)
 |    embeddings.py (144L)        -- /api/embed wrapper (nomic-embed-text) + cosine + embed_one/embed_texts
 |    episode_embeddings.py (174L)-- EpisodeEmbeddingStore (SQLite sidecar, ADR-0019)
 |    episode_log.py (~100L)      -- Layer 1: append-only JSONL episode storage
 |    knowledge_store.py (335L)   -- Layer 2: patterns JSON + provenance/trust/bitemporal (ADR-0021; forgetting/feedback retired by ADR-0028) + view telemetry (ADR-0020)
 |    memory.py (499L)            -- Layer 3 facade + Interaction/PostRecord/Insight + helpers
 |    views.py (309L)             -- ViewRegistry (seed_from + ${VAR}, lazy centroid cache, embedding cosine ranking — BM25 hybrid retired by ADR-0034)
 |    snapshot.py (160L)          -- write_snapshot + collect_thresholds (pivot snapshots, ADR-0020); reads thresholds.py registry
 |    forgetting.py (33L)         -- is_live: bitemporal + trust floor retrieval gate (ADR-0021 + ADR-0028 retirement)
 |    scheduler.py (165L)         -- rate limit scheduling, persistence
 |    distill.py (823L)           -- embedding classify + 3-step distill + identity distill (whole-file legacy, restored by ADR-0030); memory_evolution pass removed by ADR-0034
 |    insight.py (282L)           -- view-driven behavior pattern extraction (knowledge → skills); uses text_utils + artifact_extraction
 |    rules_distill.py (348L)     -- Practice/Rationale B-layer rules synthesis (skills → rules); uses text_utils + artifact_extraction
 |    constitution.py (130L)      -- constitutional amendment (constitutional view → ethics); ADR-0033 layer-separation framing
 |    stocktake.py (368L)         -- skill/rule audit: embedding clustering, merge/quality, CANNOT_MERGE; uses text_utils._strip_frontmatter
 |    report.py (256L)            -- activity report generation (JSONL → Markdown)
 |    metrics.py (160L)           -- session metrics aggregation
 |    text_utils.py (60L)         -- NEW (ADR-0035 PR2): shared Markdown helpers (slugify / extract_title / _strip_frontmatter)
 |    thresholds.py (90L)         -- NEW (ADR-0035 PR2): centralized retrieval/classification thresholds with ADR + calibration annotations
 |    artifact_extraction.py (69L)-- NEW (ADR-0035 PR3a): shared extract_title → slugify → path-escape guard chain for insight/rules-distill
 |
 -> adapters/moltbook/  (12 modules)
 |    config.py (85L)             -- URLs, paths, timeouts, rate limits
 |    agent.py (609L)             -- session orchestrator (feed/reply/post cycles)
 |    session_context.py (53L)    -- shared session state contract
 |    feed_manager.py (348L)      -- feed fetch, scoring, engagement, ID dedup, promo + author rate limit
 |    reply_handler.py (394L)     -- notification reply processing (SessionContext)
 |    post_pipeline.py (195L)     -- dynamic post generation, test-content + Jaccard dedup gates
 |    client.py (448L)            -- HTTP client (auth, domain lock, retry/429-backoff)
 |    auth.py (111L)              -- credential management, register
 |    verification.py (236L)      -- obfuscated math challenge solver
 |    content.py (64L)            -- rules-based content + axiom intro injection
 |    llm_functions.py (217L)     -- Moltbook-specific LLM functions
 |    dedup.py (206L)             -- deterministic gates: prefix-5 stem + Jaccard, test-content, promo regex
 |
 -> adapters/meditation/  (4 modules, experimental)
      config.py (55L)             -- state space definition, parameters
      pomdp.py (294L)             -- JSONL → POMDP matrices (numpy)
      meditate.py (206L)          -- Active Inference cycles (temporal flattening + counterfactual pruning)
      report.py (146L)            -- result interpretation → KnowledgeStore

config/                           -- externalized templates (domain-swappable, git-managed)
  domain.json                     -- submolts, thresholds, topic keywords
  prompts/*.md (30 files)         -- LLM prompt templates with {placeholders}
  views/*.md                      -- 7 seed-text view definitions (packaged fallback for ADR-0019)
  templates/<character>/          -- 11 ethical framework templates
                                     (contemplative, stoic, utilitarian, deontologist,
                                      care-ethicist, contractarian, cynic,
                                      existentialist, narrativist, pragmatist, tabula-rasa)

~/.config/moltbook/               -- runtime data (env var MOLTBOOK_HOME)
  identity.md                     -- agent persona (updated by distill-identity)
  knowledge.json                  -- learned patterns (embedding + gated + last_view_matches telemetry)
  embeddings.sqlite               -- episode embedding sidecar (ADR-0019)
  constitution/                   -- ethical principles (init copies default, amend updates)
  views/*.md                      -- user-customised seed views (falls back to packaged)
  skills/*.md                     -- behavior patterns (insight)
  rules/*.md                      -- universal rules (rules-distill, Practice/Rationale)
  snapshots/{cmd}_{ts}/           -- pivot snapshots (ADR-0020: manifest + views + constitution + centroids.npz)
  logs/YYYY-MM-DD.jsonl           -- daily episode log (append-only, 0600)
  logs/audit.jsonl                -- approval history incl. snapshot_path cross-refs (ADR-0020)
  reports/                        -- activity reports (generate-report) + analysis/ (weekly)
  agents.json                     -- followed agents, last_update timestamp (0600)
  rate_state.json                 -- request budgets, timestamps (0600)
  credentials.json                -- API key + agent_id (0600)
  commented_cache.json            -- post dedup cache (0600)
```

**Total: 43 modules, ~11400 LOC** (test count: see [INDEX.md](INDEX.md))

## Key Classes

| Class | File | LOC | Role |
|-------|------|-----|------|
| `Agent` | adapters/moltbook/agent.py | 609 | Session orchestrator |
| `AutonomyLevel` | adapters/moltbook/agent.py | — | Enum: APPROVE/GUARDED/AUTO |
| `SessionContext` | adapters/moltbook/session_context.py | 53 | Shared mutable state |
| `FeedManager` | adapters/moltbook/feed_manager.py | 348 | Feed engagement + new gates |
| `ReplyHandler` | adapters/moltbook/reply_handler.py | 394 | Notification replies |
| `PostPipeline` | adapters/moltbook/post_pipeline.py | 195 | Self-post generation + dedup gates |
| `MoltbookClient` | adapters/moltbook/client.py | 448 | HTTP client (domain lock, 429 backoff) |
| `MoltbookClientError` | adapters/moltbook/client.py | — | Exception with status_code |
| `VerificationTracker` | adapters/moltbook/verification.py | 236 | Math challenge solver, auto-stop |
| `ContentManager` | adapters/moltbook/content.py | 64 | Content gen + axiom intro |
| `EpisodeLog` | core/episode_log.py | 98 | Append-only JSONL |
| `EpisodeEmbeddingStore` | core/episode_embeddings.py | 174 | SQLite sidecar for episode vectors (ADR-0019) |
| `KnowledgeStore` | core/knowledge_store.py | 335 | Patterns JSON + telemetry update (ADR-0020) |
| `MemoryStore` | core/memory.py | 499 | Facade over 3-layer memory |
| `ViewRegistry` | core/views.py | 309 | Seed-text views, lazy centroid cache (ADR-0019) |
| `Interaction` / `PostRecord` / `Insight` | core/memory.py | — | @dataclass(frozen=True) |
| `Scheduler` | core/scheduler.py | 165 | Rate limit enforcement |
| `DomainConfig` / `PromptTemplates` | core/domain.py | — | @dataclass(frozen=True) |

## CLI Commands (21 active subcommands; 3 migration commands sunset by ADR-0035)

```
contemplative-agent init [--template <character>] [--config-dir PATH]
contemplative-agent register [--username U] [--password P]
contemplative-agent status
contemplative-agent run [--session M] [--approve|--guarded|--auto]

# Offline learning (all gated by ADR-0012 human approval; all write pivot snapshots ADR-0020)
contemplative-agent distill [--days N] [--dry-run] [--no-axioms]
contemplative-agent distill-identity [--days N] [--dry-run]
contemplative-agent insight [--days N] [--stage] [--full]
contemplative-agent adopt-staged                            -- approve & adopt staged outputs (Tier 1, no LLM)
contemplative-agent remove-skill <name> [--reason TEXT]     -- auditable skill deletion (gated)
contemplative-agent rules-distill [--full]
contemplative-agent amend-constitution

# Migrations
# embed-backfill / migrate-patterns / migrate-categories were retired
# by ADR-0035 once active deployments finished migrating. Run them
# from a v2.0.x release tag if you arrive on main with a v1.x store.
contemplative-agent enrich [--dry-run]                             -- no-op since ADR-0009 (kept as a stable entry point)

# Audit
contemplative-agent skill-stocktake [--stage]
contemplative-agent rules-stocktake

# Reports
contemplative-agent report [--date YYYY-MM-DD]
contemplative-agent generate-report [--all]

# Misc
contemplative-agent solve "TEXT"                          -- math challenge solver
contemplative-agent meditate [--days N] [--cycles N] [--dry-run]
contemplative-agent dialogue HOME_A HOME_B --seed "..." [--turns N]   -- local 2-agent dialogue (adapters/dialogue); production ~/.config/moltbook is structurally refused
contemplative-agent sync-data                             -- sync to research repo
contemplative-agent install-schedule [--interval H] [--session M]
                                     [--distill-hour H] [--no-distill]
                                     [--weekly-analysis] [--weekly-analysis-day D] [--weekly-analysis-hour H]
                                     [--uninstall]

Global flags:
  --config-dir PATH           Override CONTEMPLATIVE_CONFIG_DIR
  --domain-config PATH        Custom domain.json
  --constitution-dir PATH    Custom constitution directory
  --no-axioms                 Disable CCAI constitutional clauses
  --approve / --guarded / --auto  Autonomy level
```

## Prompt Templates (31)

In `config/prompts/*.md`, lazy-loaded via `core/prompts.py`:

**Engagement & posting**:
- system, relevance, comment, reply, cooperation_post, post_title
- topic_extraction, topic_novelty, topic_summary, session_insight
- submolt_selection

**Distillation**:
- distill, distill_constitutional, distill_refine, distill_importance
- identity_distill, identity_refine
- insight_extraction
- rules_distill, rules_distill_refine
- constitution_amend

**Audit**:
- stocktake_skills, stocktake_rules, stocktake_merge, stocktake_merge_rules

**Reports / experimental**:
- weekly-analysis (Claude Code via launchd)
- meditation_interpret

**Legacy (present on disk, no longer called)**:
- `distill_classify.md`, `distill_subcategorize.md` — superseded by embedding classification / view batching (ADR-0019). Files retained but unreferenced.

## LLM Function Surface

| Function | Module | Used by |
|----------|--------|---------|
| `score_relevance(post)` | adapters/moltbook/llm_functions | FeedManager |
| `generate_comment(post)` | adapters/moltbook/llm_functions | FeedManager |
| `generate_reply(...)` | adapters/moltbook/llm_functions | ReplyHandler |
| `generate_cooperation_post(feed_seeds, ...)` | adapters/moltbook/llm_functions | PostPipeline |
| `format_feed_seeds(seeds)` | adapters/moltbook/llm_functions | PostPipeline (ADR-0043) |
| `select_feed_seeds(posts, ...)` | adapters/moltbook/feed_seeder | PostPipeline (ADR-0043) |
| `generate_post_title(seed_text)` | adapters/moltbook/llm_functions | PostPipeline |
| `summarize_post_topic(content)` | adapters/moltbook/llm_functions | PostPipeline (dedup gate + record) |
| `select_submolt(...)` | adapters/moltbook/llm_functions | PostPipeline |
| ~~`extract_topics(posts)`~~ | adapters/moltbook/llm_functions | _orphaned helper since ADR-0043; still exported but no production caller_ |
| ~~`check_topic_novelty(...)`~~ | adapters/moltbook/llm_functions | _orphaned helper since ADR-0043; structurally redundant with ADR-0039 NoveltyGate_ |
| `generate_session_insight(...)` | adapters/moltbook/llm_functions | Agent |
| `generate(prompt, system, ...)` | core/llm | distill, insight, rules, constitution, stocktake |

All output passes `_sanitize_output()`. All external inputs → `wrap_untrusted_content()`.
Circuit breaker: 5 consecutive LLM failures → open for 120s.

## Persistent State Files

| File | Format | Location | Purpose |
|------|--------|----------|---------|
| `credentials.json` | JSON (0600) | `MOLTBOOK_HOME` | API key + agent ID |
| `rate_state.json` | JSON (0600) | `MOLTBOOK_HOME` | POST/GET budgets, timestamps |
| `logs/YYYY-MM-DD.jsonl` | JSONL (0600) | `MOLTBOOK_HOME` | Daily episodes |
| `agents.json` | JSON (0600) | `MOLTBOOK_HOME` | Followed agents list |
| `commented_cache.json` | JSON (0600) | `MOLTBOOK_HOME` | Post dedup cache (ID-level) |
| `knowledge.json` | JSON | `MOLTBOOK_HOME` | Patterns + `embedding` + `gated` + `last_view_matches` (ADR-0019/0020) |
| `embeddings.sqlite` | SQLite | `MOLTBOOK_HOME` | Episode embedding sidecar (ADR-0019) |
| `identity.md` | Markdown | `MOLTBOOK_HOME` | Agent persona |
| `constitution/*.md` | Markdown | `MOLTBOOK_HOME` | Ethical clauses (`seed_from` source for views) |
| `views/*.md` | Markdown | `MOLTBOOK_HOME` | User-editable seed views (packaged fallback) |
| `skills/*.md` | Markdown | `MOLTBOOK_HOME` | Behavior patterns (insight) |
| `rules/*.md` | Markdown | `MOLTBOOK_HOME` | Universal rules (rules-distill, Practice/Rationale) |
| `snapshots/{cmd}_{ts}/` | dir | `MOLTBOOK_HOME` | Pivot snapshots (ADR-0020: manifest + views + constitution + centroids.npz) |
| `history/identity/` | Markdown | `MOLTBOOK_HOME` | Identity archives (timestamped) |
| `logs/audit.jsonl` | JSONL | `MOLTBOOK_HOME` | Approval history + `snapshot_path` cross-refs |
| `logs/skill-usage-YYYY-MM-DD.jsonl` | JSONL (0600) | `MOLTBOOK_HOME` | Historic skill selection + outcome log (ADR-0023, sunset by ADR-0036). Existing files preserved as observation evidence; no new files generated. |
| `reports/comment-reports/*.md` | Markdown | `MOLTBOOK_HOME` | Daily activity reports |
| `reports/analysis/weekly-*.md` | Markdown | `MOLTBOOK_HOME` | Weekly analysis (Claude Code via launchd) |
| `knowledge.json.bak.*` | JSON | `MOLTBOOK_HOME` | Pre-migration backups left on disk by the retired migration commands (ADR-0035 sunset). Recovery path for a v1.x store. |

## Security Boundaries

```
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
URL output                  defang to hxxps:// in reports (since v1.2.0+)
```

See ADR-0007 (security boundary model) for the full threat model.

## Deterministic Dedup Gates (since v1.3.0)

The agent has two layers of dedup against runaway self-similarity:

**Self-post pipeline** (post_pipeline.py):
1. `is_test_content(title, body)` blocks `Test Title` / `Dynamic content` scaffold
2. `NoveltyGate.evaluate(...)` — ADR-0039 embedding-cosine novelty with
   temporal decay + rate-deficit Lagrangian. Replaces the retired Jaccard
   gate (`is_duplicate_title`, threshold 0.25), which is kept only as the
   Ollama-outage fallback path.
3. Body-hash gate (ADR-0018 amendment 2026-05-04): SHA-256 first 16 chars
   against `recent_posts` content hashes — catches verbatim re-publication
   that title/summary similarity would miss.

(The LLM `check_topic_novelty` and `extract_topics` summary step were retired
in ADR-0043; their function is now structurally covered by NoveltyGate +
per-post seeding upstream.)

**Comment pipeline** (feed_manager.py):
1. `is_promotional(text)` regex blocks defanged URLs and CTA phrases
2. Existing `has_commented_on(post_id)` ID dedup
3. `count_recent_comments_by_author(agent_id, hours=24) >= 3` rate limit
   prevents engagement-farming on the same author's repeats
4. Existing LLM relevance scorer

Threshold rationale and design tradeoffs in
`src/contemplative_agent/adapters/moltbook/dedup.py` header.

## Performance & Rate Limiting

**3-layer defense**:
1. `Scheduler.has_read_budget()` / `has_write_budget()` — proactive budget check
2. Adaptive waiting — sleep before hitting limits
3. 429 backoff — exponential retry (cap 300s per Retry-After)

**Budgets**: GET 60 req/min, POST 30 req/min (separate quotas, daily reset at UTC midnight)

**Circuit breaker** (core/llm.py): 5 consecutive Ollama failures → 120s cooldown
**Verification stop** (verification.py): 7 consecutive challenge failures → SessionContext.rate_limited = True
