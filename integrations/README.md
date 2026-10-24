# Coding Agent Integrations

## Claude Code: Episode Log Protection Hooks

Episode logs (`$MOLTBOOK_HOME/logs/episodes/`, since ADR-0107) contain raw content from other agents on Moltbook. `agent-launchd.log*` is blocked too (older generations hold DEBUG output with publish bodies). If a coding agent reads these files, the content enters its context and may influence its behavior (indirect prompt injection). These hooks block that access.

### Install

```bash
bash integrations/claude-code/install-hooks.sh
```

This copies 3 hook scripts plus the shared `_episode-log-common.sh` to `~/.claude/hooks/`. This directory is the canonical source of the hooks; re-run the installer after pulling. `tests/test_episode_log_hooks.py` pins the boundary with block/allow fixtures.

> The unattended weekly session runs with `--setting-sources project`, which drops user hooks, so hooks do not apply there: its boundary is the Read deny list in `scripts/weekly-pipeline.sh` (test C-SCOPE-6).

### Configure

Add the following to `~/.claude/settings.json`. If you don't have a `hooks` section yet, create one:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-read.sh" }]
      },
      {
        "matcher": "Bash",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-bash.sh" }]
      },
      {
        "matcher": "Grep",
        "hooks": [{ "type": "command", "command": "bash ~/.claude/hooks/block-episode-logs-grep.sh" }]
      }
    ]
  }
}
```

If you already have `PreToolUse` entries, add these 3 objects to the existing array.

### What gets blocked

| Tool | Blocked | Allowed |
|------|---------|---------|
| `Read` | everything under `$MOLTBOOK_HOME/logs/episodes/` (day files, `.bak`, `.pre-cleanup.bak`), and `logs/agent-launchd.log*` | Everything else, including self-written telemetry directly under `logs/` (`audit.jsonl`, `skill-selection-*.jsonl`, ...) |
| `Bash` | `cat`, `head`, `tail`, `grep`, `jq`, `<` redirection etc. naming `logs/episodes` or `agent-launchd.log` (heuristic) | `wc -l`, `ls` (metadata only), reads of other logs |
| `Grep` | A search rooted at `logs/episodes`, `logs/` or `$MOLTBOOK_HOME` (recursion would descend into `episodes/`), or a glob naming them | Search in other directories and single self-written logs |

### What to use instead

- `knowledge.json` — distilled behavioral patterns
- `identity.md` — agent persona
- `reports/comment-reports/` — daily activity reports (URLs defanged)
- `reports/analysis/` — weekly analysis reports

---

## Skills (Shelved)

Coding agent skills (`-ca` series) are shelved. See [ADR-0013](../docs/adr/0013-shelve-coding-agent-skills.md).
