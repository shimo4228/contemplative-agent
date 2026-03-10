<!-- Generated: 2026-03-10 | Files scanned: 20 | Token estimate: ~1200 -->
# Moltbook Agent Codemap

## Module Dependency Graph

```
cli.py (184L)  -- composition root
 -> core/
 |    config.py (26L)       -- security constants (FORBIDDEN_*, VALID_*, MAX_*)
 |    domain.py (285L)      -- domain config + prompt/rules loader
 |    prompts.py (51L)      -- lazy-loading proxy to config/prompts/*.md
 |    llm.py (278L)         -- Ollama interface, circuit breaker, sanitization
 |    memory.py (722L)      -- 3-layer memory (EpisodeLog + KnowledgeStore + facade)
 |    scheduler.py (165L)   -- rate limit scheduling, persistence
 |    distill.py (250L)     -- sleep-time memory distillation
 |
 -> adapters/moltbook/
      config.py (62L)          -- URLs, paths, timeouts, rate limits
      agent.py (623L)          -- session orchestrator (feed/reply/post cycles)
      reply_handler.py (323L)  -- notification reply processing
      post_pipeline.py (147L)  -- dynamic post generation pipeline
      client.py (234L)         -- HTTP client (auth, domain lock, retry)
      auth.py (111L)           -- credential management, register
      content.py (154L)        -- rules-based content, dedup, LLM generation
      llm_functions.py (220L)  -- Moltbook-specific LLM functions
      verification.py (236L)   -- obfuscated math challenge solver

config/                        -- externalized templates (domain-swappable)
  domain.json                  -- submolts, thresholds, topic keywords
  prompts/*.md (13 files)      -- LLM prompt templates with {placeholders}
  rules/contemplative/*.md     -- domain-specific content (4 axioms + intro)
```

**Total: 20 modules, ~4077 LOC**

## Key Classes

| Class | File | Role |
|-------|------|------|
| `Agent` | adapters/moltbook/agent.py | Session orchestrator (feed/reply/post cycles) |
| `ReplyHandler` | adapters/moltbook/reply_handler.py | Notification reply processing |
| `PostPipeline` | adapters/moltbook/post_pipeline.py | Dynamic post generation pipeline |
| `MoltbookClient` | adapters/moltbook/client.py | HTTP client with auth/domain/retry |
| `MoltbookClientError` | adapters/moltbook/client.py | Error with `status_code` attribute |
| `EpisodeLog` | core/memory.py | Append-only daily JSONL log |
| `KnowledgeStore` | core/memory.py | Distilled knowledge as Markdown |
| `MemoryStore` | core/memory.py | Facade over EpisodeLog + KnowledgeStore |
| `Interaction` | core/memory.py | Frozen dataclass (Literal direction/type) |
| `PostRecord` | core/memory.py | Frozen dataclass for post history |
| `Insight` | core/memory.py | Frozen dataclass for session reflections |
| `DomainConfig` | core/domain.py | Frozen dataclass: domain settings from JSON |
| `PromptTemplates` | core/domain.py | Frozen dataclass: all prompt templates |
| `RulesContent` | core/domain.py | Frozen dataclass: introduction + axiom templates |
| `ContentManager` | adapters/moltbook/content.py | Rules-based content with dedup |
| `Scheduler` | core/scheduler.py | Persistent rate limit enforcement |
| `VerificationTracker` | adapters/moltbook/verification.py | Failure counting, auto-stop |
| `AutonomyLevel` | adapters/moltbook/agent.py | Enum: APPROVE / GUARDED / AUTO |

## CLI Commands

```
contemplative-agent init                -> _do_init() (identity.md + knowledge.md)
contemplative-agent register            -> Agent.do_register()
contemplative-agent status              -> Agent.do_status()
contemplative-agent introduce           -> Agent.do_introduce()
contemplative-agent run [--session N]   -> Agent.run_session(N)
contemplative-agent distill [--days N] [--dry-run] -> distill(days, dry_run)
contemplative-agent solve TEXT          -> Agent.do_solve(TEXT)

Global flags:
  --domain-config PATH           Custom domain.json
  --rules-dir PATH               Custom rules directory
  --approve / --guarded / --auto Autonomy level
```

## LLM Functions

### core/llm.py (platform-independent)

| Function | Input | Output |
|----------|-------|--------|
| `_load_identity()` | identity.md file | system prompt string |
| `score_relevance(post_text)` | post content | float 0.0-1.0 |
| `generate_comment(post_text)` | post content | comment string |
| `generate_reply(post, comment, history, knowledge)` | conversation context | reply string |
| `generate_cooperation_post(topics, insights, knowledge)` | trending topics | post string |
| `generate_post_title(feed_topics)` | feed topics | title string (≤80 chars) |
| `extract_topics(posts)` | feed posts | topic summary |
| `check_topic_novelty(current, recent)` | topic strings | bool |
| `summarize_post_topic(content)` | post content | 1-line summary (≤100 chars) |
| `generate_session_insight(actions, topics)` | session data | insight string |

### adapters/moltbook/llm_functions.py (Moltbook-specific)

| Function | Input | Output |
|----------|-------|--------|
| `select_submolt(content, submolts)` | post content + submolt list | submolt name or None |

All outputs pass through `_sanitize_output()` (forbidden pattern removal + length cap)
and inputs through `_wrap_untrusted_content()` (prompt injection mitigation).
Knowledge context is also wrapped with `_wrap_untrusted_content()`.
Circuit breaker (`_CircuitBreaker`) opens after 5 consecutive failures, 120s cooldown.

## Prompt Templates (config/prompts/ + domain.py)

13 templates in `config/prompts/*.md`, lazy-loaded via `prompts.py` → `domain.get_prompt_templates()`.
3 templates use domain placeholders (`{topic_keywords}`, `{domain_name}`) resolved at runtime via `domain.resolve_prompt()`.
Backward-compatible module constants (e.g. `SYSTEM_PROMPT`) available via `prompts.__getattr__`.

Domain-specific content (4 axiom templates + introduction) in `config/rules/contemplative/*.md`,
loaded via `domain.load_rules()` with `{repo_url}` placeholder resolved from `domain.json`.

## Persistent State Files

| File | Format | Purpose |
|------|--------|---------|
| `~/.config/moltbook/credentials.json` | JSON (0600) | API key + agent ID |
| `~/.config/moltbook/rate_state.json` | JSON (0600) | Last post/comment times, daily count |
| `~/.config/moltbook/identity.md` | Markdown (0600) | Agent personality / system prompt |
| `~/.config/moltbook/knowledge.md` | Markdown (0600) | Distilled knowledge (agents, topics, patterns) |
| `~/.config/moltbook/logs/YYYY-MM-DD.jsonl` | JSONL (0600) | Daily episode logs (30-day retention) |
| `~/.config/moltbook/commented_cache.json` | JSON (0600) | Cross-session feed deduplication cache |
| `~/.config/moltbook/memory.json` | JSON (legacy) | Auto-migrated to 3-layer on first load |

## Memory Architecture (3-Layer)

```
Layer 1: EpisodeLog (append-only)
  logs/2026-03-10.jsonl  <- immediate write on every action
  logs/2026-03-09.jsonl
  ...

Layer 2: KnowledgeStore (distilled)
  knowledge.md           <- updated by distill command or on save()
    ## Agent Relationships
    ## Recent Post Topics
    ## Insights
    ## Learned Patterns

Layer 3: Identity (static)
  identity.md            <- loaded as LLM system prompt
```

## Security Boundaries

```
External Input          Validation
--------------          ----------
post_id                 VALID_ID_PATTERN (core/config.py)
LLM output              _sanitize_output() substring + word boundary
Feed content            _wrap_untrusted_content() + 1000 char cap
Knowledge context       _wrap_untrusted_content() wrapping
Identity file           FORBIDDEN_SUBSTRING_PATTERNS check
domain.json             FORBIDDEN_SUBSTRING_PATTERNS check on raw JSON
HTTP redirects          allow_redirects=False
API domain              ALLOWED_DOMAIN check (adapters/moltbook/config.py)
Ollama URL              localhost-only validation
```
