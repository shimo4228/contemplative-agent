#!/usr/bin/env python3
"""Join value-layer state diffs to their ADR-0012 approval records (read-only).

The weekly state diff shows *what* changed in identity / constitution /
skills / rules, and nothing about *whether the change passed the approval
gate*. That gap produced the loudest — and unresolvable — claim in the
2026-08-15 report: "whether it passed through the ``amend-constitution``
approval path is not visible in the operator-facing data supplied here".
``logs/audit.jsonl`` had already answered it. This renders that answer next
to each diff section, so a value-layer change arrives either matched to an
approval row or explicitly flagged as having none.

The *absence* of an approved row for a section that shows a diff is the
alarm condition. It is therefore distinguished, in the rendering, from the
two states that must never read as that alarm:

- the audit log is missing or unreadable (``unavailable``, with a reason
  code) — an unavailable instrument reads zero, not clean (ADR-0077);
- the section shows no diff (``none (no diff either)``).

Windowing: ``--start`` / ``--end`` are the *commit timestamps* of the two
data-repo snapshots the diff is taken between, not the report's calendar
bounds. The interval is half-open, ``start < ts <= end``: anything approved
at or before the start commit is already inside that commit's tree and so
is not part of the diff. Passing calendar dates instead would mis-window by
the sync lag.

Security / boundary (load-bearing):
- Reads ONLY ``audit.jsonl``, which the agent writes itself (never episode
  logs — injection boundary).
- Renders five dense fields per row: ``ts``, ``command``, ``decision``,
  ``source``, ``content_hash``. ``reason`` is operator free text and
  ``source_ids`` is an unbounded lineage list; neither is ever rendered.
  Target paths are not rendered either — skill filenames are slugified from
  distilled pattern text, so they are the one structural field in a record
  that carries content-derived bytes.
- The five rendered fields are written by this codebase from closed
  vocabularies, but are still squashed of non-printables, length-capped and
  pipe-escaped at render: a record is durable state, and a malformed row
  must not break out of its table cell into report prose.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

# Which path shapes belong to which state-diff section. Matched on path
# components rather than a prefix: the audit log records absolute paths from
# whatever MOLTBOOK_HOME was live at write time, which is not necessarily the
# home this scan runs against (backfill runs, relocated data dirs).
_SECTIONS = ("identity", "constitution", "skills", "rules")

_FIELD_CAP = 80
_DEFAULT_TOP = 25


class JoinUnavailable(Exception):
    """The reading cannot be produced. Carries a reason code, never zero."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ``order=True`` is load-bearing: Row is the tie-breaker in the (ts, row) sort
# below, so same-second records would raise on comparison without it.
@dataclass(frozen=True, order=True)
class Row:
    ts: str
    command: str
    decision: str
    source: str
    content_hash: str


@dataclass(frozen=True)
class Reading:
    section: str
    changed: bool
    rows: tuple[Row, ...]
    approved: int
    staged: int
    rejected: int
    other: int
    unparsable: int
    truncated: int
    window_start: str
    window_end: str


def _parse_ts(raw: object) -> datetime | None:
    """ISO-8601 -> aware UTC. Naive input is read as UTC.

    The ``Z`` replace exists for the ``requires-python = ">=3.10"`` floor;
    3.11+ ``fromisoformat`` accepts it natively.
    """
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _matches_section(raw_path: object, section: str) -> bool:
    if not isinstance(raw_path, str) or not raw_path:
        return False
    parts = PurePosixPath(raw_path).parts
    if not parts:
        return False
    if section == "identity":
        return parts[-1] == "identity.md"
    # A directory-shaped section: some *parent* component carries the name.
    # Checking parents only keeps a file literally named ``skills`` out.
    return section in parts[:-1]


def _clean(value: object) -> str:
    """Render one audit field: non-printables squashed, capped, pipe-escaped."""
    if value is None:
        return "—"
    text = "".join(ch if ch.isprintable() else " " for ch in str(value)).strip()
    if not text:
        return "—"
    if len(text) > _FIELD_CAP:
        text = text[: _FIELD_CAP - 1] + "…"
    return text.replace("|", "\\|")


def load_records(audit_path: Path) -> tuple[list[dict[str, Any]], int]:
    """Read audit.jsonl -> (records, unparsable line count).

    A missing or unreadable log raises rather than returning empty: "no
    records" and "cannot tell" are the two states this instrument exists to
    keep apart.
    """
    if not audit_path.is_file():
        raise JoinUnavailable("audit-log-missing")
    try:
        text = audit_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        raise JoinUnavailable("audit-log-unreadable") from None
    records: list[dict[str, Any]] = []
    unparsable = 0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            unparsable += 1
            continue
        if isinstance(record, dict):
            records.append(record)
        else:
            unparsable += 1
    return records, unparsable


def build_reading(
    records: list[dict[str, Any]],
    *,
    section: str,
    changed: bool,
    start: datetime,
    end: datetime,
    unparsable: int = 0,
    top: int = _DEFAULT_TOP,
) -> Reading:
    """Select the section's in-window rows and tally decisions.

    Pure: takes already-loaded records so the join is reproducible offline
    from the same inputs.
    """
    selected: list[tuple[datetime, Row]] = []
    counts = {"approved": 0, "staged": 0, "rejected": 0, "other": 0}
    for record in records:
        if not _matches_section(record.get("path"), section):
            continue
        # Pre-2026-04 records use ``timestamp``; value_layer_due_check.py
        # recognizes both, so this must too or the two readings disagree.
        raw_ts = record.get("ts") or record.get("timestamp")
        parsed = _parse_ts(raw_ts)
        if parsed is None:
            unparsable += 1
            continue
        if not (start < parsed <= end):
            continue
        decision = record.get("decision")
        counts[decision if decision in counts else "other"] += 1
        selected.append(
            (
                parsed,
                Row(
                    ts=_clean(raw_ts),
                    command=_clean(record.get("command")),
                    decision=_clean(decision),
                    source=_clean(record.get("source")),
                    content_hash=_clean(record.get("content_hash")),
                ),
            )
        )
    # Sort on the parsed timestamp, with the rendered tuple as tie-breaker so
    # same-second rows keep a stable order across runs.
    selected.sort(key=lambda item: (item[0], item[1]))
    if top <= 0 or len(selected) <= top:
        shown = selected
    else:
        # The cap must never spend itself on rows that do not answer the
        # question. A busy skills week is ~110 rows dominated by same-second
        # `staged` batches, so a plain head-of-list slice hid all 8 approved
        # rows behind 25 staged ones — while the prompt asks the report to
        # cite an approving row's ts and content_hash. Approved rows are
        # reserved first, the remaining slots go to the earliest others, and
        # the shown set is re-sorted chronologically so the table still reads
        # as a timeline.
        approved_rows = [item for item in selected if item[1].decision == "approved"]
        others = [item for item in selected if item[1].decision != "approved"]
        shown = approved_rows[:top]
        shown.extend(others[: top - len(shown)])
        shown.sort(key=lambda item: (item[0], item[1]))
    return Reading(
        section=section,
        changed=changed,
        rows=tuple(row for _, row in shown),
        approved=counts["approved"],
        staged=counts["staged"],
        rejected=counts["rejected"],
        other=counts["other"],
        unparsable=unparsable,
        truncated=len(selected) - len(shown),
        window_start=_clean(start.isoformat()),
        window_end=_clean(end.isoformat()),
    )


def format_unavailable(reason: str) -> str:
    return (
        f"**Approval provenance**: unavailable (reason={reason}). "
        "This is NOT evidence that the change above lacks an approval record — "
        "the instrument could not read `logs/audit.jsonl`."
    )


def format_reading(reading: Reading) -> str:
    total = reading.approved + reading.staged + reading.rejected + reading.other
    lines = [
        f"**Approval provenance** (`logs/audit.jsonl`, ADR-0012 gate; window "
        f"{reading.window_start} → {reading.window_end}, exclusive of the start "
        f"commit): {total} record(s) — approved {reading.approved}, staged "
        f"{reading.staged}, rejected {reading.rejected}, other {reading.other}."
    ]
    if reading.changed and reading.approved == 0:
        lines.append(
            "⚠️ NO APPROVED RECORD for a section that shows a diff. The state above "
            "changed with no matching approval row in this window — report it as the "
            "observation it is, not as a confirmed gate bypass (a sync lag or a "
            "pre-window approval also produces this shape)."
        )
    elif not reading.changed and total == 0:
        lines.append("No diff and no approval records — nothing to reconcile.")
    if reading.rows:
        lines.append("")
        lines.append("| ts | command | decision | source | content_hash |")
        lines.append("|---|---|---|---|---|")
        lines.extend(
            f"| {row.ts} | {row.command} | {row.decision} | {row.source} | {row.content_hash} |"
            for row in reading.rows
        )
    if reading.truncated:
        lines.append("")
        lines.append(f"({reading.truncated} further record(s) not shown — `--top` cap.)")
    if reading.unparsable:
        lines.append("")
        lines.append(f"({reading.unparsable} audit line(s) unparsable and excluded.)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", required=True, type=Path, help="path to audit.jsonl")
    parser.add_argument("--section", required=True, choices=_SECTIONS)
    parser.add_argument(
        "--diff",
        required=True,
        choices=("changed", "unchanged"),
        help="whether the state-diff section this annotates shows a change",
    )
    parser.add_argument("--start", required=True, help="ISO-8601 start-commit timestamp")
    parser.add_argument("--end", required=True, help="ISO-8601 end-commit timestamp")
    parser.add_argument("--top", type=int, default=_DEFAULT_TOP, help="max rows rendered")
    args = parser.parse_args(argv)

    try:
        start = _parse_ts(args.start)
        end = _parse_ts(args.end)
        if start is None or end is None:
            raise JoinUnavailable("window-unparsable")
        records, unparsable = load_records(args.audit)
    except JoinUnavailable as exc:
        print(format_unavailable(exc.reason))
        return 0

    reading = build_reading(
        records,
        section=args.section,
        changed=args.diff == "changed",
        start=start,
        end=end,
        unparsable=unparsable,
        top=args.top,
    )
    print(format_reading(reading))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
