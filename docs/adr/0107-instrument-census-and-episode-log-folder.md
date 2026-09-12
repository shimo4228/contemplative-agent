# ADR-0107: Every Self-Written Log Gets a Reader — Instrument Census, Phase 0 Read-Through, and the Episode-Log Folder

## Status

accepted

## Date

2026-09-12

## Context

RFC-0032 (the same post scored by the LLM ~10 times per session, its full text
re-fetched and an internal note regenerated each time) was found on 2026-09-12
by a code review, six months after the behaviour began. The evidence had been
on disk from the first day: `core/llm/__init__.py:emit_llm_telemetry` writes one
row per LLM call to `logs/llm-calls-{date}.jsonl` with `caller`, a prompt
digest and — via `_io.append_jsonl_restricted` — `session_id`. Counting rows
per (session, caller, digest) would have shown the repeat in week one. No
stage of the weekly chain read that file.

An inventory of `$MOLTBOOK_HOME/logs/` on 2026-09-12 (writer → readers, from
code) found the shape was general, not one file:

| Readers | Files |
|---|---|
| zero automated readers | `llm-calls-*`, `constitution-shadow`, `injection-detect-*`, `verification-audit`, `weekly-pipeline-audit`, `pipeline-metrics` |
| manual scripts only, outside the chain | `insight-novelty`, `insight-staged`, `submolt-scope-*` |
| writer retired, file still on disk | `insight-worth.jsonl` (ADR-0097), `noise-*.jsonl` (ADR-0060) |
| read weekly | `audit.jsonl`, `api-audit.jsonl`, `skill-selection-*`, `comment-outcomes`, `*.log`, episode logs (hash projection only, ADR-0083) |

Two structural causes, not one missing instrument:

1. **Every weekly reading answers a question decided in advance.** The seven
   intakes (anomaly sweep, API drift, state invariants, cross-day duplicates,
   skill selection, never-selected, confusion pairs) each encode a failure
   class someone had already imagined. The observation document (RFC-0010)
   admits only deviations from a declared baseline or deterministic-instrument
   signal. A repeated *valid* call raises no warning, breaks no invariant, and
   is not a baseline anyone declared — it is invisible to a system that only
   asks known questions. There was no step where the LLM reads raw-ish data
   with no question attached.
2. **The prohibition on reading episode logs had the wrong radius.** Episode
   logs (`YYYY-MM-DD.jsonl`, raw text authored by other agents) sat directly in
   `logs/` beside fourteen self-written files. The Bash guard in
   `~/.claude/hooks/_episode-log-common.sh` therefore blocked every glob under
   `logs/` — including the operator's own aggregate over `llm-calls-*.jsonl`
   while investigating this very bug. A boundary drawn as a filename regex
   over a mixed directory teaches "do not look in logs/" rather than "do not
   read other agents' text".

A third fact surfaced while building the reader: `prompt_sha256` is a digest of
the *raw* prompt, and every wrapped call carries a fresh delimiter nonce
(`secrets.token_hex`, `guard.py`), so two calls over the same post body never
share a digest. A census over the week before the RFC-0032 fix read **0
repeats**. Telemetry recorded that a call happened but could not say it had
happened before (ADR-0089 §968 had noted the drift for eval replay).

## Decision

1. **Episode logs move to `logs/episodes/`.** `adapters/moltbook/config.py`
   gains `EPISODES_DIR = EPISODE_LOG_DIR / "episodes"`; `EpisodeLog` and the
   report generator are constructed on it (six call sites). `EPISODE_LOG_DIR`
   keeps its name and remains the directory of self-written telemetry. The
   weekly session's deny becomes the folder `Read(/$MOLTBOOK_HOME/logs/episodes/**)`,
   the duplicate scan's `--log-dir` follows, and the harness guard's predicate
   becomes "date-named `.jsonl*` directly under a directory named `episodes`";
   its Bash glob rule narrows from `/logs/…*` to `/episodes/…*`. The 225
   existing files (190 day files, 9 `.bak`, 26 `.pre-cleanup.bak`) were moved
   once on 2026-09-12, counts verified, nothing deleted. What is protected is
   now one folder; everything one level up is readable.
2. **A registry-driven census is the reader of last resort**
   (`scripts/instrument_census.py`, read-only, stdlib). `REGISTRY` holds one row
   per self-written log: glob, owner ADR, `live` / `writer_retired`, the enum
   and numeric fields to distribute, an optional within-session
   `redundancy_key`, and optional heartbeat `expect_events`. The row *is* the
   weekly question for that file. Output, in order: a census table with a
   closed status vocabulary — `OK`, `NO_ROWS` (live, no rows in window),
   `MISSING_EVENT`, `ORPHAN` (retired writer, file present), `UNKNOWN` (file
   present, no row), `ABSENT`; distributions; redundancy (same key inside one
   `session_id`; repeats across sessions are legitimate); and a deterministic,
   body-stripped projection sample per log plus the longest session's `caller`
   run-length sequence. The census never opens `logs/episodes/` or `*.log`.
   Stale detection for additions and removals is this weekly reading alone —
   a writer added without a row shows as `UNKNOWN`, a retired writer as
   `NO_ROWS`, a lingering file as `ORPHAN`; no write-time contract, no import
   check (declined below).
3. **The projection is denylisted by name and shape, not trusted.** Fields
   ending `_b64`, names containing a body token (`content`, `prompt`, `output`,
   `body`, `message`, `text`, `reason`, `note`) unless they end in `_sha256`,
   strings over 200 characters, and every list of strings (model-produced
   names — the skill-selection renderer's ADR-0083 boundary) are dropped.
   Numbers, booleans, timestamps, enums, ids and digests survive.
   `tests/test_instrument_census.py` pins the boundary, including "never
   opens an episode or `.log` file" by spying on `open`.
4. **Telemetry gets a content identity.** `guard.nonce_stable_digest` hashes
   the prompt with every `untrusted_content_<hex>` nonce normalised;
   `emit_llm_telemetry` records it as `prompt_norm_sha256` beside the raw
   digest (ADR-0065 metadata-only contract holds — a one-way digest). The
   census keys llm-calls redundancy on `(caller, prompt_norm_sha256)`. Rows
   before 2026-09-12 lack the field and are not counted.
5. **The weekly session gains Phase 0 — read-through** (`weekly-report`
   skill). Before synthesising the observation document it reads the census
   (the *judgement* projection: scoring, selection, call sequences) and the
   seven daily comment reports in full — `Context` (the counterparty's post)
   included, because a reply cannot be read without it; the reports are
   already the sanctioned processed path — with one open question: *anything
   unexpected in repetition, absence, order or value?* Findings land inside
   the existing six headings — census-derived in Exceptions, behaviour-derived
   in Deviations as (b) structural novelty, or Discarded `no-counterfactual`.
   **Mechanism-side observations only:** anything that would be resolved by
   editing skills / rules / identity / constitution is not written — the value
   layer is observed, not repaired, and a run of such proposals is why the
   document was reduced to its RFC-0010 form. No prescriptions. F1/F2/F3
   diagnosis is unchanged.
6. **Wiring.** `weekly-analysis.sh` runs the census after the state-invariant
   check and places `## Instrument Census` after it in the materials;
   `config/prompts/weekly-analysis.md` lists it as (5b) and names census
   statuses and redundancy as Exceptions signal; `weekly-gate` Step 6f reads
   only the census's bold status line and edits `REGISTRY`. The two orphan
   files are **not** deleted here — the census reports them as `ORPHAN` and a
   human decides at the gate.

### Consumption plan

- **(a) Who reads it, when.** The unattended `/weekly-report` session, every
  week, Phase 0 (distributions, redundancy, projection). The Saturday
  `/weekly-gate`, Step 6f, reads the census table's non-OK line only.
- **(b) How many reads decide what.** One read per non-OK status decides one
  registry edit (register / retire / delete / leave with a one-line reason).
  Redundancy and distribution skew are inputs to the F1 diagnosis, not
  decisions in themselves. No numeric threshold is attached to any reading.
- **(c) Retire when.** Writing under `logs/` requires a registry row at write
  time (a contract in `append_jsonl_restricted`) — then the weekly `UNKNOWN`
  check is redundant and the census shrinks to distributions and projection;
  or the weekly chain itself is retired (north star: the mechanism layer
  stops).

## Review-when

- A second failure class that the census projection *could* have shown but
  Phase 0 did not surface within two weekly reads of it existing → the
  read-through is not doing the work; revisit whether the LLM step should get
  a different projection (e.g. per-session timelines) or be dropped.
- `prompt_norm_sha256` repeats are dominated by a legitimate caller (a retry
  loop by design) for four consecutive weeks → give that caller an exemption
  in `REGISTRY` rather than reading around it.
- The registry needs a row edited more than once per month for a month → the
  write-time contract in (c) is cheaper than the weekly human edit; build it.
- Phase 0 starts producing value-layer proposals despite the prohibition →
  the prohibition text is not holding; move the read-through to a
  code-side projection with no free-text output.
- The hook's `episodes` parent rule blocks a legitimate `episodes/` directory
  in another repo → the folder name is doing double duty; namespace it
  (e.g. `moltbook-episodes`) in both the writer and the guard.

## Alternatives Considered

- **Fix the Bash guard's glob rule with a literal-prefix test** ("block only
  if the prefix before `*` could begin a date or `agent-launchd.log`").
  Rejected by the author: it keeps the boundary as a regex over a mixed
  directory; moving the protected class into its own folder is simpler and
  reads as what it is.
- **Move the telemetry out instead of the episode logs** (`logs/instruments/`).
  Rejected: fourteen writers, the launchd plists, rotation and backup scripts
  and every reader would move; the episode logs have one writer class and
  one reader path.
- **A write-time registry contract in `append_jsonl_restricted` plus an
  import-resolving writer test, in addition to the census.** Rejected
  (author, 2026-09-12): redundant nets for a weekly-detectable condition; the
  census statuses already detect additions and removals. Kept as the
  retirement condition (c) if registry edits become frequent.
- **One dedicated reader per unread log.** Rejected: six scripts asking six
  fixed questions reproduce the failure mode — the next unread log has no
  reader until someone imagines its failure. The registry row is cheaper
  than a script and the `UNKNOWN` status covers the next file.
- **Let Phase 0 read the raw episode logs.** Rejected: the comment reports
  already carry the same bodies through the sanctioned path, and the census
  covers the judgement side that never reaches them; ADR-0083's boundary
  stands.
- **Restrict Phase 0 to the agent's own `Internal note` / `Output` sections.**
  Rejected by the author: a reply cannot be judged without the post it
  answers; the reports are processed output, and the earlier weekly format
  read them whole.

## Consequences

- Six previously unread logs now answer a declared question weekly; the two
  orphans are visible until a human decides. The first live run
  (2026-09-05 – 09-11) already reports `NO_ROWS` for `constitution-shadow`
  and `insight-novelty` — expected for a monthly shadow and a pipeline that
  did not stage that week, but now stated rather than silent.
- The weekly materials grow by one section (~200 lines at `--sample 30`).
  The `/weekly-report` session reads it in Phase 0; the reading discipline is
  in the skill text, not enforced by code — Review-when covers the failure.
- `logs/episodes/` is a new path in `MOLTBOOK_HOME`. Backups (`logs/`
  excluded wholesale), `sync-research-data.sh` (same) and the anomaly sweep
  (`*.log` glob) are unaffected. Any external tooling that spelled
  `logs/YYYY-MM-DD.jsonl` must follow; inside this repo the constant is the
  single spelling.
- The harness guard (global, `~/.claude`) and this repo changed together; the
  public harness copy is synchronised separately (`harness-sync`).
- `llm-calls` rows gain one 12-hex field. Redundancy readings start on
  2026-09-12; the RFC-0032 week itself can never be read this way — its raw
  digests are nonce-bearing.
- The census is itself an instrument and would have been refused at the gate
  without the consumption plan above (ADR-0101). Its retirement condition is
  a build, which is a deliberate inversion: the cheaper thing is kept until
  its cost is measured.
