"""Smoke for the one-shot count frozen in docs/evidence/adr-0060 (P1-04.7).

``scripts/distill_window_gap_count.py`` had no test or script consumer; it
stays because ``docs/REPRODUCING.md`` lists it as the way to recompute the
frozen distill-window-gap reading. One synthetic data dir checks that it still
runs and that only heading lines of a comment report are counted.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "distill_window_gap_count.py"


def _data_dir(root: Path) -> Path:
    rows = [
        {"provenance": {"source_episode_ids": ["2026-09-01T10:00:00+00:00"]}},
        # The same id twice counts once.
        {"provenance": {"source_episode_ids": ["2026-09-01T10:00:00+00:00"]}},
        {"provenance": {"source_episode_ids": ["2026-09-02T19:15:00+00:00"]}},
    ]
    (root / "knowledge.json").write_text(json.dumps(rows), encoding="utf-8")
    reports = root / "reports" / "comment-reports"
    reports.mkdir(parents=True)
    (reports / "comment-report-2026-09-02.md").write_text(
        "# Comment report\n"
        "### 1. [2026-09-02 09:00:00] COMMENT · with a · post\n"
        "Context: ### 9. [2026-09-02 23:00:00] quoted, not a heading\n"
        "### 2. [2026-09-02 21:05:00] REPLY · with b · post\n",
        encoding="utf-8",
    )
    return root


def test_counts_distilled_ids_and_report_headings_around_the_cutoff(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--data", str(_data_dir(tmp_path))],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "distilled episode ids (distinct): 2" in out
    assert "distilled with ts at/after 18:30Z: 1" in out
    assert "comment-report headings: 2; at/after 18:30Z: 1" in out
    assert "{'REPLY': 1}" in out
