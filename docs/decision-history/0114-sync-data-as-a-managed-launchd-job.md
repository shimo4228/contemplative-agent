# ADR-0114: The Public Research-Data Sync Is a Managed Launchd Job

## Status

accepted — partially-supersedes ADR-0010 (Sync Timing: "a post-processing step of the distill command, no launchd plist")

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session
decided-by: owner (D-P2-04-1 = A, 2026-10-24)
date: 2026-10-24

## Layer

mechanism

## Context

ADR-0010 said the sync "runs as a post-processing step of the distill command. No additional launchd plist required." That stopped being true on 2026-03-28 (the distill hook was removed, commit `14b833d`). Since then the data repo has received one `sync:` commit a day at 05:30 JST from a launchd job, `com.moltbook.sync-data`, that was installed by hand. `install-schedule` did not know it: a full stop (`--uninstall`) left it running, a re-install did not restore it, the watchdog's `sync-data` row said "installed by hand", and ADR-0010 still described a mechanism that no longer existed. The 2026-10-15 note on ADR-0010 recorded the drift without fixing it.

## Decision

D-P2-04-1 = A (owner, 2026-10-24): the daily launchd job is the path, and the installer owns it.

1. `config/launchd/com.moltbook.sync-data.plist` runs `contemplative-agent sync-data` daily at 05:30 (after the 03:30 distill, between the 00:00 and 06:00 agent sessions, which is what the watchdog row anchors to). The time is fixed in the template, like the watchdog's.
2. `install-schedule --sync-data` installs it. Like every optional job the installer is declarative: a run without the flag removes an installed sync-data job, and `--uninstall` removes it. An existing hand-installed job is therefore replaced by the managed one on the next `install-schedule ... --sync-data` run, and removed by one that omits the flag.
3. The sync runs independent of distill's success. A failed sync exits nonzero (`cli/session_cmds.py::_run_sync`, P2-04.2), so launchd records it, and the watchdog's `sync-data` row is the independent check that a commit landed.
4. What is published is the script's, not the installer's: `scripts/sync-research-data.sh` is the table of record for targets and exclusions. This ADR does not change the public scope.
5. Public surface (D-P2-05-1 = C, owner, 2026-10-24): the data repo is two tiers, a mirror tier the script copies mechanically and a hand-kept tier (`DATACARD.md`, `README*.md`, `llms.txt`, `graph.jsonld`, `CITATION.cff`) that the rsync excludes and never overwrites, with a scan before each commit as the last barrier (the home-path gate). The per-file exclusion table and the move of any exclusion to an allowlist are P2-05.1 / P0-03 work and change the script, not this decision.

ADR-0010's Sync Targets and Exclusions sections stand; only its Sync Timing is superseded.

## Review-when

- The sync moves off launchd (a different scheduler, or a hosted job).
- `install-schedule` stops being the one declarative installer.

### Consumption plan (ADR-0101)

This ADR adds no instrument; it moves an existing job under the installer. The reader of its health is unchanged: the watchdog's `sync-data` row, read by the Saturday gate's Step 0(c).

## Consequences

- A full stop is `install-schedule --uninstall` plus the `launchctl list | grep com.moltbook` check; sync-data no longer needs a manual step (docs/CONFIGURATION.md, "Stopping everything").
- The one-time migration for the existing machine: first copy the live hand-made plist aside (`cp ~/Library/LaunchAgents/com.moltbook.sync-data.plist ~/sync-data.plist.hand`; the installer removes or overwrites it and its content is not in the repo), then run `install-schedule` with the full desired set plus `--sync-data`, then diff the copy against the installed plist before the next 05:30 run, especially `EnvironmentVariables`: the template's PATH puts `/opt/homebrew/bin` before `/usr/bin`, so `rsync`, `git`, `hf` and a credential helper may resolve to different binaries than the hand plist used. Confirm that the next 05:30 `sync:` commit lands. Omitting the flag on a later run would remove the job, so the flag belongs in whatever line the owner treats as the production declaration (P2-04.22).
