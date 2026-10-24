"""scripts/pipeline_watchdog.sh — the Saturday anchor and the alert dedup (P1-08.3).

The watchdog is the only independent device that notices a dead weekly chain
(2026-07-25: a 0-byte report), and its own date arithmetic was unchecked.
The clock is a PATH-front ``date`` stub (``FAKE_NOW``), so the boundaries are
exact and the tests run on any host; ``osascript`` is an absolute path, so a
rewritten copy of the script points it at a recording stub.

Anchor rule (``anchor_sat``): before a job's deadline hour on the Saturday
itself the governing Saturday is the previous one. The report deadline is
12:00 and the findings deadline 13:00.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests._shell_harness import (
    REPO_ROOT,
    ShellEnv,
    install_bsd_stubs,
    rewrite_script,
    run_script,
    sh_stub,
)

SCRIPT = REPO_ROOT / "scripts" / "pipeline_watchdog.sh"
BASH = "/bin/bash"


def _setup(tmp_path: Path, now: str, *, notify: bool = False):
    shell = ShellEnv.create(tmp_path)
    install_bsd_stubs(shell)
    agents = shell.home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.moltbook.weekly-pipeline.plist").write_text("<plist/>\n", encoding="utf-8")
    moltbook = shell.home / ".config" / "moltbook"
    (moltbook / "logs").mkdir(parents=True)
    script = SCRIPT
    calls = tmp_path / "osascript.calls"
    if notify:
        osa = sh_stub(shell.stub_dir, "osascript", f'echo "$@" >> "{calls}"')
        script = rewrite_script(SCRIPT, tmp_path / "watchdog.sh", {"/usr/bin/osascript": str(osa)})
    env = shell.env({"FAKE_NOW": now, "MOLTBOOK_HOME": str(moltbook)})
    return shell, moltbook, script, env, calls


def _status(moltbook: Path) -> str:
    return (moltbook / "reports" / "PIPELINE-STATUS.md").read_text(encoding="utf-8")


def _seed(moltbook: Path, *jobs: str) -> None:
    status = moltbook / "reports" / "PIPELINE-STATUS.md"
    status.parent.mkdir(parents=True, exist_ok=True)
    status.write_text("".join(f"- ❌ {job} — seeded\n" for job in jobs), encoding="utf-8")


# 2026-10-24 is a Saturday; the previous one is 10-17. Artifacts are named
# for the Friday before the Saturday (weekly-<Fri>.md).
@pytest.mark.parametrize(
    ("now", "report_end", "findings_end"),
    [
        ("2026-10-24 11:59", "2026-10-16", "2026-10-16"),  # both before their deadline
        ("2026-10-24 12:00", "2026-10-23", "2026-10-16"),  # report deadline passed
        ("2026-10-24 12:59", "2026-10-23", "2026-10-16"),  # findings still pending
        ("2026-10-24 13:00", "2026-10-23", "2026-10-23"),  # both governed by today
    ],
)
def test_the_saturday_anchor_flips_at_each_deadline_hour(tmp_path, now, report_end, findings_end):
    _, moltbook, script, env, _ = _setup(tmp_path, now)
    _seed(moltbook, "weekly-findings", "weekly-report")  # keep the alert path quiet

    proc = run_script([BASH, str(script)], env)

    assert proc.returncode == 2, proc.stderr
    status = _status(moltbook)
    assert f"weekly-{report_end}.md not found" in status
    assert f"weekly-{findings_end}-findings.md not found" in status


def test_an_unchanged_fail_set_posts_no_notification(tmp_path):
    _, moltbook, script, env, calls = _setup(tmp_path, "2026-10-24 13:00", notify=True)
    _seed(moltbook, "weekly-report", "weekly-findings")

    proc = run_script([BASH, str(script)], env)

    assert proc.returncode == 2, proc.stderr
    assert not calls.exists(), calls.read_text()


def test_a_changed_fail_set_posts_one_notification_naming_the_jobs(tmp_path):
    _, moltbook, script, env, calls = _setup(tmp_path, "2026-10-24 13:00", notify=True)
    _seed(moltbook, "weekly-report")  # the findings failure is new

    proc = run_script([BASH, str(script)], env)

    assert proc.returncode == 2, proc.stderr
    lines = calls.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert "failing: weekly-findings weekly-report" in lines[0]
