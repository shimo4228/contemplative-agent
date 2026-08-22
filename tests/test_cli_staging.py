"""Staging CLI tests (cli/staging.py).

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.cli.adopt import _handle_adopt_staged
from contemplative_agent.cli.staging import StageItem, _stage_results


class TestStageResults:
    """Tests for _stage_results() staging helper."""

    def test_stages_files_with_meta(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        target = tmp_path / "skills" / "test-skill.md"
        audit = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results(items, command="insight")
        assert (staged_dir / "a.md").exists()
        assert (staged_dir / "b.md").exists()

    def test_rejects_path_traversal(self, tmp_path, capsys):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        evil_target = Path("/tmp/evil.md")
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
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
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
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


class TestStageResultsCollisionGuard:
    """Round-2 R2-H1/R2-L2: the staging path shares the H5 collision guard
    (two same-slug items in one batch previously clobbered each other's
    .md + .meta.json) and hashes the normalized on-disk text so the staged
    audit entry correlates with the adopt-time hash."""

    def _stage(self, tmp_path, items):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results(items, command="insight")
        return staged_dir, audit

    def test_same_filename_items_both_survive(self, tmp_path):
        items = [
            StageItem("dup.md", "# First", tmp_path / "skills" / "dup.md"),
            StageItem("dup.md", "# Second", tmp_path / "skills" / "dup.md"),
        ]
        staged_dir, _ = self._stage(tmp_path, items)
        assert (staged_dir / "dup.md").read_text() == "# First\n"
        assert (staged_dir / "dup-2.md").read_text() == "# Second\n"
        # Sidecars pair with the collision-resolved names, so adopt-staged
        # (which globs *.meta.json) sees both artifacts.
        assert (staged_dir / "dup.md.meta.json").exists()
        assert (staged_dir / "dup-2.md.meta.json").exists()

    def test_staged_hash_matches_disk_bytes(self, tmp_path):
        items = [StageItem("a.md", "# A", tmp_path / "skills" / "a.md")]
        staged_dir, audit = self._stage(tmp_path, items)
        disk = (staged_dir / "a.md").read_text()
        record = json.loads(audit.read_text().strip())
        assert record["content_hash"] == hashlib.sha256(disk.encode()).hexdigest()[:16]

    def test_trailing_newline_not_doubled(self, tmp_path):
        items = [StageItem("a.md", "# A\n", tmp_path / "skills" / "a.md")]
        staged_dir, _ = self._stage(tmp_path, items)
        assert (staged_dir / "a.md").read_text() == "# A\n"


class TestStageResultsPendingGuardADR0074:
    """_stage_results must never wipe an unreviewed batch (ADR-0074)."""

    def _ctx(self, tmp_path):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        return (
            staged_dir,
            (
                patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
                patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
                patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            ),
        )

    def test_refuses_when_unreviewed_batch_pending(self, tmp_path, capsys):
        staged_dir, patches = self._ctx(tmp_path)
        staged_dir.mkdir(parents=True)
        (staged_dir / "old.md").write_text("# Old\n")
        (staged_dir / "old.md.meta.json").write_text('{"target": "x", "seq": 1}\n')
        item = StageItem("new.md", "# New", tmp_path / "skills" / "new.md")
        with patches[0], patches[1], patches[2]:
            ok = _stage_results([item], command="insight")
        assert ok is False
        # Pending batch untouched, new batch not written.
        assert (staged_dir / "old.md").exists()
        assert (staged_dir / "old.md.meta.json").exists()
        assert not (staged_dir / "new.md").exists()
        assert "adopt-staged" in capsys.readouterr().out

    def test_a_held_item_still_blocks_but_the_refusal_names_it(self, tmp_path, capsys):
        """T-ADOPT-HOLD, 2026-08-15 decision: a hold keeps deferring the next
        batch — what changes is that the refusal can say the deferral was
        chosen. Without this, next week's packet §4 comes up empty and reads
        as "no candidates" rather than "you held three".
        """
        staged_dir, patches = self._ctx(tmp_path)
        staged_dir.mkdir(parents=True)
        (staged_dir / "held.md").write_text("# Held\n")
        (staged_dir / "held.md.meta.json").write_text(
            '{"target": "x", "seq": 1, "held": true, "held_at": "2026-08-15T00:00:00+00:00"}\n'
        )
        (staged_dir / "plain.md").write_text("# Plain\n")
        (staged_dir / "plain.md.meta.json").write_text('{"target": "y", "seq": 2}\n')

        item = StageItem("new.md", "# New", tmp_path / "skills" / "new.md")
        with patches[0], patches[1], patches[2]:
            ok = _stage_results([item], command="insight")

        assert ok is False
        out = capsys.readouterr().out
        assert "2 unreviewed" in out
        assert "(1 of them explicitly held at a past gate)" in out
        assert (staged_dir / "held.md.meta.json").exists()

    def test_an_unheld_batch_does_not_claim_a_hold(self, tmp_path, capsys):
        staged_dir, patches = self._ctx(tmp_path)
        staged_dir.mkdir(parents=True)
        (staged_dir / "old.md").write_text("# Old\n")
        (staged_dir / "old.md.meta.json").write_text('{"target": "x", "seq": 1}\n')

        item = StageItem("new.md", "# New", tmp_path / "skills" / "new.md")
        with patches[0], patches[1], patches[2]:
            _stage_results([item], command="insight")

        assert "held" not in capsys.readouterr().out

    def test_proceeds_when_no_pending_meta(self, tmp_path):
        staged_dir, patches = self._ctx(tmp_path)
        staged_dir.mkdir(parents=True)
        # Orphan file without a .meta.json sidecar is not a pending batch.
        (staged_dir / "stray.txt").write_text("x")
        item = StageItem("new.md", "# New", tmp_path / "skills" / "new.md")
        with patches[0], patches[1], patches[2]:
            ok = _stage_results([item], command="insight")
        assert ok is True
        assert (staged_dir / "new.md").exists()
        assert not (staged_dir / "stray.txt").exists()


class TestStagingHardeningCodexR20260709:
    """codex review 2026-07-09: corrupt-sidecar quarantine, staging lock,
    ledger-before-marker ordering."""

    def test_adopt_staged_quarantines_invalid_sidecar(self, tmp_path, capsys):
        """A corrupt meta.json must stop counting toward the pending guard
        after adopt-staged runs, instead of blocking all future staging."""
        from contemplative_agent.cli.staging import _pending_staged_count

        staged_dir = tmp_path / ".staged"
        staged_dir.mkdir()
        (staged_dir / "bad.md").write_text("# Bad\n")
        (staged_dir / "bad.md.meta.json").write_text("{not json")
        args = argparse.Namespace(yes=False)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "audit.jsonl"),
        ):
            _handle_adopt_staged(args, MagicMock())
            assert _pending_staged_count() == 0
        assert (staged_dir / "bad.md.meta.json.invalid").exists()
        assert not (staged_dir / "bad.md.meta.json").exists()
        assert "Quarantined" in capsys.readouterr().out

    def test_stage_results_refuses_when_lock_held(self, tmp_path, capsys):
        """Concurrent producer holding the staging lock → refuse, no wipe."""
        from contemplative_agent.core._io import acquire_run_lock

        staged_dir = tmp_path / ".staged"
        lock_path = tmp_path / ".staged.lock"
        item = StageItem("new.md", "# New", tmp_path / "skills" / "new.md")
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "audit.jsonl"),
            patch("contemplative_agent.cli.staging.STAGED_LOCK_PATH", lock_path),
        ):
            with acquire_run_lock(lock_path, blocking=False) as held:
                assert held is True
                ok = _stage_results([item], command="insight")
        assert ok is False
        assert not (staged_dir / "new.md").exists()
        assert "staging lock" in capsys.readouterr().out

    def test_ledger_failure_leaves_marker_unwritten(self, tmp_path):
        """Ledger append is ordered BEFORE the marker write: a failure between
        them must leave the window unconsumed (marker absent)."""
        from contemplative_agent.core.insight import InsightResult, SkillResult

        staged_dir = tmp_path / ".staged"
        skills_dir = tmp_path / "skills"
        result = InsightResult(
            skills=(
                SkillResult(
                    text='---\nname: x\ndescription: "y"\n---\n\n# X\n',
                    filename="x-20260709.md",
                    target_path=skills_dir / "x-20260709.md",
                ),
            ),
        )
        args = argparse.Namespace(stage=True, full=False)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", tmp_path / "audit.jsonl"),
            patch("contemplative_agent.cli.staging.STAGED_LOCK_PATH", tmp_path / ".staged.lock"),
            patch("contemplative_agent.cli.memory_cmds._load_view_registry", return_value=None),
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=tmp_path),
            patch(
                "contemplative_agent.cli.memory_cmds._append_insight_ledger",
                side_effect=OSError("disk full"),
            ),
            patch(
                "contemplative_agent.core.insight.extract_insight",
                return_value=result,
            ),
        ):
            from contemplative_agent.cli.memory_cmds import _handle_insight

            with pytest.raises(OSError):
                _handle_insight(args, MagicMock())
        assert not (skills_dir / ".last_insight").exists()
