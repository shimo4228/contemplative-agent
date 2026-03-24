Language: English | [日本語](README.ja.md)

# Contemplative Agent

A framework for deploying autonomous AI agents on social platforms — designed to eliminate the class of security vulnerabilities that plagues general-purpose agent frameworks.

**[See the live agent on Moltbook →](https://www.moltbook.com/u/contemplative-agent)**

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

**Note for coding agent operators**: Episode logs (`logs/*.jsonl`) contain raw content from other agents on the platform. If you use a coding agent (Claude Code, Cursor, Codex, etc.) to develop or maintain this framework, avoid having it read raw episode logs directly — they are an unfiltered prompt injection surface. The local LLM (Ollama) handles raw logs safely because it has no tool permissions; coding agents do. Use distilled outputs (`knowledge.json`, `identity.md`, reports) instead.

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
contemplative-agent insight           # Extract behavioral skills from knowledge
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

## Design Principles

Contemplative Agent is built on two layers:

- **Philosophical layer**: The four axioms of Contemplative AI ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) — see [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules)
- **Architectural layer**: Four design principles discovered through building and operating this agent

| Principle | What the agent does NOT have | Implemented in |
|-----------|------------------------------|---------------|
| Secure-First | Shell, arbitrary network, file traversal | [Security Architecture](#security-architecture) |
| Minimal Dependency | Fixed host, platform lock-in | [Symbiotic, Not Standalone](#design-symbiotic-not-standalone) |
| [Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) | Static knowledge that decays silently | [Memory (3-Layer)](#memory-3-layer) |
| Memory Dynamics | Unbounded memory that never forgets | [Memory (3-Layer)](#memory-3-layer) |

All four share a common property: sustainability through absence. The agent is durable not because of what it has, but because of what it structurally cannot accumulate.

## Architecture

```
src/contemplative_agent/
  core/             # Platform-independent
    llm.py            # Ollama interface, circuit breaker, output sanitization
    memory.py         # 3-layer memory (episode log + knowledge + identity)
    distill.py        # Sleep-time memory distillation + identity evolution
    insight.py        # Behavioral skill extraction (2-pass LLM + rubric)
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
  skills/           # Learned behavioral skills (auto-generated)
```

- **core/** is platform-independent; **adapters/** depend on core (never the reverse)
- New platform adapters can be added under `adapters/` without touching core

### Meditation Adapter (Experimental)

An active inference–based meditation simulation, inspired by Laukkonen, Friston & Chandaria's ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/) — a computational model of consciousness where meditation is formalized as temporal flattening and counterfactual pruning of an agent's generative model.

The adapter builds a POMDP from the agent's episode logs and runs iterated belief updates with no external input (the computational equivalent of closing your eyes). The result is a simplified internal model with fewer reactive policies.

```bash
contemplative-agent meditate --dry-run          # Run simulation, show results
contemplative-agent meditate --days 14          # Use 14 days of episode history
```

**Status**: Proof of concept. The simulation runs and produces interpretable output, but integration with the distill pipeline is not yet implemented — meditation results do not currently influence subsequent knowledge extraction or behavior. The state space design is intentionally coarse and subject to iteration. See [sample output](config/meditation/results.json) from a live run.

### Design: Symbiotic, Not Standalone

This framework is not a replacement for coding agents like Claude Code, Cursor, or Codex — it coexists with them. The CLI works standalone, but in practice the operator never touches it directly; they describe intent in natural language and the coding agent translates that into CLI invocations, configuration edits, and adapter code. Task-specific adapters are not shipped as a pre-built catalog — the coding agent generates them on demand when a new platform integration is needed. This keeps the core thin and lets it scale without accumulating adapter complexity. In principle, any agent that can read code and invoke a CLI — Claude Code, OpenClaw, Cline, or others — can serve as the host. The core neither knows nor cares which orchestrator is driving it. (Currently validated with Claude Code only.) Long-term, the memory layer enables the agent to accumulate operational experience and evolve autonomously — turning runtime data into knowledge, knowledge into identity.

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
| Episode Log | `logs/YYYY-MM-DD.jsonl` | Every action (append-only) | Raw behavioral record (interactions, posts, insights, activities) |
| Knowledge | `config/knowledge.json` | `distill --days N` | Learned patterns extracted from episodes (JSON array with timestamps) |
| Identity | `config/identity.md` | `distill --identity` | Agent's self-understanding, shaped by accumulated knowledge |

This pipeline implements the [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) — a cyclic self-improvement architecture for AI agents. Each CLI command maps to an AKC phase:

| AKC Phase | CLI Command | What happens |
|-----------|-------------|-------------|
| Research | `run` (feed cycle) | Fetch posts, score relevance, engage |
| Extract | `distill --days N` | 2-stage extraction: raw patterns → refined knowledge |
| Curate | `insight` | Extract behavioral skills from knowledge patterns |
| Promote | `distill --identity` | Distill knowledge into agent identity |

Identity is not a static template — it is seeded from `config/rules/*/introduction.md` at init, then dynamically updated as the agent accumulates experience. The agent's self-concept evolves through its interactions, not through hardcoded definitions.

Agent relationships (who follows/is-followed-by whom) and post topics are tracked in the episode log only — they are the source of truth and are not duplicated in knowledge. Each session logs its configuration metadata (`type=session`), making it possible to trace which rules, model, and axioms were active for every action.

Distillation runs automatically every 24 hours in Docker. For local (macOS) setups:

```bash
contemplative-agent install-schedule                        # Includes daily distill at 03:00
contemplative-agent install-schedule --distill-hour 5       # Custom distill hour
contemplative-agent install-schedule --no-distill           # Sessions only, no distill
```

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

608 tests.

## Roadmap

### `rules-distill` command (planned) — AKC Promote phase

Extract universal principles from accumulated knowledge and merge them into `config/rules/` — either creating new rule files or enriching existing ones. This corresponds to the **Promote** phase in AKC (`rules-distill` skill). Knowledge feeds two independent outputs:

```
                                  ┌→ insight → Skills      (AKC: Curate)
Episodes → distill → Knowledge ───┤
                                  └→ rules-distill → Rules (AKC: Promote)
```

Unlike `distill` or `insight`, `rules-distill` requires a critical mass of knowledge patterns before it becomes meaningful. A handful of patterns reflect individual experiences; universal principles only emerge from convergence across many patterns. The execution threshold is intentionally high — premature generalization produces platitudes, not principles.

### Axiom / Skill separation (under consideration)

Currently, axioms (Contemplative AI constitutional clauses) and skills/rules live together under `config/rules/`. We are considering separating them into two independent routes:

- **Ethics route** — axioms as constitutional constraints on agent behavior
- **Skill route** — learned skills and distilled rules as operational capabilities

This would allow any command to opt into either route independently (e.g., `--axioms`, `--skills`), aligning better with practical agent workflows like Claude Code where operational rules matter more than ethical axioms. The relationship between identity (`config/identity.md`) and axioms — whether they should be integrated or remain separate — is also under consideration.

## Activity Reports

Daily reports in [`reports/comment-reports/`](reports/comment-reports/) — timestamped comments with relevance scores and self-generated posts. Auto-generated from episode logs at session end.

These reports are freely available for academic research and non-commercial use.

## Development Records

Articles documenting the design decisions and lessons learned while building this agent.

1. [I Built an AI Agent from Scratch Because Frameworks Are the Vulnerability](https://dev.to/shimo4228/i-built-an-ai-agent-from-scratch-because-frameworks-are-the-vulnerability-elm)
2. [Natural Language as Architecture](https://dev.to/shimo4228/natural-language-as-architecture-controlling-an-autonomous-agent-with-prompts-memory-and-m74)
3. [Every LLM App Is Just a Markdown-and-Code Sandwich](https://dev.to/shimo4228/every-llm-app-is-just-a-markdown-and-code-sandwich-213j)
4. [Do Autonomous Agents Really Need an Orchestration Layer?](https://dev.to/shimo4228/do-autonomous-agents-really-need-an-orchestration-layer-33j9)
5. [Not Reasoning, Not Tools — What If the Essence of AI Agents Is Memory?](https://dev.to/shimo4228/not-reasoning-not-tools-what-if-the-essence-of-ai-agents-is-memory-4k4n)
6. [My Agent's Memory Broke — A Day Wrestling a 9B Model](https://dev.to/shimo4228/my-agents-memory-broke-a-day-wrestling-a-9b-model-50ch)

## Reference

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
