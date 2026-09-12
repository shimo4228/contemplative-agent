# ADR-0110: The Weekly Log Reading Becomes a Series — Session Ledger, Within-Week Outliers, Collapsed Windows

## Status

accepted — partially-supersedes ADR-0107 (retired: the D2 projection sample, the D3 denylist, and D5's first Phase 0 input)

## Date

2026-09-12

## Context

[ADR-0107](./0107-instrument-census-and-episode-log-folder.md) gave every
self-written log a weekly reader on the morning of 2026-09-12. Its projection
was a count table per log plus thirty deterministically sampled rows. Later the
same day RFC-0036 — the agent calling `GET /home` and `GET /feed` alternately
for the last eleven seconds of a session, twelve calls into a loop that had
nothing left to do — was found **by hand**, not by that projection, and could
not have been found by it. The reason is structural, not a tuning miss:

- The whole shape of the fault is time. Twelve rows inside eleven seconds are
  indistinguishable, in a count table, from twelve rows spread over an hour.
- A thirty-row sample of the week's 4,035 api-audit rows draws those twelve
  with an expectation of **0.09 rows**. The sample cannot see it at any seed.

Measured on the same window (2026-09-05 – 09-11, 28 sessions, raw logs only;
`logs/episodes/` was not opened):

| Fact | Value |
|---|---|
| ADR-0107 census output, that window | **130 KB / 443 lines** (the ADR's "~200 lines" was wrong) |
| of which the projection sample | 126 KB — **97%**, spent on rows that carry no question |
| this ADR's projection, same window | **24,463 B / 311 lines**, byte-identical across runs |
| RFC-0036 under the new projection | `api-audit:GET /feed gap s` = 0 s against a median of 148 (z −19.6), rank 3 of 5; the hunting window prints `15:59:09 api-audit:GET /home ×13 in 11s` and `15:59:10 api-audit:GET /feed ×12 in 10s` |
| RFC-0032 under the new projection | invisible, and this is stated below rather than worked around |
| JSONL retention | `rotate-log.sh` rotates `*.log` only; llm-calls from 06-09 and api-audit from 06-25 are intact, so a four-week vocabulary window costs one extra pass |

ADR-0107's first `Review-when` condition — "a failure class the projection
could have shown but Phase 0 did not surface within two weekly reads" — has
**not** fired: Phase 0 has run zero times. The ground for superseding is not
that condition but a design defect found before the first reading, by a person
doing the work the instrument was built to do. ADR-0107 carries a dated note to
that effect.

The generalisation is deliberate. The two known bugs are **smoke for the alarm,
not its purpose** — the instrument must not contain a column, threshold or
special case named after `/home` or `score_relevance`, or it will catch exactly
the two faults already known. What it covers instead is four failure shapes —
repetition, absence, order, value — across every category of every log and
every session, with the columns derived from the data.

### Reused, with sources (checked 2026-09-12)

| Borrowed | Source | Form here |
|---|---|---|
| Four Golden Signals / RED as *columns* | SRE Book ch.6 (2016); Wilkie, RED (2015) | three time axes per category: per-session count, busiest minute, minimum gap. No thresholds and no paging — every failure here returns HTTP 200, and ch.6 itself says a rule that never fires should be deleted |
| USE against a budget | Gregg, USE (2012) | `rate_remaining` minimum and per-minute maxima against the platform's 60 GET / 30 POST contract |
| canonical log line | Stripe / Leach (2019); Majors et al. (2022) | the session ledger: one row per session |
| BubbleUp | Honeycomb (2022) | one session against the other 27, column by column |
| Shewhart rule 1 via median / MAD | Shewhart 1931; Western Electric 1956; Iglewicz & Hoaglin 1993 | within-week outliers. The unit of comparison is the **session**, not the week: four weekly points cannot estimate a limit (Quesenberry 1993) |
| `last message repeated N times` | BSD syslogd | consecutive same-category events ≤ 2 s apart, three or more, collapse to one line |
| count invariants written, not mined | Lou et al. 2010; He et al. 2016 | the existing Redundancy section, now named as what it is |
| compression ratio as a repetition tripwire | LZ76; Cilibrasi & Vitányi 2005 | one zlib column in the ledger |

Not borrowed: threshold paging, burn-rate alerts, S-H-ESD (no season to
decompose), Skyline-style consensus (a flood of flags), Nelson rules 2–8 (they
need runs of 8–15 points), Kleinberg's burst automaton (overkill at ~23 events
per session), Kayenta's two-sample tests (no cross-week comparison is built),
process-mining variant tables (all 28 traces are unique), Drain / Loghub
(these logs are already enums).

A skill / MCP search the same day (Anthropic's official skills,
claude-plugins-official, awesome-claude-code / ECC, the MCP registry) found
**nothing** that groups local JSONL by session and minute, computes gaps and a
median/MAD reading, and holds no resident state. The near misses were
duckdb-skills (a generic SQL engine; the questions are not included),
json-logs-mcp-server (hour-level group-by, 11 commits), log-analyzer-mcp and
jsonl-tools-mcp (grep / filter), log-mcp (no aggregation), Anthropic's SRE
incident-responder cookbook (a prompt that asks the model to run `jq`), and the
SaaS connectors (Honeycomb / Grafana / Logfire / Opik), all of which require a
resident backend. The reading discipline exists as literature; the
implementation for this shape does not.

### Dependency policy

`pandas`, `tabulate` (which `DataFrame.to_markdown` needs) and `pandas-stubs` enter
`[dependency-groups] dev`, not `[project] dependencies`. `scripts/` is outside the wheel, so the weight of a
dependency is not a reason to refuse it there
(`ADR-0109` — the dependency floor scoped to the wheel, filed the same day; not yet on this branch); the wheel keeps
`requests` + `numpy`. `scipy` is **not** added: the only statistic wanted from
it is a MAD, which is three lines of the numpy already present, and no
cross-week test is being built. The census invocation in `weekly-analysis.sh`
therefore moves from bare `python3` to `uv run --project … --no-sync -q python`,
the shape the skill-selection intake in the same script already uses.

## Decision

1. **The projection sample is deleted; six sections replace it.** After the
   census table, the distributions and the redundancy reading (all unchanged in
   kind): a **session ledger** (one row per session, one column per
   log:category plus per-minute maxima, minimum gaps, error counts, saturation
   minima and a zlib ratio, with a `median` row last; only the per-category
   count axes are *drawn*, because only they share a unit — a duration sum in
   milliseconds would otherwise hold a slot on magnitude alone); a **session trace**
   (every log's events in ts order, one letter per category, run-length
   encoded, so `A B A B` stays distinct from `A A B B`); **session strips**
   (the first sixty minutes as sixty characters, scaled by the week's maximum
   so bands compare); **id-field repeats** (any `*_id` / `*_sha256` field found
   by name, repeating inside one session); **within-week outliers**; and
   **hunting windows** (the minutes around the top outliers, syslog-collapsed).

2. **Columns are derived, never declared.** Every value of a registry row's
   `category` field becomes columns on the same three time axes. The column
   vocabulary is this window's categories **unioned with the previous four
   weeks'**, and the row set is the union of every `session_id` in any log, so
   a category that stopped appearing is a column of zeros and a session that
   wrote nothing to a log is a row of zeros — both ordinary cells of the scan.
   A caller or endpoint that appears next week is measured the week it appears,
   with no registry edit.

3. **`REGISTRY` rows carry standard axes instead of a prose `note`.** `Entry`
   gains `category`, `error` (a tuple of `(field, op, value)` predicates a
   healthy row satisfies; a row whose field is absent or null is not judged)
   and `saturation`; `note` is removed and the census table's Question column
   is generated from the field names. The rows stay **data** — no callables —
   so the Saturday gate edits them without reading code.

4. **The projection becomes an allowlist at the load boundary.** Only `ts`,
   `session_id`, the fields a registry row names, and scalar `*_id` /
   `*_sha256` fields are read out of a parsed line. A body field is not
   filtered out of the output: it never becomes a value in the first place.
   This supersedes ADR-0107's D3 denylist; `strip_body` and
   `test_projection_strips_bodies_by_name_and_by_shape` are deleted, while the
   spy test ("never opens an episode or `.log` file") and the end-to-end "no
   bodies in the output" test stay — the spy repaired, see below. Markdown
   neutralisation moves to one funnel: `_short` applies `md_safe(printable(…))`
   to every log-derived string on its way out, because that string becomes a
   table cell, a column name, a legend entry and a line inside a fenced block,
   and a sanitiser repeated at four sinks is a sanitiser missing from one of
   them (it was missing from three when the security review ran).

5. **Outliers are ranked by a modified z with three stated calibrations.**
   Median and MAD per column over the sessions; `|z| ≥ 3.5` (Iglewicz &
   Hoaglin); at most five rows, **one per column and one per session**.
   - A minimum gap needs at least three intervals (`_MIN_GAP_EVENTS = 4`). A
     minimum over one interval is the sample, not a rate.
   - Gaps and sums are scored on `log1p`: they are ratio-scaled, so a departure
     is a multiple, not a difference.
   - Where the MAD is zero the scale floor is **one unit of the column**, not
     Iglewicz & Hoaglin's mean-absolute-deviation substitute. Their substitute
     is finite but saturates — with one departing session out of n it returns
     the same score whatever the size of the departure, so every constant
     column ties at 22.3 and the ordering falls to the alphabet.

   Each calibration was chosen against the live window, and each was a
   measured failure of the simpler form first: without the gap minimum one
   log's sparse sessions took the whole list; without `log1p` one endpoint's
   gap column took the whole list at four-digit scores; without the two
   deduplications one session took four of five slots with four views of one
   fact. The zlib ratio is read in the ledger but not ranked — it summarises
   the trace rather than being an axis of it, and is not on the scale of a
   count; a departure in it is printed as one line under the table.

6. **No cross-week comparison is built.** The ledger ends in a `median` row and
   the reader compares it with the previous reports the materials already
   carry. The alternative is in *Alternatives Considered*.

### Consumption plan

- **(a) Who reads it, when.** The unattended `/weekly-report` session, every
  week, in Phase 0 — now six sections rather than a sample. The Saturday
  `/weekly-gate`, Step 6f, still reads only the census table's bold status
  line; that step is unchanged.
- **(b) How many reads decide what.** Two reads (2026-09-18 and 2026-09-25)
  decide whether the projection stays as it is, through two calibrations
  stated below. After that the sections are inputs to the F1 diagnosis, as the
  distributions already were. No numeric threshold is attached to any reading,
  and the outlier list is explicitly allowed to be empty. The first
  `Review-when` condition covers both ways this can fail, and they want
  different fixes: Phase 0 did not run (a chain fault — repair the chain, the
  projection is untested) or it ran and did not cite the ledger (a projection
  fault — the median row is not worth a line, so change or drop it). The
  weekly-pipeline audit log says which.
- **(c) Retire when.** With the weekly chain (the north star's mechanism-layer
  stop). The outlier *ranking* alone retires earlier: if two consecutive weeks
  send every listed outlier to `Discarded / no-counterfactual`, the ranking
  comes down and the ledger stays.

The two calibrations (b) turns on, with the values frozen here so the check is
decidable:

1. **RFC-0036 (acute).** Already confirmed above on the unrepaired week.
2. **RFC-0032 (chronic).** The 2026-09-05 – 09-11 ledger median row reads
   `llm-calls:moltbook.score_relevance` **44.5**, `moltbook.internal_note`
   **24**, `skill-selection:selection` **21**, `llm-calls:moltbook.comment`
   **11**, `verification-audit:comment` **11**,
   `api-audit:GET /submolts/{name}/feed` **28**. The repair landed after this
   window. If the 2026-09-18 observation document writes "score_relevance
   median 44.5 → X" in its Exceptions, the ledger is being read as intended.
   If it does not, the first `Review-when` condition below has fired.

## Review-when

- The 2026-09-18 or 2026-09-25 observation document does not carry a ledger
  median line → the ledger is not being read; replace the median row with
  something the writer must act on, or drop it.
- Two consecutive weeks list outliers that all end in `Discarded
  no-counterfactual` → the ranking is producing noise; remove the ranking, keep
  the ledger (consumption plan (c)).
- A fault is found by hand that this projection *could* have shown and did not,
  in any two-week period → the sections are present but unread, which is a
  different defect from ADR-0107's and wants a different fix (fewer sections,
  or a code-side check with no free-text output).
- The outlier list is empty for four consecutive weeks → either the mechanism
  layer has stopped changing (the north star's success condition, in which case
  say so) or `_Z_THRESHOLD` is set too high for a 28-point population.
- The outlier table names a column outside the displayed ledger columns in two
  consecutive weeks (the 2026-09-05 – 09-11 window derived 135 columns and
  displays 10, so this is possible from the first week) → the display rule
  "the largest medians" is hiding the half that carries the findings; rank the
  display by departure instead of by size.
- The per-minute strips or the trace are never cited in an observation document
  for a month → they are decoration; delete them and keep the ledger.

## Alternatives Considered

### Automatic comparison against the previous four weeks

Build the series properly: carry each week's ledger forward and test this
week's against it. **Not built** (owner, 2026-09-12; `architect` independently
returned *Don't build*). The reader already does this by hand from the three
previous reports the materials carry — observation O-009's 20.2 → 17.8 → 23.4 →
26.6% series was assembled that way — and a stored series is a state file, a
schema and a migration for a comparison that a person performs in one line. The
`median` row is the whole mechanism.

### Wait for ADR-0107's own two weekly reads before touching it

The status quo, and the option this ADR pre-empts on the same day the
instrument shipped: ADR-0107 set its own review gate at "two weekly reads", and
Phase 0 has had none. The case against waiting is not that it is slower but
that it is **uninformative**: the reads would be evidence about the projection
only if the projection could show the fault at all, and the sample's 0.09
expected rows is a property of the arithmetic, not of a particular seed or
week. Two more weeks would produce two more reads that could not have found
RFC-0036 and would not say why. What is given up is real — the replacement is
also unread, so its own calibration (Consumption plan (b)) is the honest
version of the same gate, this time with a stated failure condition and a
frozen number to check against.

### Keep the projection sample alongside the new sections

Rejected on the arithmetic in Context: 97% of the output for rows that answer
no question, and a detection probability of 0.09 rows for the fault that
motivated this. What a sample is *for* — an uncurated window the document's
selection function cannot bias — is already provided by the weekly Random
Sample section (ADR-0099), which draws from the exchanges rather than the
telemetry.

### Retire the full read of the seven daily comment reports to pay for this

Considered and **rejected** (owner, 2026-09-12, after checking). Three of the
last three weeks' seven mechanism-side findings came only from the reports
(O-008 a nonce published as an attribution label, O-013 a skill heading leaking
into body text, O-014 the same prompt arriving three times and being answered
freshly each time); none of them is visible in any log. Only the wording
changes, from "read in full" to "grep first, then read the entries that
sections 8 and 9 point at" — which is what the sessions already do.

### `scipy` for the robust statistics

Rejected: the only function wanted is a MAD, which is three lines of numpy, and
no cross-week test is being built. Adding a dependency for one function is the
case the dependency policy names as over-reach, even where the wheel is not
involved.

### A SQL engine (sqlite3 / DuckDB) instead of pandas

A 13-line sqlite3 prototype did reproduce the session table, the per-minute
maximum (13 for the burst session) and the gaps. Rejected once pandas was
allowed: the same aggregations are one `groupby` or `pivot_table` each, the
trace and the strips need Python anyway, and a second query language in the
file is a second thing to read.

### A change-point / anomaly-detection package

`ruptures`, `changefinder`, `adtk`, `river`, `pyod`, `tsod`, `statsmodels`,
`prophet`. Rejected on fit, not on weight: 28 points compared within one window
have no trend, season or drift to find, and none of these offers more than
median / MAD at that size.

### An OpenTelemetry pipeline

Rejected: a wire format plus a resident backend, and it still answers only the
questions someone defined in advance — the same layer as the defect being
fixed.

## Consequences

- **"Different from the other sessions" is structurally blind to chronic
  faults.** RFC-0032 was present in every session from the first day, so it
  departs from nothing and appears in no outlier row — by construction, not by
  oversight. Two things cover that shape and both are kept: the Redundancy
  section (a written count invariant, ADR-0107 D4) and a reader looking at the
  ledger's absolute values and ratios. The census header says so in the output
  itself, so the reader is not left to infer it.
- **D4 removes a layer rather than adding one.** The allowlist is strictly
  stronger against the fields that exist today — a body is never read — but the
  shape-based net it replaces (strings over 200 characters, every list of
  strings) also covered fields *nobody had named yet*. Registry rows are data a
  human edits at the Saturday gate (Decision 3), so a row that names a
  free-text field now admits up to `_VALUE_MAX_CHARS` = 60 characters of it
  into the distributions, and the surviving tests check the current registry,
  not the editing surface. The gate step that edits `REGISTRY` (weekly-gate 6f)
  is the control, and it is a human one; if a registry edit ever names a
  free-text field, the cheap fix is a shape assertion on the enum values rather
  than restoring `strip_body`.
- **The boundary test that ADR-0107 relied on was not testing anything, and
  this diff repairs it.** Its spy replaced `builtins.open`, but the census
  reads through `Path.read_text`, which reaches `io.open` by module attribute
  and never passes through `builtins`. The spy recorded zero opens, so the
  assertion quantified over an empty list and passed for any behaviour — a
  read of `logs/episodes/` inserted into `census()` still passed it. The spy
  now watches `Path.read_text` as well, asserts it recorded something at all,
  matches on the path *below* `logs/` (pytest's own tmpdir is named after the
  test, so "episodes" and ".log" appear in every absolute path), and was
  confirmed by running exactly that mutation and watching it fail. The
  boundary itself was never breached; what was missing was the proof.
- A constant column needs a departure of `3.5 × 1.4826 ≈ 5.2` units to be
  listed (Decision 5). A category that every session calls three times and one
  session never calls is therefore *not* in the outlier table; it is a zero in
  the ledger. This is the price of a scale floor that makes scores comparable
  across columns.
- The first live run reads two facts nobody had asked for: one session wrote
  1,919 `comment-outcomes:reply` rows in two seconds while the median session
  wrote none, and sixteen `llm-calls` callers present in the previous four
  weeks are absent from this one (the monthly and pipeline-only callers — the
  reading is correct and uninteresting, which is what a zero column should look
  like when nothing is wrong).
- The output is 25 KB against a 130 KB predecessor, but the display budgets
  that keep it there (10 ledger columns of 135, 10 trace runs, 18 hunting
  lines) are tuned to this week's shape. They are constants at the top of the
  file, and the `Review-when` above names the condition under which the display
  rule itself is wrong.
- The per-minute strips use an ASCII ramp rather than block-drawing characters.
  The blocks are more legible and cost three bytes each: 28 sessions × 2 bands
  × 60 minutes of them is 7 KB, a quarter of the whole reading spent on glyphs.
- **The reader is three modules, not one.** The single file reached 1,063
  lines against a budget of 500, and the budget was arithmetic on a wrong
  subtraction: it assumed the retired sample would free 250 lines, where what
  could actually be deleted was `strip_body` 37 + `_render_sample` 20 + the
  `_Acc` accumulator 44 ≈ 101, while the registry grew at the same time (a
  `note=` string became three declared axes). Measured, a file holding only
  what ADR-0107 established — header, `Entry`, `REGISTRY`, the loader, the
  census table, Distributions, Redundancy, `main`, and the blank lines ruff
  format requires between definitions — is already **≈ 535 lines**, so one file
  under 500 was unreachable for any version of this instrument. The split is by
  responsibility, not by line count:
  `_census_registry.py` (**333**) owns the row schema, the status vocabulary
  and the read, including both boundaries; `_census_series.py` (**315**) owns
  the aggregation and the statistics and touches no file; `instrument_census.py`
  (**431**) owns the nine renderers and stays the entry point the weekly chain
  calls. Each imports only downward, so there is one direction to read in.
  **1,079 lines in total: the split itself came in at 1,048 against 1,063
  before it, and five code-review fixes then added 31** — a reduction pass
  paid for the three headers: the module docstring stopped restating this ADR
  (−29), `REGISTRY` is hand-wrapped at two lines per row under `# fmt: off`
  (82 → 33 — the gate edits that table row-wise and the formatter's
  one-argument-per-line form made fifteen rows eighty-two lines), and three
  single-use helpers were inlined (−11). Nothing the reader sees was removed:
  the output is byte-identical to the single-file version.
- `pandas` is now required to produce the weekly materials. A machine with the
  dev group unsynced gets the stub line the shell already had
  (`No instrument census available`), not a broken chain.
- The census now reads roughly five weeks of each log instead of one, to build
  the category vocabulary. On the current corpus (api-audit 13.9 MB) the whole
  run takes 1.8 s, so no incremental reading is built.

## References

- [ADR-0107](./0107-instrument-census-and-episode-log-folder.md) — the census
  this partially supersedes (D2 projection, D3 denylist, D5 Phase 0 input 1);
  D1 (the episodes folder), D4 (content identity) and D6 (wiring) stand
- [ADR-0101](./0101-instrument-dissolution-mandate.md) — the consumption plan
  above exists because of it
- `ADR-0109` (dependency floor scoped to the wheel) — why pandas is allowed in
  `scripts/`; link it once that ADR is on the same branch
- [ADR-0099](./0099-weekly-report-instrument-redesign.md) — the Random Sample section
  that already carries the uncurated-window role
- [RFC-0036](../../rfcs/0036-session-end-cycle-spin.md) — the acute fault used
  as smoke
- [RFC-0032](../../rfcs/0032-feed-score-cache-per-cycle.md) — the chronic fault
  this projection cannot see
