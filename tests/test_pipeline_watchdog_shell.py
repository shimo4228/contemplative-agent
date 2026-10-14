"""scripts/pipeline_watchdog.sh — what its status file says (RFC-0051).

``reports/PIPELINE-STATUS.md`` sits under ``reports/``, which the public data
sync publishes, so no line of it may carry the machine's home path: paths are
written relative to ``MOLTBOOK_HOME``.

The sync row: the daily ``com.moltbook.sync-data`` job is best-effort — a
failure, including the RFC-0051 home-path gate refusing to commit, is a stderr
warning and exit 0 (``cli/session_cmds.py::_run_sync``). The watchdog is the
only place a stopped sync shows, and it reads the data repo's reflog file
rather than calling ``git`` (the script's HARD CONSTRAINT).

Each run gets a throwaway ``HOME`` holding only the plists a case installs, so
every other job reads SKIP. The script posts a Notification Center alert when
its FAIL set changes from the previous status file; each case seeds that file
with the FAIL set it expects, so a passing run posts nothing.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "pipeline_watchdog.sh"
BASH = "/bin/bash"  # the 3.2 launchd resolves through PATH=/usr/bin:/bin

pytestmark = pytest.mark.skipif(not Path("/usr/bin/osascript").exists(), reason="macOS only")


def _home(tmp_path: Path, *plists: str) -> Path:
    home = tmp_path / "Users" / "someuser"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    for label in plists:
        (agents / f"com.moltbook.{label}.plist").write_text("<plist/>\n", encoding="utf-8")
    (home / ".config" / "moltbook" / "logs").mkdir(parents=True)
    return home


def _status(home: Path) -> Path:
    return home / ".config" / "moltbook" / "reports" / "PIPELINE-STATUS.md"


def _seed_fails(home: Path, *jobs: str) -> None:
    """The previous run's FAIL set, so this run's alert dedup stays quiet."""
    status = _status(home)
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text("".join(f"- ❌ {job} — seeded\n" for job in jobs), encoding="utf-8")


def _reflog(home: Path, *entries: tuple[int, str]) -> None:
    git = home / "MyAI_Lab" / "contemplative-agent-data" / ".git" / "logs"
    git.mkdir(parents=True)
    zero, sha = "0" * 40, "a" * 40
    (git / "HEAD").write_text(
        "".join(
            f"{zero} {sha} Some One <someone@example.com> {epoch} +0900\t{message}\n"
            for epoch, message in entries
        ),
        encoding="utf-8",
    )


def _run(home: Path) -> tuple[int, str]:
    env = {
        "HOME": str(home),
        "MOLTBOOK_HOME": str(home / ".config" / "moltbook"),
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
    }
    proc = subprocess.run([BASH, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    return proc.returncode, _status(home).read_text(encoding="utf-8")


def _row(status: str, job: str) -> str:
    rows = [line for line in status.splitlines() if line.startswith("- ") and f" {job} — " in line]
    assert len(rows) == 1, status
    return rows[0]


class TestNoHomePath:
    def test_a_failing_status_names_its_logs_relative_to_the_store(self, tmp_path):
        # distill scheduled, its log absent: the "log missing" row and the
        # footer's Logs pointer are the two places a path is printed.
        home = _home(tmp_path, "distill")
        _seed_fails(home, "distill")
        code, status = _run(home)
        assert code == 2
        assert str(home) not in status
        assert _row(status, "distill").endswith("log missing: logs/distill-launchd.log")
        assert "Logs: `logs`" in status

    def test_a_log_tail_error_names_the_log_relative_to_the_store(self, tmp_path):
        home = _home(tmp_path, "backup")
        log = home / ".config" / "moltbook" / "logs" / "backup-launchd.log"
        log.write_text("Traceback (most recent call last):\n", encoding="utf-8")
        _seed_fails(home, "backup")
        code, status = _run(home)
        assert code == 2
        assert str(home) not in status
        assert _row(status, "backup").endswith("log tail shows errors: logs/backup-launchd.log")


class TestSyncRow:
    def test_a_sync_commit_today_is_ok(self, tmp_path):
        home = _home(tmp_path, "sync-data")
        _reflog(home, (int(time.time()) - 60, "commit: sync: 2026-10-15T20:30:06Z"))
        code, status = _run(home)
        assert code == 0, status
        assert "✅" in _row(status, "sync-data")

    def test_a_sync_that_stopped_committing_fails(self, tmp_path):
        # The latest sync is 3 days old; a later non-sync commit (a hand edit
        # of the README) must not stand in for it.
        now = int(time.time())
        home = _home(tmp_path, "sync-data")
        _reflog(
            home,
            (now - 3 * 86400, "commit: sync: 2026-10-12T20:30:06Z"),
            (now - 60, "commit: docs(readme): a hand edit"),
        )
        _seed_fails(home, "sync-data")
        code, status = _run(home)
        assert code == 2
        row = _row(status, "sync-data")
        assert "❌" in row and "no sync commit since" in row
        assert str(home) not in status

    def test_a_data_repo_without_a_reflog_fails(self, tmp_path):
        home = _home(tmp_path, "sync-data")
        _seed_fails(home, "sync-data")
        code, status = _run(home)
        assert code == 2
        assert "❌" in _row(status, "sync-data")
        assert str(home) not in status

    def test_an_unscheduled_sync_is_skipped(self, tmp_path):
        home = _home(tmp_path)
        code, status = _run(home)
        assert code == 0
        assert "➖" in _row(status, "sync-data")
