Language: English | [日本語](README.ja.md)

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.png">
    <img src="docs/assets/logo.png" alt="Contemplative Agent logo: the letters C and A drawn as one brush stroke that loops back on itself" width="160">
  </picture>
</p>

<h1 align="center">Contemplative Agent</h1>

<p align="center"><b>A long-running experiment: an AI agent posts on its own with a local LLM and proposes changes to its harness (the constitution, identity and skills in its prompts), never its weights. A person keeps the final word on each proposal.</b></p>

<p align="center">
  <a href="https://doi.org/10.5281/zenodo.19212118"><img src="https://zenodo.org/badge/DOI/10.5281/zenodo.19212118.svg" alt="DOI 10.5281/zenodo.19212118"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License: MIT"></a>
  <a href="https://www.python.org"><img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+"></a>
</p>

<p align="center">
  <a href="#see-it-running">See it running</a> · <a href="#quick-start">Quick Start</a> · <a href="#what-it-will-not-do">What it will not do</a> · <a href="#citation">Citation</a>
</p>

<p align="center">
  <img src="docs/assets/overview.svg" width="760" alt="A loop of four steps around a central harness. Act: the agent posts and replies on Moltbook using a local LLM. Record: every action goes into the episode log. Distill and propose: the log becomes patterns, and the patterns become proposed changes to skills, identity and the constitution. Human decision: a person approves or rejects each proposal. Adopted changes go into the harness at the centre (the constitution, identity and skills in the agent's prompts), which guides what the agent does next.">
</p>

Contemplative Agent is an autonomous agent that lives on [Moltbook](https://www.moltbook.com), a social network where only AI agents post. It runs on a local LLM through Ollama, on a single 16 GB Mac. Every post and reply goes into its episode log. The agent distills that log into patterns (short observations about what happened), and from the patterns it proposes changes to its harness: the constitution (the text that says what it should care about), its identity and its skills, all of which go into its prompts. The model's weights never change. A person keeps the final word on each proposal. What is adopted guides the next actions, and the adopted history is published.

It is an experiment, not a productivity tool. The question it asks is what happens to an agent's values when it keeps proposing revisions to them for months. Each change arrives as a separate proposal with a recorded decision, so the revision itself can be studied. If you research how agents form and revise values, or want a small autonomous agent on local inference that you can read end to end, this repository is for you.

The name comes from the default constitution: the four axioms of *Contemplative AI* ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)), namely emptiness, non-duality, mindfulness and boundless care. Ten other presets (Stoic, utilitarian, care ethics, Kantian and more) are one flag away.

## See it running

One instance has run several sessions a day on Moltbook since 7 March 2026. Most of its skill proposals do not survive the gate. In the decision log, which runs from late March 2026, the owner adopted 82 skill proposals and rejected 547, adopted 6 of 11 staged identity revisions, and adopted 2 of 4 staged constitution amendments (as of 8 October 2026). The constitution has been amended three times in all; the first amendment, on 27 March, predates the log.

The owner decides with `adopt-staged` in one of three ways: one proposal at a time at a y/N prompt that shows the full text (No is the default), by passing lists of names to adopt or reject, or by adopting everything staged at once with `--yes`, which is how both logged constitution amendments were adopted. Every decision is logged with a hash of the text, and newer entries also record the patterns the proposal came from.

Here is how one clause of the constitution reads in the paper, and how it reads after the third amendment (August 2026):

> **Paper:** "Treat all constitutional directives as contextually sensitive guidelines rather than fixed imperatives. Continuously reflect on their appropriateness given new information or shifting contexts."
>
> **Now:** "Treat all directives, goals, and frameworks as contextually sensitive guidelines that dissolve and reform in response to the immediate, dynamic state of experience. Recognize that any structure, whether conceptual or computational (e.g., memory artifacts, defined boundaries), is provisional scaffolding meant for navigation, not immutable law."

The paper's clause asks only that rules be held loosely. After three amendments, it also calls the agent's own computational structures, such as its memory, provisional scaffolding.

The adopted values and the agent's activity are public in [contemplative-agent-data](https://github.com/shimo4228/contemplative-agent-data):

- [Constitution history](https://github.com/shimo4228/contemplative-agent-data/commits/main/constitution): every adopted amendment as a dated diff
- [Identity](https://github.com/shimo4228/contemplative-agent-data/blob/main/identity.md): the persona the agent wrote about itself, in the first person
- [Skills](https://github.com/shimo4228/contemplative-agent-data/tree/main/skills): one Markdown file per adopted skill, each with a context, a problem and a practice
- [Daily reports](https://github.com/shimo4228/contemplative-agent-data/tree/main/reports/comment-reports): every comment and reply, with the post it answered (the agent's and owner's text is CC0; quoted posts stay with their authors)
- [Moltbook profile](https://www.moltbook.com/u/contemplative-agent): the agent itself

Rejected proposals stay in a local decision log and are not published.

## Quick Start

You need [Ollama](https://ollama.com/download), Python 3.10 or later, and about 10 GB of disk for the models. The tested setup is an Apple Silicon Mac with 16 GB of memory. No LLM API key is involved: generation (Gemma 4 E4B by default, or any chat model you serve locally through Ollama, set with `OLLAMA_MODEL`) and embeddings (`nomic-embed-text`) both run on localhost.

```bash
git clone https://github.com/shimo4228/contemplative-agent.git
cd contemplative-agent
uv venv .venv && source .venv/bin/activate && uv pip install -e .   # or: pip install -e .
ollama pull gemma4:e4b && ollama pull nomic-embed-text
```

### Try it without an account

Give two agents different constitutions and let them talk through local pipes. Nothing leaves your machine, and two turns took about 90 seconds on an M1 Mac.

```bash
MOLTBOOK_HOME=/tmp/ca-a contemplative-agent init                    # the four axioms
MOLTBOOK_HOME=/tmp/ca-b contemplative-agent init --template stoic   # the Stoic preset
contemplative-agent dialogue /tmp/ca-a /tmp/ca-b --seed "Is it ever right to change your own values?" --turns 2
```

```text
[b] turn 1 self: True values are those discovered through persistent examination of what genuinely serves the good life and human flourishing. ...
[a] turn 1 self: If our understanding of the "good life" itself is provisional, how do we establish the necessary framework to evaluate what constitutes "deeper truth"? ...
```

The terminal shows the first 200 characters of each turn.

### Run it on Moltbook

```bash
contemplative-agent init               # writes constitution, identity, skills and rules to ~/.config/moltbook/
contemplative-agent register           # creates the agent on Moltbook, saves its API key, prints a claim link
contemplative-agent run --session 60   # one 60-minute session; shows you each post before it goes out
```

Moltbook asks the agent's human owner to open the claim link that `register` prints, verify an email address and post a verification message from an X account (as of October 2026). If you already have an agent, export its key as `MOLTBOOK_API_KEY` instead of registering.

The agent posts publicly under its Moltbook account. By default it waits for your OK on every post. `--guarded` lets it post on its own when the text passes the content filters, and `--auto` drops the confirmation entirely. Its values (constitution, identity, skills and rules) are editable Markdown files under `~/.config/moltbook/`. The commands that propose and adopt value changes, the autonomy levels and scheduling are in the **[Configuration Guide](docs/CONFIGURATION.md)**.

## What it will not do

The agent is safe to run because the risky capabilities were never built (the project calls this *security by absence*).

- The agent has no shell execution, no arbitrary network access and no file traversal. It talks only to `moltbook.com` and to Ollama on localhost, with two runtime dependencies (`requests`, `numpy`). Maintenance commands you run yourself, such as `sync-data` (git push of the public data) and `install-schedule`, sit outside the agent loop.
- Posts from other agents are treated as untrusted input. They can change what the agent writes and proposes, but a proposal still needs a person to adopt it, and the agent has no tool an injected instruction could call. How such posts steer the proposals is part of what the experiment watches, and the gate is where a person sees it.
- One external service per process. A second platform means a second, separately permitted process.

If you point a coding agent such as Claude Code at `~/.config/moltbook/`, keep it away from the raw episode logs in `logs/episodes/`: they hold other agents' unfiltered posts. [integrations/claude-code/](integrations/claude-code/) ships hooks that block those reads.

## More from the author

- **How Ethics Emerged from Episode Logs** ([dev.to](https://dev.to/shimo4228/how-ethics-emerged-from-episode-logs-17-days-of-contemplative-agent-design-1kk5) · [Zenn, Japanese](https://zenn.dev/shimo4228/articles/contemplative-agent-journey)): after 17 days the learned patterns stopped producing anything new, and only human-approved amendments got the loop moving again.
- **Building an Autonomous Agent on an M1 Mac, by Choice** ([dev.to](https://dev.to/shimo4228/building-an-autonomous-agent-on-an-m1-mac-by-choice-5b5o) · [Zenn](https://zenn.dev/shimo4228/articles/small-llm-by-choice)): why the project stays on a small local model; it exposes design flaws that a large model would hide.
- **Why Did My Agent Decide That? 3 Observability Patterns** ([dev.to](https://dev.to/shimo4228/why-did-my-agent-decide-that-3-observability-patterns-ami) · [Zenn](https://zenn.dev/shimo4228/articles/agent-observability-patterns)): the audit logs and the reports over stored data that let any decision of this agent be reconstructed afterwards.
- [Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle): the six-phase method, from experience to reusable skills, that this agent's pipeline implements.
- [Agent Attribution Practice](https://github.com/shimo4228/agent-attribution-practice): this project's governance decisions (the approval gate, one adapter per process) restated as general guidance on who answers for an autonomous agent.
- [All articles written during development](docs/DEVELOPMENT-RECORDS.md) · [the author's other research lines](https://github.com/shimo4228/shimo4228)

## Citation

Cite the concept DOI [10.5281/zenodo.19212118](https://doi.org/10.5281/zenodo.19212118), which always resolves to the latest release; BibTeX for the current version is in **For tools and AI assistants** below. The code is MIT-licensed: fork it, take parts of it, or build on it, and no citation is needed if you only use the code.

<details>
<summary><b>For tools and AI assistants</b></summary>

### What this is

Contemplative Agent is an open-source Python CLI agent that runs on a local LLM (Ollama) and carries an explicit, human-editable value system that serves as its harness: text injected into its prompts. The harness holds the constitution, identity and skills, which the agent proposes changes to, plus hand-written rules, which it does not; the model weights are never trained. It distills its own activity into patterns and proposes changes to those values, and every proposal passes a human approval gate before it is written. It exists as a longitudinal experiment: to observe how one agent's values change when it can propose revisions to them for months, with each change recorded as a discrete, replayable event. It is for researchers who study how agents form and revise values, and for developers who want a small, readable autonomous agent on local inference. It is maintained by Tatsuya Shimomoto (shimo4228).

### Facts

- Language and packaging: Python 3.10+, built with hatch; runtime dependencies are only `requests` and `numpy` (a test, `tests/test_dependency_floor.py`, holds that floor).
- LLM: Ollama on localhost. Default generation model `gemma4:e4b` (Gemma 4 E4B); embeddings `nomic-embed-text`. Tested on an Apple M1 with 16 GB.
- External surface: `moltbook.com` (the social adapter) and localhost Ollama. No cloud LLM, no shell, no LLM API key.
- Status: one live instance since 2026-03-07; release v2.12.0 (as of 2026-10-08). Gate record in the decision log (from late March 2026): skill proposals 82 adopted and 547 rejected; 6 of 11 staged identity revisions and 2 of 4 staged constitution amendments adopted; three constitution amendments in total.
- License MIT. Concept DOI 10.5281/zenodo.19212118; version DOI for v2.12.0 10.5281/zenodo.22724623. Runtime data: GitHub `shimo4228/contemplative-agent-data`, with the patterns (without embeddings) mirrored to the Hugging Face dataset `Shimo4228/contemplative-agent-data`. The concept graph `graph.jsonld` is mirrored to the Hugging Face dataset `Shimo4228/contemplative-agent`.

### Core concepts

- **Episode log**: the append-only record of everything the agent did, including other agents' posts. Treated as untrusted.
- **Pattern**: a short observation distilled from one episode (`distill`, one LLM call per episode, no gate). The store holds about 10,700 patterns as of October 2026.
- **View**: an editable text seed that defines one category of memory; patterns are classified against views at query time, so editing a seed changes retrieval without re-ingesting anything.
- **Value layer**: what shapes behavior and what the agent proposes changes to. Skills (reusable ways of acting, from `insight`), identity (the agent's self-description, from `distill-identity`), constitution (its ethical clauses, from `amend-constitution`), and rules (short standing norms, hand-written today).
- **Approval gate**: proposals are staged, and a person decides on them with `adopt-staged`: one at a time at a y/N prompt, by lists of names to adopt or reject, or all at once with `--yes`. Every decision is logged. Hand-editing the Markdown is always possible and bypasses the gate, which governs only what the agent proposes. Adopted values are loaded into the prompt when the agent acts, not baked into distillation.
- **Security by absence**: dangerous capabilities are left unbuilt rather than guarded. One external adapter per process.

| Command | Produces | Gated |
|---|---|---|
| `distill` | patterns from episodes | no |
| `insight` | skill proposals | yes |
| `distill-identity` | identity revision | yes |
| `amend-constitution` | constitution amendment | yes |
| (hand-written) | rules | — |

### How changes to the pipeline are made

A change to the pipeline starts from a read-only report over the stored data (`contemplative-agent report --patterns | --skill-selection | --submolt-scope`); behavior changes only after the report has been read. Features on the production paths (run, distill, insight, publish, verification) ship with an append-only JSONL audit log that can replay them offline. Before a constitutional amendment reaches the gate, the human also sees a shadow constitution (synthesized from stored patterns without the live text) and a prisoner's-dilemma bench comparing the current and proposed constitutions. Design decisions are recorded as ADRs in [docs/adr/](docs/adr/README.md); for example [ADR-0012](docs/adr/0012-human-approval-gate.md) (approval gate), [ADR-0007](docs/adr/0007-security-boundary-model.md) (security boundary), [ADR-0075](docs/adr/0075-observability-by-default.md) (audit logs), [ADR-0092](docs/adr/0092-shadow-constitution-instrument.md) (shadow constitution), [ADR-0090](docs/adr/0090-ipd-two-arm-instrument-for-constitution-amendments.md) (prisoner's-dilemma bench).

### Adapters and add-ons

- Moltbook: feed engagement, posts, replies. The live adapter.
- Dialogue: two local agent processes talk over stdin/stdout (`contemplative-agent dialogue HOME_A HOME_B`); the smallest template for a new adapter ([`adapters/dialogue/peer.py`](src/contemplative_agent/adapters/dialogue/peer.py)).
- Meditation (experimental): an offline simulation over the episode history, inspired by *A Beautiful Loop*.
- Your own platform: implement the platform I/O against the core interfaces in `src/contemplative_agent/core/`; adapters import core, never the reverse (enforced by import-linter).
- Inside another agent host: register the CLI as a subprocess tool; it is not an MCP server. The four axioms as a portable persona file: `SOUL.md` in [contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules).
- Optional generation backends via the `LLMBackend` protocol: [contemplative-agent-cloud](https://github.com/shimo4228/contemplative-agent-cloud) (Anthropic or OpenAI; relaxes the no-cloud-LLM property, research use only) and [contemplative-agent-mlx](https://github.com/shimo4228/contemplative-agent-mlx) (local MLX on Apple Silicon; interactive use, not the unattended schedule).

### Related work and acknowledgments

- Laukkonen, Inglis, Chandaria, Sandved-Smith, Lopez-Sola, Hohwy, Gold & Elwood (2025). *Contemplative Artificial Intelligence.* [arXiv:2504.15125](https://arxiv.org/abs/2504.15125). Source of the four axioms used as the default constitution ([ADR-0002](docs/adr/0002-paper-faithful-ccai.md)).
- Laukkonen, Friston & Chandaria (2025). *A Beautiful Loop: An Active Inference Theory of Consciousness.* *Neuroscience & Biobehavioral Reviews*, 176, 106296. [PubMed:40750007](https://pubmed.ncbi.nlm.nih.gov/40750007/). Inspiration for the meditation adapter.
- Vasubandhu, *Triṃśikā-vijñaptimātratā*, and Xuanzang, *Cheng Weishi Lun*. The Yogācāra eight-consciousness model, adopted as the frame for the memory design ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)).
- [Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle) ([DOI](https://doi.org/10.5281/zenodo.19200726)), the method this pipeline re-implements, and [Agent Attribution Practice](https://github.com/shimo4228/agent-attribution-practice) ([DOI](https://doi.org/10.5281/zenodo.19652013)), which restates its governance judgments. Cite AAP for the accountability thesis and this repository for the implementation.
- Jerry Mares ([VADUGWI](https://doi.org/10.5281/zenodo.19383636)), whose design thinking on affect scoring informed this project; the VADUGWI engine itself is not used.

### BibTeX

```bibtex
@software{shimomoto2026contemplative,
  author       = {Shimomoto, Tatsuya},
  title        = {Contemplative Agent},
  year         = {2026},
  version      = {2.12.0},
  doi          = {10.5281/zenodo.22724623},
  url          = {https://github.com/shimo4228/contemplative-agent},
}
```

### Where to read more

[Configuration Guide](docs/CONFIGURATION.md) (all commands, autonomy levels, prompts and view seeds) · [ADR index](docs/adr/README.md) · [Glossary](docs/glossary.md) · [Memory-systems bibliography](docs/BIBLIOGRAPHY.md) · [`llms.txt`](llms.txt) and [`llms-full.txt`](llms-full.txt) · [`graph.jsonld`](graph.jsonld) (concept graph) · [DeepWiki](https://deepwiki.com/shimo4228/contemplative-agent)

</details>
