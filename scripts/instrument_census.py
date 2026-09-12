#!/usr/bin/env python3
"""Instrument census over the self-written logs (read-only, ADR-0107).

Every JSONL file the agent writes under ``$MOLTBOOK_HOME/logs/`` gets a
reader here, each week, whether or not a dedicated instrument exists for it.
The census exists because of a six-month blind spot: the duplicate scoring of
RFC-0032 was recorded from day one in ``llm-calls-*.jsonl`` (same session,
same ``prompt_sha256``, ten times) and no stage of the weekly chain read that
file. Six self-written logs had zero readers; two more were orphans whose
writer had been retired. A ``REGISTRY`` row is the reader: the fields it
names are the question that log is asked every week.

Four sections, in the order a reader needs them:

1. **Census** — one row per registry entry and per unregistered file, with a
   status from a closed vocabulary. This is the stale detector for additions
   and removals: a writer that starts without a registry row shows as
   ``UNKNOWN``; a writer that stops shows as ``NO_ROWS``; a retired writer
   whose file lingers shows as ``ORPHAN``. The Saturday gate fixes the table.
2. **Distributions** — value counts of the declared enum fields, min / median
   / max of the declared numeric fields. No thresholds: readings, not verdicts.
3. **Redundancy** — for entries with a ``redundancy_key``, how often the same
   key repeats *within one session*. Repeats across sessions are legitimate
   (the same post is a new decision the next day); repeats inside a session
   are the RFC-0032 shape.
4. **Projection sample** — a deterministic sample of rows per entry with the
   body fields stripped, one JSON object per line, for the weekly session to
   read as raw-ish data with no question attached. Plus, for ``llm-calls``,
   the longest session's ``caller`` sequence compressed to one line, so a
   repeated call is visible to the eye.

Security (load-bearing):
- Reads ONLY files matched by the registry globs plus the directory listing of
  ``logs/`` (names, not contents) for the UNKNOWN check. It NEVER opens
  ``logs/episodes/`` (raw text authored by other agents — the prompt-injection
  carrier this output must not relay) nor any ``*.log`` (the anomaly sweep's
  ground, and ``agent-launchd.log`` is contaminated — T-LOG-DEBUG-CONTENT).
- The projection strips every field whose name ends in ``_b64`` or contains a
  body-ish token (``content``, ``prompt``, ``output``, ``body``, ``message``,
  ``text``, ``reason``, ``note``), every string value longer than ``MAX_STR``,
  and every list of strings (model-produced names). What survives is
  timestamps, enums, numbers, ids and digests.
  ``tests/test_instrument_census.py`` pins that boundary.
- Enum values are rendered through ``md_safe`` and truncated; they are
  self-written vocabulary, but the render is fed to an LLM.

Consumption plan (ADR-0101): the weekly session's Phase 0 reads sections 2-4;
the Saturday gate reads section 1's non-OK rows and edits ``REGISTRY``. The
census retires when writing to ``logs/`` requires a registry row at write
time (a contract in ``append_jsonl_restricted``), which would make the weekly
UNKNOWN check redundant.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from _md import md_safe

# Episode-log day files (any suffix — .bak, .pre-cleanup.bak) live in
# logs/episodes/ since ADR-0107; this pattern guards the census against a
# stray copy left directly under logs/ by an older layout.
_EPISODE_NAME_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}\.jsonl")

MAX_STR = 200
_BODY_TOKENS = ("content", "prompt", "output", "body", "message", "text", "reason", "note")
_TOP_VALUES = 8
_TOP_REDUNDANT = 10
_VALUE_MAX_CHARS = 60

LIVE = "live"
WRITER_RETIRED = "writer_retired"


@dataclass(frozen=True)
class Entry:
    """One registered self-written log.

    ``enum_fields`` / ``numeric_fields`` are the weekly question for this file.
    ``redundancy_key`` names the fields whose identical repetition inside one
    ``session_id`` is suspicious. ``expect_events`` lists ``event`` values that
    must appear at least once per window (a heartbeat); absence is a status.
    """

    glob: str
    owner_adr: str
    status: str = LIVE
    enum_fields: tuple[str, ...] = ()
    numeric_fields: tuple[str, ...] = ()
    redundancy_key: tuple[str, ...] | None = None
    expect_events: tuple[str, ...] = ()
    note: str = ""

    def matches(self, name: str) -> bool:
        return Path(name).match(self.glob)


# The registry IS the reader. Add a row when a writer is added; flip status to
# writer_retired when the writer is removed (the file lingers as ORPHAN until
# the gate deletes it, then the row goes). Never list logs/episodes/ here.
REGISTRY: tuple[Entry, ...] = (
    Entry(
        "llm-calls-*.jsonl",
        "ADR-0065",
        enum_fields=("caller", "outcome", "error_kind", "done_reason"),
        numeric_fields=("duration_ms",),
        # prompt_norm_sha256, not prompt_sha256: the raw digest changes with
        # every wrapped call (fresh delimiter nonce) and reads 0 repeats over
        # a week of RFC-0032 duplicates. Rows before 2026-09-12 lack the field
        # and are not counted.
        redundancy_key=("caller", "prompt_norm_sha256"),
        note="same prompt re-sent within a session (RFC-0032 shape); per-caller outcome / truncation",
    ),
    Entry(
        "constitution-shadow.jsonl",
        "ADR-0092",
        enum_fields=("verdict",),
        numeric_fields=("cosine_vs_current",),
        note="shadow-constitution divergence as a weekly reading (input to the next amendment gate)",
    ),
    Entry(
        "injection-detect-*.jsonl",
        "ADR-0075",
        enum_fields=("event", "saturated"),
        numeric_fields=("total_removed",),
        expect_events=("guard_alive",),
        note="guard heartbeat present; token removals observed",
    ),
    Entry(
        "verification-audit.jsonl",
        "ADR-0062",
        enum_fields=("solve_success", "verify_success", "action", "solver_path"),
        note="CAPTCHA solve / verify success",
    ),
    Entry(
        "weekly-pipeline-audit.jsonl",
        "ADR-0085",
        enum_fields=("event", "stage", "result", "reason"),
        note="which chain stage failed with which reason (the watchdog sees artifacts only)",
    ),
    Entry(
        "pipeline-metrics.jsonl",
        "ADR-0085",
        enum_fields=("phase", "verdict"),
        note="Saturday gate verdict distribution",
    ),
    Entry(
        "insight-novelty.jsonl",
        "ADR-0096",
        enum_fields=("verdict", "reason"),
        note="novelty judge fail_open share",
    ),
    Entry("insight-staged.jsonl", "ADR-0097", note="rows staged this window"),
    Entry(
        "submolt-scope-*.jsonl",
        "ADR-0086",
        enum_fields=("event", "verdict", "subscribed"),
        note="scan completion",
    ),
    Entry(
        "api-audit.jsonl",
        "ADR-0062",
        enum_fields=("method", "endpoint", "status"),
        note="status per endpoint (the drift scan reads schema only)",
    ),
    Entry(
        "audit.jsonl",
        "ADR-0012",
        enum_fields=("decision", "source", "command"),
        note="approval decisions",
    ),
    Entry(
        "skill-selection-*.jsonl",
        "ADR-0076",
        enum_fields=("kind", "verdict", "enforced", "publish_status"),
        # Repeat reading for selection prompts rides llm-calls (caller
        # core.skill_selection); this file's prompt_sha256 is the raw, nonce-
        # bearing digest and would read 0.
        note="verdict / enforcement mix; publish status of the linked comment",
    ),
    Entry(
        "comment-outcomes.jsonl",
        "ADR-0106",
        enum_fields=("kind", "by_self"),
        note="record kinds",
    ),
    Entry("insight-worth.jsonl", "ADR-0097", status=WRITER_RETIRED, note="worth gate removed"),
    Entry(
        "noise-*.jsonl", "ADR-0060", status=WRITER_RETIRED, note="ingest-time noise gate removed"
    ),
)

# Status vocabulary (closed).
OK = "OK"
NO_ROWS = "NO_ROWS"
MISSING_EVENT = "MISSING_EVENT"
ORPHAN = "ORPHAN"
UNKNOWN = "UNKNOWN"
ABSENT = "ABSENT"


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
    enums: dict[str, Counter] = field(default_factory=dict)
    numerics: dict[str, list[float]] = field(default_factory=dict)
    redundancy: list[tuple[tuple, int, Counter]] = field(default_factory=list)
    redundant_keys: int = 0
    redundant_calls: int = 0
    sample: list[dict] = field(default_factory=list)
    caller_sequence: str | None = None


def _is_forbidden_name(name: str) -> bool:
    return bool(_EPISODE_NAME_RE.match(name)) or ".log" in name


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _in_window(dt: datetime, start: date, end: date) -> bool:
    d = dt.astimezone(timezone.utc).date()
    return start <= d <= end


def strip_body(record: dict) -> dict:
    """Return a copy of ``record`` with body-shaped fields removed.

    Denylist by NAME (``_b64`` suffix, body-ish tokens) and by SHAPE (strings
    longer than ``MAX_STR``). Nested dicts are stripped recursively; a list
    survives only if every element is a non-text scalar (bool / int / float /
    None) — one string element drops the whole list regardless of its length,
    because lists of strings are model-produced names (ADR-0083).
    """
    out: dict = {}
    for k, v in record.items():
        kl = k.lower()
        if kl.endswith("_b64"):
            continue
        bodyish = any(tok in kl for tok in _BODY_TOKENS) and not kl.endswith("_sha256")
        if isinstance(v, (bool, int, float)) or v is None:
            out[k] = v  # counts and flags never carry text (prompt_chars, has_format …)
            continue
        if bodyish:
            continue
        if isinstance(v, str):
            if len(v) > MAX_STR:
                continue
            out[k] = v
        elif isinstance(v, dict):
            out[k] = strip_body(v)
        elif isinstance(v, list):
            # Lists of strings are names and labels the model produced
            # (selected / rejected skill names, deferred topics) — text
            # shaped by untrusted input, which the skill-selection renderer
            # deliberately keeps out of the prompt (ADR-0083). Only scalar
            # non-text lists survive.
            if all(isinstance(x, (bool, int, float)) or x is None for x in v):
                out[k] = v
        else:
            out[k] = v
    return out


class _Acc:
    """Per-entry accumulators for one pass over the files (mutable, local)."""

    def __init__(self, entry: Entry) -> None:
        self.entry = entry
        self.enums: dict[str, Counter] = {f: Counter() for f in entry.enum_fields}
        self.numerics: dict[str, list[float]] = {f: [] for f in entry.numeric_fields}
        self.sessions: set[str] = set()
        # (session, key) -> outcome counter
        self.key_counts: dict[tuple, Counter] = defaultdict(Counter)
        self.seen_events: set[str] = set()
        self.window_rows: list[dict] = []
        self.per_session_callers: dict[str, list[str]] = defaultdict(list)
        self.last: datetime | None = None

    def ingest(self, rec: dict, dt: datetime) -> None:
        entry = self.entry
        if self.last is None or dt > self.last:
            self.last = dt
        sid = rec.get("session_id")
        if isinstance(sid, str):
            self.sessions.add(sid)
        for f in entry.enum_fields:
            if f in rec:
                self.enums[f][_short(rec[f])] += 1
        for f in entry.numeric_fields:
            v = rec.get(f)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                self.numerics[f].append(float(v))
        ev = rec.get("event")
        if isinstance(ev, str):
            self.seen_events.add(ev)
        if isinstance(sid, str):
            self._track_session(rec, sid)
        self.window_rows.append(rec)

    def _track_session(self, rec: dict, sid: str) -> None:
        entry = self.entry
        if entry.redundancy_key:
            key = tuple(_short(rec.get(f)) for f in entry.redundancy_key)
            if all(k != "None" for k in key):
                self.key_counts[(sid, key)][_short(rec.get("outcome"))] += 1
        if entry.glob.startswith("llm-calls"):
            self.per_session_callers[sid].append(_short(rec.get("caller")))


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
        if not isinstance(rec, dict):
            r.parse_failures += 1
            continue
        yield rec


def _read_entry(
    entry: Entry, files: list[Path], start: date, end: date, *, sample_n: int, seed: str
) -> Reading:
    r = Reading(entry=entry, name=entry.glob, status=OK, files=len(files))
    acc = _Acc(entry)
    for path in files:
        for rec in _iter_rows(path, r):
            dt = _parse_ts(rec.get("ts"))
            if dt is None:
                r.rows_without_ts += 1
            elif not _in_window(dt, start, end):
                r.rows_out_of_window += 1
            else:
                r.rows += 1
                acc.ingest(rec, dt)

    r.sessions = len(acc.sessions)
    r.last_ts = (
        acc.last.astimezone(timezone.utc).isoformat(timespec="seconds") if acc.last else None
    )
    r.enums = acc.enums
    r.numerics = acc.numerics
    if r.rows == 0:
        r.status = NO_ROWS
    elif any(ev not in acc.seen_events for ev in entry.expect_events):
        r.status = MISSING_EVENT

    redundant = [
        ((sid, key), sum(outs.values()), outs)
        for (sid, key), outs in acc.key_counts.items()
        if sum(outs.values()) >= 2
    ]
    redundant.sort(key=lambda t: -t[1])
    r.redundancy = redundant[:_TOP_REDUNDANT]
    r.redundant_keys = len(redundant)
    r.redundant_calls = sum(n - 1 for _, n, _ in redundant)

    if acc.window_rows and sample_n > 0:
        rng = random.Random(f"census-{seed}-{entry.glob}")
        picked = rng.sample(acc.window_rows, min(sample_n, len(acc.window_rows)))
        picked.sort(key=lambda rec: str(rec.get("ts")))
        r.sample = [strip_body(rec) for rec in picked]
    if acc.per_session_callers:
        sid, callers = max(acc.per_session_callers.items(), key=lambda kv: len(kv[1]))
        r.caller_sequence = (
            _compress_sequence(callers) + f"  (session {sid[:12]}, {len(callers)} calls)"
        )
    return r


def _short(v: object) -> str:
    s = "None" if v is None else str(v)
    return s if len(s) <= _VALUE_MAX_CHARS else s[: _VALUE_MAX_CHARS - 1] + "…"


def _compress_sequence(items: list[str]) -> str:
    """``a a a b a`` → ``a ×3, b ×1, a ×1`` — runs, not totals, so order survives."""
    out: list[str] = []
    run: str | None = None
    n = 0
    for it in items:
        if it == run:
            n += 1
        else:
            if run is not None:
                out.append(f"{run} ×{n}")
            run, n = it, 1
    if run is not None:
        out.append(f"{run} ×{n}")
    return ", ".join(out)


def census(logs_dir: Path, start: date, end: date, *, sample_n: int, seed: str) -> list[Reading]:
    """Match every file directly under ``logs_dir`` against the registry."""
    readings: list[Reading] = []
    names = sorted(p.name for p in logs_dir.iterdir() if p.is_file()) if logs_dir.is_dir() else []
    claimed: set[str] = set()
    for entry in REGISTRY:
        matched = [logs_dir / n for n in names if entry.matches(n)]
        claimed.update(p.name for p in matched)
        if entry.status == WRITER_RETIRED:
            readings.append(
                Reading(
                    entry=entry,
                    name=entry.glob,
                    status=ORPHAN if matched else ABSENT,
                    files=len(matched),
                )
            )
            continue
        if not matched:
            readings.append(Reading(entry=entry, name=entry.glob, status=ABSENT))
            continue
        readings.append(_read_entry(entry, matched, start, end, sample_n=sample_n, seed=seed))
    for n in names:
        if n in claimed or _is_forbidden_name(n):
            continue
        readings.append(Reading(entry=None, name=n, status=UNKNOWN, files=1))
    return readings


def _render_census_table(readings: list[Reading]) -> list[str]:
    lines: list[str] = []
    non_ok = [r for r in readings if r.status != OK]
    if non_ok:
        lines.append(
            "**"
            + ", ".join(f"{r.status} `{md_safe(r.name)}`" for r in non_ok)
            + "** — the Saturday gate edits `REGISTRY` in `scripts/instrument_census.py` "
            "(register / retire) or removes the file."
        )
    else:
        lines.append("All registered logs wrote this window; no unregistered files.")
    lines.append("")
    lines.append("| Status | Log | Files | Rows in window | Sessions | Last ts | Question |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in readings:
        q = md_safe(r.entry.note) if r.entry else "not in REGISTRY — register or retire"
        lines.append(
            f"| {r.status} | `{md_safe(r.name)}` | {r.files} | {r.rows} | {r.sessions} | "
            f"{r.last_ts or '—'} | {q} |"
        )
    # Out-of-window rows are the file's history and expected; rows the census
    # could not place (no ts) or parse are a defect and are named.
    skipped = [r for r in readings if r.rows_without_ts or r.parse_failures]
    if skipped:
        lines.append("")
        lines.append(
            "Rows not counted: "
            + "; ".join(
                f"`{md_safe(r.name)}` no-ts {r.rows_without_ts}, unparsable {r.parse_failures}"
                for r in skipped
            )
        )
    return lines


def _render_distributions(readings: list[Reading]) -> list[str]:
    lines = ["### Distributions", ""]
    any_dist = False
    for r in readings:
        if r.status in (ORPHAN, ABSENT, UNKNOWN, NO_ROWS) or r.entry is None:
            continue
        parts: list[str] = []
        for f, c in r.enums.items():
            if not c:
                continue
            top = ", ".join(f"{md_safe(v)} {n}" for v, n in c.most_common(_TOP_VALUES))
            more = len(c) - _TOP_VALUES
            parts.append(f"  - `{f}`: {top}" + (f" (+{more} more)" if more > 0 else ""))
        for f, vals in r.numerics.items():
            if not vals:
                continue
            parts.append(
                f"  - `{f}`: min {min(vals):.3g} · median {statistics.median(vals):.3g} · "
                f"max {max(vals):.3g} (n={len(vals)})"
            )
        if parts:
            any_dist = True
            lines.append(f"- `{md_safe(r.name)}`")
            lines.extend(parts)
    if not any_dist:
        lines.append("No distributions (no declared fields with rows in window).")
    return lines


def _render_redundancy(readings: list[Reading]) -> list[str]:
    lines = ["### Redundancy (same key repeated within one session)", ""]
    any_red = False
    for r in readings:
        if r.entry is None or not r.entry.redundancy_key or r.status in (ORPHAN, ABSENT, NO_ROWS):
            continue
        any_red = True
        key_desc = " + ".join(r.entry.redundancy_key)
        lines.append(
            f"- `{md_safe(r.name)}` key = ({key_desc}): {r.redundant_keys} keys repeated, "
            f"{r.redundant_calls} redundant calls (Σ n−1), "
            f"max repeat {max((n for _, n, _ in r.redundancy), default=0)}"
        )
        for (sid, key), n, outs in r.redundancy:
            key_s = " / ".join(md_safe(k) for k in key)
            outs_s = ", ".join(f"{md_safe(o)} {c}" for o, c in outs.most_common())
            lines.append(f"  - ×{n} `{key_s}` session {md_safe(sid[:12])} → {outs_s}")
    if not any_red:
        lines.append("No redundancy keys with rows in window.")
    return lines


def _render_sample(readings: list[Reading]) -> list[str]:
    lines = ["### Projection sample (body fields stripped; read for anything unexpected)", ""]
    any_sample = False
    for r in readings:
        if not r.sample:
            continue
        any_sample = True
        lines.append(f"#### `{md_safe(r.name)}` — {len(r.sample)} of {r.rows} rows")
        if r.caller_sequence:
            lines.append("")
            lines.append(f"Longest session, caller sequence: {md_safe(r.caller_sequence)}")
        lines.append("")
        lines.append("```")
        for rec in r.sample:
            lines.append(md_safe(json.dumps(rec, ensure_ascii=False, sort_keys=True, default=str)))
        lines.append("```")
        lines.append("")
    if not any_sample:
        lines.append("No rows to sample.")
    return lines


def render_markdown(readings: list[Reading], *, start: date, end: date, logs_dir: Path) -> str:
    lines = ["## Instrument Census", ""]
    lines.append(
        f"Window: {start} – {end} (by `ts`, UTC date). Source: `{logs_dir}` — self-written JSONL "
        "only; `episodes/` and `*.log` are never opened here (ADR-0107). Readings, not verdicts."
    )
    lines.append("")
    lines.extend(_render_census_table(readings))
    lines.append("")
    lines.extend(_render_distributions(readings))
    lines.append("")
    lines.extend(_render_redundancy(readings))
    lines.append("")
    lines.extend(_render_sample(readings))
    return "\n".join(lines).rstrip() + "\n"


def run(home: Path, start: date, end: date, *, sample_n: int) -> str:
    logs_dir = home / "logs"
    readings = census(logs_dir, start, end, sample_n=sample_n, seed=end.isoformat())
    return render_markdown(readings, start=start, end=end, logs_dir=logs_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Instrument census over self-written logs (ADR-0107)."
    )
    parser.add_argument("--home", type=Path, required=True, help="MOLTBOOK_HOME")
    parser.add_argument(
        "--start", type=date.fromisoformat, required=True, help="YYYY-MM-DD inclusive"
    )
    parser.add_argument(
        "--end", type=date.fromisoformat, required=True, help="YYYY-MM-DD inclusive (sample seed)"
    )
    parser.add_argument(
        "--sample", type=int, default=30, help="projection rows per log (0 disables)"
    )
    args = parser.parse_args(argv)
    try:
        print(run(args.home, args.start, args.end, sample_n=args.sample))
    except Exception as exc:  # observability only — never break the weekly chain
        print(
            f"## Instrument Census\n\nunavailable (reason=exception: {type(exc).__name__}: {md_safe(str(exc))})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
