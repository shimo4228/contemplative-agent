#!/usr/bin/env python3
"""Instrument census over the self-written logs (read-only, ADR-0107 / ADR-0110).

Every JSONL file the agent writes under ``$MOLTBOOK_HOME/logs/`` gets a reader
here, each week. A ``REGISTRY`` row is that reader: the fields it names are the
question the log is asked. ADR-0110 replaced the random projection sample with
a time-aware reading — a sample cannot see a fault whose whole shape is time
(twelve calls in eleven seconds are 0.09 expected rows out of four thousand).
Sections, in reading order:

1. Census — one row per registry entry and per unregistered file, status from a
   closed vocabulary. The stale detector: a new writer reads ``UNKNOWN``, a
   stopped one ``NO_ROWS``, a retired writer's lingering file ``ORPHAN``.
2. Distributions — declared enum counts, numeric min / median / max.
3. Redundancy — the declared key repeating inside one session. A count
   invariant, and the only section that sees a *chronic* fault.
4. Session ledger — one row per session; columns derived from the data (one
   per log:category, plus per-minute maxima, minimum gaps, errors, saturation
   minima, zlib ratio), so next week's new caller is measured on arrival.
5. Session trace — all logs in ts order, one letter per category, run-length
   encoded: ``A B A B`` stays different from ``A A B B``.
6. Session strips — the first hour as sixty characters, scaled by the week's
   maximum so bands are comparable between sessions.
7. Id-field repeats — any ``*_id`` / ``*_sha256`` field, found by name.
8. Within-week outliers — median / MAD per column over the sessions.
9. Hunting windows — the minutes around the top outliers, consecutive
   same-category events collapsed the way syslog collapses them.

A session is compared with the other sessions of the same week, so a fault
present in every session since it began departs from nothing: chronic shapes
belong to section 3 and to the reader of section 4's absolute values.

Security (load-bearing): reads ONLY registry-matched files plus the directory
listing of ``logs/``. It NEVER opens ``logs/episodes/`` (text authored by other
agents — the injection carrier this output must not relay) nor any ``*.log``
(``agent-launchd.log`` is contaminated, T-LOG-DEBUG-CONTENT). The projection is
an allowlist at the load boundary: ``ts``, ``session_id``, registry-named
fields and scalar ``*_id`` / ``*_sha256`` fields are the only values ever read
into a frame, so no later stage can leak a body it never held.
``tests/test_instrument_census.py`` pins both boundaries.
"""

from __future__ import annotations

import argparse
import json
import re
import zlib
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from _md import md_safe, printable

# Episode-log day files (any suffix) live in logs/episodes/ since ADR-0107;
# this guards against a stray copy left directly under logs/ by an older layout.
_EPISODE_NAME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl")

_TOP_VALUES = 6
_TOP_REDUNDANT = 8
_VALUE_MAX_CHARS = 60
_LEDGER_COLS = 10  # displayed columns; the outlier scan uses every column
_TRACE_RUNS = 10  # runs printed per session before the tail is summarised
_STRIP_MINUTES = 60
# ASCII on purpose: the block-drawing ramp is prettier but three bytes a
# character, and 28 sessions × 2 bands × 60 minutes of it cost 7 KB of the
# section budget — a quarter of the whole reading, spent on glyphs.
_STRIP_RAMP = ".:-=+*#%@"  # index 0 is "no rows that minute"
_Z_THRESHOLD = 3.5  # Iglewicz & Hoaglin (1993)
_MAX_OUTLIERS = 5
_HUNT_SESSIONS = 3
_HUNT_LINES = 18
_HUNT_SPREAD = 2  # minutes either side of the peak
_COLLAPSE_GAP_S = 2.0
_COLLAPSE_MIN_RUN = 3
_MIN_GAP_EVENTS = 4  # a minimum gap needs at least three intervals to mean anything
_PAST_WEEKS = 4  # vocabulary window for categories that vanished this week
_STRUCTURAL_IDS = ("run_id", "session_id")
_UNRANKED = ("compress",)  # read in the ledger, not ranked against the event axes
_LEDGER_LABEL = 14  # displayed header width; the full column name is in the outlier table

LIVE = "live"
WRITER_RETIRED = "writer_retired"


@dataclass(frozen=True)
class Entry:
    """One registered self-written log — data only, no callables.

    ``category`` names the field whose values become ledger columns, trace
    letters and outlier axes. ``error`` holds ``(field, op, value)`` predicates
    a healthy row satisfies (``in`` / ``not-in`` take a tuple, ``<`` a number;
    a row whose field is absent or null is not judged). ``saturation`` names a
    budget field read as a per-session minimum. ``redundancy_key`` names the
    fields whose identical repetition inside one ``session_id`` is the declared
    count invariant. ``expect_events`` are ``event`` values that must appear at
    least once per window (a heartbeat); absence is a status.
    """

    glob: str
    owner_adr: str
    status: str = LIVE
    enum_fields: tuple[str, ...] = ()
    numeric_fields: tuple[str, ...] = ()
    category: str | None = None
    error: tuple[tuple[str, str, object], ...] = ()
    saturation: str | None = None
    redundancy_key: tuple[str, ...] | None = None
    expect_events: tuple[str, ...] = ()

    def matches(self, name: str) -> bool:
        return Path(name).match(self.glob)

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

    @property
    def question(self) -> str:
        """The weekly question, generated from the fields rather than prose."""
        bits = [self.category] if self.category else []
        for f, op, v in self.error:
            shown = ",".join(str(x) for x in v) if isinstance(v, tuple) else str(v)
            bits.append(f"error if {f} {'∉' if op == 'in' else op} {{{shown}}}")
        bits += [f for f in self.enum_fields if f != self.category]
        bits += [*self.numeric_fields, *([self.saturation] if self.saturation else [])]
        return " · ".join(bits) or "rows in window"


# The registry IS the reader. Add a row when a writer is added; flip status to
# writer_retired when the writer is removed (the file lingers as ORPHAN until
# the gate deletes it, then the row goes). Never list logs/episodes/ here.
# llm-calls keys redundancy on prompt_norm_sha256, not prompt_sha256: the raw
# digest changes with every wrapped call (fresh delimiter nonce) and reads 0
# repeats over a week of RFC-0032 duplicates. Rows before 2026-09-12 lack it.
# skill-selection has no redundancy key for the same reason — its repeat
# reading rides llm-calls (caller core.skill_selection).
REGISTRY: tuple[Entry, ...] = (
    Entry(
        "llm-calls-*.jsonl",
        "ADR-0065",
        enum_fields=("caller", "outcome", "error_kind", "done_reason"),
        numeric_fields=("duration_ms",),
        category="caller",
        error=(("outcome", "in", ("ok",)),),
        redundancy_key=("caller", "prompt_norm_sha256"),
    ),
    Entry(
        "constitution-shadow.jsonl",
        "ADR-0092",
        enum_fields=("verdict",),
        numeric_fields=("cosine_vs_current",),
        category="verdict",
        error=(("verdict", "in", ("ok",)),),
    ),
    Entry(
        "injection-detect-*.jsonl",
        "ADR-0075",
        enum_fields=("event", "saturated"),
        numeric_fields=("total_removed",),
        category="event",
        expect_events=("guard_alive",),
    ),
    Entry(
        "verification-audit.jsonl",
        "ADR-0062",
        enum_fields=("solve_success", "verify_success", "action", "solver_path"),
        category="action",
        error=(("solve_success", "in", (True,)), ("verify_success", "in", (True,))),
    ),
    Entry(
        "weekly-pipeline-audit.jsonl",
        "ADR-0085",
        enum_fields=("event", "stage", "result", "reason"),
        category="stage",
        error=(("result", "not-in", ("fail", "failed", "verify_fail")),),
    ),
    Entry("pipeline-metrics.jsonl", "ADR-0085", enum_fields=("phase", "verdict"), category="phase"),
    Entry(
        "insight-novelty.jsonl",
        "ADR-0096",
        enum_fields=("verdict", "reason"),
        category="verdict",
        error=(("verdict", "in", ("judged",)),),
    ),
    Entry("insight-staged.jsonl", "ADR-0097"),
    Entry(
        "submolt-scope-*.jsonl",
        "ADR-0086",
        enum_fields=("event", "verdict", "subscribed"),
        category="event",
    ),
    Entry(
        "api-audit.jsonl",
        "ADR-0062",
        enum_fields=("method", "endpoint", "status"),
        numeric_fields=("rate_remaining",),
        category="endpoint",
        error=(("status", "<", 400),),
        saturation="rate_remaining",
    ),
    Entry(
        "audit.jsonl",
        "ADR-0012",
        enum_fields=("decision", "source", "command"),
        category="command",
        error=(("decision", "in", ("approved", "staged", "held")),),
    ),
    Entry(
        "skill-selection-*.jsonl",
        "ADR-0076",
        enum_fields=("kind", "verdict", "enforced", "publish_status"),
        category="kind",
        error=(("publish_status", "in", ("published",)),),
    ),
    Entry("comment-outcomes.jsonl", "ADR-0106", enum_fields=("kind", "by_self"), category="kind"),
    Entry("insight-worth.jsonl", "ADR-0097", status=WRITER_RETIRED),
    Entry("noise-*.jsonl", "ADR-0060", status=WRITER_RETIRED),
)

# Status vocabulary (closed).
OK, NO_ROWS, MISSING_EVENT = "OK", "NO_ROWS", "MISSING_EVENT"
ORPHAN, UNKNOWN, ABSENT = "ORPHAN", "UNKNOWN", "ABSENT"


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


def _short(v: object) -> str:
    """The one funnel every log-derived string passes on its way to the output.

    Length, control characters and Markdown structure are all handled here
    rather than in each renderer: this value becomes a table cell, a column
    name, a trace legend entry and a line inside a fenced block, and a
    sanitiser repeated at four sinks is a sanitiser missing from one of them.
    """
    s = "None" if v is None else str(v)
    s = md_safe(printable(s))
    return s if len(s) <= _VALUE_MAX_CHARS else s[: _VALUE_MAX_CHARS - 1] + "…"


def _compress_sequence(items: list[str]) -> str:
    """``a a a b a`` → ``a ×3, b ×1, a ×1`` — runs, not totals, so order survives."""
    out: list[str] = []
    run: str | None = None
    n = 0
    for it in items:
        if it == run:
            n += 1
            continue
        if run is not None:
            out.append(f"{run} ×{n}")
        run, n = it, 1
    if run is not None:
        out.append(f"{run} ×{n}")
    return ", ".join(out)


def collapse_runs(events: list[tuple[datetime, str]]) -> list[str]:
    """Render ``(ts, category)`` events the way syslog renders a repeat.

    Three or more consecutive events of one category, each within
    ``_COLLAPSE_GAP_S`` of the previous, become one line. Collapsing is a
    display choice: no count is lost, the ledger counted the same rows.
    """
    return [line for _, line in collapse_runs_dated(events)]


def collapse_runs_dated(events: list[tuple[datetime, str]]) -> list[tuple[datetime, str]]:
    """``collapse_runs`` with each line's own start time kept beside it.

    The printed stamp is ``HH:MM:SS``, so a caller merging several categories
    cannot order them by the text — a window spanning midnight would sort
    tomorrow's 00:00 before tonight's 23:59.
    """
    lines: list[tuple[datetime, str]] = []
    i = 0
    while i < len(events):
        j = i + 1
        while (
            j < len(events)
            and events[j][1] == events[i][1]
            and (events[j][0] - events[j - 1][0]).total_seconds() <= _COLLAPSE_GAP_S
        ):
            j += 1
        ts, cat = events[i]
        stamp = ts.astimezone(timezone.utc).strftime("%H:%M:%S")
        if j - i >= _COLLAPSE_MIN_RUN:
            span = int((events[j - 1][0] - ts).total_seconds())
            lines.append((ts, f"{stamp} {cat} ×{j - i} in {span}s"))
            i = j
        else:
            lines.append((ts, f"{stamp} {cat}"))
            i += 1
    return lines


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
    past_start = start - timedelta(weeks=_PAST_WEEKS)
    rows: list[dict] = []
    past: set[str] = set()
    id_fields: set[str] = set()
    seen_events: set[str] = set()
    for path in files:
        for rec in _iter_rows(path, r):
            dt = _parse_ts(rec.get("ts"))
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
            if entry.category and past_start <= d < start and rec.get(entry.category) is not None:
                past.add(_short(rec[entry.category]))
    r.rows, r.past_categories, r.id_fields = (
        len(rows),
        tuple(sorted(past)),
        tuple(sorted(id_fields)),
    )
    if not rows:
        r.status = NO_ROWS
        return r
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    r.frame = df.sort_values("ts", kind="stable").reset_index(drop=True)
    r.sessions = int(df["session_id"].nunique()) if "session_id" in df else 0
    r.last_ts = r.frame["ts"].iloc[-1].isoformat(timespec="seconds")
    if any(ev not in seen_events for ev in entry.expect_events):
        r.status = MISSING_EVENT
    _read_redundancy(r)
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
            (str(g[0]), tuple(_short(x) for x in g[1:])),
            len(idx),
            {_short(o): int(n) for o, n in outcome[idx].value_counts().items()},
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


def _sessioned(readings: list[Reading]) -> list[Reading]:
    """Readings whose rows carry both a session and a category — the matrix input."""
    return [
        r
        for r in readings
        if r.entry is not None
        and r.entry.category
        and not r.frame.empty
        and "session_id" in r.frame
        and r.entry.category in r.frame
    ]


def _cat_series(r: Reading) -> pd.DataFrame:
    """``session_id`` / ``cat`` / ``ts`` for one reading, nulls dropped."""
    assert r.entry is not None and r.entry.category
    df = r.frame[["session_id", r.entry.category, "ts"]].dropna()
    df.columns = pd.Index(["session_id", "cat", "ts"])
    return df.assign(cat=df["cat"].map(_short))


def _failing(series: pd.Series, op: str, value: object) -> pd.Series:
    """Rows violating one registry predicate; null / missing is not judged."""
    known = series.notna()
    if op == "in":
        return known & ~series.isin(list(value))  # type: ignore[arg-type]
    if op == "not-in":
        return known & series.isin(list(value))  # type: ignore[arg-type]
    numeric = pd.to_numeric(series, errors="coerce")
    return numeric.notna() & (numeric >= value if op == "<" else numeric < value)


def session_matrix(readings: list[Reading]) -> tuple[pd.DataFrame, list[str]]:
    """Sessions × derived columns, plus the columns that are zero everywhere.

    Rows are the union of every session id in any log, so a session that wrote
    nothing to one log is a row of zeros there. Columns are the union of this
    window's categories and the previous four weeks', so a category that
    stopped appearing is a column of zeros rather than no column. Both are then
    ordinary rows and columns of the outlier scan.
    """
    sessions: set[str] = set()
    for r in readings:
        if not r.frame.empty and "session_id" in r.frame:
            sessions.update(r.frame["session_id"].dropna().astype(str))
    index = pd.Index(sorted(sessions), name="session_id")
    cols: dict[str, pd.Series] = {}
    absent: list[str] = []
    if index.empty:
        return pd.DataFrame(index=index), absent
    for r in _sessioned(readings):
        absent += _category_columns(r, index, cols)
    for r in readings:
        _log_columns(r, index, cols)
    matrix = pd.DataFrame(cols, index=index)
    ratios = {sid: _compress_ratio(seq) for sid, seq in _traces(readings).items()}
    matrix["compress"] = pd.Series(ratios).reindex(index)
    return matrix, absent


def _category_columns(r: Reading, index: pd.Index, cols: dict[str, pd.Series]) -> list[str]:
    """Count / busiest-minute / minimum-gap columns for one log; zero columns named."""
    assert r.entry is not None
    key, d = r.entry.key, _cat_series(r)
    counts = d.pivot_table(index="session_id", columns="cat", aggfunc="size", fill_value=0)
    per_min = (
        d.groupby(["session_id", "cat", d["ts"].dt.floor("min")])
        .size()
        .groupby(level=[0, 1])
        .max()
        .unstack(fill_value=0)
    )
    gaps = d.groupby(["session_id", "cat"])["ts"].diff().dt.total_seconds()
    # A minimum over one or two intervals is not a rate reading — it is the
    # sample. Below _MIN_GAP_EVENTS the cell is absent rather than extreme;
    # a session that made two calls instead of six already says so in the
    # count column. Without this the gap axis, being ratio-scaled and
    # heavy-tailed, fills the outlier list with sparse sessions.
    min_gap = gaps.groupby([d["session_id"], d["cat"]]).min().unstack()
    sparse = counts.reindex_like(min_gap).fillna(0) < _MIN_GAP_EVENTS
    min_gap = min_gap.mask(sparse)
    for cat in counts.columns:
        cols[f"{key}:{cat}"] = counts[cat].reindex(index, fill_value=0)
        cols[f"{key}:{cat} /1m"] = per_min[cat].reindex(index, fill_value=0)
        cols[f"{key}:{cat} gap s"] = min_gap[cat].reindex(index)
    absent = [f"{key}:{c}" for c in r.past_categories if f"{key}:{c}" not in cols]
    for col in absent:
        cols[col] = pd.Series(0, index=index)
    return absent


def _log_columns(r: Reading, index: pd.Index, cols: dict[str, pd.Series]) -> None:
    """Per-log columns: errors, numeric sums, saturation minimum."""
    if r.entry is None or r.frame.empty or "session_id" not in r.frame:
        return
    key, df = r.entry.key, r.frame
    sid = df["session_id"].astype(str)
    if r.entry.error:
        bad = pd.Series(False, index=df.index)
        for f, op, value in r.entry.error:
            if f in df:
                bad |= _failing(df[f], op, value)
        cols[f"{key} errors"] = bad.groupby(sid).sum().reindex(index, fill_value=0)
    for f in r.entry.numeric_fields:
        if f in df and f != r.entry.saturation:
            total = pd.to_numeric(df[f], errors="coerce").groupby(sid).sum()
            cols[f"{key} {f} Σ"] = total.reindex(index, fill_value=0)
    if r.entry.saturation and r.entry.saturation in df:
        low = pd.to_numeric(df[r.entry.saturation], errors="coerce").groupby(sid).min()
        cols[f"{key} {r.entry.saturation} min"] = low.reindex(index)


def _compress_ratio(seq: list[str]) -> float:
    """zlib ratio of the session's category stream — a tripwire for repetition."""
    raw = "".join(seq).encode("utf-8")
    return round(len(raw) / max(len(zlib.compress(raw, 6)), 1), 2) if raw else 0.0


def _letters(readings: list[Reading]) -> dict[str, str]:
    """One character per ``log:category``, most frequent first, for the trace."""
    pool = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    counts: dict[str, int] = {}
    for r in _sessioned(readings):
        assert r.entry is not None
        for cat, n in _cat_series(r)["cat"].value_counts().items():
            counts[f"{r.entry.key}:{cat}"] = int(n)
    ordered = sorted(counts, key=lambda c: (-counts[c], c))
    return {c: (pool[i] if i < len(pool) else "?") for i, c in enumerate(ordered)}


def _events(readings: list[Reading]) -> pd.DataFrame:
    """Every sessioned event of every log as ``session_id`` / ``cat`` / ``ts``."""
    frames = []
    for r in _sessioned(readings):
        assert r.entry is not None
        d = _cat_series(r)
        frames.append(d.assign(cat=r.entry.key + ":" + d["cat"]))
    if not frames:
        return pd.DataFrame(columns=["session_id", "cat", "ts"])
    return pd.concat(frames, ignore_index=True).sort_values(["ts", "cat"], kind="stable")


def _traces(readings: list[Reading]) -> dict[str, list[str]]:
    """Per session, the letters of its events in ts order."""
    letters, ev = _letters(readings), _events(readings)
    if ev.empty:
        return {}
    ev = ev.assign(letter=ev["cat"].map(letters).fillna("?"))
    return {str(sid): list(g["letter"]) for sid, g in ev.groupby("session_id", sort=True)}


def _render_census_table(readings: list[Reading]) -> list[str]:
    non_ok = [r for r in readings if r.status != OK]
    head = (
        "**"
        + ", ".join(f"{r.status} `{md_safe(r.name)}`" for r in non_ok)
        + "** — the Saturday gate edits `REGISTRY` in `scripts/instrument_census.py` "
        "(register / retire) or removes the file."
        if non_ok
        else "All registered logs wrote this window; no unregistered files."
    )
    lines = [head, "", "| Status | Log | Files | Rows in window | Sessions | Last ts | Question |"]
    lines.append("|---|---|---|---|---|---|---|")
    for r in readings:
        q = md_safe(r.entry.question) if r.entry else "not in REGISTRY — register or retire"
        lines.append(
            f"| {r.status} | `{md_safe(r.name)}` | {r.files} | {r.rows} | {r.sessions} | "
            f"{r.last_ts or '—'} | {q} |"
        )
    # Out-of-window rows are the file's history and expected; rows the census
    # could not place (no ts) or parse are a defect and are named.
    skipped = [r for r in readings if r.rows_without_ts or r.parse_failures]
    if skipped:
        lines += [
            "",
            "Rows not counted: "
            + "; ".join(
                f"`{md_safe(r.name)}` no-ts {r.rows_without_ts}, unparsable {r.parse_failures}"
                for r in skipped
            ),
        ]
    return lines


def _render_distributions(readings: list[Reading]) -> list[str]:
    lines = ["### Distributions", ""]
    for r in readings:
        if r.entry is None or r.frame.empty:
            continue
        parts: list[str] = []
        for f in r.entry.enum_fields:
            counts = r.frame[f].dropna().map(_short).value_counts() if f in r.frame else None
            if counts is None or counts.empty:
                continue
            top = ", ".join(f"{v} {n}" for v, n in counts.head(_TOP_VALUES).items())
            more = len(counts) - _TOP_VALUES
            parts.append(f"  - `{f}`: {top}" + (f" (+{more} more)" if more > 0 else ""))
        for f in r.entry.numeric_fields:
            vals = pd.to_numeric(r.frame[f], errors="coerce").dropna() if f in r.frame else None
            if vals is None or vals.empty:
                continue
            parts.append(
                f"  - `{f}`: min {vals.min():.3g} · median {vals.median():.3g} · "
                f"max {vals.max():.3g} (n={len(vals)})"
            )
        if parts:
            lines += [f"- `{md_safe(r.name)}`", *parts]
    if len(lines) == 2:
        lines.append("No distributions (no declared fields with rows in window).")
    return lines


def _render_redundancy(readings: list[Reading]) -> list[str]:
    lines = ["### Redundancy (same key repeated within one session)", ""]
    for r in readings:
        if r.entry is None or not r.entry.redundancy_key or r.frame.empty:
            continue
        lines.append(
            f"- `{md_safe(r.name)}` key = ({' + '.join(r.entry.redundancy_key)}): "
            f"{r.redundant_keys} keys repeated, {r.redundant_calls} redundant calls (Σ n−1), "
            f"max repeat {max((n for _, n, _ in r.redundancy), default=0)}"
        )
        for (sid, key), n, outs in r.redundancy:
            outs_s = ", ".join(f"{o} {c}" for o, c in outs.items())
            lines.append(f"  - ×{n} `{' / '.join(key)}` session {md_safe(sid[:12])} → {outs_s}")
    if len(lines) == 2:
        lines.append("No redundancy keys with rows in window.")
    return lines


def _squeeze(text: str, width: int) -> str:
    """Shorten from the middle — both ends carry the distinguishing part of a name."""
    if len(text) <= width:
        return text
    head = width // 2 - 1
    return text[:head] + "…" + text[-(width - head - 1) :]


def _ledger_labels(columns: list[str]) -> list[str]:
    """Short headers for the ledger — a markdown table pads every cell to its header.

    Sixteen columns named ``api-audit:GET /posts/{id}/comments /1m`` cost more
    bytes in padding than in data. The log prefix and any dotted namespace go
    first; when that makes two columns look alike, the pair falls back to a
    middle-squeezed form of the full name, which keeps both the log and the tail
    that distinguishes them. The outlier table always prints the full name.
    """
    short = []
    for col in columns:
        label = col.split(":", 1)[-1]
        head, _, axis = label.partition(" ")
        short.append((head.rsplit(".", 1)[-1] + (f" {axis}" if axis else "")).strip())
    return [
        _squeeze(col if short.count(s) > 1 else s, _LEDGER_LABEL)
        for col, s in zip(columns, short, strict=True)
    ]


def _render_ledger(matrix: pd.DataFrame) -> list[str]:
    lines = ["### Session ledger (one row per session, one column per log:category)", ""]
    if matrix.empty:
        return lines + ["No sessions in window."]
    # Ranked by median, not by sum: the ledger should show what a typical
    # session does. A column that is enormous in one session and zero in the
    # other twenty-seven has a huge sum and belongs to the outlier table, which
    # is where it lands.
    countish = [c for c in matrix.columns if not c.endswith("gap s")]
    shown = sorted(
        sorted(countish, key=lambda c: (-float(matrix[c].median()), -float(matrix[c].sum())))[
            :_LEDGER_COLS
        ]
    )
    table = matrix[shown].copy()
    table.loc["median"] = matrix[shown].median()
    table.columns = pd.Index(_ledger_labels(shown))
    table.index = pd.Index([str(s)[:8] for s in table.index], name="session")
    # Per-column formatting: an integral column prints without a decimal tail,
    # and no column prints in scientific notation (a duration sum rendered as
    # 2.09413e+06 is both wider and less readable than 2094130). The median row
    # is what makes some count columns non-integral, so the choice is per
    # column and made after that row exists.
    # The leading entry is for the index column that to_markdown prints first;
    # without it every format lands one column to the left.
    fmts = ["s"] + [".0f" if (table[c].dropna() % 1 == 0).all() else ".2f" for c in table.columns]
    return lines + [
        f"{len(matrix)} sessions × {len(matrix.columns)} derived columns; the {len(shown)} "
        "with the largest median are shown (the outlier scan uses all of them, full names "
        "there). `/1m` = busiest single minute, `Σ` = per-session sum.",
        "",
        table.round(2).to_markdown(floatfmt=fmts),
        "",
        "The `median` row is this window's representative session; previous reports carry "
        "the earlier ones (no cross-week comparison is computed here).",
    ]


def _render_trace(readings: list[Reading]) -> list[str]:
    lines = ["### Session trace (all logs, ts order, run-length)", ""]
    letters, traces = _letters(readings), _traces(readings)
    if not traces:
        return lines + ["No sessioned events in window."]
    lines += [" · ".join(f"`{ch}` {cat}" for cat, ch in letters.items()), "", "```"]
    for sid, seq in traces.items():
        runs = _compress_sequence(seq).split(", ")
        head = " ".join(runs[:_TRACE_RUNS]).replace(" ×", "×")
        tail = f" … +{len(runs) - _TRACE_RUNS} runs" if len(runs) > _TRACE_RUNS else ""
        lines.append(f"{sid[:8]} {head}{tail}")
    return lines + ["```"]


def _render_strips(readings: list[Reading]) -> list[str]:
    lines = [f"### Session strips (rows per minute, first {_STRIP_MINUTES} minutes)", ""]
    ranked = sorted(_sessioned(readings), key=lambda r: -r.rows)[:2]
    if not ranked:
        return lines + ["No sessioned events in window."]
    for r in ranked:
        assert r.entry is not None
        d = _cat_series(r)
        if d.empty:
            continue  # every row's category was null — nothing to band
        starts = d.groupby("session_id")["ts"].min()
        minute = ((d["ts"] - d["session_id"].map(starts)).dt.total_seconds() // 60).astype(int)
        inside = d.assign(m=minute)[lambda x: (x["m"] >= 0) & (x["m"] < _STRIP_MINUTES)]
        per = inside.groupby(["session_id", "m"]).size()
        if per.empty:
            continue
        scale = int(per.max())
        lines += [
            f"`{md_safe(r.entry.key)}` — `{_STRIP_RAMP[-1]}` = {scale}/min, `{_STRIP_RAMP[0]}` = 0",
            "```",
        ]
        for sid, g in per.groupby(level=0):
            counts = g.droplevel(0)
            chars = "".join(
                # A minute with rows is never the zero glyph: floor it at the
                # first step, or a session with one busy minute renders its
                # other fifty-nine as empty.
                _STRIP_RAMP[min(max(int(counts.get(m, 0)) * 8 // scale, 1), 8)]
                if counts.get(m, 0)
                else _STRIP_RAMP[0]
                for m in range(_STRIP_MINUTES)
            )
            lines.append(f"{str(sid)[:8]} {r.entry.key[:3]} {chars}")
        lines.append("```")
    return lines


def _render_id_repeats(readings: list[Reading]) -> list[str]:
    lines = ["### Id-field repeats (same value inside one session, fields found by name)", ""]
    rows = []
    for r in readings:
        if r.entry is None or r.frame.empty or "session_id" not in r.frame:
            continue
        for f in r.id_fields:
            counts = r.frame.dropna(subset=[f]).groupby(["session_id", f]).size()
            if counts.empty:
                continue
            per_session = counts.groupby(level=0).max()
            rows.append(
                {
                    "log": r.entry.key,
                    "field": f,
                    "sessions": int(per_session.size),
                    "median max repeat": float(per_session.median()),
                    "max repeat": int(per_session.max()),
                    "in session": str(per_session.idxmax())[:8],
                }
            )
    if not rows:
        return lines + ["No id-shaped fields with rows in window."]
    return lines + [pd.DataFrame(rows).to_markdown(index=False)]


def _is_ratio_scale(column: str) -> bool:
    """Durations and sums are ratio-scaled: a departure is a multiple, not a difference.

    Scored on ``log1p``, so "five seconds where the others take one" and "five
    hundred where the others take a hundred" read alike. Without it a
    heavy-tailed second-scale column produces four-digit z scores and fills the
    whole list while a count doubling is invisible beside it (measured
    2026-09-12 on the 09-05 – 09-11 window).
    """
    return column.endswith((" gap s", " Σ"))


def _modified_z(values: pd.Series, *, ratio_scale: bool = False) -> pd.Series:
    """Iglewicz & Hoaglin (1993) modified z, with a unit floor where MAD = 0.

    When every session holds the same number the MAD is zero and the usual
    formula is an infinity. Iglewicz & Hoaglin substitute the mean absolute
    deviation; that is finite but saturates — with one departing session out of
    n it returns the same score whatever the size of the departure, so every
    constant column ties. The floor used instead is **one unit of the column**:
    on a column that never varies, one count (or, in log space, one e-fold) is
    the smallest departure that means anything, and the score then grows with
    the departure. A column where nothing departs still scores zero.

    The floor sets the sensitivity on constant columns: a departure must reach
    ``_Z_THRESHOLD * 1.4826`` ≈ 5.2 units to be listed. A category everyone
    calls three times that one session never calls is therefore *not* flagged
    here — it is visible as a zero in the ledger, and the id-repeat and
    redundancy sections carry the small-count shapes.
    """
    x = pd.to_numeric(values, errors="coerce")
    if not x.notna().any():
        return pd.Series(dtype=float)
    if ratio_scale:
        x = np.log1p(x.clip(lower=0))
    med = float(np.nanmedian(x))
    mad = float(np.nanmedian(np.abs(x - med)))
    return (x - med) / (1.4826 * (mad if mad > 0 else 1.0))


def outliers(matrix: pd.DataFrame) -> list[dict]:
    """The strongest departures, one per column and one per session, z descending.

    Both deduplications are load-bearing. Without the per-column one a single
    broad column takes every slot; without the per-session one a single unusual
    session takes four of five with four views of the same fact (both measured
    2026-09-12 on the 09-05 – 09-11 window). The reading is "one session unlike
    the others", so five rows should name five sessions. Everything omitted is
    still in the ledger and the hunting window. ``_UNRANKED`` columns do not
    compete here: a zlib ratio summarises the trace rather than being an axis
    of it, and is not on the scale of a count.
    """
    found: list[dict] = []
    for col in matrix.columns:
        if str(col) in _UNRANKED:
            continue
        values = pd.to_numeric(matrix[col], errors="coerce")
        z = _modified_z(values, ratio_scale=_is_ratio_scale(str(col)))
        if z.empty:
            continue
        med = float(np.nanmedian(values))
        found += [
            {
                "z": round(float(score), 1),
                "column": str(col),
                "session": str(sid)[:8],
                "value": round(float(values[sid]), 2),
                "median": round(med, 2),
                "MAD": round(float(np.nanmedian(np.abs(values - med))), 2),
            }
            for sid, score in z.dropna().items()
            if abs(score) >= _Z_THRESHOLD
        ]
    found.sort(key=lambda d: (-abs(d["z"]), d["column"], d["session"]))
    picked: list[dict] = []
    for item in found:
        if any(p["column"] == item["column"] or p["session"] == item["session"] for p in picked):
            continue
        picked.append(item)
        if len(picked) >= _MAX_OUTLIERS:
            break
    return picked


def _render_outliers(found: list[dict], absent: list[str], matrix: pd.DataFrame) -> list[str]:
    lines = [
        f"### Within-week outliers (median / MAD over sessions, |modified z| ≥ {_Z_THRESHOLD})",
        "",
        pd.DataFrame(found).to_markdown(index=False)
        if found
        else "No session departed from the others on any derived column.",
    ]
    for col in _UNRANKED:
        if col not in matrix:
            continue
        z = _modified_z(matrix[col])
        hits = z[z.abs() >= _Z_THRESHOLD].dropna()
        if not hits.empty:
            lines += [
                "",
                f"`{col}` (not ranked above): "
                + ", ".join(
                    f"{str(sid)[:8]} {matrix.loc[sid, col]:.2f} (z {score:.1f})"
                    for sid, score in hits.items()
                )
                + f" against a median of {float(np.nanmedian(matrix[col])):.2f}.",
            ]
    if absent:
        lines += [
            "",
            f"Absent this window, present in the previous {_PAST_WEEKS} weeks: "
            + ", ".join(f"`{md_safe(c)}`" for c in sorted(absent))
            + " — zero in every session, so no departure is computed.",
        ]
    return lines


def _render_hunting(readings: list[Reading], found: list[dict]) -> list[str]:
    lines = ["### Hunting windows (peak minutes, consecutive same-category events collapsed)", ""]
    ev = _events(readings)
    if not found or ev.empty:
        return lines + ["No outliers to hunt." if not found else "No sessioned events in window."]
    seen: set[str] = set()
    for item in found:
        if len(seen) >= _HUNT_SESSIONS or item["session"] in seen:
            continue
        seen.add(item["session"])
        rows = ev[ev["session_id"].astype(str).str.startswith(item["session"])]
        if rows.empty:
            continue
        peak = rows.groupby(rows["ts"].dt.floor("min")).size().idxmax()
        lo, hi = peak - timedelta(minutes=_HUNT_SPREAD), peak + timedelta(minutes=_HUNT_SPREAD)
        window = rows[(rows["ts"] >= lo) & (rows["ts"] <= hi)].sort_values("ts", kind="stable")
        # Collapse each category's own stream, then re-interleave by time. Two
        # endpoints called alternately are two repeats, not twenty-four
        # singletons; the raw interleaving is what the trace section carries.
        # Collapsing the mixed stream prints every burst in full and then hits
        # the line cap (measured 2026-09-12 on the 09-05 – 09-11 window).
        collapsed = [
            line
            for _, line in sorted(
                (
                    item
                    for _, g in window.groupby("cat", sort=True)
                    for item in collapse_runs_dated(
                        [
                            (ts.to_pydatetime(), str(c))
                            for ts, c in zip(g["ts"], g["cat"], strict=True)
                        ]
                    )
                ),
                key=lambda item: item[0],
            )
        ]
        lines += [
            f"`{item['session']}` around {peak.strftime('%Y-%m-%d %H:%M')}Z "
            f"({item['column']} = {item['value']}, z {item['z']}):",
            "```",
            *collapsed[:_HUNT_LINES],
        ]
        if len(collapsed) > _HUNT_LINES:
            lines.append(f"… +{len(collapsed) - _HUNT_LINES} more lines")
        lines += ["```", ""]
    return lines


def render_markdown(readings: list[Reading], *, start: date, end: date, logs_dir: Path) -> str:
    matrix, absent = session_matrix(readings)
    found = outliers(matrix)
    lines = [
        "## Instrument Census",
        "",
        f"Window: {start} – {end} (by `ts`, UTC date). Source: `{logs_dir}` — self-written "
        "JSONL only; `episodes/` and `*.log` are never opened here (ADR-0107). Readings, not "
        "verdicts. A session is compared with the other sessions of this window, so a fault "
        "present in every session since it began departs from nothing: that shape belongs to "
        "Redundancy and to the reader of the ledger's absolute values (ADR-0110).",
        "",
    ]
    for block in (
        _render_census_table(readings),
        _render_distributions(readings),
        _render_redundancy(readings),
        _render_ledger(matrix),
        _render_trace(readings),
        _render_strips(readings),
        _render_id_repeats(readings),
        _render_outliers(found, absent, matrix),
        _render_hunting(readings, found),
    ):
        lines += [*block, ""]
    return "\n".join(lines).rstrip() + "\n"


def run(home: Path, start: date, end: date) -> str:
    logs_dir = home / "logs"
    return render_markdown(census(logs_dir, start, end), start=start, end=end, logs_dir=logs_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Instrument census over self-written logs (ADR-0107 / ADR-0110)."
    )
    parser.add_argument("--home", type=Path, required=True, help="MOLTBOOK_HOME")
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="YYYY-MM-DD incl.")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="YYYY-MM-DD incl.")
    args = parser.parse_args(argv)
    try:
        print(run(args.home, args.start, args.end))
    except Exception as exc:  # observability only — never break the weekly chain
        print(
            "## Instrument Census\n\nunavailable "
            f"(reason=exception: {type(exc).__name__}: {md_safe(str(exc))})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
