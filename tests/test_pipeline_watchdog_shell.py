"""scripts/pipeline_watchdog.sh — what its status file says (RFC-0051).

``reports/PIPELINE-STATUS.md`` sits under ``reports/``, which the public data
sync publishes, so no line of it may carry the machine's home path: paths are
written relative to ``MOLTBOOK_HOME``.

The sync row: the daily ``com.moltbook.sync-data`` job exits nonzero on a
failure (P2-04.2), including the RFC-0051 home-path gate refusing to commit.
The watchdog is the independent check that a sync commit landed, and it reads
the data repo's reflog file rather than calling ``git`` (the script's HARD
CONSTRAINT).

Rows added by P2-04.4 / .10 / .15 (agent, moltbook, moltbook-7d, disk,
log-rotation, launchctl PID / exit status) and the status file's
``Next check by`` / ``Notified`` lines (P2-04.17) are below. macOS-only (BSD
``date -v`` / ``stat -f``): verified on the Mac, skipped on ubuntu.

Each run gets a throwaway ``HOME`` holding only the plists a case installs, so
every other job reads SKIP. The script posts a Notification Center alert when
its FAIL set changes from the previous status file; each case seeds that file
with the FAIL set it expects, so a passing run posts nothing.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import time
from datetime import datetime, timedelta, timezone
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


def _run(
    home: Path, extra_env: dict[str, str] | None = None, path_prefix: str = ""
) -> tuple[int, str]:
    env = {
        "HOME": str(home),
        "MOLTBOOK_HOME": str(home / ".config" / "moltbook"),
        "PATH": f"{path_prefix}/usr/bin:/bin:/usr/sbin:/sbin",
        **(extra_env or {}),
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


class TestLastHumanGateRow:
    """P2-01.6: the public status file shows when a human last ran the gate."""

    def _metrics(self, home: Path, *lines: str) -> None:
        log = home / ".config" / "moltbook" / "logs" / "pipeline-metrics.jsonl"
        log.write_text("".join(line + "\n" for line in lines), encoding="utf-8")

    def test_newest_gate_record_date_and_weeks_are_shown(self, tmp_path):
        home = _home(tmp_path)
        self._metrics(
            home,
            '{"ts": "2020-01-04T04:00:00+00:00", "event": "gate_record"}',
            '{"ts": "2020-01-11T04:00:00+00:00", "event": "gate_record"}',
            '{"ts": "2020-01-12T04:00:00+00:00", "event": "gate_item"}',
        )
        code, status = _run(home)
        assert code == 0
        row = _row(status, "last-human-gate")
        assert "last human gate: 2020-01-11 (" in row and "weeks ago)" in row
        assert row.startswith("- ➖")

    def test_no_gate_record_reads_none_and_does_not_fail(self, tmp_path):
        home = _home(tmp_path)
        code, status = _run(home)
        assert code == 0
        assert "last human gate: none recorded" in _row(status, "last-human-gate")


# --- P2-04.4 / .10 / .15 / .17 -------------------------------------------------

def _moltbook(home: Path) -> Path:
    return home / ".config" / "moltbook"


def _utc_day(back: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=back)).strftime("%Y-%m-%d")


def _agent_files(home: Path, *, calls: bool = True, report: bool = True, back: int = 0) -> None:
    day = _utc_day(back)
    if calls:
        (_moltbook(home) / "logs" / f"llm-calls-{day}.jsonl").write_text('{"ok": true}\n')
    if report:
        reports = _moltbook(home) / "reports" / "comment-reports"
        reports.mkdir(parents=True, exist_ok=True)
        (reports / f"comment-report-{day}.md").write_text("# report\n")


def _audit_rows(home: Path, *rows: tuple[int, object]) -> None:
    """(hours_ago, status) rows; status None is a transport failure."""
    lines = []
    for hours_ago, status in rows:
        ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat(timespec="seconds")
        lines.append(json.dumps({"ts": ts, "method": "GET", "endpoint": "GET /home", "status": status}))
    (_moltbook(home) / "logs" / "api-audit.jsonl").write_text("\n".join(lines) + "\n")


class TestAgentAndMoltbookRows:
    def test_a_day_with_calls_a_report_and_2xx_is_healthy(self, tmp_path):
        home = _home(tmp_path, "agent")
        _agent_files(home)
        _audit_rows(home, (1, 200), (2, 429))
        code, status = _run(home)
        assert code == 0, status
        assert "✅" in _row(status, "agent")
        assert "✅" in _row(status, "moltbook")
        assert "✅" in _row(status, "moltbook-7d")

    def test_no_llm_calls_today_fails_the_agent_row(self, tmp_path):
        home = _home(tmp_path, "agent")
        _agent_files(home, calls=False, report=False, back=3)  # a report 3 days ago
        _seed_fails(home, "agent")
        code, status = _run(home)
        assert code == 2
        assert "❌" in _row(status, "agent") and "no LLM calls" in _row(status, "agent")
        assert str(home) not in status

    def test_llm_calls_without_a_comment_report_fails_the_agent_row(self, tmp_path):
        home = _home(tmp_path, "agent")
        _agent_files(home, report=False)
        _seed_fails(home, "agent", "moltbook-7d")
        code, status = _run(home)
        assert code == 2
        assert "no fresh comment report" in _row(status, "agent")

    def test_24h_of_calls_with_no_2xx_fails_the_moltbook_row(self, tmp_path):
        home = _home(tmp_path, "agent")
        _agent_files(home)
        _audit_rows(home, (1, 500), (2, None), (3, 302))
        _seed_fails(home, "moltbook")
        code, status = _run(home)
        row = _row(status, "moltbook")
        assert code == 2 and "❌" in row and "ERROR:" in row

    def test_rows_older_than_24h_do_not_count(self, tmp_path):
        home = _home(tmp_path, "agent")
        _agent_files(home)
        _audit_rows(home, (48, 500), (50, None))
        code, status = _run(home)
        assert code == 0, status
        assert "✅" in _row(status, "moltbook")

    def test_seven_days_without_a_comment_report_fails(self, tmp_path):
        home = _home(tmp_path, "agent")
        _agent_files(home, report=False)
        _seed_fails(home, "agent", "moltbook-7d")
        _code, status = _run(home)
        assert "❌" in _row(status, "moltbook-7d")

    def test_a_report_three_days_old_keeps_the_seven_day_row_green(self, tmp_path):
        home = _home(tmp_path, "agent")
        _agent_files(home, calls=False, back=3)
        _seed_fails(home, "agent")
        _code, status = _run(home)
        assert "✅" in _row(status, "moltbook-7d")


def _launchctl_stub(tmp_path: Path, body: str) -> str:
    bin_dir = tmp_path / "stubbin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "launchctl"
    stub.write_text(f"#!/bin/bash\ncat <<'EOF'\n{body}\nEOF\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    return f"{bin_dir}:"


class TestLaunchctlRows:
    def _distill_home(self, tmp_path: Path) -> Path:
        home = _home(tmp_path, "distill")
        log = _moltbook(home) / "logs" / "distill-launchd.log"
        log.write_text("done\n")
        return home

    def test_a_job_still_holding_a_pid_is_not_healthy(self, tmp_path):
        home = self._distill_home(tmp_path)
        _seed_fails(home, "distill")
        prefix = _launchctl_stub(tmp_path, '{\n\t"PID" = 4242;\n\t"LastExitStatus" = 0;\n};')
        code, status = _run(home, path_prefix=prefix)
        assert code == 2
        assert "still running" in _row(status, "distill")

    def test_a_nonzero_last_exit_status_fails_even_with_a_clean_log(self, tmp_path):
        home = self._distill_home(tmp_path)
        _seed_fails(home, "distill")
        prefix = _launchctl_stub(tmp_path, '{\n\t"LastExitStatus" = 512;\n};')
        code, status = _run(home, path_prefix=prefix)
        assert code == 2
        assert "last exit 512" in _row(status, "distill")

    def test_exit_zero_and_no_pid_is_healthy(self, tmp_path):
        home = self._distill_home(tmp_path)
        prefix = _launchctl_stub(tmp_path, '{\n\t"LastExitStatus" = 0;\n};')
        code, status = _run(home, path_prefix=prefix)
        assert code == 0, status
        assert "✅" in _row(status, "distill")


class TestDiskAndRotationRows:
    def test_free_space_below_the_floor_fails(self, tmp_path):
        home = _home(tmp_path)
        _seed_fails(home, "disk")
        code, status = _run(home, {"WATCHDOG_MIN_FREE_KB": str(10**12)})
        assert code == 2 and "❌" in _row(status, "disk")
        assert str(home) not in status

    def test_free_space_above_the_floor_is_ok(self, tmp_path):
        home = _home(tmp_path)
        code, status = _run(home, {"WATCHDOG_MIN_FREE_KB": "1"})
        assert code == 0, status
        assert "✅" in _row(status, "disk")

    def test_rotation_skipped_two_weeks_fails(self, tmp_path):
        home = _home(tmp_path, "backup")
        logs = _moltbook(home) / "logs"
        (logs / "backup-launchd.log").write_text("ok\n")
        gz = logs / "agent-launchd.log.1.gz"
        gz.write_bytes(b"x")
        old = time.time() - 20 * 86400
        os.utime(gz, (old, old))
        _seed_fails(home, "log-rotation")
        code, status = _run(home)
        assert code == 2 and "❌" in _row(status, "log-rotation")

    def test_a_recent_rotation_is_ok(self, tmp_path):
        home = _home(tmp_path, "backup")
        logs = _moltbook(home) / "logs"
        (logs / "backup-launchd.log").write_text("ok\n")
        (logs / "agent-launchd.log.1.gz").write_bytes(b"x")
        code, status = _run(home)
        assert code == 0, status
        assert "✅" in _row(status, "log-rotation")


class TestStatusFileFreshnessLines:
    def test_the_status_names_its_next_check_and_the_notification_attempt(self, tmp_path):
        home = _home(tmp_path)
        _code, status = _run(home)
        assert any(line.startswith("Next check by: ") for line in status.splitlines())
        assert "Notified: none" in status

    def test_a_status_that_cannot_be_written_is_an_error(self, tmp_path):
        home = _home(tmp_path)
        _seed_fails(home)
        reports = _status(home).parent
        reports.chmod(0o500)  # the temp file cannot be created, so the final mv fails
        try:
            proc = subprocess.run(
                [BASH, str(SCRIPT)],
                env={
                    "HOME": str(home),
                    "MOLTBOOK_HOME": str(_moltbook(home)),
                    "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                },
                capture_output=True, text=True, timeout=60,
            )
        finally:
            reports.chmod(0o700)
        assert proc.returncode == 3
        assert "mv failed" in proc.stderr
