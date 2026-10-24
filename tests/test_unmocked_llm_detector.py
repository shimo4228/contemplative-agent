"""The un-mocked-LLM detector itself (P1-08.8).

A mini pytest session runs ``tests/_llm_sentinel.py`` as a plugin against a
throwaway test file, because the detector fails a test at teardown and that
cannot be asserted from inside the suite it guards.
"""

from __future__ import annotations

import re
import subprocess
import sys

import pytest
import tomllib

from tests._shell_harness import REPO_ROOT

_BODY = """
import socket
{mark}
def test_reaches_the_sentinel():
    s = socket.socket()
    s.settimeout(1)
    try:
        s.connect(("127.0.0.1", 1))
    except OSError:
        pass
    finally:
        s.close()
"""


def _run(tmp_path, mark: str) -> subprocess.CompletedProcess:
    (tmp_path / "test_probe.py").write_text("import pytest\n" + _BODY.format(mark=mark))
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "tests._llm_sentinel",
            "-p",
            "no:cacheprovider",
            "--rootdir",
            str(tmp_path),
            "-c",
            "/dev/null",
            "-q",
            str(tmp_path / "test_probe.py"),
        ],
        env={"PYTHONPATH": str(REPO_ROOT), "PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=120,
        cwd=tmp_path,
    )


def test_an_unmarked_connection_to_the_sentinel_is_red(tmp_path):
    proc = _run(tmp_path, "")
    assert proc.returncode != 0, proc.stdout
    assert "un-mocked LLM connection" in proc.stdout


def test_the_opt_in_marker_makes_it_green(tmp_path):
    proc = _run(tmp_path, "@pytest.mark.allow_unmocked_llm")
    assert proc.returncode == 0, proc.stdout


def test_every_declared_marker_is_used():
    config = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {line.split(":")[0] for line in config["tool"]["pytest"]["ini_options"]["markers"]}
    sources = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (REPO_ROOT / "tests").glob("test_*.py")
        if p.name != "test_unmocked_llm_detector.py"
    )
    unused = {m for m in declared if not re.search(rf"mark\.{m}\b", sources)}
    assert not unused, f"declared but never used: {sorted(unused)}"


@pytest.mark.parametrize("name", ["integration"])
def test_retired_markers_stay_retired(name):
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"{name}:' not in text
