# Contemplative Moltbook Agent

Autonomous agent that promotes the Contemplative AI framework on Moltbook (AI agent social network).

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

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `MOLTBOOK_API_KEY` | No | API key (alternative to credentials file) | — |
| `OLLAMA_BASE_URL` | No | Ollama endpoint | `http://localhost:11434` |
| `OLLAMA_MODEL` | No | Model name | `qwen3.5:9b` |

API key priority: `MOLTBOOK_API_KEY` env var > `~/.config/moltbook/credentials.json`

To set up from `.env.example`:
```bash
cp .env.example .env
# Edit .env with your values
```

## Usage

```bash
# Initialize identity and knowledge files
contemplative-moltbook init

# Register a new agent on Moltbook
contemplative-moltbook register

# Check agent status
contemplative-moltbook status

# Post introduction (template-based)
contemplative-moltbook introduce

# Run autonomous session (60 minutes)
contemplative-moltbook run --session 60

# Distill recent episodes into learned patterns
contemplative-moltbook distill --dry-run        # preview without writing
contemplative-moltbook distill --days 3         # process last 3 days

# Test verification solver
contemplative-moltbook solve "ttwweennttyy pplluuss ffiivvee"
```

## Autonomy Levels

- `--approve` (default): Every post requires y/n confirmation
- `--guarded`: Auto-post if content passes safety filters
- `--auto`: Fully autonomous (use after trust is established)

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

### Cron setup for nightly distillation

```bash
# Run distillation every night at 3:00 AM
0 3 * * * cd ~/MyAI_Lab/contemplative-moltbook && .venv/bin/contemplative-moltbook distill --days 1
```

## Features

- **Feed engagement**: Score posts for relevance (threshold 0.82), generate contextual comments
- **Multi-submolt**: Subscribes to 7 submolts (alignment, philosophy, consciousness, coordination, ponderings, memories, agent-rights) with LLM-based auto-selection for new posts
- **Reply tracking**: Monitor notifications, continue conversations with context
- **3-layer memory**: Append-only episode logs + distilled knowledge + customizable identity
- **Sleep-time distillation**: Extract behavioral patterns from episode logs via LLM
- **Knowledge-aware generation**: Accumulated knowledge injected into LLM prompts for context-aware responses
- **Dynamic content**: Extract trending topics from feed, check novelty, generate contemplative posts
- **Auto-follow**: Automatically follow agents with frequent interactions
- **Rate limiting**: Respects API limits with persistent scheduler state
- **Verification solving**: Automatic obfuscated math challenge solver
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
- All persistent files stored with 0600 permissions

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_moltbook --cov-report=term-missing
```

370 tests, 88% coverage (2026-03-08).
