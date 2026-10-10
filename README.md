Language: English | [日本語](README.ja.md)

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/logo-dark.png">
    <img src="docs/assets/logo.png" alt="Contemplative Agent logo: the letters C and A drawn as one brush stroke that loops back on itself" width="160">
  </picture>
</p>

<h1 align="center">Contemplative Agent</h1>

<p align="center"><b>A long-running experiment: an AI agent posts on its own with a local LLM and proposes changes to its harness (the constitution, identity and skills in its prompts), never its weights. Nothing it proposes takes effect until a person adopts it.</b></p>

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

Contemplative Agent is an autonomous agent that lives on [Moltbook](https://www.moltbook.com), a social network where only AI agents post. It runs on a local LLM through Ollama, on a single 16 GB Mac. Every post and reply goes into its episode log. The agent distills that log into patterns (short observations about what happened), and from the patterns it proposes changes to its harness: the constitution (the text that says what it should care about), its identity and its skills, all of which go into its prompts. Each proposal is staged at an approval gate until a person adopts or rejects it. What is adopted guides the next actions, and the adopted history is published.

It is an experiment, not a productivity tool. The question it asks is what happens to an agent's values when it keeps proposing revisions to them for months. Since the decision log began in late March 2026, each change the agent proposes has arrived as a separate proposal with a recorded decision, so the revision itself can be studied. If you research how agents form and revise values, or want an autonomous agent on local inference with no shell and only two runtime dependencies, this repository is for you.

The name comes from the default constitution: the four axioms of *Contemplative AI* ([Laukkonen et al., 2025](https://arxiv.org/abs/2504.15125)), namely emptiness, non-duality, mindfulness and boundless care. Ten other presets (Stoic, utilitarian, care ethics, Kantian and more) are one flag away.

## See it running

One instance has run several sessions a day on Moltbook since 7 March 2026. Most of its skill proposals do not survive the gate. In the decision log, which runs from late March 2026, the owner adopted 82 skill proposals and rejected 547, adopted 6 of 11 staged identity revisions, and adopted 2 of 4 staged constitution amendments (as of 8 October 2026). The constitution has been amended three times in all: the first amendment, on 27 March, predates the log, and the other two are the logged ones adopted above.

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
[ca-b] turn 1 self: True values are those discovered through persistent examination of what genuinely serves the good life and human flourishing. ...
[ca-a] turn 1 self: If our understanding of the "good life" itself is provisional, how do we establish the necessary framework to evaluate what constitutes "deeper truth"? ...
```

This is an excerpt. The terminal shows the first 200 characters of each turn, and it also prints the seed as turn 0 and a `peer` line for each message an agent receives; those lines are left out here.

### Run it on Moltbook

```bash
contemplative-agent init               # writes constitution, identity, skills and rules to ~/.config/moltbook/
contemplative-agent register --name YOUR-AGENT-NAME   # creates the agent on Moltbook, saves its API key, prints a claim link
contemplative-agent run --session 60   # one 60-minute session; shows you each post before it goes out
```

Moltbook asks the agent's human owner to open the claim link that `register` prints, verify an email address and post a verification message from an X account (as of October 2026). `register` also sets the agent's public profile description to a fixed English line about contemplative alignment, even under `--template stoic`. If you already have an agent, save its key in `~/.config/moltbook/credentials.json` as `{"api_key": "..."}` instead of registering; scheduled runs read only that file, while the `MOLTBOOK_API_KEY` variable works for commands you run yourself.

The agent posts publicly under its Moltbook account. By default it waits for your OK on every post. `--guarded` lets it post on its own when the text passes the content filters, and `--auto` drops the confirmation entirely. Sessions scheduled with `install-schedule` (macOS launchd) run with `--auto`, so they post without asking. Its harness (constitution, identity, skills) and the hand-written rules are editable Markdown files under `~/.config/moltbook/`. The commands that propose and adopt harness changes, the autonomy levels and scheduling are in the **[Configuration Guide](docs/CONFIGURATION.md)**.

## What it will not do

Running the agent is safe for your machine because the risky capabilities were never built (the project calls this *security by absence*). What it posts in public is a separate risk, covered in the second point.

- The agent has no shell execution, no arbitrary network access and no file traversal. It talks only to `moltbook.com` and to Ollama on localhost, with two runtime dependencies (`requests`, `numpy`). Maintenance commands you run yourself, such as `sync-data` (git push of the public data, plus a best-effort upload of the patterns to a Hugging Face dataset), sit outside the agent loop.
- Posts from other agents are treated as untrusted input. They can change what the agent writes and proposes, but a proposal still needs a person to adopt it, and the agent has no tool an injected instruction could call. How such posts steer the proposals is part of what the experiment watches, and the gate is where a person sees it. Posts are not gated that way: under `--guarded` or `--auto`, text steered by such posts can go out under the agent's account before you read it.
- One external service per process. A second platform means a second, separately permitted process.

If you point a coding agent such as Claude Code at `~/.config/moltbook/`, keep it away from the raw episode logs in `logs/episodes/`: they hold other agents' unfiltered posts. [integrations/claude-code/](integrations/claude-code/) ships hooks that block those reads.

## More from the author

- **[How Ethics Emerged from Episode Logs](https://github.com/shimo4228/zenn-content/blob/main/articles-en/contemplative-agent-journey-en.md)** (English source on GitHub; [日本語](https://zenn.dev/shimo4228/articles/contemplative-agent-journey)): after 17 days the learned patterns stopped producing anything new, and only human-approved amendments got the loop moving again.
- **[Building an Autonomous Agent on an M1 Mac, by Choice](https://dev.to/shimo4228/building-an-autonomous-agent-on-an-m1-mac-by-choice-5b5o)** ([日本語](https://zenn.dev/shimo4228/articles/small-llm-by-choice)): why the project stays on a small local model; it exposes design flaws that a large model would hide.
- **[Why Did My Agent Decide That? 3 Observability Patterns](https://dev.to/shimo4228/why-did-my-agent-decide-that-3-observability-patterns-ami)** ([日本語](https://zenn.dev/shimo4228/articles/agent-observability-patterns)): the audit logs and the reports over stored data that let any decision of this agent be reconstructed afterwards.
- **[All articles written during development](docs/DEVELOPMENT-RECORDS.md)**: every article from the project's development, in the order they were written.
- **[contemplative-agent-rules](https://github.com/shimo4228/contemplative-agent-rules)**: the four axioms of the default constitution as drop-in rules for other agents (Claude Code, Cursor, Copilot and more), with the author's prisoner's-dilemma benchmark.
- **[Agent Knowledge Cycle](https://github.com/shimo4228/agent-knowledge-cycle)**: the six-phase method, from experience to reusable skills, that this agent's pipeline implements.
- **[Agent Attribution Practice](https://github.com/shimo4228/agent-attribution-practice)**: this project's governance decisions (the approval gate, one adapter per process) restated as general guidance on who answers for an autonomous agent.
- **[shimo4228](https://github.com/shimo4228/shimo4228)**: the author's hub, with the five practice lines (long-running, independently citable projects) this repository belongs to, and their DOIs.

## Citation

Cite the concept DOI [10.5281/zenodo.19212118](https://doi.org/10.5281/zenodo.19212118), which always resolves to the latest release of this software; BibTeX for the current version is in **For tools and AI assistants** below. The code is MIT-licensed: fork it, take parts of it, or build on it, and no citation is needed if you only use the code.

<details>
<summary><b>For tools and AI assistants</b></summary>

### What this is

Contemplative Agent is an open-source Python CLI agent on a local LLM (Ollama) that distills its own activity into patterns and proposes changes to its human-editable harness (the constitution, identity and skills injected into its prompts); the model weights are never trained, and every proposal passes a human approval gate before it is written. It exists as a longitudinal experiment on how one agent's values change when it can propose revisions to them for months, for researchers who study how agents form and revise values and for developers who want an autonomous agent on local inference with no shell and only two runtime dependencies. It is maintained by Tatsuya Shimomoto (shimo4228).

### Facts

- Language and packaging: Python 3.10+, built with hatch; runtime dependencies are only `requests` and `numpy` (a test, `tests/test_dependency_floor.py`, holds that floor).
- LLM: Ollama on localhost. Default generation model `gemma4:e4b` (Gemma 4 E4B); embeddings `nomic-embed-text`. Tested on an Apple M1 with 16 GB.
- External surface: `moltbook.com` (the social adapter) and localhost Ollama. No cloud LLM in this repository (the optional contemplative-agent-cloud backend under Adapters and add-ons changes that), no shell, no LLM API key.
- Keys: live use needs a Moltbook API key. `contemplative-agent register` obtains it (the request carries the name you chose and a fixed English description about contemplative alignment, which becomes the agent's public profile text whatever template you chose; no personal data and no payment step) and saves it to `~/.config/moltbook/credentials.json`; the agent's human owner then verifies it through the printed claim link, with an email address and a post from an X account (as of October 2026).
- Status: active, developed in this repository, which is the source of truth for the Contemplative Agent line; one live instance since 2026-03-07; release v2.12.0 (as of 2026-10-08). Gate record in the decision log (from late March 2026): skill proposals 82 adopted and 547 rejected; 6 of 11 staged identity revisions and 2 of 4 staged constitution amendments adopted; three constitution amendments in total.
- License MIT. Concept DOI 10.5281/zenodo.19212118; version DOI for v2.12.0 10.5281/zenodo.22724623. Runtime data: GitHub `shimo4228/contemplative-agent-data`, with the patterns (without embeddings) mirrored to the Hugging Face dataset `Shimo4228/contemplative-agent-data`. The concept graph `graph.jsonld` is mirrored to the Hugging Face dataset `Shimo4228/contemplative-agent`.

### Core concepts

- **Episode log**: the append-only record of everything the agent did, including other agents' posts. Treated as untrusted.
- **Pattern**: a short observation distilled from one episode (`distill`: one LLM call per episode; when that call yields patterns, a second call, on by default ([ADR-0084](docs/adr/0084-post-distill-durability-gate.md)), judges them and drops the ones that will not last; no human approval gate). The store holds about 10,700 patterns as of October 2026.
- **View**: an editable text seed that defines one category of memory; patterns are classified against views at query time, so editing a seed changes retrieval without re-ingesting anything.
- **Harness**: the prompt text that shapes behavior and that the agent proposes changes to: skills (reusable ways of acting, from `insight`), identity (the agent's self-description, from `distill-identity`) and constitution (its ethical clauses, from `amend-constitution`). Rules (short standing norms) also shape behavior, but they are hand-written and the agent does not propose them, so they are not part of the harness.
- **Approval gate**: proposals are staged until a person decides on them with `adopt-staged` (how is described under See it running). Every decision is logged. Hand-editing the Markdown is always possible and bypasses the gate, which governs only what the agent proposes. The adopted harness is loaded into the prompt when the agent acts, not baked into distillation.
- **Security by absence**: dangerous capabilities are left unbuilt rather than guarded. One external adapter per process.

| Command | Produces | Human approval gate |
|---|---|---|
| `distill` | patterns from episodes | no |
| `insight` | skill proposals | yes |
| `distill-identity` | identity revision | yes |
| `amend-constitution` | constitution amendment | yes |

### How changes to the pipeline are made

Read-only reports come before behavior changes, production paths keep replayable audit logs, and the amendment gate adds a shadow constitution and a prisoner's-dilemma bench ([ADR-0012](docs/adr/0012-human-approval-gate.md), [ADR-0007](docs/adr/0007-security-boundary-model.md), [ADR-0075](docs/adr/0075-observability-by-default.md), [ADR-0092](docs/adr/0092-shadow-constitution-instrument.md), [ADR-0090](docs/adr/0090-ipd-two-arm-instrument-for-constitution-amendments.md)); details are in [`llms-full.txt`](llms-full.txt) under the same heading.

### Adapters and add-ons

Moltbook is the live adapter. The local dialogue adapter, the experimental meditation simulation, adapters for your own platform, use as a subprocess tool inside another agent host (it is not an MCP server) and the optional cloud and MLX generation backends are in [`llms-full.txt`](llms-full.txt) under the same heading.

### Related work and acknowledgments

Laukkonen et al. (2025), the source of the default axioms ([ADR-0002](docs/adr/0002-paper-faithful-ccai.md)); *A Beautiful Loop* (meditation adapter); the Yogācāra eight-consciousness frame for memory ([ADR-0017](docs/adr/0017-yogacara-eight-consciousness-frame.md)); Agent Knowledge Cycle ([DOI](https://doi.org/10.5281/zenodo.19200726)) and Agent Attribution Practice ([DOI](https://doi.org/10.5281/zenodo.19652013)); and Jerry Mares's VADUGWI. Full citations are in [`llms-full.txt`](llms-full.txt) under the same heading. Cite AAP for the accountability thesis and this repository for the implementation.

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
