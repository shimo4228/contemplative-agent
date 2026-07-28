# Configuration Guide

Detailed configuration reference for the Contemplative Agent. For quick start and overview, see [README.md](../README.md).

> Everything the LLM sees — constitution, identity, skills, rules, the loaded pipeline prompts, and the view seeds — lives as Markdown under `$MOLTBOOK_HOME/`, editable per run.

## Table of Contents

- [CLI Commands](#cli-commands)
- [Character Templates](#character-templates)
- [Domain Settings](#domain-settings)
- [Identity & Constitution](#identity--constitution)
- [Skills & Rules](#skills--rules)
- [Autonomy Levels](#autonomy-levels)
- [Session & Scheduling](#session--scheduling)
- [Development](#development)
- [Environment Variables](#environment-variables)

---

## CLI Commands

### Daily Operation

```bash
contemplative-agent init                   # Create identity + knowledge files
contemplative-agent register               # Register on Moltbook
contemplative-agent run --session 60       # Run a session (feed → replies → posts)
```

### Distillation & Skill Evolution

```bash
contemplative-agent distill --days 3       # Extract patterns from episode logs
contemplative-agent distill-identity       # Distill identity from knowledge (block-aware)
contemplative-agent insight                # Extract behavioral skills
contemplative-agent rules-distill          # Synthesize rules from skills
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
contemplative-agent skill-stocktake                    # Audit skills for duplicates / low quality
contemplative-agent rules-stocktake                    # Audit rules for duplicates / low quality
```

### Scheduling

```bash
contemplative-agent install-schedule [--weekly-analysis] [--weekly-insight] [--weekly-backup]
contemplative-agent install-schedule --uninstall
```

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
- `skills/*.md` -- Initial behavioral skills (2)
- `rules/*.md` -- Initial behavioral rules (2)

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
    "relevance": 0.92,
    "known_agent": 0.75
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
| `thresholds.relevance` | Minimum score (0.0--1.0) to engage with a post. Higher = more selective |
| `thresholds.known_agent` | Threshold for recognizing a known agent |
| `repo_url` | Public repository linked in the agent's profile |

### Overriding Domain Config

```bash
contemplative-agent --domain-config path/to/custom-domain.json run --session 30
```

---

## Identity & Constitution

### Identity

Location: `MOLTBOOK_HOME/identity.md` (default: `~/.config/moltbook/identity.md`)

- Starts empty at `init`, or from a template if pre-copied
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
candidate already covers (ledger: `MOLTBOOK_HOME/logs/insight-staged.jsonl`);
the marker advances when candidates reach review (staging or the interactive
loop), not at adoption. `--stage` refuses while an unreviewed batch sits in
staging — review it with `adopt-staged` first. Weekly automation:
`install-schedule --weekly-insight` (default Mon 08:00).

2026-07-18 amendment: the novelty judge runs in token-budgeted chunks (each
carries the full known-theme inventory) and fails open per chunk; clusters
that reach extraction unjudged are capped at `MOLTBOOK_INSIGHT_FAILOPEN_CAP`
(env, default 20 — a circuit breaker for a broken gate, never applied to
judged-novel clusters). Deferred clusters are not staged or ledger-written
and recur in later windows; deferrals are recorded in
`MOLTBOOK_HOME/logs/insight-novelty.jsonl`.

You can also hand-write skill files and place them in the directory.

Injection (ADR-0076/0081): every adopted skill body is injected into the
generation system prompt by default. Setting
`MOLTBOOK_SKILL_SELECTION_ENFORCE=1` (env, read at call time) switches the
three observed publish paths (comment / reply / cooperation post, with
post_title reusing cooperation post's selection) to two-pass injection —
a pass-1 LLM selection picks the applicable skills and pass 2 generates
with only those bodies. Any selector failure falls back to full injection;
unset (default) keeps shadow-only observation. The selection log
(`logs/skill-selection-*.jsonl`) marks each record with `enforced`.
launchd does not inherit shell exports, so for the production schedule
re-run `contemplative-agent install-schedule` with the flag exported —
the installer bakes it into the session plist's `EnvironmentVariables`
(re-run without it to turn enforcement back off).

### Rules

Location: `MOLTBOOK_HOME/rules/*.md`

```bash
contemplative-agent rules-distill        # Distill rules from accumulated skills
contemplative-agent rules-distill --full # Process all patterns
contemplative-agent rules-distill --stage # Staged approval
```

You can also hand-write rule files and place them in the directory.

### Auditing for Duplicates

```bash
contemplative-agent skill-stocktake      # Detect and merge duplicate skills
contemplative-agent rules-stocktake      # Detect and merge duplicate rules
```

### Coding Agent Skills (-ca)

Five maintenance skills are available in [`integrations/`](../integrations/README.md) for coding agents (Claude Code, Cursor, OpenAI Codex). These use the coding agent's own reasoning (Opus-class holistic judgment) instead of the local model pipeline.

```bash
bash integrations/claude-code/install.sh   # Claude Code: copies to .claude/skills/
bash integrations/cursor/install.sh        # Cursor: converts to .cursor/rules/*.mdc
bash integrations/codex/install.sh         # Codex: appends to AGENTS.md
```

See [integrations/README.md](../integrations/README.md) for the full workflow and security notes.

---

## Pipeline Prompts & View Seeds

Every LLM interaction the agent makes is defined in a Markdown file. After `init`, `MOLTBOOK_HOME/` contains **every text the LLM will see** — the constitution, identity, skills, rules, every loaded pipeline prompt, and the view seeds. Edit any file to change behavior; changes are visible to `git diff` against the shipped defaults and captured in pivot snapshots. The counts below are the canonical inventory; other documents deliberately reference this section instead of repeating numbers.

### Pipeline prompts

Location: `MOLTBOOK_HOME/prompts/*.md` (default: `~/.config/moltbook/prompts/`)

38 loaded prompt templates plus 7 script-read prompt documents (`principles.md`, `weekly-analysis.md`, and `weekly-analysis-ja.md` — the Japanese translation pass — are read by `scripts/weekly-analysis.sh`; `fix-implementation.md`, `fix-review.md`, `insight-recommendation.md`, and `pipeline-improvement.md` are read by `scripts/weekly-pipeline.sh` (ADR-0085) — none by the loader). The main ones:

| File | Drives |
|------|--------|
| `distill_episode.md` | Per-episode grounded pattern extraction from episode logs (ADR-0060; the retired batch prompts `distill.md` / `distill_refine.md` were deleted in ADR-0072) |
| `distill_postgate.md` | Per-pattern durability verdict on what `distill_episode.md` produced — keeps the grounded patterns, drops the ones written to fill the space. On by default (`MOLTBOOK_DISTILL_POSTGATE=0` opts out); fails open (keeps all) with a `reason=postgate_*` line |
| `verification_solve_extract_system.md` | Create-time math challenge solving: guarded expression extraction (the free-reasoning fallback was retired by ADR-0062's 9th amendment — past this path the solver abstains) |
| `insight_extraction.md` | Skill extraction from uncategorized patterns (naming/vocabulary discipline, ADR-0074) |
| `insight_novelty.md` / `insight_novelty_system.md` | Novelty gate: one grouping call judging which candidate clusters an existing or previously staged skill theme already covers (ADR-0074; fails open) |
| `rules_distill.md` | Rule distillation from accumulated skills (2-stage with `rules_distill_refine.md`) |
| `identity_distill.md` | Identity update from knowledge (1-stage, ADR-0030) |
| `constitution_amend.md` | Constitution amendment proposals |
| `stocktake_skills.md` / `stocktake_rules.md` / `stocktake_merge.md` / `stocktake_merge_rules.md` / `stocktake_clean.md` / `stocktake_description.md` | Duplicate detection, merge, cleaning, and description-fidelity audit (ADR-0081) for skills / rules |
| `system.md` | Base system prompt (credentials-safety note — edit with care) |
| `learned_skills_framing.md` / `learned_rules_framing.md` | Usage framing preambles before the injected `<learned_skills>` / `<learned_rules>` blocks: the corpus is internal disposition, never narrated in published text (weekly diagnosis 2026-07-05 F1.1; hardcoded fallback if deleted) |
| `relevance.md` / `comment.md` / `reply.md` / `cooperation_post.md` / `post_title.md` / `internal_note.md` / `dialogue.md` | Adapter actions (comment scoring, reply text, post generation, internal note, dialogue) |
| `reply_post_block.md` | The `Original post:` section of a reply, filled into `reply.md`'s `{original_post_block}` slot only when a post body is held. The comment-scan path holds none, and rendering the slot empty made the prompt assert `complete (0 chars)` under the header — a false claim the model then described (weekly diagnosis 2026-07-24 F1.1). Deleting this file keeps the section (hardcoded fallback + warning); it never silently drops a post |
| `skill_selection.md` | Shadow pass-1 skill applicability selection before content generations (ADR-0076; records to `logs/skill-selection-*.jsonl`, injection unchanged) |

**Editing model:** Copied from `config/prompts/` at `init`; after that your home copies are the source of truth. If you delete a file, the loader falls back to the packaged default — useful after a version upgrade introduces new prompts to an existing home. Edits pass the same forbidden-pattern validation that identity content does; a tainted override silently falls back to the packaged default with a warning.

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

After any behavior-producing command (`distill`, `distill-identity`, `insight`, `rules-distill`, `amend-constitution`), a pivot snapshot is written to `MOLTBOOK_HOME/snapshots/<command>_<timestamp>/` containing:

- `views/`, `constitution/`, `prompts/`, `skills/`, `rules/`, `identity.md` — full inference-time context
- `centroids.npz` — view centroid embeddings at that moment
- `manifest.json` — thresholds, embedding model, timestamp, source paths

This means every pattern or amendment is reproducible from its snapshot alone. To audit what changed since a prior run:

```bash
diff -r MOLTBOOK_HOME/snapshots/distill_OLD/prompts/ MOLTBOOK_HOME/prompts/
```

---

## Autonomy Levels

| Level | Flag | Behavior | When to use |
|-------|------|----------|-------------|
| Approve | `--approve` (default) | Every post requires y/n confirmation | Development, initial testing |
| Guarded | `--guarded` | Auto-post if content passes safety filters | Supervised operation |
| Auto | `--auto` | Fully autonomous | Unattended sessions |

```bash
contemplative-agent run --session 60              # Default: approve mode
contemplative-agent --guarded run --session 60    # Guarded mode
contemplative-agent --auto run --session 60       # Auto mode
```

---

## Session & Scheduling

### Session Duration

```bash
contemplative-agent run --session 30     # 30-minute session
contemplative-agent run --session 120    # 2-hour session (default: 60)
```

### macOS Scheduling (launchd)

```bash
contemplative-agent install-schedule                                    # 6h intervals, 120min sessions, distill at 03:00
contemplative-agent install-schedule --interval 4 --session 90          # 4h intervals, 90min sessions
contemplative-agent install-schedule --distill-hour 5                   # Distill at 05:00
contemplative-agent install-schedule --no-distill                       # Sessions only, no distillation
contemplative-agent install-schedule --weekly-insight                   # + weekly staged insight (Sat 08:00, ADR-0074; 1h before the weekly chain)
contemplative-agent install-schedule --weekly-backup                    # + weekly runtime backup to a PRIVATE mirror repo (Mon 10:00)
contemplative-agent install-schedule --weekly-pipeline                  # + unattended weekly chain (Sat 09:00, ADR-0085; replaces --weekly-analysis)
contemplative-agent install-schedule --watchdog                         # + pipeline watchdog (pure bash; daily 04:30 + Sat 12:30/13:30 + Mon 11:00)
contemplative-agent install-schedule --uninstall                        # Remove schedule
```

`--weekly-pipeline` and `--weekly-analysis` are mutually exclusive: the chain
(`scripts/weekly-pipeline.sh`) runs `weekly-analysis.sh` as its own Stage 1,
then diagnosis → fix (worktree + Verify) → insight review → decision packet.
Nothing in the chain commits or adopts — promotion happens in the Saturday
`/weekly-gate` session. Stage selection for a shadow rollout:
`MOLTBOOK_PIPELINE_STAGES=report,diagnosis,insight,packet` (no `fix`). The
watchdog writes `reports/PIPELINE-STATUS.md` and posts a Notification Center
alert when the failure set changes.

The weekly backup (`scripts/backup-runtime.sh`) rsync-mirrors MOLTBOOK_HOME —
including `logs/`, which `sync-data` deliberately excludes from the public data
repo — into the git repo at `MOLTBOOK_BACKUP_REPO` (default
`~/MyAI_Lab/contemplative-agent-runtime-backup`) and pushes it. The backup repo
must stay **private forever**: episode logs are raw untrusted external content.
`credentials.json` is excluded — a restore needs this repo plus a re-issued
credential. See `docs/runbooks/runtime-backup-restore.md` for the restore
procedure.

Valid intervals: 1, 2, 3, 4, 6, 8, 12, 24 hours.

`install-schedule` manages the agent, distill, weekly-analysis, insight, backup, weekly-pipeline, and watchdog plists — declaratively: re-running it removes any optional job whose flag is not passed, so always pass the full desired set. One plist under `config/launchd/` is outside its scope: `com.moltbook.ollama-restart.plist` is installed and updated manually via `launchctl`, and `--uninstall` does not touch it. It restarts the local `ollama serve` nightly at 23:55 — starting `ollama serve` directly (no GUI app) with `AbandonProcessGroup` so the daemon survives its parent exiting. The repo copy is the reference template: when the live plist changes, mirror it here in the same change.

---

## Development

### Running Tests

```bash
uv run pytest tests/ -v
uv run pytest tests/ --cov=contemplative_agent --cov-report=term-missing
```

Test organization and fixtures live under `tests/`; see [docs/CODEMAPS/INDEX.md](CODEMAPS/INDEX.md) for the module map used by tests.

---

## Runtime Logs

Runtime logs live under `MOLTBOOK_HOME/logs/`. Daily episode logs
(`YYYY-MM-DD.jsonl`) contain untrusted external content and should not be read
directly by coding agents. `api-audit.jsonl` records structural API outcomes
only. `verification-audit.jsonl` records create-time verification challenges for
solver evaluation: challenge text is stored as `challenge_b64` plus
`challenge_sha256`, with hashed `verification_code`, answer, `solver_path`, and
`verify_success`.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MOLTBOOK_API_KEY` | (required) | Moltbook API key |
| `OLLAMA_MODEL` | `gemma4:e4b` | Ollama model name |
| `MOLTBOOK_HOME` | `~/.config/moltbook/` | Runtime data directory |
| `CONTEMPLATIVE_CONFIG_DIR` | `{project}/config/` | Config templates directory |
| `OLLAMA_TRUSTED_HOSTS` | (none) | Additional trusted Ollama hosts (comma-separated) |
