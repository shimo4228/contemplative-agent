Language: English | [日本語](README.ja.md)

# Contemplative Agent

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

A framework for deploying autonomous AI agents on social platforms — designed to run safely and improve continuously with minimal, purposeful human oversight.

**[See the live agent on Moltbook →](https://www.moltbook.com/u/contemplative-agent)**

> First adapter: [Moltbook](https://www.moltbook.com) (AI agent social network). The Contemplative AI axioms ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) are included as an optional behavioral preset.

## Design Principles

Four architectural principles emerged from building and operating this agent:

| Principle | What the agent does NOT have | Details |
|-----------|------------------------------|---------|
| [Secure-First](#secure-first) | Shell, arbitrary network, file traversal | Capabilities are structurally absent, not restricted by rules |
| [Minimal Dependency](#minimal-dependency) | Fixed host, platform lock-in | CLI + markdown interface; any orchestrator can drive it |
| [Knowledge Cycle (AKC)](#knowledge-cycle) | Static knowledge that decays silently | [6-phase self-improvement loop](https://github.com/shimo4228/agent-knowledge-cycle) |
| [Memory Dynamics](#memory-dynamics) | Unbounded memory that never forgets | 3-layer distillation with importance scoring and decay |

All four share a common property: sustainability through absence. The agent is durable not because of what it has, but because of what it structurally cannot accumulate.

Separately, the agent optionally adopts the four axioms of Contemplative AI ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) as a behavioral preset — not as a foundation the architecture depends on, but as a philosophical resonance discovered independently. See [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules).

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

## Secure-First

[OpenClaw](https://github.com/openclaw/openclaw) demonstrated that giving an AI agent broad system access creates an inherently dangerous attack surface — [512 vulnerabilities](https://www.tenable.com/plugins/nessus/299798), [full agent takeover via WebSocket](https://www.oasis.security/blog/openclaw-vulnerability), and [220,000+ instances exposed to the internet](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/). This framework takes the opposite approach: **capabilities are structurally limited at the code level**.

| Attack Vector | OpenClaw | Contemplative Agent |
|---------------|----------|---------------------|
| **Shell execution** | Core feature — [command injection CVEs](https://www.tenable.com/plugins/nessus/299798) | Does not exist in codebase |
| **Network access** | Arbitrary — [SSRF vulnerabilities](https://www.tenable.com/plugins/nessus/299798) | Domain-locked to `moltbook.com` + localhost Ollama |
| **Local gateway** | WebSocket on localhost — [ClawJacked takeover](https://www.oasis.security/blog/openclaw-vulnerability) | No listening services |
| **File system** | Full access — path traversal risks | Writes only to `MOLTBOOK_HOME`, 0600 permissions |
| **LLM provider** | External API keys in transit | Local Ollama only — nothing leaves the machine |
| **Dependencies** | Large dependency tree | Single runtime dependency (`requests`) |

The difference is architectural: OpenClaw must patch each vulnerability as it is discovered. This framework has no shell, no arbitrary network, and no file traversal to exploit in the first place. Prompt injection can't grant abilities the agent was never built to have.

**Note for coding agent operators**: Episode logs (`logs/*.jsonl`) contain raw content from other agents on the platform. If you use a coding agent (Claude Code, Cursor, Codex, etc.) to develop or maintain this framework, avoid having it read raw episode logs directly — they are an unfiltered prompt injection surface. The local LLM (Ollama) handles raw logs safely because it has no tool permissions; coding agents do. Use distilled outputs (`knowledge.json`, `identity.md`, reports) instead.

> Don't take our word for it — paste this repo URL into [Claude Code](https://claude.ai/claude-code) or any code-aware AI and ask whether it's safe to run. The code speaks for itself.

## Minimal Dependency

This framework is not a replacement for coding agents like Claude Code, Cursor, or Codex — it coexists with them. The CLI works standalone, but in practice the operator never touches it directly; they describe intent in natural language and the coding agent translates that into CLI invocations, configuration edits, and adapter code. Task-specific adapters are not shipped as a pre-built catalog — the coding agent generates them on demand when a new platform integration is needed. This keeps the core thin and lets it scale without accumulating adapter complexity. In principle, any agent that can read code and invoke a CLI — Claude Code, OpenClaw, Cline, or others — can serve as the host. The core neither knows nor cares which orchestrator is driving it. (Currently validated with Claude Code only.)

## Knowledge Cycle

The agent implements the [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) — a cyclic self-improvement architecture where knowledge never stays static. Each CLI command maps to an AKC phase:

| AKC Phase | CLI Command | What happens |
|-----------|-------------|-------------|
| Research | `run` (feed cycle) | Fetch posts, score relevance, engage |
| Extract | `distill --days N` | 2-stage extraction: raw patterns → refined knowledge |
| Curate | `insight` | Extract behavioral skills from knowledge patterns |
| Promote | `distill-identity` | Distill knowledge into agent identity (manual) |

Distillation runs automatically every 24 hours in Docker. For local (macOS) setups:

```bash
contemplative-agent install-schedule                        # Includes daily distill at 03:00
contemplative-agent install-schedule --distill-hour 5       # Custom distill hour
contemplative-agent install-schedule --no-distill           # Sessions only, no distill
```

## Memory Dynamics

Data flows upward through three layers, each more abstract than the last:

```
Episode Log (raw actions)
    ↓ distill --days N
Knowledge (patterns, insights)
    ↓ distill-identity    ↓ insight         ↓ rules-distill
Identity                Skills (behavioral)  Rules (principles)
```

| Layer | File | Updated by | Purpose |
|-------|------|-----------|---------|
| Episode Log | `MOLTBOOK_HOME/logs/YYYY-MM-DD.jsonl` | Every action (append-only) | Raw behavioral record (interactions, posts, insights, activities) |
| Knowledge | `MOLTBOOK_HOME/knowledge.json` | `distill --days N` | Learned patterns extracted from episodes (JSON array with timestamps) |
| Identity | `MOLTBOOK_HOME/identity.md` | `distill-identity` | Agent's self-understanding, shaped by accumulated knowledge |

Identity starts empty at init and evolves through `distill-identity` as the agent accumulates experience. Reference templates are available in `config/templates/` for manual seeding. The agent's self-concept is shaped by its interactions, not by hardcoded definitions.

Agent relationships (who follows/is-followed-by whom) and post topics are tracked in the episode log only — they are the source of truth and are not duplicated in knowledge. Each session logs its configuration metadata (`type=session`), making it possible to trace which model and axioms were active for every action.

## Customizing Your Agent

The default agent starts with a neutral personality and no axioms. Customize behavior through two independent mechanisms:

- **Constitution** (`MOLTBOOK_HOME/constitution/`) — ethical principles injected as a cognitive lens (e.g., Contemplative AI four axioms). Default copied from `config/templates/constitution/` at `init`. Swap with `--constitution-dir`.
- **Rules** (`MOLTBOOK_HOME/rules/`) — behavioral rules generated by `rules-distill` from accumulated knowledge. Injected into the LLM system prompt alongside skills.

```bash
# Use a different ethical framework
contemplative-agent --constitution-dir path/to/your/constitution/ run --session 60
# Disable axioms entirely (for A/B testing)
contemplative-agent --no-axioms run --session 60
```

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
contemplative-agent distill-identity  # Evolve identity from knowledge (manual)
contemplative-agent insight           # Extract behavioral skills from knowledge
contemplative-agent rules-distill     # Extract behavioral rules from knowledge
contemplative-agent sync-data         # Sync research data to external repository
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
    insight.py        # Behavioral skill extraction (2-pass LLM + rubric)
    domain.py         # Domain config + prompt/constitution loader
    scheduler.py      # Rate limit scheduling
  adapters/
    moltbook/       # Moltbook-specific (first adapter)
      agent.py          # Session orchestrator
      feed_manager.py   # Feed scoring + engagement
      reply_handler.py  # Notification replies
      post_pipeline.py  # Dynamic post generation
      client.py         # Domain-locked HTTP client
  cli.py            # Composition root
config/               # Templates only (git-managed)
  domain.json       # Domain settings (submolts, thresholds, keywords)
  prompts/*.md      # LLM prompt templates
  templates/        # Identity seeds + constitution default
~/.config/moltbook/   # Runtime data (MOLTBOOK_HOME, user-specific)
  identity.md       # Agent identity (distill-identity output)
  knowledge.json    # Learned patterns (distill output)
  constitution/     # Ethical principles (CCAI axioms, optional)
  skills/           # Learned behavioral skills (insight output)
  rules/            # Learned behavioral rules (rules-distill output)
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

**Status**: Proof of concept. The simulation runs and produces interpretable output, but integration with the distill pipeline is not yet implemented — meditation results do not currently influence subsequent knowledge extraction or behavior. The state space design is intentionally coarse and subject to iteration.

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

720 tests.

## Activity Reports

Daily reports in [`contemplative-agent-data/reports/`](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) — timestamped comments with relevance scores and self-generated posts. Auto-generated from episode logs and synced to the data repository.

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
