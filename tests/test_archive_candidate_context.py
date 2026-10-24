"""P2-06.3: reply_rate / observed_publishes beside the archive candidates.

The pinned property is the one-way flow (ADR-0106 D6/D7): the reading is written
to a sibling file, the candidate file is never touched, and neither the
candidate producer nor ``adopt-staged`` knows the reading exists.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "archive_candidate_context.py"

OUTCOMES = {
    "observed_publishes": 96,
    "unobserved_publishes": 189,
    "skills": [
        {"skill": "alpha-20260601", "injected_comments": 12, "reply_rate": 0.25},
        {"skill": "beta-20260602.md", "injected_comments": 4, "reply_rate": 0.0},
    ],
}


def _run(tmp: Path, candidates: str, outcomes: object | None = OUTCOMES):
    cand = tmp / "weekly-2026-10-24-archive-candidates.txt"
    cand.write_text(candidates, encoding="utf-8")
    out = tmp / "weekly-2026-10-24-archive-candidates.context.txt"
    oc = tmp / "comment-outcomes.json"
    if outcomes is not None:
        oc.write_text(json.dumps(outcomes), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--candidates", str(cand),
         "--comment-outcomes", str(oc), "--out", str(out)],
        capture_output=True, text=True,
    )
    return proc, cand, out


def test_rows_are_beside_each_candidate_and_candidate_file_is_untouched(tmp_path):
    text = "alpha-20260601.md\nbeta-20260602.md\ngamma-20260603.md\n"
    before = hashlib.sha256(text.encode()).hexdigest()
    proc, cand, out = _run(tmp_path, text)
    assert proc.returncode == 0, proc.stderr
    assert hashlib.sha256(cand.read_bytes()).hexdigest() == before
    rows = [ln for ln in out.read_text().splitlines() if not ln.startswith("#")]
    assert rows == [
        "alpha-20260601.md\treply_rate=0.250\tinjected_comments=12\tobserved_publishes=96",
        "beta-20260602.md\treply_rate=0.000\tinjected_comments=4\tobserved_publishes=96",
        "gamma-20260603.md\treply_rate=-\tinjected_comments=0\tobserved_publishes=96",
    ]


def test_missing_outcomes_abstains_and_writes_nothing(tmp_path):
    proc, _, out = _run(tmp_path, "alpha-20260601.md\n", outcomes=None)
    assert proc.returncode == 2
    assert "reason=ARCHIVE_CONTEXT_NO_OUTCOMES" in proc.stderr
    assert not out.exists()


def test_empty_candidate_file_writes_no_context(tmp_path):
    proc, _, out = _run(tmp_path, "")
    assert proc.returncode == 0
    assert not out.exists()


def test_the_value_cannot_reach_the_archive_decision():
    """No decision-side module reads the comment outcomes (ADR-0106 D7)."""
    decision_side = [
        REPO / "scripts" / "confusion_pair_reading.py",
        REPO / "src" / "contemplative_agent" / "cli" / "adopt.py",
        REPO / "src" / "contemplative_agent" / "cli" / "remove_skill.py",
        REPO / "src" / "contemplative_agent" / "core" / "skill_confusion.py",
    ]
    pattern = re.compile(r"comment_outcomes|reply_rate|archive_candidate_context")
    for path in decision_side:
        if path.exists():
            assert not pattern.search(path.read_text(encoding="utf-8")), path.name


def test_context_file_is_not_a_names_file():
    """The reading lives in its own file: the candidate file's grammar is
    untouched, so ``--archive-names`` never meets a column it cannot parse."""
    from contemplative_agent.cli.adopt import _read_archive_names_file  # noqa: PLC0415

    assert callable(_read_archive_names_file)
    assert "reply_rate" not in (REPO / "scripts" / "confusion_pair_reading.py").read_text()
