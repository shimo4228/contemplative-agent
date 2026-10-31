"""The stage 7b reading moved out of weekly-pipeline.sh (P2-04.13 PR-A).

It runs on any OS: an empty MOLTBOOK_HOME must yield valid JSON on stdout
with the key the chain's follow-up check reads (`strict`).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(script: str, home: Path, *extra: str) -> dict:
    out = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / script),
            "--home",
            str(home),
            "--end-date",
            "2026-09-05",
            *extra,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def test_never_selected_reading_prints_json_with_strict(tmp_path):
    (tmp_path / "logs").mkdir()
    assert "strict" in _run("never_selected_reading.py", tmp_path)


def test_chain_calls_the_scripts_not_inline_python():
    chain = (SCRIPTS / "weekly-pipeline.sh").read_text()
    assert "scripts/never_selected_reading.py" in chain
    assert "python -c '" not in chain


def test_stage_7d_stays_removed():
    """ADR-0106 note 2026-10-31 (D-P1-04-2 = A): the comment-outcome reading
    left the chain with its tail. Windows are read directly when needed."""
    chain = (SCRIPTS / "weekly-pipeline.sh").read_text()
    for gone in ("comment_outcomes_reading.py", "archive_candidate_context.py", "comment-outcomes"):
        assert gone not in chain
