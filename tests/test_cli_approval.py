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
                epistemic_counts={"generated": 2, "unknown": 1},
            )
        record = json.loads(audit_path.read_text().strip())
        assert record["source_ids"] == ["abc123def456", "0123456789ab"]
        assert record["epistemic_counts"] == {"generated": 2, "unknown": 1}

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
            epistemic_counts={"generated": 2, "unknown": 0},
        )
        with (
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit_path),
            patch("builtins.input", side_effect=["y"]),
        ):
            _run_approval_loop([item], command="insight", target_dir=skills_dir)
        record = json.loads(audit_path.read_text().strip())
        assert record["source_ids"] == ["a1a1a1a1a1a1", "b2b2b2b2b2b2"]
        assert record["epistemic_counts"] == {"generated": 2, "unknown": 0}

    def test_run_approval_loop_plumbs_rule_source_ids(self, tmp_path):
        """A result exposing source_ids (filenames), not pattern_ids, is plumbed as-is.

        The original producer of this shape (``rules-distill``) was retired by
        ADR-0097; the approval loop's lineage contract outlives it.
        """
        from dataclasses import dataclass

        from contemplative_agent.cli.approval import _run_approval_loop

        @dataclass(frozen=True)
        class _RuleLike:
            text: str
            filename: str
            target_path: Path
            source_ids: tuple[str, ...]

        audit_path = tmp_path / "logs" / "audit.jsonl"
        rules_dir = tmp_path / "rules"
        item = _RuleLike(
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
            epistemic_counts={"generated": 1, "unknown": 0},
        )
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results([item], command="insight")

        meta = json.loads((staged_dir / "a.md.meta.json").read_text())
        assert meta["source_ids"] == ["c3c3c3c3c3c3"]
        assert meta["epistemic_counts"] == {"generated": 1, "unknown": 0}
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
        assert adopted_record["epistemic_counts"] == {"generated": 1, "unknown": 0}

    def test_closed_input_count_roundtrip_is_sparse(self, tmp_path):
        """P3-04.14: identity's closed_input_count rides meta.json into the
        stage and adopt audit rows; other producers' rows do not gain the key."""
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        item = StageItem(
            "identity.md",
            "# I",
            tmp_path / "identity.md",
            source_ids=["c3c3c3c3c3c3"],
            epistemic_counts={"generated": 1, "unknown": 0},
            closed_input_count=3,
        )
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results([item], command="distill-identity")
        meta = json.loads((staged_dir / "identity.md.meta.json").read_text())
        assert meta["closed_input_count"] == 3
        assert json.loads(audit.read_text().splitlines()[-1])["closed_input_count"] == 3
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
            _handle_adopt_staged(argparse.Namespace(yes=False), MagicMock())
        adopted = json.loads(audit.read_text().splitlines()[-1])
        assert adopted["decision"] == "approved"
        assert adopted["closed_input_count"] == 3

    def test_closed_input_count_absent_for_other_producers(self, tmp_path):
        audit = tmp_path / "logs" / "audit.jsonl"
        with patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit):
            _log_approval("insight", Path("a.md"), True, "a")
        assert "closed_input_count" not in json.loads(audit.read_text())

    def test_adopt_passes_through_pre_adr0082_meta_verbatim(self, tmp_path):
        """ADR-0082 is non-retroactive: meta.json staged before the retirement
        still carries ``observed`` and must adopt unchanged. Guards the claim
        that the 78 files staged on 2026-07-25 stay adoptable."""
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        staged_dir.mkdir(parents=True)
        (staged_dir / "legacy.md").write_text("# Legacy")
        legacy_counts = {"observed": 0, "generated": 4, "unknown": 0}
        (staged_dir / "legacy.md.meta.json").write_text(
            json.dumps(
                {
                    "target": str(tmp_path / "skills" / "legacy.md"),
                    "command": "insight",
                    "seq": 1,
                    "source_ids": ["d4d4d4d4d4d4"],
                    "epistemic_counts": legacy_counts,
                }
            )
        )

        args = argparse.Namespace(yes=False)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
            _handle_adopt_staged(args, MagicMock())

        record = json.loads(audit.read_text().strip().splitlines()[-1])
        assert record["decision"] == "approved"
        assert record["epistemic_counts"] == legacy_counts


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


class TestValueHistoryP30402:
    """P3-04.2: adopting identity / constitution leaves a verbatim history copy."""

    def _stage_and_adopt(self, tmp_path, command, target, text):
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _stage_results([StageItem(target.name, text, target)], command=command)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
            _handle_adopt_staged(argparse.Namespace(yes=False), MagicMock())

    def test_identity_adoption_writes_history_with_matching_sha(self, tmp_path):
        import hashlib

        (tmp_path / "identity.md").write_text("old\n")
        self._stage_and_adopt(tmp_path, "distill-identity", tmp_path / "identity.md", "new self")
        files = list((tmp_path / "history" / "identity").glob("*.md"))
        assert len(files) == 1
        body = files[0].read_bytes()
        assert body == (tmp_path / "identity.md").read_bytes()
        assert files[0].name.endswith(f"-{hashlib.sha256(body).hexdigest()[:12]}.md")

    def test_constitution_adoption_writes_dated_history_outside_the_flat_glob(self, tmp_path):
        cdir = tmp_path / "constitution"
        cdir.mkdir()
        target = cdir / "contemplative-axioms.md"
        target.write_text("old\n")
        self._stage_and_adopt(tmp_path, "amend-constitution", target, "new clauses")
        hist = list((cdir / "history").glob("*.md"))
        assert len(hist) == 1 and hist[0].read_bytes() == target.read_bytes()
        # the loader and the snapshot read constitution/*.md flat: history is not seen
        assert [p.name for p in cdir.glob("*.md")] == ["contemplative-axioms.md"]
        # P3-04.12: the version's section -> technique map is recorded beside it
        lineage = json.loads((cdir / "history" / "lineage.json").read_text())
        assert hist[0].name in lineage["versions"]

    def test_other_commands_leave_no_history(self, tmp_path):
        self._stage_and_adopt(tmp_path, "insight", tmp_path / "skills" / "a.md", "# A")
        assert not (tmp_path / "history").exists()
        assert not (tmp_path / "constitution").exists()

    def test_history_failure_never_blocks_adoption(self, tmp_path):
        (tmp_path / "identity.md").write_text("old\n")
        (tmp_path / "history").write_text("a file where the dir should go")
        self._stage_and_adopt(tmp_path, "distill-identity", tmp_path / "identity.md", "new self")
        assert (tmp_path / "identity.md").read_text() == "new self\n"
