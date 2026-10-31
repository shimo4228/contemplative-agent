# Credential inventory and rotation

Where every key this project touches lives, why they are plain files, and what
to do when one leaks. Policy context: [ADR-0007](../adr/0007-security-boundary-model.md)
(boundary model) and [ADR-0015](../adr/0015-one-external-adapter-per-agent.md)
(credentials never enter the LLM context -- pinned by `tests/test_credential_absence.py`).
Threat model: [docs/security/threat-model.md](../security/threat-model.md).

## Why plain 0600 files and not the OS keychain

The jobs that need the Moltbook key run unattended under launchd
(`com.moltbook.agent`, `com.moltbook.submolt-scan`). A keychain item needs an
unlocked login keychain or an interactive allow prompt; neither exists at 06:00
with nobody at the keyboard, so the job would stall or silently run without the
key. The key is therefore a `0600` file inside `$MOLTBOOK_HOME`
(`adapters/moltbook/auth.py::save_credentials`), with the `MOLTBOOK_API_KEY`
environment variable taking precedence for hand-run sessions. The cost is that
the file is only as safe as the account and the backups -- hence the inventory
below and the exclusions in `scripts/backup-runtime.sh` / `sync-research-data.sh`.

## Inventory (seven locations)

| # | Location | Holds | Who reads it | Leaves the machine? |
|---|---|---|---|---|
| 1 | `$MOLTBOOK_HOME/credentials.json` (0600) | Moltbook API key | the agent process (`load_credentials()`) | never: excluded from the private backup (`--exclude` + `rm -f`) and from the public data sync |
| 2 | `MOLTBOOK_API_KEY` environment variable | Moltbook API key | same loader, ahead of the file | only if exported into a shell/plist that is itself synced -- do not put it in a plist |
| 3 | `$MOLTBOOK_HOME/cloud.env` | provider key(s) for the optional cloud sibling | the cloud sibling at startup | never: `*.env` is excluded from the private backup (`--exclude` + post-transfer removal) and from the public data sync (`--exclude='*.env'`) |
| 4 | `~/.config/typesafe/api_key` | key for the research tool used by `evals/jev_arm.py` | that script, human-started | no (outside `$MOLTBOOK_HOME`) |
| 5 | Hugging Face token (`hf` login) | write scope used by `hf upload` in `sync-research-data.sh` | the sync script | token lives in the `hf` cache; a fine-grained token with repo read / write on the owner's repos only (no global scope) — the graph sync writes five other datasets with it |
| 6 | git credentials (credential helper / SSH key) | push access to the public data repo and the private backup repo | `git push` in the two sync/backup scripts | n/a |
| 7 | the private backup repo's **history** | any key that was ever mirrored: `cloud.env` was not excluded before this runbook's change, so a copy may exist in history | whoever can read the private repo | it is a private remote; treat any key that existed in `$MOLTBOOK_HOME` while the mirror ran as exposed to that repo's readers |

Which of these actually hold a live key on the production machine is a fact only
the owner's machine can answer (item 7 especially: `git -C <backup> log --all --oneline -- cloud.env`).
Checked on the production machine on 2026-10-31 (presence only; no value was
read or printed):

| # | Present on 2026-10-31 |
|---|---|
| 1 | yes, mode 0600 |
| 2 | no: not set in the login shell, and no launch agent plist or shell profile names it |
| 3 | no `cloud.env` (no `*.env` at all) in `$MOLTBOOK_HOME` |
| 4 | yes |
| 5 | yes, an `hf` token is cached; checked 2026-10-31 through `whoami` (value not read): fine-grained, `repo.content.read` / `repo.access.read` / `repo.write` on user shimo4228, no global scope |
| 6 | not inspected (the git host's settings) |
| 7 | no: none of the private backup repo's 22 commits (all refs) touches `cloud.env`, any `*.env` or `credentials.json` |

So the live keys sit in rows 1, 4, 5 and 6; row 7 holds no copy, so its step 3
below has nothing to clean.

## When a key leaks (or might have)

1. **Stop what uses it.** `contemplative-agent install-schedule --uninstall`
   (or unload the launchd jobs) so nothing keeps publishing with it.
2. **Rotate at the issuer** -- per location:
   - Moltbook key (1, 2): reissue availability depends on what the platform
     offers; the platform-spec reading ledger is the source (see P1-07.19 once
     present). If the platform cannot reissue, the only route is a **new
     registration** (`contemplative-agent register --name ...`) plus stopping the
     old agent. That is a one-way operation: it splits the platform identity
     and the relationships attached to it. It is decided by the owner at a
     Saturday gate (`gate_item`), never by a session on its own; record the
     date as input to the boundary table and the end-of-project review.
   - Provider keys (3): revoke and reissue in the provider console, then
     replace `cloud.env` (keep it 0600).
   - Research-tool key (4): reissue in that tool, replace the file (0600).
   - HF token (5): revoke at huggingface.co, create a fine-grained write token
     with repo write on the owner's datasets (the data sync and the graph sync both use it), `hf auth login`.
   - git credentials (6): revoke the token / deploy key at the git host and
     re-authenticate.
3. **Clean the copies.** For (7): if a key was ever in the mirror, rotating it
   (step 2) is the remedy; rewriting private history is optional hygiene, not a
   substitute.
4. **Verify absence.** `tests/test_credential_absence.py` and the backup tests
   (`tests/test_backup_runtime_shell.py`) pin that the key reaches neither the
   LLM context, logs, stdout nor the mirror; run them after any change to the
   loader or the backup script.
5. **Resume** (`install-schedule`), and note the rotation date in the weekly
   gate record.

## Review-when

- a new credential-bearing file or env var is introduced (add a row);
- the agent moves to a host with an unattended-capable secret store;
- the cloud sibling is unfrozen or removed (rows 3 and 7 change).
