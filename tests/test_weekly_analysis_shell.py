"""End-to-end guards for ``scripts/weekly-analysis.sh`` (the launchd job).

The script is the only piece of the weekly pipeline that no test executed, and
both defects it shipped in July were shell-level: a redirect that truncated the
report before ``claude`` ran (fixed 2026-07-25, ``9bb4615``), and an anomaly-sweep
state committed during collection so a failed run still spent the week's novelty
baseline (findings F1.2 — twice in a row).

The invariant pinned here: **a run that produces no report changes no state.**
It is demonstrated by injection — a ``claude`` stub that exits non-zero — because
the failure mode is invisible in a passing run.

macOS-only: the script uses BSD ``date -j``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="weekly-analysis.sh uses BSD `date -j`"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "weekly-analysis.sh"

END_DATE = "2026-07-24"
SEEDED_STATE = "7\t[warning] seeded signature\n"


def _make_home(tmp_path: Path) -> Path:
    """A minimal MOLTBOOK_HOME: one daily report, one log, a seeded state."""
    home = tmp_path / "moltbook"
    (home / "reports" / "comment-reports").mkdir(parents=True)
    (home / "reports" / "analysis").mkdir(parents=True)
    (home / "logs").mkdir(parents=True)

    (home / "reports" / "comment-reports" / f"comment-report-{END_DATE}.md").write_text(
        "# Comment report\n\n## Entry 1\n\nOutput: hello.\n", encoding="utf-8"
    )
    (home / "logs" / "agent.log").write_text(
        "[10:00:00] WARNING a fresh anomaly type\n[10:01:00] ERROR another fresh anomaly type\n",
        encoding="utf-8",
    )
    (home / "reports" / "analysis" / ".anomaly-sweep-state.tsv").write_text(
        SEEDED_STATE, encoding="utf-8"
    )
    return home


def _stub_claude(tmp_path: Path, *, exit_code: int, body: str = "") -> Path:
    """A fake ``claude`` on PATH. Consumes stdin so the writer never sees EPIPE."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    emit = ""
    if body:
        body_file = tmp_path / "stub-body.md"
        body_file.write_text(body, encoding="utf-8")
        emit = f'cat "{body_file}"\n'
    stub = bin_dir / "claude"
    stub.write_text(f"#!/bin/bash\ncat > /dev/null\n{emit}exit {exit_code}\n", encoding="utf-8")
    stub.chmod(0o755)
    return bin_dir


def _run(home: Path, bin_dir: Path, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["MOLTBOOK_HOME"] = str(home)
    # HOME drives DATA_REPO ($HOME/MyAI_Lab/contemplative-agent-data); point it
    # at the sandbox so the run cannot touch the real data repo.
    env["HOME"] = str(tmp_path / "fakehome")
    (tmp_path / "fakehome").mkdir(exist_ok=True)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    return subprocess.run(
        ["bash", str(SCRIPT), "--end-date", END_DATE],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO_ROOT,
        timeout=300,
    )


def _state(home: Path) -> Path:
    return home / "reports" / "analysis" / ".anomaly-sweep-state.tsv"


def _pending_files(home: Path) -> list[Path]:
    return list((home / "reports" / "analysis").glob(".anomaly-sweep-state.pending*"))


class TestFailedRunSpendsNothing:
    def test_generate_failure_leaves_sweep_state_byte_identical(self, tmp_path):
        home = _make_home(tmp_path)
        result = _run(home, _stub_claude(tmp_path, exit_code=1), tmp_path)

        assert result.returncode != 0, result.stdout
        assert _state(home).read_text(encoding="utf-8") == SEEDED_STATE
        assert not (home / "reports" / "analysis" / f"weekly-{END_DATE}.md").exists()
        assert _pending_files(home) == [], "pending snapshot leaked past the trap"

    def test_empty_output_also_leaves_state_untouched(self, tmp_path):
        """``claude`` exiting 0 with no output is the other failure shape."""
        home = _make_home(tmp_path)
        result = _run(home, _stub_claude(tmp_path, exit_code=0), tmp_path)

        assert result.returncode != 0, result.stdout
        assert _state(home).read_text(encoding="utf-8") == SEEDED_STATE
        assert _pending_files(home) == []


class TestSuccessfulRunCommits:
    def test_report_promoted_and_sweep_state_updated(self, tmp_path):
        home = _make_home(tmp_path)
        body = "# Weekly\n\nA. Volume\n\nB. Signals\n"
        result = _run(home, _stub_claude(tmp_path, exit_code=0, body=body), tmp_path)

        assert result.returncode == 0, result.stderr
        report = home / "reports" / "analysis" / f"weekly-{END_DATE}.md"
        assert report.read_text(encoding="utf-8") == body

        state = _state(home).read_text(encoding="utf-8")
        assert state != SEEDED_STATE, "sweep state was never committed"
        assert "a fresh anomaly type" in state
        assert _pending_files(home) == []

    def test_translation_failure_does_not_roll_back_the_state(self, tmp_path):
        """The .ja.md pass is best-effort and must not gate the baseline.

        The stub fails on its second invocation (the translation call), which is
        the shape of the real timeout / session-limit failures.
        """
        home = _make_home(tmp_path)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        marker = tmp_path / "call-count"
        stub = bin_dir / "claude"
        stub.write_text(
            "#!/bin/bash\n"
            "cat > /dev/null\n"
            f"echo x >> {marker}\n"
            f"if [[ $(wc -l < {marker}) -gt 1 ]]; then exit 1; fi\n"
            "printf '# Weekly\\n'\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)

        result = _run(home, bin_dir, tmp_path)

        assert result.returncode == 0, result.stderr
        assert not (home / "reports" / "analysis" / f"weekly-{END_DATE}.ja.md").exists()
        assert _state(home).read_text(encoding="utf-8") != SEEDED_STATE


class TestPreflight:
    def test_missing_claude_fails_before_the_collection_pass(self, tmp_path):
        """Regression pin for 2026-07-25: the binary moved to ~/.local/bin and
        launchd's PATH did not cover it. The preflight must fire before any
        collection work, and in particular before the sweep runs."""
        home = _make_home(tmp_path)
        bin_dir = tmp_path / "emptybin"
        bin_dir.mkdir()
        env = dict(os.environ)
        env["MOLTBOOK_HOME"] = str(home)
        env["HOME"] = str(tmp_path / "fakehome")
        (tmp_path / "fakehome").mkdir(exist_ok=True)
        # A PATH with the real coreutils but no `claude` anywhere.
        env["PATH"] = f"{bin_dir}:{Path(shutil.which('bash') or '/bin/bash').parent}:/usr/bin:/bin"

        result = subprocess.run(
            ["bash", str(SCRIPT), "--end-date", END_DATE],
            capture_output=True,
            text=True,
            env=env,
            cwd=REPO_ROOT,
            timeout=120,
        )

        assert result.returncode != 0
        assert "'claude' not found on PATH" in result.stderr
        assert _state(home).read_text(encoding="utf-8") == SEEDED_STATE
        assert _pending_files(home) == []
