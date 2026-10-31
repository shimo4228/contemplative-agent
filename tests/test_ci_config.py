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

import os
import re
import subprocess
import sys
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


def test_every_pytest_the_workflow_runs_has_plugin_autoload_off():
    """P1-08.6: CI loads only the plugins `-p` names, in every job that runs pytest.

    The verify job reaches pytest through verify.sh (pinned above); a job that
    calls pytest itself carries the switch in its own env.
    """
    job_env_switch = re.compile(r'^    env:\n      PYTEST_DISABLE_PLUGIN_AUTOLOAD: "1"$', re.M)
    checked = []
    for name, block in _jobs().items():
        runs_pytest = re.search(r"^\s+(?:run: )?uv run .*\bpytest\b", block, re.MULTILINE)
        if not runs_pytest or "./.claude/verify.sh" in block:
            continue
        checked.append(name)
        assert job_env_switch.search(block), name
    assert "packaging" in checked or "packaging" not in _jobs()


def test_the_launch_line_loads_only_the_plugins_it_names():
    """P1-08.6: under the verify launch line the header lists {cov, randomly} only.

    A pytest11 entry point a dependency ships (hypothesis, platformdirs, ...) must
    not join the run; hypothesis needs no plugin (conftest loads its profile).
    """
    env = {**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "pytest_cov", "-p", "no:cacheprovider"]
        + ["--co", "tests/test_stats.py"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    header = next(line for line in proc.stdout.splitlines() if line.startswith("plugins:"))
    names = {item.strip().rsplit("-", 1)[0] for item in header.removeprefix("plugins:").split(",")}
    assert names == {"cov", "randomly"}, header
