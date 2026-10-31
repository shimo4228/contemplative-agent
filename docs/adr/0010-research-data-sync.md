# ADR-0010: Research Data Sync

## Status

accepted — partially-superseded-by ADR-0114 (Sync Timing: the daily launchd job replaces the distill post-processing hook) (amended 2026-10-15, 2026-10-17, 2026-10-24, 2026-10-31)

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
>
> **Note (2026-10-24, ADR-0114)**: superseded. The daily launchd job is now managed by `install-schedule --sync-data`; Sync Targets and Exclusions here are unchanged.

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

## Amendment (2026-10-24): an allowlist boundary, retraction, a secret scan, and no force push (P0-03)

- **Allowlist.** The rsync call now transfers only the top-level names in `PUBLIC_TOP_LEVEL` (`identity.md`, `constitution/`, `meditation/`, `pipeline/`, `reports/`, `rules/`, `skills/`, `snapshots/`, `views/`) and ends in `--exclude='*'`. A new top-level name is not published until it is added, and is named on stderr. Every earlier leak (a 72 MB backup with embeddings, locks, absolute paths) came through a name nobody had written down.
- **One exclude list.** The names that are never published live in `config/sync-excludes.txt` (shared with `backup-runtime.sh`) and `config/sync-excludes-public.txt` (public only: `logs/`, `*.bak*`, `.last_*`, `_gc_trash/`, ...), read with `--exclude-from`. `scripts/gen-data-gitignore.py` prints the data repo's `.gitignore` from the same two files. `_gc_trash/` is excluded (D-P0-03-2 = A): retired-skill originals are not published; history keeps what was already pushed.
- **Retraction.** `--exclude` shields a copy already in the data repo from `--delete`, so the former comment that an exclusion withdraws earlier publications was wrong. After the rsync, the names on the two lists are removed from the data repo. Governance files, `knowledge.json`, `.git/` and `.private/` are never touched.
- **rsync 3.x.** `scripts/lib-rsync.sh` resolves the rsync once for both scripts; a 3.x is preferred; with only macOS's openrsync the run continues after one WARNING line (the allowlist uses `/name/` + `/name/**`, which openrsync supports), and no rsync at all stops it with ERROR. The version line goes into the sync commit body.
- **Secret scan.** Before the commit, `git grep --cached` searches the index for the value shapes in `config/secret-patterns.txt` (no `api_key` / `Bearer ` words: other agents' text contains them). A hit unstages, names the files, and exits nonzero; a scan that cannot run also stops.
- **No force push.** The push is a plain `git push`; before the commit, the run checks that `origin/<branch>` is an ancestor of HEAD, so a diverged remote leaves no `sync:` commit and the watchdog row turns red. A commit made on the remote is no longer overwritten the next morning; a diverged remote is an ERROR and a nonzero exit. The data repo is edited only from the sync checkout, with the job unloaded.

Review-when: a second reader of `config/sync-excludes*.txt` appears, or the allowlist is split per audience (roadmap P2-05.1).

## Amendment (2026-10-24): derived files are generated in the export stage (P2-05.7, P2-05.8)

`pipeline/` and `skills/` in the data repo are `rsync --delete` mirrors of `MOLTBOOK_HOME`, so a file placed there by hand is deleted by the next sync. Two derived files are therefore regenerated after the rsync, in the same stage as `knowledge.json`:

- **`pipeline/value-layer/changes.json`** (+ `regime-candidates.json`) from `scripts/value_layer_change_series.py`, whose only input is the public `snapshots/` copy: the points where identity / constitution / rules / skills digests change, and the points where a manifest's Ollama version or weight digests change (candidates only; the sync never writes `pipeline/regimes.json`).
- **`skills/INDEX.md`** and **`pipeline/skills-index.json`** from `scripts/skills_index.py`: one row per live skill, plus name and date of each retired skill (`skills/.archive/` itself stays private). The script reads `logs/audit.jsonl` for timestamp, source and file name only.

A failure of either script prints a `WARNING:` and leaves the file absent; it does not stop the publish of the rest. Consumption plans are in each script's header (ADR-0101).

Review-when: `pipeline/` or `skills/` stops being a mirror (the files could then be hand-kept), or the final sync of the run sessions freezes both files.

## Amendment (2026-10-24): `history/` is public, and takedown `file:` entries are applied (P3-04, ADR-0127)

- **`history` joins `PUBLIC_TOP_LEVEL`.** Identity versions are kept under the top-level `history/identity/` (`core/value_history.py`), while the constitution's versions live under `constitution/history/`, which the allowlist already published. Publishing one and withholding the other was an accident of where the directory sits, not a decision. The owner decided on 2026-10-24 to publish it: the texts are adopted identity versions, which `identity.md` already publishes one at a time.
- **Takedown `file:` entries.** The sync reads `file:<rel/path>` from `config/takedown-suppressions.txt` and the private `$MOLTBOOK_HOME/takedown-suppressions.txt`. It excludes each path from the rsync (anchored, that path only) and removes it from the data repo after the retraction step, so `git add -A` stages the deletion. A malformed line, an absolute path, a `..` or `.` segment, a glob character, a path under `.git/` or `.private/`, or a hand-kept data-repo file stops the sync before anything is copied. The other entry kinds (`post:` / `name:` / `pattern:`) are validated here too, since a malformed line is malformed for every reader.

Review-when: a `history/` subdirectory other than `identity/` appears (decide its publication separately), or a takedown has to reach a hand-kept file (it is removed by hand under ADR-0127 Decision 5).

## Amendment (2026-10-31): two retired names leave the public tree, two generated files join it (P3-05.5, P1-04.7, P3-05.9, P2-05.2)

- **`patches/` and `ledger-watch/` join `config/sync-excludes-public.txt`.** `reports/analysis/patches/` holds the weekly patch proposals against the framework: framework code under MIT, not data (decision D-P3-05-4 = A). `pipeline/ledger-watch/` is the series retired with ADR-0095. Both stay in the home, so an exclusion is needed for the copy and the retraction step removes the copy the data repo already holds. The names are basenames, so a directory of either name anywhere in the tree is withheld; the data repo's `.gitignore` is regenerated from the list.
- **`reports/analysis/README.md` is hand-kept.** The rsync's unanchored `--exclude='README.md'` already shields a `README.md` at any depth from the copy and from `--delete`; the data repo keeps one there that lists the active and retired formats of that directory.
- **Two files are generated after the rsync, like `skills/INDEX.md`.** `pipeline/skill-names.json` (`scripts/skills_index.py --out-names`, P3-05.9) maps each skill file stem to its `name:`, for live and retired skills; no `name:` and no file is renamed. `pipeline/decisions/decisions.jsonl` (`scripts/decisions_projection.py`, P2-05.2, decision D-P2-05-2 = A) is `logs/audit.jsonl` without its bodies: the free-text `reason`, `epistemic_counts` and `prev` are never copied, paths are home-relative, and a path outside the home keeps only its file name. `logs/` itself stays unpublished.

Review-when: a second directory named `patches` or `ledger-watch` appears in the home and is meant to be public (anchor the pattern instead).
