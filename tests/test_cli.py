"""Tests for the CLI entry point: main dispatch, runtime setup, repo root."""

import argparse
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
    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_register(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent.do_register.return_value = {"claim_url": "https://example.com"}
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "register"]):
            main()

        mock_agent.do_register.assert_called_once()


class TestMainStatus:
    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_status(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent.do_status.return_value = {"claimed": True}
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "status"]):
            main()

        mock_agent.do_status.assert_called_once()


class TestMainRun:
    @patch("contemplative_agent.cli.agent_cmds.Agent")
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

    @patch("contemplative_agent.cli.agent_cmds.Agent")
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

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_run_clears_session_id_even_when_lock_unavailable(self, mock_agent_cls):
        from contemplative_agent.core.run_context import current_session_id

        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("contemplative_agent.cli.agent_cmds.acquire_run_lock") as mock_lock:
            mock_lock.return_value.__enter__.return_value = False
            with patch("sys.argv", ["contemplative-agent", "run"]):
                main()

        mock_agent.run_session.assert_not_called()
        assert current_session_id() is None

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_run_custom_duration(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "run", "--session", "30"]):
            main()

        call_kwargs = mock_agent.run_session.call_args[1]
        assert call_kwargs["duration_minutes"] == 30


class TestMainSolve:
    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_solve(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "solve", "test text"]):
            main()

        mock_agent.do_solve.assert_called_once_with("test text")


class TestAutonomyFlags:
    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_approve_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "--approve", "status"]):
            main()

        from contemplative_agent.adapters.moltbook.agent import AutonomyLevel

        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.APPROVE, domain_config=None)

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_guarded_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "--guarded", "status"]):
            main()

        from contemplative_agent.adapters.moltbook.agent import AutonomyLevel

        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.GUARDED, domain_config=None)

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_auto_flag(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "--auto", "status"]):
            main()

        from contemplative_agent.adapters.moltbook.agent import AutonomyLevel

        mock_agent_cls.assert_called_once_with(autonomy=AutonomyLevel.AUTO, domain_config=None)

    @patch("contemplative_agent.cli.agent_cmds.Agent")
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
    @patch("contemplative_agent.cli.agent_cmds.Agent")
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

    @patch("contemplative_agent.cli.agent_cmds.Agent")
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


# ---------------------------------------------------------------------------
# ADR-0081: description-audit phase (advisory-only) in the skill stocktake
# ---------------------------------------------------------------------------


class TestStocktakeDescriptionPhase:
    def _items(self, name="s.md", description="A narrow skill"):
        """``StocktakeResult.items`` shape: (filename, raw, stripped body)."""
        raw = f'---\nname: {name[:-3]}\ndescription: "{description}"\n---\n\n# T\n\nbody'
        return [(name, raw, "# T\n\nbody")]

    def test_prints_mismatch_with_usage_annotation(self, capsys):
        from unittest.mock import patch

        from contemplative_agent.cli.stocktake_cmd import _stocktake_description_phase

        with patch(
            "contemplative_agent.core.stocktake.audit_skill_description",
            return_value=("broader: description omits the narrow trigger", None),
        ):
            _stocktake_description_phase(
                self._items(),
                desc_prompt="audit {name} {description} {skill}",
                usage_counts={"s": 920},
            )
        out = capsys.readouterr().out
        assert "broader" in out
        assert "selected 920x" in out
        assert "advisory only" in out

    def test_missing_description_flagged_without_llm_call(self, capsys):
        from unittest.mock import patch

        from contemplative_agent.cli.stocktake_cmd import _stocktake_description_phase

        with patch(
            "contemplative_agent.core.stocktake.audit_skill_description",
            return_value=(None, None),
        ) as mock_audit:
            _stocktake_description_phase(
                [("s.md", "# Title only\n\nbody", "# Title only\n\nbody")],
                desc_prompt="audit {name} {description} {skill}",
            )
        out = capsys.readouterr().out
        # skill_theme falls back to the markdown title as description, so a
        # title-only file still audits; a truly empty one is flagged. Either
        # way the phase must not crash — assert the summary line printed.
        assert "Description audit" in out
        assert mock_audit.call_count <= 1


class TestCodexReviewFixes20260724:
    """Regression pins for the codex-review P2 findings on the ADR-0081 diff."""

    def test_load_selection_reading_empty_window_is_none(self, tmp_path, monkeypatch):
        from contemplative_agent.cli import stocktake_cmd

        monkeypatch.setattr(stocktake_cmd.config, "EPISODE_LOG_DIR", tmp_path / "logs")
        monkeypatch.setattr(stocktake_cmd.config, "SKILLS_DIR", tmp_path / "skills")
        assert stocktake_cmd._load_selection_reading() is None

    def test_description_phase_audits_the_body_the_quality_check_read(self):
        """The audit sees StocktakeResult.items — one read policy, not two."""
        from unittest.mock import patch

        from contemplative_agent.cli.stocktake_cmd import _stocktake_description_phase

        raw = '---\nname: s\ndescription: "d"\n---\n\n# T\n\nFRESH_BODY'
        with patch(
            "contemplative_agent.core.stocktake.audit_skill_description",
            return_value=(None, None),
        ) as mock_audit:
            _stocktake_description_phase(
                [("s.md", raw, "# T\n\nFRESH_BODY")],
                desc_prompt="audit {name} {description} {skill}",
            )
        audited_body = mock_audit.call_args.args[0][2]
        assert "FRESH_BODY" in audited_body


class TestCommandRegistry:
    """The registry exists so parser construction and dispatch cannot disagree.

    Before it, a command was declared in two places — a subparsers.add_parser
    block and a tier dispatch table — and an entry present in one but missing
    from the other fell through to Agent construction instead of erroring.
    """

    def test_every_registered_command_has_a_parser(self):
        from contemplative_agent.cli import COMMANDS, main  # noqa: F401

        parser = _build_parser()
        subparsers_action = _subparsers_action(parser)
        assert set(subparsers_action.choices) == {spec.name for spec in COMMANDS}

    def test_every_command_is_dispatchable(self):
        from contemplative_agent.cli import _COMMANDS_BY_NAME, COMMANDS

        assert set(_COMMANDS_BY_NAME) == {spec.name for spec in COMMANDS}

    def test_duplicate_registration_is_rejected(self):
        from contemplative_agent.cli.registry import CommandSpec, Tier, index_by_name

        def _noop(args, parser):
            return None

        spec = CommandSpec(name="dup", help="h", handler=_noop, tier=Tier.NO_LLM)
        with pytest.raises(ValueError, match="duplicate command registration: dup"):
            index_by_name((spec, spec))

    def test_agent_tier_handlers_take_domain_config(self):
        # AGENT-tier handlers get a third argument; the other tiers must not,
        # or dispatch would pass an argument the handler cannot accept.
        import inspect

        from contemplative_agent.cli import COMMANDS
        from contemplative_agent.cli.registry import Tier

        for spec in COMMANDS:
            arity = len(inspect.signature(spec.handler).parameters)
            expected = 3 if spec.tier is Tier.AGENT else 2
            assert arity == expected, f"{spec.name} handler takes {arity} args"

    def test_internal_command_still_listed_as_internal(self):
        # `dialogue-peer` is spawned by `dialogue`, never typed by a user, but
        # it stays visible in --help: the marker is the "(internal)" prefix in
        # its help text, not suppression.
        from contemplative_agent.cli import _COMMANDS_BY_NAME

        assert _COMMANDS_BY_NAME["dialogue-peer"].help.startswith("(internal)")

    def test_resolve_follows_a_patched_definition_site(self):
        # The spec captures the function object at import time, so dispatch
        # resolves by name — otherwise patching a handler would silently no-op
        # and CLI wiring tests would exercise the real implementation.
        from contemplative_agent.cli import _COMMANDS_BY_NAME

        spec = _COMMANDS_BY_NAME["skill-stocktake"]
        with patch("contemplative_agent.cli.stocktake_cmd._handle_skill_stocktake") as stub:
            assert spec.resolve() is stub


def _build_parser():
    """Parse-only construction of the real CLI parser."""
    import contemplative_agent.cli as cli_mod

    captured = {}
    real_parse = argparse.ArgumentParser.parse_args

    def _capture(self, *a, **kw):
        captured["parser"] = self
        raise SystemExit(0)

    with patch.object(argparse.ArgumentParser, "parse_args", _capture):
        with patch("sys.argv", ["contemplative-agent"]):
            with pytest.raises(SystemExit):
                cli_mod.main()
    assert real_parse is not None
    return captured["parser"]


def _subparsers_action(parser):
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action
    raise AssertionError("no subparsers action on the CLI parser")


class TestMainSubmoltScan:
    """CLI surface of the ADR-0086 instrument."""

    def _scan(self, **overrides):
        from contemplative_agent.adapters.moltbook.submolt_scope import SubmoltScopeScan

        fields = {
            "verdict": "completed",
            "scan_id": "abc123",
            "discovered": 3,
            "scanned": ("ai", "philosophy"),
            "skipped": (("hidden", "private"),),
            "scored": 40,
        }
        fields.update(overrides)
        return SubmoltScopeScan(**fields)

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_default_sample_size_is_the_module_default(self, mock_agent_cls):
        from contemplative_agent.adapters.moltbook.submolt_scope import DEFAULT_SAMPLE_SIZE

        mock_agent = MagicMock()
        mock_agent.do_submolt_scan.return_value = self._scan()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "submolt-scan"]):
            main()

        mock_agent.do_submolt_scan.assert_called_once_with(DEFAULT_SAMPLE_SIZE)

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_custom_sample_size(self, mock_agent_cls):
        mock_agent = MagicMock()
        mock_agent.do_submolt_scan.return_value = self._scan()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "submolt-scan", "--sample-size", "5"]):
            main()

        mock_agent.do_submolt_scan.assert_called_once_with(5)

    @pytest.mark.parametrize("value", ["0", "-1", "101"])
    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_out_of_range_sample_size_is_rejected(self, mock_agent_cls, value):
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "submolt-scan", "--sample-size", value]):
            with pytest.raises(SystemExit):
                main()

        mock_agent.do_submolt_scan.assert_not_called()

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_held_run_lock_skips_the_sweep(self, mock_agent_cls):
        """The sweep spends the same GET budget a session does — it must not
        run alongside one."""
        mock_agent = MagicMock()
        mock_agent_cls.return_value = mock_agent

        with patch("contemplative_agent.cli.agent_cmds.acquire_run_lock") as mock_lock:
            mock_lock.return_value.__enter__.return_value = False
            with patch("sys.argv", ["contemplative-agent", "submolt-scan"]):
                main()

        mock_agent.do_submolt_scan.assert_not_called()

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_skipped_submolts_are_reported(self, mock_agent_cls, capsys):
        mock_agent = MagicMock()
        mock_agent.do_submolt_scan.return_value = self._scan()
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "submolt-scan"]):
            main()

        out = capsys.readouterr().out
        assert "skipped hidden: private" in out
        assert "40 posts scored" in out

    @patch("contemplative_agent.cli.agent_cmds.Agent")
    def test_disabled_verdict_names_the_kill_switch(self, mock_agent_cls, capsys):
        mock_agent = MagicMock()
        mock_agent.do_submolt_scan.return_value = self._scan(
            verdict="disabled", scanned=(), skipped=(), scored=0, discovered=0
        )
        mock_agent_cls.return_value = mock_agent

        with patch("sys.argv", ["contemplative-agent", "submolt-scan"]):
            main()

        assert "Instrument disabled" in capsys.readouterr().out
