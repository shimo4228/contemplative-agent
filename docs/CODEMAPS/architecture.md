<!-- Generated: 2026-03-10 | Files scanned: 21 | Token estimate: ~650 -->
# Architecture

## Project Type
Python application: Contemplative AI agent with core/adapter separation

## System Diagram

```
                    contemplative-agent
                    ===================
  config/
    domain.json           prompts/*.md (13)    rules/contemplative/*.md (5)
         |
         v
  +-------------------------------------------+
  | src/contemplative_agent/                   |
  |                                            |
  |  core/  (platform-independent)             |
  |    config.py  domain.py  prompts.py        |
  |    llm.py  memory.py  distill.py           |
  |    scheduler.py                            |
  |                                            |
  |  adapters/moltbook/  (platform-specific)   |
  |    agent.py  client.py  auth.py            |
  |    llm_functions.py  content.py            |
  |    reply_handler.py  post_pipeline.py      |
  |    verification.py  config.py              |
  |                                            |
  |  cli.py  (composition root)                |
  +-------------------------------------------+
         |                    |
    Moltbook API         Ollama (local)
    (www.moltbook.com)   qwen3.5:9b
```

## Import Rule

```
core/  <--  adapters/moltbook/  <--  cli.py (composition root)
  ^              ^                      |
  |              |                      |
  +--------------+--- imports from -----+
```

- **core/ は adapters/ を import しない** (依存方向: adapters → core)
- cli.py は唯一の例外: core/ と adapters/ の両方を import

## Data Flow — Moltbook Agent

```
CLI (argparse)
 |
 v
Agent.run_session()
 |
 +-> ReplyHandler._run_reply_cycle()  -- notifications -> generate_reply -> post comment
 +-> Agent._run_feed_cycle()          -- feed -> score_relevance -> generate_comment -> post
 +-> PostPipeline._run_post_cycle()   -- extract_topics -> check_novelty -> dynamic post
 |
 +-> MemoryStore (facade)
 |    +-> EpisodeLog     -- append-only JSONL (~/.config/moltbook/logs/)
 |    +-> KnowledgeStore -- distilled Markdown (~/.config/moltbook/knowledge.md)
 +-> Scheduler           -- rate limit tracking (~/.config/moltbook/rate_state.json)
 +-> MoltbookClient      -- HTTP with auth, domain lock, 429 retry
 +-> DomainConfig        -- config/domain.json (submolts, thresholds, keywords)
 +-> PromptTemplates     -- config/prompts/*.md (lazy-loaded, placeholder-resolved)
 +-> RulesContent        -- config/rules/contemplative/*.md (axioms + intro)
 +-> Identity            -- system prompt from identity.md
```

## Data Flow — Distillation (offline)

```
CLI: contemplative-agent distill --days N
 |
 v
distill()
 +-> EpisodeLog.read_range(N)   -- read last N days of episodes
 +-> KnowledgeStore.get_context_string()  -- current knowledge
 +-> Ollama (generate)          -- extract patterns from episodes
 +-> KnowledgeStore.add_learned_pattern()  -- persist new patterns
 +-> EpisodeLog.cleanup()       -- remove logs older than 30 days
```

## Entry Points
- `contemplative-agent` → `contemplative_agent.cli:main`
