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

Subcommands:

    render  — print the markdown "current view" the materials embed: open
              observations with week counts, active + proposed baselines, and
              the next free O-id.
    append  — validate a session-staged delta file and append it to the
              canonical ledger. Fail-closed: ANY invalid row rejects the whole
              delta (exit 1, nothing appended) so a malformed delta cannot
              half-land. The pipeline quarantines the delta on failure.

Deliberately stdlib-only (plus the ``scripts/_md`` neutralizer every LLM-facing
scripts/ render shares) and stateless beyond the JSONL itself (the ADR-0095
lesson: a ledger that grows rendering/state-machine machinery becomes its own
bug producer).
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import sys
from pathlib import Path

from _md import md_safe, printable


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


_ID_RE = re.compile(r"^O-\d{3,}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Row types the unattended session may stage. ``baseline`` is absent by
# design: activating a baseline recalibrates what counts as a deviation, and
# calibration changes pass the human gate (RFC-0010 Q5/Q8).
_SESSION_TYPES = {"observation", "archive", "baseline_proposal"}


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


def _current_state(rows: list[dict]) -> tuple[dict[str, dict], set[str], list[dict], list[dict]]:
    """Fold rows into (open observations by id, archived ids, active baselines,
    proposed baselines)."""
    observations: dict[str, dict] = {}
    archived: set[str] = set()
    baselines_by_metric: dict[str, dict] = {}
    proposals: list[dict] = []
    for row in rows:
        rtype = row.get("type")
        # .get, not [..]: a malformed historical row must degrade to "skipped"
        # here, never to a traceback — append-side validation rejects new ones.
        if rtype == "observation":
            oid = row.get("id")
            if isinstance(oid, str) and oid:
                observations[oid] = row
        elif rtype == "archive":
            oid = row.get("id")
            if isinstance(oid, str) and oid:
                archived.add(oid)
        elif rtype == "baseline":
            # Fold by metric, last row wins: a gate re-declaration supersedes
            # the earlier value instead of rendering two contradictory actives.
            baselines_by_metric[str(row.get("metric", "?"))] = row
        elif rtype == "baseline_proposal":
            proposals.append(row)
    open_obs = {oid: row for oid, row in observations.items() if oid not in archived}
    # A proposal is closed once an active baseline exists for its metric —
    # the gate ratifies by appending a `baseline` row, never by rewriting.
    proposals = [row for row in proposals if str(row.get("metric", "?")) not in baselines_by_metric]
    return open_obs, archived, list(baselines_by_metric.values()), proposals


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


def cmd_render(args: argparse.Namespace) -> int:
    rows = _read_rows(Path(args.ledger))
    open_obs, archived, baselines, proposals = _current_state(rows)
    as_of = args.as_of or _dt.date.today().isoformat()

    out: list[str] = ["## Observation Ledger (current view)", ""]
    out.append(
        f"Ledger: {args.ledger} · rows {len(rows)} · open {len(open_obs)} · "
        f"archived {len(archived)} · next id {_next_id(rows)} · as-of {as_of}"
    )
    out.append("")
    out.append("### Open observations")
    out.append("")
    if open_obs:
        for oid in sorted(open_obs):
            row = open_obs[oid]
            weeks = _weeks_since(row.get("first_seen", ""), as_of)
            out.append(
                f"- **{oid}** (first seen {_flat(row.get('first_seen', '?'))}, week {weeks}): "
                f"{_flat(row.get('title', '?'))} — {_flat(row.get('summary', ''))} "
                f"[expiry: {_flat(row.get('expiry', 'MISSING'))}]"
            )
    else:
        out.append("None.")
    out.append("")
    out.append("### Active baselines (declared by gate/bootstrap)")
    out.append("")
    if baselines:
        for row in baselines:
            out.append(
                f"- **{_flat(row.get('metric', '?'))}**: "
                f"{_flat(row.get('expected', '?'))} "
                f"(declared {_flat(row.get('declared', '?'))})"
            )
    else:
        out.append("None declared — every observation this week is a novelty, not a deviation.")
    out.append("")
    if proposals:
        out.append("### Proposed baselines (await gate ratification; NOT active)")
        out.append("")
        for row in proposals:
            out.append(
                f"- {_flat(row.get('metric', '?'))}: "
                f"{_flat(row.get('expected', '?'))} "
                f"(proposed {_flat(row.get('declared', '?'))}, {_flat(row.get('source_report', '?'))})"
            )
        out.append("")
    print("\n".join(out))
    return 0


def _validate_delta(delta_rows: list[dict], ledger_rows: list[dict]) -> list[str]:
    errors: list[str] = []
    open_obs, archived, _, _ = _current_state(ledger_rows)
    known_ids = set(open_obs) | archived
    seen_new: set[str] = set()
    for i, row in enumerate(delta_rows, 1):
        rtype = row.get("type")
        if rtype not in _SESSION_TYPES:
            errors.append(f"row {i}: type {rtype!r} not stageable by the session")
            continue
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
        ):
            value = row.get(field)
            if isinstance(value, str) and printable(value) != value:
                errors.append(
                    f"row {i}: {field} contains control characters (newlines included) — "
                    "the render lands outside the untrusted frame, so these rows are refused"
                )
        if rtype == "observation":
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
        elif rtype == "archive":
            oid = row.get("id", "")
            if oid not in open_obs:
                errors.append(f"row {i}: archive targets {oid!r} which is not an open observation")
            if not row.get("reason"):
                errors.append(f"row {i}: archive needs a reason citing the fired expiry")
        elif rtype == "baseline_proposal":
            if not row.get("metric") or not row.get("expected"):
                errors.append(f"row {i}: baseline_proposal needs metric and expected")
    return errors


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
    stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        for row in delta_rows:
            row = dict(row)
            row["appended_at"] = stamp  # unconditional: the one chain-side provenance stamp
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"appended {len(delta_rows)} row(s) to {ledger_path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_render = sub.add_parser("render", help="print the markdown current view")
    p_render.add_argument("--ledger", required=True)
    p_render.add_argument("--as-of", default="", help="YYYY-MM-DD for week counts")
    p_render.set_defaults(func=cmd_render)
    p_append = sub.add_parser("append", help="validate + append a staged delta")
    p_append.add_argument("--ledger", required=True)
    p_append.add_argument("--delta", required=True)
    p_append.set_defaults(func=cmd_append)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
