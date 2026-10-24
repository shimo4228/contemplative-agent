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

Schema 3 (RFC-0046, owner decision 2026-09-26: "my domain" = identity +
axioms): the row clock — answered rows, dedupe, rates, the reach of n — counts
only rows asked under that definition (``domain_source: identity+axioms``),
and ``domain_sources`` gives the answered rows since the switch per
definition; a row without the field predates it and is ``identity``. The
window totals and the ISO weeks still pool every row.

Rows per post (RFC-0046 S38, 2026-10-04): before that fix a post the gate
dropped was scored again — and wrote a row — in every session it stayed in the
feed (2026-09-28..10-03: 1,223 rows for 502 posts, a dropped post 2.84 times on
average), so row-level rates over-weight dropped posts; read the post-level
dedupe for them. From the fix on, a reading is remembered across sessions
(``relevance_cache.json``) and a reuse writes no row, so a post has one row per
text + judge pin and the row and post views converge. Nothing here changed.

Schema 4 (RFC-0046 cleanup 2, 2026-10-07): the feed stopped asking the
free-generated score, so a row written from then on has no ``live_*`` field and
its ``gate_source`` is ``score4`` or ``fail_closed``. A row counts as a
judgment when its live half is ``scored`` *or absent*; ``answered`` and the
would-be gate rates read both kinds of row, while ``live_gate_rate``,
``agreement_with_live`` and ``enforce_live_agreement`` read only rows that
carry a live half (null once a window holds none — no ``--until`` needed).

Schema 5 (ADR-0113 amendment 2, 2026-10-09): self-post seed selection asks the
same gate and writes rows with ``source: "seed"``. This reading is about the
feed, so those rows are left out of every aggregate and counted in
``seed_rows_excluded``; a row without ``source`` predates the field and is a
feed row.

Schema 6 (P1-15.2 / .3, RFC-0047): three additions, none of them a decision.
(1) ``margin`` per window and per week: of the distinct answered posts (post
level, the latest row of a post), the share whose P(top) lies within
``MARGIN_HALF_WIDTH`` (0.05) of the enforce threshold ``--t`` (default 0.3) —
the posts a single re-read of a logprobs value that does not reproduce bit for
bit (RFC-0046 S31) could flip; counts always, a Wilson interval from 10 posts.
Default stance until four weekly readings exist: no majority vote, no
hysteresis. (2) ``ollama_versions`` per week: the Ollama versions of the
sessions that wrote the week's rows, joined by ``session_id`` from the
session-start record of ``logs/episodes/`` (``--episodes``; only the two keys
``session_id`` and ``ollama_version`` of ``event == start`` records are kept,
every other field is dropped at parse time and nothing else of that folder is
read); ``changed`` marks a week whose set differs from the previous week's.
A row whose session has no recorded version counts in ``unresolved`` — absent,
not guessed. (3) ``adopt_window`` (with ``--adopt-at`` or ``--adopt-from-audit``):
the post-level gate rate over the 7 days before and the 7 days from the latest
identity adopt, each with its Wilson interval, their difference with a
Newcombe interval, and a verdict by the rule the pre-registration states
(``docs/evidence/rfc-0046/preregistration-third-reading.md``): ``counts_only``
below 10 posts on a side, ``hold`` when the difference interval lies inside
+-6 pt, ``reopen`` when it lies wholly outside, ``indeterminate`` when it
straddles an edge. A row's gate is ``enforce_gate`` when written, else
``P(top) >= --t`` on an answered row.

Instrument, never intervention (skill ``read-only-instruments``): nothing is
written and nothing feeds the gate. Thresholds here are candidates to read,
not a decision — the enforce threshold is set after the readings.

stdlib only (``python3 scripts/relevance_shadow_reading.py``, plus the
sibling ``_stats.py`` for intervals): it runs against a log directory without
the package installed. Reads ``logs/relevance-YYYY-MM-DD.jsonl``; each row is
projected to the fields below at parse time, so ``content_b64`` is never held,
let alone decoded. Beyond that only ``logs/episodes/`` (the two keys above)
and, for ``--adopt-from-audit``, ``logs/audit.jsonl`` (``ts`` of the latest
approved ``distill-identity`` row).

### Consumption plan (ADR-0101)

(a) The Saturday gate reads the weekly ``margin`` and ``ollama_versions`` lines
in the relevance section of the weekly report; the ``adopt_window`` section is
read in the week after an identity adopt, from the chain stage's JSON
(``pipeline/relevance-adopt-window/``), which the weekly report transcribes.
(b) Four weekly margin readings decide one thing: write an RFC for a
majority-of-two-reads / hysteresis rule near the cut, or record "not adding
it" (the default before the reading). The adopt window opens a re-read (150
labelled posts, ADR-0113 Review-when) only on ``reopen``; ``hold`` and
``indeterminate`` change nothing. (c) Retire the ``margin`` columns once that
one line is written (keep ``ollama_versions``); retire ``adopt_window`` and its
chain stage when identity adopts stop (D-P2-01-3 steady-state declaration).

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
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _stats import newcombe_diff_ci, wilson_ci  # noqa: E402  (sibling import)

SCHEMA = "relevance-shadow-reading/6"
FILE_RE = re.compile(r"^relevance-(\d{4}-\d{2}-\d{2})\.jsonl$")
# Candidate cuts on P(directly on-topic) (RFC-0046: read, not yet chosen).
THRESHOLDS: tuple[float, ...] = (0.3, 0.5, 0.7)
ANSWERED = "answered"
# The allowlist: every other key of a row (content_b64 above all) is dropped
# at parse time.
KEEP = (
    "ts",
    "post_id",
    "session_id",
    "source",
    "domain_source",
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
# failure's "no" would read an outage as disagreement. A row with no live half
# (written from 2026-10-07, RFC-0046 cleanup 2) is judged by its decision alone.
SCORED = "scored"
# RFC-0046: the n the face gate's pre-registered question needs (binomial 95%
# CI half-width ~ 1/sqrt(n) = +-5.7 pt).
DEFAULT_N = 300
# ``core.relevance_state``'s names, copied because this script is stdlib-only:
# the definition the clock counts, and what a row without the field was.
DOMAIN_SOURCE_PRODUCTION = "identity+axioms"
DOMAIN_SOURCE_IDENTITY = "identity"
# ``relevance_gate.SOURCE_FEED``, copied for the same reason; a row without
# the field is a feed row.
SOURCE_FEED = "feed"
# P1-15.3: the gate's production threshold on P(directly on-topic) (ADR-0113
# amendment 1; D-P1-15-1 may move it) and how close to it counts as "near".
ENFORCE_T = 0.3
MARGIN_HALF_WIDTH = 0.05
# P1-15.2 / P2-01.9: below this many posts on a side a rate is a count, not a
# rate; the band the pre-registration reads a before / after difference against.
MIN_POSTS_FOR_RATE = 10
ADOPT_WINDOW_DAYS = 7
ADOPT_BAND = 0.06
EPISODE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.jsonl$")
IDENTITY_ADOPT_COMMAND = "distill-identity"


def iter_rows(logs: Path, start: date, end: date) -> tuple[list[dict[str, Any]], int, int]:
    """Projected feed rows of the window's files, parse failures, and seed rows left out."""
    rows: list[dict[str, Any]] = []
    failures = 0
    seed_rows = 0
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
            if (row.get("source") or SOURCE_FEED) != SOURCE_FEED:
                seed_rows += 1
                continue
            row["day"] = day
            rows.append(row)
    return rows, failures, seed_rows


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


def _judged(row: dict[str, Any]) -> bool:
    """A judgment: the live half ``scored``, or no live half at all (schema 4)."""
    return row.get("live_reason") in (None, SCORED)


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The reading over one set of rows."""
    reasons: dict[str, int] = {}
    for row in rows:
        key = str(row.get("decision_reason"))
        reasons[key] = reasons.get(key, 0) + 1
    scored = [row for row in rows if row.get("live_reason") == SCORED]
    judged = [row for row in rows if _judged(row)]
    answered = [row for row in judged if _is_answered(row)]
    paired = [row for row in answered if isinstance(row.get("live_gate"), bool)]
    live_gated = sum(1 for row in scored if row.get("live_gate") is True)
    by_threshold: dict[str, dict[str, Any]] = {}
    for t in THRESHOLDS:
        would = sum(1 for row in answered if (_p_top(row) or 0.0) >= t)
        agree = sum(1 for row in paired if ((_p_top(row) or 0.0) >= t) == row["live_gate"])
        by_threshold[f"{t:.1f}"] = {
            "would_gate_rate": _rate(would, len(answered)),
            "agreement_with_live": _rate(agree, len(paired)),
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
        "judged": len(judged),
        "answered": len(answered),
        "answered_rate": _rate(len(answered), len(judged)),
        "decision_reasons": dict(sorted(reasons.items())),
        "live_gate_rate": _rate(live_gated, len(scored)),
        "live_gate_rate_answered": _rate(sum(1 for row in paired if row["live_gate"]), len(paired)),
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
    """The rows ``summarize`` counts as answered: a judgment the decision answered.

    A row with a live half needs its comparable ``live_gate`` too (schema 1-3);
    a row without one (schema 4) needs only the decision.
    """
    if not _judged(row) or row.get("decision_reason") != ANSWERED or _p_top(row) is None:
        return False
    return row.get("live_reason") is None or isinstance(row.get("live_gate"), bool)


def _domain_source(row: dict[str, Any]) -> str:
    return str(row.get("domain_source") or DOMAIN_SOURCE_IDENTITY)


def _counts(values: list[Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


def readiness(rows: list[dict[str, Any]], since: datetime, n: int) -> dict[str, Any]:
    """How far the row clock has run since *since*, and when it reaches *n*."""
    timed = [(ts, row) for row in rows if (ts := _ts(row)) is not None and ts >= since]
    answered_any = [(ts, row) for ts, row in timed if _is_answered(row)]
    answered = [
        (ts, row) for ts, row in answered_any if _domain_source(row) == DOMAIN_SOURCE_PRODUCTION
    ]
    posts = {row.get("post_id") for _ts_, row in answered if row.get("post_id")}
    rate_all = rate_day = None
    reach: list[str] | None = None
    last = max((ts for ts, _row in answered), default=None)
    if last is not None:
        # With pre-switch (identity) rows in the span, the clock starts at the
        # first counted row, not at *since*: their hours are not the clock's.
        start = since
        if len(answered) < len(answered_any):
            start = max(since, min(ts for ts, _row in answered))
        span_days = (last - start).total_seconds() / 86400
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
        "domain_source_counted": DOMAIN_SOURCE_PRODUCTION,
        "domain_sources": _counts([_domain_source(row) for _ts_, row in answered_any]),
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


def _latest_per_post(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per ``post_id`` (the latest by ``ts``); rows without an id are dropped."""
    latest: dict[str, tuple[datetime, dict[str, Any]]] = {}
    for row in rows:
        post_id = row.get("post_id")
        ts = _ts(row)
        if not post_id or ts is None:
            continue
        kept = latest.get(str(post_id))
        if kept is None or ts >= kept[0]:
            latest[str(post_id)] = (ts, row)
    return [row for _ts_, row in latest.values()]


def margin(rows: list[dict[str, Any]], t: float = ENFORCE_T) -> dict[str, Any]:
    """Distinct answered posts within ``MARGIN_HALF_WIDTH`` of the cut *t* (post level)."""
    posts = _latest_per_post([row for row in rows if _is_answered(row)])
    # Rounded so the edge is inclusive whatever the float subtraction says
    # (0.35 - 0.3 is 0.04999999999999999).
    near = sum(1 for row in posts if round(abs((_p_top(row) or 0.0) - t), 9) <= MARGIN_HALF_WIDTH)
    return {
        "t": t,
        "half_width": MARGIN_HALF_WIDTH,
        "posts": len(posts),
        "near": near,
        # Counts only below the floor (P2-01.9): a share of fewer than 10 posts
        # is a count with a percent sign.
        "share": _rate(near, len(posts)) if len(posts) >= MIN_POSTS_FOR_RATE else None,
        "share_ci": wilson_ci(near, len(posts)) if len(posts) >= MIN_POSTS_FOR_RATE else None,
    }


def load_ollama_versions(episodes: Path | None, start: date, end: date) -> dict[str, str]:
    """``session_id -> ollama_version`` from the session-start records of the window.

    The only reader of ``logs/episodes/`` here, and it keeps exactly two keys
    of exactly one record kind: every other field of every line is dropped as
    soon as the line is parsed (the folder holds other agents' text; CLAUDE.md
    "episode log"). The day before the window is read too: a session that
    started before midnight writes rows after it.
    """
    versions: dict[str, str] = {}
    if episodes is None or not episodes.is_dir():
        return versions
    for path in sorted(episodes.iterdir()):
        match = EPISODE_FILE_RE.match(path.name)
        if match is None:
            continue
        day = date.fromisoformat(match.group(1))
        if not start - timedelta(days=1) <= day <= end:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            data = record.get("data") if isinstance(record, dict) else None
            if (
                not isinstance(data, dict)
                or record.get("type") != "session"
                or data.get("event") != "start"
            ):
                continue
            session_id, version = data.get("session_id"), data.get("ollama_version")
            if isinstance(session_id, str) and isinstance(version, str):
                versions[session_id] = version
    return versions


def week_versions(
    weeks: dict[str, list[dict[str, Any]]], versions: dict[str, str]
) -> dict[str, dict[str, Any]]:
    """Per ISO week: the Ollama versions behind its rows, and whether that set changed."""
    out: dict[str, dict[str, Any]] = {}
    previous: list[str] | None = None
    for week in sorted(weeks):
        seen: dict[str, int] = {}
        unresolved = 0
        for row in weeks[week]:
            version = versions.get(str(row.get("session_id")))
            if version is None:
                unresolved += 1
            else:
                seen[version] = seen.get(version, 0) + 1
        names = sorted(seen)
        out[week] = {
            "versions": dict(sorted(seen.items())),
            "unresolved": unresolved,
            # The first week has nothing before it to differ from.
            "changed": previous is not None and bool(names) and names != previous,
        }
        if names:
            previous = names
    return out


def _gate_of(row: dict[str, Any], t: float) -> bool | None:
    """A row's gate: the recorded ``enforce_gate``, else P(top) >= *t* on an answered row."""
    if isinstance(row.get("enforce_gate"), bool):
        return row["enforce_gate"]
    if _is_answered(row):
        return (_p_top(row) or 0.0) >= t
    return None


def _side(rows: list[dict[str, Any]], low: datetime, high: datetime, t: float) -> dict[str, Any]:
    """Post-level gate rate of the rows with ``low <= ts < high``."""
    inside = [row for row in rows if (ts := _ts(row)) is not None and low <= ts < high]
    gated = [(row, g) for row in _latest_per_post(inside) if (g := _gate_of(row, t)) is not None]
    passed = sum(1 for _row, g in gated if g)
    enough = len(gated) >= MIN_POSTS_FOR_RATE
    return {
        "from": low.isoformat(),
        "to": high.isoformat(),
        "posts": len(gated),
        "gated": passed,
        "gate_rate": _rate(passed, len(gated)) if enough else None,
        "gate_rate_ci": wilson_ci(passed, len(gated)) if enough else None,
    }


def adopt_window(
    rows: list[dict[str, Any]], adopt_at: datetime, t: float = ENFORCE_T
) -> dict[str, Any]:
    """Post-level gate rate 7 days before and 7 days from *adopt_at*, and their difference."""
    span = timedelta(days=ADOPT_WINDOW_DAYS)
    before = _side(rows, adopt_at - span, adopt_at, t)
    after = _side(rows, adopt_at, adopt_at + span, t)
    diff = ci = None
    verdict = "counts_only"
    if before["gate_rate"] is not None and after["gate_rate"] is not None:
        diff = round(after["gate_rate"] - before["gate_rate"], 4)
        ci = newcombe_diff_ci(before["gated"], before["posts"], after["gated"], after["posts"])
        if ci is not None:
            if ci[0] >= -ADOPT_BAND and ci[1] <= ADOPT_BAND:
                verdict = "hold"
            elif ci[0] > ADOPT_BAND or ci[1] < -ADOPT_BAND:
                verdict = "reopen"
            else:
                verdict = "indeterminate"
    return {
        "adopt_at": adopt_at.isoformat(),
        "t": t,
        "unit": "post",
        "band": ADOPT_BAND,
        "before": before,
        "after": after,
        "difference": diff,
        "difference_ci": ci,
        "verdict": verdict,
    }


def latest_identity_adopt(audit: Path, until: datetime) -> datetime | None:
    """``ts`` of the latest approved ``distill-identity`` row at or before *until*."""
    if not audit.is_file():
        return None
    found: datetime | None = None
    for line in audit.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            not isinstance(record, dict)
            or record.get("command") != IDENTITY_ADOPT_COMMAND
            or record.get("decision") != "approved"
            or not isinstance(record.get("ts"), str)
        ):
            continue
        try:
            ts = parse_since(record["ts"])
        except ValueError:
            continue
        if ts <= until and (found is None or ts > found):
            found = ts
    return found


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
    t: float = ENFORCE_T,
    episodes: Path | None = None,
    adopt_at: datetime | None = None,
) -> dict[str, Any]:
    rows, failures, seed_rows = iter_rows(logs, start, end)
    if since is None:
        since = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    weeks: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        weeks.setdefault(iso_week(row["day"]), []).append(row)
    versions = week_versions(weeks, load_ollama_versions(episodes, start, end))
    result: dict[str, Any] = {
        "schema": SCHEMA,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "parse_failures": failures,
        "seed_rows_excluded": seed_rows,
        "total": {**summarize(rows), "margin": margin(rows, t)},
        "weeks": {
            week: {
                **summarize(weeks[week]),
                "margin": margin(weeks[week], t),
                "ollama": versions[week],
            }
            for week in sorted(weeks)
        },
        "readiness": readiness(rows, since, n),
    }
    if adopt_at is not None:
        result["adopt_window"] = adopt_window(rows, adopt_at, t)
    return result


def reach_line(ready: dict[str, Any]) -> str:
    """The face gate's one line: when n is reached, at the two rates."""
    head = f"n={ready['n']} 到達 [{ready['domain_source_counted']}]: "
    rates = [r for r in (ready["rate_per_day_last_day"], ready["rate_per_day_all"]) if r]
    width = f"{min(rates)}〜{max(rates)} 行/日" if rates else "到達率なし"
    others = sum(
        count
        for source, count in ready["domain_sources"].items()
        if source != ready["domain_source_counted"]
    )
    excluded = f"、{DOMAIN_SOURCE_IDENTITY} 行 {others} は数えない" if others else ""
    tail = f"（{width}、dedupe 後 {ready['answered_dedupe']} 行{excluded}）"
    if ready["reached"]:
        return f"{head}到達済み（answered {ready['answered_rows']} 行）{tail}"
    if ready["reach_dates"] is None:
        return f"{head}見込みなし{tail}"
    first, last = ready["reach_dates"]
    return f"{head}{first}〜{last} 見込み{tail}"


def margin_line(result: dict[str, Any]) -> str:
    """The weekly margin share and any Ollama version change, one line."""
    parts = []
    for week, w in result["weeks"].items():
        m = w["margin"]
        share = f"{m['near']}/{m['posts']}" + (f" ({m['share']})" if m["share"] is not None else "")
        mark = (
            " [ollama changed: " + ", ".join(w["ollama"]["versions"]) + "]"
            if w["ollama"]["changed"]
            else ""
        )
        parts.append(f"{week} {share}{mark}")
    total = result["total"]["margin"]
    return f"margin |P(top) - {total['t']}| <= {total['half_width']} (posts near/all): " + (
        ", ".join(parts) or "none"
    )


def adopt_line(window: dict[str, Any]) -> str:
    """The adopt window's one line a weekly report transcribes."""
    b, a = window["before"], window["after"]

    def side(x: dict[str, Any]) -> str:
        return f"{x['gated']}/{x['posts']}" + (
            f" ({x['gate_rate']})" if x["gate_rate"] is not None else ""
        )

    return (
        f"adopt {window['adopt_at']} post-level gate rate: before {side(b)} -> after {side(a)}, "
        f"diff {window['difference']} CI {window['difference_ci']} (band +-{window['band']}) "
        f"=> {window['verdict']}"
    )


def summary_lines(result: dict[str, Any]) -> list[str]:
    """Seven lines a gate session reads before the JSON (then the margin and adopt lines)."""
    total = result["total"]
    window = result["window"]
    cuts = "  ".join(
        f"t={t}: would {v['would_gate_rate']} / agree {v['agreement_with_live']}"
        for t, v in total["thresholds"].items()
    )
    return [
        f"relevance shadow {window['start']}..{window['end']}: "
        f"{total['rows']} rows ({total['judged']} judged, {total['live_scored']} with a "
        f"live score), {result['parse_failures']} parse failure(s), "
        f"{result['seed_rows_excluded']} seed row(s) left out",
        f"answered {total['answered']} ({total['answered_rate']} of judged); "
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
        margin_line(result),
        *([adopt_line(result["adopt_window"])] if "adopt_window" in result else []),
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
    parser.add_argument(
        "--t", type=float, default=ENFORCE_T, help="the enforce threshold the margin reads against"
    )
    parser.add_argument(
        "--episodes",
        type=Path,
        default=None,
        help="logs/episodes dir for the session_id -> ollama_version join (default <home>/logs/episodes)",
    )
    adopt = parser.add_mutually_exclusive_group()
    adopt.add_argument(
        "--adopt-at", type=parse_since, default=None, help="UTC instant of an identity adopt"
    )
    adopt.add_argument(
        "--adopt-from-audit",
        action="store_true",
        help="take the instant from the latest approved distill-identity row of logs/audit.jsonl",
    )
    args = parser.parse_args(argv)
    if args.end < args.start:
        parser.error("--end is before --start")
    adopt_at = args.adopt_at
    if args.adopt_from_audit:
        until = datetime(
            args.end.year, args.end.month, args.end.day, tzinfo=timezone.utc
        ) + timedelta(days=1)
        adopt_at = latest_identity_adopt(args.home / "logs" / "audit.jsonl", until)
        if adopt_at is None:
            print("adopt window: no identity adopt in audit.jsonl up to --end; section omitted")
    result = reading(
        args.home / "logs",
        args.start,
        args.end,
        since=args.since,
        n=args.n,
        t=args.t,
        episodes=args.episodes or args.home / "logs" / "episodes",
        adopt_at=adopt_at,
    )
    for line in summary_lines(result):
        print(line)
    text = json.dumps(result, indent=1, sort_keys=True)
    print(text)
    if args.json_out is not None:
        args.json_out.write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
