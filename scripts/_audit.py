"""Shared audit.jsonl line grammar for scripts/ deterministic intakes.

Sibling-imported like `_scan.py` and `_md.py` (the scripts/ dir is not a
package; `python3 scripts/<name>.py` puts it on sys.path).

Only the *line* grammar lives here — how a timestamp is spelled, what makes a
line a record, and the closed command vocabulary the log is written with. The
abstain policy does not: `value_layer_due_check` refuses a non-UTF-8 log
(`AUDIT_UNREADABLE`) while `value_layer_approval_join` decodes with
`errors="replace"` and continues, and those are deliberate differences in what
each reading is for. What must NOT differ is the parse, because both feed the
same weekly packet: if they disagree about which records fall in the window,
§8 (cadence) and the approval-provenance annotation describe different weeks
under one heading.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

# Commands whose write targets the identity layer. `distill-identity-ca` is the
# shelved ADR-0013 path, kept because the log is append-only. Shared rather
# than restated per module: `value_layer_due_check` counts these rows to decide
# the monthly cadence and `value_layer_approval_join` uses them to place a row
# whose leaf name was renamed by the collision guard — a rename of the command
# that reached only one of the two would silently re-open the 2026-08-15 drop
# (a row counted by neither reading is invisible, not loud).
IDENTITY_COMMANDS = frozenset({"distill-identity", "distill-identity-ca"})


def parse_ts(raw: object) -> datetime | None:
    """ISO-8601 -> aware UTC. Naive input is read as UTC.

    The ``Z`` replace exists for the ``requires-python = ">=3.10"`` floor;
    3.11+ ``fromisoformat`` accepts it natively. ``astimezone`` matters for the
    day arithmetic downstream: ``.date()`` on a non-UTC offset would shift the
    day boundary and flip ``due`` at the interval edge.
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


def parse_records(text: str) -> tuple[list[dict[str, Any]], int]:
    """Split already-decoded log text into (records, unparsable line count).

    A line that is valid JSON but not an object counts as unparsable rather
    than being dropped silently — "cannot tell" and "nothing there" are the two
    states these instruments exist to keep apart.

    Decoding and the missing-file decision stay with the caller: those are the
    policy half, and the two callers answer them differently on purpose.
    """
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
