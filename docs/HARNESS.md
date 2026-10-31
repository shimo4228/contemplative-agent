# External references: what lives outside this repository

The repository declares that its shared workspace is the repository itself (`docs/CYCLES.md`). Some of what drives it still lives in the owner's private `~/.claude/` and in the public [claude-harness](https://github.com/shimo4228/claude-harness) repository — the *harness*. This page sorts every such reference into three classes, states what a clone without the harness can and cannot run, and lists the changes this repository asks of the harness. It is the answer to "can a third party, or the owner's absence, reproduce the operating model?" (ADR-0098 note, 2026-10-24; D-P2-03-1 = B, owner, 2026-10-24).

## 1. The three classes

**(A) Taken into this repository.** Needed at run time by the unattended chain, or part of the ledger's own rules.

| Reference | Where it lives now | Status |
|---|---|---|
| Who filed an unattended RFC draft (was `claims.py spawn`) | `filed_by:` / `producer:` frontmatter of the draft; numbering and the optional claims record at the gate (`scripts/rfc_inbox.py`) | done (P2-03.2 / .3) |
| The RFC ledger's minimum conventions (state vocabulary, `blocked` form, RFC to ADR promotion) | `rfcs/README.md` | done (P2-03.4) |
| The episode-log read guard for interactive sessions | `integrations/claude-code/hooks/` (shipped); the owner's own copy under `~/.claude/hooks/` is a second installation of the same rule | shipped, boundary sync is P1-10.4 |
| The weekly session's instructions and permission scope | `.claude/skills/weekly-report/`, `scripts/weekly-pipeline.sh` (`--setting-sources project`, so the owner's `~/.claude` settings are not read) | in the repository |

**(B) External dependency, documented here.** The repository calls it by name; the contract is stated below, and the thing itself is the harness's. Links point at the harness `main`; the *Pinned commit* column records the public claude-harness commit the contract was read against (read 2026-10-31 at `1f4fe432057a`, 2026-10-25). Re-read a row and move its pin when the harness changes that skill or script.

| Reference | What this repository uses it for | Input / output contract | Without it | Pinned commit |
|---|---|---|---|---|
| `task-triage` skill (run by the `triage-ca` tick on Wednesday 17:07, and on Saturday inside the `/weekly-gate` session as its Step 8) | judges, verifies and dispatches the drafts that the chain files | reads `rfcs/NNNN-*.md` with `state: draft`; writes `rfcs/` (state changes, triage notes) and may open worktrees; a human merges | drafts stay `draft`; triage is done by hand (section 3) | [`1f4fe432057a`](https://github.com/shimo4228/claude-harness/tree/1f4fe432057a/skills/task-triage) |
| `task-stocktake` skill | state vocabulary of the ledger; periodic sweep of stale entries | reads `rfcs/`; reports, edits state lines | sweep by hand using `rfcs/README.md` | [`1f4fe432057a`](https://github.com/shimo4228/claude-harness/tree/1f4fe432057a/skills/task-stocktake) |
| `rfc-writer` skill | how a filing is shaped (cut-off, numbering, form) | produces `rfcs/NNNN-slug.md` | `rfcs/README.md` carries the minimum | [`1f4fe432057a`](https://github.com/shimo4228/claude-harness/tree/1f4fe432057a/skills/rfc-writer) |
| `claims.py` (`~/.claude/scripts/`) | the owner's private lease log for concurrent sessions: `ready`, `claim`, `release`, `spawn` | appends to `.notes/claims.jsonl` (gitignored). The chain does **not** call it any more; `rfc_inbox.py adopt --claims-py` calls `spawn RFC-NNNN --origin gate --note … [--producer path:line]` when the file exists | nothing changes for the public record | [`1f4fe432057a`](https://github.com/shimo4228/claude-harness/tree/1f4fe432057a/scripts/claims.py) |
| `release-doi` skill | release and DOI steps | procedure lives in `docs/runbooks/release.md` (P0-06.6); the skill does not link to it yet (section 4) | follow the runbook | [`1f4fe432057a`](https://github.com/shimo4228/claude-harness/tree/1f4fe432057a/skills/release-doi) |
| `jsonld-knowledge-graph` skill | the rules for `graph.jsonld` and its HF mirror sync | edits `graph.jsonld`; mirror steps are in its SKILL.md | edit `graph.jsonld` by the rules in `CLAUDE.md` | [`1f4fe432057a`](https://github.com/shimo4228/claude-harness/tree/1f4fe432057a/skills/jsonld-knowledge-graph) |
| `verify-bootstrap` skill | defines the `.claude/verify.sh` contract the harness hook calls | `.claude/verify.sh` exits 0/1 | run `./.claude/verify.sh` by hand | [`1f4fe432057a`](https://github.com/shimo4228/claude-harness/tree/1f4fe432057a/skills/verify-bootstrap) |
| `rules/common/*` (`task-tracking`, `agents`, `planning`; `coding-style` is in the owner's copy only) | the owner's working rules for Claude Code sessions | text read by the session | `CLAUDE.md` is the repository's own rule set | [`1f4fe432057a`](https://github.com/shimo4228/claude-harness/tree/1f4fe432057a/rules/common) |

**(C) Cut off: owner-private.** Not needed to run, verify or understand the repository. Listed so that a reference to them is not mistaken for a dependency.

| Reference | What it is |
|---|---|
| `wiki-harvest`, `wiki-query` | feed the owner's research wiki (Cycle #1); no code here reads their output |
| `archify` | renders `docs/diagrams/*.json` to HTML. The JSON is canonical; the HTML can only be regenerated by the owner |
| `~/.claude/plans/*` | one-off planning files |

## 2. What runs in a clone without the harness

| Stage | Needs | Without the harness |
|---|---|---|
| `contemplative-agent run` and the other CLI commands | Python, `requests`, `numpy`, local Ollama | works |
| Scheduled jobs (`install-schedule`) | macOS launchd | works |
| `scripts/weekly-pipeline.sh`: every stage except the weekly session (listed in its header comment) | `git`, `uv`, `python3`, local data; the identity stage (5b, `distill-identity --stage`) also needs local Ollama | works |
| `scripts/weekly-pipeline.sh`: the weekly session | the `claude` CLI and a Claude Code subscription (ADR-0080 amendment 2026-10-24); the repository's own `.claude/skills/weekly-report/` | works; absent = instruments-only (`REPORT_ABSENT`) |
| Draft filing | nothing: drafts go to `rfcs/.inbox/` | works |
| Saturday `/weekly-gate` | Claude Code with this repository's `.claude/skills/weekly-gate/` | works; `claims.py` is optional |
| Triage of drafts | the harness `task-triage` | **does not run**; do it by hand (below) |
| Repair of code | a person or a Claude Code session | not automated; it never was in the chain (ADR-0098) |

## 3. Operating without the harness

`docs/runbooks/harness-less-operation.md`.

## 4. Requests this repository makes of the harness

Each row is a change in the harness, tracked here until it lands. The evidence column is the harness commit and its date, filled by the owner; an empty cell means not done. Read on 2026-10-31 against the owner's harness and the public claude-harness at `1f4fe432057a`: none of the seven has landed. *Due* is the roadmap's date where it set one; where this repository's side has landed and the roadmap set no harness date, the cell says so.

| Roadmap item | Harness file | Change requested | Due | Evidence (commit, date) |
|---|---|---|---|---|
| P0-03.6 | the secret-scan hook | read patterns from this repository's `config/secret-patterns.txt` instead of a private copy | 2026-10-24 week (passed; the data-repo scan of the same item is at the 2026-11-14 gate) | |
| P1-01.6 | `task-triage` skill | synchronise the post-freeze PR acceptance rules (fix type, RFC id, reproduction trailer) | after 2026-11-28 gate | |
| P1-02.1 | `rfc-writer` skill | the body `## Status` section follows the frontmatter or is renamed; the convention test lives here (this repository renamed the section `## 決定の記録`, P1-02.1) | none set; repository side landed | |
| P1-02.2 | `task-triage` skill | respect `next_check:` (no note or re-check before it) and `decide_by:` | none set; repository side landed (P1-02.2) | |
| P1-13.3 | commit template | the attribution trailers (`Co-Authored-By`, `X-Session`, `Reviewed-by`, and `Roadmap:`, D-P2-01-5 = B) | none (optional, the owner's own change) | |
| P1-10.4 | the duplicated episode-log hooks | retire the harness copy where `integrations/claude-code/hooks/` is the same rule; first run `bash integrations/claude-code/install-hooks.sh` (the owner's installed copy still differs from the shipped one on 2026-10-31) | none set; repository side landed (P1-10.4) | |
| P0-06.6 | `release-doi` skill | become a link to `docs/runbooks/release.md` | none set; repository side landed (P0-06.6) | |
