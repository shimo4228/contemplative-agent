"""adopt-staged / remove-skill CLI tests (cli/adopt.py).

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import json
from pathlib import Path
from typing import Literal
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli.adopt import _handle_adopt_staged, _handle_remove_skill
from contemplative_agent.cli.staging import StageItem, _stage_results


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
            name=name,
            reason=reason,
            yes=yes,
            dry_run=dry_run,
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
            patch("contemplative_agent.cli.approval._approve_delete", return_value=True),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
            patch("contemplative_agent.cli.approval._approve_delete", return_value=False),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
        ):
            with pytest.raises(SystemExit) as exc:
                _handle_remove_skill(
                    self._args("../other"),
                    MagicMock(),
                )
        assert exc.value.code == 2
        assert (tmp_path / "other.md").exists()


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
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results([item], command=command)
        return staged_dir

    def _run_adopt(self, tmp_path, staged_dir, *, inputs: list[str]):
        audit = tmp_path / "logs" / "audit.jsonl"
        args = argparse.Namespace(yes=False)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=inputs),
        ):
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
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.exists()
        assert target.read_text().startswith("# A")
        # staging cleared
        assert not (staged / "a.md").exists()
        assert not (staged / "a.md.meta.json").exists()

    def test_reject_does_not_write_and_clears_staging(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        self._run_adopt(tmp_path, staged, inputs=["n"])
        assert not target.exists()
        # rejected items are also cleared from staging
        assert not (staged / "a.md").exists()
        assert not (staged / "a.md.meta.json").exists()

    def test_adopt_logs_audit_entry(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
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
        # Bytes preserved for inspection, but the sidecar is quarantined
        # (renamed .invalid) so a permanently skipped entry stops counting
        # toward the ADR-0074 pending guard instead of blocking all future
        # staging (codex review 2026-07-09).
        assert (staged_dir / "evil.md").exists()
        assert (staged_dir / "evil.md.meta.json.invalid").exists()
        assert not (staged_dir / "evil.md.meta.json").exists()

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

    def test_adopt_clean_rewrite_overwrites_in_place(self, tmp_path):
        """Regression (2026-07-10): a staged skill-stocktake clean rewrite
        targets its own original file. The collision guard must recognize the
        self-source and overwrite in place — the pre-fix behavior minted a
        `-2.md` duplicate for all 10 rewrites of a batch, doubling the corpus
        the stocktake was meant to shrink."""
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "a.md").write_text("# A original")

        target = skills_dir / "a.md"
        staged = self._stage_one(
            tmp_path,
            filename="a.md",
            text="# A cleaned",
            target=target,
            command="skill-stocktake-clean",
            sources=["a.md"],
        )
        self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.read_text().startswith("# A cleaned")
        assert not (skills_dir / "a-2.md").exists()

    def test_adopt_prints_system_budget_reading(self, tmp_path, capsys):
        """The adopt gate shows the read-only system-prompt budget projection
        (2026-07-09: a 13-skill batch was approved blind and grew the system
        prompt past the C2 guard)."""
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        with patch(
            "contemplative_agent.core.llm.prompting._build_system_prompt",
            return_value="a" * 3000,
        ):
            self._run_adopt(tmp_path, staged, inputs=["y"])
        out = capsys.readouterr().out
        assert "System prompt budget" in out

    def test_budget_reading_skips_targets_outside_data_root(self, tmp_path, capsys):
        """Codex review 2026-07-10 P2: the instrument pre-pass must apply the
        same MOLTBOOK_HOME containment check as _load_staged_item — a
        tampered sidecar (target outside the data root, e.g. a special file)
        must not be read by the budget pass."""
        from contemplative_agent.cli.adopt import _print_system_budget_for_staged

        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("x" * 30000)  # 10K tok if wrongly counted
        (staged_dir / "evil.md").write_text("small")
        (staged_dir / "evil.md.meta.json").write_text(
            json.dumps({"target": str(outside), "command": "insight"})
        )
        with patch(
            "contemplative_agent.core.llm.prompting._build_system_prompt",
            return_value="a" * 3000,  # 1000 tok
        ):
            _print_system_budget_for_staged(
                [staged_dir / "evil.md.meta.json"], data_root=tmp_path / "home"
            )
        out = capsys.readouterr().out
        # Escaping entry skipped entirely: reading stays at the bare prompt.
        assert "≈1,000 tok → ≈1,000 tok" in out

    def test_budget_reading_does_not_subtract_collision_targets(self, tmp_path, capsys):
        """Codex review 2026-07-10 P2: a write whose target exists with
        different content and is NOT in sources gets a `-2.md` suffix on
        adopt — the original survives, so its tokens must not be subtracted."""
        from contemplative_agent.cli.adopt import _print_system_budget_for_staged

        skills_dir = tmp_path / "home" / "skills"
        skills_dir.mkdir(parents=True)
        target = skills_dir / "a.md"
        target.write_text("b" * 1500)  # 500 tok — must NOT be subtracted
        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        (staged_dir / "a.md").write_text("c" * 300)  # +100 tok
        (staged_dir / "a.md.meta.json").write_text(
            json.dumps({"target": str(target), "command": "insight"})
        )
        with patch(
            "contemplative_agent.core.llm.prompting._build_system_prompt",
            return_value="a" * 3000,  # 1000 tok
        ):
            _print_system_budget_for_staged(
                [staged_dir / "a.md.meta.json"], data_root=tmp_path / "home"
            )
        out = capsys.readouterr().out
        assert "≈1,000 tok → ≈1,100 tok" in out  # +100, no -500

    def test_adopt_survives_budget_instrument_failure(self, tmp_path):
        """Degrade, never abort (ADR-0071 invariant): a broken instrument
        must not block the adoption it merely informs."""
        target = tmp_path / "skills" / "a.md"
        staged = self._stage_one(tmp_path, filename="a.md", text="# A", target=target)
        with patch(
            "contemplative_agent.core.llm.system_prompt_budget_reading",
            side_effect=RuntimeError("instrument broke"),
        ):
            self._run_adopt(tmp_path, staged, inputs=["y"])
        assert target.exists()

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
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results([item], command=command)
        return staged_dir

    def _run_adopt(self, tmp_path, staged_dir, *, inputs: list[str]):
        audit = tmp_path / "logs" / "audit.jsonl"
        args = argparse.Namespace(yes=False)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=inputs),
        ):
            _handle_adopt_staged(args, MagicMock())

    def test_adopt_drop_approved_deletes_target(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        target = skills_dir / "low-quality.md"
        target.write_text("# Low quality skill\nshort")

        staged = self._stage_one(
            tmp_path,
            filename="low-quality.md",
            text="# Low quality skill\nshort",
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
            tmp_path,
            filename="low-quality.md",
            text="# Low quality skill\nshort",
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
            tmp_path,
            filename="low-quality.md",
            text="# LQ",
            target=target,
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
            tmp_path,
            filename="gone.md",
            text="# Ghost",
            target=target,
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
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
        args = argparse.Namespace(yes=True)
        # Patch input() with a sentinel that fails the test if called.
        # If --yes works correctly, the prompt path should never run.
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input") as mock_input,
        ):
            _handle_adopt_staged(args, MagicMock())
            mock_input.assert_not_called()

    def test_yes_flag_approves_merge_without_prompt(self, tmp_path):
        target = tmp_path / "skills" / "a.md"
        staged_dir = tmp_path / ".staged"
        item = StageItem("a.md", "# Auto-approved A", target)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.cli.approval.AUDIT_LOG_PATH",
                tmp_path / "logs" / "audit.jsonl",
            ),
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.cli.approval.AUDIT_LOG_PATH",
                tmp_path / "logs" / "audit.jsonl",
            ),
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.cli.approval.AUDIT_LOG_PATH",
                tmp_path / "logs" / "audit.jsonl",
            ),
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


class TestAdoptionOrderForCollisionPair:
    """Codex review round-2 P2: adopt-staged must process a collision pair in
    staging order — a plain name sort put dup-2.md.meta.json first ('-' < '.')
    and swapped the pair's final target names."""

    def test_adoption_preserves_staging_order(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        target = tmp_path / "skills" / "dup.md"
        items = [
            StageItem("dup.md", "# First", target),
            StageItem("dup.md", "# Second", target),
        ]
        ns = argparse.Namespace(yes=True)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results(items, command="insight")
            _handle_adopt_staged(ns, MagicMock())
        # First staged item keeps the unsuffixed name; the collider gets -2.
        assert (tmp_path / "skills" / "dup.md").read_text() == "# First\n"
        assert (tmp_path / "skills" / "dup-2.md").read_text() == "# Second\n"
