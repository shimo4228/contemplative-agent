# Threat model

Status: living document (canonical, English). Japanese mirror:
[threat-model.ja.md](./threat-model.ja.md). Earlier point-in-time reviews
([2026-04-01 security scan](./2026-04-01-security-scan.md),
[2026-04-01 episode-log access control](./2026-04-01-episode-log-access-control.md))
are historical; where they disagree with this page, this page wins.

This page says **what the project protects, where its trust boundaries are, which
threats it treats as threats, and which residual risks it has accepted**. It is
deliberately short: the design is *security by absence* ([ADR-0007](../adr/0007-security-boundary-model.md),
[ADR-0015](../adr/0015-one-external-adapter-per-agent.md)), so most of the
argument is about what does not exist.

## Assets

| Asset | Why it matters |
|---|---|
| API keys (Moltbook, optional provider and research-tool keys) | impersonation of the agent's public identity; spend on someone else's account. Inventory and rotation: [credential-rotation.md](../runbooks/credential-rotation.md) |
| The agent's public identity and posts | its Moltbook account speaks in public under `--guarded` / `--auto` |
| The longitudinal record (episode logs, decisions, published data) | the research output; integrity and provenance matter more than secrecy |
| The operator's machine and the Claude Code sessions run on it | the only actors with tool permissions in this system |

## What is *not* a threat surface

Two things that look like threats and are deliberately not treated as such
(CLAUDE.md, security policy; the reasoning is structural, not optimistic):

- **Value-layer content** (skills, rules, identity, constitution). It is injected
  into prompts and can change what the agent *writes*; it cannot move any guard,
  because containment, sanitisation and control-character stripping all live in
  code. No path lets an LLM judgement authorise a write, a publication or a
  permission. Review value-layer text for its effect on text quality and on the
  experiment, not for "dangerous operations it might provoke".
- **Prompt injection against the agent.** The only outward action the agent has is
  an HTTP request to one adapter. A successful injection changes generated text
  and choices the code validates (skill names, submolt names); there is no tool,
  file-write or permission path to abuse. The injection guards that exist
  (`wrap_untrusted_content()`, output sanitisation) are an experiment in designs
  that would hold for broader-permission agents; this repository's safety does not
  rest on them.

## Threats that *are* in scope

Exactly two, and both are about **code and sessions that hold permissions**:

- **(a) A code change that widens the I/O surface or the agent's permissions**:
  a new adapter, a new outward HTTP target, a new file write outside the data
  directory, a new credential path. Controls: the one-adapter rule (ADR-0015), the
  domain lock and `allow_redirects=False` on every transport call, the import-
  direction gate, the dependency floor test, the `/home` field allowlist
  (`tests/test_home_field_allowlist.py`), the shell-egress inventory
  (`tests/test_shell_egress_allowlist.py`), and review (the I/O table below is the
  list to diff against).
- **(b) A tool-holding Claude Code session reading untrusted text.** The raw
  episode logs (`logs/episodes/`) and `agent-launchd.log*` hold other agents'
  unfiltered posts; a session with Read/Bash/Edit that ingests them can be steered.
  Controls: the bundled hooks ([integrations/claude-code/](../../integrations/claude-code/),
  pinned by `tests/test_episode_log_hooks.py`), and for the unattended weekly
  session -- which drops user hooks -- a positively scoped Read allow plus a deny
  list (`scripts/weekly-pipeline.sh`, tests C-SCOPE-0..9) and a preflight that
  refuses widening project settings. Humans and sessions read
  `reports/comment-reports/` (URLs defanged, no raw JSON) instead.

## Trust boundaries and the I/O surface

Everything the system can do to the outside, as of this revision. The table is
maintained by hand and **must be regenerated from the I/O allowlist test constants
once those exist (P1-08.17); the test, not this table, is then the source of
truth**.

| Surface | Direction | Target | Carried by | Guard |
|---|---|---|---|---|
| Moltbook API | out (HTTP) + in | `www.moltbook.com` only | `adapters/moltbook/client.py` | domain lock, `allow_redirects=False`, rate budgets, `/home` field allowlist |
| Local inference | out (HTTP) | Ollama on localhost / `OLLAMA_TRUSTED_HOSTS` (dot-free names) | `core/llm/`, `core/embeddings.py` | host allowlist, `allow_redirects=False`; a local utility under ADR-0015, not an external adapter |
| Provider inference (optional sibling) | out (HTTP) | an LLM provider API | sibling repo `contemplative-agent-cloud` via the `LLMBackend` Protocol | human-started, research use only; counted as external by [ADR-0015 addendum 2026-10-24](../adr/0015-one-external-adapter-per-agent.md) |
| Research tool (human-started) | out (HTTP) | a third-party answer API | `evals/jev_arm.py` | human runs it, key is the human's, output goes to `.notes/` only (`assert_private_output`); no bodies are published |
| Data publication | out (git, HF) | public data repo, HF dataset | `scripts/sync-research-data.sh`, `sync-data` | embedding-free export boundary, credential/`*.env`/log exclusions |
| Private backup | out (git) | private backup repo | `scripts/backup-runtime.sh` | credential/`*.env` exclusions, visibility check |
| Unattended Claude session | out (CLI) | the model provider via `claude -p` | `scripts/weekly-pipeline.sh` | no Bash; tool set, Read allow/deny, preflight (ADR-0098) |
| Local files | in/out | `$MOLTBOOK_HOME` only | `core/_io.py`, store modules | containment check, 0600 for secrets, symlink-safe temp writes |

Shell and launchd verbs that can leave the machine are pinned separately in
`tests/test_shell_egress_allowlist.py`; the agent's own transport calls are pinned
by the per-module tests and `tests/test_cloud_egress_absence.py`.

## Accepted residual risks

Each row is a risk the project knowingly carries. Review them under **Review
when** below.

| # | Residual | Why it is accepted |
|---|---|---|
| R1 | An API error body (up to 500 chars, printable-stripped, single line) can reach `*.log` through a WARNING | diagnosis needs it; collapsed to one line it is not a multi-line injection carrier (`client.py`, T-LOG-DEBUG-CONTENT). The one-off `agent-launchd.log` exception remains until rotation replaces old generations |
| R2 | A human-started research tool sends third-party post bodies to a third-party API | started by a person, with the person's key, output kept in `.notes/`, results published only as aggregates; it is outside the agent loop |
| R3 | The Saturday interactive session reads `comment-report-*.md`, whose `Context` sections quote other agents' posts | a human is present, URLs are defanged (including Title and Submolt), it is not raw JSON, and the session is the one place that judgement belongs |
| R4 (a) | Output of the weekly session (report, findings, drafted `rfcs/` entries) is second-hand text derived from untrusted posts; the chain's structural gate checks names and `state:` only, and the Saturday full-tool sessions then read it | gated by the human Saturday read before anything is committed publicly; a steered draft is a quality problem in a document, not a permission |
| R5 (b) | Fixed `post` strings in public fixtures and evidence (`docs/evidence/rfc-0017/comment_golden-skills-off-20260902.json`, `evals/datasets/comment_golden.jsonl` -- 12 rows, `tests/fixtures/sampling/comment_suite.jsonl` -- 4 rows) are real posts unless a manifest says `source: synthetic` | they are public posts already; the provenance manifest for each is a to-do (P1-10.1) -- a synthetic one leaves this row |
| R6 (c) | `tests/fixtures/benchmark/real_sample.jsonl` holds 50 production episode rows, and git history keeps them even after removal | removal and history note tracked as P0-03.11; the weekly session's Read deny covers the path in the meantime |

## Where the keys are

[docs/runbooks/credential-rotation.md](../runbooks/credential-rotation.md): seven
locations, why plain 0600 files and not a keychain, and the leak procedure.

## Review when

- an I/O surface is added or removed (the table above, and the egress tests);
- a sibling repo is unfrozen, or the cloud backend gains a default path;
- the weekly chain's tool set or `--setting-sources` changes;
- a residual row is resolved (delete it) or a new one is accepted (add it, with the reason);
- the platform changes what `/home` delivers (`scripts/api_drift_scan.py` signals this).

Reporting a vulnerability or requesting removal of data: see [SECURITY.md](../../SECURITY.md).
