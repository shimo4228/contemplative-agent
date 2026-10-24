"""Every unattended filing names the run that filed it (P2-03.2).

`origin: gate` entries come from the weekly chain; `filed_by: weekly-<end-date>[-<HHMMSS>]`
in the public frontmatter is what lets a clone without the private claims log
say which week an entry came from.
"""

from __future__ import annotations

import re
from pathlib import Path

RFCS = Path(__file__).resolve().parent.parent / "rfcs"


def _frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), path.name
    return text.split("\n---\n", 1)[0]


def test_every_gate_origin_rfc_carries_filed_by():
    gate_entries = [
        p
        for p in sorted(RFCS.glob("[0-9][0-9][0-9][0-9]-*.md"))
        if "\norigin: gate" in _frontmatter(p)
    ]
    assert gate_entries, "no origin: gate entries found — the check is vacuous"
    missing = []
    for path in gate_entries:
        m = re.search(
            r"^filed_by: (weekly-\d{4}-\d{2}-\d{2}(?:-\d{6})?)\b", _frontmatter(path), re.M
        )
        if not m:
            missing.append(path.name)
    assert not missing, f"origin: gate entries without a filed_by: {missing}"
