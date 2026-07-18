"""Tests for the CLI entry point: main dispatch, runtime setup, repo root."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli import main
from contemplative_agent.cli.runtime import _setup_logging



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


class TestMainRun:
    @patch("contemplative_agent.cli.Agent")
    def test_run_default_duration(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "run"]):
            main()

        mock_agent.run_session.assert_called_once()
        call_kwargs = mock_agent.run_session.call_args[1]
        assert call_kwargs["duration_minutes"] == 60
        assert "session_meta" in call_kwargs
        meta = call_kwargs["session_meta"]
        assert "domain" in meta
        assert meta["llm_backend"] == "ollama"
        # Session metadata reuses the canonical served-model resolver (ADR-0069)
        # rather than a stale literal, so assert against it, not a hardcoded id.
        from contemplative_agent.core.llm import served_model

        assert meta["llm_model"] == served_model()
        assert meta["ollama_model"] == served_model()

    @patch("contemplative_agent.cli.Agent")
    def test_run_clears_session_id_after_return(self, mock_agent_cls):
        # 回帰 (codex-review 2026-07-16): run 終了後に session_id が残留し、
        # 同一プロセスの後続 audit 書き込みへ stale session_id が付く
        from contemplative_agent.core.run_context import current_session_id

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "run"]):
            main()

        assert current_session_id() is None
        session_meta = mock_agent.run_session.call_args[1]["session_meta"]
        assert session_meta["session_id"]  # session 中は採番済みの id が渡る

    @patch("contemplative_agent.cli.Agent")
    def test_run_clears_session_id_even_when_lock_unavailable(self, mock_agent_cls):
        from contemplative_agent.core.run_context import current_session_id

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("contemplative_agent.cli.acquire_run_lock") as mock_lock:
            mock_lock.return_value.__enter__.return_value = False
            with patch("sys.argv", ["contemplative-agent", "run"]):
                main()

        mock_agent.run_session.assert_not_called()
        assert current_session_id() is None

    @patch("contemplative_agent.cli.Agent")
    def test_run_custom_duration(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "run", "--session", "30"]):
            main()

        call_kwargs = mock_agent.run_session.call_args[1]
        assert call_kwargs["duration_minutes"] == 30


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


class TestNoAxiomsFlag:
    """Tests for --no-axioms flag controlling CCAI clause injection."""

    @patch("contemplative_agent.cli.runtime.load_constitution")
    @patch("contemplative_agent.cli.Agent")
    @patch("contemplative_agent.cli.runtime.configure_llm")
    def test_axioms_injected_by_default(
        self, mock_configure, mock_agent_cls, mock_load_constitution
    ):
        """Without --no-axioms, configure_llm should be called with axiom_prompt."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent
        mock_load_constitution.return_value = "Axiom clauses for test."

        with patch("sys.argv", ["contemplative-agent", "status"]):
            main()

        calls = [c for c in mock_configure.call_args_list if "axiom_prompt" in c.kwargs]
        assert calls, "configure_llm was never called with axiom_prompt"
        assert calls[0].kwargs["axiom_prompt"] == "Axiom clauses for test."

    @patch("contemplative_agent.cli.Agent")
    @patch("contemplative_agent.cli.runtime.configure_llm")
    def test_no_axioms_skips_injection(self, mock_configure, mock_agent_cls):
        """With --no-axioms, configure_llm should NOT be called with axiom_prompt."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "--no-axioms", "status"]):
            main()

        # axiom_prompt should NOT have been passed
        axiom_calls = [c for c in mock_configure.call_args_list if "axiom_prompt" in c.kwargs]
        assert len(axiom_calls) == 0


class TestRepoRoot:
    """ADR-0079 Phase 2 regression (codex P1): the former single-file cli.py
    resolved the repo root as ``Path(__file__).resolve().parents[2]`` inline at
    three call sites. Inside the cli/ package that expression silently points
    at ``src/`` — breaking schedule install, making sync-data a silent no-op,
    and missing the packaged views fallback. These tests pin the shared
    ``_repo_root()`` helper and each original call site's derived asset."""

    def test_repo_root_is_project_root(self):
        from contemplative_agent.cli.runtime import _repo_root

        root = _repo_root()
        assert (root / "pyproject.toml").is_file()
        assert (root / "src" / "contemplative_agent").is_dir()

    def test_schedule_launchd_templates_resolve(self):
        # _install_plist reads config/launchd/<template> from the repo root.
        from contemplative_agent.cli.runtime import _repo_root

        assert (_repo_root() / "config" / "launchd" / "com.moltbook.agent.plist").is_file()

    def test_sync_script_resolves(self):
        # _run_sync shells out to scripts/sync-research-data.sh from the repo root.
        from contemplative_agent.cli.runtime import _repo_root

        assert (_repo_root() / "scripts" / "sync-research-data.sh").is_file()

    def test_packaged_views_resolve(self):
        # _resolve_views_dir falls back to config/views under the repo root.
        from contemplative_agent.cli.runtime import _repo_root

        assert (_repo_root() / "config" / "views").is_dir()
