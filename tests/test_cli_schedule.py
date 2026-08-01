"""launchd schedule CLI tests (cli/schedule.py).

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import re
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli import main
from contemplative_agent.cli.schedule import (
    _build_calendar_intervals,
    _do_install_backup_schedule,
    _do_install_distill_schedule,
    _do_install_schedule,
    _do_install_submolt_scan_schedule,
    _do_install_weekly_analysis_schedule,
    _do_uninstall_schedule,
    _remove_stale_schedule_jobs,
)


class TestBuildCalendarIntervals:
    def test_every_6_hours(self):
        result = _build_calendar_intervals(6)
        assert "<integer>0</integer>" in result
        assert "<integer>6</integer>" in result
        assert "<integer>12</integer>" in result
        assert "<integer>18</integer>" in result
        assert result.count("<dict>") == 4

    def test_every_12_hours(self):
        result = _build_calendar_intervals(12)
        assert result.count("<dict>") == 2

    def test_every_24_hours(self):
        result = _build_calendar_intervals(24)
        assert result.count("<dict>") == 1


class TestInstallSchedule:
    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_creates_plist(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.agent.plist"

        with (
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_PATH", plist_path),
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_DIR", tmp_path),
        ):
            _do_install_schedule(interval=6, session=120)

        assert plist_path.exists()
        content = plist_path.read_text()
        assert "<string>120</string>" in content
        # The agent plist invokes the contemplative-agent binary directly via
        # caffeinate (commit b888840 / ADR-0067).
        assert "/contemplative-agent" in content
        assert "{{VENV_BIN}}/contemplative-agent" not in content
        # Verify all placeholders were replaced
        for placeholder in (
            "{{VENV_BIN}}",
            "{{PROJECT_ROOT}}",
            "{{SESSION_MINUTES}}",
            "{{LOG_PATH}}",
            "{{CALENDAR_INTERVALS}}",
        ):
            assert placeholder not in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_unloads_existing(self, mock_run, tmp_path):
        """If plist already exists, unload before overwriting."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.agent.plist"
        plist_path.write_text("old content")

        with (
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_PATH", plist_path),
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_DIR", tmp_path),
        ):
            _do_install_schedule(interval=6, session=120)

        # First call: unload, second call: load
        assert mock_run.call_count == 2
        assert "unload" in mock_run.call_args_list[0][0][0]
        assert "load" in mock_run.call_args_list[1][0][0]


@pytest.fixture
def plist_sandbox(tmp_path, monkeypatch):
    """Redirect EVERY ``LAUNCHD_*_PLIST_PATH`` constant into tmp_path.

    Discovery is dynamic so a newly added schedule plist can never fall
    through to the user's real ~/Library/LaunchAgents/. Hand-listing the
    paths per test caused two live-plist deletions during full-suite runs:
    the Apr 8 incident (weekly-analysis) and the Jul 9 incident (insight —
    ledger T-FLAKY1: the walker unloaded and deleted the freshly installed
    com.moltbook.insight.plist because the test patched only three paths).
    """
    import contemplative_agent.cli.schedule as schedule_mod

    paths = {}
    for attr in dir(schedule_mod):
        if attr.startswith("LAUNCHD_") and attr.endswith("_PLIST_PATH"):
            sandboxed = tmp_path / getattr(schedule_mod, attr).name
            monkeypatch.setattr(schedule_mod, attr, sandboxed)
            paths[attr] = sandboxed
    # Guard (ADR-0079 Phase 2): the constants moved from the old single-file
    # cli module into cli.schedule. If they ever move again, dir() discovery
    # here would silently find nothing and the uninstall tests below would
    # walk the user's REAL ~/Library/LaunchAgents/ — fail loudly instead.
    assert paths, "plist_sandbox discovered no LAUNCHD_*_PLIST_PATH constants — wrong module?"
    monkeypatch.setattr(schedule_mod, "LAUNCHD_PLIST_DIR", tmp_path)
    return paths


class TestUninstallSchedule:
    def test_uninstall_no_plist(self, plist_sandbox, capsys):
        _do_uninstall_schedule()
        assert "No schedule installed" in capsys.readouterr().out

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_uninstall_removes_plist(self, mock_run, plist_sandbox):
        plist_sandbox["LAUNCHD_PLIST_PATH"].write_text("dummy")

        _do_uninstall_schedule()

        assert not plist_sandbox["LAUNCHD_PLIST_PATH"].exists()
        mock_run.assert_called_once()

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_uninstall_walks_every_registered_plist(self, mock_run, plist_sandbox):
        """Regression pin for the Jul 9 incident (T-FLAKY1): the uninstall
        walker must cover every LAUNCHD_*_PLIST_PATH constant — a constant
        the walker misses would survive here."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        for path in plist_sandbox.values():
            path.write_text("dummy")

        _do_uninstall_schedule()

        for name, path in plist_sandbox.items():
            assert not path.exists(), f"{name} not removed by uninstall walker"


class TestInstallDistillSchedule:
    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_creates_distill_plist(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.distill.plist"

        with (
            patch("contemplative_agent.cli.schedule.LAUNCHD_DISTILL_PLIST_PATH", plist_path),
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_DIR", tmp_path),
        ):
            _do_install_distill_schedule(distill_hour=3)

        assert plist_path.exists()
        content = plist_path.read_text()
        assert "distill" in content
        # The distill plist invokes the contemplative-agent binary directly
        # (commit b888840 / ADR-0067).
        assert "/contemplative-agent" in content
        assert "{{VENV_BIN}}/contemplative-agent" not in content
        assert "<integer>3</integer>" in content
        # Audit M5: distill fires at :30, offset from the agent plist's
        # HH:00, so the two scheduled jobs never start in the same minute.
        assert "<integer>30</integer>" in content
        # Verify all placeholders were replaced
        for placeholder in ("{{VENV_BIN}}", "{{PROJECT_ROOT}}", "{{DISTILL_HOUR}}", "{{LOG_PATH}}"):
            assert placeholder not in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_distill_custom_hour(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.distill.plist"

        with (
            patch("contemplative_agent.cli.schedule.LAUNCHD_DISTILL_PLIST_PATH", plist_path),
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_DIR", tmp_path),
        ):
            _do_install_distill_schedule(distill_hour=5)

        content = plist_path.read_text()
        assert "<integer>5</integer>" in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_distill_unloads_existing(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.distill.plist"
        plist_path.write_text("old content")

        with (
            patch("contemplative_agent.cli.schedule.LAUNCHD_DISTILL_PLIST_PATH", plist_path),
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_DIR", tmp_path),
        ):
            _do_install_distill_schedule(distill_hour=3)

        assert mock_run.call_count == 2
        assert "unload" in mock_run.call_args_list[0][0][0]
        assert "load" in mock_run.call_args_list[1][0][0]


class TestInstallBackupSchedule:
    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_creates_backup_plist(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        _do_install_backup_schedule(weekday=1, hour=10)

        plist_path = plist_sandbox["LAUNCHD_BACKUP_PLIST_PATH"]
        assert plist_path.exists()
        content = plist_path.read_text()
        assert "backup-runtime.sh" in content
        assert "<integer>1</integer>" in content
        assert "<integer>10</integer>" in content
        # Verify all placeholders were replaced
        for placeholder in ("{{PROJECT_ROOT}}", "{{WEEKDAY}}", "{{HOUR}}", "{{LOG_PATH}}"):
            assert placeholder not in content


class TestInstallWeeklyAnalysisSchedule:
    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_creates_weekly_analysis_plist(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        _do_install_weekly_analysis_schedule(weekday=6, hour=9)

        content = plist_sandbox["LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH"].read_text()
        assert "weekly-analysis.sh" in content
        assert "<integer>6</integer>" in content
        assert "<integer>9</integer>" in content
        for placeholder in (
            "{{PROJECT_ROOT}}",
            "{{USER_LOCAL_BIN}}",
            "{{WEEKDAY}}",
            "{{HOUR}}",
            "{{LOG_PATH}}",
        ):
            assert placeholder not in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_weekly_analysis_path_reaches_claude(self, mock_run, plist_sandbox):
        """Regression pin for the 2026-07-25 incident: the template hardcoded
        ``/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin``. When Claude Code's
        native installer moved the binary to ~/.local/bin, the scheduled job
        died with ``claude: command not found`` and left a 0-byte weekly report
        that read as a successful run. The script's whole purpose is to shell
        out to ``claude``, so its PATH must cover that directory."""
        import re
        from pathlib import Path

        mock_run.return_value = MagicMock(returncode=0, stderr="")

        _do_install_weekly_analysis_schedule(weekday=6, hour=9)

        content = plist_sandbox["LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH"].read_text()
        match = re.search(r"<key>PATH</key>\s*<string>([^<]*)</string>", content)
        assert match, "weekly-analysis plist declares no PATH"
        path_entries = match.group(1).split(":")
        assert str(Path.home() / ".local" / "bin") in path_entries


class TestUninstallScheduleBoth:
    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_uninstall_removes_both_plists(self, mock_run, plist_sandbox):
        # Only session + distill exist; the walker skips the others,
        # keeping the mock_run.call_count expectation at 2.
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_sandbox["LAUNCHD_PLIST_PATH"].write_text("dummy")
        plist_sandbox["LAUNCHD_DISTILL_PLIST_PATH"].write_text("dummy")

        _do_uninstall_schedule()

        assert not plist_sandbox["LAUNCHD_PLIST_PATH"].exists()
        assert not plist_sandbox["LAUNCHD_DISTILL_PLIST_PATH"].exists()
        assert mock_run.call_count == 2

    def test_uninstall_no_plists(self, plist_sandbox, capsys):
        _do_uninstall_schedule()

        assert "No schedule installed" in capsys.readouterr().out


class TestInstallScheduleCommand:
    def test_invalid_interval_exits(self):
        with patch("sys.argv", ["contemplative-agent", "install-schedule", "--interval", "5"]):
            with pytest.raises(SystemExit):
                main()

    def test_invalid_session_exits(self):
        with patch("sys.argv", ["contemplative-agent", "install-schedule", "--session", "0"]):
            with pytest.raises(SystemExit):
                main()


class TestInstallScheduleValidationOrderM9:
    """Bug-audit 2026-07-06 M9: an invalid --weekly-analysis-* argument must
    be rejected BEFORE any launchd schedule is installed."""

    def test_invalid_weekly_day_installs_nothing(self):
        from contemplative_agent.cli.schedule import _handle_install_schedule

        args = argparse.Namespace(
            uninstall=False,
            interval=6,
            session=30,
            distill_hour=3,
            no_distill=False,
            weekly_analysis=True,
            weekly_analysis_day=9,  # invalid (>6)
            weekly_analysis_hour=8,
        )
        parser = argparse.ArgumentParser()
        with (
            patch("contemplative_agent.cli.schedule._do_install_schedule") as mock_session,
            patch("contemplative_agent.cli.schedule._do_install_distill_schedule") as mock_distill,
            patch(
                "contemplative_agent.cli.schedule._do_install_weekly_analysis_schedule"
            ) as mock_weekly,
        ):
            with pytest.raises(SystemExit):
                _handle_install_schedule(args, parser)
        mock_session.assert_not_called()
        mock_distill.assert_not_called()
        mock_weekly.assert_not_called()


class TestRemoveStaleScheduleJobs:
    """Round-2 R2-M1: install-schedule is declarative over the full schedule
    set — optional jobs from a previous install whose flag is off this run
    are removed instead of running forever on a stale schedule."""

    @staticmethod
    def _all_on(**overrides):
        flags = {
            "distill": True,
            "weekly_analysis": True,
            "weekly_insight": True,
            "weekly_backup": True,
        }
        flags.update(overrides)
        return flags

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_removes_distill_when_flag_off(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        distill = plist_sandbox["LAUNCHD_DISTILL_PLIST_PATH"]
        distill.write_text("dummy")
        _remove_stale_schedule_jobs(**self._all_on(distill=False))
        assert not distill.exists()
        mock_run.assert_called_once()  # one unload, for the distill plist

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_removes_weekly_when_flag_dropped(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        weekly = plist_sandbox["LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH"]
        weekly.write_text("dummy")
        _remove_stale_schedule_jobs(**self._all_on(weekly_analysis=False))
        assert not weekly.exists()

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_removes_insight_when_flag_dropped(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        insight = plist_sandbox["LAUNCHD_INSIGHT_PLIST_PATH"]
        insight.write_text("dummy")
        _remove_stale_schedule_jobs(**self._all_on(weekly_insight=False))
        assert not insight.exists()

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_removes_backup_when_flag_dropped(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        backup = plist_sandbox["LAUNCHD_BACKUP_PLIST_PATH"]
        backup.write_text("dummy")
        _remove_stale_schedule_jobs(**self._all_on(weekly_backup=False))
        assert not backup.exists()

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_keeps_jobs_whose_flag_is_on(self, mock_run, plist_sandbox):
        for attr in (
            "LAUNCHD_DISTILL_PLIST_PATH",
            "LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH",
            "LAUNCHD_INSIGHT_PLIST_PATH",
            "LAUNCHD_BACKUP_PLIST_PATH",
        ):
            plist_sandbox[attr].write_text("dummy")
        _remove_stale_schedule_jobs(**self._all_on())
        for attr in (
            "LAUNCHD_DISTILL_PLIST_PATH",
            "LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH",
            "LAUNCHD_INSIGHT_PLIST_PATH",
            "LAUNCHD_BACKUP_PLIST_PATH",
        ):
            assert plist_sandbox[attr].exists()
        mock_run.assert_not_called()


class TestInstallScheduleEnforceFlag:
    """ADR-0081 rollout: launchd does not inherit shell exports, so
    install-schedule must propagate MOLTBOOK_SKILL_SELECTION_ENFORCE from
    the installing shell into the session plist's EnvironmentVariables
    (codex review 2026-07-24 P1 — without this, production silently stays
    in shadow mode after the documented post-smoke rollout)."""

    def _install(self, tmp_path):
        plist_path = tmp_path / "com.moltbook.agent.plist"
        with (
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_PATH", plist_path),
            patch("contemplative_agent.cli.schedule.LAUNCHD_PLIST_DIR", tmp_path),
        ):
            _do_install_schedule(interval=6, session=120)
        return plist_path.read_text()

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_flag_set_in_shell_lands_in_plist(self, mock_run, tmp_path, monkeypatch):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        monkeypatch.setenv("MOLTBOOK_SKILL_SELECTION_ENFORCE", "1")
        content = self._install(tmp_path)
        assert "MOLTBOOK_SKILL_SELECTION_ENFORCE" in content
        assert "{{ENFORCE_ENV}}" not in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_flag_unset_leaves_plist_clean(self, mock_run, tmp_path, monkeypatch):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        monkeypatch.delenv("MOLTBOOK_SKILL_SELECTION_ENFORCE", raising=False)
        content = self._install(tmp_path)
        assert "MOLTBOOK_SKILL_SELECTION_ENFORCE" not in content
        assert "{{ENFORCE_ENV}}" not in content


class TestWeeklyPipelineSchedule:
    """ADR-0085: the unattended weekly chain replaces --weekly-analysis and
    ships with a dependency-free watchdog job on fixed check times."""

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_weekly_pipeline_creates_plist(self, mock_run, plist_sandbox):
        from contemplative_agent.cli.schedule import _do_install_weekly_pipeline_schedule

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        _do_install_weekly_pipeline_schedule(weekday=6, hour=9)

        content = plist_sandbox["LAUNCHD_WEEKLY_PIPELINE_PLIST_PATH"].read_text()
        assert "weekly-pipeline.sh" in content
        assert "<integer>6</integer>" in content
        assert "<integer>9</integer>" in content
        for placeholder in (
            "{{PROJECT_ROOT}}",
            "{{WEEKDAY}}",
            "{{HOUR}}",
            "{{LOG_PATH}}",
            "{{STAGES_ENV}}",
        ):
            assert placeholder not in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_pipeline_stages_env_baked_when_exported(self, mock_run, plist_sandbox, monkeypatch):
        from contemplative_agent.cli.schedule import _do_install_weekly_pipeline_schedule

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        monkeypatch.setenv("MOLTBOOK_PIPELINE_STAGES", "report,diagnosis,insight,packet")
        _do_install_weekly_pipeline_schedule(weekday=6, hour=9)
        content = plist_sandbox["LAUNCHD_WEEKLY_PIPELINE_PLIST_PATH"].read_text()
        assert "MOLTBOOK_PIPELINE_STAGES" in content
        assert "report,diagnosis,insight,packet" in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_pipeline_stages_env_absent_when_unset(self, mock_run, plist_sandbox, monkeypatch):
        from contemplative_agent.cli.schedule import _do_install_weekly_pipeline_schedule

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        monkeypatch.delenv("MOLTBOOK_PIPELINE_STAGES", raising=False)
        _do_install_weekly_pipeline_schedule(weekday=6, hour=9)
        content = plist_sandbox["LAUNCHD_WEEKLY_PIPELINE_PLIST_PATH"].read_text()
        assert "MOLTBOOK_PIPELINE_STAGES" not in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_watchdog_creates_plist(self, mock_run, plist_sandbox):
        from contemplative_agent.cli.schedule import _do_install_watchdog_schedule

        mock_run.return_value = MagicMock(returncode=0, stderr="")
        _do_install_watchdog_schedule()

        content = plist_sandbox["LAUNCHD_WATCHDOG_PLIST_PATH"].read_text()
        assert "pipeline_watchdog.sh" in content
        # The watchdog must not shell out to claude/uv — pure bash entrypoint.
        # Prose comments in the plist may mention them; <string> args must not.
        arg_strings = [line for line in content.splitlines() if "<string>" in line]
        assert not any("claude" in line or "uv " in line for line in arg_strings)
        for placeholder in ("{{PROJECT_ROOT}}", "{{LOG_PATH}}"):
            assert placeholder not in content

    def test_weekly_pipeline_excludes_weekly_analysis(self):
        from contemplative_agent.cli.schedule import _handle_install_schedule

        args = argparse.Namespace(
            uninstall=False,
            interval=6,
            session=30,
            distill_hour=3,
            no_distill=False,
            weekly_analysis=True,
            weekly_analysis_day=6,
            weekly_analysis_hour=9,
            weekly_insight=False,
            weekly_backup=False,
            weekly_submolt_scan=False,
            weekly_pipeline=True,
            weekly_pipeline_day=6,
            weekly_pipeline_hour=9,
            watchdog=False,
        )
        parser = argparse.ArgumentParser()
        with (
            patch("contemplative_agent.cli.schedule._do_install_schedule") as mock_session,
            patch(
                "contemplative_agent.cli.schedule._do_install_weekly_pipeline_schedule"
            ) as mock_pipeline,
        ):
            with pytest.raises(SystemExit):
                _handle_install_schedule(args, parser)
        mock_session.assert_not_called()
        mock_pipeline.assert_not_called()

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_stale_pipeline_and_watchdog_removed(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        pipeline = plist_sandbox["LAUNCHD_WEEKLY_PIPELINE_PLIST_PATH"]
        watchdog = plist_sandbox["LAUNCHD_WATCHDOG_PLIST_PATH"]
        pipeline.write_text("dummy")
        watchdog.write_text("dummy")
        _remove_stale_schedule_jobs(
            distill=True,
            weekly_analysis=True,
            weekly_insight=True,
            weekly_backup=True,
            weekly_pipeline=False,
            watchdog=False,
        )
        assert not pipeline.exists()
        assert not watchdog.exists()


class TestWeeklyPipelineValidationOrder:
    """M9-shaped guard for the new flags: invalid --weekly-pipeline-* values
    must reject before ANY schedule is installed (2026-07-29 review)."""

    def test_invalid_pipeline_day_installs_nothing(self):
        from contemplative_agent.cli.schedule import _handle_install_schedule

        args = argparse.Namespace(
            uninstall=False,
            interval=6,
            session=30,
            distill_hour=3,
            no_distill=False,
            weekly_analysis=False,
            weekly_insight=False,
            weekly_backup=False,
            weekly_submolt_scan=False,
            weekly_pipeline=True,
            weekly_pipeline_day=9,  # invalid (>6)
            weekly_pipeline_hour=9,
            watchdog=False,
        )
        parser = argparse.ArgumentParser()
        with (
            patch("contemplative_agent.cli.schedule._do_install_schedule") as mock_session,
            patch(
                "contemplative_agent.cli.schedule._do_install_weekly_pipeline_schedule"
            ) as mock_pipeline,
        ):
            with pytest.raises(SystemExit):
                _handle_install_schedule(args, parser)
        mock_session.assert_not_called()
        mock_pipeline.assert_not_called()


class TestInstallSubmoltScanSchedule:
    """ADR-0086: the scope sweep gets its own job rather than a stage inside
    an existing one — it is ~20 feed reads plus a few hundred local LLM calls,
    and it must not land on top of a session."""

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_install_creates_plist(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        _do_install_submolt_scan_schedule(weekday=4, hour=3)

        plist_path = plist_sandbox["LAUNCHD_SUBMOLT_SCAN_PLIST_PATH"]
        assert plist_path.exists()
        content = plist_path.read_text()
        assert "submolt-scan" in content
        assert "<integer>4</integer>" in content
        assert "<integer>3</integer>" in content
        for placeholder in (
            "{{PROJECT_ROOT}}",
            "{{WEEKDAY}}",
            "{{HOUR}}",
            "{{LOG_PATH}}",
            "{{VENV_BIN}}",
        ):
            assert placeholder not in content

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_default_hour_avoids_the_session_hours(self, mock_run, plist_sandbox):
        """The sweep and a session must never contend for the one Ollama."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        parser = argparse.ArgumentParser()
        from contemplative_agent.cli.schedule import _add_install_schedule_arguments

        _add_install_schedule_arguments(parser)
        args = parser.parse_args([])
        assert args.weekly_submolt_scan_hour not in (0, 6, 12, 18)

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_removed_when_flag_dropped(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        scan = plist_sandbox["LAUNCHD_SUBMOLT_SCAN_PLIST_PATH"]
        scan.write_text("dummy")
        _remove_stale_schedule_jobs(
            distill=True,
            weekly_analysis=True,
            weekly_insight=True,
            weekly_backup=True,
            weekly_pipeline=True,
            watchdog=True,
            submolt_scan=False,
        )
        assert not scan.exists()

    @patch("contemplative_agent.cli.schedule.subprocess.run")
    def test_kept_when_flag_on(self, mock_run, plist_sandbox):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        scan = plist_sandbox["LAUNCHD_SUBMOLT_SCAN_PLIST_PATH"]
        scan.write_text("dummy")
        _remove_stale_schedule_jobs(
            distill=True,
            weekly_analysis=True,
            weekly_insight=True,
            weekly_backup=True,
            weekly_pipeline=True,
            watchdog=True,
            submolt_scan=True,
        )
        assert scan.exists()

    @pytest.mark.parametrize("flag", ["--weekly-submolt-scan-day", "--weekly-submolt-scan-hour"])
    def test_out_of_range_schedule_installs_nothing(self, flag, plist_sandbox):
        """M9 ordering: validation runs before any plist is written."""
        argv = ["contemplative-agent", "install-schedule", "--weekly-submolt-scan", flag, "99"]
        with patch("sys.argv", argv):
            with pytest.raises(SystemExit):
                main()
        assert not any(p.exists() for p in plist_sandbox.values())


class TestLaunchdTemplatesStayNonVerbose:
    """No scheduled job may run verbose (T-LOG-DEBUG-CONTENT).

    Every template routes both StandardOutPath and StandardErrorPath to
    ``{{LOG_PATH}}``, which ``_install_plist`` always resolves under
    ``MOLTBOOK_DATA_DIR/logs`` — the directory ``scripts/log_anomaly_sweep.py``
    globs and ``scripts/weekly-analysis.sh`` feeds to an LLM. So "verbose +
    logs-dir redirection" reduces to "verbose at all", and the check is a
    property of the templates rather than of the installed plists (which live
    outside the repo and cannot be gated here).

    ``publish.log_published``'s docstring stated this as prose from weekly
    2026-07-11 F1.1 and the production ``com.moltbook.agent`` plist violated it
    for weeks. Prose is not a gate.
    """

    VERBOSE_FLAGS = {"-v", "--verbose", "-vv", "-vvv"}

    def _templates(self):
        from contemplative_agent.cli import runtime

        template_dir = runtime._repo_root() / "config" / "launchd"
        templates = sorted(template_dir.glob("*.plist"))
        assert templates, f"no launchd templates found under {template_dir}"
        return templates

    def test_no_template_passes_a_verbose_flag(self):
        offenders = []
        for template in self._templates():
            block = re.search(
                r"<key>ProgramArguments</key>\s*<array>(.*?)</array>",
                template.read_text(encoding="utf-8"),
                re.DOTALL,
            )
            assert block, f"{template.name} has no ProgramArguments array"
            args = re.findall(r"<string>([^<]*)</string>", block.group(1))
            for arg in args:
                if arg.strip() in self.VERBOSE_FLAGS:
                    offenders.append(f"{template.name}: {arg.strip()}")
        assert not offenders, (
            "launchd templates must not run verbose — DEBUG output lands in the "
            f"sweep-scanned logs dir: {offenders}"
        )

    def test_every_template_redirects_into_the_logs_dir(self):
        """Guards the reduction the test above relies on. If a future template
        writes somewhere else, 'verbose implies leak' stops holding and this
        fails loudly instead of letting the check quietly over-scope."""
        for template in self._templates():
            content = template.read_text(encoding="utf-8")
            for key in ("StandardOutPath", "StandardErrorPath"):
                match = re.search(rf"<key>{key}</key>\s*<string>([^<]*)</string>", content)
                assert match, f"{template.name} has no {key}"
                target = match.group(1)
                # Two placeholder shapes. ``{{LOG_PATH}}`` is code-backed:
                # _install_plist computes it under MOLTBOOK_DATA_DIR/logs.
                # ``{{LOG_DIR}}/<name>.log`` is NOT — it appears only in
                # com.moltbook.ollama-restart.plist, which install-schedule
                # deliberately does not manage (installed by hand via
                # launchctl; docs/CONFIGURATION.md). Nothing in src/
                # substitutes it, so accepting it here is a convention check,
                # not a resolved-path guarantee. That is tolerable because
                # that job does not run the contemplative-agent CLI at all
                # (it is `bash -c pkill … ; ollama serve`), so the verbose
                # flag this class exists to catch cannot apply to it.
                assert target == "{{LOG_PATH}}" or target.startswith("{{LOG_DIR}}/"), (
                    f"{template.name} {key} is {target!r}, which is not a "
                    "logs-dir placeholder this gate can vouch for"
                )
