# ADR-0010: Research Data Sync

## Status

accepted (amended 2026-10-15, 2026-10-17)

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

> **Note (2026-10-15, RFC-0051)**: no longer how it runs. The distill hook was removed on 2026-03-28 (commit `14b833d`); the sync runs daily at 05:30 from a hand-installed launchd job, `com.moltbook.sync-data` (`contemplative-agent sync-data`), not from `install-schedule`. `cli/session_cmds.py::_run_sync` reports a failure only as a stderr warning and exits 0. See the 2026-10-15 amendment below.

## Review-when

Revisit when the sync destination, the daily launchd schedule or the data-repo publication boundary changes (the pre-commit gates of the 2026-10 amendments are the current boundary).

## Consequences

- Runtime data evolution can be tracked via git log
- The main repository stays focused on source code only
- Risk of accidentally publishing episode logs is eliminated

## Amendment (2026-10-15): home-path gate before commit (RFC-0051)

Every published writer now records paths relative to `MOLTBOOK_HOME`, with the home as `~` outside it (`src/contemplative_agent/core/portable_path.py`; RFC-0050 did the snapshot manifests, RFC-0051 the weekly value-layer reading, the confusion-pair findings section, the log-anomaly state file, the watchdog status file, and the writers of three evidence files). The machine's home path names the OS user, and before the fix 114 synced files held it (`pipeline/` 7, `reports/analysis/` 10, `snapshots/` 97 — the data repo's working tree on 2026-10-15).

- **Gate.** `scripts/sync-research-data.sh` searches the data repo's working tree (`.git/` excluded; narrowed to the files git can publish on 2026-10-17, see below) for the home path, in any letter case (macOS file systems are case-insensitive, so a lowercased `/users/<user>` names the same user), after the rsync and the `knowledge.json` export, and before `git add`; symlink targets are checked too, since git stores a link's target as its content. On a hit it prints the file names (never their content) to stderr and exits nonzero without committing or pushing. It rewrites nothing — the fix belongs to the writer. `HOME` empty or `/`, or a search that errors, also stops the sync (fail closed).
- **Old files.** Files written before the fix are rewritten once by `scripts/rewrite_home_paths.py` (dry-run by default, `--apply` to write; the file set is the rsync set above, read from the sync script's own excludes). Until that runs the gate keeps the sync shut. The data repo's git history is out of scope (roadmap item on public-data versions and backfill).
- **Visibility.** A stopped sync is a stderr warning only (see the note above), so `scripts/pipeline_watchdog.sh` gains a `sync-data` row (ADR-0085 amendment 2026-10-15).

Review-when: the sync stops being an rsync pass-through (an export-time transform layer appears), or a new route publishes generated files from outside `MOLTBOOK_HOME`.

## Amendment (2026-10-17): the gate searches only what git can publish (RFC-0053)

The 2026-10-15 gate searched the whole working tree, which is wider than what the sync publishes. `git add -A` stages tracked files and untracked files that are not ignored. An ignored file never reaches the public repo.

- **Searched set.** The gate now reads its file set from `git ls-files -z --cached --others --exclude-standard` in the data repo, which is the set `git add -A` can stage (`.gitignore`, `.git/info/exclude` and `core.excludesFile` all apply). Regular files are searched for the home path; symlinks are checked by their target. A tracked file gone from the working tree (listed by `--cached`, deleted by rsync's `--delete`) has nothing to search and is skipped, because its deletion is what gets published. `-z` keeps names with spaces or non-ASCII text intact, with no `core.quotePath` quoting. The match stays case-insensitive, and the sync still stops when `HOME` is empty or `/` or when the search fails (now including a failing `git ls-files`).
- **Why.** An ignored file in an rsync-excluded path (`reports/.private/`, ignored by the data repo's own `.gitignore`) is neither updated nor deleted by rsync, and `scripts/rewrite_home_paths.py` cannot reach it either, because it rewrites `MOLTBOOK_HOME`. One such file held the home path, so every daily sync stopped from 2026-10-15T20:30Z on, and nothing was committed to the public data repo. The gate was refusing a file the sync would never have published.
- **Unchanged.** Tracked and untracked-not-ignored files are searched as before, and the rsync exclude list is unchanged. A file that is ignored but already tracked (force-added) is still in `--cached`, so it is still searched.

Review-when: the sync stops staging with `git add -A` (the gate's set must follow whatever stages), or the data repo starts publishing through another route (LFS, submodules).
