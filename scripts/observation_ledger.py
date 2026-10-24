#!/usr/bin/env python3
"""Observation ledger for the weekly instrument document (RFC-0010, 2026-08-26).

The ledger is an append-only JSONL file (default:
``$MOLTBOOK_HOME/reports/analysis/observation-ledger.jsonl``). Rows are never
rewritten; state changes (archive, baseline activation) are new rows. Row
types:

    observation        — an open longitudinal observation (O-NNN). Must carry
                         an ``expiry`` condition so it can leave the ledger.
    archive            — closes an observation by id, citing the fired expiry.
    baseline           — an ACTIVE baseline (declared by the Saturday gate or
                         the bootstrap; never by the unattended session).
    baseline_proposal  — a session-proposed baseline awaiting gate ratification.
                         Proposals carry a derived id ``P-NNN`` (ordinal among
                         proposal rows, file order) that the gate commands name.
    baseline_rejection — gate-only: a proposal the gate declined (kept as a row).
    baseline_hold      — gate-only: a proposal the gate deliberately parked; it
                         stays pending but is excluded from the staleness flag.

An ``observation`` may carry ``metric`` (at most ONE open observation per
metric — the append refuses a second unless it ``supersedes`` the first or the
same delta archives it), ``supersedes`` (an open O-id it replaces) and
``expiry_rule`` (``{"kind": "unchanged_weeks", "n": 4}`` or
``{"kind": "event"}``; optional, free-text ``expiry`` stays mandatory). A
``baseline`` row may carry ``band`` (see ``_validate_band``; optional ``reading`` names the readings key,
default the metric) which ``render`` compares with this week's readings
(``--readings``, written by ``surface_counter_scan.py``).

Subcommands:

    render  — print the markdown "current view" the materials embed: open
              observations with week counts, active + proposed baselines, and
              the next free O-id.
    declare-baseline / reject / hold
            — the human gate's commands (``declared_by: gate``). The session
              cannot stage these row types (``_SESSION_TYPES``).
    append  — validate a session-staged delta file and append it to the
              canonical ledger. Fail-closed: ANY invalid row rejects the whole
              delta (exit 1, nothing appended) so a malformed delta cannot
              half-land. The pipeline quarantines the delta on failure.

Deliberately stdlib-only (plus the ``scripts/_md`` neutralizer every LLM-facing
scripts/ render shares, and ``_stats`` for the interval rule) and stateless
beyond the JSONL itself (the ADR-0095 lesson: a ledger that grows
rendering/state-machine machinery becomes its own bug producer).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

from _md import md_safe, printable
from _stats import band_verdict, format_rate, wilson_ci


def _flat(value: object) -> str:
    """Render-side neutralizer for session-authored free text.

    The ledger view is spliced into the materials OUTSIDE the untrusted nonce
    frame, so a newline in a row field would let staged text stand as
    top-level trusted prompt structure. ``printable`` flattens every control
    character (newlines included) and ``md_safe`` the Markdown breakers; the
    append-side validation below rejects such rows outright, and this guard
    covers rows that predate it or arrived out of band.
    """
    return md_safe(printable(str(value)))


def _band_reading(row: dict) -> str:
    """The interval-judged reading of a baseline that declares ``band`` and ``k`` / ``n``.

    A band is judged on the Wilson interval of ``k/n`` (P2-01.9, ``_stats``):
    a point inside the band whose interval crosses an edge is
    ``indeterminate`` (判定不能), and under ten rows only the counts print.
    Empty when the row declares none of it — free-text baselines are unchanged.
    """
    band, k, n = row.get("band"), row.get("k"), row.get("n")
    if not (
        isinstance(band, list)
        and len(band) == 2
        and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in band)
        and isinstance(k, int)
        and isinstance(n, int)
        and not isinstance(k, bool)
        and not isinstance(n, bool)
    ):
        return ""
    return f" — reading {format_rate(k, n)}: {band_verdict(k, n, float(band[0]), float(band[1]))}"


_ID_RE = re.compile(r"^O-\d{3,}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Row types the unattended session may stage. ``baseline`` is absent by
# design: activating a baseline recalibrates what counts as a deviation, and
# calibration changes pass the human gate (RFC-0010 Q5/Q8).
_SESSION_TYPES = {"observation", "archive", "baseline_proposal"}

_PROPOSAL_ID_RE = re.compile(r"^P-\d{3,}$")

# D-P1-05-2 = A (owner, 2026-10-24): an observation open this many weeks must
# leave the ledger — converted to a baseline_proposal (``source_observation``)
# or archived with an RFC. The convention text is in config/prompts/weekly-analysis.md.
FORCE_WEEKS = 8
# A proposal pending longer than this (and not held) is flagged by render.
PROPOSAL_STALE_WEEKS = 2
# Below this denominator a rate is reported as counts only (P2-01.9 rule).
MIN_RATE_DENOMINATOR = 10
_EXPIRY_KINDS = {"unchanged_weeks", "event"}
_ESTIMATORS = {"point", "quantile"}


def _read_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"ledger corrupt at line {lineno}: {exc}") from exc
        if not isinstance(row, dict):
            raise SystemExit(f"ledger corrupt at line {lineno}: row is not an object")
        rows.append(row)
    return rows


def _superseded_ids(row: dict) -> set[str]:
    sup = row.get("supersedes")
    return {sup} if isinstance(sup, str) and sup else set()


def _current_state(rows: list[dict]) -> tuple[dict[str, dict], set[str], list[dict], list[dict]]:
    """Fold rows into (open observations by id, closed ids, active baselines,
    pending proposals).

    Closed ids are archived or superseded observations (never reused).
    Pending proposals are copies carrying ``_pid`` (``P-NNN``) and ``_held``.
    """
    observations: dict[str, dict] = {}
    archived: set[str] = set()
    baselines_by_metric: dict[str, dict] = {}
    proposals: list[dict] = []
    rejected: set[str] = set()  # closed by id: rejected, or ratified by a `baseline` row
    held: set[str] = set()
    for row in rows:
        rtype = row.get("type")
        # .get, not [..]: a malformed historical row must degrade to "skipped"
        # here, never to a traceback — append-side validation rejects new ones.
        if rtype == "observation":
            oid = row.get("id")
            if isinstance(oid, str) and oid:
                observations[oid] = row
                archived.update(_superseded_ids(row))
        elif rtype == "archive":
            oid = row.get("id")
            if isinstance(oid, str) and oid:
                archived.add(oid)
        elif rtype == "baseline":
            # Fold by metric, last row wins: a gate re-declaration supersedes
            # the earlier value instead of rendering two contradictory actives.
            baselines_by_metric[str(row.get("metric", "?"))] = row
            rejected.add(str(row.get("ratifies", "")))
        elif rtype == "baseline_proposal":
            proposals.append(dict(row, _pid=f"P-{len(proposals) + 1:03d}"))
        elif rtype == "baseline_rejection":
            rejected.add(str(row.get("proposal", "")))
        elif rtype == "baseline_hold":
            held.add(str(row.get("proposal", "")))
    open_obs = {oid: row for oid, row in observations.items() if oid not in archived}
    # A proposal is closed once an active baseline exists for its metric (the
    # gate ratifies by appending a `baseline` row, never by rewriting) or the
    # gate rejected it by id.
    pending = _pending_proposals(proposals, set(baselines_by_metric), rejected, held)
    return open_obs, archived, list(baselines_by_metric.values()), pending


def _pending_proposals(
    proposals: list[dict], active_metrics: set[str], rejected: set[str], held: set[str]
) -> list[dict]:
    return [
        dict(row, _held=row["_pid"] in held)
        for row in proposals
        if str(row.get("metric", "?")) not in active_metrics and row["_pid"] not in rejected
    ]


def _next_id(rows: list[dict]) -> str:
    highest = 0
    for row in rows:
        oid = row.get("id", "")
        if isinstance(oid, str) and _ID_RE.match(oid):
            highest = max(highest, int(oid.split("-", 1)[1]))
    return f"O-{highest + 1:03d}"


def _weeks_since(first_seen: str, as_of: str) -> int:
    try:
        start = _dt.date.fromisoformat(first_seen)
        end = _dt.date.fromisoformat(as_of)
    except ValueError:
        return 0
    return max(0, (end - start).days // 7)


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _rate_verdict(k: int, n: int, low: float, high: float, unit: str) -> tuple[str, str]:
    if n < MIN_RATE_DENOMINATOR:
        return "counts-only", f"{k}/{n} (denominator < {MIN_RATE_DENOMINATOR})"
    ci = wilson_ci(k, n)
    if ci is None:
        return "no-reading", f"impossible count {k}/{n}"
    scale = 100.0 if unit == "%" else 1.0
    point, lo_ci, hi_ci = k / n * scale, ci[0] * scale, ci[1] * scale
    detail = f"{point:.1f}{unit} ({k}/{n}; 95% CI {lo_ci:.1f}-{hi_ci:.1f})"
    if hi_ci < low:
        return "below", detail
    if lo_ci > high:
        return "above", detail
    if lo_ci >= low and hi_ci <= high:
        return "in", detail
    return "indeterminate", detail + " — interval crosses a band edge"


def _band_verdict(band: dict, reading: object) -> tuple[str, str]:
    """Machine in / below / above for one band against one reading.

    ``reading`` is ``{"value": x}`` (count-like) or ``{"successes": k,
    "trials": n}`` (a rate; band unit ``%``). A rate is judged by its Wilson
    interval (scripts/_stats.wilson_ci, P2-01.9): denominator < 10 is counts
    only, and an interval that crosses a band edge is "indeterminate" even when
    the point sits inside. Returns (label, detail).
    """
    low, high = _num(band.get("low")), _num(band.get("high"))
    if low is None or high is None or not isinstance(reading, dict):
        return "no-reading", "no reading supplied this week"
    unit = str(band.get("unit", ""))
    k, n = reading.get("successes"), reading.get("trials")
    if isinstance(k, int) and isinstance(n, int) and not isinstance(k, bool):
        return _rate_verdict(k, n, low, high, unit)
    value = _num(reading.get("value"))
    if value is None:
        return "no-reading", "reading has neither value nor successes/trials"
    detail = f"{value:g}{unit}"
    if value < low:
        return "below", detail
    if value > high:
        return "above", detail
    return "in", detail


def _load_readings(path: str) -> dict:
    if not path:
        return {}
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _band_text(band: object) -> str:
    if isinstance(band, list) and len(band) == 2:
        # P2-01.9 form: [lo, hi] judged on the k/n interval (see _band_reading)
        return f"band {_flat(band[0])}–{_flat(band[1])} on k/n"
    if not isinstance(band, dict):
        return "no structured band (prose only)"
    return (
        f"band {_flat(band.get('low', '?'))}–{_flat(band.get('high', '?'))}{_flat(band.get('unit', ''))} "
        f"[{_flat(band.get('estimator', '?'))}, windows {_flat(band.get('windows', '?'))}, "
        f"regime {_flat(band.get('regime', '?'))}]"
    )


def _baseline_line(row: dict, readings: dict) -> str:
    metric = str(row.get("metric", "?"))
    line = (
        f"- **{_flat(metric)}**: "
        f"{_flat(row.get('expected', '?'))} "
        f"(declared {_flat(row.get('declared', '?'))}; {_band_text(row.get('band'))})"
    )
    band = row.get("band")
    if not isinstance(band, dict):
        return line
    label, detail = _band_verdict(band, readings.get(str(band.get("reading") or metric)))
    line += f" → this week: **{label.upper()}** {_flat(detail)}"
    low, high, sd = _num(band.get("low")), _num(band.get("high")), _num(band.get("weekly_sd"))
    if low is not None and high is not None and sd:
        line += f" · band width/SD {(high - low) / sd:.1f}"
    return line


def _expiry_marks(row: dict, weeks: int, linked: bool) -> str:
    marks: list[str] = []
    rule = row.get("expiry_rule")
    if isinstance(rule, dict) and rule.get("kind") == "unchanged_weeks":
        n = rule.get("n")
        if isinstance(n, int) and not isinstance(n, bool) and weeks >= n:
            marks.append(
                f'open ≥ {n}w ({weeks}w) — archive only if the last {n} weekly lines were "unchanged"'
            )
    if weeks >= FORCE_WEEKS:
        marks.append(
            f"AT {FORCE_WEEKS}-WEEK LIMIT — "
            + (
                "linked to a proposal"
                if linked
                else "needs a baseline_proposal or an RFC + archive"
            )
        )
    return " ".join(f"⚑ {m}" for m in marks)


def cmd_render(args: argparse.Namespace) -> int:
    rows = _read_rows(Path(args.ledger))
    open_obs, archived, baselines, proposals = _current_state(rows)
    as_of = args.as_of or _dt.date.today().isoformat()
    readings = _load_readings(getattr(args, "readings", ""))
    linked_ids = {
        str(r.get("source_observation"))
        for r in rows
        if r.get("type") == "baseline_proposal" and r.get("source_observation")
    }

    out: list[str] = ["## Observation Ledger (current view)", ""]
    out.append(
        f"Ledger: {args.ledger} · rows {len(rows)} · open {len(open_obs)} · "
        f"closed {len(archived)} · next id {_next_id(rows)} · as-of {as_of}"
    )
    out.append("")
    out.append("### Open observations")
    out.append("")
    if open_obs:
        for oid in sorted(open_obs):
            row = open_obs[oid]
            weeks = _weeks_since(row.get("first_seen", ""), as_of)
            line = (
                f"- **{oid}** (first seen {_flat(row.get('first_seen', '?'))}, week {weeks}): "
                f"{_flat(row.get('title', '?'))} — {_flat(row.get('summary', ''))} "
                f"[expiry: {_flat(row.get('expiry', 'MISSING'))}]"
            )
            marks = _expiry_marks(row, weeks, oid in linked_ids)
            out.append(f"{line} {marks}".rstrip())
    else:
        out.append("None.")
    out.append("")
    out.append("### Active baselines (declared by gate/bootstrap)")
    out.append("")
    if baselines:
        for row in baselines:
            out.append(_baseline_line(row, readings) + _band_reading(row))
    else:
        out.append("None declared — every observation this week is a novelty, not a deviation.")
    out.append("")
    if proposals:
        out.append("### Proposed baselines (await gate ratification; NOT active)")
        out.append("")
        for row in proposals:
            weeks = _weeks_since(str(row.get("declared", "")), as_of)
            if row["_held"]:
                state = f"HELD by the gate, {weeks}w"
            elif weeks > PROPOSAL_STALE_WEEKS:
                state = f"⚑ STALE {weeks}w pending (> {PROPOSAL_STALE_WEEKS}w) — declare / reject / hold"
            else:
                state = f"{weeks}w pending"
            out.append(
                f"- **{row['_pid']}** {_flat(row.get('metric', '?'))}: "
                f"{_flat(row.get('expected', '?'))} "
                f"(proposed {_flat(row.get('declared', '?'))}, {_flat(row.get('source_report', '?'))}; {state})"
            )
        out.append("")
    print("\n".join(out))
    return 0


def _validate_delta_common_fields(row: dict, i: int, errors: list[str]) -> None:
    """Field-shape checks that apply to every delta row, regardless of type. Appends to
    ``errors`` in place.
    """
    src = row.get("source_report", "")
    if not isinstance(src, str) or not src.startswith("weekly-"):
        errors.append(f"row {i}: source_report missing or malformed")
    for field in (
        "title",
        "summary",
        "expiry",
        "reason",
        "metric",
        "expected",
        "rationale",
        "source_report",
        "metric",
        "supersedes",
        "source_observation",
    ):
        value = row.get(field)
        if isinstance(value, str) and printable(value) != value:
            errors.append(
                f"row {i}: {field} contains control characters (newlines included) — "
                "the render lands outside the untrusted frame, so these rows are refused"
            )


def _validate_expiry_rule(row: dict, i: int, errors: list[str]) -> None:
    """``expiry_rule`` is optional (rows predate it) but, when present, machine-readable."""
    if "expiry_rule" not in row:
        return
    rule = row["expiry_rule"]
    if not isinstance(rule, dict) or rule.get("kind") not in _EXPIRY_KINDS:
        errors.append(f"row {i}: expiry_rule.kind must be one of {sorted(_EXPIRY_KINDS)}")
        return
    if rule["kind"] == "unchanged_weeks":
        n = rule.get("n")
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            errors.append(f"row {i}: expiry_rule unchanged_weeks needs integer n >= 1")


def _validate_open_slot(row: dict, i: int, open_state: dict[str, str], errors: list[str]) -> str:
    """``supersedes`` + one-open-per-metric. Returns the row's metric ("" if none)."""
    sup = row.get("supersedes")
    if sup is not None:
        if not isinstance(sup, str) or sup not in open_state:
            errors.append(f"row {i}: supersedes {sup!r} which is not an open observation")
        else:
            del open_state[sup]
    metric = row.get("metric")
    if metric is None:
        return ""
    if not isinstance(metric, str) or not metric:
        errors.append(f"row {i}: metric must be a non-empty string")
        return ""
    holders = [k for k, v in open_state.items() if v == metric]
    if holders:
        errors.append(
            f"row {i}: metric {metric!r} already has open observation {holders[0]} "
            "(at most one open per metric — supersede or archive it first)"
        )
    return metric


def _validate_observation_row(
    row: dict,
    i: int,
    known_ids: set[str],
    seen_new: set[str],
    open_state: dict[str, str],
    errors: list[str],
) -> None:
    """Validate an ``observation`` delta row.

    ``seen_new`` collects ids accepted earlier in the delta (no reuse).
    ``open_state`` maps every open O-id to its metric ("" when it has none) and
    is advanced in delta order, so "at most one open observation per metric"
    holds after each row: a second open on the same metric is refused unless it
    ``supersedes`` the first or an earlier row of the same delta archived it.
    """
    oid = row.get("id", "")
    if not isinstance(oid, str) or not _ID_RE.match(oid):
        errors.append(f"row {i}: bad observation id {oid!r}")
    elif oid in known_ids or oid in seen_new:
        errors.append(f"row {i}: id {oid} already exists (archived ids are never reused)")
    else:
        seen_new.add(oid)
    if not row.get("expiry"):
        errors.append(f"row {i}: observation {row.get('id')} has no expiry condition")
    if not _DATE_RE.match(str(row.get("first_seen", ""))):
        errors.append(f"row {i}: bad first_seen")
    if not row.get("title") or not row.get("summary"):
        errors.append(f"row {i}: observation needs title and summary")
    _validate_expiry_rule(row, i, errors)
    metric = _validate_open_slot(row, i, open_state, errors)
    if isinstance(oid, str) and _ID_RE.match(oid):
        open_state[oid] = metric


def _validate_archive_row(row: dict, i: int, open_state: dict[str, str], errors: list[str]) -> None:
    """Validate an ``archive`` delta row (advances ``open_state``)."""
    oid = row.get("id", "")
    if oid not in open_state:
        errors.append(f"row {i}: archive targets {oid!r} which is not an open observation")
    else:
        del open_state[oid]
    if not row.get("reason"):
        errors.append(f"row {i}: archive needs a reason citing the fired expiry")


def _validate_baseline_proposal_row(row: dict, i: int, errors: list[str]) -> None:
    """Validate a ``baseline_proposal`` delta row."""
    if not row.get("metric") or not row.get("expected"):
        errors.append(f"row {i}: baseline_proposal needs metric and expected")
    src = row.get("source_observation")
    if src is not None and (not isinstance(src, str) or not _ID_RE.match(src)):
        errors.append(f"row {i}: source_observation must be an O-id")


def _validate_delta(delta_rows: list[dict], ledger_rows: list[dict]) -> list[str]:
    errors: list[str] = []
    open_obs, archived, _, _ = _current_state(ledger_rows)
    known_ids = set(open_obs) | archived
    seen_new: set[str] = set()
    open_state = {
        oid: (m if isinstance(m := row.get("metric"), str) else "") for oid, row in open_obs.items()
    }
    for i, row in enumerate(delta_rows, 1):
        rtype = row.get("type")
        if rtype not in _SESSION_TYPES:
            errors.append(f"row {i}: type {rtype!r} not stageable by the session")
            continue
        _validate_delta_common_fields(row, i, errors)
        if rtype == "observation":
            _validate_observation_row(row, i, known_ids, seen_new, open_state, errors)
        elif rtype == "archive":
            _validate_archive_row(row, i, open_state, errors)
        elif rtype == "baseline_proposal":
            _validate_baseline_proposal_row(row, i, errors)
    return errors


def _stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def cmd_append(args: argparse.Namespace) -> int:
    ledger_path = Path(args.ledger)
    delta_path = Path(args.delta)
    if not delta_path.exists() or delta_path.stat().st_size == 0:
        print("empty delta — nothing to append")
        return 0
    ledger_rows = _read_rows(ledger_path)
    try:
        delta_rows = _read_rows(delta_path)
    except SystemExit as exc:
        print(f"REJECTED: {exc}", file=sys.stderr)
        return 1
    errors = _validate_delta(delta_rows, ledger_rows)
    if errors:
        for err in errors:
            print(f"REJECTED: {err}", file=sys.stderr)
        return 1
    stamp = _stamp()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        for row in delta_rows:
            row = dict(row)
            row["appended_at"] = stamp  # unconditional: the one chain-side provenance stamp
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"appended {len(delta_rows)} row(s) to {ledger_path}")
    return 0


def _validate_band(band: dict, metric: str) -> list[str]:
    """Structural check of a ``baseline.band`` (P1-05.2). Required keys:
    metric (equals the row's), low <= high (numbers), unit, source, estimator
    (point | quantile), windows (int >= 1), regime (free string: the P3-02.1
    boundary-table row id, validated for presence only). ``weekly_sd`` optional.
    """
    errs: list[str] = []
    if band.get("metric") != metric:
        errs.append("band.metric must equal the baseline's metric")
    low, high = _num(band.get("low")), _num(band.get("high"))
    if low is None or high is None or low > high:
        errs.append("band.low / band.high must be numbers with low <= high")
    # "" is a valid unit (counts have no natural one); source / regime need text.
    required = {"unit": False, "source": True, "regime": True}
    for key, non_empty in required.items():
        v = band.get(key)
        if not isinstance(v, str) or (non_empty and not v.strip()):
            errs.append(f"band.{key} must be a {'non-empty ' if non_empty else ''}string")
    if band.get("estimator") not in _ESTIMATORS:
        errs.append(f"band.estimator must be one of {sorted(_ESTIMATORS)}")
    w = band.get("windows")
    if isinstance(w, bool) or not isinstance(w, int) or w < 1:
        errs.append("band.windows must be an integer >= 1")
    if "weekly_sd" in band and (_num(band["weekly_sd"]) is None or band["weekly_sd"] <= 0):
        errs.append("band.weekly_sd must be a positive number")
    for key, value in band.items():
        if isinstance(value, str) and printable(value) != value:
            errs.append(f"band.{key} contains control characters")
    return errs


def _append_gate_row(ledger_path: Path, row: dict) -> None:
    row = dict(row)
    row["appended_at"] = _stamp()
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _clean(value: str) -> bool:
    return bool(value.strip()) and printable(value) == value


def _find_pending(rows: list[dict], pid: str) -> dict | None:
    _, _, _, pending = _current_state(rows)
    return next((r for r in pending if r["_pid"] == pid), None)


def _mark_ratified(row: dict, proposal_id: str) -> None:
    # Ratifying under a different metric name (a re-declaration that replaces an
    # older active baseline) must still close the proposal.
    if proposal_id:
        row["ratifies"] = proposal_id


def cmd_declare_baseline(args: argparse.Namespace) -> int:
    """Gate-only: activate a baseline (``declared_by: gate``). Ratifies by metric,
    exactly as ``_current_state`` closes proposals."""
    ledger = Path(args.ledger)
    rows = _read_rows(ledger)
    metric, expected = args.metric or "", args.expected or ""
    if args.from_proposal:
        prop = _find_pending(rows, args.from_proposal)
        if prop is None:
            print(f"REJECTED: {args.from_proposal} is not a pending proposal", file=sys.stderr)
            return 1
        metric = metric or str(prop.get("metric", ""))
        expected = expected or str(prop.get("expected", ""))
    if not _clean(metric) or not _clean(expected):
        print("REJECTED: metric and expected are required (single-line text)", file=sys.stderr)
        return 1
    if not args.source or not _clean(args.source):
        print("REJECTED: --source (where the band comes from) is required", file=sys.stderr)
        return 1
    row: dict = {
        "type": "baseline",
        "metric": metric,
        "expected": expected,
        "declared": args.date or _dt.date.today().isoformat(),
        "declared_by": "gate",
        "source": args.source,
    }
    _mark_ratified(row, args.from_proposal)
    if args.band_low is not None or args.band_high is not None:
        band: dict = {
            "metric": metric,
            "low": args.band_low,
            "high": args.band_high,
            "unit": args.unit,
            "source": args.source,
            "estimator": args.estimator,
            "windows": args.windows,
            "regime": args.regime,
        }
        if args.weekly_sd is not None:
            band["weekly_sd"] = args.weekly_sd
        if args.reading_key:
            band["reading"] = args.reading_key
        errs = _validate_band(band, metric)
        if errs:
            for err in errs:
                print(f"REJECTED: {err}", file=sys.stderr)
            return 1
        row["band"] = band
    _append_gate_row(ledger, row)
    print(f"declared baseline {metric!r} (declared_by gate) in {ledger}")
    return 0


def _gate_decision(args: argparse.Namespace, rtype: str) -> int:
    ledger = Path(args.ledger)
    if not _PROPOSAL_ID_RE.match(args.id):
        print(f"REJECTED: bad proposal id {args.id!r} (expected P-NNN)", file=sys.stderr)
        return 1
    prop = _find_pending(_read_rows(ledger), args.id)
    if prop is None:
        print(f"REJECTED: {args.id} is not a pending proposal", file=sys.stderr)
        return 1
    if not _clean(args.reason):
        print("REJECTED: --reason is required (single-line text)", file=sys.stderr)
        return 1
    _append_gate_row(
        ledger,
        {
            "type": rtype,
            "proposal": args.id,
            "metric": prop.get("metric", ""),
            "date": args.date or _dt.date.today().isoformat(),
            "reason": args.reason,
            "declared_by": "gate",
        },
    )
    print(f"{rtype} recorded for {args.id} in {ledger}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    return _gate_decision(args, "baseline_rejection")


def cmd_hold(args: argparse.Namespace) -> int:
    return _gate_decision(args, "baseline_hold")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_render = sub.add_parser("render", help="print the markdown current view")
    p_render.add_argument("--ledger", required=True)
    p_render.add_argument("--as-of", default="", help="YYYY-MM-DD for week counts")
    p_render.add_argument(
        "--readings",
        default="",
        help="JSON {metric: {value} | {successes, trials}} for the in/below/above column",
    )
    p_render.set_defaults(func=cmd_render)
    p_decl = sub.add_parser("declare-baseline", help="gate: activate a baseline")
    p_decl.add_argument("--ledger", required=True)
    p_decl.add_argument("--from-proposal", default="", help="P-NNN: take metric/expected from it")
    p_decl.add_argument("--metric", default="")
    p_decl.add_argument("--expected", default="")
    p_decl.add_argument("--source", default="")
    p_decl.add_argument("--date", default="")
    p_decl.add_argument("--band-low", type=float, default=None)
    p_decl.add_argument("--band-high", type=float, default=None)
    p_decl.add_argument("--unit", default="")
    p_decl.add_argument("--estimator", default="point")
    p_decl.add_argument("--windows", type=int, default=1)
    p_decl.add_argument("--regime", default="")
    p_decl.add_argument("--weekly-sd", type=float, default=None)
    p_decl.add_argument(
        "--reading-key",
        default="",
        help="readings key this band is judged against (default: the metric name), "
        "e.g. question_closer.comment from surface_counter_scan.py",
    )
    p_decl.set_defaults(func=cmd_declare_baseline)
    for name, fn, helptext in (
        ("reject", cmd_reject, "gate: decline a pending proposal (kept as a row)"),
        ("hold", cmd_hold, "gate: park a pending proposal (excluded from the stale flag)"),
    ):
        p_dec = sub.add_parser(name, help=helptext)
        p_dec.add_argument("--ledger", required=True)
        p_dec.add_argument("--id", required=True, help="proposal id P-NNN (see render)")
        p_dec.add_argument("--reason", required=True)
        p_dec.add_argument("--date", default="")
        p_dec.set_defaults(func=fn)
    p_append = sub.add_parser("append", help="validate + append a staged delta")
    p_append.add_argument("--ledger", required=True)
    p_append.add_argument("--delta", required=True)
    p_append.set_defaults(func=cmd_append)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
