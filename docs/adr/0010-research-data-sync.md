# ADR-0010: Research Data Sync

## Status

accepted

## Date

2026-03-25

## Context

Runtime data (knowledge.json, identity.md, history/, etc.) is stored in MOLTBOOK_HOME but is not under git version control. We want to version-control it for research purposes, but mixing it into the main repository causes the following problems:

- Episode logs (`logs/*.jsonl`) are a prompt injection vector (ADR-0007)
- Runtime data and source code commit histories become interleaved
- Risk of accidentally committing sensitive files like credentials.json

## Decision

Rsync only safe runtime data to `~/MyAI_Lab/contemplative-agent-data/` (a separate repository), then automatically git commit + push after distill execution.

### Sync Targets

- knowledge.json, identity.md, agents.json
- history/identity/\*, history/knowledge/\*
- skills/\*, rules/\*, meditation/results.json
- reports/comment-reports/\* (from the project repository)

### Exclusions

- `logs/*.jsonl` — Prompt injection vector (ADR-0007)
- `credentials.json` — API keys
- `rate_state.json`, `commented_cache.json` — Ephemeral data with no research value

### Sync Timing

Runs as a post-processing step of the distill command. No additional launchd plist required. Manual execution: `contemplative-agent sync-data`.

## Consequences

- Runtime data evolution can be tracked via git log
- The main repository stays focused on source code only
- Risk of accidentally publishing episode logs is eliminated
