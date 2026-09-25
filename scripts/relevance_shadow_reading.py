#!/usr/bin/env python3
"""Read-only reading of the relevance shadow (RFC-0046 / ADR-0113).

The weekly-gate reads this to decide enforce or retire for the 4-level Score
shadow. Per window and per ISO week it reports: how many rows the live gate
wrote and how many of them were real (``scored``) judgments, and over those the
share the decision backend answered, the live gate rate, and — for
each candidate cut t on P(directly on-topic) — the would-be gate rate and how
often it agrees with the live gate, plus the shadow's latency p50 / p95.

Schema 2 adds ``readiness`` (RFC-0047 row clock, RFC-0046 face gate): the
answered rows since the switch (``--since``, default the window start), how
many distinct posts they are, the reach rate as two values — the whole span
since the switch and its last day, the width a single rate would hide — and
the day n (``--n``, default 300) is reached at each; plus, over rows carrying
the enforce fields, the split by ``gate_source``, how often ``enforce_gate``
agrees with ``live_gate``, and the ``enforce_reason`` distribution. The v1
aggregates are unchanged. The face gate opens on the reach date, any weekday.

Instrument, never intervention (skill ``read-only-instruments``): nothing is
written and nothing feeds the gate. Thresholds here are candidates to read,
not a decision — the enforce threshold is set after the readings.

stdlib only (``python3 scripts/relevance_shadow_reading.py``): it runs against
a log directory without the package installed. Reads ONLY
``logs/relevance-YYYY-MM-DD.jsonl``; each row is projected to the fields below
at parse time, so ``content_b64`` is never held, let alone decoded.

Usage::

    python3 scripts/relevance_shadow_reading.py --home ~/.config/moltbook \\
        --start 2026-09-26 --end 2026-10-02 [--since 2026-09-27T06:20:00Z] \\
        [--n 300] [--json-out reading.json]

Dates are UTC days, matching how the writer names the files; ``--since`` is a
UTC instant. Output: seven summary lines, then the JSON (also written to
``--json-out`` when given).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

SCHEMA = "relevance-shadow-reading/2"
FILE_RE = re.compile(r"^relevance-(\d{4}-\d{2}-\d{2})\.jsonl$")
# Candidate cuts on P(directly on-topic) (RFC-0046: read, not yet chosen).
THRESHOLDS: tuple[float, ...] = (0.3, 0.5, 0.7)
ANSWERED = "answered"
# The allowlist: every other key of a row (content_b64 above all) is dropped
# at parse time.
KEEP = (
    "ts",
    "post_id",
    "gate_source",
    "enforce_gate",
    "enforce_reason",
    "live_reason",
    "live_gate",
    "decision_reason",
    "decision_p_top",
    "decision_latency_ms",
)
# Only a ``scored`` live reading is a judgment; the four 0.0 sentinels
# (outage, unparseable ...) are events, and comparing a would-be gate with a
# failure's "no" would read an outage as disagreement.
SCORED = "scored"
# RFC-0046: the n the face gate's pre-registered question needs (binomial 95%
# CI half-width ~ 1/sqrt(n) = +-5.7 pt).
DEFAULT_N = 300


def iter_rows(logs: Path, start: date, end: date) -> tuple[list[dict[str, Any]], int]:
    """Projected rows of the window's files, and how many lines failed to parse."""
    rows: list[dict[str, Any]] = []
    failures = 0
    for path in sorted(logs.glob("relevance-*.jsonl")):
        match = FILE_RE.match(path.name)
        if match is None:
            continue
        day = date.fromisoformat(match.group(1))
        if not start <= day <= end:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                failures += 1
                continue
            if not isinstance(record, dict):
                failures += 1
                continue
            row = {key: record.get(key) for key in KEEP}
            row["day"] = day
            rows.append(row)
    return rows, failures


def _rate(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 4) if denominator else None


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..1); None on no values."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]


def _p_top(row: dict[str, Any]) -> float | None:
    value = row.get("decision_p_top")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The reading over one set of rows."""
    reasons: dict[str, int] = {}
    for row in rows:
        key = str(row.get("decision_reason"))
        reasons[key] = reasons.get(key, 0) + 1
    scored = [row for row in rows if row.get("live_reason") == SCORED]
    answered = [
        row
        for row in scored
        if row.get("decision_reason") == ANSWERED
        and _p_top(row) is not None
        and isinstance(row.get("live_gate"), bool)
    ]
    live_gated = sum(1 for row in scored if row.get("live_gate") is True)
    by_threshold: dict[str, dict[str, Any]] = {}
    for t in THRESHOLDS:
        would = [(_p_top(row) or 0.0) >= t for row in answered]
        agree = sum(
            1 for flag, row in zip(would, answered, strict=True) if flag == row["live_gate"]
        )
        by_threshold[f"{t:.1f}"] = {
            "would_gate_rate": _rate(sum(would), len(answered)),
            "agreement_with_live": _rate(agree, len(answered)),
        }
    latencies = [
        float(row["decision_latency_ms"])
        for row in rows
        if isinstance(row.get("decision_latency_ms"), (int, float))
        and not isinstance(row.get("decision_latency_ms"), bool)
    ]
    return {
        "rows": len(rows),
        "live_scored": len(scored),
        "answered": len(answered),
        "answered_rate": _rate(len(answered), len(scored)),
        "decision_reasons": dict(sorted(reasons.items())),
        "live_gate_rate": _rate(live_gated, len(scored)),
        "live_gate_rate_answered": _rate(
            sum(1 for row in answered if row["live_gate"]), len(answered)
        ),
        "thresholds": by_threshold,
        "latency_ms_p50": percentile(latencies, 0.50),
        "latency_ms_p95": percentile(latencies, 0.95),
    }


def parse_since(text: str) -> datetime:
    """A UTC instant from ISO text; a trailing ``Z`` and a naive value read as UTC."""
    value = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _ts(row: dict[str, Any]) -> datetime | None:
    value = row.get("ts")
    if not isinstance(value, str):
        return None
    try:
        return parse_since(value)
    except ValueError:
        return None


def _is_answered(row: dict[str, Any]) -> bool:
    """The same rows ``summarize`` counts as answered."""
    return (
        row.get("live_reason") == SCORED
        and row.get("decision_reason") == ANSWERED
        and _p_top(row) is not None
        and isinstance(row.get("live_gate"), bool)
    )


def _counts(values: list[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


def readiness(rows: list[dict[str, Any]], since: datetime, n: int) -> dict[str, Any]:
    """How far the row clock has run since *since*, and when it reaches *n*."""
    timed = [(ts, row) for row in rows if (ts := _ts(row)) is not None and ts >= since]
    answered = [(ts, row) for ts, row in timed if _is_answered(row)]
    posts = {row.get("post_id") for _ts_, row in answered if row.get("post_id")}
    rate_all = rate_day = None
    reach: list[str] | None = None
    last = max((ts for ts, _row in answered), default=None)
    if last is not None:
        span_days = (last - since).total_seconds() / 86400
        if span_days > 0:
            rate_all = round(len(answered) / span_days, 2)
            day_span = min(1.0, span_days)
            recent = sum(1 for ts, _row in answered if ts > last - timedelta(days=day_span))
            rate_day = round(recent / day_span, 2)
    remaining = n - len(answered)
    if remaining > 0 and rate_all and rate_day:
        reach = sorted(
            (last + timedelta(days=remaining / rate)).date().isoformat()
            for rate in (rate_all, rate_day)
        )
    enforced = [row for _ts_, row in timed if row.get("gate_source") is not None]
    compared = [
        row
        for row in enforced
        if isinstance(row.get("enforce_gate"), bool) and isinstance(row.get("live_gate"), bool)
    ]
    agree = sum(1 for row in compared if row["enforce_gate"] == row["live_gate"])
    return {
        "since": since.isoformat(),
        "n": n,
        "answered_rows": len(answered),
        "answered_dedupe": len(posts),
        "rate_per_day_all": rate_all,
        "rate_per_day_last_day": rate_day,
        "reached": remaining <= 0,
        "reach_dates": reach,
        "gate_source": _counts([row["gate_source"] for row in enforced]),
        "enforce_live_agreement": _rate(agree, len(compared)),
        "enforce_reasons": _counts([row.get("enforce_reason") for row in enforced]),
    }


def iso_week(day: date) -> str:
    year, week, _weekday = day.isocalendar()
    return f"{year}-W{week:02d}"


def reading(
    logs: Path,
    start: date,
    end: date,
    *,
    since: datetime | None = None,
    n: int = DEFAULT_N,
) -> dict[str, Any]:
    rows, failures = iter_rows(logs, start, end)
    if since is None:
        since = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    weeks: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        weeks.setdefault(iso_week(row["day"]), []).append(row)
    return {
        "schema": SCHEMA,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "parse_failures": failures,
        "total": summarize(rows),
        "weeks": {week: summarize(weeks[week]) for week in sorted(weeks)},
        "readiness": readiness(rows, since, n),
    }


def reach_line(ready: dict[str, Any]) -> str:
    """The face gate's one line: when n is reached, at the two rates."""
    head = f"n={ready['n']} 到達: "
    rates = [r for r in (ready["rate_per_day_last_day"], ready["rate_per_day_all"]) if r]
    width = f"{min(rates)}〜{max(rates)} 行/日" if rates else "到達率なし"
    tail = f"（{width}、dedupe 後 {ready['answered_dedupe']} 行）"
    if ready["reached"]:
        return f"{head}到達済み（answered {ready['answered_rows']} 行）{tail}"
    if ready["reach_dates"] is None:
        return f"{head}見込みなし{tail}"
    first, last = ready["reach_dates"]
    return f"{head}{first}〜{last} 見込み{tail}"


def summary_lines(result: dict[str, Any]) -> list[str]:
    """Seven lines a gate session reads before the JSON."""
    total = result["total"]
    window = result["window"]
    cuts = "  ".join(
        f"t={t}: would {v['would_gate_rate']} / agree {v['agreement_with_live']}"
        for t, v in total["thresholds"].items()
    )
    return [
        f"relevance shadow {window['start']}..{window['end']}: "
        f"{total['rows']} rows ({total['live_scored']} live-scored), "
        f"{result['parse_failures']} parse failure(s)",
        f"answered {total['answered']} ({total['answered_rate']} of live-scored); "
        f"reasons {total['decision_reasons']}",
        f"live gate rate {total['live_gate_rate']} of live-scored (answered rows: "
        f"{total['live_gate_rate_answered']})",
        f"would-be gate on P(on-topic): {cuts}",
        f"shadow latency ms p50 {total['latency_ms_p50']} / p95 {total['latency_ms_p95']}",
        "weeks: "
        + (
            ", ".join(
                f"{week} {w['rows']} rows / answered {w['answered']}"
                for week, w in result["weeks"].items()
            )
            or "none"
        ),
        reach_line(result["readiness"]),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only reading of the relevance shadow.")
    parser.add_argument("--home", type=Path, required=True, help="MOLTBOOK_HOME to read")
    parser.add_argument("--start", type=date.fromisoformat, required=True, help="UTC day")
    parser.add_argument("--end", type=date.fromisoformat, required=True, help="UTC day")
    parser.add_argument(
        "--since",
        type=parse_since,
        default=None,
        help="UTC instant the clock starts (the switch); default the window start",
    )
    parser.add_argument("--n", type=int, default=DEFAULT_N, help="rows the face gate needs")
    parser.add_argument("--json-out", type=Path, default=None, help="also write the JSON here")
    args = parser.parse_args(argv)
    if args.end < args.start:
        parser.error("--end is before --start")
    result = reading(args.home / "logs", args.start, args.end, since=args.since, n=args.n)
    for line in summary_lines(result):
        print(line)
    text = json.dumps(result, indent=1, sort_keys=True)
    print(text)
    if args.json_out is not None:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
