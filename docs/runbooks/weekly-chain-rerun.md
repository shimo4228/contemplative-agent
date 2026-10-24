# Weekly chain: missing report, mid-run death, re-run

What to do when the Saturday chain (`scripts/weekly-pipeline.sh`, ADR-0085 / ADR-0098) did not leave a report, died part-way, or has to be run again for the same week. Everything here is read off the script; if the script changes, change this page in the same commit.

Companion pages: `docs/CONFIGURATION.md` ("Stopping everything", the log-retention table), `docs/runbooks/machine-rebuild.md`, `docs/runbooks/model-swap.md`.

## 1. Find out which case it is

```bash
cat "$MOLTBOOK_HOME/reports/PIPELINE-STATUS.md"                       # the watchdog's rows
tail -40 "$MOLTBOOK_HOME/logs/weekly-pipeline-audit.jsonl"            # chain_start / stage_result / chain_end
ls "$MOLTBOOK_HOME/logs/weekly-pipeline/"                             # run directories, newest 12 kept
```

| What the audit shows | Meaning | Section |
|---|---|---|
| no `chain_start` for the week | the job did not start (login, power, plist) or another chain held the lock (`CHAIN_ALREADY_RUNNING`) | 2 |
| `chain_start` and no `chain_end` | the chain died or was killed mid-run | 3 |
| `stage=report result=fail reason=REPORT_SESSION_FAIL` or `REPORT_SESSION_ERROR` | the session exited non-zero, timed out (`PIPELINE_WEEKLY_TIMEOUT`, 5400 s) or returned `is_error` — the usual causes are an exhausted subscription window or a hung CLI | 4 |
| `reason=PREFLIGHT_TOOLSET_DRIFT` | the CLI no longer resolves the declared tool set; no session was spent | 5 |
| `chain_end` with `report=none`, reason `REPORT_ABSENT` | instruments-only run: the report stage was not requested | 6 |
| `chain_end` with `REPORT_SESSION_DENIED` | the session ran but was refused a tool call; the report may be thin | 4 |

## 2. The job did not start

Check `launchctl list | grep com.moltbook.weekly-pipeline`, then "Time zone, power and login" in `docs/CONFIGURATION.md`. A hand run is safe at any time — the single-instance lock turns a second chain into `CHAIN_ALREADY_RUNNING` and exit 0.

## 3. The chain died mid-run

Nothing was committed or pushed by the chain. What a death can leave behind:

- `reports/.private/` — the session's partial outputs (`weekly-<end>.md`, `-findings.md`, the staged ledger delta, `tasks-<end>/`). This is the **quarantine**: it is excluded from the public sync, and the canonical `reports/analysis/` files are only ever replaced after the structural gate. Leave it; the next run for the same week deletes the matching leftovers itself.
- `.pending` baseline files in `reports/analysis/` — promoted only after a complete report; the next run removes stale ones first.
- the lock — held by the open file description, so it goes away with the process.

Then run it again (section 7).

## 4. The session failed, timed out or was refused

1. Read the numbers the chain kept: `stage=report` in the audit has `is_error`, `denials`, `num_turns`, `duration_ms`, `models`. The session's stderr is in `logs/weekly-pipeline/<run_id>/weekly-session.log`. The envelope's text is deliberately not kept.
2. **Subscription exhausted or rate-limited:** wait for the window to reset, then re-run (section 7). Do not shorten the week.
3. **Timeout:** look at `materials_bytes` on the `stage=materials` row. The materials file is what the session has to read; `WEEKLY_PREV_COUNT` (default 1) sets how many previous reports it embeds. A run that timed out on a large input can be retried with the same input once; if it times out twice, run `WEEKLY_PREV_COUNT=0 ./scripts/weekly-pipeline.sh --end-date <date>` (the variable reaches the collector; no script edit).
4. **Denials:** a nonzero `denials` with a complete report is a reading to note at the gate, not a failure. A refused session with no report is the 2026-08-29 shape: check that the value-layer read paths in the script's permission block still match `references/diagnosis.md`.

## 5. Tool-set drift

`PREFLIGHT_TOOLSET_DRIFT` means `claude` no longer honours a name in `WEEKLY_TOOLS` (or adds one). Run `python3 scripts/claude_toolset_probe.py --tools "Read,Glob,Grep,Edit,Write,Skill"` to see `missing=` / `gained=`. Fix the names in `weekly-pipeline.sh` after reading the CLI's changelog; do not remove the preflight.

## 6. Instruments-only

`MOLTBOOK_PIPELINE_STAGES=valuelayer,deadcode,docsscan ./scripts/weekly-pipeline.sh --end-date <date>` runs the deterministic stages with no `claude` on the machine. Use it when the subscription is unavailable for the whole week: the gate still gets the value-layer reading, the dead-code and docs scans, and the document is simply absent (`REPORT_ABSENT`).

## 7. Re-run the same week

```bash
cd ~/MyAI_Lab/contemplative-agent
./scripts/weekly-pipeline.sh --end-date <the week's end date, YYYY-MM-DD>
```

`--end-date` pins the week; it also marks the run a backfill, which **skips the identity distill** (`IDENTITY_BACKFILL_SKIP`). What a second full run does to the week's artifacts:

| Artifact | Effect of a re-run |
|---|---|
| `reports/analysis/weekly-<end>.md` | replaced (the previous one is not kept; copy it aside first if the first attempt was complete) |
| `-findings.md` | an earlier one is moved to `.private/…superseded-<run_id>` |
| observation ledger | the new session proposes its own delta and the chain appends it (ids are never reused), so a week whose first attempt already landed its rows can carry the same observations twice. If the first attempt reached the ledger step (`stage=ledger result=ok` in the audit), do not run the session again — use `--skip-report` |
| draft RFCs | the new session files a new set into `rfcs/.inbox/` (untracked, unnumbered); a draft with the same slug as one already there is left in `reports/.private/tasks-<end>/`. Delete the duplicates from the inbox by hand before the Saturday gate runs `scripts/rfc_inbox.py adopt` |
| intake baselines | promoted only with the new complete report |

`--skip-report --end-date <date>` re-runs the instruments over the existing report and files nothing.

Record what you did in the gate's notes: the audit already shows two `chain_start` rows for the week, and `instr_sha12` / `model` on each tell a reader whether the two runs read the same instructions and used the same writer.
