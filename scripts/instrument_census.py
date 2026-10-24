#!/usr/bin/env python3
"""Instrument census over the self-written logs (read-only, ADR-0107 / ADR-0110).

Every JSONL file the agent writes under ``$MOLTBOOK_HOME/logs/`` gets a reader
here, each week. This module is layer 3 of three: it draws the eleven sections
and is the entry point the weekly chain calls. What each section answers, and
why the random projection sample was retired, is in ADR-0110 — not restated.

- ``_census_registry`` — the row schema, the status vocabulary and the read
  (including the two boundaries: no ``logs/episodes/``, no ``*.log``, and an
  allowlist at the load boundary).
- ``_census_series`` — the matrix, the trace and the outlier statistics.

``tests/test_instrument_census.py`` pins the boundaries through this module.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from _census_registry import OK_STATUSES, PAST_WEEKS, Reading, census, short
from _census_series import (
    UNRANKED,
    Z_THRESHOLD,
    cat_series,
    collapse_runs_dated,
    compress_sequence,
    events,
    gate_record,
    letters,
    modified_z,
    outliers,
    reply_retry_loops,
    session_matrix,
    sessioned,
    traces,
)
from _md import md_safe

_TOP_VALUES = 6  # enum values printed per field
_LEDGER_COLS = 9  # displayed columns; the outlier scan uses every column
_TRACE_RUNS = 10  # runs printed per session before the tail is summarised
_STRIP_MINUTES = 60
# ASCII on purpose: the block-drawing ramp is prettier but three bytes a
# character, and 28 sessions × 2 bands × 60 minutes of it cost 7 KB of the
# section budget — a quarter of the whole reading, spent on glyphs.
_STRIP_RAMP = ".:-=+*#%@"  # index 0 is "no rows that minute"
_HUNT_SESSIONS = 3
_HUNT_LINES = 18
_HUNT_SPREAD = 2  # minutes either side of the peak
_LEDGER_LABEL = 14  # displayed header width; the full column name is in the outlier table


def _render_census_table(readings: list[Reading]) -> list[str]:
    non_ok = [r for r in readings if r.status not in OK_STATUSES]
    head = (
        "**"
        + ", ".join(f"{r.status} `{md_safe(r.name)}`" for r in non_ok)
        + "** — the Saturday gate edits `REGISTRY` in `scripts/_census_registry.py` "
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
            counts = r.frame[f].dropna().map(short).value_counts() if f in r.frame else None
            if counts is None or counts.empty:
                continue
            top = ", ".join(f"{v} {n}" for v, n in counts.head(_TOP_VALUES).items())
            more = len(counts) - _TOP_VALUES
            parts.append(f"  - `{f}`: {top}" + (f" (+{more} more)" if more > 0 else ""))
            unknown = r.entry.unknown_values(f, r.frame[f])
            if unknown:
                shown = ", ".join(f"`{md_safe(short(v))}`" for v in unknown)
                parts.append(
                    f"  - **UNKNOWN `{f}` value(s) outside the writer's vocabulary**: {shown}"
                )
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


def _ledger_labels(columns: list[str]) -> list[str]:
    """Short headers for the ledger — a markdown table pads every cell to its header.

    Sixteen columns named ``api-audit:GET /posts/{id}/comments /1m`` cost more
    bytes in padding than in data. The log prefix and any dotted namespace go
    first; when that makes two columns look alike, the pair falls back to a
    middle-squeezed form of the full name, which keeps both the log and the
    tail that distinguishes them. The outlier table always prints the full name.
    """
    short = []
    for col in columns:
        label = col.split(":", 1)[-1]
        head, _, axis = label.partition(" ")
        short.append((head.rsplit(".", 1)[-1] + (f" {axis}" if axis else "")).strip())
    # Squeezed from the middle, not the end: both ends carry the part of a
    # path or a dotted name that tells two columns apart.
    head = _LEDGER_LABEL // 2 - 1
    labels = [
        label
        if len(label) <= _LEDGER_LABEL
        else label[:head] + "…" + label[-(_LEDGER_LABEL - head - 1) :]
        for label in (
            col if short.count(s) > 1 else s for col, s in zip(columns, short, strict=True)
        )
    ]
    # Two full names can still squeeze to the same string. A duplicate header
    # is not cosmetic: pandas then returns a DataFrame for `table[label]` and
    # the section renders as `unavailable`. Number the collisions.
    seen: dict[str, int] = {}
    for i, label in enumerate(labels):
        seen[label] = n = seen.get(label, 0) + 1
        if n > 1:
            labels[i] = f"{label[: _LEDGER_LABEL - 2]}~{n}"
    return labels


def _render_ledger(matrix: pd.DataFrame) -> list[str]:
    lines = ["### Session ledger (one row per session, one column per log:category)", ""]
    if matrix.empty:
        return lines + ["No sessions in window."]
    # Ranked by median, not by sum: the ledger shows what a typical session
    # does, and a column that is enormous in one session belongs to the outlier
    # table. Only the per-category count axes compete, because only they share a
    # unit — a duration sum in milliseconds and a budget minimum would
    # otherwise hold two slots forever on magnitude alone, in a section whose
    # header promises one column per log:category. Errors, sums and budget
    # minima stay in the matrix, so the outlier scan still sees them.
    counts = [c for c in matrix.columns if ":" in c and not c.endswith("gap s")]
    shown = sorted(
        sorted(counts, key=lambda c: (-float(matrix[c].median()), -float(matrix[c].sum())))[
            :_LEDGER_COLS
        ]
    )
    if not shown:
        return lines + ["No sessioned categories in window."]
    table = matrix[shown].copy()
    table.loc["median"] = matrix[shown].median()
    table.columns = pd.Index(_ledger_labels(shown))
    table.index = pd.Index([str(s)[:8] for s in table.index], name="session")
    # Per-column formatting: integral columns print without a decimal tail and
    # nothing prints in scientific notation. The median row is what makes some
    # count columns non-integral, so the choice is made after that row exists.
    # The leading entry is for the index column that to_markdown prints first;
    # without it every format lands one column to the left.
    fmts = ["s"] + [".0f" if (table[c].dropna() % 1 == 0).all() else ".2f" for c in table.columns]
    return lines + [
        f"{len(matrix)} sessions × {len(matrix.columns)} derived columns; the {len(shown)} "
        "log:category columns with the largest median are drawn — errors, sums and budget "
        "minima are scanned, not drawn. `/1m` = busiest single minute.",
        "",
        table.round(2).to_markdown(floatfmt=fmts),
        "",
        "The `median` row is this window's representative session; previous reports carry "
        "the earlier ones (no cross-week comparison is computed here).",
    ]


def _render_trace(readings: list[Reading]) -> list[str]:
    lines = ["### Session trace (all logs, ts order, run-length)", ""]
    alphabet, per_session = letters(readings), traces(readings)
    if not per_session:
        return lines + ["No sessioned events in window."]
    legend = " · ".join(f"`{ch}` {cat}" for cat, ch in alphabet.items() if ch != "?")
    if overflowed := sum(1 for ch in alphabet.values() if ch == "?"):
        legend += (
            f" · `?` {overflowed} further categories share this letter — the trace merges "
            "them into one run and `compress` reads high for that reason alone"
        )
    lines += [legend, "", "```"]
    for sid, seq in per_session.items():
        runs = compress_sequence(seq).split(", ")
        head = " ".join(runs[:_TRACE_RUNS]).replace(" ×", "×")
        tail = f" … +{len(runs) - _TRACE_RUNS} runs" if len(runs) > _TRACE_RUNS else ""
        lines.append(f"{sid[:8]} {head}{tail}")
    return lines + ["```"]


def _render_strips(readings: list[Reading]) -> list[str]:
    lines = [f"### Session strips (rows per minute, first {_STRIP_MINUTES} minutes)", ""]
    ranked = sorted(sessioned(readings), key=lambda r: -r.rows)[:2]
    if not ranked:
        return lines + ["No sessioned events in window."]
    for r in ranked:
        assert r.entry is not None
        d = cat_series(r)
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


def _render_outliers(found: list[dict], absent: list[str], matrix: pd.DataFrame) -> list[str]:
    lines = [
        f"### Within-week outliers (median / MAD over sessions, |modified z| ≥ {Z_THRESHOLD})",
        "",
        pd.DataFrame(found)[["z", "column", "session", "value", "median", "MAD"]].to_markdown(
            index=False
        )
        if found
        else "No session departed from the others on any derived column.",
    ]
    for col in UNRANKED:
        if col not in matrix:
            continue
        z = modified_z(matrix[col])
        hits = z[z.abs() >= Z_THRESHOLD].dropna()
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
            f"Absent this window, present in the previous {PAST_WEEKS} weeks: "
            + ", ".join(f"`{md_safe(c)}`" for c in sorted(absent))
            + " — zero in every session, so no departure is computed.",
        ]
    return lines


def _render_hunting(readings: list[Reading], found: list[dict]) -> list[str]:
    lines = ["### Hunting windows (peak minutes, consecutive same-category events collapsed)", ""]
    ev = events(readings)
    if not found or ev.empty:
        return lines + ["No outliers to hunt." if not found else "No sessioned events in window."]
    seen: set[str] = set()
    for item in found:
        if len(seen) >= _HUNT_SESSIONS or item["session_id"] in seen:
            continue
        rows = ev[ev["session_id"].astype(str) == item["session_id"]]
        if rows.empty:
            continue  # a column with no sessioned events must not burn a slot
        seen.add(item["session_id"])
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


def _render_gates(readings: list[Reading]) -> list[str]:
    lines = [
        "### Gate record (pipeline-metrics.jsonl joined to audit.jsonl / insight-staged.jsonl)",
        "",
    ]
    g = gate_record(readings)
    if not g["decisions"]:
        return lines + ["No `gate_record` row in window — read it with a window that spans a gate."]
    lines += [
        "decisions this gate (gate_record: adopted + rejected + deleted + whitelisted + "
        "archived; `*_held` is not a ruling):",
        "",
        pd.DataFrame(g["decisions"]).to_markdown(index=False),
        "",
    ]
    if g["agreement"]:
        rows = [{k: r[k] for k in ("category", "agree", "n", "agreement")} for r in g["agreement"]]
        lines += [
            "recommendation == decision (rate with Wilson 95% interval; fewer than ten items "
            "print counts only):",
            "",
            pd.DataFrame(rows).to_markdown(index=False),
            "",
        ]
        whole = g["agreement"][-1]
        lines.append(
            f"ADR-0099 Review-when (agreement ~100% sustained → one retrospective lens audit, "
            f"D-P2-01-2): {whole['agree']}/{whole['n']} this window — "
            + (
                "at 100%, the condition's point reading holds."
                if whole["review_when"]
                else "not at 100% (or fewer than ten items)."
            )
            + " Sustained is read across weeks, not here."
        )
        lines.append("")
    else:
        lines += ["No `gate_item` pair in window.", ""]
    lines += [
        "gates bundled from the item-level logs (everything in (previous gate day, gate day]; "
        "`staged` = insight-staged.jsonl rows, `adopted` / `rejected` = insight audit rows, "
        "`archived` = skill retirements):",
        "",
        pd.DataFrame(
            [{k: v for k, v in b.items() if k != "exceptions"} for b in g["gates"]]
        ).to_markdown(index=False),
    ]
    exc = [f"{b['date']}: {e}" for b in g["gates"] for e in b["exceptions"]]
    lines += [
        "",
        ("Exceptions: " + "; ".join(exc))
        if exc
        else "No gate_record count differs from the item-level logs.",
    ]
    return lines


def _render_retry_loops(readings: list[Reading]) -> list[str]:
    lines = ["### Reply-target retry loops (404 + unknown, same target, 2+ sessions)", ""]
    loops = reply_retry_loops(readings)
    if not loops:
        return lines + ["None in window."]
    return lines + [
        pd.DataFrame(loops).to_markdown(index=False),
        "",
        "A target the other side deleted stays retryable under `unknown`; whether a 404 joins "
        "the retiring codes is the owner's decision, not this reading's.",
    ]


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
        _render_gates(readings),
        _render_retry_loops(readings),
    ):
        lines += [*block, ""]
    return "\n".join(lines).rstrip() + "\n"


# ADR-0123: the knowledge live-pool retention trigger, in bytes on disk.
KNOWLEDGE_SIZE_TRIGGER_MB = 50


def knowledge_age_reading(patterns: list[dict], now: datetime) -> dict[str, int]:
    """Live-row age split at the dedup floor (ADR-0123, P2-07.4).

    ``within`` rows still enter the dedup comparison population
    (``effective_importance >= DEDUP_IMPORTANCE_FLOOR``, about 58 days);
    ``beyond`` rows are live but outside it, so a re-observed insight can
    re-enter beside them. Tombstones (``valid_until`` set) are counted apart
    and never in ``live``. A row with no parsable ``distilled`` is
    ``no_timestamp`` -- it gets the heavy-penalty importance, i.e. beyond.
    """
    from contemplative_agent.core.knowledge_store import (  # noqa: PLC0415
        parse_distilled,
        is_live,
    )
    from contemplative_agent.core.thresholds import DEDUP_IMPORTANCE_FLOOR  # noqa: PLC0415

    max_days = math.log(DEDUP_IMPORTANCE_FLOOR) / math.log(0.95)
    out = {"live": 0, "within": 0, "beyond": 0, "no_timestamp": 0, "tombstones": 0}
    for p in patterns:
        if not is_live(p):
            out["tombstones"] += 1
            continue
        out["live"] += 1
        dt = parse_distilled(p)
        if dt is None:
            out["no_timestamp"] += 1
            out["beyond"] += 1
        elif (now - dt).total_seconds() / 86400 <= max_days:
            out["within"] += 1
        else:
            out["beyond"] += 1
    return out


def render_knowledge_age(home: Path, now: datetime | None = None) -> list[str]:
    """One reading line for the knowledge live pool; never raises (observability)."""
    path = home / "knowledge.json"
    head = "### Knowledge live-pool age"
    try:
        size_mb = path.stat().st_size / (1024 * 1024)
        data = json.loads(path.read_text(encoding="utf-8"))
        patterns = data.get("patterns", []) if isinstance(data, dict) else data
        if not isinstance(patterns, list):
            raise ValueError("knowledge.json is neither a list nor {patterns: [...]}")
        r = knowledge_age_reading(patterns, now or datetime.now(timezone.utc))
    except (OSError, ValueError) as exc:
        return [head, "", f"not read ({type(exc).__name__}: {md_safe(str(exc))})"]
    pct = f"{100 * r['within'] / r['live']:.0f}%" if r["live"] else "n/a"
    return [
        head,
        "",
        f"live {r['live']} (within dedup floor {r['within']} = {pct}, beyond {r['beyond']}, "
        f"of which no timestamp {r['no_timestamp']}); tombstones {r['tombstones']}; "
        f"file {size_mb:.1f} MB vs {KNOWLEDGE_SIZE_TRIGGER_MB} MB trigger (ADR-0123: no GC; "
        "trigger crossed -> the owner revisits b / c).",
    ]


def run(home: Path, start: date, end: date) -> str:
    logs_dir = home / "logs"
    body = render_markdown(census(logs_dir, start, end), start=start, end=end, logs_dir=logs_dir)
    return body + "\n" + "\n".join(render_knowledge_age(home)) + "\n"


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
