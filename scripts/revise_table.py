#!/usr/bin/env python3
"""One-shot table of the naming stage's ``revise`` verdicts (read-only, stdlib only).

ADR-0111 Consumption plan addendum (2026-10-24, P0-01.6): the ``revise`` rows
in ``logs/insight-stages.jsonl`` accumulate with no reader. The Saturday gate
reads them once, as a table of date / target skill / the model's one-line
reason, to decide whether option B (a replacement path) is viable. This is not
a weekly instrument and is not registered in the census (ADR-0101): run it
once, freeze the output under ``docs/evidence/adr-0111/``, and stop.

Prints no prompt or output bodies — those are base64 in the log and are never
decoded here. ``change_reason`` is model prose written after reading untrusted
observations, so it is control-stripped and clipped before printing.

    python3 scripts/revise_table.py [--log PATH] [--max-reason 120]

``--log`` defaults to ``$MOLTBOOK_HOME/logs/insight-stages.jsonl`` (or
``~/.config/moltbook/logs/insight-stages.jsonl``). Exit 0 and a header-only
table when the log is absent or has no revise rows.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

_CONTROL = re.compile(r"[^\x20-\x7E -￿]")


def default_log() -> Path:
    home = os.environ.get("MOLTBOOK_HOME") or str(Path.home() / ".config" / "moltbook")
    return Path(home) / "logs" / "insight-stages.jsonl"


def revise_rows(lines: list[str]) -> list[dict]:
    rows = []
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            isinstance(record, dict)
            and record.get("kind") == "insight_naming"
            and record.get("verdict") == "revise"
        ):
            rows.append(record)
    return rows


def _clean(value: object, limit: int) -> str:
    text = _CONTROL.sub(" ", str(value or "")).replace("|", "/")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render(rows: list[dict], max_reason: int = 120) -> str:
    out = ["| date | target skill | change reason |", "|---|---|---|"]
    for r in rows:
        date = _clean(str(r.get("ts") or "")[:10], 10)
        out.append(
            f"| {date} | {_clean(r.get('target_skill') or '(none)', 80)} "
            f"| {_clean(r.get('change_reason'), max_reason)} |"
        )
    out.append("")
    out.append(f"{len(rows)} revise row(s)")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--log", type=Path, default=None)
    parser.add_argument("--max-reason", type=int, default=120)
    args = parser.parse_args(argv)
    log = args.log or default_log()
    lines: list[str] = []
    if log.exists():
        lines = log.read_text(encoding="utf-8").splitlines()
    print(render(revise_rows(lines), args.max_reason))
    return 0


if __name__ == "__main__":
    sys.exit(main())
