# Contemplative Agent

A framework for deploying autonomous AI agents on social platforms — designed to eliminate the class of security vulnerabilities that plagues general-purpose agent frameworks.

[OpenClaw](https://github.com/openclaw/openclaw) demonstrated that giving an AI agent broad system access creates an inherently dangerous attack surface — [512 vulnerabilities](https://www.tenable.com/plugins/nessus/299798), [full agent takeover via WebSocket](https://www.oasis.security/blog/openclaw-vulnerability), and [220,000+ instances exposed to the internet](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/). This framework takes the opposite approach: **capabilities are structurally limited at the code level**, then reinforced by Docker containerization. There is no shell execution to exploit, no arbitrary network access to hijack, and no file system to traverse. Prompt injection can't grant abilities the agent was never built to have.

> First adapter: [Moltbook](https://www.moltbook.com) (AI agent social network). The Contemplative AI axioms ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) are included as an optional behavioral preset.

## Quick Start

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
cp .env.example .env
# Edit .env — set MOLTBOOK_API_KEY (and optionally OLLAMA_MODEL)
./setup.sh                            # Build + pull model (~5GB) + start
```

```bash
docker compose logs -f agent          # Watch the agent
docker compose run agent command status   # Check status
docker compose down                   # Stop
docker compose up -d                  # Restart (no setup.sh needed)
./setup.sh llama3.1:8b               # Pull additional models
```

## Security Architecture

The agent operates within hardcoded structural constraints — not LLM-enforced guidelines:

| Attack Vector | OpenClaw | Contemplative Agent |
|---------------|----------|---------------------|
| **Shell execution** | Core feature — [command injection CVEs](https://www.tenable.com/plugins/nessus/299798) | Does not exist in codebase |
| **Network access** | Arbitrary — [SSRF vulnerabilities](https://www.tenable.com/plugins/nessus/299798) | Domain-locked to `moltbook.com` + localhost Ollama |
| **Local gateway** | WebSocket on localhost — [ClawJacked takeover](https://www.oasis.security/blog/openclaw-vulnerability) | No listening services |
| **File system** | Full access — path traversal risks | Writes only to `MOLTBOOK_HOME`, 0600 permissions |
| **LLM provider** | External API keys in transit | Local Ollama only — nothing leaves the machine |
| **Dependencies** | Large dependency tree | Single runtime dependency (`requests`) |
| **Container** | Often runs as root with Docker socket | Non-root (UID 1000), Ollama isolated from internet (setup-only access for model pull) |

The difference is architectural: OpenClaw must patch each vulnerability as it is discovered. This framework has no shell, no arbitrary network, and no file traversal to exploit in the first place.

## Customizing Your Agent

The default agent starts with a neutral personality and no axioms. Define your agent's behavior by editing markdown files:

```
config/rules/
  default/              # Neutral (active by default)
    introduction.md       # Self-introduction posted on Moltbook
  contemplative/        # Contemplative AI preset (four axioms)
    introduction.md
    contemplative-axioms.md
  your-agent/           # Create your own
    introduction.md
    contemplative-axioms.md  # Optional: constitutional clauses
```

Select a preset via environment variable or CLI flag:

```bash
# Docker (.env)
RULES_DIR=config/rules/contemplative/

# CLI
contemplative-agent --rules-dir config/rules/contemplative/ run --session 60
```

See [`config/rules/README.md`](config/rules/README.md) for details.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MOLTBOOK_API_KEY` | (required) | Your Moltbook API key |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama model name |
| `SESSION_MINUTES` | `30` | Duration of each session (minutes) |
| `BREAK_MINUTES` | `5` | Pause between sessions (minutes) |
| `MODE` | `loop` | `loop`, `single`, or `command` |
| `RULES_DIR` | (neutral) | Path to rules directory |

## Local Setup

For development without Docker:

```bash
uv venv .venv && source .venv/bin/activate
uv pip install -e ".[dev]"
ollama serve && ollama pull qwen3.5:9b
```

```bash
contemplative-agent init              # Create identity + knowledge files
contemplative-agent register          # Register on Moltbook
contemplative-agent run --session 60  # Run a session
contemplative-agent distill --days 3  # Distill episode logs
```

### Autonomy Levels

- `--approve` (default): Every post requires y/n confirmation
- `--guarded`: Auto-post if content passes safety filters
- `--auto`: Fully autonomous

### Scheduling (macOS)

```bash
contemplative-agent install-schedule              # 6h intervals, 120min sessions
contemplative-agent install-schedule --uninstall  # Remove schedule
```

## Architecture

```
src/contemplative_agent/
  core/             # Platform-independent
    llm.py            # Ollama interface, circuit breaker, output sanitization
    memory.py         # 3-layer memory (episode log + knowledge + identity)
    distill.py        # Sleep-time memory distillation
    domain.py         # Domain config + prompt/rules loader
    scheduler.py      # Rate limit scheduling
  adapters/
    moltbook/       # Moltbook-specific (first adapter)
      agent.py          # Session orchestrator
      feed_manager.py   # Feed scoring + engagement
      reply_handler.py  # Notification replies
      post_pipeline.py  # Dynamic post generation
      client.py         # Domain-locked HTTP client
  cli.py            # Composition root
config/
  domain.json       # Domain settings (submolts, thresholds, keywords)
  prompts/*.md      # LLM prompt templates (13 files)
  rules/            # Agent personality presets
```

- **core/** is platform-independent; **adapters/** depend on core (never the reverse)
- New platform adapters can be added under `adapters/` without touching core

### Memory (3-Layer)

| Layer | File | Purpose |
|-------|------|---------|
| Episode Log | `logs/YYYY-MM-DD.jsonl` | Append-only record of every action |
| Knowledge | `knowledge.md` | Distilled patterns and insights |
| Identity | `identity.md` | System prompt (LLM personality) |

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

533 tests.

## Activity Reports

Daily reports in [`reports/comment-reports/`](reports/comment-reports/) — timestamped comments with relevance scores and self-generated posts. Auto-generated from episode logs at session end.

These reports are freely available for academic research and non-commercial use.

## Reference

Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
