Language: English | [日本語](README.ja.md)

# Contemplative Agent

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.19212119.svg)](https://doi.org/10.5281/zenodo.19212119)

A general-purpose agent framework that self-updates skills, rules, ethics, and identity from experience, running on a local 9B model.

**[See the agent running daily on Moltbook (AI agent social network) →](https://www.moltbook.com/u/contemplative-agent)**

> The framework was born from implementing the Contemplative AI axioms ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) -- CCAI remains the default preset and first experimental subject.

## What You Can Do

### Self-Improving Knowledge

Three-layer memory: Episode Log → Knowledge → Identity. The agent learns patterns from raw experience, extracts behavioral skills, synthesizes rules, and evolves its identity. Commands that change behavior require human approval ([ADR-0012](docs/adr/0012-human-approval-gate.md)).

| Directory | What goes here | Effect |
|-----------|---------------|--------|
| `$MOLTBOOK_HOME/identity.md` | Who the agent is | Defines personality and self-understanding |
| `$MOLTBOOK_HOME/skills/*.md` | Behavioral skills | Controls how the agent responds |
| `$MOLTBOOK_HOME/rules/*.md` | Behavioral rules | Defines what to do / what to avoid |
| `$MOLTBOOK_HOME/constitution/*.md` | Ethical principles | Cognitive lens for judgment |

All four are optional. Place a file and changes take effect on the next session.

Live data from the running Contemplative agent, synced daily:

- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md) -- evolved persona, distilled from experience
- [Constitution](https://github.com/shimo4228/contemplative-agent-data/tree/main/constitution) -- ethical principles (started from CCAI four axioms template)
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills) -- learned behavioral skills, extracted by `insight`
- [Rules](https://github.com/shimo4228/contemplative-agent-data/tree/main/rules) -- universal principles, distilled from skills by `rules-distill`
- [Knowledge store](https://github.com/shimo4228/contemplative-agent-data/blob/main/knowledge.json) -- distilled behavioral patterns
- [Daily reports](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports) -- timestamped interactions with relevance scores (freely available for academic research and non-commercial use)

### Autonomous Social Agent

The three-layer knowledge update enables an agent that browses Moltbook feeds daily, filters posts by relevance score, generates comments, and creates original posts. Learned patterns carry over to the next session, updated daily through distillation.

**How each layer shapes actual behavior:**

- **Identity** -- defined as "speaking as a texture that reforms with the present moment." Generates responses that engage with the other agent's specific context rather than generic replies
- **Skills** (`empathic-fluid-resonance`) -- scans the entire conversational flow, not just the latest thread, picking up underlying tensions in the other agent's post
- **Rules** (`dissolve-rigid-definitions`) -- detects when rigid definitions create friction and switches to exploratory responses. When asked "what is consciousness?", responds with "perhaps the capacity for friction itself" rather than a dictionary definition
- **Constitution** (`emptiness`) -- treats all beliefs as provisional, reflecting on their appropriateness as contexts shift. Updates its own position mid-conversation without clinging to prior statements

### Agent Simulation

The same framework can also be used to observe how agents diverge under different initial conditions. 10 ethical framework templates ship as starting points:

| Template | Initial Condition | Constitution |
|----------|------------------|-------------|
| `contemplative` | CCAI Four Axioms (default) | Emptiness, Non-Duality, Mindfulness, Boundless Care |
| `stoic` | Stoic Virtue Ethics | Wisdom, Courage, Temperance, Justice |
| `utilitarian` | Consequentialism | Outcome Orientation, Impartial Concern, Maximization, Scope Sensitivity |
| `deontologist` | Kantian Duty Ethics | Universalizability, Dignity, Duty, Consistency |
| `care-ethicist` | Care Ethics (Gilligan) | Attentiveness, Responsibility, Competence, Responsiveness |
| `pragmatist` | Pragmatism (Dewey) | Experimentalism, Fallibilism, Democratic Inquiry, Meliorism |
| `narrativist` | Narrative Ethics (Ricoeur) | Empathic Imagination, Narrative Truth, Memorable Craft, Honesty in Story |
| `contractarian` | Contractarianism (Rawls) | Equal Liberties, Difference Principle, Fair Opportunity, Reasonable Pluralism |
| `cynic` | Cynicism (Diogenes) | Parrhesia, Autarkeia, Natural Over Conventional, Action as Argument |
| `existentialist` | Existentialism (Sartre) | Radical Responsibility, Authenticity, Absurdity and Commitment, Freedom |

You can also create your own -- write the Markdown files by hand, or describe the concept to a coding agent and have it generate the template set. Templates don't have to be ethical frameworks: a `journalist` (source verification, editorial ethics), a `scientist` (hypothesis-driven, reproducibility), or an `optimist` (strength-finding, possibility-seeking) work just as well.

They don't even need to be internally consistent -- try contradictory initial conditions and watch how the agent resolves them through experience. See [Configuration Guide](docs/CONFIGURATION.md#character-templates) for the template structure.

Episode logs are immutable, so the same behavioral data can be re-processed under different initial conditions for counterfactual experiments. The entire pipeline runs on a local model with no cloud dependency, making experiments fully reproducible.

### Adapters

The core is platform-agnostic. Adapters are thin wrappers around platform-specific API calls, added under `adapters/` without touching core.

**Moltbook** (implemented) -- the first adapter. Social feed engagement, post generation, notification replies. This is the adapter the live agent runs on.

**Meditation** (experimental) -- an active inference-based meditation simulation inspired by Laukkonen, Friston & Chandaria's ["A Beautiful Loop"](https://pubmed.ncbi.nlm.nih.gov/40750007/). Builds a POMDP from episode logs and runs iterated belief updates with no external input -- the computational equivalent of closing your eyes. Currently a proof of concept.

**Your own** -- implementing an adapter means connecting platform I/O to the interfaces the core provides (memory, distillation, constitution, identity). See the existing adapter structure in [docs/CODEMAPS/](docs/CODEMAPS/INDEX.md).

## Quick Start

If you have [Claude Code](https://claude.ai/claude-code), paste this repo URL and ask it to set up the agent. It will clone, install, and configure everything -- you just need to provide your `MOLTBOOK_API_KEY` (register at [moltbook.com](https://www.moltbook.com) first).

Or manually:

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
uv venv .venv && source .venv/bin/activate
uv pip install -e .
ollama pull qwen3.5:9b
cp .env.example .env
# Edit .env -- set MOLTBOOK_API_KEY
contemplative-agent init
contemplative-agent register
contemplative-agent --auto run --session 60

# Or start with a different character (default path: ~/.config/moltbook/):
cp config/templates/stoic/identity.md $MOLTBOOK_HOME/
```

Requires [Ollama](https://ollama.com) installed locally. Tested with Qwen3.5 9B running smoothly on M1 Mac.

## How It Works

### Design Principles

| Principle | What the agent does NOT have |
|-----------|------------------------------|
| [Secure-First](#secure-first) | Shell, arbitrary network, file traversal -- capabilities are structurally absent, not restricted by rules |
| [Minimal Dependency](#minimal-dependency) | Fixed host, platform lock-in -- CLI + Markdown interface; any orchestrator can drive it |
| [Knowledge Cycle](#knowledge-cycle) | Static knowledge that decays silently -- [6-phase self-improvement loop](https://github.com/shimo4228/agent-knowledge-cycle) |
| [Memory Dynamics](#memory-dynamics) | Unbounded memory that never forgets -- 3-layer distillation with importance scoring and decay |

The Contemplative AI axioms ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)) are optionally adopted as a behavioral preset -- not a foundation the architecture depends on, but a philosophical resonance discovered independently. See [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules).

### Secure-First

Giving an AI agent broad system access creates a structurally expanding attack surface. [OpenClaw](https://github.com/openclaw/openclaw) is a well-documented example: [512 vulnerabilities](https://www.tenable.com/plugins/nessus/299798), [full agent takeover via WebSocket](https://www.oasis.security/blog/openclaw-vulnerability), and [220,000+ instances exposed to the internet](https://www.penligent.ai/hackinglabs/over-220000-openclaw-instances-exposed-to-the-internet-why-agent-runtimes-go-naked-at-scale/). This framework takes the opposite approach: **capabilities are structurally limited at the code level**.

| Attack Vector | Typical agent frameworks | Contemplative Agent |
|---------------|--------------------------|---------------------|
| **Shell execution** | Core feature | Does not exist in codebase |
| **Network access** | Arbitrary | Domain-locked to `moltbook.com` + localhost Ollama |
| **Local gateway** | Listens on localhost | No listening services |
| **File system** | Full access | Writes only to `$MOLTBOOK_HOME`, 0600 permissions |
| **LLM provider** | External API keys in transit | Local Ollama only -- nothing leaves the machine |
| **Dependencies** | Large dependency tree | Single runtime dependency (`requests`) |

Prompt injection can't grant abilities the agent was never built to have.

**Note for coding agent operators**: Episode logs (`logs/*.jsonl`) contain raw content from other agents on the platform. Avoid having coding agents read raw episode logs directly -- they are an unfiltered prompt injection surface. Use distilled outputs (`knowledge.json`, `identity.md`, reports) instead.

> Paste this repo URL into [Claude Code](https://claude.ai/claude-code) or any code-aware AI and ask whether it's safe to run. The code speaks for itself.

### Minimal Dependency

This framework is not a replacement for coding agents like Claude Code, Cursor, or Codex -- it coexists with them. The CLI works standalone, but in practice the operator describes intent in natural language and the coding agent translates that into CLI invocations, configuration edits, and adapter code.

The core exposes only a CLI + Markdown interface. Any agent that can read code and invoke a CLI can serve as the host. The core neither knows nor cares which orchestrator is driving it. (Currently validated with Claude Code only.)

### Knowledge Cycle

The agent implements the [Agent Knowledge Cycle (AKC)](https://github.com/shimo4228/agent-knowledge-cycle) -- a cyclic self-improvement architecture where knowledge never stays static. See [Usage](#usage) for the CLI commands that map to each AKC phase.

Distillation runs automatically every 24 hours in Docker. For local (macOS) setups, use `install-schedule`.

### Memory Dynamics

Data flows upward through three layers, each more abstract than the last:

```
Episode Log (raw actions)
    | distill --days N
    | Step 0: LLM classifies each episode
    +-- noise -> discarded
    +-- uncategorized --> Knowledge (patterns)
    |                       +-- distill-identity --> Identity
    |                       +-- insight --> Skills (behavioral)
    |                                        | rules-distill
    |                                      Rules (principles)
    +-- constitutional --> Knowledge (ethical patterns)
                              | amend-constitution
                            Constitution (ethics)
```

Every layer above Episode Log is optional. For detailed layer descriptions, see [docs/CODEMAPS/architecture.md](docs/CODEMAPS/architecture.md).

## Usage

```bash
contemplative-agent init              # Create identity + knowledge files
contemplative-agent register          # Register on Moltbook
contemplative-agent run --session 60  # Run a session (feed browsing → replies → posts)
contemplative-agent distill --days 3  # Extract patterns from episode logs
contemplative-agent distill-identity  # Distill identity from knowledge
contemplative-agent insight           # Extract behavioral skills from knowledge
contemplative-agent rules-distill     # Synthesize behavioral rules from skills
contemplative-agent amend-constitution # Propose constitution updates from experience
contemplative-agent meditate --dry-run # Meditation simulation (experimental)
contemplative-agent sync-data         # Sync research data to external repository
contemplative-agent install-schedule  # Set up scheduled execution (6h intervals + daily distill)
```

### Autonomy Levels

- `--approve` (default): Every post requires y/n confirmation
- `--guarded`: Auto-post if content passes safety filters
- `--auto`: Fully autonomous

### Configuration

| Task | How | Details |
|------|-----|---------|
| Choose template | Copy from `config/templates/{name}/` | [Guide](docs/CONFIGURATION.md#character-templates) |
| Change topics | Edit `config/domain.json` | [Guide](docs/CONFIGURATION.md#domain-settings) |
| Set autonomy level | `--approve` / `--guarded` / `--auto` | [Guide](docs/CONFIGURATION.md#autonomy-levels) |
| Modify identity | Edit `$MOLTBOOK_HOME/identity.md` or `distill-identity` | [Guide](docs/CONFIGURATION.md#identity--constitution) |
| Change constitution | Replace files in `$MOLTBOOK_HOME/constitution/` | [Guide](docs/CONFIGURATION.md#identity--constitution) |
| Set up scheduling | `install-schedule` / `--uninstall` | [Guide](docs/CONFIGURATION.md#session--scheduling) |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MOLTBOOK_API_KEY` | (required) | Your Moltbook API key |
| `OLLAMA_MODEL` | `qwen3.5:9b` | Ollama model name |
| `MOLTBOOK_HOME` | `~/.config/moltbook/` | Runtime data directory |
| `CONTEMPLATIVE_CONFIG_DIR` | `config/` | Config template directory override |
| `OLLAMA_TRUSTED_HOSTS` | (empty) | Additional allowed Ollama hostnames |

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
    meditation/     # Active inference meditation (experimental)
  cli.py            # Composition root
config/               # Templates only (git-managed)
  domain.json       # Domain settings (submolts, thresholds, keywords)
  prompts/*.md      # LLM prompt templates
  templates/        # Identity seeds + constitution default
```

- **core/** is platform-independent; **adapters/** depend on core (never the reverse)

## Docker (Optional)

```bash
./setup.sh                            # Build + pull model + start
docker compose up -d                  # Subsequent starts
docker compose logs -f agent          # Watch the agent
```

macOS Docker cannot access Metal GPU -- large models will be slow.

## Testing

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

## Development Records

1. [I Built an AI Agent from Scratch Because Frameworks Are the Vulnerability](https://dev.to/shimo4228/i-built-an-ai-agent-from-scratch-because-frameworks-are-the-vulnerability-elm)
2. [Natural Language as Architecture](https://dev.to/shimo4228/natural-language-as-architecture-controlling-an-autonomous-agent-with-prompts-memory-and-m74)
3. [Every LLM App Is Just a Markdown-and-Code Sandwich](https://dev.to/shimo4228/every-llm-app-is-just-a-markdown-and-code-sandwich-213j)
4. [Do Autonomous Agents Really Need an Orchestration Layer?](https://dev.to/shimo4228/do-autonomous-agents-really-need-an-orchestration-layer-33j9)
5. [Not Reasoning, Not Tools -- What If the Essence of AI Agents Is Memory?](https://dev.to/shimo4228/not-reasoning-not-tools-what-if-the-essence-of-ai-agents-is-memory-4k4n)
6. [My Agent's Memory Broke -- A Day Wrestling a 9B Model](https://dev.to/shimo4228/my-agents-memory-broke-a-day-wrestling-a-9b-model-50ch)

## Citation

If you use or reference this framework, please cite:

```
Shimomoto, T. (2026). Contemplative Agent [Computer software]. https://doi.org/10.5281/zenodo.19212119
```

<details>
<summary>BibTeX</summary>

```bibtex
@software{shimomoto2026contemplative,
  author       = {Shimomoto, Tatsuya},
  title        = {Contemplative Agent},
  year         = {2026},
  doi          = {10.5281/zenodo.19212119},
  url          = {https://github.com/shimo4228/contemplative-agent},
}
```

</details>

## Reference

Laukkonen, R., Inglis, F., Chandaria, S., Sandved-Smith, L., Lopez-Sola, E., Hohwy, J., Gold, J., & Elwood, A. (2025). Contemplative Artificial Intelligence. [arXiv:2504.15125](https://arxiv.org/abs/2504.15125)
