"""docs/research/LOG.md indexes the evidence by question (P3-02.4)."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LOG = (REPO_ROOT / "docs" / "research" / "LOG.md").read_text(encoding="utf-8")


def test_every_evidence_directory_has_a_row():
    missing = [
        d.name
        for d in sorted((REPO_ROOT / "docs" / "evidence").iterdir())
        if d.is_dir() and f"docs/evidence/{d.name}/" not in LOG
    ]
    assert missing == []


def test_the_four_known_nulls_are_rows_with_a_null_result_and_a_dropped_or_withdrawn_status():
    rows = [ln for ln in LOG.splitlines() if ln.startswith("| ")]
    for needle in (
        "dialogue two-arm",
        "Converse IPD",
        "RFC-0002 axiom-removal A/B",
        "T-GAP1 mode recount",
    ):
        row = next((r for r in rows if needle in r), None)
        assert row is not None, needle
        assert "null" in row and re.search(r"dropped|withdrawn", row), needle


def test_boundary_ids_in_the_log_exist_in_the_regime_table():
    import json

    ids = {
        r["id"]
        for r in json.loads(
            (REPO_ROOT / "docs" / "evidence" / "regimes" / "regimes.json").read_text(
                encoding="utf-8"
            )
        )["regimes"]
    }
    used = set(re.findall(r"\bR\d{2}\b", LOG))
    assert used <= ids
