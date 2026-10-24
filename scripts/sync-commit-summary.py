#!/usr/bin/env python3
"""One deterministic line summarising what a data-repo sync carries (P0-06.4).

Printed by sync-research-data.sh as the second line of the commit message so
`git log --format=%b` gives the repo's size over time:

    patterns=10985 skills=53 rules=2 reports=217 snapshots=100 framework=v2.13.0

stdlib only (the script runs under whatever `python3` launchd finds; macOS
system Python can be older than 3.11, so no tomllib). The framework version is
read from the checkout's pyproject.toml, the same file the installed metadata
comes from.

Usage: sync-commit-summary.py DATA_REPO [PYPROJECT]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _count_files(directory: Path, pattern: str = "*") -> int:
    if not directory.is_dir():
        return 0
    return sum(
        1
        for p in directory.rglob(pattern)
        if p.is_file() and ".private" not in p.relative_to(directory).parts
    )


def _patterns(repo: Path) -> int:
    path = repo / "knowledge.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return len(data) if isinstance(data, list) else 0


def _framework(pyproject: Path | None) -> str:
    if pyproject is not None:
        try:
            m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
        except OSError:
            m = None
        if m:
            return f"v{m.group(1)}"
    return "unknown"


def summary(repo: Path, pyproject: Path | None = None) -> str:
    snapshots = repo / "snapshots"
    n_snapshots = sum(1 for p in snapshots.iterdir() if p.is_dir()) if snapshots.is_dir() else 0
    return (
        f"patterns={_patterns(repo)} skills={_count_files(repo / 'skills', '*.md')}"
        f" rules={_count_files(repo / 'rules', '*.md')} reports={_count_files(repo / 'reports')}"
        f" snapshots={n_snapshots} framework={_framework(pyproject)}"
    )


def main(argv: list[str]) -> int:
    if not 2 <= len(argv) <= 3:
        print(__doc__, file=sys.stderr)
        return 2
    print(summary(Path(argv[1]), Path(argv[2]) if len(argv) == 3 else None))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
