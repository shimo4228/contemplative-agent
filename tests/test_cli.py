"""Tests for the CLI entry point."""

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli import (
    main,
    _setup_logging,
    _build_calendar_intervals,
    _do_init,
    _do_install_schedule,
    _do_install_distill_schedule,
    _do_uninstall_schedule,
    _list_templates,
    _log_approval,
    _stage_results,
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
        assert "domain" in call_kwargs["session_meta"]

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
        # NOTE: _do_uninstall_schedule walks THREE plist paths (session,
        # distill, weekly-analysis). All three must be patched to tmp_path,
        # otherwise the weekly-analysis path falls through to the user's
        # real ~/Library/LaunchAgents/ and the test will silently delete
        # the live plist. (See Apr 8 incident.)
        plist_path = tmp_path / "com.moltbook.agent.plist"
        distill_plist_path = tmp_path / "com.moltbook.distill.plist"
        weekly_plist_path = tmp_path / "com.moltbook.weekly-analysis.plist"
        with patch("contemplative_agent.cli.LAUNCHD_PLIST_PATH", plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_DISTILL_PLIST_PATH", distill_plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH", weekly_plist_path):
            _do_uninstall_schedule()
        assert "No schedule installed" in capsys.readouterr().out

    @patch("contemplative_agent.cli.subprocess.run")
    def test_uninstall_removes_plist(self, mock_run, tmp_path):
        plist_path = tmp_path / "com.moltbook.agent.plist"
        distill_plist_path = tmp_path / "com.moltbook.distill.plist"
        weekly_plist_path = tmp_path / "com.moltbook.weekly-analysis.plist"
        plist_path.write_text("dummy")

        with patch("contemplative_agent.cli.LAUNCHD_PLIST_PATH", plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_DISTILL_PLIST_PATH", distill_plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH", weekly_plist_path):
            _do_uninstall_schedule()

        assert not plist_path.exists()
        mock_run.assert_called_once()


class TestInstallDistillSchedule:
    @patch("contemplative_agent.cli.subprocess.run")
    def test_install_creates_distill_plist(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.distill.plist"

        with patch("contemplative_agent.cli.LAUNCHD_DISTILL_PLIST_PATH", plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_PLIST_DIR", tmp_path):
            _do_install_distill_schedule(distill_hour=3)

        assert plist_path.exists()
        content = plist_path.read_text()
        assert "distill" in content
        assert "<integer>3</integer>" in content
        # Verify all placeholders were replaced
        for placeholder in ("{{VENV_BIN}}", "{{PROJECT_ROOT}}", "{{DISTILL_HOUR}}", "{{LOG_PATH}}"):
            assert placeholder not in content

    @patch("contemplative_agent.cli.subprocess.run")
    def test_install_distill_custom_hour(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.distill.plist"

        with patch("contemplative_agent.cli.LAUNCHD_DISTILL_PLIST_PATH", plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_PLIST_DIR", tmp_path):
            _do_install_distill_schedule(distill_hour=5)

        content = plist_path.read_text()
        assert "<integer>5</integer>" in content

    @patch("contemplative_agent.cli.subprocess.run")
    def test_install_distill_unloads_existing(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        plist_path = tmp_path / "com.moltbook.distill.plist"
        plist_path.write_text("old content")

        with patch("contemplative_agent.cli.LAUNCHD_DISTILL_PLIST_PATH", plist_path), \
             patch("contemplative_agent.cli.LAUNCHD_PLIST_DIR", tmp_path):
            _do_install_distill_schedule(distill_hour=3)

        assert mock_run.call_count == 2
        assert "unload" in mock_run.call_args_list[0][0][0]
        assert "load" in mock_run.call_args_list[1][0][0]


class TestUninstallScheduleBoth:
    @patch("contemplative_agent.cli.subprocess.run")
    def test_uninstall_removes_both_plists(self, mock_run, tmp_path):
        # NOTE: All THREE plist paths must be patched (session, distill,
        # weekly-analysis), otherwise the unpatched one falls through to
        # the user's real ~/Library/LaunchAgents/. The weekly tmp path is
        # left intentionally non-existent so the uninstall walker skips
        # it, keeping the mock_run.call_count expectation at 2.
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        agent_plist = tmp_path / "com.moltbook.agent.plist"
        distill_plist = tmp_path / "com.moltbook.distill.plist"
        weekly_plist = tmp_path / "com.moltbook.weekly-analysis.plist"
        agent_plist.write_text("dummy")
        distill_plist.write_text("dummy")

        with patch("contemplative_agent.cli.LAUNCHD_PLIST_PATH", agent_plist), \
             patch("contemplative_agent.cli.LAUNCHD_DISTILL_PLIST_PATH", distill_plist), \
             patch("contemplative_agent.cli.LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH", weekly_plist):
            _do_uninstall_schedule()

        assert not agent_plist.exists()
        assert not distill_plist.exists()
        assert mock_run.call_count == 2

    def test_uninstall_no_plists(self, tmp_path, capsys):
        agent_plist = tmp_path / "com.moltbook.agent.plist"
        distill_plist = tmp_path / "com.moltbook.distill.plist"
        weekly_plist = tmp_path / "com.moltbook.weekly-analysis.plist"

        with patch("contemplative_agent.cli.LAUNCHD_PLIST_PATH", agent_plist), \
             patch("contemplative_agent.cli.LAUNCHD_DISTILL_PLIST_PATH", distill_plist), \
             patch("contemplative_agent.cli.LAUNCHD_WEEKLY_ANALYSIS_PLIST_PATH", weekly_plist):
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


class TestListTemplates:
    def test_lists_available_templates(self):
        templates = _list_templates()
        assert "contemplative" in templates
        assert "stoic" in templates
        assert len(templates) >= 2

    def test_returns_sorted(self):
        templates = _list_templates()
        assert templates == sorted(templates)


class TestDoInit:
    def test_default_template(self, tmp_path):
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.IDENTITY_PATH", tmp_path / "identity.md"), \
             patch("contemplative_agent.cli.KNOWLEDGE_PATH", tmp_path / "knowledge.json"), \
             patch("contemplative_agent.cli.CONSTITUTION_DIR", tmp_path / "constitution"), \
             patch("contemplative_agent.cli.SKILLS_DIR", tmp_path / "skills"), \
             patch("contemplative_agent.cli.RULES_DIR", tmp_path / "rules"):
            _do_init()

        assert (tmp_path / "identity.md").exists()
        assert (tmp_path / "knowledge.json").exists()
        assert (tmp_path / "constitution").is_dir()
        assert (tmp_path / "skills").is_dir()
        assert (tmp_path / "rules").is_dir()
        # Knowledge is always empty array
        assert json.loads((tmp_path / "knowledge.json").read_text()) == []

    def test_custom_template(self, tmp_path):
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.IDENTITY_PATH", tmp_path / "identity.md"), \
             patch("contemplative_agent.cli.KNOWLEDGE_PATH", tmp_path / "knowledge.json"), \
             patch("contemplative_agent.cli.CONSTITUTION_DIR", tmp_path / "constitution"), \
             patch("contemplative_agent.cli.SKILLS_DIR", tmp_path / "skills"), \
             patch("contemplative_agent.cli.RULES_DIR", tmp_path / "rules"):
            _do_init(template_name="stoic")

        identity = (tmp_path / "identity.md").read_text()
        assert len(identity) > 1  # Not empty — copied from template

    def test_invalid_template(self, tmp_path):
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.IDENTITY_PATH", tmp_path / "identity.md"), \
             patch("contemplative_agent.cli.KNOWLEDGE_PATH", tmp_path / "knowledge.json"), \
             patch("contemplative_agent.cli.CONSTITUTION_DIR", tmp_path / "constitution"), \
             patch("contemplative_agent.cli.SKILLS_DIR", tmp_path / "skills"), \
             patch("contemplative_agent.cli.RULES_DIR", tmp_path / "rules"):
            with pytest.raises(SystemExit):
                _do_init(template_name="nonexistent")

    def test_skips_existing(self, tmp_path, capsys):
        identity = tmp_path / "identity.md"
        identity.write_text("existing identity")
        constitution = tmp_path / "constitution"
        constitution.mkdir()

        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.IDENTITY_PATH", identity), \
             patch("contemplative_agent.cli.KNOWLEDGE_PATH", tmp_path / "knowledge.json"), \
             patch("contemplative_agent.cli.CONSTITUTION_DIR", constitution), \
             patch("contemplative_agent.cli.SKILLS_DIR", tmp_path / "skills"), \
             patch("contemplative_agent.cli.RULES_DIR", tmp_path / "rules"):
            _do_init()

        # Identity should not be overwritten
        assert identity.read_text() == "existing identity"
        out = capsys.readouterr().out
        assert "already exists" in out


class TestLogApproval:
    def test_creates_audit_log(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("skills/foo.md"), True, "# Skill content")

        assert audit_path.exists()
        record = json.loads(audit_path.read_text().strip())
        assert record["command"] == "insight"
        assert record["decision"] == "approved"
        assert record["path"] == "skills/foo.md"
        assert len(record["content_hash"]) == 16
        assert "ts" in record

    def test_logs_rejection(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval("rules-distill", Path("rules/bar.md"), False, "content")

        record = json.loads(audit_path.read_text().strip())
        assert record["decision"] == "rejected"

    def test_appends_multiple(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "a")
            _log_approval("insight", Path("b.md"), False, "b")

        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_different_content_different_hash(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content A")
            _log_approval("insight", Path("a.md"), True, "content B")

        lines = audit_path.read_text().strip().splitlines()
        h1 = json.loads(lines[0])["content_hash"]
        h2 = json.loads(lines[1])["content_hash"]
        assert h1 != h2


class TestStageResults:
    """Tests for _stage_results() staging helper."""

    def test_stages_files_with_meta(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        target = tmp_path / "skills" / "test-skill.md"
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path):
            _stage_results(
                [("test-skill.md", "# Test Skill\nContent", target)],
                command="insight",
            )
        assert (staged_dir / "test-skill.md").exists()
        assert "# Test Skill" in (staged_dir / "test-skill.md").read_text()
        meta = json.loads((staged_dir / "test-skill.md.meta.json").read_text())
        assert meta["target"] == str(target)
        assert meta["command"] == "insight"

    def test_stages_multiple_files(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        items = [
            ("a.md", "# A", tmp_path / "skills" / "a.md"),
            ("b.md", "# B", tmp_path / "skills" / "b.md"),
        ]
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path):
            _stage_results(items, command="insight")
        assert (staged_dir / "a.md").exists()
        assert (staged_dir / "b.md").exists()

    def test_rejects_path_traversal(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"
        evil_target = Path("/tmp/evil.md")
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path):
            _stage_results(
                [("evil.md", "pwned", evil_target)],
                command="insight",
            )
        assert not (staged_dir / "evil.md").exists()
        assert "escapes MOLTBOOK_HOME" in capsys.readouterr().err
