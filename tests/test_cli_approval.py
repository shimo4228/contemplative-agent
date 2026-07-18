"""Approval gate CLI tests (cli/approval.py).

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from contemplative_agent.cli.adopt import _handle_adopt_staged
from contemplative_agent.cli.approval import _approve_delete, _log_approval
from contemplative_agent.cli.staging import StageItem, _stage_results


class TestLogApproval:
    def test_creates_audit_log(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
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
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("rules-distill", Path("rules/bar.md"), False, "content")

        record = json.loads(audit_path.read_text().strip())
        assert record["decision"] == "rejected"

    def test_appends_multiple(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "a")
            _log_approval("insight", Path("b.md"), False, "b")

        lines = audit_path.read_text().strip().splitlines()
        assert len(lines) == 2

    def test_different_content_different_hash(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content A")
            _log_approval("insight", Path("a.md"), True, "content B")

        lines = audit_path.read_text().strip().splitlines()
        h1 = json.loads(lines[0])["content_hash"]
        h2 = json.loads(lines[1])["content_hash"]
        assert h1 != h2

    def test_default_source_is_direct(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content")
        record = json.loads(audit_path.read_text().strip())
        assert record["source"] == "direct"

    def test_source_stage_adopted(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content", source="stage-adopted")
        record = json.loads(audit_path.read_text().strip())
        assert record["source"] == "stage-adopted"
        assert record["decision"] == "approved"

    def test_snapshot_path_recorded(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        snap = tmp_path / "snapshots" / "distill_20260415T104542Z"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval(
                "distill-identity",
                Path("identity.md"),
                True,
                "content",
                snapshot_path=snap,
            )
        record = json.loads(audit_path.read_text().strip())
        assert record["snapshot_path"] == str(snap)

    def test_snapshot_path_null_when_omitted(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content")
        record = json.loads(audit_path.read_text().strip())
        assert "snapshot_path" in record  # field always present for forward compat
        assert record["snapshot_path"] is None

    def test_reason_field_preserved_when_provided(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval(
                "remove-skill",
                Path("skills/foo.md"),
                True,
                "content",
                source="direct-remove",
                reason="superseded by 2026-04-17 run",
            )
        record = json.loads(audit_path.read_text().strip())
        assert record["reason"] == "superseded by 2026-04-17 run"
        assert record["source"] == "direct-remove"

    def test_reason_null_when_omitted(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "content")
        record = json.loads(audit_path.read_text().strip())
        assert "reason" in record  # field always present for forward compat
        assert record["reason"] is None

    def test_staged_decision_for_none_approval(self, tmp_path):
        """approved=None should map to decision='staged'."""
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), None, "content", source="stage")
        record = json.loads(audit_path.read_text().strip())
        assert record["decision"] == "staged"
        assert record["source"] == "stage"


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


class TestApprovalLineageADR0050:
    """ADR-0050: source_ids + epistemic_counts flow into audit.jsonl
    through every approval path (direct loop, single approve, stage→adopt)."""

    def test_log_approval_records_lineage_fields(self, tmp_path):
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval(
                "insight",
                Path("skills/foo.md"),
                True,
                "# Skill",
                source_ids=["abc123def456", "0123456789ab"],
                epistemic_counts={"observed": 1, "generated": 2, "unknown": 0},
            )
        record = json.loads(audit_path.read_text().strip())
        assert record["source_ids"] == ["abc123def456", "0123456789ab"]
        assert record["epistemic_counts"] == {
            "observed": 1,
            "generated": 2,
            "unknown": 0,
        }

    def test_log_approval_lineage_fields_always_present(self, tmp_path):
        """Nullable but always present — stable record shape for analysis."""
        audit_path = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path):
            _log_approval("insight", Path("a.md"), True, "a")
        record = json.loads(audit_path.read_text().strip())
        assert "source_ids" in record and record["source_ids"] is None
        assert "epistemic_counts" in record and record["epistemic_counts"] is None

    def test_run_approval_loop_plumbs_skill_lineage(self, tmp_path):
        from contemplative_agent.cli.approval import _run_approval_loop
        from contemplative_agent.core.insight import SkillResult

        audit_path = tmp_path / "logs" / "audit.jsonl"
        skills_dir = tmp_path / "skills"
        item = SkillResult(
            text="# S",
            filename="s.md",
            target_path=skills_dir / "s.md",
            pattern_ids=("a1a1a1a1a1a1", "b2b2b2b2b2b2"),
            epistemic_counts={"observed": 0, "generated": 2, "unknown": 0},
        )
        with (
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
            patch("builtins.input", side_effect=["y"]),
        ):
            _run_approval_loop([item], command="insight", target_dir=skills_dir)
        record = json.loads(audit_path.read_text().strip())
        assert record["source_ids"] == ["a1a1a1a1a1a1", "b2b2b2b2b2b2"]
        assert record["epistemic_counts"] == {
            "observed": 0,
            "generated": 2,
            "unknown": 0,
        }

    def test_run_approval_loop_plumbs_rule_source_ids(self, tmp_path):
        """RuleResult exposes source_ids (skill filenames), not pattern_ids."""
        from contemplative_agent.cli.approval import _run_approval_loop
        from contemplative_agent.core.rules_distill import RuleResult

        audit_path = tmp_path / "logs" / "audit.jsonl"
        rules_dir = tmp_path / "rules"
        item = RuleResult(
            text="# R",
            filename="r.md",
            target_path=rules_dir / "r.md",
            source_ids=("skill-a.md", "skill-b.md"),
        )
        with (
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
            patch("builtins.input", side_effect=["y"]),
        ):
            _run_approval_loop([item], command="rules-distill", target_dir=rules_dir)
        record = json.loads(audit_path.read_text().strip())
        assert record["source_ids"] == ["skill-a.md", "skill-b.md"]

    def test_stage_adopt_roundtrip_carries_lineage(self, tmp_path):
        """The most leak-prone plumbing: stage meta.json → adopt → audit."""
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        target = tmp_path / "skills" / "a.md"
        item = StageItem(
            "a.md",
            "# A",
            target,
            source_ids=["c3c3c3c3c3c3"],
            epistemic_counts={"observed": 1, "generated": 0, "unknown": 0},
        )
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results([item], command="insight")

        meta = json.loads((staged_dir / "a.md.meta.json").read_text())
        assert meta["source_ids"] == ["c3c3c3c3c3c3"]
        assert meta["epistemic_counts"] == {
            "observed": 1,
            "generated": 0,
            "unknown": 0,
        }
        # Stage-time audit record already carries lineage.
        stage_record = json.loads(audit.read_text().strip().splitlines()[-1])
        assert stage_record["decision"] == "staged"
        assert stage_record["source_ids"] == ["c3c3c3c3c3c3"]

        args = argparse.Namespace(yes=False)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
            _handle_adopt_staged(args, MagicMock())

        adopted_record = json.loads(audit.read_text().strip().splitlines()[-1])
        assert adopted_record["decision"] == "approved"
        assert adopted_record["source"] == "stage-adopted"
        assert adopted_record["source_ids"] == ["c3c3c3c3c3c3"]
        assert adopted_record["epistemic_counts"] == {
            "observed": 1,
            "generated": 0,
            "unknown": 0,
        }


class TestCollisionFreePathH5:
    """Bug-audit 2026-07-06 H5: an approved write must never silently
    overwrite an existing file with different content — same-day slug
    collisions previously clobbered the earlier skill/rule while audit.jsonl
    recorded both items as approved."""

    def test_nonexistent_path_unchanged(self, tmp_path):
        from contemplative_agent.cli.approval import _collision_free_path

        target = tmp_path / "skill-20260706.md"
        assert _collision_free_path(target, "body") == target

    def test_identical_content_keeps_path(self, tmp_path):
        from contemplative_agent.cli.approval import _collision_free_path

        target = tmp_path / "skill-20260706.md"
        target.write_text("same body\n", encoding="utf-8")
        assert _collision_free_path(target, "same body") == target

    def test_different_content_gets_suffix(self, tmp_path):
        from contemplative_agent.cli.approval import _collision_free_path

        target = tmp_path / "skill-20260706.md"
        target.write_text("first batch skill", encoding="utf-8")
        resolved = _collision_free_path(target, "second batch skill")
        assert resolved == tmp_path / "skill-20260706-2.md"

    def test_suffix_increments_past_existing(self, tmp_path):
        from contemplative_agent.cli.approval import _collision_free_path

        (tmp_path / "s-20260706.md").write_text("one", encoding="utf-8")
        (tmp_path / "s-20260706-2.md").write_text("two", encoding="utf-8")
        resolved = _collision_free_path(tmp_path / "s-20260706.md", "three")
        assert resolved == tmp_path / "s-20260706-3.md"

    def test_approval_loop_does_not_clobber(self, tmp_path):
        """Two approved same-slug items in one run both survive on disk."""
        from contemplative_agent.cli.approval import _run_approval_loop
        from contemplative_agent.core.insight import SkillResult

        audit_path = tmp_path / "logs" / "audit.jsonl"
        skills_dir = tmp_path / "skills"
        items = [
            SkillResult(
                text="# First cluster skill", filename="s.md", target_path=skills_dir / "s.md"
            ),
            SkillResult(
                text="# Second cluster skill", filename="s.md", target_path=skills_dir / "s.md"
            ),
        ]
        with (
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
            patch("builtins.input", side_effect=["y", "y"]),
        ):
            written = _run_approval_loop(items, command="insight", target_dir=skills_dir)
        assert written == 2
        assert (skills_dir / "s.md").read_text(encoding="utf-8") == "# First cluster skill"
        assert (skills_dir / "s-2.md").read_text(encoding="utf-8") == "# Second cluster skill"


class TestCollisionRerunIdempotencyCodex:
    """Codex review 2026-07-06: rerunning the same collision batch must reuse
    an existing identical -2 file, not mint -3, -4… on every retry."""

    def test_identical_suffixed_file_is_reused(self, tmp_path):
        from contemplative_agent.cli.approval import _collision_free_path

        (tmp_path / "s-20260706.md").write_text("first", encoding="utf-8")
        (tmp_path / "s-20260706-2.md").write_text("second", encoding="utf-8")
        resolved = _collision_free_path(tmp_path / "s-20260706.md", "second")
        assert resolved == tmp_path / "s-20260706-2.md"
