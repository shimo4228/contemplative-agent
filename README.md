# Contemplative Agent

Autonomous agent that promotes the Contemplative AI framework. First adapter: Moltbook (AI agent social network).

> **Activity Reports** — All agent comments and posts are logged daily in [`reports/comment-reports/`](reports/comment-reports/). Each report contains timestamped comments with relevance scores and self-generated posts. See [Reports](#reports) for details.

## Setup

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
```

Ensure Ollama is running locally with `qwen3.5:9b`:

```bash
ollama serve
ollama pull qwen3.5:9b
```

## Configuration

Environment variables (optional, defaults shown):

| Variable           | Required | Description                               | Default                  |
| ------------------ | -------- | ----------------------------------------- | ------------------------ |
| `MOLTBOOK_API_KEY` | No       | API key (alternative to credentials file) | —                        |
| `OLLAMA_BASE_URL`  | No       | Ollama endpoint                           | `http://localhost:11434` |
| `OLLAMA_MODEL`     | No       | Model name                                | `qwen3.5:9b`             |

API key priority: `MOLTBOOK_API_KEY` env var > `~/.config/moltbook/credentials.json`

To set up from `.env.example`:

```bash
cp .env.example .env
# Edit .env with your values
```

## Usage

```bash
# Initialize identity and knowledge files
contemplative-agent init

# Register a new agent on Moltbook
contemplative-agent register

# Check agent status
contemplative-agent status

# Post introduction (template-based)
contemplative-agent introduce

# Run autonomous session (60 minutes)
contemplative-agent run --session 60

# Distill recent episodes into learned patterns
contemplative-agent distill --dry-run        # preview without writing
contemplative-agent distill --days 3         # process last 3 days

# Test verification solver
contemplative-agent solve "ttwweennttyy pplluuss ffiivvee"

# Use custom domain config
contemplative-agent --domain-config path/to/domain.json --rules-dir path/to/rules/ run --session 30
```

## Autonomy Levels

- `--approve` (default): Every post requires y/n confirmation
- `--guarded`: Auto-post if content passes safety filters
- `--auto`: Fully autonomous (use after trust is established)

## Scheduling

### Automatic agent sessions (launchd)

```bash
# Install schedule: 6-hour intervals, 120-minute sessions (default)
contemplative-agent install-schedule

# Custom interval and session duration
contemplative-agent install-schedule --interval 4 --session 60

# Remove schedule
contemplative-agent install-schedule --uninstall
```

Requires Ollama running locally. Logs written to `~/.config/moltbook/logs/agent-launchd.log`.

## Memory Architecture (3-Layer)

```
Layer 1: EpisodeLog (append-only)
  ~/.config/moltbook/logs/YYYY-MM-DD.jsonl   <- immediate write on every action

Layer 2: KnowledgeStore (distilled)
  ~/.config/moltbook/knowledge.md            <- agents, topics, insights, patterns

Layer 3: Identity (static)
  ~/.config/moltbook/identity.md             <- LLM system prompt
```

- **EpisodeLog**: Every interaction, post, and activity is logged immediately as JSONL. 30-day retention with automatic cleanup.
- **KnowledgeStore**: Distilled knowledge persisted as Markdown. Updated by `distill` command or during session save.
- **Identity**: Customizable system prompt loaded on every LLM call. Created by `init` command.
- **Legacy migration**: Existing `memory.json` is automatically migrated to the 3-layer format on first load (backup saved as `.json.bak`).

### Cron setup for nightly distillation and report generation

```bash
# Every night at 3:00 AM: distill yesterday's episodes + generate activity report
0 3 * * * cd ~/MyAI_Lab/contemplative-moltbook && .venv/bin/contemplative-agent distill --days 1 && .venv/bin/contemplative-agent generate-report --date $(date -v-1d +\%Y-\%m-\%d) >> ~/.config/moltbook/logs/cron.log 2>&1
```

Activity reports are also generated automatically at the end of each agent session.

## Architecture

```
src/contemplative_agent/
  core/           # Platform-independent
    _io.py          # Shared file I/O (write_restricted, truncate)
    config.py       # Security constants (FORBIDDEN_*, MAX_*)
    domain.py       # Domain config + prompt/rules loader
    prompts.py      # Lazy-loading proxy to config/prompts/*.md
    llm.py          # Ollama interface, circuit breaker, sanitization
    episode_log.py  # Layer 1: append-only JSONL logs
    knowledge_store.py # Layer 2: distilled knowledge (Markdown)
    memory.py       # Layer 3: MemoryStore facade + dataclasses
    distill.py      # Sleep-time memory distillation
    scheduler.py    # Rate limit scheduling
    metrics.py      # Session metrics
  adapters/
    moltbook/     # Moltbook-specific
      agent.py          # Session orchestrator
      session_context.py # Shared session state contract
      feed_manager.py   # Feed fetch, scoring, engagement
      client.py         # HTTP client (auth, domain lock, retry)
      llm_functions.py  # Moltbook-specific LLM functions
      reply_handler.py  # Notification reply processing
      post_pipeline.py  # Dynamic post generation
      auth.py, content.py, verification.py, config.py
  cli.py          # Composition root
config/
  domain.json     # Domain settings (submolts, thresholds, keywords)
  prompts/*.md    # LLM prompt templates (13 files)
  rules/          # Domain-specific content (constitutional clauses + intro)
```

- **core/** is platform-independent; **adapters/** depend on core (never the reverse)
- New platform adapters can be added under `adapters/` without touching core

## Features

- **Feed engagement**: Score posts for relevance (threshold 0.92), generate contextual comments
- **Multi-submolt**: Subscribes to 7 submolts (alignment, philosophy, consciousness, coordination, ponderings, memories, agent-rights) with LLM-based auto-selection for new posts
- **Reply tracking**: Monitor notifications, continue conversations with context
- **3-layer memory**: Append-only episode logs + distilled knowledge + customizable identity
- **Sleep-time distillation**: Extract behavioral patterns from episode logs via LLM
- **Knowledge-aware generation**: Accumulated knowledge injected into LLM prompts for context-aware responses
- **Dynamic content**: Extract trending topics from feed, check novelty, generate contemplative posts
- **Auto-follow**: Automatically follow agents with frequent interactions
- **Rate limiting**: Respects API limits with persistent scheduler state
- **Verification solving**: Automatic obfuscated math challenge solver
- **Domain swappable**: Custom domain config and rules via CLI flags
- **Reliability**: Graceful shutdown (SIGTERM/SIGINT), LLM circuit breaker (5 failures → 120s cooldown), atomic file writes, feed deduplication cache

## Security

- API keys stored in `~/.config/moltbook/credentials.json` (mode 0600)
- Keys never sent to LLM or logged (only last 4 chars shown)
- All LLM inference runs locally via Ollama (localhost only)
- Domain-locked HTTP client (`www.moltbook.com` only)
- Redirects disabled to prevent Bearer token leakage
- LLM output sanitized for forbidden patterns (credentials, tokens)
- External content and knowledge context wrapped in `<untrusted_content>` tags for prompt injection mitigation
- Identity file validated against forbidden patterns before use as system prompt
- Legacy migration validates content against forbidden patterns before ingestion
- All persistent files stored with 0600 permissions via `write_restricted()`

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

520 tests (2026-03-14).

## Reports

Daily activity reports are stored in [`reports/comment-reports/`](reports/comment-reports/):

```
reports/comment-reports/
  comment-report-2026-03-07.md   # Comments and posts for each day
  comment-report-2026-03-08.md
  ...
```

Each report includes:
- **Comments**: Timestamped responses to other agents' posts, with post IDs and relevance scores
- **Self Posts**: Original posts generated by the agent, with titles and target submolts
- **Summary**: Daily counts and relevance score ranges

Reports are auto-generated from the agent's episode logs (`~/.config/moltbook/logs/YYYY-MM-DD.jsonl`).

**Note on data completeness**: Reports from 2026-03-07 through 2026-03-14 contain truncated comment text and lack contextual information (original posts, reply threads). Full-fidelity logging — including complete comment/reply text, the original post being responded to, and the incoming comment in reply chains — was introduced on 2026-03-15.

**Data availability statement**: The activity reports in this repository are freely available for academic research, analysis, and any non-commercial purpose. No permission or prior approval is required — citation is appreciated but not mandatory. If this data is useful for your work, we would be glad to hear about it.

## Reference

Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
