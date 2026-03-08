"""Tests for the CLI entry point."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from contemplative_moltbook.cli import main, _setup_logging


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
        with patch("sys.argv", ["contemplative-moltbook"]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1


class TestMainRegister:
    @patch("contemplative_moltbook.cli.Agent")
    def test_register(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent.do_register.return_value = {"claim_url": "https://example.com"}
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "register"]):
            main()

        mock_agent.do_register.assert_called_once()


class TestMainStatus:
    @patch("contemplative_moltbook.cli.Agent")
    def test_status(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent.do_status.return_value = {"claimed": True}
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "status"]):
            main()

        mock_agent.do_status.assert_called_once()


class TestMainIntroduce:
    @patch("contemplative_moltbook.cli.Agent")
    def test_introduce(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "introduce"]):
            main()

        mock_agent.do_introduce.assert_called_once()


class TestMainRun:
    @patch("contemplative_moltbook.cli.Agent")
    def test_run_default_duration(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "run"]):
            main()

        mock_agent.run_session.assert_called_once_with(duration_minutes=60)

    @patch("contemplative_moltbook.cli.Agent")
    def test_run_custom_duration(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "run", "--session", "30"]):
            main()

        mock_agent.run_session.assert_called_once_with(duration_minutes=30)


class TestMainSolve:
    @patch("contemplative_moltbook.cli.Agent")
    def test_solve(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "solve", "test text"]):
            main()

        mock_agent.do_solve.assert_called_once_with("test text")


class TestAutonomyFlags:
    @patch("contemplative_moltbook.cli.Agent")
    def test_approve_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "--approve", "status"]):
            main()

        from contemplative_moltbook.agent import AutonomyLevel
        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.APPROVE)

    @patch("contemplative_moltbook.cli.Agent")
    def test_guarded_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "--guarded", "status"]):
            main()

        from contemplative_moltbook.agent import AutonomyLevel
        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.GUARDED)

    @patch("contemplative_moltbook.cli.Agent")
    def test_auto_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-moltbook", "--auto", "status"]):
            main()

        from contemplative_moltbook.agent import AutonomyLevel
        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.AUTO)

    @patch("contemplative_moltbook.cli.Agent")
    def test_verbose_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        root = logging.getLogger()
        root.handlers.clear()
        with patch("sys.argv", ["contemplative-moltbook", "-v", "status"]):
            main()

        assert root.level == logging.DEBUG
