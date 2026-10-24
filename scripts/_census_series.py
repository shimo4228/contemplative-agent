"""Aggregation and statistics over the readings — the series layer.

Layer 2 of three (ADR-0110). Everything here turns ``Reading`` objects into
numbers: the session × derived-column matrix whose columns are derived from the
data rather than declared, the per-session event trace, and the within-week
outlier scan with its three calibrations. It renders nothing and reads no file.

Imports ``_census_registry`` for the row schema; imported by
``instrument_census``, which draws what this computes.

Two readings are not session-shaped and live at the bottom: the Saturday gate's
own record (decisions per gate, recommendation/decision agreement, the gates
bundled from ``audit.jsonl`` and ``insight-staged.jsonl`` — P2-01.1) and the
reply-target retry loop in ``skill-selection-*.jsonl`` (P2-01.8).
"""

from __future__ import annotations

import zlib
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
from _census_registry import Reading, short
from _stats import MIN_DENOMINATOR, format_rate

Z_THRESHOLD = 3.5  # Iglewicz & Hoaglin (1993)
_MAX_OUTLIERS = 5
_COLLAPSE_GAP_S = 2.0
_COLLAPSE_MIN_RUN = 3
_MIN_GAP_EVENTS = 4  # a minimum gap needs at least three intervals to mean anything
UNRANKED = ("compress",)  # read in the ledger, not ranked against the event axes


def compress_sequence(items: list[str]) -> str:
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


def sessioned(readings: list[Reading]) -> list[Reading]:
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


def cat_series(r: Reading) -> pd.DataFrame:
    """``session_id`` / ``cat`` / ``ts`` for one reading, nulls dropped."""
    assert r.entry is not None and r.entry.category
    df = r.frame[["session_id", r.entry.category, "ts"]].dropna()
    df.columns = pd.Index(["session_id", "cat", "ts"])
    return df.assign(cat=df["cat"].map(short))


def _failing(series: pd.Series, op: str, value: object) -> pd.Series:
    """Rows violating one registry predicate; null / missing is not judged."""
    known = series.notna()
    if op == "in-range":
        # Half-open [lo, hi). Unlike every other op a null / non-numeric value
        # IS judged (it fails): a transport row carries ``status: null`` and
        # reading it as "not judged" made an outage week an error rate of 0.
        lo, hi = value  # type: ignore[misc]
        numeric = pd.to_numeric(series, errors="coerce")
        return ~(numeric.notna() & (numeric >= lo) & (numeric < hi))
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
    for r in sessioned(readings):
        absent += _category_columns(r, index, cols)
    for r in readings:
        _log_columns(r, index, cols)
    matrix = pd.DataFrame(cols, index=index)
    # zlib ratio of each session's category stream — a tripwire for repetition.
    ratios = {
        sid: round(len(raw) / max(len(zlib.compress(raw, 6)), 1), 2) if raw else 0.0
        for sid, raw in (
            (sid, "".join(seq).encode("utf-8")) for sid, seq in traces(readings).items()
        )
    }
    matrix["compress"] = pd.Series(ratios).reindex(index)
    return matrix, absent


def _category_columns(r: Reading, index: pd.Index, cols: dict[str, pd.Series]) -> list[str]:
    """Count / busiest-minute / minimum-gap columns for one log; zero columns named."""
    assert r.entry is not None
    key, d = r.entry.key, cat_series(r)
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
            elif op == "in-range":
                bad |= True  # the field never appeared: no row proves a success
        cols[f"{key} errors"] = bad.groupby(sid).sum().reindex(index, fill_value=0)
    for f in r.entry.numeric_fields:
        if f in df and f != r.entry.saturation:
            total = pd.to_numeric(df[f], errors="coerce").groupby(sid).sum()
            cols[f"{key} {f} Σ"] = total.reindex(index, fill_value=0)
    if r.entry.saturation and r.entry.saturation in df:
        low = pd.to_numeric(df[r.entry.saturation], errors="coerce").groupby(sid).min()
        cols[f"{key} {r.entry.saturation} min"] = low.reindex(index)


def letters(readings: list[Reading]) -> dict[str, str]:
    """One character per ``log:category``, most frequent first, for the trace."""
    pool = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    counts: dict[str, int] = {}
    for r in sessioned(readings):
        assert r.entry is not None
        for cat, n in cat_series(r)["cat"].value_counts().items():
            counts[f"{r.entry.key}:{cat}"] = int(n)
    ordered = sorted(counts, key=lambda c: (-counts[c], c))
    # Past the pool every category shares "?", which merges distinct events into
    # one run and inflates the zlib ratio that exists to detect repetition. The
    # legend says so rather than letting the tripwire read high silently.
    return {c: (pool[i] if i < len(pool) else "?") for i, c in enumerate(ordered)}


def events(readings: list[Reading]) -> pd.DataFrame:
    """Every sessioned event of every log as ``session_id`` / ``cat`` / ``ts``."""
    frames = []
    for r in sessioned(readings):
        assert r.entry is not None
        d = cat_series(r)
        frames.append(d.assign(cat=r.entry.key + ":" + d["cat"]))
    if not frames:
        return pd.DataFrame(columns=["session_id", "cat", "ts"])
    return pd.concat(frames, ignore_index=True).sort_values(["ts", "cat"], kind="stable")


def traces(readings: list[Reading]) -> dict[str, list[str]]:
    """Per session, the letters of its events in ts order."""
    alphabet, ev = letters(readings), events(readings)
    if ev.empty:
        return {}
    ev = ev.assign(letter=ev["cat"].map(alphabet).fillna("?"))
    return {str(sid): list(g["letter"]) for sid, g in ev.groupby("session_id", sort=True)}


def modified_z(values: pd.Series, *, ratio_scale: bool = False) -> pd.Series:
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
    ``Z_THRESHOLD * 1.4826`` ≈ 5.2 units to be listed. A category everyone
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
    still in the ledger and the hunting window. ``UNRANKED`` columns do not
    compete here: a zlib ratio summarises the trace rather than being an axis
    of it, and is not on the scale of a count.
    """
    found: list[dict] = []
    for col in matrix.columns:
        if str(col) in UNRANKED:
            continue
        values = pd.to_numeric(matrix[col], errors="coerce")
        # Gaps and sums are ratio-scaled — a departure in them is a multiple,
        # not a difference — so they are scored on log1p (ADR-0110 D5).
        z = modified_z(values, ratio_scale=str(col).endswith((" gap s", " Σ")))
        if z.empty:
            continue
        med = float(np.nanmedian(values))
        # value / median / MAD are printed in raw units even where z was scored
        # on log1p, so those rows say "(log z)": a reader recomputing
        # (value − median) / (1.4826·MAD) would otherwise get a different number.
        ratio = str(col).endswith((" gap s", " Σ"))
        found += [
            {
                "z": round(float(score), 1),
                "column": str(col) + (" (log z)" if ratio else ""),
                "session": str(sid)[:8],
                "session_id": str(sid),
                "value": round(float(values[sid]), 2),
                "median": round(med, 2),
                "MAD": round(float(np.nanmedian(np.abs(values - med))), 2),
            }
            for sid, score in z.dropna().items()
            if abs(score) >= Z_THRESHOLD
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


# --- The gate record (P2-01.1) ----------------------------------------------
#
# ``pipeline-metrics.jsonl`` is written by the Saturday gate (weekly-gate Step
# 0 / 1c / 7) with ``pipeline_audit.py``: ``gate_record`` carries the counts,
# ``gate_item`` one recommendation/decision pair per ruled item. These are
# readings of that record, joined to the two logs that hold the same decisions
# at item level. Nothing is written and no verdict is made.

# gate_record counts that are rulings. ``*_held`` is a deferral and is left out.
GATE_DECISION_FIELDS = (
    "insight_adopted",
    "insight_rejected",
    "deadcode_deleted",
    "deadcode_whitelisted",
    "skills_archived",
)
# ADR-0099 Review-when: "agreement with the briefing recommendations runs at
# ~100% sustained" triggers one retrospective lens audit (D-P2-01-2).
AGREEMENT_REVIEW_WHEN = 1.0


def _reading(readings: list[Reading], glob: str) -> pd.DataFrame:
    for r in readings:
        if r.entry is not None and r.entry.glob == glob and not r.frame.empty:
            return r.frame
    return pd.DataFrame()


def _num(frame: pd.DataFrame, col: str) -> pd.Series:
    if col not in frame:
        return pd.Series(0, index=frame.index, dtype="int64")
    return pd.to_numeric(frame[col], errors="coerce").fillna(0).astype("int64")


def _day(frame: pd.DataFrame) -> pd.Series:
    return frame["ts"].dt.tz_convert("UTC").dt.date


def gate_decisions(pm: pd.DataFrame) -> list[dict]:
    """One row per gate day: rulings in ``gate_record`` and ``gate_item`` rows."""
    if pm.empty or "event" not in pm:
        return []
    rec = pm[pm["event"] == "gate_record"]
    if rec.empty:
        return []
    items = pm[pm["event"] == "gate_item"]
    item_days = _day(items) if not items.empty else pd.Series(dtype=object)
    out = []
    for day, g in rec.groupby(_day(rec), sort=True):
        total = int(sum(_num(g, f).sum() for f in GATE_DECISION_FIELDS))
        out.append(
            {
                "date": str(day),
                "decisions": total,
                "gate_items": int((item_days == day).sum()) if not items.empty else 0,
            }
        )
    return out


def gate_agreement(pm: pd.DataFrame) -> list[dict]:
    """``recommendation == decision`` per ``gate_item`` category, plus the whole.

    ``category=roadmap`` rows carry the option letter in both fields (``A|B|C``),
    the others adopt / reject / hold; either way the two are compared as text.
    A row missing either side is not counted — it is neither agreement nor
    disagreement. The rate is printed with its interval (P2-01.9); under ten
    rows only the counts are.
    """
    need = {"event", "category", "recommendation", "decision"}
    if pm.empty or not need <= set(pm.columns):
        return []
    items = pm[(pm["event"] == "gate_item")].dropna(subset=["recommendation", "decision"])
    items = items[items["recommendation"].astype(str) != "closed"]
    items = items[items["decision"].astype(str) != "closed"]
    if items.empty:
        return []
    items = items.assign(
        cat=items["category"].map(short),
        agree=items["recommendation"].astype(str) == items["decision"].astype(str),
    )
    rows = []
    for cat, g in sorted(items.groupby("cat"), key=lambda kv: kv[0]):
        rows.append(_agreement_row(str(cat), int(g["agree"].sum()), len(g)))
    rows.append(_agreement_row("(all)", int(items["agree"].sum()), len(items)))
    return rows


def _agreement_row(category: str, agree: int, n: int) -> dict:
    return {
        "category": category,
        "agree": agree,
        "n": n,
        "agreement": format_rate(agree, n),
        "review_when": n >= MIN_DENOMINATOR and agree / n >= AGREEMENT_REVIEW_WHEN,
    }


def _audit_counts(audit: pd.DataFrame, staged: pd.DataFrame, lo: date | None, hi: date) -> dict:
    """Counts for gate days in ``(lo, hi]`` (``lo`` None = from the window start)."""

    def within(frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame
        d = _day(frame)
        keep = d <= hi
        return frame[keep & (d > lo)] if lo is not None else frame[keep]

    a = within(audit)
    n_staged = len(within(staged))
    if a.empty:
        return {"staged": n_staged, "adopted": 0, "rejected": 0, "archived": 0}
    cmd = a["command"] if "command" in a else pd.Series("", index=a.index)
    src = a["source"].fillna("").astype(str) if "source" in a else pd.Series("", index=a.index)
    dec = a["decision"] if "decision" in a else pd.Series("", index=a.index)
    insight = cmd == "insight"
    return {
        "staged": n_staged,
        "adopted": int((insight & (dec == "approved")).sum()),
        "rejected": int((insight & (dec == "rejected")).sum()),
        "archived": int(
            (src.eq("stage-archived-names") | src.str.startswith("direct-archive")).sum()
        ),
    }


def gate_bundles(pm: pd.DataFrame, audit: pd.DataFrame, staged: pd.DataFrame) -> list[dict]:
    """Gates as ``{date, staged, adopted, rejected, archived, exceptions}``.

    A gate is a day with a ``gate_record``. Its bundle is everything the two
    item-level logs hold in ``(previous gate day, this gate day]`` — ``staged``
    from ``insight-staged.jsonl`` rows, ``adopted`` / ``rejected`` from the
    ``insight`` audit rows, ``archived`` from the skill-retirement sources. No
    writer is added: the bundle is a join. Where ``gate_record`` states the same
    count (``insight_adopted`` / ``insight_rejected`` / ``skills_archived``) and
    the two differ, the difference is named in ``exceptions`` rather than
    reconciled. The first gate of the window is bundled from the window start,
    so read it with a window that begins a gate earlier.
    """
    if pm.empty or "event" not in pm:
        return []
    rec = pm[pm["event"] == "gate_record"]
    if rec.empty:
        return []
    days = sorted(set(_day(rec)))
    out, prev = [], None
    for day in days:
        counts = _audit_counts(audit, staged, prev, day)
        stated = rec[_day(rec) == day]
        exceptions = []
        for field, key in (
            ("insight_adopted", "adopted"),
            ("insight_rejected", "rejected"),
            ("skills_archived", "archived"),
        ):
            if field in stated and stated[field].notna().any():
                said = int(_num(stated, field).sum())
                if said != counts[key]:
                    exceptions.append(f"{field} gate_record {said} vs log {counts[key]}")
        out.append({"date": str(day), **counts, "exceptions": exceptions})
        prev = day
    return out


def gate_record(readings: list[Reading]) -> dict:
    """Everything the gate section draws, from the registered readings."""
    pm = _reading(readings, "pipeline-metrics.jsonl")
    return {
        "decisions": gate_decisions(pm),
        "agreement": gate_agreement(pm),
        "gates": gate_bundles(
            pm, _reading(readings, "audit.jsonl"), _reading(readings, "insight-staged.jsonl")
        ),
    }


# --- Reply-target retry loop (P2-01.8) --------------------------------------

LOOP_MIN_SESSIONS = 2


def reply_retry_loops(readings: list[Reading]) -> list[dict]:
    """``reply_key_sha256`` values that failed ``404`` + ``unknown`` in 2+ sessions.

    The shape of a target the other agent deleted: the dedup key is retired only
    by ``parent_rejected`` (``reply_handler``), so an ``unknown`` 404 stays
    retryable and comes back next session. Names the digest and the sessions,
    never a body. Nothing here retires anything.
    """
    frame = _reading(readings, "skill-selection-*.jsonl")
    need = {"reply_key_sha256", "failure_reason", "http_status", "session_id"}
    if frame.empty or not need <= set(frame.columns):
        return []
    hit = frame[
        (frame["failure_reason"].astype(str) == "unknown")
        & (pd.to_numeric(frame["http_status"], errors="coerce") == 404)
    ].dropna(subset=["reply_key_sha256", "session_id"])
    if hit.empty:
        return []
    out = []
    for key, g in hit.groupby("reply_key_sha256"):
        sessions = g["session_id"].astype(str).nunique()
        if sessions >= LOOP_MIN_SESSIONS:
            out.append({"reply_key": str(key)[:12], "sessions": sessions, "rows": len(g)})
    return sorted(out, key=lambda d: (-d["sessions"], d["reply_key"]))
