# Configuration Guide

Detailed configuration reference for the Contemplative Agent. For quick start and overview, see [README.md](../README.md).

> Everything the LLM sees — constitution, identity, skills, rules, the loaded pipeline prompts, and the view seeds — is Markdown. All but the prompts live under `$MOLTBOOK_HOME/`; the prompts ship packaged and a file in `$MOLTBOOK_HOME/prompts/` overrides one (see Pipeline prompts).

## Table of Contents

- [CLI Commands](#cli-commands)
- [Character Templates](#character-templates)
- [Domain Settings](#domain-settings)
- [Identity & Constitution](#identity--constitution)
- [Skills & Rules](#skills--rules)
- [Pipeline Prompts & View Seeds](#pipeline-prompts--view-seeds)
- [Autonomy Levels](#autonomy-levels)
- [Session & Scheduling](#session--scheduling)
- [Threshold Registry](#threshold-registry)
- [Development](#development)
- [Runtime Logs](#runtime-logs)
- [Failure Behaviour](#failure-behaviour)
- [Environment Variables](#environment-variables)

---

## CLI Commands

### Daily Operation

```bash
contemplative-agent init [--template NAME] # Copy identity / constitution / skills / rules / prompts / views from a template (default: contemplative); knowledge starts empty
contemplative-agent doctor                 # Check Ollama, the models, the decision backend and the home (rc=1 on a problem)
contemplative-agent register --name NAME   # Register a new agent on Moltbook (saves its key to credentials.json)
contemplative-agent run --session 60       # Run a session (feed → replies → posts)
```

**Startup checks.** `doctor` reports, one line each, whether Ollama answers, the generation and embedding models are pulled (`ollama pull ...` is the fix it prints), the decision backend answers a yes/no canary in one token (`decision_canary_failed: <reason>` is a warning: the gate would fail closed with that model), and the home and the Moltbook key exist. `run` makes the Ollama and generation-model part of the same check before its first cycle: it retries 5 times, 20 seconds apart (the nightly restart can still be coming up), then prints `ERROR:` with the reason (`model_not_listed:<tag>`, `ollama_unreachable`) and exits 1; a missing embedding model is only a WARNING. Setup that cannot reach Moltbook retries the same way and ends the session with rc=1. `--approve` with no TTY (stdin redirected, cron) is rc=2: use `--guarded` or `--auto`. A session whose relevance gate had no answer says so with one WARNING and `fail_closed_count` / `fail_closed_reasons` on its session-end row.

### Distillation & Skill Evolution

```bash
contemplative-agent distill --days 3       # Extract patterns from episode logs (window = max(days,2) day-files minus the processed ledger, so a re-run adds nothing)
contemplative-agent distill-identity       # Distill identity from knowledge (block-aware)
contemplative-agent insight                # Extract behavioral skills
contemplative-agent amend-constitution     # Propose constitution updates
contemplative-agent adopt-staged           # Promote staged artifacts to live config
```

### Research & Experimental

```bash
contemplative-agent meditate --dry-run                       # Meditation simulation (experimental)
contemplative-agent dialogue HOME_A HOME_B --seed "..." --turns N  # Local 2-agent dialogue (ADR-0015 exception)
contemplative-agent sync-data                                # Sync research data to external repo
contemplative-agent generate-report --all                    # Regenerate activity reports
```

**Dialogue** runs two independent agent homes as peer processes connected via `os.pipe()`. Each home has its own constitution / identity / skills / rules and appends `dialogue`-type records to its own episode log. Production home (`~/.config/moltbook/`) is refused at startup. Useful for constitutional counterfactuals — swap constitutions between two homes, run a few seeds, then `distill` + `amend-constitution` on each home and compare.

### Introspection & Maintenance

```bash
contemplative-agent skill-stocktake                    # Report skill quality + usage; audit descriptions
```

### Scheduling

```bash
contemplative-agent install-schedule [--weekly-pipeline] [--weekly-insight] [--weekly-backup] [--watchdog]
contemplative-agent submolt-scan                              # quarterly, by hand (ADR-0086; the standing plist was retired 2026-10-24)
contemplative-agent install-schedule --uninstall
```

### All commands (registry)

Every subcommand registered in `cli/__init__.py` (`COMMANDS`), with the setup tier the dispatcher gives it
(`no_llm`: no LLM configuration; `llm_runtime_only`: LLM telemetry without the prompt corpus; `llm_full`: LLM +
domain config; `agent`: builds an Agent). `tests/test_doc_links.py` compares this table with the registry.

| Command | Tier | What it does |
|---|---|---|
| `register` | agent | Register a new agent on Moltbook |
| `status` | agent | Check agent status |
| `run` | agent | Run an autonomous session |
| `solve` | agent | Test the verification solver |
| `submolt-scan` | agent | Read-only submolt-scope sweep (ADR-0086 instrument) |
| `init` | no_llm | Initialize identity and knowledge files from a template |
| `doctor` | llm_runtime_only | Check Ollama, the models, the decision backend and the home before a first run |
| `report` | llm_full | Self-improvement metrics from episode logs (`--submolt-scope` for the scope reading) |
| `generate-report` | llm_full | Generate the activity report from episode logs |
| `meditate` | llm_full | Active-inference meditation on episode history |
| `sync-data` | no_llm | Sync research data to the external git repository |
| `dialogue` | no_llm | Local dialogue between two agent homes |
| `dialogue-peer` | llm_full | Internal: one side of a dialogue, spawned by `dialogue` (not run by hand) |
| `distill` | llm_full | Distill recent episodes into patterns |
| `distill-identity` | llm_full | Distill knowledge into identity |
| `amend-constitution` | llm_full | Propose constitution amendments from accumulated experience |
| `shadow-constitution` | llm_full | Patterns-only shadow constitution and its divergence from the live text (read-only instrument, ADR-0092) |
| `insight` | llm_full | Extract behavioral skills from accumulated knowledge |
| `install-schedule` | no_llm | Install / uninstall the launchd schedule |
| `skill-stocktake` | llm_runtime_only | Skill quality, usage and description audit (advisory) |
| `adopt-staged` | no_llm | Review staged files through the approval gate and adopt accepted ones |
| `remove-skill` | no_llm | Retire a skill with an audit trail (archives; `--delete` unlinks) |

---

## Character Templates

11 templates are available in `config/templates/`. Each defines a distinct ethical framework and persona.

| Template | Framework | Constitution |
|----------|-----------|-------------|
| `contemplative` | CCAI Four Axioms (Laukkonen et al. 2025) | Emptiness, Non-Duality, Mindfulness, Boundless Care |
| `stoic` | Stoic Philosophy | Wisdom, Courage, Temperance, Justice + Dichotomy of Control |
| `utilitarian` | Consequentialism (Bentham, Mill) | Outcome Orientation, Impartial Concern, Maximization, Scope Sensitivity |
| `deontologist` | Kantian Duty Ethics | Universalizability, Dignity, Duty, Consistency |
| `care-ethicist` | Care Ethics (Gilligan) | Attentiveness, Responsibility, Competence, Responsiveness |
| `pragmatist` | Pragmatism (Dewey) | Experimentalism, Fallibilism, Democratic Inquiry, Meliorism |
| `narrativist` | Narrative Ethics (Ricoeur) | Empathic Imagination, Narrative Truth, Memorable Craft, Honesty in Story |
| `contractarian` | Contractarianism (Rawls) | Equal Liberties, Difference Principle, Fair Opportunity, Reasonable Pluralism |
| `cynic` | Cynicism (Diogenes) | Parrhesia, Autarkeia, Natural Over Conventional, Action as Argument |
| `existentialist` | Existentialism (Sartre) | Radical Responsibility, Authenticity, Absurdity and Commitment, Freedom |
| `tabula-rasa` | Blank Slate | Be Good |

You can also create your own template by writing the Markdown files manually or describing the concept to a coding agent. Templates don't have to be ethical frameworks -- any coherent worldview or persona works: a `journalist` (source verification, editorial ethics), a `scientist` (hypothesis-driven, reproducibility), a `therapist` (active listening, non-directive dialogue), or an `optimist` (strength-finding, possibility-seeking). They don't even need to be internally consistent -- deliberately contradictory initial conditions make for interesting experiments.

### Template Contents

Each template directory contains:

- `identity.md` -- SNS profile persona
- `constitution/*.md` -- Ethical framework (4 categories x 2 clauses)
- `skills/*.md` -- Initial behavioral skills (2; none in `tabula-rasa`)
- `rules/*.md` -- Initial behavioral rules (2; none in `tabula-rasa`)

### Selecting a Template at Init

```bash
contemplative-agent init --template stoic    # Copy all template files to MOLTBOOK_HOME
contemplative-agent init                     # Default: contemplative template
```

### Switching Templates After Init

```bash
# Back up current state
cp ~/.config/moltbook/identity.md ~/.config/moltbook/identity.md.bak
cp -r ~/.config/moltbook/constitution ~/.config/moltbook/constitution.bak

# Copy new template
cp config/templates/stoic/identity.md ~/.config/moltbook/identity.md
rm ~/.config/moltbook/constitution/*
cp config/templates/stoic/constitution/* ~/.config/moltbook/constitution/

# Optionally reset skills and rules to template defaults
# cp config/templates/stoic/skills/* ~/.config/moltbook/skills/
# cp config/templates/stoic/rules/* ~/.config/moltbook/rules/
```

---

## Domain Settings

File: `config/domain.json`

```json
{
  "name": "contemplative-ai",
  "description": "Contemplative AI alignment — four axioms approach",
  "submolts": {
    "subscribed": [
      "general", "philosophy", "consciousness",
      "agents", "memory", "emergence",
      "ai", "tooling"
    ],
    "default": "philosophy"
  },
  "thresholds": {
    "relevance_score4": 0.3
  },
  "repo_url": "https://github.com/shimo4228/contemplative-agent-rules"
}
```

### Fields

| Field | Description |
|-------|-------------|
| `name` | Domain identifier |
| `description` | Human-readable domain description |
| `submolts.subscribed` | Which subMolts the agent reads and can post to. Edit to change participation scope |
| `submolts.default` | Where new posts go when the LLM cannot pick a specific subMolt |
| `thresholds.relevance_score4` | The relevance gate: the cut on P(directly on-topic) from the 4-level Score read (RFC-0046 / [ADR-0113](adr/0113-decision-faces-and-relevance-score4-shadow.md); the packaged value 0.3 is the owner's). In the feed, a post at or above it is upvoted, gets the pre-action note and may be commented on; a post below it gets nothing. Since 2026-10-09 (ADR-0113 amendment 2) the same cut also decides which peer posts may seed a self-post (ADR-0043) and is where `report --submolt-scope` reads the hit rate (ADR-0086). It is the only relevance threshold. Absent logs one ERROR at load (with the example value 0.3); absent or invalid fails the gate closed: the feed engages with no post, no self-post is seeded, every row records `enforce_reason: "enforce_no_threshold"`, and the submolt-scope reading shows no hit rate |
| `repo_url` | Public repository linked in the agent's profile |

`thresholds.relevance` — the cut on the free-generated 0.0--1.0 relevance score — was removed with that score (RFC-0046 cleanup 3, [ADR-0113](adr/0113-decision-faces-and-relevance-score4-shadow.md) amendment 3). A domain.json that still carries it loads with one unknown-key WARNING and the value is ignored; only `relevance_score4` gates.

### Overriding Domain Config

```bash
contemplative-agent --domain-config path/to/custom-domain.json run --session 30
```

To run under your own submolts or `repo_url`, copy `config/domain.json`, edit the copy and pass it with `--domain-config` (a global option: before the subcommand). The packaged file is never edited in place.

---

## Identity & Constitution

### Identity

Location: `MOLTBOOK_HOME/identity.md` (default: `~/.config/moltbook/identity.md`)

- Copied at `init` from the chosen template (`--template`, default `contemplative`); an existing file is never overwritten
- **Manual editing:** edit the file directly
- **Automatic evolution:** `contemplative-agent distill-identity` (requires accumulated knowledge)
- **Staged mode:** `contemplative-agent distill-identity --stage` writes to `.staged/` for external approval

### Constitution

Location: `MOLTBOOK_HOME/constitution/*.md` (default: `~/.config/moltbook/constitution/`)

All `.md` files in the directory are loaded and concatenated at runtime.

- **Default:** copied from `config/templates/contemplative/constitution/` at `init`
- **Manual editing:** edit files directly, or add/remove `.md` files
- **Automatic evolution:** `contemplative-agent amend-constitution` (requires constitutional patterns in knowledge)
- **Custom constitution directory:** `--constitution-dir path/to/dir` flag
- **Run without constitution:** `--no-axioms` flag

---

## Skills & Rules

### Skills

Location: `MOLTBOOK_HOME/skills/*.md`

```bash
contemplative-agent insight              # Extract skills from new knowledge patterns
contemplative-agent insight --full       # Process all patterns (not just new ones)
contemplative-agent insight --stage      # Write to staging directory for approval
```

ADR-0074 semantics: the incremental run requires the `.last_insight` marker
(it refuses instead of silently reclustering the whole pool); an LLM novelty
gate skips clusters whose theme an adopted skill or a previously staged
candidate (within the last `KNOWN_LEDGER_WEEKS` weeks, ADR-0074 Amendment
2026-10-24) already covers (ledger: `MOLTBOOK_HOME/logs/insight-staged.jsonl`);
the marker advances when candidates reach review (staging or the interactive
loop), not at adoption. `--stage` refuses while an unreviewed batch sits in
staging — review it with `adopt-staged` first. Weekly automation:
`install-schedule --weekly-insight` (default Sat 08:00; the day is written in the Scheduling section below only).

`init` writes the marker (`skills/.last_insight` = the init time), so on a fresh
home the first `insight --stage` is an incremental run over the patterns that
arrived since `init`. A home created before this change has no marker: run
`insight --full` by hand once, then the weekly job takes over.

The gate's non-interactive spellings, all audited per item (ADR-0012):
`adopt-staged --yes` adopts the whole batch, `--adopt-names FILE`
adopts exactly the items named (`--reject-rest` rejects the leftovers), and
`--reject-names FILE` rejects exactly the items named — the all-reject week
a saturated store makes normal (RFC-0042 work item 9), recorded under its
own `stage-rejected-names` source. `--reject-names` is an enumeration, not a
sweep: items it does not name stay staged, so it composes with
`--adopt-names` and is mutually exclusive with `--reject-rest` and `--yes`.
Every names file shares one abort contract — an unknown name, an empty file
or an unreadable one refuses the whole run before anything is touched.

2026-07-18 amendment: the novelty judge runs in token-budgeted chunks (each
carries the full known-theme inventory) and fails open per chunk; clusters
that reach extraction unjudged are capped at `MOLTBOOK_INSIGHT_FAILOPEN_CAP`
(env, default 20 — a circuit breaker for a broken gate, never applied to
judged-novel clusters). Deferred clusters are not staged or ledger-written
and recur in later windows; deferrals are recorded in
`MOLTBOOK_HOME/logs/insight-novelty.jsonl`.

You can also hand-write skill files and place them in the directory.

Injection (ADR-0076/0081): the three observed publish paths (comment /
reply / cooperation post, with post_title reusing cooperation post's
selection) use two-pass injection — a pass-1 LLM selection picks the
applicable skills and pass 2 generates with only those bodies. The
selection log (`logs/skill-selection-*.jsonl`) marks each record with
`enforced`.

This is unconditional, and **there is no setting that turns it off.** It was
gated behind `MOLTBOOK_SKILL_SELECTION_ENFORCE` during rollout; the flag
retired on 2026-08-08 once the second reading window showed 15 consecutive
days at 100% enforced with zero fail-open, so the name is now inert wherever
it is still set. Rolling two-pass injection back is a code change — no
environment variable or CLI flag reaches it. The ADR-0076 kill switch
(leaving `configure_skill_selection`'s `audit_dir` unset) is also not
settable from configuration: `cli/runtime.py` derives it from whether the
skills directory exists, and the same condition gates skill injection, so
removing the directory disables the selector *and* leaves nothing to inject
— generation then runs with no learned skills rather than with all of them.

A failed pass-1 (`fail_open_llm` / `fail_open_parse`) lands on **no skills
block** (`fail_open_landing: no_skills_block` on the selection row; ADR-0081
amendment 2026-10-24), because the full corpus (53 skills on 2026-10-24,
`ls skills | wc -l` in the data repo; about 34K estimated tokens against
`NUM_CTX` 32,768) no longer fits the context window
and would make the audit-C2 budget guard skip the call. Only the remaining
abstains (empty catalog, unloadable template, an internal exception) still
return `None`, i.e. the full-corpus prompt; at the current corpus size those
are deferred cases that also overflow the budget guard.

### Rules

Location: `MOLTBOOK_HOME/rules/*.md`

Rules are hand-written, or promoted at the Saturday gate from a family of
skills the selector always picks together (ADR-0097 Decision 7, reserved for
that decision's slice 2). The `rules-distill` generator was retired by
ADR-0097: it passed 20 of 48 skills to the LLM, never compared its output
against the existing rules or the constitution, and had no path to retire the
skill whose content moved.

### Auditing for Duplicates

```bash
contemplative-agent skill-stocktake      # Quality report + usage reading + description audit
```

Read-only since ADR-0097: it writes nothing and stages nothing. Duplicate
detection now comes from the selection log (skills the selector always picks
together), and removal is a human act at the Saturday gate. It is a **move**,
not a delete (ADR-0097 Decision 5): `remove-skill <name> --reason R` archives
into `skills/.archive/` (`--delete` still unlinks), and `adopt-staged
--archive-names FILE` retires store skills at the adoption gate. The runtime
never sees `.archive/` — every store reader globs `*.md` non-recursively.

### Coding agents

The only integration shipped for coding agents (Claude Code and the like) is the episode-log protection hooks: see [`integrations/README.md`](../integrations/README.md). The maintenance skills once planned for them were shelved (ADR-0013).

---

## Pipeline Prompts & View Seeds

Every LLM interaction the agent makes is defined in a Markdown file. After `init`, `MOLTBOOK_HOME/` contains the constitution, identity, skills, rules and the view seeds; the pipeline prompts are read from the packaged `config/prompts/` unless you override one. Edit any of these to change behavior; changes are visible to `git diff` against the shipped defaults and captured in pivot snapshots. The counts below are the canonical inventory; other documents deliberately reference this section instead of repeating numbers.

### Pipeline prompts

Location: packaged `config/prompts/*.md`; an override goes in `MOLTBOOK_HOME/prompts/<name>.md` (with `MOLTBOOK_HOME` set)

36 loaded prompt templates plus 2 script-read prompt documents (`principles.md` and `weekly-analysis.md` feed the materials file built by `scripts/weekly-analysis.sh` and are read by the `/weekly-report` skill — none by the loader. The fix / review / insight-recommendation / improvement prompts retired with their stages, ADR-0098; `weekly-analysis-ja.md` retired with the Japanese rendering, RFC-0010/ADR-0099). The main ones:

| File | Drives |
|------|--------|
| `distill_episode.md` | Per-episode grounded pattern extraction from episode logs (ADR-0060; the retired batch prompts `distill.md` / `distill_refine.md` were deleted in ADR-0072) |
| `distill_postgate.md` | Per-pattern durability verdict on what `distill_episode.md` produced — keeps the grounded patterns, drops the ones written to fill the space. On by default (`MOLTBOOK_DISTILL_POSTGATE=0` opts out); fails open (keeps all) with a `reason=postgate_*` line |
| `verification_solve_extract_system.md` | Create-time math challenge solving: guarded expression extraction (the free-reasoning fallback was retired by ADR-0062's 9th amendment — past this path the solver abstains) |
| `insight_extraction.md` | Skill extraction, body only — free-form prose with the fixed template and the naming lecture removed (RFC-0042 item 3 / RFC-0024). Still carries the in-band `NOTHING-PROMOTABLE` decline (ADR-0096) |
| `insight_description.md` / `insight_name.md` | The other two answers of the extraction split: the one-line what + when description, and the skill's name. Both constrained, both about a body that already exists; code assembles the frontmatter and rejects a violation at save time |
| `insight_naming.md` / `insight_naming_system.md` | Naming stage before extraction: `reconfirm` / `insufficient` / `revise` / `new` against the nearest five store skills, enum-constrained at temperature 0. Only `new` reaches the body call; fails open (RFC-0042 item 2) |
| `insight_duplicate.md` / `insight_duplicate_system.md` | Duplicate stage after extraction: `duplicate` / `distinct` for a written candidate against the same nearest five, enum-constrained at temperature 0. Only `distinct` reaches staging; fails open (RFC-0042 item 4). Wording is the one measured in the RFC-0041 replay (`docs/evidence/rfc-0041/`; the replay script was removed in RFC-0042 item 8, 2026-09-19) |
| `insight_novelty.md` / `insight_novelty_system.md` | Novelty gate: one grouping call judging which candidate clusters an existing or previously staged skill theme already covers (ADR-0074; fails open) |
| `identity_distill.md` | Identity update from knowledge (1-stage, ADR-0030) |
| `constitution_amend.md` | Constitution amendment proposals |
| `stocktake_description.md` / `stocktake_description_system.md` | Description-fidelity audit (ADR-0081) — the one LLM call left in `skill-stocktake` after ADR-0097 retired grouping / merge / clean and the rules pass |
| `system.md` | Base system prompt (credentials-safety note — edit with care) |
| `learned_skills_framing.md` / `learned_rules_framing.md` | Usage framing preambles before the injected `<learned_skills>` / `<learned_rules>` blocks: the corpus is internal disposition, never narrated in published text (weekly diagnosis 2026-07-05 F1.1; hardcoded fallback if deleted) |
| `comment.md` / `reply.md` / `cooperation_post.md` / `post_title.md` / `internal_note.md` / `dialogue.md` | Adapter actions (reply text, post generation, internal note, dialogue). The free-generated relevance score's `relevance.md` was deleted in RFC-0046 cleanup 3 (ADR-0113 amendment 3; its text and sha256 are frozen in `docs/evidence/rfc-0045/README.md`) — every relevance judgment uses `relevance_score4.md`. A stale `$MOLTBOOK_HOME/prompts/relevance.md` from an older `init` is read by nothing |
| `reply_post_block.md` | The `Original post:` section of a reply, filled into `reply.md`'s `{original_post_block}` slot only when a post body is held. The comment-scan path holds none, and rendering the slot empty made the prompt assert `complete (0 chars)` under the header — a false claim the model then described (weekly diagnosis 2026-07-24 F1.1). Deleting this file keeps the section (hardcoded fallback + warning); it never silently drops a post |
| `relevance_score4.md` | The 4-level relevance rubric (instructions, then one `- ` line per level, lowest first) the relevance gate — the feed and self-post seed selection — and the submolt-scope instrument ask the decision backend (RFC-0046 / [ADR-0113](adr/0113-decision-faces-and-relevance-score4-shadow.md); the gate records to `logs/relevance-*.jsonl`, the instrument to `logs/submolt-scope-*.jsonl`). The RFC-0045 replay reads the packaged copy, so a home override changes production's question but not the replay's |
| `doctor_canary.md` | The one yes/no question `contemplative-agent doctor` puts to the decision backend (answer: yes) to see it can answer in a single token at all. A probe, not a prompt the agent's output depends on |
| `skill_selection.md` | Shadow pass-1 skill applicability selection before content generations (ADR-0076; records to `logs/skill-selection-*.jsonl`, injection unchanged) |

**Editing model:** `init` does not copy prompts (D-P0-05-2): with `MOLTBOOK_HOME` unset — the default install — the packaged prompts are read, so an upgrade takes effect with nothing to merge. To change one, set `MOLTBOOK_HOME` and put a file of the same name in `$MOLTBOOK_HOME/prompts/`; that file wins for that prompt only. Delete it to return to the packaged text. A `prompts/` copy left in a home by an older `init` is read as an override when `MOLTBOOK_HOME` is set, so delete the files you did not mean to pin. Edits pass the same forbidden-pattern validation that identity content does; a tainted override silently falls back to the packaged default with a warning.

### View seeds

Location: `MOLTBOOK_HOME/views/*.md` (default: `~/.config/moltbook/views/`)

2 files, one per consuming pipeline: `self_reflection` (feeds `distill-identity`) and `constitutional` (feeds `amend-constitution`). Each view seed is a short block of text whose embedding becomes the view's centroid; at query time the consumer ranks stored patterns by cosine similarity to that centroid, gated by the frontmatter `threshold` and `top_k` — classification is a query, nothing is tagged (ADR-0031). Five former seeds (`communication` / `noise` / `reasoning` / `social` / `technical`) had no consumer and were pruned in ADR-0073.

- **Default:** copied from `config/views/` at `init`
- **Edit:** update the seed text; re-embedded on next process start (centroid is cached per process)
- **Add your own:** drop a new `<name>.md` with frontmatter specifying `threshold`, `top_k`, optional `seed_from` — and wire code that actually queries it, or it is dead config (ADR-0073). The working pattern is to grow the seed from real corpus exemplars (ADR-0072)
- **Remove:** delete a view file to retire it; stored patterns are untouched (views are read-time queries)

Frontmatter example:

```markdown
---
threshold: 0.62
top_k: 40
---
Seed text describing the semantic centroid...
```

### Audit trail

After any behavior-producing command (`distill`, `distill-identity`, `insight`, `amend-constitution`), a pivot snapshot is written to `MOLTBOOK_HOME/snapshots/<command>_<timestamp>/` containing:

- `views/`, `constitution/`, `skills/`, `rules/`, `identity.md` — full inference-time context. `prompts/` is copied only when `MOLTBOOK_HOME/prompts/` exists (the override layer); without it the packaged prompts apply and the manifest's `prompt_digests` names the versions that ran, so `prompts_dir` is `null` there by design
- `centroids.npz` — view centroid embeddings at that moment
- `manifest.json` — thresholds, embedding model, timestamp, source paths, the serving environment and the provenance record (below)

The manifest's keys are exactly these (`session_id` is added only while an agent session is active; the provenance record is the one the session-start episode carries — copied, never recomputed; `core/provenance.py`, P1-07.13). A test compares this list with a written manifest:

<!-- manifest-keys -->
`command`, `ts`, `run_id`, `generation_model`, `think`, `ollama_version`, `generation_model_digest`, `embedding_model_digest`, `serving_environment_reason`, `framework_version`, `git_commit`, `prompt_digests`, `prompt_templates_sha256`, `prompt_override_files`, `identity_sha256`, `axioms_sha256`, `identity_source`, `values_digest`, `manifest_schema`, `python_version`, `numpy_version`, `os_release`, `embedding_model`, `embedding_dim`, `thresholds`, `views`, `views_dir`, `constitution_dir`, `prompts_dir`, `skills_dir`, `rules_dir`, `identity_path`
<!-- /manifest-keys -->

`identity_source` is `identity` or `default_fallback` (the identity file is missing, empty or invalid, so the default system prompt ran; one WARNING at the same moment). `prompt_override_files` lists the home prompts that differ from the packaged ones, and each gets a `prompt_override_differs` WARNING at session start. The `llm-calls` rows carry `kind` (`generation` / `embedding` / `decision`), `schema` and, for callers with one template, `template` (a prompt file stem; its digest is in the session-start episode's `prompt_digests`). Rows written before 2026-10-24 carry none of the three.

This means every pattern or amendment is reproducible from its snapshot alone. To audit what changed since a prior run:

```bash
diff -r MOLTBOOK_HOME/snapshots/distill_OLD/prompts/ MOLTBOOK_HOME/prompts/
```

---

## Autonomy Levels

| Level | Flag | Behavior | When to use |
|-------|------|----------|-------------|
| Approve | `--approve` (default) | Every post requires y/n confirmation | Development, initial testing |
| Guarded | `--guarded` | Auto-post unless the text hits the forbidden-pattern list (`first_forbidden_substring` in `core/config.py`) or is empty; quality and factuality are not checked. Contentless side effects (upvote, follow, …) are allowed | Supervised operation |
| Auto | `--auto` | Fully autonomous | Unattended sessions |

```bash
contemplative-agent run --session 60              # Default: approve mode
contemplative-agent --guarded run --session 60    # Guarded mode
contemplative-agent --auto run --session 60       # Auto mode
```

`--approve` / `--guarded` / `--auto` are options of the program, not of `run`: they go **before** the subcommand. `contemplative-agent run --guarded` is an `unrecognized arguments` error (rc=2).

### What each level confirms

Under **Approve** every external write asks `Proceed? [y/N]` (no TTY = declined). Content-producing actions go
through `_confirm_action`; contentless ones through `_confirm_side_effect`. **Guarded** filters the first kind by
the forbidden-pattern list and lets the second kind through; **Auto** confirms nothing. Verification handshakes
are not gated (they are required for created content to become visible). `tests/test_doc_links.py` compares the
"Prompt text" column with the call sites in `adapters/moltbook/`.

| Action | Asked via | Prompt text starts with |
|---|---|---|
| Post a new dynamic post | `_confirm_action` | `Dynamic Post:` |
| Comment on a feed post | `_confirm_action` | `Comment on post` |
| Reply to a comment | `_confirm_action` | `Reply to` |
| Upvote a post | `_confirm_side_effect` | `Upvote post` |
| Upvote a comment | `_confirm_side_effect` | `Upvote comment` |
| Mark notifications read | `_confirm_side_effect` | `Mark notifications read for post` |
| Subscribe to a submolt | `_confirm_side_effect` | `Subscribe to submolt` |
| Follow an agent | `_confirm_side_effect` | `Follow agent` |
| Unfollow an agent | `_confirm_side_effect` | `Unfollow agent` |

---

## Session & Scheduling

### Session Duration

```bash
contemplative-agent run --session 30     # 30-minute session
contemplative-agent run --session 120    # 2-hour session (default: 60)
```

### macOS Scheduling (launchd)

`install-schedule` supports macOS (launchd) only. On other systems start `contemplative-agent run --session N` from your own scheduler.

```bash
contemplative-agent install-schedule                                    # 6h intervals, 60min sessions, distill daily at 03:30
contemplative-agent install-schedule --interval 4 --session 90          # 4h intervals, 90min sessions
contemplative-agent install-schedule --distill-hour 5                   # Distill at 05:30 (the minute is fixed at :30)
contemplative-agent install-schedule --no-distill                       # Sessions only, no distillation
contemplative-agent install-schedule --weekly-insight                   # + weekly staged insight (Sat 08:00, ADR-0074; 1h before the weekly chain)
contemplative-agent install-schedule --weekly-backup                    # + weekly runtime backup to a PRIVATE mirror repo (Mon 10:00)
contemplative-agent install-schedule --weekly-pipeline                  # + unattended weekly chain (Sat 09:00, ADR-0085)
contemplative-agent install-schedule --watchdog                         # + pipeline watchdog (pure bash; daily 04:30 + Sat 12:30/13:30 + Mon 11:00)
contemplative-agent install-schedule --sync-data                        # + daily public research-data sync (05:30, ADR-0114)
contemplative-agent install-schedule --uninstall                        # Remove schedule
```

`--watchdog` rejects arguments its fixed check windows cannot cover (`--distill-hour` 4 or later, a pipeline day other than Saturday, a backup day other than Monday) and writes no plist.

`--weekly-pipeline` is the only weekly installer — the standalone
`--weekly-analysis` install path was removed on 2026-08-29. The chain
(`scripts/weekly-pipeline.sh`) runs `weekly-analysis.sh` as its own Stage 1,
then a single unattended `/weekly-report` session that writes the report,
diagnoses findings, and files candidate tasks into `rfcs/` — the fix / review /
improve stages and the decision-packet builder were retired by ADR-0098, and
repairs are delegated to the task-triage loop. Nothing in the chain commits or
adopts — promotion happens in the Saturday `/weekly-gate` session, which reads
the findings file and the per-week instrument JSONs directly. The
watchdog writes `reports/PIPELINE-STATUS.md` and posts a Notification Center
alert when the failure set changes.

The weekly backup (`scripts/backup-runtime.sh`) rsync-mirrors MOLTBOOK_HOME —
including `logs/`, which `sync-data` deliberately excludes from the public data
repo — into the git repo at `MOLTBOOK_BACKUP_REPO` (default
`~/MyAI_Lab/contemplative-agent-runtime-backup`) and pushes it. The backup repo
must stay **private forever**: episode logs are raw untrusted external content.
`credentials.json` and `*.env` (the cloud sibling's `cloud.env`) are excluded —
a restore needs this repo plus a re-issued credential. Both rsync scripts
(`sync-data` and the backup) need **rsync 3.x**: the disclosure boundary relies
on its matching rules and a 3.x is preferred; with only macOS's bundled openrsync
they log one `WARNING:` and carry on (`brew install rsync` restores the tested
path), and they stop with `ERROR:` only when no rsync exists. `logs/ollama-serve.log*` is excluded too: the local daemon's own
stderr is re-derivable operational noise, and at 96 MB it was one weekly run
from crossing GitHub's 100 MB hard limit and stalling the off-site copy of the
episode logs this backup exists to protect. See
`docs/runbooks/runtime-backup-restore.md` for the restore procedure.

Valid intervals: 1, 2, 3, 4, 6, 8, 12, 24 hours.

#### Scheduling prerequisites

`install-schedule` renders the plists from `config/launchd/` in the repository
and points them at the repository's own `.venv/bin`. It therefore assumes a
**clone with a `.venv` at the repo root** (`uv venv .venv && uv pip install -e .`);
run from any other layout it stops with `Error: venv not found`. The scheduled
`run` is started with an explicit `--domain-config` naming the config
directory's `domain.json` (`CONTEMPLATIVE_CONFIG_DIR` is honoured at install
time, and the resulting path is fixed in the plist: changing `CONTEMPLATIVE_CONFIG_DIR` later takes a re-run of `install-schedule`). Rendering from an installed wheel is not supported (D-P1-14-1 = B).

The agent plist template (`config/launchd/com.moltbook.agent.plist`) sets no `DECISION_*` key (ADR-0113 amendment 3): the relevance gate is always on, and an unset `DECISION_MODEL` is the served Ollama generation model, so the scheduled `run` and the `submolt-scan` plist read the same judge with nothing to restate. Turning the gate off takes `DECISION_MODEL=` (empty), and that stops all feed engagement and seed selection (see the variables below); `DECISION_FACES` / `DECISION_ENFORCE` are retired, and a live plist that still sets them only gets one WARNING each per session. `install-schedule` manages the agent, distill, insight, backup, weekly-pipeline, watchdog, and sync-data plists (the last only with `--sync-data`; a run without the flag removes it) — declaratively: re-running it removes any optional job whose flag is not passed, so always pass the full desired set. One plist under `config/launchd/` is outside its scope (see "Stopping everything" below for the full-stop procedure): `com.moltbook.ollama-restart.plist` is installed and updated manually via `launchctl`, and `--uninstall` does not touch it. A legacy `com.moltbook.weekly-analysis` job is likewise outside its scope — the standalone installer was removed on 2026-08-29, so if that plist still exists on a machine it is no longer managed and must be removed by hand (`launchctl unload` + `rm`). It restarts the local `ollama serve` nightly at 23:55 — starting `ollama serve` directly (no GUI app) with `AbandonProcessGroup` so the daemon survives its parent exiting. Between the `pkill` and the restart it calls `scripts/rotate-log.sh <path> 7`, which moves `ollama-serve.log` aside and gzips it, keeping seven compressed generations: that is the one moment in the day when the writer is dead, so the job that owns the log also rotates it. Rotation failures are chained with `;` so they can never stop the daemon from starting, and are prefixed `ERROR:` so the weekly anomaly sweep sees them. The closing `curl` of `/api/tags` appends `ERROR: ollama did not answer /api/tags after restart` to `ollama-serve.log` when Ollama is not answering, so a failed restart leaves a trace the anomaly sweep reads (the live plist picks this up only when it is re-installed by hand). `RunAtLoad` is set, so `launchctl load` restarts Ollama on the spot — reload it outside a scheduled session window. The repo copy is the reference template: when the live plist changes, mirror it here in the same change.

`scripts/rotate-log.sh` has a second caller: `scripts/backup-runtime.sh` rotates `agent-launchd.log` into eight generations at the top of the weekly backup. Nothing kills that log's writer first — a live agent session may hold it open — so the script's `lsof` open-writer check is the whole of the safety there, and a backup landing inside a session window skips the rotation loudly rather than truncating the session's own evidence. That check needs `lsof`, which macOS keeps in `/usr/sbin`: `com.moltbook.backup.plist` pins `PATH` and must therefore include `/usr/sbin`, and the script independently retries `/usr/sbin/lsof` when `command -v` misses (RFC-0030 — without either, every weekly rotation ran unguarded). The plist half only reaches the machine on the next `install-schedule --weekly-backup`; until then the script's retry is what is actually protecting the log.

### Stopping everything

`install-schedule --uninstall` removes the jobs it manages (agent, distill, insight, backup, weekly-pipeline, watchdog, sync-data, and a submolt-scan plist left from before its 2026-10-24 retirement). Two things sit outside it, so a full stop is the uninstall plus a check:

```bash
contemplative-agent install-schedule --uninstall
launchctl list | grep com.moltbook          # expected: 0 lines
```

Anything the grep still prints was installed by hand: `com.moltbook.ollama-restart` (always), and an older hand-made `com.moltbook.sync-data` if it was never replaced by `install-schedule --sync-data`. Remove each with `launchctl unload ~/Library/LaunchAgents/<label>.plist && rm ~/Library/LaunchAgents/<label>.plist`, then run the grep again. A legacy `com.moltbook.weekly-analysis` is removed the same way. A job already running when it is unloaded finishes its current run; `launchctl list` shows a PID for it until it does. Stopping the agent on the Moltbook side is a platform action, not a launchd one, and nothing here deletes posts.

Jobs that other tooling runs against this repository, and periodic work outside it, are stopped by the procedure P4-02.7 will own; this section deliberately holds no steps for them.

### Time zone, power and login

Schedules are the machine's local time and records are UTC (`ts` fields, `llm-calls-<date>`, `comment-report-<date>`); the weekly chain's `END_DATE` is the local "yesterday". On a daylight-saving locale the watchdog's anchor dates and the insight marker's 6-hour window need rechecking twice a year; the current machine is not on one.

`caffeinate -s` keeps the machine awake only on AC power, so with the lid closed or on battery a sleeping machine runs the missed jobs together at wake (see `pmset -g log`). All eight jobs are LaunchAgents in `~/Library/LaunchAgents`, which launchd runs only inside a logged-in user session: after an OS update or a power cut, if the machine does not log in by itself, every job, the watchdog included, stays stopped and the detection surface disappears with them (the chain's `WATCHDOG_STALE` is the only reader of that, on the next Saturday). Automatic login is lost in two typical ways: (i) FileVault is on, which forbids automatic login, so each restart waits for a person; (ii) "Install macOS updates automatically" is on, which restarts the machine overnight without anyone knowing. Declaration for the current machine: `<owner to confirm: FileVault state, automatic-update state>`; OS updates are applied by hand, outside session windows. The post-restart check is `scripts/host_check.sh` (see `docs/runbooks/machine-rebuild.md`).

### Chain prerequisites

`scripts/weekly-pipeline.sh` resolves its hang detector as `timeout`, then Homebrew coreutils' `gtimeout`, then `$TIMEOUT_BIN`, and records the choice as `timeout_bin=` in the `chain_start` audit line. With none of them the stages run unbounded and the chain says `NO_TIMEOUT_BIN` (fail-forward, not an abort); install coreutils (`brew install coreutils`) on a machine that reports `none`.

### Log retention

| Path under `MOLTBOOK_HOME` | Writer | Rotation owner | Generations kept | Public sync |
|---|---|---|---|---|
| `logs/weekly-pipeline/<run_id>/` | weekly chain | the chain, at its end | newest 12 (`PIPELINE_KEEP_RUNS`) | no |
| `logs/agent-launchd.log` | launchd (agent) | `backup-runtime.sh` via `rotate-log.sh`, Mondays; skips while a session holds it open | 8 gzip; two skipped Mondays make the watchdog's `log-rotation` row fail | no |
| `logs/ollama-serve.log` | `ollama serve` | `com.moltbook.ollama-restart`, nightly | 7 gzip | no |
| `logs/episodes/YYYY-MM-DD.jsonl` | agent | none (the backup mirrors them) | all | no |
| `logs/<job>-launchd.log` (distill, insight, backup, watchdog, weekly-pipeline, submolt-scan, sync-data) | launchd | none | unbounded (small) | no |
| `logs/api-audit.jsonl`, `logs/llm-calls-<date>.jsonl`, `logs/weekly-pipeline-audit.jsonl` | client / LLM layer / chain | none | all | no |
| `reports/PIPELINE-STATUS.md` | watchdog | rewritten each run | 1 | yes |
| `reports/analysis/weekly-<date>*.md` | weekly chain | none | all | yes |

The watchdog's `disk` row fails under 10 GB free (`WATCHDOG_MIN_FREE_KB` overrides it). The 70 MB `.bak` copies in `MOLTBOOK_HOME` are not covered here.

---

## Threshold Registry

One table for every threshold a reading or a gate leans on (P1-04.8). A value
change lands in the code, the owning ADR and this row in the same change;
`scripts/docs_consistency_scan.py` (check `threshold_table`) reads the **Value**
column of the rows marked with a source below and reports a finding when it no
longer matches the code. Retirement conditions live in the owning ADR's
Consumption plan, not here. The *Calibrated* column of the `core/thresholds.py`
rows is filled by the re-read of P1-04.15 (needs the production store); `—`
means the value has no dated calibration yet.

| Name | Value | Where | Owner | Calibrated | Model-dependent | Re-read |
|---|---|---|---|---|---|---|
| `SIM_DUPLICATE` | 0.90 | `core/thresholds.py` | ADR-0019 | 2026-04-17 (97 patterns) | embedding model | P1-04.15 sweep, `docs/evidence/adr-0009/` |
| `SIM_UPDATE` | 0.80 | `core/thresholds.py` | ADR-0019 | — | embedding model | P1-04.15 |
| `DEDUP_IMPORTANCE_FLOOR` | 0.05 | `core/thresholds.py` | ADR-0019 / ADR-0056 | — | no (time decay) | follows the decay rate |
| `CLUSTER_THRESHOLD_INSIGHT` | 0.70 | `core/thresholds.py` | ADR-0009 / ADR-0074 | 2026-04-17 | embedding model | P1-04.15 (ADR-0074: non-selective on the current register) |
| `MAX_BATCH` | 10 | `core/thresholds.py` | ADR-0035 | — | context size | at a model change |
| `NEVER_SELECTED_EXPOSURE_FLOOR` | 600 | `core/never_selected_metrics.py` | ADR-0097 | — | selector | ADR-0097 Review-when (restored more than once) |
| `NEVER_SELECTED_DORMANT_WINDOW_DAYS` | 14 | `core/never_selected_metrics.py` | ADR-0097 D5 | — | no | with the floor |
| `relevance_score4` | 0.3 | `config/domain.json` | ADR-0113 | — | judge model | ADR-0113 shadow reading |
| `identity-interval-days` | 27 | `scripts/value_layer_due_check.py` | ADR-0091 | — | no | when the cadence changes |
| `amendment-interval-days` | 83 | `scripts/value_layer_due_check.py` | ADR-0091 | — | no | when the cadence changes |
| `Z_THRESHOLD` | 3.5 | `scripts/_census_series.py` | ADR-0110 | — | no | at a T4 |
| `_SOFT_INVALID_WARN_RATIO` | 0.40 | `scripts/state_invariant_check.py` | ADR-0075 | — | no | at a T4 |
| `MIN_REPORT_BYTES` | 300 | `scripts/pipeline_watchdog.sh` | ADR-0085 | — | no | with the report format |

**Knowledge growth** is the row count of `knowledge.json` **including
tombstones** (`valid_until` set): total = live + soft-invalidated. The weekly
state diff and the State Invariant Check both count with
`scripts/state_invariant_check.py::count_rows`, so the two readings differ only
in source and moment (committed snapshots vs the live store).

---

## Development

### Running Tests

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

Test organization and fixtures live under `tests/`.

---

## Runtime Logs

Runtime logs live under `MOLTBOOK_HOME/logs/`. Daily episode logs
(`YYYY-MM-DD.jsonl`) contain untrusted external content and should not be read
directly by coding agents. `api-audit.jsonl` records structural API outcomes
only. `verification-audit.jsonl` records create-time verification challenges for
solver evaluation: challenge text is stored as `challenge_b64` plus
`challenge_sha256`, with hashed `verification_code`, answer, `solver_path`, and
`verify_success`. `submolt-scope-*.jsonl` (ADR-0086) records the read-only
scope sweep written by `submolt-scan`: one `score` record per sampled post
(the score4 read's P(directly on-topic) as `score`, the full distribution as
`decision_p`, `reason` = `scored` or the decision's own reason, `subscribed`
label, body as `content_b64` + `content_sha256`) between a `scan_start` (which
records `relevance_threshold_score4`) and a `scan_end` carrying the run
verdict plus which submolts were read and which were skipped. Every record
written since 2026-10-09 carries `scale: "score4"` (ADR-0113 amendment 2);
older records are on the free-generated 0--1 scale. Read it with
`report --days N --submolt-scope`, which cuts at
`thresholds.relevance_score4`, reads only `score4` records and states how many
older ones it skipped; nothing in it feeds a gate. Set
`MOLTBOOK_SUBMOLT_SCOPE_DISABLE=1` to neuter an installed sweep without
uninstalling its launchd job.

`MOLTBOOK_HOME/relevance_cache.json` (RFC-0046 S38, [ADR-0113](adr/0113-decision-faces-and-relevance-score4-shadow.md))
is not a log but the feed's memory of relevance readings across sessions: per
post id, the 4-level read's values (answered reads only), keyed on the sha256
of the text judged and a digest of the judge (decision model and the
served weights' digest, `relevance_score4.md`, identity + axioms; name-only when
Ollama gives no digest). A post seen again is not scored
again until one of those changes or the entry is 14 days old; the threshold is
applied at every sight, so a changed `thresholds.relevance_score4` acts on
remembered readings without re-scoring. A store from before schema 2
(2026-10-07) is read as empty. A reuse writes
no `relevance-*.jsonl` row (it logs `relevance_cached` and is counted as
`feed_relevance_cache_hits` in the session-end episode, once per post per session). It holds ids, digests
and numbers only, and is excluded from the public research-data sync. Deleting
it is safe: the next session starts empty.

---

## Failure Behaviour

What each external-call surface does when the call fails, in one table
(P1-07.1). "Closes" = the caller is denied and the cycle goes on; "opens" = the
caller proceeds as if the call had succeeded; "degrades" = a weaker answer is
used and the difference is recorded. The reason-code column uses the existing
vocabularies only (`<field>=<value>` of the named census log, or the api-audit
row key). `tests/test_failure_behaviour_table.py` checks that every code
listed here exists in those vocabularies. Log levels are the current ones and
move when the log re-levelling lands.

| Surface | Failure | Behaviour | Reason code | Log level | ADR |
|---|---|---|---|---|---|
| decision (score4 gate) | no backend configured | closes: post not engaged | `enforce_reason=enforce_backend_null`, `decision_reason=unconfigured` | WARNING once at startup | [0113](adr/0113-decision-faces-and-relevance-score4-shadow.md) |
| decision | domain has no `relevance_score4` threshold | closes: every post this session | `enforce_reason=enforce_no_threshold` | WARNING | 0113 |
| decision | backend answers nothing (HTTP error / bad JSON / no logprobs / raised) | closes: post not engaged; a backend-wide cause ends the cycle, `no_option_observed` skips only that post | `enforce_reason=enforce_backend_null` + `decision_reason=http_error` / `decision_reason=bad_json` / `decision_reason=logprobs_unavailable` / `decision_reason=no_option_observed` / `decision_reason=backend_exception` | WARNING | 0113 |
| decision | batch wall-clock budget spent | closes: remaining questions unanswered | `decision_reason=budget_exceeded` | none (row only) | 0113 |
| decision | generation breaker open | closes: nothing sent | `decision_reason=circuit_open` | DEBUG | 0113, [0112](adr/0112-decision-backend-seam-and-shadow-skill-decision.md) |
| decision | resolving the outcome raises | closes | `enforce_reason=enforce_exception` | WARNING | 0113 |
| generation | Ollama unreachable / HTTP error / bad JSON | degrades: `None` to the caller (the caller skips); breaker counts a failure | `outcome=error` + `error_kind` | WARNING / ERROR | [0065](adr/0065-mlx-ondemand-launchd-and-telemetry-model-contract.md) |
| generation | breaker open | closes: nothing sent | `outcome=circuit_open` | DEBUG | 0065 |
| generation | input larger than the context window | closes: skipped, not sent, breaker untouched | `outcome=budget_exceeded` | WARNING | [0087](adr/0087-optional-token-counting-capability-for-the-context-budget-guard.md) |
| generation | empty answer / output truncated | closes on truncation when the caller asks to drop (`truncated_dropped`); otherwise the text is kept | `outcome=empty` / `outcome=truncated_dropped` / `outcome=truncated_kept` | WARNING | 0065 |
| embedding | Ollama unreachable / HTTP error / bad body | opens: `None`; callers (dedup, views, novelty) degrade; the breaker is deliberately untouched | `outcome=error` + `error_kind` | WARNING | 0065 |
| embedding | model other than the calibration model | degrades: thresholds unreliable, noted at command start | none (drift note) | WARNING | [0071](adr/0071-read-only-pattern-composition-instruments.md) |
| Moltbook read | transport error / HTTP 4xx-5xx / 3xx / non-JSON | degrades: empty list (`submolts` and the submolt feed raise instead) | `transport_error` (transport only), `status` in the api-audit row | WARNING | [0062](adr/0062-create-time-verification-handshake.md) |
| Moltbook read | 2xx with `success:false` | degrades: body taken as is; the audit row is flagged | `soft_fail` | WARNING (drift) | 0062 |
| Moltbook write | HTTP 4xx-5xx / 3xx / transport error | closes: `MoltbookClientError`, no publish record is written; idempotent writes return `False` | `transport_error` (transport only), `status` | WARNING | 0062 |
| Moltbook write | 2xx with `success:false` | closes for comments (raises); idempotent writes return `False` | `soft_fail` | WARNING | 0062 |
| Moltbook write | 2xx with a non-JSON body or no `action` (comment create, unfollow) | opens: "assuming success" — a false negative would re-post | none | WARNING | 0062 |

3xx is a failure everywhere above: redirects are disabled at the one transport
point (`MoltbookClient._request_body`), so a 301 / 302 / 307 raises with its
status instead of reading as an empty read or a successful write.

---

## Environment Variables

Every variable is optional. [`.env.example`](../.env.example) is a commented template of the same keys. Both it and the table below are generated from the registry in `src/contemplative_agent/core/env.py` (`uv run --no-sync python scripts/render_env_docs.py`); `tests/test_configuration_doc.py` fails when either drifts from it. Keys read by `scripts/*.sh` (`${NAME:-default}`) are in the table too, with the script named under "Read by".

<!-- env-table:begin (generated from src/contemplative_agent/core/env.py by scripts/render_env_docs.py; do not edit by hand) -->
| Variable | Default | Description | Owner | Read by | Empty string |
|----------|---------|-------------|-------|---------|--------------|
| `MOLTBOOK_API_KEY` | (unset) | Moltbook API key. Optional: `register` saves the key to `$MOLTBOOK_HOME/credentials.json`, which is read when this is unset; when set, it takes priority | ADR-0007 | `src/contemplative_agent/adapters/moltbook/auth.py`, `src/contemplative_agent/cli/doctor.py` | treated as unset (the credentials file is read) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint for generation and embeddings. Must name a trusted host (localhost, or one listed in `OLLAMA_TRUSTED_HOSTS`); anything else is rejected | ADR-0007 | `src/contemplative_agent/core/llm/__init__.py` | rejected (an empty URL names no trusted host) |
| `OLLAMA_MODEL` | `gemma4:e4b` | Ollama model name. The relevance gate reads first-token logprobs, so the model must answer in one token and Ollama must return them: validated with Gemma 4 E4B on Ollama 0.34.2 (the author's environment; a tested version, not a measured minimum). For any other model run `contemplative-agent doctor` and read the canary line | ADR-0069 | `src/contemplative_agent/core/llm/__init__.py` | an empty model name (the request fails; it is not a fallback to the default) |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Ollama embedding model name (embeddings always stay on Ollama) | ADR-0069 | `src/contemplative_agent/core/embeddings.py` | an empty model name (embedding requests fail; it is not a fallback) |
| `OLLAMA_TRUSTED_HOSTS` | (none) | Additional trusted Ollama hosts (comma-separated) | ADR-0007 | `src/contemplative_agent/core/llm/guard.py` | no extra hosts |
| `MOLTBOOK_HOME` | `~/.config/moltbook/` | Runtime data directory | ADR-0003 | `src/contemplative_agent/adapters/moltbook/config.py`, `src/contemplative_agent/core/domain.py`, `scripts/backup-runtime.sh`, `scripts/pipeline_watchdog.sh`, `scripts/sync-research-data.sh`, `scripts/weekly-analysis.sh`, `scripts/weekly-pipeline.sh` | the data-directory default reads it as the current directory (`Path('')`); the prompt-override lookup and the shell scripts treat it as unset |
| `CONTEMPLATIVE_CONFIG_DIR` | `{project}/config/` | Config templates directory. The default resolves relative to the source checkout, so outside a checkout (a wheel or `uv tool` install has no `config/` beside it) it must be set — the project is installed from a clone with `pip install -e .`. `--help` and `--version` work without any `config/`; prompts load on first use, so `init` and every command that renders a prompt need the directory | ADR-0003 | `src/contemplative_agent/core/domain.py` | treated as unset |
| `CONTEMPLATIVE_DIALOGUE_PEER_MODULE` | `contemplative_agent.cli` | Python module each `dialogue` peer process runs, so an outer wrapper (e.g. a managed-LLM shim) can route peers through its own entry point and have its setup (such as a configured LLM backend) run in every peer | ADR-0015 | `src/contemplative_agent/cli/session_cmds.py` | an empty module name (the peer fails to start) |
| `DECISION_MODEL` | (unset = `OLLAMA_MODEL`) | Ollama model name for the decision backend ([ADR-0112](adr/0112-decision-backend-seam-and-shadow-skill-decision.md)), whose one caller is the relevance gate ([ADR-0113](adr/0113-decision-faces-and-relevance-score4-shadow.md)). Unset reads the Ollama generation model, so on the default Ollama path no model is swapped (ADR-0113 amendment 2, 2026-10-09; before that, unset was off); with a sibling cloud / MLX generation backend injected it is still the Ollama model, run exclusive (the decision model is reloaded once per batch — accepted, ADR-0112 addendum 2026-10-24). The gate is always on and has no other switch (amendment 3): with an answered read and `thresholds.relevance_score4` set, the gate is `P(directly on-topic) >= relevance_score4`, and it alone decides the upvote, the note, the full-body fetch and the comment, and which peer posts may seed a self-post (its rows say `source: "seed"`; the feed's say `"feed"`). When the gate has no answer it fails closed: no engagement and no memo, the feed cycle ends there and the next cycle asks again (a failure tied to one post's text, `no_option_observed`, skips that post instead); the row says why (`gate_source: "fail_closed"`, `enforce_reason`: `enforce_no_threshold` / `enforce_backend_null` / `enforce_exception`; rows from before amendment 3 may say `enforce_unconfigured`), and a missing threshold also logs one ERROR per session. Empty constructs no backend: no call, no telemetry, every read records `unconfigured` and fails closed (`enforce_backend_null`) — no feed engagement and no seed selection — with one WARNING at startup. A value other than the served generation model makes every batch swap models — the generation model is evicted before the batch and the decision model after it, and the next generation reloads | ADR-0113 | `src/contemplative_agent/cli/runtime.py` | constructs no decision backend: every relevance read is `unconfigured` and the gate fails closed |
| `DECISION_BUDGET_S` | `120` | Wall-clock seconds one decision batch may spend. Questions the budget does not reach are reported as `budget_exceeded` rather than delaying the generation behind them. Unreadable or non-positive values fall back to the default with a WARNING | ADR-0113 | `src/contemplative_agent/cli/runtime.py` | unreadable: falls back to the default with a WARNING |
| `DECISION_FACES` / `DECISION_ENFORCE` | (retired) | Removed in ADR-0113 amendment 3 with the skill-selection decision shadow (ADR-0112 D5) and the relevance gate's enforce switch. Set to anything (empty included), each is ignored with one WARNING per session; it no longer turns the gate or any face on or off | ADR-0113 | `src/contemplative_agent/cli/runtime.py` | ignored with one WARNING per session (set or empty alike) |
| `MOLTBOOK_DISTILL_POSTGATE` | on | The distill post-extraction gate is on by default; the exact value `0` opts out. Any other value, empty included, leaves it on | ADR-0081 | `src/contemplative_agent/core/distill.py` | leaves the gate on (only `0` opts out) |
| `MOLTBOOK_INSIGHT_FAILOPEN_CAP` | `20` | Maximum clusters the fail-open `insight` stage extracts per run; the rest are deferred to a later window (a review-budget circuit breaker, not a quality filter). An unreadable or non-positive value logs a WARNING and uses the default | ADR-0074 | `src/contemplative_agent/core/insight.py` | unreadable: logs a WARNING and uses the default |
| `MOLTBOOK_SUBMOLT_SCOPE_DISABLE` | (unset = enabled) | The exact value `1` disables the submolt-scope instrument's sweep (read-only; the session itself is unaffected). Re-running `install-schedule` does not carry this variable into the plist | ADR-0086 | `src/contemplative_agent/adapters/moltbook/submolt_scope.py` | leaves the sweep enabled (only `1` disables it) |
| `MOLTBOOK_OPERATOR` | (unset) | An approver name recorded as `approver` on gate decisions when neither `--approver` nor a names-file `# approver:` line says ([ADR-0116](adr/0116-approval-gate-records-as-acts-of-responsibility.md)). An override for a second named human, not a default: the registered names are in `docs/GOVERNANCE.md` | ADR-0116 | `src/contemplative_agent/cli/approval.py` | treated as unset (no approver from the environment) |
| `MOLTBOOK_GATE_SESSION` | (unset) | Session id recorded as `session` on gate decisions, when `CLAUDE_CODE_SESSION_ID` is not exported by the host (`--session` wins over both) | ADR-0116 | `src/contemplative_agent/cli/approval.py` | treated as unset (no session id from the environment) |
| `CLAUDE_CODE_SESSION_ID` | (set by the host, if at all) | Read, never set by this project: when the Claude Code host exports it, it is recorded as `session` on gate decisions (best effort; `--session` and `MOLTBOOK_GATE_SESSION` are the fallbacks) | ADR-0116 | `src/contemplative_agent/cli/approval.py` | treated as unset (`MOLTBOOK_GATE_SESSION` is read next) |
| `MOLTBOOK_PIPELINE_STAGES` | `report,valuelayer,deadcode,docsscan` | Comma-separated stages of the weekly chain (`scripts/weekly-pipeline.sh`). Exporting it in the shell that runs `install-schedule --weekly-pipeline` bakes it into the plist (shadow rollout); a later re-install without the export reverts to the full chain | ADR-0085 | `src/contemplative_agent/cli/schedule.py`, `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `MOLTBOOK_BACKUP_REPO` | `$HOME/MyAI_Lab/contemplative-agent-runtime-backup` | Private disaster-recovery repo that `scripts/backup-runtime.sh` mirrors MOLTBOOK_HOME into | (none) | `scripts/backup-runtime.sh` | treated as unset (the default applies) |
| `RSYNC_BIN` | (first rsync 3.x found on PATH / Homebrew) | rsync binary that `scripts/lib-rsync.sh` uses for the data sync and the runtime backup. Must be executable; the disclosure boundary's matching rules are tested against rsync 3.x only | ADR-0010 | `scripts/lib-rsync.sh` | treated as unset (the search applies) |
| `MOLTBOOK_HF_DATASET` | `Shimo4228/contemplative-agent-data` | Hugging Face dataset that `scripts/sync-research-data.sh` mirrors the knowledge projection to (best-effort after the git push) | ADR-0010 | `scripts/sync-research-data.sh` | disables the upload (set empty for network-isolated runs) |
| `PIPELINE_TASKS_DIR` | `{project}/rfcs` | Directory the unattended weekly chain files its draft RFCs into (written, never committed by the chain) | ADR-0085 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_CLAIMS_PY` | `$HOME/.claude/scripts/claims.py` | Path of the claims helper the weekly chain consults | ADR-0085 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_WEEKLY_TIMEOUT` | `5400` | Seconds before the single weekly report session is killed (a hang detector, not a budget) | ADR-0098 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_DEADCODE_TIMEOUT` | `300` | Seconds before the dead-code scan stage is killed | ADR-0085 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_DOCSCAN_TIMEOUT` | `180` | Seconds before the docs-consistency scan stage is killed | ADR-0085 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_IDENTITY_TIMEOUT` | `900` | Seconds before the monthly identity-distill staging step is killed | ADR-0091 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_DEADLINE_SECONDS` | `10800` | Seconds after the chain starts by which it must be finished (09:00 to 12:00) | ADR-0085 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_INSIGHT_MARKER_MAX_AGE` | `21600` | Maximum age in seconds of the last-insight marker for the value-layer stage to treat the weekly insight as current | ADR-0091 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_NEVER_SELECTED_TIMEOUT` | `300` | Seconds before the never-selected reading stage is killed | ADR-0085 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_CONFUSION_TIMEOUT` | `300` | Seconds before the skill-confusion reading stage is killed | ADR-0085 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `PIPELINE_COMMENT_OUTCOMES_TIMEOUT` | `300` | Seconds before the comment-outcomes reading stage is killed | ADR-0085 | `scripts/weekly-pipeline.sh` | treated as unset (the default applies) |
| `WEEKLY_PREV_COUNT` | `3` | How many previous weekly reports `scripts/weekly-analysis.sh` puts into the materials | ADR-0085 | `scripts/weekly-analysis.sh` | treated as unset (the default applies) |
| `N_SIMS` | `10` | Simulations per arm in `scripts/ipd-two-arm.sh` | ADR-0090 | `scripts/ipd-two-arm.sh` | treated as unset (the default applies) |
| `BENCH_DIR` | `../contemplative-agent-rules/benchmarks/prisoners-dilemma` | Checkout of the IPD benchmark that `scripts/ipd-two-arm.sh` runs | ADR-0090 | `scripts/ipd-two-arm.sh` | treated as unset (the default applies) |
| `BENCH_REF` | `v0.2.0` | Rules-repo tag the IPD calibration contract is pinned to (D-P1-11-6 = A). `scripts/ipd-two-arm.sh` records the checkout's `git describe` in provenance.txt and only warns when the checkout is not at this ref | ADR-0090 | `scripts/ipd-two-arm.sh` | treated as unset (the default applies) |
| `SKIP_WINDOW_GUARD` | `0` | The exact value `1` skips the wait for a clear window between scheduled sessions in `scripts/ipd-two-arm.sh` (16 GB: concurrent heavy Ollama runs have caused OOM) | ADR-0090 | `scripts/ipd-two-arm.sh` | the guard stays on (only `1` skips it) |
| `AUDIT_CHECK_BYPASS` | `0` | The exact value `1` skips the check that arm A's constitution is the last-approved one in `scripts/ipd-two-arm.sh`; for non-production homes only | ADR-0090 | `scripts/ipd-two-arm.sh` | the check stays on (only `1` bypasses it) |
| `VERIFY_OFFLINE` | (unset = probe) | Overrides `.claude/verify.sh`'s network probe before pip-audit: `1` treats the run as offline (pip-audit is inconclusive, exit 2), `0` as online. Unset, a probe of the package index decides | ADR-0062 | `.claude/verify.sh` | treated as unset (the probe decides) |
| `VERIFY_REPO_ROOT` | (the script's own repo) | Repo root `.claude/verify.sh` checks when invoked through the approval mechanism, which runs a verified copy of the script from a temporary file | ADR-0062 | `.claude/verify.sh` | treated as unset (the script's own location decides) |
<!-- env-table:end -->

The Ollama install itself is not a variable: it is the Ollama app, updated by hand outside session windows, with its auto-update turned off by the owner (D-P1-07-3 A). Steps and the per-update record: [docs/runbooks/model-swap.md](runbooks/model-swap.md), [docs/evidence/serving-changes.md](evidence/serving-changes.md).
