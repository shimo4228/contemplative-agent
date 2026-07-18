"""Session subcommand CLI tests (cli/session_cmds.py): init/report/meditate/dialogue/sync.

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli import main
from contemplative_agent.cli.session_cmds import _do_init, _handle_dialogue, _list_templates



class TestSyncDataSmoke:
    """F7: argv parse → dispatch → _handle_sync_data → _run_sync wiring.

    The shell script boundary (subprocess.run) is mocked so no real sync runs.
    """

    @patch("pathlib.Path.exists", return_value=True)
    @patch("contemplative_agent.cli.session_cmds.subprocess.run")
    def test_sync_data_runs_clean(self, mock_run, _mock_exists, capsys):
        mock_run.return_value = MagicMock(returncode=0, stdout="synced", stderr="")

        with patch("sys.argv", ["contemplative-agent", "sync-data"]):
            main()  # must not raise / exit non-zero

        # Path.exists is forced True so the subprocess boundary is always
        # exercised regardless of cwd / checkout layout — proves the full
        # argv → _handle_sync_data → _run_sync → subprocess.run wiring.
        mock_run.assert_called_once()
        assert "synced" in capsys.readouterr().out


class TestGenerateReportSmoke:
    """F7: argv parse → Tier-2 config → _handle_generate_report wiring."""

    @patch("contemplative_agent.core.report.generate_report")
    def test_generate_report_single_date(self, mock_gen, capsys):
        mock_gen.return_value = Path("/tmp/report.md")

        with patch("sys.argv", ["contemplative-agent", "generate-report", "--date", "2026-06-23"]):
            main()

        mock_gen.assert_called_once()
        assert "Report generated" in capsys.readouterr().out

    @patch("contemplative_agent.core.report.generate_all_reports")
    def test_generate_report_all_dates(self, mock_gen_all, capsys):
        mock_gen_all.return_value = [Path("/tmp/a.md"), Path("/tmp/b.md")]

        with patch("sys.argv", ["contemplative-agent", "generate-report", "--all"]):
            main()

        mock_gen_all.assert_called_once()
        assert "Generated 2 reports" in capsys.readouterr().out


class TestReportPatternsSmoke:
    """report --patterns: argv → Tier-2 config → pattern-instrument wiring."""

    @patch("contemplative_agent.core.view_metrics.format_pattern_report")
    @patch("contemplative_agent.cli.memory_cmds._load_view_registry")
    @patch("contemplative_agent.core.memory.KnowledgeStore")
    @patch("contemplative_agent.core.metrics.format_report")
    @patch("contemplative_agent.core.metrics.compute_metrics")
    def test_report_patterns_flag_appends_composition(
        self,
        _mock_metrics,
        mock_fmt,
        mock_ks,
        _mock_reg,
        mock_pattern_report,
        capsys,
    ):
        mock_fmt.return_value = "SESSION-METRICS"
        mock_ks.return_value.get_live_patterns.return_value = []
        mock_pattern_report.return_value = "PATTERN-COMPOSITION"

        with patch("sys.argv", ["contemplative-agent", "report", "--patterns"]):
            main()

        out = capsys.readouterr().out
        assert "SESSION-METRICS" in out
        assert "PATTERN-COMPOSITION" in out
        mock_pattern_report.assert_called_once()

    @patch("contemplative_agent.core.view_metrics.format_pattern_report")
    @patch("contemplative_agent.core.metrics.format_report")
    @patch("contemplative_agent.core.metrics.compute_metrics")
    def test_report_without_flag_skips_instruments(
        self,
        _mock_metrics,
        mock_fmt,
        mock_pattern_report,
        capsys,
    ):
        mock_fmt.return_value = "SESSION-METRICS"

        with patch("sys.argv", ["contemplative-agent", "report"]):
            main()

        assert "SESSION-METRICS" in capsys.readouterr().out
        mock_pattern_report.assert_not_called()


class TestReportSkillSelectionSmoke:
    """report --skill-selection: argv → shadow-selection reading wiring (ADR-0076)."""

    @patch("contemplative_agent.core.skill_selection.format_skill_selection_report")
    @patch("contemplative_agent.core.skill_selection.read_skill_selection_log")
    @patch("contemplative_agent.core.metrics.format_report")
    @patch("contemplative_agent.core.metrics.compute_metrics")
    def test_report_skill_selection_flag_appends_reading(
        self,
        _mock_metrics,
        mock_fmt,
        mock_read,
        mock_sel_report,
        capsys,
    ):
        mock_fmt.return_value = "SESSION-METRICS"
        mock_sel_report.return_value = "SKILL-SELECTION-READING"

        with patch("sys.argv", ["contemplative-agent", "report", "--skill-selection"]):
            main()

        out = capsys.readouterr().out
        assert "SESSION-METRICS" in out
        assert "SKILL-SELECTION-READING" in out
        mock_read.assert_called_once()

    @patch("contemplative_agent.core.skill_selection.read_skill_selection_log")
    @patch("contemplative_agent.core.metrics.format_report")
    @patch("contemplative_agent.core.metrics.compute_metrics")
    def test_report_without_flag_skips_selection_reading(
        self,
        _mock_metrics,
        mock_fmt,
        mock_read,
        capsys,
    ):
        mock_fmt.return_value = "SESSION-METRICS"

        with patch("sys.argv", ["contemplative-agent", "report"]):
            main()

        assert "SESSION-METRICS" in capsys.readouterr().out
        mock_read.assert_not_called()

    @patch("contemplative_agent.core.skill_selection.read_skill_selection_log")
    @patch("contemplative_agent.core.metrics.format_report")
    @patch("contemplative_agent.core.metrics.compute_metrics")
    def test_reading_failure_degrades_to_warning(
        self,
        _mock_metrics,
        mock_fmt,
        mock_read,
        capsys,
        caplog,
    ):
        # A broken instrument must not break the report that hosts it.
        mock_fmt.return_value = "SESSION-METRICS"
        mock_read.side_effect = OSError("boom")

        with (
            patch("sys.argv", ["contemplative-agent", "report", "--skill-selection"]),
            caplog.at_level(logging.WARNING),
        ):
            main()

        assert "SESSION-METRICS" in capsys.readouterr().out
        assert any("skill-selection" in r.message.lower() for r in caplog.records)


class TestMeditateSmoke:
    """F7: argv parse → Tier-2 config → _handle_meditate wiring.

    The active-inference math (POMDP build / meditate / interpret) is mocked;
    this verifies only that the subcommand parses and dispatches.
    """

    @patch("contemplative_agent.adapters.meditation.report.interpret_and_save")
    @patch("contemplative_agent.adapters.meditation.meditate.meditate")
    @patch("contemplative_agent.adapters.meditation.pomdp.build_matrices")
    def test_meditate_dry_run(self, mock_build, mock_meditate, mock_interpret, capsys):
        mock_build.return_value = MagicMock()
        mock_meditate.return_value = MagicMock()
        mock_interpret.return_value = "meditation summary"

        with patch(
            "sys.argv",
            ["contemplative-agent", "meditate", "--days", "1", "--cycles", "1", "--dry-run"],
        ):
            main()

        mock_build.assert_called_once()
        mock_meditate.assert_called_once()
        mock_interpret.assert_called_once()
        assert "meditation summary" in capsys.readouterr().out


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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.adapters.moltbook.config.IDENTITY_PATH",
                tmp_path / "identity.md",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.KNOWLEDGE_PATH",
                tmp_path / "knowledge.json",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.CONSTITUTION_DIR",
                tmp_path / "constitution",
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", tmp_path / "skills"),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", tmp_path / "rules"),
        ):
            _do_init()

        assert (tmp_path / "identity.md").exists()
        assert (tmp_path / "knowledge.json").exists()
        assert (tmp_path / "constitution").is_dir()
        assert (tmp_path / "skills").is_dir()
        assert (tmp_path / "rules").is_dir()
        # Knowledge is always empty array
        assert json.loads((tmp_path / "knowledge.json").read_text()) == []

    def test_custom_template(self, tmp_path):
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.adapters.moltbook.config.IDENTITY_PATH",
                tmp_path / "identity.md",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.KNOWLEDGE_PATH",
                tmp_path / "knowledge.json",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.CONSTITUTION_DIR",
                tmp_path / "constitution",
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", tmp_path / "skills"),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", tmp_path / "rules"),
        ):
            _do_init(template_name="stoic")

        identity = (tmp_path / "identity.md").read_text()
        assert len(identity) > 1  # Not empty — copied from template

    def test_invalid_template(self, tmp_path):
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.adapters.moltbook.config.IDENTITY_PATH",
                tmp_path / "identity.md",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.KNOWLEDGE_PATH",
                tmp_path / "knowledge.json",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.CONSTITUTION_DIR",
                tmp_path / "constitution",
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", tmp_path / "skills"),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", tmp_path / "rules"),
        ):
            with pytest.raises(SystemExit):
                _do_init(template_name="nonexistent")

    def test_skips_existing(self, tmp_path, capsys):
        identity = tmp_path / "identity.md"
        identity.write_text("existing identity")
        constitution = tmp_path / "constitution"
        constitution.mkdir()

        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.adapters.moltbook.config.IDENTITY_PATH", identity),
            patch(
                "contemplative_agent.adapters.moltbook.config.KNOWLEDGE_PATH",
                tmp_path / "knowledge.json",
            ),
            patch("contemplative_agent.adapters.moltbook.config.CONSTITUTION_DIR", constitution),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", tmp_path / "skills"),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", tmp_path / "rules"),
        ):
            _do_init()

        # Identity should not be overwritten
        assert identity.read_text() == "existing identity"
        out = capsys.readouterr().out
        assert "already exists" in out

    def test_copies_prompts_and_views_from_config(self, tmp_path):
        """`init` materialises all LLM-facing Markdown files under MOLTBOOK_HOME."""
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.adapters.moltbook.config.IDENTITY_PATH",
                tmp_path / "identity.md",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.KNOWLEDGE_PATH",
                tmp_path / "knowledge.json",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.CONSTITUTION_DIR",
                tmp_path / "constitution",
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", tmp_path / "skills"),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", tmp_path / "rules"),
            patch("contemplative_agent.adapters.moltbook.config.PROMPTS_DIR", tmp_path / "prompts"),
            patch("contemplative_agent.adapters.moltbook.config.VIEWS_DIR", tmp_path / "views"),
        ):
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

        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.adapters.moltbook.config.IDENTITY_PATH",
                tmp_path / "identity.md",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.KNOWLEDGE_PATH",
                tmp_path / "knowledge.json",
            ),
            patch(
                "contemplative_agent.adapters.moltbook.config.CONSTITUTION_DIR",
                tmp_path / "constitution",
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", tmp_path / "skills"),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", tmp_path / "rules"),
            patch("contemplative_agent.adapters.moltbook.config.PROMPTS_DIR", prompts),
            patch("contemplative_agent.adapters.moltbook.config.VIEWS_DIR", views),
        ):
            _do_init()

        assert (prompts / "distill.md").read_text(encoding="utf-8") == "user-edited distill"
        out = capsys.readouterr().out
        assert "Prompts already exists" in out
        assert "Views already exists" in out


class TestDialogueCommand:
    """Validation logic for the `dialogue` subcommand."""

    @pytest.fixture
    def patched_production(self, tmp_path):
        """Point _PRODUCTION_HOME at an unused tmp path so tests never collide with real production."""
        with patch("contemplative_agent.cli.session_cmds._PRODUCTION_HOME", tmp_path / "nowhere"):
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

        with patch("contemplative_agent.cli.session_cmds._PRODUCTION_HOME", fake_prod.resolve()):
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
        with (
            patch(
                "contemplative_agent.cli.session_cmds.subprocess.Popen", return_value=fake_proc
            ) as popen,
            patch("contemplative_agent.cli.session_cmds.os.pipe", return_value=(1000, 1001)),
            patch("contemplative_agent.cli.session_cmds.os.close"),
        ):
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
        with (
            patch(
                "contemplative_agent.cli.session_cmds.subprocess.Popen", return_value=fake_proc
            ) as popen,
            patch("contemplative_agent.cli.session_cmds.os.pipe", return_value=(1000, 1001)),
            patch("contemplative_agent.cli.session_cmds.os.close"),
        ):
            _handle_dialogue(self._args(home_a, home_b), MagicMock())

        for call in popen.call_args_list:
            cmd = call.args[0]
            assert "some_wrapper_pkg.cli" in cmd
            assert "contemplative_agent.cli" not in cmd


class TestDialoguePeerShortfallM10:
    """Bug-audit 2026-07-06 M10: a dialogue truncated by peer EOF previously
    exited 0, so the parent rc gate reported it as a clean full run."""

    @staticmethod
    def _args(turns):
        return argparse.Namespace(turns=turns, seed=None, label="peer-a")

    def test_shortfall_exits_nonzero(self):
        from contemplative_agent.cli.session_cmds import _handle_dialogue_peer

        with patch(
            "contemplative_agent.adapters.dialogue.peer.run_peer_loop",
            return_value=1,
        ):
            with pytest.raises(SystemExit) as exc_info:
                _handle_dialogue_peer(self._args(turns=5), MagicMock())
        assert exc_info.value.code == 2

    def test_full_run_exits_cleanly(self):
        from contemplative_agent.cli.session_cmds import _handle_dialogue_peer

        with patch(
            "contemplative_agent.adapters.dialogue.peer.run_peer_loop",
            return_value=5,
        ):
            _handle_dialogue_peer(self._args(turns=5), MagicMock())
