"""Aggregation and statistics over the readings — the series layer.

Layer 2 of three (ADR-0110). Everything here turns ``Reading`` objects into
numbers: the session × derived-column matrix whose columns are derived from the
data rather than declared, the per-session event trace, and the within-week
outlier scan with its three calibrations. It renders nothing and reads no file.

Imports ``_census_registry`` for the row schema; imported by
``instrument_census``, which draws what this computes.
"""

from __future__ import annotations

import zlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from _census_registry import Reading, short

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
