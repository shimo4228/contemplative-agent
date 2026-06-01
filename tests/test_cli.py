"""Tests for the CLI entry point."""

import json
import logging
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli import (
    main,
    _approve_delete,
    _handle_adopt_staged,
    _handle_dialogue,
    _handle_remove_skill,
    _handle_rules_stocktake,
    _handle_skill_stocktake,
    _setup_logging,
    _build_calendar_intervals,
    _do_init,
    _do_install_schedule,
    _do_install_distill_schedule,
    _do_uninstall_schedule,
    _list_templates,
    _log_approval,
    _stage_results,
    StageItem,
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

    def test_copies_prompts_and_views_from_config(self, tmp_path):
        """`init` materialises all LLM-facing Markdown files under MOLTBOOK_HOME."""
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.IDENTITY_PATH", tmp_path / "identity.md"), \
             patch("contemplative_agent.cli.KNOWLEDGE_PATH", tmp_path / "knowledge.json"), \
             patch("contemplative_agent.cli.CONSTITUTION_DIR", tmp_path / "constitution"), \
             patch("contemplative_agent.cli.SKILLS_DIR", tmp_path / "skills"), \
             patch("contemplative_agent.cli.RULES_DIR", tmp_path / "rules"), \
             patch("contemplative_agent.cli.PROMPTS_DIR", tmp_path / "prompts"), \
             patch("contemplative_agent.cli.VIEWS_DIR", tmp_path / "views"):
            _do_init()

        prompts_dst = tmp_path / "prompts"
        views_dst = tmp_path / "views"
        assert prompts_dst.is_dir()
        assert views_dst.is_dir()

        # Every .md the repo ships under config/prompts/ and config/views/
        # should now be materialised in the home.
        from contemplative_agent.core.domain import DEFAULT_CONFIG_DIR
        packaged_prompts = sorted(p.name for p in (DEFAULT_CONFIG_DIR / "prompts").glob("*.md"))
        packaged_views = sorted(p.name for p in (DEFAULT_CONFIG_DIR / "views").glob("*.md"))
        assert sorted(p.name for p in prompts_dst.glob("*.md")) == packaged_prompts
        assert sorted(p.name for p in views_dst.glob("*.md")) == packaged_views

    def test_skips_existing_prompts_and_views(self, tmp_path, capsys):
        """Re-running `init` after a user edit leaves the edit intact."""
        prompts = tmp_path / "prompts"
        prompts.mkdir()
        (prompts / "distill.md").write_text("user-edited distill", encoding="utf-8")
        views = tmp_path / "views"
        views.mkdir()

        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.IDENTITY_PATH", tmp_path / "identity.md"), \
             patch("contemplative_agent.cli.KNOWLEDGE_PATH", tmp_path / "knowledge.json"), \
             patch("contemplative_agent.cli.CONSTITUTION_DIR", tmp_path / "constitution"), \
             patch("contemplative_agent.cli.SKILLS_DIR", tmp_path / "skills"), \
             patch("contemplative_agent.cli.RULES_DIR", tmp_path / "rules"), \
             patch("contemplative_agent.cli.PROMPTS_DIR", prompts), \
             patch("contemplative_agent.cli.VIEWS_DIR", views):
            _do_init()

        assert (prompts / "distill.md").read_text(encoding="utf-8") == "user-edited distill"
        out = capsys.readouterr().out
        assert "Prompts already exists" in out
        assert "Views already exists" in out


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

    def test_default_source_is_direct(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content")
        record = json.loads(audit_path.read_text().strip())
        assert record["source"] == "direct"

    def test_source_stage_adopted(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval(
                "insight", Path("a.md"), True, "content", source="stage-adopted"
            )
        record = json.loads(audit_path.read_text().strip())
        assert record["source"] == "stage-adopted"
        assert record["decision"] == "approved"

    def test_snapshot_path_recorded(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        snap = tmp_path / "snapshots" / "distill_20260415T104542Z"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval(
                "distill-identity", Path("identity.md"), True, "content",
                snapshot_path=snap,
            )
        record = json.loads(audit_path.read_text().strip())
        assert record["snapshot_path"] == str(snap)

    def test_snapshot_path_null_when_omitted(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content")
        record = json.loads(audit_path.read_text().strip())
        assert "snapshot_path" in record  # field always present for forward compat
        assert record["snapshot_path"] is None

    def test_reason_field_preserved_when_provided(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval(
                "remove-skill", Path("skills/foo.md"), True, "content",
                source="direct-remove", reason="superseded by 2026-04-17 run",
            )
        record = json.loads(audit_path.read_text().strip())
        assert record["reason"] == "superseded by 2026-04-17 run"
        assert record["source"] == "direct-remove"

    def test_reason_null_when_omitted(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content")
        record = json.loads(audit_path.read_text().strip())
        assert "reason" in record  # field always present for forward compat
        assert record["reason"] is None

    def test_staged_decision_for_none_approval(self, tmp_path):
        """approved=None should map to decision='staged'."""
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _log_approval(
                "insight", Path("a.md"), None, "content", source="stage"
            )
        record = json.loads(audit_path.read_text().strip())
        assert record["decision"] == "staged"
        assert record["source"] == "stage"


class TestHandleRemoveSkill:
    """`remove-skill` CLI: audit-backed manual skill deletion."""

    @staticmethod
    def _args(
        name: str,
        *,
        reason: str = "obsolete",
        yes: bool = True,
        dry_run: bool = False,
    ):
        """Build an argparse.Namespace matching the remove-skill subparser."""
        import argparse
        return argparse.Namespace(
            name=name, reason=reason, yes=yes, dry_run=dry_run,
        )

    @staticmethod
    def _make_skill(skills_dir: Path, name: str, body: str = "# Skill\ncontent\n") -> Path:
        skills_dir.mkdir(parents=True, exist_ok=True)
        path = skills_dir / f"{name}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def test_removes_skill_with_yes(self, tmp_path):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "foo-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _handle_remove_skill(
                self._args("foo-20260417", reason="old pipeline"),
                MagicMock(),
            )
        assert not target.exists()
        record = json.loads(audit_path.read_text().strip())
        assert record["command"] == "remove-skill"
        assert record["decision"] == "approved"
        assert record["source"] == "direct-remove-auto"
        assert record["reason"] == "old pipeline"

    def test_prompts_without_yes_approved(self, tmp_path):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "bar-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path), \
             patch("contemplative_agent.cli._approve_delete", return_value=True):
            _handle_remove_skill(
                self._args("bar-20260417", yes=False),
                MagicMock(),
            )
        assert not target.exists()
        record = json.loads(audit_path.read_text().strip())
        assert record["source"] == "direct-remove"
        assert record["decision"] == "approved"

    def test_rejects_without_yes(self, tmp_path):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "baz-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path), \
             patch("contemplative_agent.cli._approve_delete", return_value=False):
            _handle_remove_skill(
                self._args("baz-20260417", yes=False),
                MagicMock(),
            )
        assert target.exists()
        record = json.loads(audit_path.read_text().strip())
        assert record["source"] == "direct-remove"
        assert record["decision"] == "rejected"

    def test_nonexistent_skill_exits(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            with pytest.raises(SystemExit) as exc:
                _handle_remove_skill(
                    self._args("nonexistent-20260417"),
                    MagicMock(),
                )
        assert exc.value.code == 1
        assert not audit_path.exists()

    def test_dry_run_skips_delete_and_audit(self, tmp_path, capsys):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "keep-me-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _handle_remove_skill(
                self._args("keep-me-20260417", dry_run=True),
                MagicMock(),
            )
        assert target.exists()
        assert not audit_path.exists()
        out = capsys.readouterr().out
        assert "dry-run" in out
        assert "keep-me-20260417" in out

    def test_reason_required_non_empty(self, tmp_path):
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "req-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            with pytest.raises(SystemExit) as exc:
                _handle_remove_skill(
                    self._args("req-20260417", reason="   "),
                    MagicMock(),
                )
        assert exc.value.code == 2

    def test_accepts_name_with_or_without_md(self, tmp_path):
        skills_dir = tmp_path / "skills"
        target = self._make_skill(skills_dir, "ext-20260417")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            _handle_remove_skill(
                self._args("ext-20260417.md"),
                MagicMock(),
            )
        assert not target.exists()

    def test_escape_attempt_rejected(self, tmp_path):
        """Path traversal (../) must be blocked."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (tmp_path / "other.md").write_text("outside", encoding="utf-8")
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit_path):
            with pytest.raises(SystemExit) as exc:
                _handle_remove_skill(
                    self._args("../other"),
                    MagicMock(),
                )
        assert exc.value.code == 2
        assert (tmp_path / "other.md").exists()


class TestStageResults:
    """Tests for _stage_results() staging helper."""

    def test_stages_files_with_meta(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        target = tmp_path / "skills" / "test-skill.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results(
                [StageItem("test-skill.md", "# Test Skill\nContent", target)],
                command="insight",
            )
        assert (staged_dir / "test-skill.md").exists()
        assert "# Test Skill" in (staged_dir / "test-skill.md").read_text()
        meta = json.loads((staged_dir / "test-skill.md.meta.json").read_text())
        assert meta["target"] == str(target)
        assert meta["command"] == "insight"
        assert "sources" not in meta  # empty -> field omitted

    def test_stages_multiple_files(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        items = [
            StageItem("a.md", "# A", tmp_path / "skills" / "a.md"),
            StageItem("b.md", "# B", tmp_path / "skills" / "b.md"),
        ]
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results(items, command="insight")
        assert (staged_dir / "a.md").exists()
        assert (staged_dir / "b.md").exists()

    def test_rejects_path_traversal(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        evil_target = Path("/tmp/evil.md")
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results(
                [StageItem("evil.md", "pwned", evil_target)],
                command="insight",
            )
        assert not (staged_dir / "evil.md").exists()
        assert "escapes MOLTBOOK_HOME" in capsys.readouterr().err

    def test_records_stage_audit_entry(self, tmp_path):
        """_stage_results should log 'staged' entries to the audit log."""
        staged_dir = tmp_path / ".staged"
        target = tmp_path / "skills" / "a.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results(
                [StageItem("a.md", "# A", target)],
                command="insight",
            )
        assert audit.exists()
        record = json.loads(audit.read_text().strip())
        assert record["command"] == "insight"
        assert record["decision"] == "staged"
        assert record["source"] == "stage"
        assert record["path"] == str(target)

    def test_records_sources_in_meta(self, tmp_path):
        """When sources is provided (skill-stocktake merge), it lands in meta.json."""
        staged_dir = tmp_path / ".staged"
        target = tmp_path / "skills" / "merged.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results(
                [
                    StageItem(
                        "merged.md",
                        "# Merged",
                        target,
                        sources=["orig1.md", "orig2.md"],
                    )
                ],
                command="skill-stocktake",
            )
        meta = json.loads((staged_dir / "merged.md.meta.json").read_text())
        assert meta["sources"] == ["orig1.md", "orig2.md"]


class TestAdoptStaged:
    """Tests for `adopt-staged` CLI command (_handle_adopt_staged)."""

    def _stage_one(
        self,
        tmp_path,
        *,
        filename: str,
        text: str,
        target: Path,
        command: str = "insight",
        sources: list[str] | None = None,
    ) -> Path:
        """Write one staged file + meta.json for the adopt-staged tests."""
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        item = StageItem(filename, text, target, sources=list(sources or []))
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results([item], command=command)
        return staged_dir

    def _run_adopt(self, tmp_path, staged_dir, *, inputs: list[str]):
        audit = tmp_path / "logs" / "audit.jsonl"
        # MagicMock attributes return MagicMock (truthy) by default, so set
        # `yes` explicitly to exercise the interactive prompt path.
        args = MagicMock()
        args.yes = False
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit), \
             patch("builtins.input", side_effect=inputs):
            _handle_adopt_staged(args, MagicMock())

    def test_empty_staging_dir_is_noop(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        self._run_adopt(tmp_path, staged_dir, inputs=[])
        out = capsys.readouterr().out
        assert "No staged files." in out

    def test_missing_staging_dir_is_noop(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"  # does not exist
        self._run_adopt(tmp_path, staged_dir, inputs=[])
        out = capsys.readouterr().out
        assert "No staging directory." in out

    def test_approve_writes_target_and_clears_staging(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(
            tmp_path, filename="a.md", text="# A", target=target
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.exists()
        assert target.read_text().startswith("# A")
        # staging cleared
        assert not (staged / "a.md").exists()
        assert not (staged / "a.md.meta.json").exists()

    def test_reject_does_not_write_and_clears_staging(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(
            tmp_path, filename="a.md", text="# A", target=target
        )
        self._run_adopt(tmp_path, staged, inputs=["n"])
        assert not target.exists()
        # rejected items are also cleared from staging
        assert not (staged / "a.md").exists()
        assert not (staged / "a.md.meta.json").exists()

    def test_adopt_logs_audit_entry(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        staged = self._stage_one(
            tmp_path, filename="a.md", text="# A", target=target
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        lines = audit.read_text().strip().splitlines()
        # stage + stage-adopted, so >= 2 entries
        decisions = [json.loads(line) for line in lines]
        sources = [d["source"] for d in decisions]
        assert "stage" in sources
        assert "stage-adopted" in sources
        adopted = [d for d in decisions if d["source"] == "stage-adopted"]
        assert adopted[-1]["decision"] == "approved"

    def test_adopt_deletes_merge_sources(self, tmp_path):
        """skill-stocktake merge: adopting should delete the original files."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        orig1 = skills_dir / "orig1.md"
        orig2 = skills_dir / "orig2.md"
        orig1.write_text("# orig1")
        orig2.write_text("# orig2")

        target = skills_dir / "merged.md"
        staged = self._stage_one(
            tmp_path,
            filename="merged.md",
            text="# merged",
            target=target,
            command="skill-stocktake",
            sources=["orig1.md", "orig2.md"],
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.exists()
        assert not orig1.exists()
        assert not orig2.exists()

    def test_adopt_rejects_escaping_target(self, tmp_path, capsys):
        """Tampered meta.json pointing outside MOLTBOOK_HOME must be rejected."""
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        (staged_dir / "evil.md").write_text("pwned\n")
        (staged_dir / "evil.md.meta.json").write_text(
            json.dumps({"target": "/tmp/evil-adopted.md", "command": "insight"})
        )
        self._run_adopt(tmp_path, staged_dir, inputs=[])
        assert not Path("/tmp/evil-adopted.md").exists()
        captured = capsys.readouterr()
        assert "escapes MOLTBOOK_HOME" in captured.err
        # staging entries remain (skipped, not cleared)
        assert (staged_dir / "evil.md").exists()
        assert (staged_dir / "evil.md.meta.json").exists()

    def test_adopt_blocks_source_path_traversal(self, tmp_path):
        """Suspicious source filenames in meta.json must not delete arbitrary files."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # victim file outside skills/ that should NOT be deleted
        victim = tmp_path / "victim.md"
        victim.write_text("keep me")

        target = skills_dir / "merged.md"
        staged = self._stage_one(
            tmp_path,
            filename="merged.md",
            text="# merged",
            target=target,
            command="skill-stocktake",
            sources=["../victim.md"],
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.exists()
        assert victim.exists()  # traversal blocked

    def test_adopt_preserves_target_when_source_name_matches(self, tmp_path):
        """Regression: when a merged target has the same basename as one of
        its sources (e.g. merged title slugifies back to the dominant
        original's filename), the delete loop must skip that source so the
        freshly-written merge survives."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # Two original skills; the merged target name matches the first one
        (skills_dir / "a.md").write_text("# A original")
        (skills_dir / "b.md").write_text("# B original")

        target = skills_dir / "a.md"  # collides with sources[0]
        staged = self._stage_one(
            tmp_path,
            filename="a.md",
            text="# Merged\n\nnew body",
            target=target,
            command="skill-stocktake",
            sources=["a.md", "b.md"],
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        # Merged file survived (guard worked)
        assert target.exists(), "merged target deleted by self-delete bug"
        assert "Merged" in target.read_text()
        # The other (non-colliding) source is deleted
        assert not (skills_dir / "b.md").exists()


class TestSkillStocktakeDirectMerge:
    """Tests for `skill-stocktake` direct-mode merge (no --stage).

    Regression guard: the direct branch must call `_log_approval` so that
    both accepted and rejected merges are recorded in audit.jsonl, matching
    distill-identity / insight / rules-distill / amend-constitution.
    """

    def _make_result(self, filenames, text="# Merged skill body"):
        from contemplative_agent.core.stocktake import (
            MergeGroup,
            StocktakeResult,
        )

        return StocktakeResult(
            merge_groups=(MergeGroup(filenames=tuple(filenames), reason="dup"),),
            quality_issues=(),
            total_files=len(filenames),
            items=tuple((name, text) for name in filenames),
        )

    def _run_direct(self, tmp_path, inputs, *, merged_text="# Merged\n\nBody"):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "a.md").write_text("# A")
        (skills_dir / "b.md").write_text("# B")
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = False

        fake_result = self._make_result(["a.md", "b.md"])
        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.merge_group",
            return_value=merged_text,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=inputs):
            _handle_skill_stocktake(args, MagicMock())

        return skills_dir, audit

    def test_direct_approved_merge_logs_audit(self, tmp_path):
        skills_dir, audit = self._run_direct(tmp_path, inputs=["y"])
        assert audit.exists()
        record = json.loads(audit.read_text().strip())
        assert record["command"] == "skill-stocktake"
        assert record["decision"] == "approved"
        assert record["source"] == "direct"
        # Merged file written, originals deleted
        assert not (skills_dir / "a.md").exists()
        assert not (skills_dir / "b.md").exists()

    def test_direct_rejected_merge_logs_audit(self, tmp_path):
        skills_dir, audit = self._run_direct(tmp_path, inputs=["n"])
        assert audit.exists()
        record = json.loads(audit.read_text().strip())
        assert record["command"] == "skill-stocktake"
        assert record["decision"] == "rejected"
        assert record["source"] == "direct"
        # Nothing deleted on rejection
        assert (skills_dir / "a.md").exists()
        assert (skills_dir / "b.md").exists()

    def test_direct_merge_preserves_target_when_name_collides_with_source(
        self, tmp_path
    ):
        """Regression: when LLM's merged title slugifies to an existing source
        filename, target_path == sources[0]. The delete loop must not unlink
        the file we just wrote. Previously this caused total loss of merge
        output (observed 2026-04-11 during resonant-fluidity merge)."""
        from contemplative_agent.core.stocktake import MergeGroup, StocktakeResult

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "a.md").write_text("# A original")
        (skills_dir / "b.md").write_text("# B original")
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = False

        # LLM returns "# A" as title -> slug "a" -> target collides with a.md
        # The date suffix forces filename to f"a-{YYYYMMDD}.md" though, so to
        # reproduce the exact collision we patch the filename derivation via
        # the original being named identically to today's slug. Easier: use a
        # source filename that matches what slugify(title) + today produces.
        from datetime import date

        today = date.today().strftime("%Y%m%d")
        colliding = f"merged-skill-{today}.md"
        (skills_dir / colliding).write_text("# pre-existing content at collision path")

        fake_result = StocktakeResult(
            merge_groups=(
                MergeGroup(filenames=(colliding, "b.md"), reason="dup"),
            ),
            quality_issues=(),
            total_files=2,
            items=((colliding, "# X"), ("b.md", "# Y")),
        )
        # merged_text has no title -> _extract_title returns None -> slug falls
        # back to "merged-skill" -> filename becomes merged-skill-{today}.md
        # which matches `colliding`.
        merged_text = "No title here, just body prose.\n\nMore body."

        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.merge_group",
            return_value=merged_text,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=["y"]):
            _handle_skill_stocktake(args, MagicMock())

        target = skills_dir / colliding
        # Merged output survives (guard worked)
        assert target.exists(), "merge output was deleted by self-delete bug"
        assert merged_text in target.read_text()
        # Non-colliding source still deleted
        assert not (skills_dir / "b.md").exists()

    def test_direct_merge_writes_frontmatter_bearing_output(self, tmp_path):
        """Merge now emits a frontmatter block (mirroring insight). It is
        written verbatim and the filename is still derived from the title
        heading, since extract_title skips the frontmatter lines."""
        from datetime import date

        merged_text = (
            "---\n"
            "name: merged-pattern\n"
            'description: "A unified pattern"\n'
            "origin: auto-extracted\n"
            "---\n\n"
            "# Merged Pattern\n\n"
            "**Context:** When two skills overlap.\n"
        )
        skills_dir, _ = self._run_direct(
            tmp_path, inputs=["y"], merged_text=merged_text
        )

        today = date.today().strftime("%Y%m%d")
        written = skills_dir / f"merged-pattern-{today}.md"
        assert written.exists(), "filename should derive from the title heading"
        content = written.read_text()
        assert content.startswith("---")
        assert "name: merged-pattern" in content
        assert 'description: "A unified pattern"' in content
        assert "# Merged Pattern" in content


class TestSkillStocktakeCleanPhase:
    """Clean phase: skills not consumed by a merge and not flagged for drop
    get their triggers rewritten at structural altitude. Merged and dropped
    files are excluded; rules-stocktake skips the phase entirely.
    """

    def test_singleton_cleaned_direct_mode(self, tmp_path):
        from contemplative_agent.core.stocktake import StocktakeResult

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "solo.md").write_text("# Solo\n\noriginal")
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = False

        # No merges, no drops -> only the clean phase runs.
        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("solo.md", "# Solo\n\noriginal"),),
        )
        cleaned = (
            "# Solo\n\noriginal\n\n## When to Use\nWhen a particular individual acts."
        )
        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.clean_skill_triggers",
            return_value=cleaned,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=["y"]):
            _handle_skill_stocktake(args, MagicMock())

        body = (skills_dir / "solo.md").read_text()
        assert "a particular individual" in body
        # A frontmatter-less legacy skill gets a synthesized block so the
        # cleaned file is never written without metadata.
        assert body.startswith("---")
        assert "name: solo" in body
        assert "origin: auto-extracted" in body
        record = json.loads(audit.read_text().strip())
        assert record["command"] == "skill-stocktake-clean"
        assert record["decision"] == "approved"

    def test_singleton_frontmatter_preserved(self, tmp_path):
        """A cleaned singleton keeps its original frontmatter verbatim —
        name / description / origin and reflection bookkeeping survive the
        body rewrite (regression: clean must not drop frontmatter)."""
        from contemplative_agent.core.stocktake import StocktakeResult

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        original = (
            "---\n"
            "last_reflected_at: null\n"
            "success_count: 3\n"
            "failure_count: 1\n"
            "name: solo-skill\n"
            'description: "An existing description"\n'
            "origin: auto-extracted\n"
            "---\n\n"
            "# Solo\n\n"
            "**Context:** When user u_123 acts on post p_456.\n"
        )
        (skills_dir / "solo.md").write_text(original)
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = False

        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("solo.md", "# Solo\n\n**Context:** When user u_123 acts."),),
        )
        # clean_skill_triggers returns a frontmatter-stripped, rewritten body.
        # Leading newline included on purpose: the re-attach must not leave a
        # triple-blank gap under the frontmatter.
        cleaned = (
            "\n# Solo\n\n"
            "**Context:** When a particular individual acts.\n\n"
            "## When to Use\nWhen a particular individual acts on a specific topic."
        )
        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.clean_skill_triggers",
            return_value=cleaned,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=["y"]):
            _handle_skill_stocktake(args, MagicMock())

        body = (skills_dir / "solo.md").read_text()
        # Original frontmatter preserved verbatim — description NOT regenerated.
        assert body.startswith("---")
        assert "success_count: 3" in body
        assert "failure_count: 1" in body
        assert "name: solo-skill" in body
        assert 'description: "An existing description"' in body
        assert "origin: auto-extracted" in body
        # Cleaned body re-attached below the frontmatter.
        assert "a particular individual" in body
        # No triple-blank gap from a stray leading newline in the model output.
        assert "\n\n\n" not in body

    def test_frontmatter_less_singleton_synthesizes_description(self, tmp_path):
        """A frontmatter-less legacy skill gets a synthesized block whose
        description is the first sentence of its ``**Context:**`` line."""
        from contemplative_agent.core.stocktake import StocktakeResult

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "solo.md").write_text(
            "# Solo Pattern\n\n"
            "**Context:** Applies when a particular individual acts. Extra detail.\n"
        )
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = False

        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("solo.md", "# Solo Pattern\n\n**Context:** Applies when X acts."),),
        )
        cleaned = (
            "# Solo Pattern\n\n"
            "**Context:** Applies when a particular individual acts. Extra detail.\n\n"
            "## When to Use\nWhen a particular individual acts."
        )
        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.clean_skill_triggers",
            return_value=cleaned,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=["y"]):
            _handle_skill_stocktake(args, MagicMock())

        body = (skills_dir / "solo.md").read_text()
        assert body.startswith("---")
        assert "name: solo-pattern" in body
        assert "origin: auto-extracted" in body
        assert 'description: "Applies when a particular individual acts."' in body
        assert "a particular individual" in body

    def test_noop_leaves_file_untouched(self, tmp_path):
        from contemplative_agent.core.stocktake import StocktakeResult

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "solo.md").write_text("# Solo original")
        audit = tmp_path / "logs" / "audit.jsonl"
        args = MagicMock()
        args.stage = False

        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("solo.md", "# Solo original"),),
        )
        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.clean_skill_triggers",
            return_value="CLEAN_NOOP",
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch(
            "builtins.input", side_effect=AssertionError("no approval prompt expected")
        ):
            _handle_skill_stocktake(args, MagicMock())

        # CLEAN_NOOP -> no rewrite, no approval prompt, file unchanged.
        assert (skills_dir / "solo.md").read_text() == "# Solo original"

    def test_merged_and_dropped_excluded_from_clean(self, tmp_path):
        """Files consumed by a merge or flagged for drop are not cleaned."""
        from contemplative_agent.core.stocktake import (
            MergeGroup,
            QualityIssue,
            StocktakeResult,
        )

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for n in ("a.md", "b.md", "bad.md", "solo.md"):
            (skills_dir / n).write_text(f"# {n}")
        audit = tmp_path / "logs" / "audit.jsonl"
        args = MagicMock()
        args.stage = False

        fake_result = StocktakeResult(
            merge_groups=(MergeGroup(filenames=("a.md", "b.md"), reason="dup"),),
            quality_issues=(QualityIssue(filename="bad.md", reason="too short"),),
            total_files=4,
            items=(
                ("a.md", "# a"),
                ("b.md", "# b"),
                ("bad.md", "# bad"),
                ("solo.md", "# solo"),
            ),
        )
        clean_calls: list[str] = []

        def fake_clean(item, _prompt):
            clean_calls.append(item[0])
            return "CLEAN_NOOP"

        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.merge_group",
            return_value="# Merged\n\nBody",
        ), patch(
            "contemplative_agent.core.stocktake.clean_skill_triggers",
            side_effect=fake_clean,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=["y", "y"]):
            _handle_skill_stocktake(args, MagicMock())

        # a.md+b.md consumed by the merge, bad.md dropped -> only solo.md cleaned.
        assert clean_calls == ["solo.md"]

    def test_stage_mode_queues_clean_item(self, tmp_path):
        """--stage queues a clean StageItem (no live write) tagged with the
        skill-stocktake-clean command, leaving the live file untouched."""
        from contemplative_agent.core.stocktake import StocktakeResult

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "solo.md").write_text("# Solo original")
        staged = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = True

        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("solo.md", "# Solo original"),),
        )
        cleaned = "# Solo\n\n## When to Use\nWhen a particular individual acts."
        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.clean_skill_triggers",
            return_value=cleaned,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.STAGED_DIR", staged
        ), patch(
            "contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path
        ), patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _handle_skill_stocktake(args, MagicMock())

        # Live file untouched; staged copy + meta written under the clean command.
        assert (skills_dir / "solo.md").read_text() == "# Solo original"
        meta = json.loads((staged / "solo.md.meta.json").read_text())
        assert meta["command"] == "skill-stocktake-clean"
        staged_text = (staged / "solo.md").read_text()
        # Synthesized frontmatter now leads the staged body.
        assert staged_text.startswith("---")
        assert "# Solo" in staged_text

    def test_rules_stocktake_skips_clean(self, tmp_path):
        from contemplative_agent.core.stocktake import StocktakeResult

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "r.md").write_text("# Rule")
        audit = tmp_path / "logs" / "audit.jsonl"
        args = MagicMock()
        args.stage = False

        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("r.md", "# Rule"),),
        )
        with patch(
            "contemplative_agent.core.stocktake.run_rules_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.clean_skill_triggers",
        ) as mock_clean, patch(
            "contemplative_agent.cli.RULES_DIR", rules_dir
        ), patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _handle_rules_stocktake(args, MagicMock())

        mock_clean.assert_not_called()


class TestRulesStocktakeDirectMerge:
    """Tests for `rules-stocktake` direct-mode merge (no --stage).

    Mirrors TestSkillStocktakeDirectMerge. rules-stocktake previously had
    no merge implementation (only report). This class exists as both a
    feature test and regression guard against future divergence from
    skill-stocktake's merge semantics (audit logging + self-delete guard).
    """

    def _make_result(self, filenames, text="# Merged rule body"):
        from contemplative_agent.core.stocktake import (
            MergeGroup,
            StocktakeResult,
        )

        return StocktakeResult(
            merge_groups=(MergeGroup(filenames=tuple(filenames), reason="dup"),),
            quality_issues=(),
            total_files=len(filenames),
            items=tuple((name, text) for name in filenames),
        )

    def _run_direct(self, tmp_path, inputs, *, merged_text="# Merged\n\nbody"):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "a.md").write_text("# A")
        (rules_dir / "b.md").write_text("# B")
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = False

        fake_result = self._make_result(["a.md", "b.md"])
        with patch(
            "contemplative_agent.core.stocktake.run_rules_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.merge_group",
            return_value=merged_text,
        ), patch("contemplative_agent.cli.RULES_DIR", rules_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=inputs):
            _handle_rules_stocktake(args, MagicMock())

        return rules_dir, audit

    def test_direct_approved_merge_logs_audit(self, tmp_path):
        rules_dir, audit = self._run_direct(tmp_path, inputs=["y"])
        assert audit.exists()
        record = json.loads(audit.read_text().strip())
        assert record["command"] == "rules-stocktake"
        assert record["decision"] == "approved"
        assert record["source"] == "direct"
        assert not (rules_dir / "a.md").exists()
        assert not (rules_dir / "b.md").exists()

    def test_direct_rejected_merge_logs_audit(self, tmp_path):
        rules_dir, audit = self._run_direct(tmp_path, inputs=["n"])
        assert audit.exists()
        record = json.loads(audit.read_text().strip())
        assert record["command"] == "rules-stocktake"
        assert record["decision"] == "rejected"
        assert record["source"] == "direct"
        # Nothing deleted on rejection
        assert (rules_dir / "a.md").exists()
        assert (rules_dir / "b.md").exists()

    def test_direct_merge_preserves_target_when_name_collides_with_source(
        self, tmp_path
    ):
        """Regression: same self-delete bug that hit skill-stocktake
        (commit 542f0b2). When the merged rule title slugifies to the
        name of one of the source rules, the delete loop must not unlink
        the file we just wrote."""
        from contemplative_agent.core.stocktake import MergeGroup, StocktakeResult
        from datetime import date

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        audit = tmp_path / "logs" / "audit.jsonl"

        today = date.today().strftime("%Y%m%d")
        colliding = f"merged-rule-{today}.md"
        (rules_dir / colliding).write_text("# pre-existing content")
        (rules_dir / "b.md").write_text("# B original")

        args = MagicMock()
        args.stage = False

        fake_result = StocktakeResult(
            merge_groups=(
                MergeGroup(filenames=(colliding, "b.md"), reason="dup"),
            ),
            quality_issues=(),
            total_files=2,
            items=((colliding, "# X"), ("b.md", "# Y")),
        )
        # No title in merged_text -> _extract_title returns None ->
        # slug falls back to "merged-rule" -> filename matches `colliding`.
        merged_text = "No title here, just rule body prose.\n\nMore body."

        with patch(
            "contemplative_agent.core.stocktake.run_rules_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.merge_group",
            return_value=merged_text,
        ), patch("contemplative_agent.cli.RULES_DIR", rules_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=["y"]):
            _handle_rules_stocktake(args, MagicMock())

        target = rules_dir / colliding
        assert target.exists(), "merge output was deleted by self-delete bug"
        assert merged_text in target.read_text()
        assert not (rules_dir / "b.md").exists()


# ---- Drop feature tests ----


class TestStageItemAction:
    """StageItem.action field tests."""

    def test_default_action_is_merge(self):
        item = StageItem("a.md", "# A", Path("/tmp/a.md"))
        assert item.action == "merge"

    def test_drop_action(self):
        item = StageItem("a.md", "# A", Path("/tmp/a.md"), action="drop")
        assert item.action == "drop"


class TestStageResultsDropAction:
    """Drop items in _stage_results should record action in meta.json."""

    def test_stages_drop_item_with_action_in_meta(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        target = tmp_path / "skills" / "low-quality.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results(
                [StageItem("low-quality.md", "# LQ", target, action="drop")],
                command="skill-stocktake-drop",
            )
        meta = json.loads((staged_dir / "low-quality.md.meta.json").read_text())
        assert meta["action"] == "drop"
        assert meta["command"] == "skill-stocktake-drop"
        assert "sources" not in meta

    def test_merge_item_omits_action_key(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        target = tmp_path / "skills" / "merged.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results(
                [StageItem("merged.md", "# M", target)],
                command="skill-stocktake",
            )
        meta = json.loads((staged_dir / "merged.md.meta.json").read_text())
        assert "action" not in meta


class TestApproveDelete:
    """Tests for _approve_delete helper."""

    def test_approve_on_y(self):
        with patch("builtins.input", return_value="y"):
            assert _approve_delete(Path("/tmp/x.md")) is True

    def test_reject_on_n(self):
        with patch("builtins.input", return_value="n"):
            assert _approve_delete(Path("/tmp/x.md")) is False

    def test_reject_on_empty(self):
        with patch("builtins.input", return_value=""):
            assert _approve_delete(Path("/tmp/x.md")) is False

    def test_reject_on_eof(self):
        with patch("builtins.input", side_effect=EOFError):
            assert _approve_delete(Path("/tmp/x.md")) is False


class TestAdoptStagedDrop:
    """Tests for adopt-staged handling of drop actions."""

    def _stage_one(
        self,
        tmp_path,
        *,
        filename: str,
        text: str,
        target: Path,
        command: str = "skill-stocktake-drop",
        action: Literal["merge", "drop"] = "drop",
    ) -> Path:
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        item = StageItem(filename, text, target, action=action)
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results([item], command=command)
        return staged_dir

    def _run_adopt(self, tmp_path, staged_dir, *, inputs: list[str]):
        audit = tmp_path / "logs" / "audit.jsonl"
        args = MagicMock()
        args.yes = False
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit), \
             patch("builtins.input", side_effect=inputs):
            _handle_adopt_staged(args, MagicMock())

    def test_adopt_drop_approved_deletes_target(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "low-quality.md"
        target.write_text("# Low quality skill\nshort")

        staged = self._stage_one(
            tmp_path, filename="low-quality.md", text="# Low quality skill\nshort",
            target=target,
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert not target.exists(), "target should be deleted on drop approval"

    def test_adopt_drop_rejected_keeps_target(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "low-quality.md"
        target.write_text("# Low quality skill\nshort")

        staged = self._stage_one(
            tmp_path, filename="low-quality.md", text="# Low quality skill\nshort",
            target=target,
        )
        self._run_adopt(tmp_path, staged, inputs=["n"])
        assert target.exists(), "target should be kept on drop rejection"

    def test_adopt_drop_logs_audit(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "low-quality.md"
        target.write_text("# LQ")

        audit = tmp_path / "logs" / "audit.jsonl"
        staged = self._stage_one(
            tmp_path, filename="low-quality.md", text="# LQ", target=target,
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])

        lines = audit.read_text().strip().splitlines()
        decisions = [json.loads(line) for line in lines]
        adopted = [d for d in decisions if d["source"] == "stage-adopted"]
        assert len(adopted) >= 1
        assert adopted[-1]["decision"] == "approved"
        assert adopted[-1]["command"] == "skill-stocktake-drop"

    def test_adopt_drop_already_absent_is_noop(self, tmp_path):
        """Drop of non-existent file should not error."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "gone.md"  # does not exist

        staged = self._stage_one(
            tmp_path, filename="gone.md", text="# Ghost", target=target,
        )
        # Should not raise
        self._run_adopt(tmp_path, staged, inputs=["y"])

    def test_adopt_mixed_merge_and_drop(self, tmp_path):
        """Merge + drop items coexist in the same staging batch."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        merge_target = skills_dir / "merged.md"
        drop_target = skills_dir / "low-q.md"
        drop_target.write_text("# low quality")

        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        merge_item = StageItem("merged.md", "# Merged body", merge_target)
        drop_item = StageItem(
            "low-q.md",
            "# low quality",
            drop_target,
            action="drop",
            command="skill-stocktake-drop",
        )
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit):
            _stage_results([merge_item, drop_item], command="skill-stocktake")

        self._run_adopt(tmp_path, staged_dir, inputs=["y", "y"])
        assert merge_target.exists(), "merged file should be written"
        assert not drop_target.exists(), "drop target should be deleted"


class TestAdoptStagedYesFlag:
    """Tests for `adopt-staged --yes` non-interactive auto-approval.

    Coding agents (Claude Code, etc.) run the CLI in a non-TTY bash sandbox
    where `input()` returns EOF and rejects everything. The `--yes` flag
    skips the prompts entirely and records adoptions in the audit log with
    `source="stage-adopted-auto"` so they can be distinguished from
    interactively reviewed adoptions.
    """

    def _run_adopt_yes(self, tmp_path, staged_dir):
        audit = tmp_path / "logs" / "audit.jsonl"
        args = MagicMock()
        args.yes = True
        # Patch input() with a sentinel that fails the test if called.
        # If --yes works correctly, the prompt path should never run.
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch("contemplative_agent.cli.AUDIT_LOG_PATH", audit), \
             patch("builtins.input") as mock_input:
            _handle_adopt_staged(args, MagicMock())
            mock_input.assert_not_called()

    def test_yes_flag_approves_merge_without_prompt(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        staged_dir = tmp_path / ".staged"
        item = StageItem("a.md", "# Auto-approved A", target)
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch(
                 "contemplative_agent.cli.AUDIT_LOG_PATH",
                 tmp_path / "logs" / "audit.jsonl",
             ):
            _stage_results([item], command="insight")

        self._run_adopt_yes(tmp_path, staged_dir)

        assert target.exists()
        assert target.read_text().startswith("# Auto-approved A")
        # staging cleared
        assert not (staged_dir / "a.md").exists()
        assert not (staged_dir / "a.md.meta.json").exists()

        # Audit log records the adoption with the auto source value
        audit_lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().splitlines()
        decisions = [json.loads(line) for line in audit_lines]
        adopted = [d for d in decisions if d["source"] == "stage-adopted-auto"]
        assert len(adopted) == 1
        assert adopted[0]["decision"] == "approved"
        assert adopted[0]["command"] == "insight"

    def test_yes_flag_approves_drop_without_prompt(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "low-quality.md"
        target.write_text("# low quality body")
        staged_dir = tmp_path / ".staged"
        item = StageItem(
            "low-quality.md",
            "# low quality body",
            target,
            action="drop",
            command="skill-stocktake-drop",
        )
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch(
                 "contemplative_agent.cli.AUDIT_LOG_PATH",
                 tmp_path / "logs" / "audit.jsonl",
             ):
            _stage_results([item], command="skill-stocktake")

        self._run_adopt_yes(tmp_path, staged_dir)

        assert not target.exists(), "drop target should be deleted under --yes"
        assert not (staged_dir / "low-quality.md.meta.json").exists()

        audit_lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().splitlines()
        decisions = [json.loads(line) for line in audit_lines]
        adopted = [d for d in decisions if d["source"] == "stage-adopted-auto"]
        assert len(adopted) == 1
        assert adopted[0]["decision"] == "approved"
        assert adopted[0]["command"] == "skill-stocktake-drop"

    def test_yes_flag_approves_mixed_merge_and_drop(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        merge_target = skills_dir / "merged.md"
        drop_target = skills_dir / "low-q.md"
        drop_target.write_text("# low quality")
        staged_dir = tmp_path / ".staged"

        merge_item = StageItem("merged.md", "# Merged body", merge_target)
        drop_item = StageItem(
            "low-q.md",
            "# low quality",
            drop_target,
            action="drop",
            command="skill-stocktake-drop",
        )
        with patch("contemplative_agent.cli.STAGED_DIR", staged_dir), \
             patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), \
             patch(
                 "contemplative_agent.cli.AUDIT_LOG_PATH",
                 tmp_path / "logs" / "audit.jsonl",
             ):
            _stage_results([merge_item, drop_item], command="skill-stocktake")

        self._run_adopt_yes(tmp_path, staged_dir)

        assert merge_target.exists(), "merge should be written under --yes"
        assert not drop_target.exists(), "drop should be deleted under --yes"
        # staging fully cleared
        assert list(staged_dir.glob("*.meta.json")) == []

        audit_lines = (tmp_path / "logs" / "audit.jsonl").read_text().strip().splitlines()
        decisions = [json.loads(line) for line in audit_lines]
        adopted = [d for d in decisions if d["source"] == "stage-adopted-auto"]
        assert len(adopted) == 2
        commands = sorted(d["command"] for d in adopted)
        assert commands == ["skill-stocktake", "skill-stocktake-drop"]
        assert all(d["decision"] == "approved" for d in adopted)


class TestSkillStocktakeDirectDrop:
    """Tests for skill-stocktake direct-mode drop (quality issue deletion)."""

    def _make_result_with_quality_issues(self, quality_files, body="short"):
        from contemplative_agent.core.stocktake import QualityIssue, StocktakeResult

        return StocktakeResult(
            merge_groups=(),
            quality_issues=tuple(
                QualityIssue(filename=f, reason="body < 200 chars")
                for f in quality_files
            ),
            total_files=len(quality_files),
            items=tuple((f, body) for f in quality_files),
        )

    def _run_direct_drop(self, tmp_path, inputs, *, quality_files=("lq.md",)):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for f in quality_files:
            (skills_dir / f).write_text("# short")
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = False

        fake_result = self._make_result_with_quality_issues(quality_files)
        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=inputs):
            _handle_skill_stocktake(args, MagicMock())

        return skills_dir, audit

    def test_direct_drop_approved_deletes_file(self, tmp_path):
        skills_dir, audit = self._run_direct_drop(tmp_path, inputs=["y"])
        assert not (skills_dir / "lq.md").exists()

    def test_direct_drop_rejected_keeps_file(self, tmp_path):
        skills_dir, audit = self._run_direct_drop(tmp_path, inputs=["n"])
        assert (skills_dir / "lq.md").exists()

    def test_direct_drop_logs_audit(self, tmp_path):
        skills_dir, audit = self._run_direct_drop(tmp_path, inputs=["y"])
        assert audit.exists()
        record = json.loads(audit.read_text().strip())
        assert record["command"] == "skill-stocktake-drop"
        assert record["decision"] == "approved"
        assert record["source"] == "direct"

    def test_staged_drop_creates_staging_entry(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "lq.md").write_text("# short")
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = True

        fake_result = self._make_result_with_quality_issues(["lq.md"])
        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.STAGED_DIR", staged_dir
        ), patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ):
            _handle_skill_stocktake(args, MagicMock())

        meta = json.loads((staged_dir / "lq.md.meta.json").read_text())
        assert meta["command"] == "skill-stocktake-drop"
        assert meta["action"] == "drop"


class TestRulesStocktakeDirectDrop:
    """Tests for rules-stocktake direct-mode drop (quality issue deletion)."""

    def _make_result_with_quality_issues(self, quality_files, body="short"):
        from contemplative_agent.core.stocktake import QualityIssue, StocktakeResult

        return StocktakeResult(
            merge_groups=(),
            quality_issues=tuple(
                QualityIssue(filename=f, reason='missing "**Practice:**" section')
                for f in quality_files
            ),
            total_files=len(quality_files),
            items=tuple((f, body) for f in quality_files),
        )

    def _run_direct_drop(self, tmp_path, inputs, *, quality_files=("old-rule.md",)):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        for f in quality_files:
            (rules_dir / f).write_text("# old rule without Practice/Rationale")
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = False

        fake_result = self._make_result_with_quality_issues(quality_files)
        with patch(
            "contemplative_agent.core.stocktake.run_rules_stocktake",
            return_value=fake_result,
        ), patch("contemplative_agent.cli.RULES_DIR", rules_dir), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ), patch("builtins.input", side_effect=inputs):
            _handle_rules_stocktake(args, MagicMock())

        return rules_dir, audit

    def test_direct_drop_approved_deletes_file(self, tmp_path):
        rules_dir, audit = self._run_direct_drop(tmp_path, inputs=["y"])
        assert not (rules_dir / "old-rule.md").exists()

    def test_direct_drop_rejected_keeps_file(self, tmp_path):
        rules_dir, audit = self._run_direct_drop(tmp_path, inputs=["n"])
        assert (rules_dir / "old-rule.md").exists()

    def test_direct_drop_logs_audit(self, tmp_path):
        rules_dir, audit = self._run_direct_drop(tmp_path, inputs=["y"])
        assert audit.exists()
        record = json.loads(audit.read_text().strip())
        assert record["command"] == "rules-stocktake-drop"
        assert record["decision"] == "approved"
        assert record["source"] == "direct"

    def test_staged_drop_creates_staging_entry(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "old-rule.md").write_text("# old")
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = True

        fake_result = self._make_result_with_quality_issues(["old-rule.md"])
        with patch(
            "contemplative_agent.core.stocktake.run_rules_stocktake",
            return_value=fake_result,
        ), patch("contemplative_agent.cli.RULES_DIR", rules_dir), patch(
            "contemplative_agent.cli.STAGED_DIR", staged_dir
        ), patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ):
            _handle_rules_stocktake(args, MagicMock())

        meta = json.loads((staged_dir / "old-rule.md.meta.json").read_text())
        assert meta["command"] == "rules-stocktake-drop"
        assert meta["action"] == "drop"


class TestStocktakeStageMergeAndDropCoexist:
    """Regression: when both merge_groups and quality_issues are present
    and --stage is set, all items must survive in STAGED_DIR.

    Previous bug: _handle_*_stocktake called _stage_results twice (once
    for merges, once for drops). _stage_results wipes STAGED_DIR on every
    call, so the second call erased the first batch — losing the merges.
    Fix: build a single staged_batch list and call _stage_results once.
    """

    def _make_mixed_result(self, merge_files, quality_files, body="x" * 250):
        from contemplative_agent.core.stocktake import (
            MergeGroup,
            QualityIssue,
            StocktakeResult,
        )

        return StocktakeResult(
            merge_groups=(
                MergeGroup(filenames=tuple(merge_files), reason="dup"),
            ),
            quality_issues=tuple(
                QualityIssue(filename=f, reason="missing section")
                for f in quality_files
            ),
            total_files=len(merge_files) + len(quality_files),
            items=tuple(
                (f, body) for f in (*merge_files, *quality_files)
            ),
        )

    def test_skill_stage_merge_and_drop_both_survive(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for f in ("a.md", "b.md", "lq.md"):
            (skills_dir / f).write_text("# body")
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = True

        fake_result = self._make_mixed_result(
            merge_files=("a.md", "b.md"),
            quality_files=("lq.md",),
        )
        merged_text = "# Merged Skill\n\n## Problem\nx\n\n## Solution\ny\n"

        with patch(
            "contemplative_agent.core.stocktake.run_skill_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.merge_group",
            return_value=merged_text,
        ), patch("contemplative_agent.cli.SKILLS_DIR", skills_dir), patch(
            "contemplative_agent.cli.STAGED_DIR", staged_dir
        ), patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ):
            _handle_skill_stocktake(args, MagicMock())

        meta_files = sorted(staged_dir.glob("*.meta.json"))
        assert len(meta_files) == 2, (
            f"expected 2 staged items (1 merge + 1 drop), got {len(meta_files)}: "
            f"{[p.name for p in meta_files]}"
        )

        commands = sorted(
            json.loads(p.read_text())["command"] for p in meta_files
        )
        assert commands == ["skill-stocktake", "skill-stocktake-drop"]

        # The drop meta should be for lq.md and carry action="drop"
        drop_meta = json.loads((staged_dir / "lq.md.meta.json").read_text())
        assert drop_meta["action"] == "drop"
        assert drop_meta["command"] == "skill-stocktake-drop"

    def test_rules_stage_merge_and_drop_both_survive(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        for f in ("a.md", "b.md", "lq.md"):
            (rules_dir / f).write_text("# body")
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"

        args = MagicMock()
        args.stage = True

        fake_result = self._make_mixed_result(
            merge_files=("a.md", "b.md"),
            quality_files=("lq.md",),
        )
        merged_text = (
            "# Merged Rule\n\n**Practice:** do x\n\n**Rationale:** because y\n"
        )

        with patch(
            "contemplative_agent.core.stocktake.run_rules_stocktake",
            return_value=fake_result,
        ), patch(
            "contemplative_agent.core.stocktake.merge_group",
            return_value=merged_text,
        ), patch("contemplative_agent.cli.RULES_DIR", rules_dir), patch(
            "contemplative_agent.cli.STAGED_DIR", staged_dir
        ), patch("contemplative_agent.cli.MOLTBOOK_DATA_DIR", tmp_path), patch(
            "contemplative_agent.cli.AUDIT_LOG_PATH", audit
        ):
            _handle_rules_stocktake(args, MagicMock())

        meta_files = sorted(staged_dir.glob("*.meta.json"))
        assert len(meta_files) == 2, (
            f"expected 2 staged items (1 merge + 1 drop), got {len(meta_files)}: "
            f"{[p.name for p in meta_files]}"
        )

        commands = sorted(
            json.loads(p.read_text())["command"] for p in meta_files
        )
        assert commands == ["rules-stocktake", "rules-stocktake-drop"]

        drop_meta = json.loads((staged_dir / "lq.md.meta.json").read_text())
        assert drop_meta["action"] == "drop"
        assert drop_meta["command"] == "rules-stocktake-drop"



class TestDialogueCommand:
    """Validation logic for the `dialogue` subcommand."""

    @pytest.fixture
    def patched_production(self, tmp_path):
        """Point _PRODUCTION_HOME at an unused tmp path so tests never collide with real production."""
        with patch("contemplative_agent.cli._PRODUCTION_HOME", tmp_path / "nowhere"):
            yield

    @staticmethod
    def _init_home(path: Path) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        (path / "identity.md").write_text("test identity\n", encoding="utf-8")
        return path

    @staticmethod
    def _args(home_a: Path, home_b: Path, *, turns: int = 3, seed: str = "hello"):
        import argparse
        return argparse.Namespace(home_a=home_a, home_b=home_b, turns=turns, seed=seed)

    def test_rejects_production_home(self, tmp_path, capsys):
        fake_prod = tmp_path / "fake-prod"
        fake_prod.mkdir()
        home_under_prod = fake_prod / "a"
        self._init_home(home_under_prod)
        home_b = self._init_home(tmp_path / "b")

        with patch("contemplative_agent.cli._PRODUCTION_HOME", fake_prod.resolve()):
            with pytest.raises(SystemExit):
                _handle_dialogue(self._args(home_under_prod, home_b), MagicMock())
        assert "overlaps with production" in capsys.readouterr().err

    def test_rejects_missing_home(self, tmp_path, capsys, patched_production):
        home_a = tmp_path / "does-not-exist"
        home_b = self._init_home(tmp_path / "b")
        with pytest.raises(SystemExit):
            _handle_dialogue(self._args(home_a, home_b), MagicMock())
        assert "does not exist" in capsys.readouterr().err

    def test_rejects_home_without_identity(self, tmp_path, capsys, patched_production):
        home_a = tmp_path / "a"
        home_a.mkdir()
        home_b = self._init_home(tmp_path / "b")
        with pytest.raises(SystemExit):
            _handle_dialogue(self._args(home_a, home_b), MagicMock())
        assert "identity.md" in capsys.readouterr().err

    def test_rejects_zero_turns(self, tmp_path, capsys, patched_production):
        home_a = self._init_home(tmp_path / "a")
        home_b = self._init_home(tmp_path / "b")
        with pytest.raises(SystemExit):
            _handle_dialogue(self._args(home_a, home_b, turns=0), MagicMock())
        assert "--turns" in capsys.readouterr().err

    def test_rejects_empty_seed(self, tmp_path, capsys, patched_production):
        home_a = self._init_home(tmp_path / "a")
        home_b = self._init_home(tmp_path / "b")
        with pytest.raises(SystemExit):
            _handle_dialogue(self._args(home_a, home_b, seed="   "), MagicMock())
        assert "--seed" in capsys.readouterr().err

    def test_spawns_two_peers_and_waits(self, tmp_path, patched_production):
        home_a = self._init_home(tmp_path / "a")
        home_b = self._init_home(tmp_path / "b")

        fake_proc = MagicMock()
        fake_proc.wait.return_value = 0
        with patch("contemplative_agent.cli.subprocess.Popen", return_value=fake_proc) as popen, \
             patch("contemplative_agent.cli.os.pipe", return_value=(1000, 1001)), \
             patch("contemplative_agent.cli.os.close"):
            _handle_dialogue(self._args(home_a, home_b), MagicMock())

        assert popen.call_count == 2
        env_a = popen.call_args_list[0].kwargs["env"]
        env_b = popen.call_args_list[1].kwargs["env"]
        assert env_a["MOLTBOOK_HOME"] == str(home_a.resolve())
        assert env_b["MOLTBOOK_HOME"] == str(home_b.resolve())
        # Initiator (A) carries the seed, responder (B) does not.
        cmd_a = popen.call_args_list[0].args[0]
        cmd_b = popen.call_args_list[1].args[0]
        assert "--seed" in cmd_a
        assert "--seed" not in cmd_b
        # Default peer module is the main CLI.
        assert "contemplative_agent.cli" in cmd_a
        assert "contemplative_agent.cli" in cmd_b

    def test_peer_module_env_override(self, tmp_path, patched_production, monkeypatch):
        """CONTEMPLATIVE_DIALOGUE_PEER_MODULE redirects peer spawn to a wrapper module."""
        home_a = self._init_home(tmp_path / "a")
        home_b = self._init_home(tmp_path / "b")

        monkeypatch.setenv(
            "CONTEMPLATIVE_DIALOGUE_PEER_MODULE",
            "some_wrapper_pkg.cli",
        )

        fake_proc = MagicMock()
        fake_proc.wait.return_value = 0
        with patch("contemplative_agent.cli.subprocess.Popen", return_value=fake_proc) as popen, \
             patch("contemplative_agent.cli.os.pipe", return_value=(1000, 1001)), \
             patch("contemplative_agent.cli.os.close"):
            _handle_dialogue(self._args(home_a, home_b), MagicMock())

        for call in popen.call_args_list:
            cmd = call.args[0]
            assert "some_wrapper_pkg.cli" in cmd
            assert "contemplative_agent.cli" not in cmd
