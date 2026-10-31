# Serving changes

Every change to what serves the models (Ollama build, a model re-pull, a model swap) gets one line here, written by the person who made it ([docs/runbooks/model-swap.md](../runbooks/model-swap.md), section h). The weights' identity is the digest (first 12 hex of `ollama list`), not the tag. Consumed by: the Saturday gate when a drift scan or a canary flags a change; the regime boundary table (P3-02) copies from here. Retire this file when the project's final record is written (it then holds the last line).

| Date | Ollama before -> after | Model digests (generation / embedding) | Canary / `check` result | Note |
|---|---|---|---|---|
| 2026-09-20 | 0.30.11 -> 0.34.2 | c6eb396dbd59 / 0a109f422b47 (unchanged) | not run (no canary yet) | Recorded after the fact from the public snapshot manifests (`ollama_version`); the decision to update was not recorded (RFC-0044). |
| 2026-10-31 | 0.34.2 (unchanged; baseline, not a change) | not read (`ollama list` not run on this pass) | `scripts/host_check.sh` (no flags): macOS 27.0 (26A428), python3 3.14.3 (Homebrew), git 2.54.0, rsync 3.5.1, claude 2.1.316, gh 2.96.0, hf present, `timeout` present, production `.venv` Python 3.13.5, 8 `com.moltbook` jobs loaded; embed digest and doctor SKIP | Baseline for P2-04.23, taken before the next OS / Ollama update so the after-update pass has a row to compare against. Run from a worktree, so the script's own `.venv` row failed (the worktree has no `.venv`); the production `.venv/bin/python -V` was checked by hand. |
