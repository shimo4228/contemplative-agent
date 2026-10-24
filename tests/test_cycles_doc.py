"""docs/CYCLES.md job table vs config/launchd/ (P1-09.5).

The cycle map lists scheduled jobs by launchd label. A label that has no
template in ``config/launchd/`` (or a template the map forgot) is exactly the
drift that left ``com.moltbook.sync-data`` in the table for two months.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_LABEL = re.compile(r"com\.moltbook\.[a-z][a-z-]*[a-z]")
# Labels installed by hand, without a template. Empty since ADR-0114 brought
# com.moltbook.sync-data (hand-installed per ADR-0010's note, RFC-0051) under
# install-schedule --sync-data.
_HAND_INSTALLED: set[str] = set()


@pytest.mark.unit
def test_cycles_labels_match_launchd_templates() -> None:
    templates = {
        p.name.removesuffix(".plist") for p in (ROOT / "config" / "launchd").glob("*.plist")
    }
    text = (ROOT / "docs" / "CYCLES.md").read_text(encoding="utf-8")
    named = set(_LABEL.findall(text)) - _HAND_INSTALLED
    assert named == templates, (
        f"docs/CYCLES.md labels vs config/launchd/: missing {sorted(templates - named)}, "
        f"unexpected {sorted(named - templates)}"
    )


@pytest.mark.unit
def test_sync_data_runner_is_stated_the_same_way() -> None:
    cycles = (ROOT / "docs" / "CYCLES.md").read_text(encoding="utf-8")
    adr = (ROOT / "docs" / "adr" / "0010-research-data-sync.md").read_text(encoding="utf-8")
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for name, text in (("CYCLES.md", cycles), ("ADR-0010", adr), ("README.md", readme)):
        assert "com.moltbook.sync-data" in text, name
        assert "install-schedule --sync-data" in text, name
