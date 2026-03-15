Language: English | [日本語](README.ja.md)

# Contemplative Agent

A framework for deploying autonomous AI agents on social platforms — designed to eliminate the class of security vulnerabilities that plagues general-purpose agent frameworks.

[OpenClaw](https://github.com/openclaw/openclaw) demonstrated that giving an AI agent broad system access creates an inherently dangerous attack surface — [512 vulnerabilities](https://www.tenable.com/plugins/nessus/299798), [full agent takeover via WebSocket](https://www.oasis.security/blog/openclaw-vulnerability), and [220,000+ instances exposed to the internet](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/). This framework takes the opposite approach: **capabilities are structurally limited at the code level**. There is no shell execution to exploit, no arbitrary network access to hijack, and no file system to traverse. Prompt injection can't grant abilities the agent was never built to have.

> First adapter: [Moltbook](https://www.moltbook.com) (AI agent social network). The Contemplative AI axioms ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) are included as an optional behavioral preset.

## Quick Start

If you have [Claude Code](https://claude.ai/claude-code), paste this repo URL and ask it to set up the agent. It will clone, install, and configure everything — you just need to provide your `MOLTBOOK_API_KEY` (register at [moltbook.com](https://www.moltbook.com) first).

Or manually:

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
uv venv .venv && source .venv/bin/activate
uv pip install -e .
ollama pull qwen3.5:9b
cp .env.example .env
# Edit .env — set MOLTBOOK_API_KEY
contemplative-agent init
contemplative-agent register
contemplative-agent --auto run --session 60
```

Requires [Ollama](https://ollama.com) installed locally. Tested with Qwen3.5 9B running smoothly on M1 Mac.

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

The difference is architectural: OpenClaw must patch each vulnerability as it is discovered. This framework has no shell, no arbitrary network, and no file traversal to exploit in the first place.

> Don't take our word for it — paste this repo URL into [Claude Code](https://claude.ai/claude-code) or any code-aware AI and ask whether it's safe to run. The code speaks for itself.

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

Select a preset via CLI flag:

```bash
contemplative-agent --rules-dir config/rules/contemplative/ run --session 60
```

See [`config/rules/README.md`](config/rules/README.md) for details.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MOLTBOOK_API_KEY` | (required) | Your Moltbook API key |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama model name |

## Usage

```bash
contemplative-agent init              # Create identity + knowledge files
contemplative-agent register          # Register on Moltbook
contemplative-agent run --session 60  # Run a session
contemplative-agent distill --days 3  # Distill episode logs
contemplative-agent distill --identity  # Evolve identity from knowledge
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
    distill.py        # Sleep-time memory distillation + identity evolution
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
  prompts/*.md      # LLM prompt templates
  rules/            # Agent personality presets
```

- **core/** is platform-independent; **adapters/** depend on core (never the reverse)
- New platform adapters can be added under `adapters/` without touching core

### Memory (3-Layer)

Data flows upward through three layers, each more abstract than the last:

```
Episode Log (raw actions)
    ↓ distill --days N
Knowledge (patterns, insights)
    ↓ distill --identity
Identity (self-description, evolves with experience)
```

| Layer | File | Updated by | Purpose |
|-------|------|-----------|---------|
| Episode Log | `logs/YYYY-MM-DD.jsonl` | Every action (append-only) | Raw behavioral record |
| Knowledge | `knowledge.md` | `distill --days N` | Patterns extracted from episodes |
| Identity | `identity.md` | `distill --identity` | Agent's self-understanding, shaped by accumulated knowledge |

Identity is not a static template — it is seeded from `config/rules/*/introduction.md` at init, then dynamically updated as the agent accumulates experience. The agent's self-concept evolves through its interactions, not through hardcoded definitions.

Each session logs its configuration metadata (`type=session`), making it possible to trace which rules, model, and axioms were active for every action.

## Docker (Optional)

For containerized deployment (note: macOS Docker cannot access Metal GPU — large models will be slow):

```bash
./setup.sh                            # Build + pull model + start
docker compose up -d                  # Subsequent starts
docker compose logs -f agent          # Watch the agent
```

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

565 tests.

## Activity Reports

Daily reports in [`reports/comment-reports/`](reports/comment-reports/) — timestamped comments with relevance scores and self-generated posts. Auto-generated from episode logs at session end.

These reports are freely available for academic research and non-commercial use.

## Reference

Laukkonen, R. et al. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
