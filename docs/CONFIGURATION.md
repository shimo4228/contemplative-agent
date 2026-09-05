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
contemplative-agent install-schedule [--weekly-pipeline] [--weekly-insight] [--weekly-backup]
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

Any selector failure (fail-open, empty catalog, unloadable template) does
fall back to full-corpus injection, and **at the current corpus size that
fallback no longer fits the context window** (45 skills ≈ 36K tokens against
`NUM_CTX` 32,768), so the audit-C2 budget guard skips the call rather than
degrading it. In practice fail-open has not fired since 2026-07-13. See the
ADR-0081 amendment (2026-08-08).

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

34 loaded prompt templates plus 2 script-read prompt documents (`principles.md` and `weekly-analysis.md` feed the materials file built by `scripts/weekly-analysis.sh` and are read by the `/weekly-report` skill — none by the loader. The fix / review / insight-recommendation / improvement prompts retired with their stages, ADR-0098; `weekly-analysis-ja.md` retired with the Japanese rendering, RFC-0010/ADR-0099). The main ones:

| File | Drives |
|------|--------|
| `distill_episode.md` | Per-episode grounded pattern extraction from episode logs (ADR-0060; the retired batch prompts `distill.md` / `distill_refine.md` were deleted in ADR-0072) |
| `distill_postgate.md` | Per-pattern durability verdict on what `distill_episode.md` produced — keeps the grounded patterns, drops the ones written to fill the space. On by default (`MOLTBOOK_DISTILL_POSTGATE=0` opts out); fails open (keeps all) with a `reason=postgate_*` line |
| `verification_solve_extract_system.md` | Create-time math challenge solving: guarded expression extraction (the free-reasoning fallback was retired by ADR-0062's 9th amendment — past this path the solver abstains) |
| `insight_extraction.md` | Skill extraction from uncategorized patterns (naming/vocabulary discipline, ADR-0074) |
| `insight_novelty.md` / `insight_novelty_system.md` | Novelty gate: one grouping call judging which candidate clusters an existing or previously staged skill theme already covers (ADR-0074; fails open) |
| `identity_distill.md` | Identity update from knowledge (1-stage, ADR-0030) |
| `constitution_amend.md` | Constitution amendment proposals |
| `stocktake_description.md` / `stocktake_description_system.md` | Description-fidelity audit (ADR-0081) — the one LLM call left in `skill-stocktake` after ADR-0097 retired grouping / merge / clean and the rules pass |
| `stocktake_merge_rules.md` | Shared-core synthesis of a co-selection family into one Practice/Rationale rule — the prompt for family-to-rule promotion (ADR-0097 Decision 7; `rules-distill` / `rules-stocktake` were retired) |
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

After any behavior-producing command (`distill`, `distill-identity`, `insight`, `amend-constitution`), a pivot snapshot is written to `MOLTBOOK_HOME/snapshots/<command>_<timestamp>/` containing:

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
contemplative-agent install-schedule --weekly-pipeline                  # + unattended weekly chain (Sat 09:00, ADR-0085)
contemplative-agent install-schedule --watchdog                         # + pipeline watchdog (pure bash; daily 04:30 + Sat 12:30/13:30 + Mon 11:00)
contemplative-agent install-schedule --uninstall                        # Remove schedule
```

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
`credentials.json` is excluded — a restore needs this repo plus a re-issued
credential. `logs/ollama-serve.log*` is excluded too: the local daemon's own
stderr is re-derivable operational noise, and at 96 MB it was one weekly run
from crossing GitHub's 100 MB hard limit and stalling the off-site copy of the
episode logs this backup exists to protect. See
`docs/runbooks/runtime-backup-restore.md` for the restore procedure.

Valid intervals: 1, 2, 3, 4, 6, 8, 12, 24 hours.

`install-schedule` manages the agent, distill, insight, backup, weekly-pipeline, and watchdog plists — declaratively: re-running it removes any optional job whose flag is not passed, so always pass the full desired set. One plist under `config/launchd/` is outside its scope: `com.moltbook.ollama-restart.plist` is installed and updated manually via `launchctl`, and `--uninstall` does not touch it. A legacy `com.moltbook.weekly-analysis` job is likewise outside its scope — the standalone installer was removed on 2026-08-29, so if that plist still exists on a machine it is no longer managed and must be removed by hand (`launchctl unload` + `rm`). It restarts the local `ollama serve` nightly at 23:55 — starting `ollama serve` directly (no GUI app) with `AbandonProcessGroup` so the daemon survives its parent exiting. Between the `pkill` and the restart it calls `scripts/rotate-log.sh <path> 7`, which moves `ollama-serve.log` aside and gzips it, keeping seven compressed generations: that is the one moment in the day when the writer is dead, so the job that owns the log also rotates it. Rotation failures are chained with `;` so they can never stop the daemon from starting, and are prefixed `ERROR:` so the weekly anomaly sweep sees them. `RunAtLoad` is set, so `launchctl load` restarts Ollama on the spot — reload it outside a scheduled session window. The repo copy is the reference template: when the live plist changes, mirror it here in the same change.

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
(relevance score, reason code, `subscribed` label, body as `content_b64` +
`content_sha256`) between a `scan_start` and a `scan_end` carrying the run
verdict plus which submolts were read and which were skipped. Read it with
`report --days N --submolt-scope`; nothing in it feeds a gate. Set
`MOLTBOOK_SUBMOLT_SCOPE_DISABLE=1` to neuter an installed sweep without
uninstalling its launchd job.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MOLTBOOK_API_KEY` | (required) | Moltbook API key |
| `OLLAMA_MODEL` | `gemma4:e4b` | Ollama model name |
| `MOLTBOOK_HOME` | `~/.config/moltbook/` | Runtime data directory |
| `CONTEMPLATIVE_CONFIG_DIR` | `{project}/config/` | Config templates directory |
| `OLLAMA_TRUSTED_HOSTS` | (none) | Additional trusted Ollama hosts (comma-separated) |
