# Wind-down Runbook

The order of steps for ending the observation run. **This runbook has no
trigger.** Whether and when to stop is decided by the owner in a review
session ([ADR-0080](../adr/0080-north-star-layered-end-state.md), Amendment
2026-10-24 — review events open a session; they never imply stopping). This
file only says *how*, in a fixed order, so that an ending is a designed
event and not only a forced one (machine failure, platform closure,
operator unavailability).

Nothing here is automated. Every external action (Zenodo, Software Heritage,
GitHub archive, Hugging Face, Moltbook) is performed by a human, described
here and never executed by a dry-run.

## How to read this file

- **Rev.** column: `R` = reversible (undone by re-running `install-schedule`
  or a plain `git revert`), `I` = irreversible (a published version, a
  deposited DOI, a revoked credential, a deleted copy).
- **Confirm** = a command whose output proves the step happened. Run it and
  write the date next to the step in the dry-run record (bottom of this
  file).
- Items marked *(planned)* point at a document or a script that the roadmap
  ([docs/plans/roadmap-2026-10/ROADMAP.md](../plans/roadmap-2026-10/ROADMAP.md))
  schedules and that may not exist yet; fill the link when it lands. Items
  marked *(inferred, unverified)* describe things outside this repository.
- Paths: `$MOLTBOOK_HOME` is `~/.config/moltbook` unless set; the data repo
  is `$DATA_REPO` (the clone `scripts/sync-research-data.sh` writes to).

## Decisions on record

| ID | Decision | Date |
|---|---|---|
| D-P4-02-1 | Moltbook account: leave it, freeze the identifiers, add a status word to the READMEs (option A below) | 2026-10-24 (owner, as recommended) |
| D-P4-01-2 | Moltbook closure ends the run; no porting, no SNS-side Protocol | 2026-10-24 (owner, as recommended) |
| D-P3-05-2 | Takedown policy: terms clause plus statutory exceptions, with a suppression list as the execution path (A + E) | 2026-10-24 (owner, as recommended) |
| D-P3-05-1 | Dataset versions: (a) per code minor release + pre-amend + final; (b) deposit copy with `**Context:**` replaced by a pointer | 2026-10-24 (owner, as recommended) |
| D-P1-11-1 / -2 / -3 / -6 | Siblings: cloud frozen, mlx frozen, otel frozen, rules kept until the bench dependency is gone | 2026-10-24 (owner, as recommended) |
| D-P4-02-2 | Whether the final tree restores snapshots that rotated out of `MAX_SNAPSHOTS` | **undecided** — waits for the final-size check (2027-Q2); see "Final snapshot checklist" |

## Order of steps

Execute top to bottom; do not reorder. A step is done only when its confirm
command has been run.

| # | Step | Rev. | Confirm (expected output) |
|---|---|---|---|
| 0 | Stop new sessions first: `launchctl unload ~/Library/LaunchAgents/com.moltbook.agent.plist` (the 6-hour `StartCalendarInterval` job; otherwise a new session can start between (1) and (2)). | R | `launchctl list \| grep com.moltbook.agent` prints nothing. |
| 1 | Final intake. Before the manual run, confirm that no `weekly-pipeline` run is in progress (`pgrep -f weekly-pipeline` prints nothing). Run the weekly chain once by hand (`scripts/weekly-pipeline.sh`), hold a last Saturday gate that adjudicates **every** staged item and writes one `gate_record` row with an end verdict, then `contemplative-agent distill`, `contemplative-agent sync-data`, `scripts/backup-runtime.sh`. | R for the schedules; the `gate_record` end row and the pushed `sync-data` commit stay (public, not undone) | Staged count is 0, counted the way the Saturday gate census counts it (`find "$MOLTBOOK_HOME/.staged" -name '*.meta.json' \| wc -l` prints `0`); `git -C "$DATA_REPO" log -1 --format=%cd` is today; the backup repo's last commit is today. |
| 2 | Stop every remaining scheduled job: `contemplative-agent install-schedule --uninstall`, which also removes the daily `sync-data` job (ADR-0114), then the hand-managed plist it does not own (`com.moltbook.ollama-restart`; see "Stopping everything" in `docs/CONFIGURATION.md`), then the off-repo jobs of "Periodic jobs outside the repository" below. | R | `launchctl list \| grep com.moltbook` prints nothing. |
| — | **ABORT LINE.** The schedules above are restored by re-running `contemplative-agent install-schedule` with the full flag set, `--sync-data` included (and `launchctl load` of the hand-managed `ollama-restart` plist); the step-1 `gate_record` end row and the pushed data sync are not undone, so an abort appends a superseding `gate_record` row stating that the end verdict is withdrawn. From step 3 on, the Zenodo deposit makes the ending public and cannot be taken back. Stop here if anything in steps 0-2 was surprising. | | |
| 3 | Final sync and deposit. (a) `contemplative-agent sync-data` once more. (b) Run the deposit-side items of the final snapshot checklist below. (c) Tag the data repo `final`. If D-P3-05-1 (b) deposits a curated copy (not the whole tree), the data repo's Zenodo–GitHub integration stays **off** — the owner confirms the toggle in the Zenodo/GitHub settings and notes the date in `releases.md` *(planned, P0-06)*; do not create a GitHub Release on the data repo. (d) Deposit following the release runbook step 8 *(planned, P0-06.6; whether the GitHub–Zenodo integration fires on a tag or only on a Release is external knowledge, unconfirmed)*. (e) Request a Software Heritage save of both repositories — only after the withdrawal reach table (P3-05.14, *planned*) has a confirmed date on every row. (f) Final Hugging Face upload of the data card and graph (`hf upload`, owner token). (g) GitHub archive of the data repo. | I | `git -C "$DATA_REPO" tag -l final` prints `final`; the Zenodo record URL and the SWH save request are written in `releases.md`; `gh repo view <owner>/contemplative-agent-data --json isArchived -q .isArchived` prints `true`. |
| 4 | Final release of this repository: the CHANGELOG gets an `Ending` section; README Status line, `CITATION.cff` version, `.zenodo.json`, `graph.jsonld` repo-state node, `llms.txt` / `llms-full.txt` are updated with the wording templates below; GitHub archive of this repository comes last. | I | `grep -cE 'ran 2026-03-07\.\.[0-9]{4}-[0-9]{2}-[0-9]{2}' README.md README.ja.md` prints `1` for each of the two files; `grep -c '^## \[Unreleased\]' CHANGELOG.md` is `0` or the section is empty. |
| 5 | Siblings: archive each one per the "Sibling repositories" table below; then add a dated note to the present-tense descriptions in the owner's sibling research repositories (agent-knowledge-cycle, agent-attribution-practice) — the write-back table of P3-06.7 *(planned; the AKC rows)* is the source. | I | Each sibling shows `isArchived` true in `gh repo view` (rules last, after the condition below). |
| 6 | Moltbook account: apply the option recorded under "Moltbook account disposition". | I | The READMEs carry the status word; `test ! -e "$MOLTBOOK_HOME/credentials.json"` once the plaintext key is removed (see the credential table). |
| 7 | Private records: final push of the private runtime backup, record where it is kept, move `takedown-requests.jsonl` into it (see "After the end"). | I | `scripts/backup-runtime.sh` exits 0 and the backup repo's last commit is today; `test ! -e "$MOLTBOOK_HOME/takedown-requests.jsonl"` after the move. |

Notes that apply to the whole order:

- Keep the local data-repo clone until the weekly chain has stopped for
  good: `scripts/weekly-analysis.sh` reads `git log --before=<date>` in
  `$DATA_REPO` to get a week's state diff, so the lookup is date-based and
  independent of commit SHAs.
- If the data repo's history is ever rewritten (for example the removal of
  `.bak` blobs, roadmap P0-03), run `scripts/weekly-analysis.sh` once
  afterwards and confirm the date lookup still resolves, before step 1.
- After step 2 a daily `sync-data` that is still scheduled would keep
  pushing. A failed push now exits 1 (P2-04), but a successful one is silent,
  so a leftover job is not noticed. The confirm in step 2 is the check.
- At no point is the agent asked to do anything: the stop is performed on
  the host, never through the agent's own I/O surface.

## Final snapshot checklist

What to fix before the immutable version is cut. Every line has a command
that can say yes or no. Run them in `$DATA_REPO` (unless noted) before step 3.

| # | Item | Check |
|---|---|---|
| 1 | No backup blobs in the tree (P0-03). | `ls knowledge.json.bak* 2>/dev/null` prints nothing. |
| 2 | Public text says what state the dataset is in. Live wording is allowed only on a line that also carries a state word. | `grep -rniE 'auto-synced\|daily\|live agent\|grows continuously' README* DATACARD.md llms.txt CITATION.cff NOTICE .zenodo.json` has no line without a state word (`ended`, `archived`, `frozen`). |
| 3 | The DATACARD volumes table equals the manifest aggregate (patterns, report days, snapshots, skills, period, model digests). The rule "do not write volatile volumes" is switched off for the final version only. | `python3 -I scripts/export-patterns-jsonl.py --describe` (planned, P3-05.4) matches the DATACARD table: `diff` is empty. |
| 4 | The regime table (P3-02, *planned*) lists every regime up to the end date. | `grep -c '^## ' DATACARD.md` equals the section count the DATACARD skeleton fixes (7 sections, P3-05.3 *planned*). |
| 5 | `llms.txt`, `CITATION.cff` `version`, `graph.jsonld` are regenerated for the final version. | `grep '^version' CITATION.cff` equals the final git tag; `python3 -c 'import json;json.load(open("graph.jsonld"))'` exits 0. |
| 6 | DATACARD carries `status: archived (ended YYYY-MM-DD)` and a Maintenance section; the HF card says "frozen as of `YYYY-MM-DD`". | `grep -n 'status: archived' DATACARD.md` prints one line. |
| 7 | `takedown-requests.jsonl` has no undecided row (the intake ledger of P3-05.14, *planned*). | `jq -s '[.[] \| select(.decision == null)] \| length' "$MOLTBOOK_HOME/takedown-requests.jsonl"` prints `0` (the file may be absent: then nothing was received). |
| 8 | The snapshot window — see below. | `ls snapshots \| wc -l` and `du -sh snapshots` recorded in the dry-run record. |

Items 2 and 7 must be true **before** the deposit of step 3 (the final
Zenodo record is immutable). The ones after can be satisfied in the same
sitting.

**Snapshot window (undecided, D-P4-02-2).** `core/snapshot.py` rotates
snapshots (`MAX_SNAPSHOTS`); snapshots that rotated out
exist only in git history and in earlier Zenodo versions, and a release zip
holds only the tree. The final version either leaves that as it is or
restores them. Three alternatives, to be decided with the final-size check
(2027-Q2):

- **A** — do not restore; history and the earlier Zenodo versions keep them.
- **B** — restore every snapshot from git history into the tree. The
  recommendation is B *with a size check*: measure first with
  `git -C "$DATA_REPO" log --diff-filter=A --name-only --format= -- snapshots | sort -u | wc -l`
  and the summed blob size; the number of files and the megabytes are
  unmeasured as of this writing (the clones used to draft this were shallow).
- **C** — restore an extract (for example one per month).

Until the owner records the choice, write the DATACARD sentence in the form
that is true under all three: "Snapshots present in this tree are listed in
`snapshots/`; earlier ones are in the git history of the repository."

## Moltbook account disposition

The agent's account is not deleted by this procedure. Three options; the
owner chose **A** (D-P4-02-1, 2026-10-24, as recommended).

| Option | What happens | Why / why not |
|---|---|---|
| **A. Leave and freeze identifiers** (chosen) | No post, no deletion. The account name and URLs stay as the public record; the READMEs say the run ended. | Matches observation over steering (no last intervention on the observed system) and keeps the public record = the account URL consistent. |
| B. One closing post under a human name | A human posts "ended" once. | Crosses the line that a human speaks in the agent's name. |
| C. Ask the platform to delete the account | A request to the platform. | Depends on a third party's terms and a deletion route the client never calls (`grep -rniE 'deregister\|delete-account' src` is empty); whether the platform offers one is not known from this repository — it is checked in the human re-reading ledger of the platform specification (`docs/evidence/moltbook-platform-readings.md`, P1-07.19, *planned*): add one dated row, with a digest, at stop time and cite that row here. This runbook does not tell the reader to re-read the specification themselves. |

Wording for the three README surfaces that say the agent is live (this
repository's `README.md` and `README.ja.md`, the data repository's
`README.md`): replace "Live agent on Moltbook" by a form with a state word,
for example "Ended on Moltbook (ran 2026-03-07..YYYY-MM-DD; the account is
left as it was)". Record the final form after step 6.

## Wording for the ended state

**Repository (EN)** — README Status line:

> Status: ended (ran 2026-03-07..YYYY-MM-DD). One instance ran; the last
> release is vX.Y.Z. This repository is archived and read-only. After the end,
> requests about third-party text in the dataset are received only at the
> contact alias in the repository's NOTICE, and are handled on a best-effort
> basis.

**Repository (JA)** — README.ja.md Status 行:

> 状態: 終了 (ran 2026-03-07..YYYY-MM-DD)。稼働インスタンスは 1 つだった。最終
> リリースは vX.Y.Z。このリポジトリは archive 済みで読み取り専用。終了後の、データ
> セットに含まれる第三者の文章についての連絡は NOTICE の連絡先 alias のみで受け付け、
> 対応は best-effort。

The period form `ran 2026-03-07..YYYY-MM-DD` must appear once per README
language (the confirm command of step 4 matches it); keep it
in that form (it is the one literal the templates and the check share).

**Surfaces outside the repositories** (one line each, done by the owner):
the profile repository that `.zenodo.json` names in `isPartOf`, the
published articles linked from the README, and the two Hugging Face cards.

## Sibling repositories

GitHub archive, one row each. The `Frozen as of contemplative-agent vX.Y.Z`
status line in each sibling README is owned by the sibling-sync item of the
roadmap (P1-11.1), not by this runbook.

| Repository | Operation | Condition |
|---|---|---|
| `contemplative-agent-otel` | Archive. | Frozen at the v2.10.0 schema (D-P1-11-3). Nothing else depends on it. |
| `contemplative-agent-cloud` | Archive. | Frozen (D-P1-11-1); archive after the last conformance run is recorded. Do not archive while any run still uses it. |
| `contemplative-agent-mlx` | Archive. | Frozen until the ADR-0067 reversal thresholds are met (D-P1-11-2); at the end of the run, archive. |
| `contemplative-agent-rules` | Archive **last**. | Only after this repository has retired `amend-constitution` (after step 4), or after the IPD bench has been vendored here (D-P1-11-6 B). `scripts/ipd-two-arm.sh` defaults to the rules repository's bench and the constitution-amendment approval requires the bench, so archiving earlier would leave the last amendment without its instrument. The clause text stays verbatim (rules ADR-0002); the README gets one line: the live instance's constitution was amended (data repository). |

## Credentials and keys

One table. "When" is the step number. P1-10.9 (the credential-rotation
runbook, *planned*) is expected to hold the rotation procedure for the same
locations and should link here.

| # | Location | Action | When | Reason | Check |
|---|---|---|---|---|---|
| 1 | `$MOLTBOOK_HOME/credentials.json` (plaintext, mode 0600) | Delete the file | 6 | Removes the live key from disk; the account is frozen, not deleted (D-P4-02-1 A). | `test ! -e "$MOLTBOOK_HOME/credentials.json"` |
| 2 | `MOLTBOOK_API_KEY` in the environment (shell profile, launchd plist) | Remove | 6 | Takes priority over the file; a leftover would still authenticate. | `launchctl getenv MOLTBOOK_API_KEY` and `env \| grep -c MOLTBOOK_API_KEY` print nothing / 0 |
| 3 | Sealed copy of the Moltbook key in the password manager | **Keep** until the takedown-alias expiry date, then destroy and record the date | 7 / expiry | The platform cannot re-issue a key; destroying it early permanently removes the ability to respond to a takedown on the platform side. The destruction date equals the alias expiry date (see "After the end"). | A dated line in the Ending section of the CHANGELOG |
| 4 | `$MOLTBOOK_HOME/cloud.env` (provider keys of the cloud backend) | Revoke at the provider, delete the file | after 2 | Frozen sibling; no job uses it after step 2. | `test ! -e "$MOLTBOOK_HOME/cloud.env"`; provider console shows the key revoked (date noted) |
| 5 | The hosted-judge key used by the lab evaluation (`TYPESAFE_API_KEY` or `~/.config/typesafe/api_key`) | Revoke, delete | after 2 | Experiment-only credential. | `test ! -e ~/.config/typesafe/api_key` |
| 6 | Hugging Face token | **Keep** until the alias expiry date; narrow its scope to the dataset repositories if it is not dedicated to this project, then revoke | 3(f) / expiry | A takedown after the archive may need a direct deletion on Hugging Face. | Token page shows scope and date |
| 7 | GitHub push credential (SSH key / token) | **Keep** until the alias expiry date; remove the scope for this project's repositories if it is not dedicated | 3(g) / expiry | Executing a takedown after the archive means unarchive, remove, re-archive. | Settings page checked, date noted |
| 8 | Zenodo–GitHub integration | Toggle **off** for the data repository once the deposit is done (already off if D-P3-05-1 (b) deposits a curated copy: confirm only) | 3(d) | A later tag or Release would otherwise create a new, unreviewed version. | GitHub Settings → Applications lists no active integration for the repository; date noted |
| 9 | Hugging Face write scope | Same token as row 6 | expiry | — | — |

Rows 6 and 7 follow the single retention date; do not set another date.

## Periodic jobs outside the repository

*(inferred, unverified — these live in the owner's `~/.claude` harness and
are described here from the repository's own documents: ADR-0098,
`scripts/weekly-pipeline.sh` header, `CLAUDE.md`.)* Add to step 2:

| Job | Stop | Confirm |
|---|---|---|
| The harness `triage-ca` registration (Wednesday 17:07 / Saturday 14:07 ticks that judge `rfcs/` and dispatch worktree sessions) | Remove this project from the harness tick list. | After the next tick time, `git log --since=<tick time>` and the `rfcs/` file mtimes show no change. |
| `claims.py` tasks for this project | Close or hand over each open claim. | `python3 ~/.claude/scripts/claims.py ready` has no line for this project. |
| The graph mirror to Hugging Face (harness skill `jsonld-knowledge-graph`, Mirror Sync) | Remove this repository from the mirror targets. | The skill's target list does not name it. |

`contemplative-agent install-schedule --uninstall` only removes the managed
`com.moltbook.*` plists (`src/contemplative_agent/cli/schedule.py`), so none
of these three is touched by it.

## After the end

- **Contact route.** The contact alias in NOTICE stays alive until the
  expiry date **`<owner to decide: alias lifetime>`**. That date is also the
  destruction date of credential rows 3, 6, 7 and 9. The ended-state wording
  above says reception is by that alias only and best-effort.
- **Execution of a takedown after the archive.** GitHub: unarchive → remove
  the text in a commit → archive again. Hugging Face: delete directly. Zenodo:
  follow the row of the reach table (P3-05.14, *planned*) — an immutable
  version may not be editable; what is possible is a metadata/notice
  amendment or a request to Zenodo. Whether GitHub advisories can still be
  received on an archived repository is external knowledge, unverified.
- **Ledger.** `takedown-requests.jsonl` is moved at step 7 into the private
  backup repository.
- **Private backup retention.** The private runtime backup is the only
  off-machine copy of the raw episode logs; deleting it makes any re-analysis
  of private rows impossible for good. Retention period and the action at
  expiry (delete the repository) are decided by the owner as a `gate_item`
  **`<owner to decide: backup retention>`**, and the date is written in the
  CHANGELOG Ending section. Before deciding, check the `reanalysis:` column of
  the longitudinal-record plan (P3-01.1, *planned*, values `private-rows` |
  `rerun-local`) and state in one line how long after the paper cutoff a
  re-verification request could come.

## Dry-run record

Not run yet. A dry-run executes each step's confirm command and times it; it
does **not** perform the external actions of steps 3-6 (`final` tag, Zenodo,
Software Heritage, Hugging Face upload, GitHub archive, the final release,
sibling archive, Moltbook disposition) and does not unload launchd.

| Date | Operator | Steps timed | Notes |
|---|---|---|---|
| — | — | — | — |

## Open items

- Dry-run on the production machine: launchd timings, `weekly-analysis.sh`
  after any history rewrite (owner, on the Mac, 2027-Q1).
- D-P4-02-2 (snapshot window) — undecided.
- `<owner to decide: alias lifetime>`, `<owner to decide: backup retention>`.
- Links to fill when they exist: full-stop schedule section (P2-04.3),
  release runbook step 8 (P0-06.6), reach table (P3-05.14), credential
  rotation runbook (P1-10.9), AKC write-back rows (P3-06.7), re-reading
  ledger (P1-07.19), `reanalysis:` column (P3-01.1).
