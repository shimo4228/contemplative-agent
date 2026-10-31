#!/usr/bin/env python3
"""Per-series interval table from the regime boundary table (P3-02.1).

stdlib only; run as ``python3 -I scripts/regime_intervals.py``. Read-only: the
inputs are ``docs/evidence/regimes/regimes.json`` and a public data-repo copy
(``knowledge.json``, ``snapshots/``, ``reports/``, ``pipeline/``); the outputs
are files the caller names.

Question it answers: *between two apparatus boundaries that touch a series,
how many days is that stretch and how many weekly points fall inside it?*
The distilled corpus is dominated by apparatus changes (``distilled`` 707 in
2026-06 against 3,441 in 2026-07 straddles the per-episode distill and the
model swap), and with one agent the only inference left is a comparison inside
one stretch. P3-01.4 (b) therefore compares only stretches with at least
``MIN_POINTS`` weekly points and keeps the rest to descriptive statistics.

Rules:
- ``regimes.json`` rows each carry ``affects``: names from ``SERIES``. An
  unknown name or an empty list fails the run (exit 2), so a row cannot be
  added without saying what it moves.
- A *point* is an ISO week (Monday start) with at least one observation of the
  series; the observation dates come from the data repo (see ``SERIES``).
- A stretch of a series runs from one affecting boundary date to the next (the
  first begins at the series' first observation, the last ends at its last).
  A point exactly on a boundary date belongs to the new stretch. The time of
  day on a row is ignored; ``date`` is the calendar day it takes effect.
- ``--check-changes changes.json`` compares the value-layer rows with the
  ``value_layer_change_series.py`` output (P2-05.7): every change row must have
  a regimes row carrying the same ``sha_after``, and the reverse. It does not
  write anything; a mismatch exits 1.
- No instrument reads a boundary automatically (RFC-0008 stays withdrawn).

Consumption plan (ADR-0101): (a) the owner when writing the research-questions
ADR (P3-01.1 (d)) and the longitudinal method (P3-01.4 (b)), P3-05.11's figure
script (it reads ``regimes.json`` for its boundary lines) and the paper's
figures; (b) one tabulation fixes the stretch in which the loop was closed (Q2's
period) and afterwards a landing ADR adds one row, nothing is decided
automatically; (c) retire: the table is permanent (a record of the data's
boundaries). At the P4-02 final sync the file is frozen and not appended to,
and this script is run once more.

Usage:
    regime_intervals.py --regimes docs/evidence/regimes/regimes.json \\
        --data-repo ~/contemplative-agent-data \\
        [--out-json intervals.json] [--out-md intervals.md] \\
        [--render-datacard] [--check-changes changes.json]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

MIN_POINTS = 4  # P3-01.4 (b): within-series comparison needs >= 4 weekly points

_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_SNAP = re.compile(r"^([a-z-]+)_(\d{4})(\d{2})(\d{2})T")


def _d(s: str) -> dt.date:
    return dt.date.fromisoformat(s[:10])


def _week(d: dt.date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# --- observation sources -------------------------------------------------


def _knowledge_dates(repo: Path) -> list[dt.date]:
    p = repo / "knowledge.json"
    if not p.is_file():
        return []
    rows = json.loads(p.read_text(encoding="utf-8"))
    out: list[dt.date] = []
    for r in rows:
        v = r.get("distilled")
        if isinstance(v, str) and _DATE.match(v):
            out.append(_d(v))
    return out


def _file_dates(directory: Path, pattern: str) -> list[dt.date]:
    rx = re.compile(pattern)
    out: list[dt.date] = []
    if directory.is_dir():
        for f in directory.iterdir():
            m = rx.match(f.name)
            if m:
                out.append(_d(m.group(1)))
    return out


def _snapshot_dates(repo: Path, kinds: Iterable[str] | None = None) -> list[dt.date]:
    out: list[dt.date] = []
    root = repo / "snapshots"
    if not root.is_dir():
        return out
    want = set(kinds) if kinds else None
    for f in root.iterdir():
        m = _SNAP.match(f.name)
        if not m or (want and m.group(1) not in want):
            continue
        out.append(dt.date(int(m.group(2)), int(m.group(3)), int(m.group(4))))
    return out


def _pipeline(name: str) -> Callable[[Path], list[dt.date]]:
    return lambda repo: _file_dates(
        repo / "pipeline" / name, rf"^{re.escape(name)}-(\d{{4}}-\d{{2}}-\d{{2}})\.json$"
    )


# series name -> (description, observation source or None when the public data
# has no dated observations for it)
SERIES: dict[str, tuple[str, Callable[[Path], list[dt.date]] | None]] = {
    "knowledge.patterns": ("distilled patterns, by distilled day", _knowledge_dates),
    "knowledge.provenance": ("provenance field on patterns, by distilled day", _knowledge_dates),
    "knowledge.embedding": ("embedding handling of the corpus, by distilled day", _knowledge_dates),
    "comment-reports": (
        "reports/comment-reports/comment-report-DATE.md",
        lambda repo: _file_dates(
            repo / "reports" / "comment-reports", r"^comment-report-(\d{4}-\d{2}-\d{2})\.md$"
        ),
    ),
    "comment-reports.relevance": (
        "the relevance figure inside comment reports, by report day",
        lambda repo: _file_dates(
            repo / "reports" / "comment-reports", r"^comment-report-(\d{4}-\d{2}-\d{2})\.md$"
        ),
    ),
    "weekly-analysis": (
        "reports/analysis/weekly-DATE.md (the main weekly document only)",
        lambda repo: _file_dates(
            repo / "reports" / "analysis", r"^weekly-(\d{4}-\d{2}-\d{2})\.md$"
        ),
    ),
    "pipeline/comment-outcomes": (
        # ended: weekly stage 7d was removed on 2026-10-31 (R33, ADR-0106 note); the
        # last file is comment-outcomes-2026-10-30.json, nothing is written after it
        "pipeline/comment-outcomes/*.json (ends 2026-10-30)",
        _pipeline("comment-outcomes"),
    ),
    "pipeline/confusion-pairs": ("pipeline/confusion-pairs/*.json", _pipeline("confusion-pairs")),
    "pipeline/dead-code": ("pipeline/dead-code/*.json", _pipeline("dead-code")),
    "pipeline/docs-consistency": (
        "pipeline/docs-consistency/*.json",
        _pipeline("docs-consistency"),
    ),
    "pipeline/ledger-watch": ("pipeline/ledger-watch/*.json", _pipeline("ledger-watch")),
    "pipeline/never-selected": ("pipeline/never-selected/*.json", _pipeline("never-selected")),
    "pipeline/value-layer": ("pipeline/value-layer/*.json", _pipeline("value-layer")),
    "snapshots": ("snapshots/<kind>_<ts>/ of every run kind", _snapshot_dates),
    "insight-staging": (
        "snapshots/insight_*",
        lambda repo: _snapshot_dates(repo, ["insight"]),
    ),
    # value-layer kinds: observed at every snapshot (the layer is copied into each)
    "identity": ("identity.md as copied into each snapshot", _snapshot_dates),
    "skills": ("skills/ as copied into each snapshot", _snapshot_dates),
    "constitution": ("constitution/ as copied into each snapshot", _snapshot_dates),
    # no dated public observations: stretches are given in days only
    "views": ("views/*.md (no dated public observations)", None),
    "ipd-benchmark": ("IPD runs frozen under docs/evidence (not a dated public series)", None),
}


# --- loading and validation ---------------------------------------------


class RegimeError(ValueError):
    pass


def load_regimes(path: Path) -> dict[str, Any]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    rows = doc.get("regimes")
    if not isinstance(rows, list) or not rows:
        raise RegimeError("regimes.json has no rows")
    seen: set[str] = set()
    for r in rows:
        rid = r.get("id")
        if not rid or rid in seen:
            raise RegimeError(f"missing or duplicate id: {rid!r}")
        seen.add(rid)
        try:
            _d(r["date"])
        except (KeyError, ValueError) as exc:
            raise RegimeError(f"{rid}: bad date") from exc
        aff = r.get("affects")
        if not isinstance(aff, list) or not aff:
            raise RegimeError(f"{rid}: affects is required and must be a non-empty list")
        unknown = [a for a in aff if a not in SERIES]
        if unknown:
            raise RegimeError(f"{rid}: unknown series in affects: {unknown}")
        for key in ("change", "status", "kind"):
            if not r.get(key):
                raise RegimeError(f"{rid}: {key} is required")
    return doc


def sorted_rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(doc["regimes"], key=lambda r: (r["date"], r.get("time", ""), r["id"]))


# --- interval computation -----------------------------------------------


def series_intervals(
    name: str, boundaries: list[tuple[dt.date, str]], obs: list[dt.date]
) -> list[dict[str, Any]]:
    """Stretches of one series. ``boundaries`` are (date, regime id), sorted."""
    if not obs:
        return []
    first, last = min(obs), max(obs)
    # one boundary date can hold several rows; stretches split on dates
    by_date: dict[dt.date, list[str]] = {}
    for d, rid in boundaries:
        by_date.setdefault(d, []).append(rid)
    cuts = sorted(d for d in by_date if first < d <= last)
    starts = [first] + cuts
    ends = cuts + [last]
    prior = [d for d in by_date if d <= first]
    opening = by_date[max(prior)] if prior else []
    out: list[dict[str, Any]] = []
    for i, (s, e) in enumerate(zip(starts, ends, strict=True)):
        last_stretch = i == len(starts) - 1
        in_obs = [d for d in obs if s <= d and (d <= e if last_stretch else d < e)]
        weeks = {_week(d) for d in in_obs}
        span_end = e if last_stretch else e
        out.append(
            {
                "series": name,
                "from": s.isoformat(),
                "to": e.isoformat(),
                "to_is_boundary": not last_stretch,
                "opened_by": by_date[s] if i else opening,
                "closed_by": by_date[e] if not last_stretch else [],
                "span_days": (span_end - s).days + (1 if last_stretch else 0),
                "observations": len(in_obs),
                "weekly_points": len(weeks),
                "within_series_ok": len(weeks) >= MIN_POINTS,
            }
        )
    return out


def day_only_intervals(name: str, boundaries: list[tuple[dt.date, str]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    dates = sorted({d for d, _ in boundaries})
    for a, b in zip(dates, dates[1:], strict=False):
        out.append(
            {
                "series": name,
                "from": a.isoformat(),
                "to": b.isoformat(),
                "to_is_boundary": True,
                "opened_by": [rid for d, rid in boundaries if d == a],
                "closed_by": [rid for d, rid in boundaries if d == b],
                "span_days": (b - a).days,
                "observations": None,
                "weekly_points": None,
                "within_series_ok": None,
            }
        )
    return out


def build(doc: dict[str, Any], repo: Path | None) -> dict[str, Any]:
    rows = sorted_rows(doc)
    per: dict[str, list[tuple[dt.date, str]]] = {}
    for r in rows:
        for s in r["affects"]:
            per.setdefault(s, []).append((_d(r["date"]), r["id"]))
    table: list[dict[str, Any]] = []
    summary: list[dict[str, Any]] = []
    for name in sorted(SERIES):
        bnd = per.get(name, [])
        source = SERIES[name][1]
        if source is None or repo is None:
            ivs = day_only_intervals(name, bnd) if bnd else []
            span = None
        else:
            obs = source(repo)
            ivs = series_intervals(name, bnd, obs)
            span = (min(obs).isoformat(), max(obs).isoformat()) if obs else None
        table.extend(ivs)
        ok = [i for i in ivs if i["within_series_ok"]]
        longest = max(ivs, key=lambda i: i["span_days"]) if ivs else None
        summary.append(
            {
                "series": name,
                "boundaries": len(bnd),
                "observed_span": span,
                "stretches": len(ivs),
                "stretches_with_4plus_weekly_points": len(ok),
                "longest_stretch_days": longest["span_days"] if longest else None,
                "longest_stretch": (longest["from"], longest["to"]) if longest else None,
                "points_in_longest": longest["weekly_points"] if longest else None,
            }
        )
    return {"min_points": MIN_POINTS, "summary": summary, "intervals": table}


# --- rendering -----------------------------------------------------------


def render_markdown(result: dict[str, Any], doc: dict[str, Any]) -> str:
    lines = [
        "# Regime stretches per series",
        "",
        "Generated by `scripts/regime_intervals.py` from `docs/evidence/regimes/regimes.json`",
        "and the public data repo. A point is an ISO week with at least one observation.",
        f"P3-01.4 (b) compares within a series only across stretches with at least {result['min_points']} weekly points",
        "(`within_series_ok`); every other stretch is descriptive only.",
        "",
        "## Longest stretch per series",
        "",
        "| series | boundaries | observed span | stretches | stretches with >= 4 points | longest (days) | its points |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in result["summary"]:
        span = f"{s['observed_span'][0]} .. {s['observed_span'][1]}" if s["observed_span"] else "-"
        lg = (
            f"{s['longest_stretch_days']} ({s['longest_stretch'][0]} .. {s['longest_stretch'][1]})"
            if s["longest_stretch"]
            else "-"
        )
        pts = s["points_in_longest"] if s["points_in_longest"] is not None else "-"
        lines.append(
            f"| `{s['series']}` | {s['boundaries']} | {span} | {s['stretches']} | "
            f"{s['stretches_with_4plus_weekly_points']} | {lg} | {pts} |"
        )
    lines += [
        "",
        "## All stretches",
        "",
        "| series | from | to | days | observations | weekly points | >= 4 points | opened by | closed by |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for i in result["intervals"]:
        ok = "-" if i["within_series_ok"] is None else ("yes" if i["within_series_ok"] else "no")
        obs = "-" if i["observations"] is None else i["observations"]
        wp = "-" if i["weekly_points"] is None else i["weekly_points"]
        lines.append(
            f"| `{i['series']}` | {i['from']} | {i['to']} | {i['span_days']} | {obs} | {wp} | {ok} | "
            f"{', '.join(i['opened_by']) or '-'} | {', '.join(i['closed_by']) or '-'} |"
        )
    return "\n".join(lines) + "\n"


def render_datacard(doc: dict[str, Any]) -> str:
    """The DATACARD 'Apparatus boundaries / Regime changes' table, from the rows."""
    lines = [
        "| id | date | change | affects | ADR / RFC |",
        "|---|---|---|---|---|",
    ]
    for r in sorted_rows(doc):
        when = r["date"] + (f" {r['time']}" if r.get("time") else "")
        refs = ", ".join(r.get("refs") or []) or "-"
        aff = ", ".join(f"`{a}`" for a in r["affects"])
        lines.append(f"| {r['id']} | {when} | {r['change']} | {aff} | {refs} |")
    return "\n".join(lines) + "\n"


# --- agreement with the value-layer change series (P2-05.7) --------------


def check_changes(doc: dict[str, Any], changes: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    have = {
        (r["value_layer_change"]["kind"], r["value_layer_change"]["sha_after"]): r
        for r in doc["regimes"]
        if r.get("value_layer_change")
    }
    seen: set[tuple[str, str]] = set()
    for c in changes.get("changes", []):
        key = (c["kind"], c["sha_after"])
        seen.add(key)
        row = have.get(key)
        if row is None:
            problems.append(f"no regimes row for {c['kind']} -> {c['sha_after']} at {c['ts_to']}")
            continue
        if row["value_layer_change"]["sha_before"] != c["sha_before"]:
            problems.append(f"{row['id']}: sha_before differs from the series")
        if row["date"] != c["ts_to"][:10]:
            problems.append(f"{row['id']}: date {row['date']} != snapshot day {c['ts_to'][:10]}")
    for key, row in have.items():
        if key not in seen:
            problems.append(f"{row['id']} has no change row in the series ({key[0]} {key[1]})")
    return problems


# --- cli -----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--regimes", type=Path, required=True)
    ap.add_argument(
        "--data-repo", type=Path, help="public data repo copy; without it only day spans are given"
    )
    ap.add_argument("--out-json", type=Path)
    ap.add_argument("--out-md", type=Path)
    ap.add_argument(
        "--render-datacard", action="store_true", help="print the DATACARD table and exit"
    )
    ap.add_argument("--check-changes", type=Path, help="value_layer_change_series.py changes.json")
    args = ap.parse_args(argv)

    try:
        doc = load_regimes(args.regimes)
    except RegimeError as exc:
        print(f"regime-intervals: {exc}", file=sys.stderr)
        return 2
    if args.render_datacard:
        sys.stdout.write(render_datacard(doc))
        return 0
    if args.check_changes:
        problems = check_changes(doc, json.loads(args.check_changes.read_text(encoding="utf-8")))
        for p in problems:
            print(f"regime-intervals: {p}", file=sys.stderr)
        if problems:
            return 1
    result = build(doc, args.data_repo)
    if args.out_json:
        args.out_json.write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    md = render_markdown(result, doc)
    if args.out_md:
        args.out_md.write_text(md, encoding="utf-8")
    elif not args.out_json:
        sys.stdout.write(md)
    print(
        f"regime-intervals: {len(doc['regimes'])} rows, {len(result['intervals'])} stretches",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
