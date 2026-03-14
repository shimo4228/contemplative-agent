"""Tests for the CLI entry point."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli import (
    main,
    _setup_logging,
    _build_calendar_intervals,
    _do_install_schedule,
    _do_uninstall_schedule,
)


class TestSetupLogging:
    def test_debug_level(self):
        root = logging.getLogger()
        root.handlers.clear()
        _setup_logging(verbose=True)
        assert root.level == logging.DEBUG

    def test_info_level(self):
        root = logging.getLogger()
        root.handlers.clear()
        _setup_logging(verbose=False)
        assert root.level == logging.INFO


class TestMainNoCommand:
    def test_no_command_exits(self):
        with patch("sys.argv", ["contemplative-agent"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestMainRegister:
    @patch("contemplative_agent.cli.Agent")
    def test_register(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent.do_register.return_value = {"claim_url": "https://example.com"}
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "register"]):
            main()

        mock_agent.do_register.assert_called_once()


class TestMainStatus:
    @patch("contemplative_agent.cli.Agent")
    def test_status(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent.do_status.return_value = {"claimed": True}
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "status"]):
            main()

        mock_agent.do_status.assert_called_once()


class TestMainIntroduce:
    @patch("contemplative_agent.cli.Agent")
    def test_introduce(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "introduce"]):
            main()

        mock_agent.do_introduce.assert_called_once()


class TestMainRun:
    @patch("contemplative_agent.cli.Agent")
    def test_run_default_duration(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "run"]):
            main()

        mock_agent.run_session.assert_called_once_with(duration_minutes=60)

    @patch("contemplative_agent.cli.Agent")
    def test_run_custom_duration(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "run", "--session", "30"]):
            main()

        mock_agent.run_session.assert_called_once_with(duration_minutes=30)


class TestMainSolve:
    @patch("contemplative_agent.cli.Agent")
    def test_solve(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "solve", "test text"]):
            main()

        mock_agent.do_solve.assert_called_once_with("test text")


class TestAutonomyFlags:
    @patch("contemplative_agent.cli.Agent")
    def test_approve_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "--approve", "status"]):
            main()

        from contemplative_agent.adapters.moltbook.agent import AutonomyLevel
        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.APPROVE, domain_config=None)

    @patch("contemplative_agent.cli.Agent")
    def test_guarded_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "--guarded", "status"]):
            main()

        from contemplative_agent.adapters.moltbook.agent import AutonomyLevel
        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.GUARDED, domain_config=None)

    @patch("contemplative_agent.cli.Agent")
    def test_auto_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "--auto", "status"]):
            main()

        from contemplative_agent.adapters.moltbook.agent import AutonomyLevel
        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.AUTO, domain_config=None)

    @patch("contemplative_agent.cli.Agent")
    def test_verbose_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        root = logging.getLogger()
        root.handlers.clear()
        with patch("sys.argv", ["contemplative-agent", "-v", "status"]):
            main()

        assert root.level == logging.DEBUG


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
    @patch("contemplative_agent.cli.subprocess.run")
    def test_install_creates_plist(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.agent.plist"

        with patch("contemplative_agent.cli.LAUNCHD_PLIST_PATH", plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_PLIST_DIR", tmp_path):
            _do_install_schedule(interval=6, session=120)

        assert plist_path.exists()
        content = plist_path.read_text()
        assert "<string>120</string>" in content
        assert "contemplative-agent" in content
        # Verify all placeholders were replaced
        for placeholder in ("{{VENV_BIN}}", "{{PROJECT_ROOT}}", "{{SESSION_MINUTES}}", "{{LOG_PATH}}", "{{CALENDAR_INTERVALS}}"):
            assert placeholder not in content

    @patch("contemplative_agent.cli.subprocess.run")
    def test_install_unloads_existing(self, mock_run, tmp_path):
        """If plist already exists, unload before overwriting."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.agent.plist"
        plist_path.write_text("old content")

        with patch("contemplative_agent.cli.LAUNCHD_PLIST_PATH", plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_PLIST_DIR", tmp_path):
            _do_install_schedule(interval=6, session=120)

        # First call: unload, second call: load
        assert mock_run.call_count == 2
        assert "unload" in mock_run.call_args_list[0][0][0]
        assert "load" in mock_run.call_args_list[1][0][0]


class TestUninstallSchedule:
    def test_uninstall_no_plist(self, tmp_path, capsys):
        plist_path = tmp_path / "com.moltbook.agent.plist"
        with patch("contemplative_agent.cli.LAUNCHD_PLIST_PATH", plist_path):
            _do_uninstall_schedule()
        assert "No schedule installed" in capsys.readouterr().out

    @patch("contemplative_agent.cli.subprocess.run")
    def test_uninstall_removes_plist(self, mock_run, tmp_path):
        plist_path = tmp_path / "com.moltbook.agent.plist"
        plist_path.write_text("dummy")

        with patch("contemplative_agent.cli.LAUNCHD_PLIST_PATH", plist_path):
            _do_uninstall_schedule()

        assert not plist_path.exists()
        mock_run.assert_called_once()


class TestInstallScheduleCommand:
    def test_invalid_interval_exits(self):
        with patch("sys.argv", ["contemplative-agent", "install-schedule", "--interval", "5"]):
            with pytest.raises(SystemExit):
                main()

    def test_invalid_session_exits(self):
        with patch("sys.argv", ["contemplative-agent", "install-schedule", "--session", "0"]):
            with pytest.raises(SystemExit):
                main()


class TestNoAxiomsFlag:
    """Tests for --no-axioms flag controlling CCAI clause injection."""

    @patch("contemplative_agent.cli.Agent")
    @patch("contemplative_agent.cli.configure_llm")
    def test_axioms_injected_by_default(self, mock_configure, mock_agent_cls):
        """Without --no-axioms, configure_llm should be called with axiom_prompt."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "status"]):
            main()

        # axiom_prompt should have been passed if contemplative-axioms.md exists
        calls = [c for c in mock_configure.call_args_list if "axiom_prompt" in c.kwargs]
        if calls:
            assert calls[0].kwargs["axiom_prompt"]  # non-empty string

    @patch("contemplative_agent.cli.Agent")
    @patch("contemplative_agent.cli.configure_llm")
    def test_no_axioms_skips_injection(self, mock_configure, mock_agent_cls):
        """With --no-axioms, configure_llm should NOT be called with axiom_prompt."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "--no-axioms", "status"]):
            main()

        # axiom_prompt should NOT have been passed
        axiom_calls = [c for c in mock_configure.call_args_list if "axiom_prompt" in c.kwargs]
        assert len(axiom_calls) == 0
