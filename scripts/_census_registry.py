"""The registry and the read: which self-written logs exist and what is read out.

Layer 1 of three (ADR-0107 / ADR-0110). A ``REGISTRY`` row is the weekly
question for one log — the fields it names are what that file is asked. This
module owns the row schema, the closed status vocabulary, and the load: it
matches files, parses rows, and projects each row through an **allowlist at the
load boundary** so a body field never becomes a value in memory.

``_census_series`` aggregates what this returns; ``instrument_census`` renders
it and is the entry point. Nothing here imports either of them.

Two invariants only the code can hold:

- Reads ONLY registry-matched files plus the directory listing of ``logs/``.
  It NEVER opens ``logs/episodes/`` (text authored by other agents — the
  injection carrier this output must not relay) nor any ``*.log``.
- ``_project`` copies out ``ts``, ``session_id``, the fields a registry row
  names and scalar ``*_id`` / ``*_sha256`` fields, and nothing else, so no
  later stage can leak a body it never held. Every string then passes
  ``short`` once, which is where length, control characters and Markdown
  structure are handled.

``tests/test_instrument_census.py`` pins both.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
from _md import md_safe, printable

from contemplative_agent.adapters.moltbook.relevance_gate import ENFORCE_REASONS
from contemplative_agent.core.llm.decision import DECISION_REASONS

# Episode-log day files (any suffix) live in logs/episodes/ since ADR-0107;
# this guards against a stray copy left directly under logs/ by an older layout.
_EPISODE_NAME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl")

_TOP_REDUNDANT = 8  # repeated keys kept per log — the reading, not the render
_VALUE_MAX_CHARS = 60
PAST_WEEKS = 4  # vocabulary window for categories that vanished this week
_STRUCTURAL_IDS = ("run_id", "session_id")

LIVE = "live"
WRITER_RETIRED = "writer_retired"
# The gate decided to keep a retired writer's file as research data: it is no
# longer a question, so the census reports it as KEPT (an OK-class status)
# instead of asking ORPHAN again every week (2026-09-26 gate decision).
KEPT = "kept"  # entry status; the reading it produces is the display status KEPT_READING


@dataclass(frozen=True)
class Entry:
    """One registered self-written log — data only, no callables.

    ``category`` names the field whose values become ledger columns, trace
    letters and outlier axes. ``error`` holds ``(field, op, value)`` predicates
    a healthy row satisfies (``in`` / ``not-in`` take a tuple, ``<`` a number;
    a row whose field is absent or null is not judged — except ``in-range``,
    which takes a half-open ``(lo, hi)`` and DOES judge null as failing, so a
    transport row with ``status: null`` counts against api-audit). ``saturation`` names a
    budget field read as a per-session minimum. ``redundancy_key`` names the
    fields whose identical repetition inside one ``session_id`` is the declared
    count invariant. ``expect_events`` are ``event`` values that must appear at
    least once per window (a heartbeat); absence is a status. ``ts_field``
    names the field the writer stamps its time in; the frame always calls the
    parsed value ``ts`` whatever the source field was named.
    """

    glob: str
    owner_adr: str
    status: str = LIVE
    enum_fields: tuple[str, ...] = ()
    # ``(field, closed vocabulary)`` pairs — the writer's own constant, imported, so a
    # value outside it is read as a different writer version or a producer/consumer split
    # and shows up in the distributions (P1-08.12). A field named here must be an enum field.
    enum_values: tuple[tuple[str, tuple[str, ...]], ...] = ()
    numeric_fields: tuple[str, ...] = ()
    category: str | None = None
    error: tuple[tuple[str, str, object], ...] = ()
    saturation: str | None = None
    redundancy_key: tuple[str, ...] | None = None
    expect_events: tuple[str, ...] = ()
    # Days between runs for a writer slower than the weekly window (a monthly
    # instrument, an amendment-gate tool). An empty window reads QUIET (OK-class)
    # while the newest row is within this many days of the window end; older
    # than that it is NO_ROWS again, so a writer that silently died is still
    # asked about (2026-10-03 gate decision, code review). 0 = weekly rows expected.
    cadence_days: int = 0
    # Required on a KEPT row (P1-04.14): an ISO date the keep lapses on, or a
    # condition in words. A date in the past turns the row back into ORPHAN so
    # the gate is asked again; words are the reader's reminder and never expire
    # by themselves. Without it a KEPT row is a standing register (ADR-0101).
    until: str = ""
    # The writer's time field. Most self-written logs stamp ``ts``; a writer that
    # stamps another name is read by that name, declared on its row (RFC-0063).
    ts_field: str = "ts"

    def __post_init__(self) -> None:
        if self.status == KEPT and not self.until:
            raise ValueError(f"{self.glob}: a KEPT row needs `until` (a date or a condition)")
        for name, _ in self.enum_values:
            if name not in self.enum_fields:
                raise ValueError(f"{self.glob}: enum_values names {name!r}, not an enum field")
        # A heartbeat (expect_events) is a weekly promise; a slow cadence would
        # let the early QUIET return skip the MISSING_EVENT check.
        if self.cadence_days and self.expect_events:
            raise ValueError(f"{self.glob}: cadence_days and expect_events are exclusive")

    def matches(self, name: str) -> bool:
        return Path(name).match(self.glob)

    def keep_lapsed(self, on: date) -> bool:
        """True when ``until`` is an ISO date on or before ``on``."""
        try:
            return date.fromisoformat(self.until) <= on
        except ValueError:
            return False

    @property
    def key(self) -> str:
        """Column prefix: ``llm-calls-*.jsonl`` → ``llm-calls``."""
        return self.glob.replace("-*", "").replace("*", "").removesuffix(".jsonl")

    @property
    def fields(self) -> tuple[str, ...]:
        """Every field this row names — the allowlist for reading it."""
        names = [*self.enum_fields, *self.numeric_fields, *(self.redundancy_key or ())]
        names += [f for f, _, _ in self.error]
        names += [f for f in (self.category, self.saturation) if f]
        return tuple(dict.fromkeys(names))

    def unknown_values(self, field_name: str, values: pd.Series) -> list[str]:
        """Values of a closed-vocabulary field that its writer's constant does not list."""
        vocab = dict(self.enum_values).get(field_name)
        if vocab is None:
            return []
        return sorted({str(v) for v in values.dropna()} - set(vocab))

    @property
    def question(self) -> str:
        """The weekly question, generated from the fields rather than prose."""
        bits = [self.category] if self.category else []
        for f, op, v in self.error:
            shown = ",".join(str(x) for x in v) if isinstance(v, tuple) else str(v)
            if op == "in-range":
                bits.append(f"error if {f} ∉ [{v[0]}, {v[1]})")  # type: ignore[index]
                continue
            bits.append(f"error if {f} {'∉' if op == 'in' else op} {{{shown}}}")
        bits += [f for f in self.enum_fields if f != self.category]
        bits += [*self.numeric_fields, *([self.saturation] if self.saturation else [])]
        return " · ".join(bits) or "rows in window"


# The registry IS the reader. Add a row when a writer is added; flip status to
# writer_retired when the writer is removed (the file lingers as ORPHAN until
# the gate deletes it, then the row goes — or flips to kept if the gate keeps
# it as research data, after which the row stays and stops asking). Never list logs/episodes/ here.
# One row per registered log, wrapped by hand at two lines per row.
# fmt: off
# The gate reads and edits this table row-wise (ADR-0107 D2); the formatter's
# one-argument-per-line form turns fifteen rows into eighty-two lines.
# llm-calls keys redundancy on prompt_norm_sha256, not prompt_sha256: the raw
# digest changes with every wrapped call (fresh delimiter nonce) and reads 0
# repeats over a week of RFC-0032 duplicates. Rows before 2026-09-12 lack it.
# skill-selection has no redundancy key for the same reason — its repeat
# reading rides llm-calls (caller core.skill_selection).
REGISTRY: tuple[Entry, ...] = (
    # truncated_kept is a success (P1-07.5): the generation was kept and handed
    # to the caller, the breaker scored a success; ``done_reason`` carries the
    # truncation as its own column. kind / schema / template (P1-07.13) are the
    # row's identity; rows before 2026-10-24 carry none of them.
    Entry("llm-calls-*.jsonl", "ADR-0065", category="caller",
          error=(("outcome", "in", ("ok", "truncated_kept")),),
          enum_fields=("caller", "outcome", "error_kind", "done_reason", "kind", "schema",
                       "template"),
          numeric_fields=("duration_ms",), redundancy_key=("caller", "prompt_norm_sha256")),
    Entry("constitution-shadow.jsonl", "ADR-0092", category="verdict", enum_fields=("verdict",),
          numeric_fields=("cosine_vs_current",), error=(("verdict", "in", ("ok",)),),
          cadence_days=90),  # runs toward a constitution amendment (interval 83 d), not weekly
    # Removal date 2027-Q1 (2027-03-31) if no amendment is adopted: ADR-0092 Review-when / Consumption plan.
    Entry("injection-detect-*.jsonl", "ADR-0075", category="event", expect_events=("guard_alive",),
          enum_fields=("event", "saturated"), numeric_fields=("total_removed",)),
    Entry("verification-audit.jsonl", "ADR-0062", category="action",
          enum_fields=("solve_success", "verify_success", "action", "solver_path"),
          error=(("solve_success", "in", (True,)), ("verify_success", "in", (True,)))),
    Entry("weekly-pipeline-audit.jsonl", "ADR-0085", category="stage",
          enum_fields=("event", "stage", "result", "reason"),
          error=(("result", "not-in", ("fail", "failed", "verify_fail")),)),
    # The Saturday gate's own writer (weekly-gate Step 0 / 1c / 7): ``event`` is
    # gate_start / roadmap_start / gate_item / gate_record / roadmap_end, a
    # gate_item names its ``category`` and the ``recommendation`` / ``decision``
    # pair whose agreement the gate section reads (P2-01.1). The numeric fields
    # are the gate_record counts, written as strings by pipeline_audit.py and
    # coerced on read; ``held`` is a deferral, not a decision, and is not read.
    Entry("pipeline-metrics.jsonl", "ADR-0085", category="event",
          enum_fields=("event", "category", "recommendation", "decision"),
          numeric_fields=("insight_adopted", "insight_rejected", "deadcode_deleted",
                          "deadcode_whitelisted", "skills_archived")),
    # ``temperature`` is registered on the two judgment logs whose sampling
    # regime changed mid-history (novelty judge 2026-09-19, RFC-0042; skill
    # selector 2026-09-20, RFC-0044): the distribution line then shows how many
    # rows of the week ran under the new regime. A row written before the
    # change carries no such field and is simply not counted there.
    Entry("insight-novelty.jsonl", "ADR-0096", category="verdict",
          enum_fields=("verdict", "reason", "temperature"),
          error=(("verdict", "in", ("judged",)),)),
    # RFC-0042: the naming and duplicate stages. A judged row carries a null
    # ``reason``; a fail-open names why it could not judge, and those are the
    # errors (the stage still passed the item through, so they are load, not
    # loss).
    Entry("insight-stages.jsonl", "ADR-0111", category="verdict",
          enum_fields=("kind", "verdict", "reason"),
          error=(("reason", "not-in",
                  ("llm_none", "unparseable", "off_enum", "no_store",
                   "retrieval_unavailable")),)),
    Entry("insight-staged.jsonl", "ADR-0097"),
    # P0-04.1: ids of episodes distill processed (successes only). A row is a
    # fact, not a verdict, so no category/error fields; the count per session is
    # the reading (yield of the daily distill). The writer stamps ``processed_at``,
    # not ``ts`` (core/distill_ledger.py::record_processed; RFC-0063).
    Entry("distill-processed.jsonl", "ADR-0060", ts_field="processed_at"),
    # ``scale`` "score4" marks the score4 read (ADR-0113 amendment 2,
    # 2026-10-09); a row without it is on the retired 0-1 scale.
    # D-P1-04-1 = A (2026-10-24): a quarterly manual sweep, not weekly (RFC-0011).
    Entry("submolt-scope-*.jsonl", "ADR-0086", category="event",
          enum_fields=("event", "verdict", "subscribed", "scale"), cadence_days=92),
    Entry("api-audit.jsonl", "ADR-0062", category="endpoint", saturation="rate_remaining",
          enum_fields=("method", "endpoint", "status"), numeric_fields=("rate_remaining",),
          error=(("status", "in-range", (200, 300)),)),
    Entry("audit.jsonl", "ADR-0012", category="command",
          enum_fields=("decision", "source", "command"),
          error=(("decision", "in", ("approved", "staged", "held")),)),
    Entry("skill-selection-*.jsonl", "ADR-0076", category="kind",
          enum_fields=("kind", "verdict", "enforced", "publish_status", "temperature",
                       "decision_reason", "failure_reason", "http_status"),
          error=(("publish_status", "in", ("published",)),)),
    Entry("comment-outcomes.jsonl", "ADR-0106", category="kind", enum_fields=("kind", "by_self")),
    # ADR-0113: one row per relevance reading — the score4 gate (RFC-0046).
    # decision_reason "unconfigured" is the off state, not an error;
    # gate_source "fail_closed" + enforce_reason name a gate with no answer
    # (the free-generated live_* half ended 2026-10-07, RFC-0046 cleanup 2).
    # ``source`` names who asked: "feed" or "seed" (self-post seed selection,
    # ADR-0113 amendment 2, 2026-10-09); a row without it is a feed row.
    Entry("relevance-*.jsonl", "ADR-0113", category="decision_reason",
          enum_fields=("decision_reason", "gate_source", "enforce_reason", "source"),
          # enforce_unconfigured: written before ADR-0113 amendment 3 (2026-10-17)
          enum_values=(("decision_reason", DECISION_REASONS),
                       ("enforce_reason", (*ENFORCE_REASONS, "enforce_unconfigured"))),
          numeric_fields=("decision_latency_ms",)),
    # kept 2026-09-26 gate; `until` = the T4 run 3 date (ADR-0101), a proposal for the owner
    Entry("insight-worth.jsonl", "ADR-0097", status=KEPT, until="2027-01-09"),
    Entry("noise-*.jsonl", "ADR-0060", status=KEPT, until="2027-01-09"),
    # The weekly chain's flock file (scripts/weekly-pipeline.sh), empty, not a log.
    # Kept 2026-10-31 gate; the clean fix is the census skipping lock files.
    Entry(".weekly.lock", "ADR-0085", status=KEPT, until="2027-01-09"),
)



# Status vocabulary (closed).
OK, NO_ROWS, MISSING_EVENT = "OK", "NO_ROWS", "MISSING_EVENT"
ORPHAN, UNKNOWN, ABSENT = "ORPHAN", "UNKNOWN", "ABSENT"
# Not a question: a kept file counts as OK for the bold status line.
KEPT_READING = "KEPT"
# A slow-cadence writer whose newest row is still inside its cadence: not a question.
QUIET = "QUIET"
OK_STATUSES = frozenset({OK, KEPT_READING, QUIET})



@dataclass
class Reading:
    entry: Entry | None
    name: str  # glob for registered entries, filename for UNKNOWN
    status: str
    files: int = 0
    rows: int = 0
    rows_out_of_window: int = 0
    rows_without_ts: int = 0
    parse_failures: int = 0
    sessions: int = 0
    last_ts: str | None = None
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    past_categories: tuple[str, ...] = ()
    id_fields: tuple[str, ...] = ()
    redundancy: list[tuple[tuple, int, dict]] = field(default_factory=list)
    redundant_keys: int = 0
    redundant_calls: int = 0


def _is_forbidden_name(name: str) -> bool:
    return bool(_EPISODE_NAME_RE.match(name)) or ".log" in name


def _is_id_field(name: str) -> bool:
    return name.endswith(("_id", "_sha256")) and name not in _STRUCTURAL_IDS


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def short(v: object) -> str:
    """The one funnel every log-derived string passes on its way to the output.

    Length, control characters and Markdown structure are all handled here
    rather than in each renderer: this value becomes a table cell, a column
    name, a trace legend entry and a line inside a fenced block, and a
    sanitiser repeated at four sinks is a sanitiser missing from one of them.
    """
    s = "None" if v is None else str(v)
    s = md_safe(printable(s))
    return s if len(s) <= _VALUE_MAX_CHARS else s[: _VALUE_MAX_CHARS - 1] + "…"


def _project(rec: dict, entry: Entry, dt: datetime, id_fields: set[str]) -> dict:
    """Allowlist one row into the frame: ts, session, declared fields, ids."""
    out: dict = {"ts": dt}
    sid = rec.get("session_id")
    if isinstance(sid, str):
        out["session_id"] = sid
    for f in entry.fields:
        v = rec.get(f)
        if isinstance(v, (str, bool, int, float)) or v is None:
            out[f] = v
    for k, v in rec.items():
        if _is_id_field(k) and isinstance(v, (str, int)) and not isinstance(v, bool):
            out[k] = v
            id_fields.add(k)
    return out


def _iter_rows(path: Path, r: Reading):
    """Yield parsed dict rows of one file; count what could not be parsed."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            r.parse_failures += 1
            continue
        if isinstance(rec, dict):
            yield rec
        else:
            r.parse_failures += 1


def _read_entry(entry: Entry, files: list[Path], start: date, end: date) -> Reading:
    """One pass over the entry's files: window rows in, past categories noted."""
    r = Reading(entry=entry, name=entry.glob, status=OK, files=len(files))
    past_start = start - timedelta(weeks=PAST_WEEKS)
    rows: list[dict] = []
    past: set[str] = set()
    id_fields: set[str] = set()
    seen_events: set[str] = set()
    newest_outside: datetime | None = None
    for path in files:
        for rec in _iter_rows(path, r):
            dt = _parse_ts(rec.get(entry.ts_field))
            if dt is None:
                r.rows_without_ts += 1
                continue
            d = dt.astimezone(timezone.utc).date()
            if start <= d <= end:
                rows.append(_project(rec, entry, dt, id_fields))
                if isinstance(rec.get("event"), str):
                    seen_events.add(rec["event"])
                continue
            r.rows_out_of_window += 1
            if newest_outside is None or dt > newest_outside:
                newest_outside = dt
            if entry.category and past_start <= d < start and rec.get(entry.category) is not None:
                past.add(short(rec[entry.category]))
    r.rows, r.past_categories, r.id_fields = (
        len(rows),
        tuple(sorted(past)),
        tuple(sorted(id_fields)),
    )
    if not rows:
        return _empty_window(r, entry, newest_outside, end)
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    r.frame = df.sort_values("ts", kind="stable").reset_index(drop=True)
    r.sessions = int(df["session_id"].nunique()) if "session_id" in df else 0
    r.last_ts = r.frame["ts"].iloc[-1].isoformat(timespec="seconds")
    if any(ev not in seen_events for ev in entry.expect_events):
        r.status = MISSING_EVENT
    _read_redundancy(r)
    return r


def _empty_window(r: Reading, entry: Entry, newest_outside: datetime | None, end: date) -> Reading:
    """No rows in the window: QUIET only while a slow writer is inside its cadence."""
    if newest_outside is not None:
        r.last_ts = newest_outside.isoformat(timespec="seconds")
    fresh = newest_outside is not None and (
        end - newest_outside.astimezone(timezone.utc).date()
    ) <= timedelta(days=entry.cadence_days)
    r.status = QUIET if entry.cadence_days and fresh else NO_ROWS
    return r


def _read_redundancy(r: Reading) -> None:
    """Count the declared key repeating inside one session (the count invariant)."""
    entry, df = r.entry, r.frame
    if entry is None or not entry.redundancy_key or "session_id" not in df:
        return
    cols = ["session_id", *entry.redundancy_key]
    if any(c not in df for c in cols) or df.dropna(subset=cols).empty:
        return
    sub = df.dropna(subset=cols)
    outcome = sub["outcome"] if "outcome" in sub else pd.Series("None", index=sub.index)
    repeats = [
        (
            (str(g[0]), tuple(short(x) for x in g[1:])),
            len(idx),
            {short(o): int(n) for o, n in outcome[idx].value_counts().items()},
        )
        for g, idx in sub.groupby(cols, sort=True).groups.items()
        if len(idx) >= 2
    ]
    repeats.sort(key=lambda t: (-t[1], t[0]))
    r.redundancy = repeats[:_TOP_REDUNDANT]
    r.redundant_keys = len(repeats)
    r.redundant_calls = sum(n - 1 for _, n, _ in repeats)


def census(logs_dir: Path, start: date, end: date) -> list[Reading]:
    """Match every file directly under ``logs_dir`` against the registry."""
    readings: list[Reading] = []
    names = sorted(p.name for p in logs_dir.iterdir() if p.is_file()) if logs_dir.is_dir() else []
    claimed: set[str] = set()
    for entry in REGISTRY:
        matched = [logs_dir / n for n in names if entry.matches(n)]
        claimed.update(p.name for p in matched)
        if entry.status == WRITER_RETIRED:
            readings.append(
                Reading(entry, entry.glob, ORPHAN if matched else ABSENT, files=len(matched))
            )
        elif entry.status == KEPT:
            # A lapsed keep asks again, exactly like a retired writer's file.
            if not matched:
                shown = ABSENT
            elif entry.keep_lapsed(end):
                shown = ORPHAN
            else:
                shown = KEPT_READING
            readings.append(Reading(entry, entry.glob, shown, files=len(matched)))
        elif not matched:
            readings.append(Reading(entry, entry.glob, ABSENT))
        else:
            readings.append(_read_entry(entry, matched, start, end))
    readings += [
        Reading(None, n, UNKNOWN, files=1)
        for n in names
        if n not in claimed and not _is_forbidden_name(n)
    ]
    return readings
