"""The stage 7b / 7d readings moved out of weekly-pipeline.sh (P2-04.13 PR-A).

They run on any OS: an empty MOLTBOOK_HOME must yield valid JSON on stdout
with the keys the chain's follow-up check reads (`strict`, `joined_publishes`).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"


def _run(script: str, home: Path, *extra: str) -> dict:
    out = subprocess.run(
        [sys.executable, str(SCRIPTS / script), "--home", str(home),
         "--end-date", "2026-09-05", *extra],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def test_never_selected_reading_prints_json_with_strict(tmp_path):
    (tmp_path / "logs").mkdir()
    assert "strict" in _run("never_selected_reading.py", tmp_path)


def test_comment_outcomes_reading_prints_json_with_joined(tmp_path):
    (tmp_path / "logs").mkdir()
    assert "joined_publishes" in _run("comment_outcomes_reading.py", tmp_path)


def test_chain_calls_the_scripts_not_inline_python():
    chain = (SCRIPTS / "weekly-pipeline.sh").read_text()
    assert "scripts/never_selected_reading.py" in chain
    assert "scripts/comment_outcomes_reading.py" in chain
    assert "python -c '" not in chain
