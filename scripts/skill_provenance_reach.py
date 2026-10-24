#!/usr/bin/env python3
"""Reach check: every public skill -> the ``knowledge.json`` rows it came from.

stdlib-only (run with ``python3 -I``). Reads a checkout of the public data
repo (or ``$MOLTBOOK_HOME``): ``skills/*.md`` and ``knowledge.json``. For each
skill it reads the frontmatter ``source_ids`` (``pattern_id`` hashes,
RFC P3-05.8), recomputes ``pattern_id = sha256(f"{distilled}|{pattern}")[:12]``
for every row, and resolves the ids. The chain stops at ``knowledge.json``:
``provenance.source_episode_ids`` are episode timestamps and the episodes are
not public, so nothing further is reachable from public data.

Exit 0 when every skill reaches at least one row; 1 otherwise (skills without
``source_ids`` are listed as ``no-lineage`` — the one-time backfill of
pre-2026-10-24 skills is a Mac-side step). ``audit_content_hash`` is not part
of the check: it is not recomputable from the file (see DATACARD).

Usage:
    python3 -I scripts/skill_provenance_reach.py [DATA_DIR]
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

_FM_SOURCE_IDS = re.compile(r"^source_ids:\s*\[(.*?)\]\s*$", re.MULTILINE)
_FM_GENERATED_BY = re.compile(r"^generated_by:\s*(\S.*?)\s*$", re.MULTILINE)


def pattern_id(row: dict) -> str:
    raw = f"{row.get('distilled', '')}|{row.get('pattern', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def _frontmatter(text: str) -> str:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return ""
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "\n".join(lines[: i + 1])
    return ""


def reach(data_dir: Path) -> tuple[list[dict], int]:
    """``(per-skill result rows, exit code)``."""
    rows = json.loads((data_dir / "knowledge.json").read_text(encoding="utf-8"))
    by_id = {pattern_id(r): r for r in rows}
    results = []
    for path in sorted((data_dir / "skills").glob("*.md")):
        fm = _frontmatter(path.read_text(encoding="utf-8"))
        m = _FM_SOURCE_IDS.search(fm)
        ids = [i.strip() for i in m.group(1).split(",") if i.strip()] if m else []
        hit = [i for i in ids if i in by_id]
        g = _FM_GENERATED_BY.search(fm)
        status = "no-lineage" if not ids else ("reached" if hit else "unreached")
        results.append(
            {
                "skill": path.name,
                "status": status,
                "ids": len(ids),
                "reached": len(hit),
                "generated_by": bool(g),
            }
        )
    ok = all(r["status"] == "reached" for r in results) and bool(results)
    return results, 0 if ok else 1


def main(argv: list[str]) -> int:
    data_dir = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    if not (data_dir / "knowledge.json").is_file() or not (data_dir / "skills").is_dir():
        print(f"Error: {data_dir} has no knowledge.json and skills/", file=sys.stderr)
        return 2
    results, code = reach(data_dir)
    total = len(results)
    for status in ("reached", "unreached", "no-lineage"):
        print(f"{status}: {sum(1 for r in results if r['status'] == status)}/{total}")
    print(f"generated_by present: {sum(1 for r in results if r['generated_by'])}/{total}")
    shown = 0
    for r in results:
        if r["status"] != "reached":
            if shown < 10:
                print(f"  {r['status']}: {r['skill']}")
            shown += 1
    if shown > 10:
        print(f"  ... and {shown - 10} more")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
