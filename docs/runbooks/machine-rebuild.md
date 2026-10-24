# Machine rebuild

Bringing the unattended chain back on a new or reinstalled Mac. The order matters: each stage has a check and the stage after it assumes the check passed. Stop at the first mismatch. Facts that only the owner knows are marked `<owner to fill>`.

Companion documents: `docs/runbooks/runtime-backup-restore.md` (the data), `docs/runbooks/model-swap.md` (changing models), `docs/CONFIGURATION.md` ("Time zone, power and login", "Stopping everything").

| # | Stage | Do | Check and expected result |
|---|---|---|---|
| 1 | OS settings | FileVault off or a documented auto-login alternative, automatic login on, power: AC, "Install macOS updates automatically" off (see "Time zone, power and login") | `fdesetup status` prints `FileVault is Off.`; `sudo pmset -g` shows `sleep` and `disksleep` as intended; System Settings > Users shows the automatic login account |
| 2 | Homebrew tools | `brew install uv git gh coreutils rsync` (coreutils gives `gtimeout`; Homebrew rsync is the one the data sync is written against) | `command -v uv git gh gtimeout rsync` prints five paths; `rsync --version` runs |
| 3 | Ollama | Install by the route D-P1-07-3 = A fixed (the app), start it, `ollama pull gemma4:e4b` and `ollama pull nomic-embed-text` | `ollama list` shows both; the embedding model's digest equals the latest public snapshot manifest's `embedding_model_digest`. A mismatch stops the rebuild: follow `model-swap.md`. The manifest comparison is P1-07.12; until then compare by eye |
| 4 | Repository | `git clone git@github.com:shimo4228/contemplative-agent.git ~/MyAI_Lab/contemplative-agent && cd ~/MyAI_Lab/contemplative-agent && uv sync` | `.venv/bin/python -V` prints 3.13.x |
| 5 | `claude` and the private harness | install the CLI by its native installer (it lands in `~/.local/bin`, which the launchd PATH adds), sign in; the private harness (skills, hooks) is restored from its own repository per P2-03.1's table | `claude --version` prints a version |
| 6 | Data and backup repositories | clone `contemplative-agent-data` and the private `contemplative-agent-runtime-backup` beside the repository (same parent directory) | `git -C <repo> status` is clean on both |
| 7 | Credentials | re-issue or restore `credentials.json` from the store named in the restore runbook's drill section; never copy it through the backup repository | `contemplative-agent status` reports the account without printing the key |
| 8 | `MOLTBOOK_HOME` | follow `runtime-backup-restore.md` steps 1-6 | `scripts/restore-drill-check.sh --live <restored home>` is not applicable to a fresh home; check step 6 of that runbook instead (`contemplative-agent generate-report` runs end to end) |
| 9 | Schedules | run the production `install-schedule` line (P2-04.22: `<owner to fill: the full line, including --sync-data and --watchdog>`), then re-create the hand-managed `com.moltbook.ollama-restart` job from `config/launchd/` | `launchctl list \| grep -c com.moltbook` equals the declared count; `scripts/host_check.sh --expect-jobs <N>` is green |
| 10 | First day | leave it for one day; after the 04:30 watchdog run read `reports/PIPELINE-STATUS.md` | every row is OK or an understood SKIP; `Next check by:` is in the future |

`scripts/host_check.sh` prints stages 2-5 and 9 on one screen and exits 1 on a missing tool, a missing hang detector (`timeout`/`gtimeout`), a digest mismatch or a job-count mismatch. Run it at the end of a rebuild, after an OS, Homebrew, Ollama or Python update, and with each restore drill. The Ollama / model / home part waits for `contemplative-agent doctor` (P0-05.1).

After the next OS or Ollama update, run `scripts/host_check.sh` once and add one line to `docs/evidence/serving-changes.md` (owner, on the Mac).
