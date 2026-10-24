"""verify.yml's literals, pinned and cross-checked with verify.md (P1-08.25 / .26 a).

Read as text, not YAML: ``yaml`` is not a dependency of this repo. The workflow
is small and regular enough that a line scan is exact, and a line scan fails
loudly (a changed shape reads as a missing literal) rather than parsing around
the change.

What is pinned: the job set, each job's ``runs-on`` / ``timeout-minutes`` / the
Python minor, that ``.claude/verify.sh`` is called once with no arguments, that
``.claude/verify.md``'s CI section states the same cells and timeouts, and that
``.python-version`` is the Python minor the verify cell uses.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests._shell_harness import REPO_ROOT

WORKFLOW = (REPO_ROOT / ".github" / "workflows" / "verify.yml").read_text(encoding="utf-8")
VERIFY_MD = (REPO_ROOT / ".claude" / "verify.md").read_text(encoding="utf-8")

# `packaging` is the floor job P0-06.3 adds; it may or may not be present yet.
REQUIRED_JOBS = {"verify", "secrets"}
ALLOWED_JOBS = REQUIRED_JOBS | {"packaging"}

EXPECTED = {
    "verify": {
        "runs-on": "${{ matrix.os }}",
        "timeout-minutes": "25",
        "cells": ["ubuntu-latest", "macos-latest"],
        "python": "3.13",
    },
    "secrets": {"runs-on": "ubuntu-latest", "timeout-minutes": "10"},
}


def _jobs() -> dict[str, str]:
    """Job name -> its block of text (two-space-indented keys under ``jobs:``)."""
    head, _, body = WORKFLOW.partition("\njobs:\n")
    assert body, "no top-level jobs: key"
    blocks: dict[str, str] = {}
    name = None
    for line in body.splitlines():
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            name = m.group(1)
            blocks[name] = ""
        elif name is not None:
            blocks[name] += line + "\n"
    return blocks


def _value(block: str, key: str) -> str:
    m = re.search(rf"^    {re.escape(key)}:\s*(.+?)\s*$", block, re.MULTILINE)
    assert m, f"{key} missing"
    return m.group(1).strip("\"'")


def test_the_job_set_is_fixed():
    names = set(_jobs())
    assert REQUIRED_JOBS <= names <= ALLOWED_JOBS, names


def test_each_jobs_runner_and_timeout_are_pinned():
    jobs = _jobs()
    for name, expected in EXPECTED.items():
        assert _value(jobs[name], "runs-on") == expected["runs-on"], name
        assert _value(jobs[name], "timeout-minutes") == expected["timeout-minutes"], name


def test_the_verify_job_runs_the_two_cells():
    block = _jobs()["verify"]
    os_line = re.search(r"^\s+os:\s*\[(.+)\]", block, re.MULTILINE)
    assert os_line, "no matrix os list"
    cells = [c.strip() for c in os_line.group(1).split(",")]
    assert cells == EXPECTED["verify"]["cells"]
    py_line = re.search(r"^\s+python:\s*\[(.+)\]", block, re.MULTILINE)
    assert py_line
    assert [c.strip(" \"'") for c in py_line.group(1).split(",")] == [EXPECTED["verify"]["python"]]


def test_verify_sh_is_called_once_with_no_arguments():
    calls = re.findall(r"\./\.claude/verify\.sh(.*)", WORKFLOW)
    assert [c.strip() for c in calls] == [""], calls


def test_no_tool_pin_lives_in_the_workflow():
    # shellcheck-py is in the dev group and markdownlint-cli2 in package.json (P1-08.24).
    assert "shellcheck-py" not in WORKFLOW
    assert "markdownlint-cli2@" not in WORKFLOW


def test_verify_md_ci_section_states_the_same_literals():
    section = VERIFY_MD.partition("\n## CI\n")[2]
    assert section, "verify.md has no CI section"
    for cell in EXPECTED["verify"]["cells"]:
        assert cell in section
    assert f"`timeout-minutes: {EXPECTED['verify']['timeout-minutes']}`" in section
    assert f"`timeout-minutes: {EXPECTED['secrets']['timeout-minutes']}`" in section
    assert "未配線" not in VERIFY_MD


def test_python_version_file_matches_the_verify_cell():
    pinned = (REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert pinned == EXPECTED["verify"]["python"]


def test_the_launch_line_in_verify_sh_matches_the_documented_floor():
    sh = Path(REPO_ROOT / ".claude" / "verify.sh").read_text(encoding="utf-8")
    assert "--cov-fail-under=94" in sh
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1" in sh
    assert "--cov-fail-under=94" in VERIFY_MD
