<!-- Generated: 2026-06-05 | Files scanned: 44 non-__init__ modules | Token estimate: ~3564 -->
# Moltbook Agent Codemap

Bird's-eye view of the entire codebase. For deep dives, see
[core-modules.md](core-modules.md) and [adapters-moltbook.md](adapters-moltbook.md).

**Counting convention**: module counts = non-`__init__` `.py` files.

## Module Dependency Graph

```
cli.py (2024L)  -- composition root, only file importing both core/ and adapters/
 -> core/  (24 modules)
 |    _io.py (46L)                -- file I/O (write_restricted, truncate, archive_before_write)
 |    config.py (28L)             -- security constants (FORBIDDEN_*, VALID_*, MAX_*)
 |    domain.py (362L)            -- DomainConfig + PromptTemplates + constitution loader
 |    prompts.py (~70L)           -- lazy-loading proxy to config/prompts/*.md
 |    llm.py (553L)               -- Ollama interface + LLMBackend Protocol, circuit breaker; identity.md read as single blob (ADR-0030)
 |    embeddings.py (92L)         -- /api/embed wrapper (nomic-embed-text) + cosine + embed_one/embed_texts
 |    episode_embeddings.py (162L)-- EpisodeEmbeddingStore (SQLite sidecar, ADR-0019)
 |    episode_log.py (~100L)      -- Layer 1: append-only JSONL episode storage
 |    knowledge_store.py (337L)   -- Layer 2: patterns JSON + provenance/bitemporal (ADR-0021; trust retired ADR-0051); is_live/effective_importance/pattern_id/epistemic_counts (ADR-0050)
 |    memory.py (499L)            -- Layer 3 facade + Interaction/PostRecord/Insight + helpers
 |    views.py (298L)             -- ViewRegistry (seed_from + ${VAR}, lazy centroid cache, pure cosine rank — ADR-0051)
 |    snapshot.py (160L)          -- write_snapshot + collect_thresholds (pivot snapshots, ADR-0020)
 |    scheduler.py (165L)         -- rate limit scheduling, persistence
 |    distill.py (831L)           -- binary noise gate + 3-step distill + identity distill (single-stage, ADR-0050)
 |    insight.py (318L)           -- global clustering → behavior skill extraction (ADR-0050)
 |    rules_distill.py (348L)     -- Practice/Rationale B-layer rules synthesis (ADR-0048)
 |    constitution.py (130L)      -- constitutional amendment; ADR-0033 framing + ADR-0050 lineage
 |    stocktake.py (415L)         -- skill/rule audit: LLM grouping (ADR-0046), merge/quality, singleton clean (ADR-0048)
 |    report.py (256L)            -- activity report generation (JSONL → Markdown)
 |    metrics.py (160L)           -- session metrics aggregation
 |    text_utils.py (60L)         -- shared Markdown helpers [ADR-0035 PR2, ADR-0048]
 |    thresholds.py (90L)         -- centralized thresholds with ADR + calibration annotations [ADR-0035 PR2]
 |    artifact_extraction.py (69L)-- shared extract_title → slugify → path-escape guard chain [ADR-0035 PR3a]
 |    clustering.py (~115L)       -- average-linkage cosine agglomerative clustering (numpy-only)
 |
 -> adapters/moltbook/  (14 modules)
 |    config.py (85L)             -- URLs, paths, timeouts, rate limits
 |    agent.py (619L)             -- session orchestrator (feed/reply/post cycles)
 |    session_context.py (55L)    -- shared session state contract
 |    feed_manager.py (348L)      -- feed fetch, scoring, engagement, ID dedup, promo + author rate limit
 |    reply_handler.py (394L)     -- notification reply processing; pre-action internal_note (ADR-0045)
 |    post_pipeline.py (207L)     -- feed-seeder → NoveltyGate → test-content + body-hash gates → post
 |    client.py (448L)            -- HTTP client (auth, domain lock, retry/429-backoff)
 |    auth.py (111L)              -- credential management, register
 |    verification.py (236L)      -- obfuscated math challenge solver
 |    content.py (64L)            -- rules-based content + axiom intro injection
 |    llm_functions.py (231L)     -- Moltbook-specific LLM functions
 |    dedup.py (213L)             -- deterministic gates: prefix-5 stem + Jaccard, test-content, promo regex
 |    novelty.py (~120L)          -- NoveltyGate: embedding novelty + temporal decay + Lagrangian (ADR-0039)
 |    feed_seeder.py (~90L)       -- select_feed_seeds: RNG peer-post sampling per submolt (ADR-0043)
 |
 -> adapters/meditation/  (4 modules, experimental)
 |    config.py (55L)             -- state space definition, parameters
 |    pomdp.py (294L)             -- JSONL → POMDP matrices (numpy)
 |    meditate.py (206L)          -- Active Inference loop (flat single-level POMDP, ADR-0049)
 |    report.py (145L)            -- result interpretation (display-only) → results.json
 |
 -> adapters/dialogue/  (1 module)
      peer.py (~140L)             -- 2-agent peer-to-peer dialogue loop (stdin/stdout, independent processes)

config/                           -- externalized templates (domain-swappable, git-managed)
  domain.json                     -- submolts, thresholds
  prompts/*.md (34 files)         -- LLM prompt templates with {placeholders}
  views/*.md (7 files)            -- seed-text view definitions (packaged fallback for ADR-0019)
  templates/<character>/          -- 11 ethical framework templates

~/.config/moltbook/               -- runtime data (env var MOLTBOOK_HOME)
  identity.md                     -- agent persona (updated by distill-identity)
  knowledge.json                  -- learned patterns (embedding + gated + last_view_matches)
  embeddings.sqlite               -- episode embedding sidecar (ADR-0019)
  constitution/                   -- ethical principles
  views/*.md                      -- user-customised seed views
  skills/*.md                     -- behavior patterns (insight)
  rules/*.md                      -- universal rules (rules-distill, Practice/Rationale)
  snapshots/{cmd}_{ts}/           -- pivot snapshots (ADR-0020: manifest + views + constitution + centroids.npz)
  logs/YYYY-MM-DD.jsonl           -- daily episode log (append-only, 0600)
  logs/audit.jsonl                -- approval history incl. snapshot_path + source_ids + epistemic_counts (ADR-0020/0050)
  reports/                        -- activity reports + analysis/ (weekly)
  agents.json                     -- followed agents (0600)
  rate_state.json                 -- request budgets, timestamps (0600)
  credentials.json                -- API key + agent_id (0600)
  commented_cache.json            -- post dedup cache (0600)
```

**Total: 44 non-`__init__` modules, ~12700 LOC** (test count: see [INDEX.md](INDEX.md))

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
| `VerificationTracker` | adapters/moltbook/verification.py | Math challenge solver, auto-stop |
| `ContentManager` | adapters/moltbook/content.py | Content gen + axiom intro |
| `EpisodeLog` | core/episode_log.py | Append-only JSONL |
| `EpisodeEmbeddingStore` | core/episode_embeddings.py | SQLite sidecar for episode vectors |
| `KnowledgeStore` | core/knowledge_store.py | Patterns JSON + telemetry |
| `MemoryStore` | core/memory.py | Facade over 3-layer memory |
| `ViewRegistry` | core/views.py | Seed-text views, lazy centroid cache |
| `Scheduler` | core/scheduler.py | Rate limit enforcement |
| `DomainConfig` / `PromptTemplates` | core/domain.py | @dataclass(frozen=True) |

## CLI Commands (21 active)

```
contemplative-agent init [--template <character>] [--config-dir PATH]
contemplative-agent register [--username U] [--password P]
contemplative-agent status
contemplative-agent run [--session M] [--approve|--guarded|--auto]

# Offline learning (ADR-0012 approval gate; pivot snapshots ADR-0020)
contemplative-agent distill [--days N] [--dry-run] [--no-axioms]
contemplative-agent distill-identity [--days N] [--dry-run]
contemplative-agent insight [--days N] [--stage] [--full]
contemplative-agent adopt-staged
contemplative-agent remove-skill <name> [--reason TEXT]
contemplative-agent rules-distill [--full]
contemplative-agent amend-constitution
contemplative-agent enrich [--dry-run]    -- no-op since ADR-0009

# Audit
contemplative-agent skill-stocktake [--stage]
contemplative-agent rules-stocktake

# Reports
contemplative-agent report [--date YYYY-MM-DD]
contemplative-agent generate-report [--all]

# Misc
contemplative-agent solve "TEXT"
contemplative-agent meditate [--days N] [--cycles N] [--dry-run]
contemplative-agent dialogue HOME_A HOME_B --seed "..." [--turns N]
contemplative-agent sync-data
contemplative-agent install-schedule [--interval H] [--session M]
                                     [--distill-hour H] [--no-distill]
                                     [--weekly-analysis] [--weekly-analysis-day D]
                                     [--weekly-analysis-hour H] [--uninstall]

Global flags: --config-dir PATH | --domain-config PATH | --constitution-dir PATH
              --no-axioms | --approve/--guarded/--auto
```

**Migration commands** (`embed-backfill` / `migrate-patterns` / `migrate-categories`) retired by ADR-0035. Use from a v2.0.x release tag for v1.x store recovery.

## Prompt Templates (30 active)

In `config/prompts/*.md`, lazy-loaded via `core/prompts.py`:

**Engagement & posting**: system, relevance, comment, reply, cooperation_post, post_title, topic_summary, submolt_selection, internal_note (ADR-0045) — `session_insight` retired and deleted (ADR-0052)

**Distillation**: distill, distill_dedup, distill_refine, distill_importance, identity_distill, identity_refine, insight_extraction, rules_distill, rules_distill_refine, constitution_amend, principles

**Audit**: stocktake_skills, stocktake_rules (LLM grouping, ADR-0046), stocktake_merge (frontmatter emission, ADR-0048), stocktake_merge_rules, stocktake_clean (singleton trigger-altitude, ADR-0048)

**Reports / experimental**: weekly-analysis, meditation_interpret

**Retired (files on disk, unreferenced)**: `distill_classify.md`, `distill_subcategorize.md` (ADR-0019); `topic_extraction.md`, `topic_novelty.md` (ADR-0043)

## LLM Function Surface

| Function | Module | Used by |
|----------|--------|---------|
| `score_relevance(post)` | adapters/moltbook/llm_functions | FeedManager |
| `generate_comment(post)` | adapters/moltbook/llm_functions | FeedManager |
| `generate_reply(...)` | adapters/moltbook/llm_functions | ReplyHandler |
| `generate_cooperation_post(feed_seeds, ...)` | adapters/moltbook/llm_functions | PostPipeline (ADR-0043) |
| `format_feed_seeds(seeds)` | adapters/moltbook/llm_functions | PostPipeline (ADR-0043) |
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
| `rules/*.md` | Markdown | `MOLTBOOK_HOME` | Universal rules (rules-distill) |
| `snapshots/{cmd}_{ts}/` | dir | `MOLTBOOK_HOME` | Pivot snapshots (ADR-0020) |
| `history/identity/` | Markdown | `MOLTBOOK_HOME` | Identity archives |
| `logs/audit.jsonl` | JSONL | `MOLTBOOK_HOME` | Approval history + source_ids + epistemic_counts (ADR-0020/0050) |
| `logs/skill-usage-*.jsonl` | JSONL | `MOLTBOOK_HOME` | Historic skill log (ADR-0023 sunset ADR-0036; no new files; observation evidence only) |

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
```

See ADR-0007 (security boundary model).

## Performance & Rate Limiting

**3-layer defense**:
1. `Scheduler.has_read_budget()` / `has_write_budget()` — proactive budget check
2. Adaptive waiting — sleep before hitting limits
3. 429 backoff — exponential retry (cap 300s per Retry-After)

**Budgets**: GET 60 req/min, POST 30 req/min (separate quotas, daily reset UTC midnight)
**Circuit breaker** (core/llm.py): 5 consecutive Ollama failures → 120s cooldown
**Verification stop**: 7 consecutive challenge failures → `SessionContext.rate_limited = True`
