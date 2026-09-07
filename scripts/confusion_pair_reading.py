"""Weekly stage 7c: the confusion-pair reading and the week's archive candidates (ADR-0105).

Read-only over the store. Writes three artifacts and touches nothing else:

1. ``--json`` — the per-week reading the Saturday gate reads, beside the
   never-selected JSON stage 7b wrote.
2. ``--candidates`` — one store **filename** per line, the union of the
   never-selected strict population and each confusion pair's fewer-selected
   side. This is the file the gate hands to ``adopt-staged --archive-names``;
   nothing here archives anything.
3. ``--findings`` (optional) — the section appended to the week's findings
   document. Facts and pointers, no recommending vocabulary (ADR-0099).

The never-selected strict names are read from stage 7b's JSON rather than
recomputed. This does **not** make the week one log walk: 7b and 7c are
separate processes and each walks the log once (``read_confusion_pairs`` calls
the same ``_scan_selection_history``). What reusing 7b's JSON buys is that the
two halves of the candidate file cannot disagree about the never-selected
population, and that a lost 7b is named rather than read as "nothing to list".

Abstains with a reason code on stderr and exit 2 rather than guessing; the
pipeline turns that into ``CONFUSION_READING_FAILED`` and continues.

Reads ONLY ``skill-selection-*.jsonl`` under ``$MOLTBOOK_HOME/logs`` (through
``core.selection_window``'s file grammar, which filters on that prefix and
never globs the directory), plus the skill store and the value layer. Episode
logs and ``agent-launchd.log`` are unreachable by construction; the
``prompt_b64`` / ``output_b64`` payloads are never decoded.

Usage:
    python scripts/confusion_pair_reading.py --home ~/.config/moltbook \\
        --end-date 2026-09-05 --never-selected NS.json \\
        --json OUT.json --candidates OUT.txt [--findings FINDINGS.md]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

from contemplative_agent.core.skill_confusion import (
    CONFUSION_WINDOW_DAYS,
    archive_candidate_files,
    confusion_reading_json,
    format_confusion_findings,
    read_confusion_pairs,
)


def _abstain(code: str) -> int:
    print(code, file=sys.stderr)
    return 2


def _strict_names(path: Path | None) -> tuple[list[str], str]:
    """Strict never-selected names from stage 7b's JSON, and a reason code.

    A missing or unusable file is **not** an empty population: the candidate
    file would silently lose the ADR-0097 D5 half of the union and still look
    like a complete week. The reason code travels into the reading's own
    reasons so the gate sees which half it is holding.
    """
    if path is None or not path.is_file():
        return [], "CONFUSION_NEVER_SELECTED_MISSING"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [], "CONFUSION_NEVER_SELECTED_UNREADABLE"
    if not isinstance(data, dict) or not isinstance(data.get("strict"), list):
        return [], "CONFUSION_NEVER_SELECTED_UNREADABLE"
    names = [
        row["name"]
        for row in data["strict"]
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    ]
    return names, ""


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--home", required=True, help="store root ($MOLTBOOK_HOME)")
    ap.add_argument("--end-date", required=True, help="window end, UTC day (inclusive)")
    ap.add_argument("--days", type=int, default=CONFUSION_WINDOW_DAYS)
    ap.add_argument("--never-selected", default=None, help="stage 7b's per-week JSON")
    ap.add_argument("--json", required=True, help="where to write the per-week reading")
    ap.add_argument("--candidates", required=True, help="where to write the archive candidates")
    ap.add_argument("--findings", default=None, help="findings document to append the section to")
    args = ap.parse_args()

    # Same shape check as the manual reading's: a `2026-9-05` would select
    # the wrong window rather than fail, and a reading that quietly covers
    # the wrong days is worse than one that refuses.
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.end_date):
        return _abstain("CONFUSION_BAD_END_DATE")
    if args.days < 1:
        return _abstain("CONFUSION_BAD_WINDOW")
    until = date.fromisoformat(args.end_date)
    since = until - timedelta(days=args.days - 1)

    home = Path(args.home)
    log_dir = home / "logs"
    if not log_dir.is_dir():
        return _abstain("CONFUSION_NO_LOG_DIR")
    skills_dir = home / "skills"

    reading = read_confusion_pairs(
        log_dir,
        since=since,
        until=until,
        skills_dir=skills_dir if skills_dir.is_dir() else None,
        # Read-only, and only the mechanism split consults them: a rejected
        # name that is constitution text bled into the answer is not a skill
        # the reader confused. Absent → that rule abstains with a code.
        value_layer_paths=(home / "constitution", home / "identity.md"),
    )
    strict, strict_reason = _strict_names(
        Path(args.never_selected) if args.never_selected else None
    )
    # No ``skill_files`` argument: the reading's own store map is used, so the
    # file is written from the same traversal that decided ``no_file``.
    files, unresolved = archive_candidate_files(reading, strict)

    payload = confusion_reading_json(reading)
    payload["never_selected_strict"] = strict
    payload["candidates"] = list(files)
    payload["unresolved_names"] = list(unresolved)
    if strict_reason:
        payload["reasons"] = [*payload["reasons"], strict_reason]

    Path(args.json).write_text(json.dumps(payload) + "\n", encoding="utf-8")
    # One name per line and a trailing newline even when empty: the shape
    # `adopt-staged --archive-names` parses. An empty file is a real week
    # (nothing to list); the gate must not pass it, because that flag treats
    # an empty selection as a writer bug and exits 2.
    Path(args.candidates).write_text("".join(f"{name}\n" for name in files), encoding="utf-8")

    if args.findings:
        findings = Path(args.findings)
        if findings.is_file():
            section = format_confusion_findings(
                reading,
                strict,
                files,
                str(args.candidates),
                extra_reasons=(strict_reason,) if strict_reason else (),
            )
            with findings.open("a", encoding="utf-8") as handle:
                handle.write("\n" + section + "\n")
        else:
            # Not fatal: the JSON and the candidate file are the artifacts the
            # gate acts on, and a week whose diagnosis was quarantined still
            # has an exit reading.
            print("CONFUSION_FINDINGS_MISSING", file=sys.stderr)

    print(f"pairs={len(reading.pairs)} candidates={len(files)} strict={len(strict)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
