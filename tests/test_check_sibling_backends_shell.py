"""scripts/check-sibling-backends.sh output contract (P1-11.13).

Text-level checks plus one run against a tree with no siblings checked out
(every entry must report ``absent``; the run must not fail or go silent).
The conformance run itself needs the sibling checkouts and is the release gate.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-sibling-backends.sh"


def test_success_line_carries_sha_main_level_kit() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for field in ("sha=%s", "main=%s", "level=%s", "kit=%s", "state=%s"):
        assert field in text
    assert "git -C" in text and "describe --tags" in text


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
def test_absent_siblings_are_reported_not_silent(tmp_path: Path) -> None:
    main = tmp_path / "main"
    (main / "scripts").mkdir(parents=True)
    script = main / "scripts" / SCRIPT.name
    shutil.copy(SCRIPT, script)
    result = subprocess.run(["bash", str(script)], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert result.stdout.count("[sibling] absent") == 3
    assert "3 absent" in result.stdout


def test_every_target_declares_a_state_and_frozen_failures_do_not_block() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    targets = [ln for ln in text.splitlines() if re.match(r'\s+"(frozen|active|[a-z-]+)\|', ln)]
    assert len(targets) == 3
    for ln in targets:
        assert ln.strip().startswith(('"frozen|', '"active|'))
    assert "FROZEN, not a release blocker" in text
