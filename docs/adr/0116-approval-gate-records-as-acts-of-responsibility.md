# ADR-0116: Approval-Gate Records as Acts of Responsibility

## Status

accepted — partially-supersedes ADR-0012 (Alternative 1's rejection reason, the "when Claude Code is the orchestrator" attention note, and the audit record's field set; the gate itself, "no `--auto`", the decision table and the flow stand)

## Date

2026-10-24

## Decided by

proposed-by: Claude Code session
decided-by: owner (D-P1-12-1 = A, D-P1-12-2 = B, 2026-10-24)
date: 2026-10-24

## Layer

mechanism

## Context

ADR-0012 made the human approval gate structural and ADR-0080's 2026-08-26 addendum named the human word at that gate as the anchor of attribution. The record the gate leaves did not carry that word. The 2026-10 roadmap review (P1-12) found five gaps between what the project says and what `audit.jsonl` holds:

1. A row says *that* something was approved or rejected, not **who** did it, **why**, or **through which door**. `approve`, `--adopt-names`, `--reject-names` and `--yes` all produce rows that differ only in the free `source` string.
2. `adopt-staged --yes` (source `stage-adopted-auto`) was documented as "used by non-TTY coding-agent workflows" — the code encoded the very path ADR-0012's Alternative 1 had rejected ("`--auto` … Claude Code can read results and make an approval decision"), and ADR-0012's own attention note ("when Claude Code is the orchestrator, the approval flow needs consideration") stayed open. Two constitution amendments were adopted that way, with no reason on the record.
3. A rejection `unlink`ed the staged text. The only trace of what a human said no to was a 16-hex hash (the README counts 547 rejected skill proposals as primary data).
4. The adopt and reject paths ignored a failed audit write ("log-and-continue"): an adoption could land in the store with nothing on the record and the process exiting 0.
5. `path` was an absolute path of whatever machine wrote it; two rows name a path that never held the approved bytes; the staged rows carried no key to the snapshot of the run that generated the candidate, so a decision could not be tied back to its run from public files.

The Accountable-AI-practice work that cites this repository as its worked example (its ADR-0005, -0006 and -0008) assumes exactly the record this ADR provides: a named human approver and a timestamp, a reason for every rejection, and an audit record that is "non-negotiable".

## Decision

### D1. `--yes` is a stand-in for the TTY answer, and it carries the human's reason (D-P1-12-1 = A, owner, 2026-10-24)

`adopt-staged --yes` requires `--reason TEXT` (exit 2 before anything is touched otherwise). It is typed only in a session where a human is present and has read the batch; the reason is that human's words. **Claude Code is the explainer and the transcriber, not the approver** (weekly-gate Step 1b; ADR-0085, ADR-0098). The `cli/approval.py` docstring that described `stage-adopted-auto` as a coding-agent path is replaced accordingly. ADR-0012's Alternative 1 stands as rejected for the reason it gave only in part: an automatic skip is still not offered; a blanket `--yes` is offered because the gate is a human's act and the record now says so.

### D2. Row fields

`_log_decision` (the single owner of the row shape) writes, on every row, five more keys beside the existing ones:

| key | meaning |
|---|---|
| `reason` | the human's free-text reason (required for `--yes`, `remove-skill`, and any names-file line that carries one) |
| `reason_code` | enum `duplicate \| off-constitution \| low-quality \| stale \| other` — **required for every rejection** taken without a prompt (a code on the names-file line, or `--reason-code`); a decline at a terminal prompt asks for it |
| `channel` | `tty \| names-file \| yes-flag \| headless` — derived from `source` unless the call site overrides it |
| `session` | the session the decision was taken in (`CLAUDE_CODE_SESSION_ID` / `MOLTBOOK_GATE_SESSION` / `--session`), null when none is available |
| `approver` | the human who decided; see D3 |

`path` is recorded relative to `MOLTBOOK_HOME` when the target is inside it, absolute otherwise; `snapshot_path` likewise. The join key between rows, files and gate records is `content_hash`; `path` is a reference only. `held` stays in the schema as a historical decision value.

`AuditSource` gains `correction` (D6). A planned `takedown` source (the suppression-list application of P3-05.14, carrying an approver) is **not** added until the writer for it exists; the schema's enum equals the code's, enforced by a test.

### D3. The approver is a human's string, never a constant (D-P1-12-2 = B, owner, 2026-10-24)

A names FILE may begin with a signature line, `# approver: <name>`; `--approver NAME` says the same, and the two must agree (otherwise exit 2). `MOLTBOOK_OPERATOR` in the environment is an override for a second named human, not a source of truth. Nothing in the code fills in a default name: a fixed environment value would read the same whoever typed the command. The registered names live in `docs/GOVERNANCE.md` (the *Accountable operator* line, plus any `Registered approver:` lines). The weekly `gate_item` events carry the same `content_hash` and `approver`, so one human string reaches both the audit row and the gate record.

The names-file grammar is `name<TAB>reason_code<TAB>free text`, columns 2 and 3 optional (`-` or empty means none). Files written before the columns existed still parse.

### D4. A rejected body is kept

Every reject path (named, swept by `--reject-rest`, declined at the prompt, and the direct non-staged prompts) keeps the text under `MOLTBOOK_HOME/.rejected/<UTC ts>-<content_hash>.md` (mode 0600). The `adopt-staged` paths keep it **before** the row is written; the direct non-staged prompt paths (insight / distill-identity / amend-constitution without `--stage`) write the row first and keep the text after, best effort. The file name carries the audit row's `content_hash`, computed by the same function, so the row leads to the file; constitution and identity candidates are covered by the same path. The directory is excluded from the public sync (`sync-research-data.sh`) and is carried by the private runtime backup. Whether any of it is ever published is a separate decision (P2-05).

### D5. No record, no decision

On the `adopt-staged` adopt and reject paths, `_log_decision` returning false is no longer ignored. (The direct non-staged prompt paths log first and ignore a failed write; they are interactive, not unattended.) An adoption whose row did not reach disk is **not performed** — the store is untouched, the staged item stays, the run exits 1. A rejection puts its item back if its row fails (and removes the kept copy), and a rejection whose text could not be kept does not proceed. The earlier ordering note — "unlink before logging", so a row never claims a rejection of an item still staged — is preserved.

### D6. Integrity model and corrections

`audit.jsonl` is append-only (`O_APPEND`, umask 0177 → mode 0600), is not rotated, and is part of the weekly private backup (a git history). The tamper-evidence surface is the `prev` hash chain (ADR-0012 2026-10-09 note) — an edited, deleted or reordered row breaks the link after it; what it does not detect (a full rewrite by whoever holds the file, rows cut at the tail) stays as that note states, and the earlier line "git history only" is superseded by it. `content_hash` is an identifier, not a signature.

Because the log is append-only, a repair of a wrong `path` is a new row: `command: correction`, `decision: corrected`, `source: correction`, with `corrects_ts`, `mv_from`, `mv_to`, `sha_checked` (the live file's digest, verified equal to the corrected row's `content_hash`) and the `approver` who made the repair. `scripts/audit_correction.py` writes it (dry run by default; refuses when the hash does not match) so it carries the chain link like any row. The two known cases are the 2026-08-09 constitution and the 2026-08-15 identity adoptions (ADR-0090, ADR-0091). `scripts/value_layer_approval_join.py` treats a correction as a note, not a decision, and leaves the corrected row out of its approved-but-not-live check.

The schema is `schemas/audit.schema.json`; `tests/test_audit_schema.py` runs rows from every real writer path against it, so a new source or key without a schema change fails CI.

### D7. Snapshots are reachable from the decision

The producer's pivot snapshot is written to the staged item's `.meta.json` as `snapshot` and copied to `snapshot_path` on the `stage` row and on every adopt / reject row. The join rule lives in the schema (`x-join`): adoption row → stage row by `content_hash`; stage row → snapshot by `snapshot_path`, else `run_id` against the manifest, else a timestamp neighbourhood marked *inferred*. `scripts/snapshot_resolve.py` walks it over public files only and prints versions whose snapshot has been pruned as `rotated`.

## Review-when

- The first Saturday gate after this lands has a `--yes` adoption without a human present, or an `approver` that is not a registered name: the gate is being operated against D1/D3 and the process, not the code, needs the fix.
- Four consecutive weekly readings show no missing or unregistered approver and `gate_item` rows all resolve: stop reading the approver line weekly (see below).
- A second human approver is appointed (P4-03.2): D3's registry and the signature line need a handover row, and `--yes`'s "a human is present" needs a second look.
- The data repo gains a decisions projection (P2-05.2): `snapshot_resolve.py` reads it directly and the join rule in the schema is re-checked against it.

### Consumption plan

Three readings were added; each states its own plan in its header (ADR-0101).

- **Approver line** in `value_layer_approval_join.py` — read by the weekly report once a week; after four clean weekly readings the report drops the line and the schema/test check carries it; retire with the field.
- **`scripts/gate_item_audit_join.py`** — the gate session runs it once per Saturday after Step 7; four clean weeks stop the manual run; retire when `gate_item` stops carrying `content_hash`.
- **`scripts/snapshot_resolve.py`** — read when a reproduction guide or RCA must name the version a decision applied to; the count of `rotated` versions decides whether snapshot retention changes (P3-04.1); remove from the weekly path after eight weeks with no new `rotated`, keep as a release gate.

## Alternatives Considered

1. **`--yes` becomes sugar for a full `--adopt-names` list** (D-P1-12-1 option B). Rejected: the constitution runbook's step 4 and every "adopt the whole batch" week would need a list that only restates the staging directory.
2. **Keep `--yes` as "a supervised coding-agent session's TTY substitute" and write the exception into the accountability practice** (option C). Rejected: it records the agent as the approver the practice says it is not.
3. **A fixed `approver` from an environment variable** (D-P1-12-2 option C). Rejected: whoever types the command writes the same string; it records a configuration, not an act.
4. **The human types every gate command themselves** (option A). Not required: the signature line gives the same human-origin string without moving the typing to a person who has already read the batch.
5. **Roll back an adoption when its row fails.** Rejected as worse than not starting: a rolled-back audited write is itself an unaudited mutation. The row is written first and the write follows it.
6. **Move `.rejected/` into the public sync now.** Deferred to P2-05; the directory holds text a human declined, and publishing it is its own disclosure decision.

## Consequences

### Positive

- A row reads as an act: a named human, a reason in their words, the door it came through, the session that transcribed it.
- A rejection is recoverable and findable by `content_hash`; the 547-rejection dataset stops losing its text.
- An adoption without a record cannot happen; the exit code says so.
- The schema is checked in CI against what the writers emit.

### Negative

- The gate asks for a little more: a reason on `--yes`, a code on every non-prompt rejection. Bare `--reject-names` files written before this fail with exit 2 until a code is given.
- `approver` is the human's claim, not a cryptographic one; the hash chain detects edits, not who typed.
- Rows before 2026-10-24 keep absolute paths and lack the new keys; readers must keep tolerating that.

### Reversal cost

Low for D2–D5 (keys are additive; a reader that ignores them still works). D1 is a CLI contract: reverting `--reason` makes `--yes` silent again.

## References

- `ADR-0012` (`0012-human-approval-gate.md`) — partially superseded by this ADR.
- `ADR-0080` (`0080-north-star-layered-end-state.md`) — the 2026-08-26 addendum names the human word at the gate as the attribution anchor.
- `ADR-0085`, `ADR-0098` — the Saturday gate; Claude Code as explainer.
- `ADR-0090`, `ADR-0091` — the two hand-repaired adoptions D6 records.
- `ADR-0097` (D5) — the archive exit whose reversibility D4 copies.
- `ADR-0101` — consumption plans for the readings above.
- `ADR-0020` — pivot snapshots (D7).
- `docs/GOVERNANCE.md` — roles, the registered approver, where each record lives.
