"""skill/rules stocktake CLI tests — drop paths, staging coexistence, runtime routing (cli/stocktake_cmd.py).

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from contemplative_agent.cli import main
from contemplative_agent.cli.stocktake_cmd import (
    _handle_rules_stocktake,
    _handle_skill_stocktake,
    _labeled_sections,
    _stocktake_merge_phase,
)
from contemplative_agent.core.stocktake import MergeGroup


class TestSkillStocktakeDirectDrop:
    """Tests for skill-stocktake direct-mode drop (quality issue deletion)."""

    def _make_result_with_quality_issues(self, quality_files, body="short"):
        from contemplative_agent.core.stocktake import QualityIssue, StocktakeResult

        return StocktakeResult(
            merge_groups=(),
            quality_issues=tuple(
                QualityIssue(filename=f, reason="body < 200 chars") for f in quality_files
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

        args = argparse.Namespace(stage=False)

        fake_result = self._make_result_with_quality_issues(quality_files)
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=inputs),
        ):
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

        args = argparse.Namespace(stage=True)

        fake_result = self._make_result_with_quality_issues(["lq.md"])
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
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

        args = argparse.Namespace(stage=False)

        fake_result = self._make_result_with_quality_issues(quality_files)
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_rules_stocktake",
                return_value=fake_result,
            ),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", rules_dir),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=inputs),
        ):
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

        args = argparse.Namespace(stage=True)

        fake_result = self._make_result_with_quality_issues(["old-rule.md"])
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_rules_stocktake",
                return_value=fake_result,
            ),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", rules_dir),
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
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
            QualityIssue,
            StocktakeResult,
        )

        return StocktakeResult(
            merge_groups=(MergeGroup(filenames=tuple(merge_files), reason="dup"),),
            quality_issues=tuple(
                QualityIssue(filename=f, reason="missing section") for f in quality_files
            ),
            total_files=len(merge_files) + len(quality_files),
            items=tuple((f, body) for f in (*merge_files, *quality_files)),
        )

    def test_skill_stage_merge_and_drop_both_survive(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for f in ("a.md", "b.md", "lq.md"):
            (skills_dir / f).write_text("# body")
        staged_dir = tmp_path / ".staged"
        audit = tmp_path / "logs" / "audit.jsonl"

        args = argparse.Namespace(stage=True)

        fake_result = self._make_mixed_result(
            merge_files=("a.md", "b.md"),
            quality_files=("lq.md",),
        )
        merged_text = "# Merged Skill\n\n## Problem\nx\n\n## Solution\ny\n"

        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.merge_group",
                return_value=merged_text,
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _handle_skill_stocktake(args, MagicMock())

        meta_files = sorted(staged_dir.glob("*.meta.json"))
        assert len(meta_files) == 2, (
            f"expected 2 staged items (1 merge + 1 drop), got {len(meta_files)}: "
            f"{[p.name for p in meta_files]}"
        )

        commands = sorted(json.loads(p.read_text())["command"] for p in meta_files)
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

        args = argparse.Namespace(stage=True)

        fake_result = self._make_mixed_result(
            merge_files=("a.md", "b.md"),
            quality_files=("lq.md",),
        )
        merged_text = "# Merged Rule\n\n**Practice:** do x\n\n**Rationale:** because y\n"

        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_rules_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.merge_group",
                return_value=merged_text,
            ),
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", rules_dir),
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
            _handle_rules_stocktake(args, MagicMock())

        meta_files = sorted(staged_dir.glob("*.meta.json"))
        assert len(meta_files) == 2, (
            f"expected 2 staged items (1 merge + 1 drop), got {len(meta_files)}: "
            f"{[p.name for p in meta_files]}"
        )

        commands = sorted(json.loads(p.read_text())["command"] for p in meta_files)
        assert commands == ["rules-stocktake", "rules-stocktake-drop"]

        drop_meta = json.loads((staged_dir / "lq.md.meta.json").read_text())
        assert drop_meta["action"] == "drop"
        assert drop_meta["command"] == "rules-stocktake-drop"


class TestStocktakeRuntimeRouting:
    """M1 (review 2026-06-27): stocktake commands previously sat in
    ``no_llm_handlers`` and returned before any LLM setup, so per-call
    telemetry was silently skipped (it only "worked" because Ollama is the
    default). They now route through a Tier 1.5 runtime path that applies
    telemetry WITHOUT loading the skills/rules/axioms corpus (stocktake passes
    its own system prompts)."""

    @patch("contemplative_agent.cli.stocktake_cmd._handle_skill_stocktake")
    @patch("contemplative_agent.cli.runtime.configure_llm")
    def test_skill_stocktake_applies_telemetry(self, mock_configure, mock_handler):
        with patch("sys.argv", ["contemplative-agent", "skill-stocktake"]):
            main()
        mock_handler.assert_called_once()
        kwargs_list = [c.kwargs for c in mock_configure.call_args_list]
        # telemetry applied
        assert any("telemetry_dir" in kw for kw in kwargs_list)
        # clean prompt environment: corpus NOT loaded
        assert not any("skills_dir" in kw for kw in kwargs_list)
        assert not any("rules_dir" in kw for kw in kwargs_list)
        assert not any("axiom_prompt" in kw for kw in kwargs_list)

    @patch("contemplative_agent.cli.stocktake_cmd._handle_rules_stocktake")
    @patch("contemplative_agent.cli.runtime.configure_llm")
    def test_rules_stocktake_applies_telemetry(self, mock_configure, mock_handler):
        with patch("sys.argv", ["contemplative-agent", "rules-stocktake"]):
            main()
        mock_handler.assert_called_once()
        kwargs_list = [c.kwargs for c in mock_configure.call_args_list]
        assert any("telemetry_dir" in kw for kw in kwargs_list)
        assert not any("skills_dir" in kw for kw in kwargs_list)


class TestStocktakeTraceLabels:
    """Round-2 R2-L1: reasoning.md sections carry the operation's real label
    (console group number / skill filename) instead of list position, so a
    skipped group no longer shifts later traces onto the wrong slot."""

    def test_merge_labels_survive_skipped_group(self, tmp_path):
        groups = [
            MergeGroup(filenames=("a.md", "b.md"), reason="dup"),
            MergeGroup(filenames=("c.md", "d.md"), reason="dup"),
            MergeGroup(filenames=("e.md", "f.md"), reason="dup"),
        ]
        items = {n: f"# {n}" for n in ("a.md", "b.md", "c.md", "d.md", "e.md", "f.md")}
        traces: list[str] = []
        labels: list[str] = []
        calls = {"n": 0}

        def fake_render(group_items, prompt, fallback, sink):
            calls["n"] += 1
            if calls["n"] == 2:
                return None  # LLM error: no trace appended for group 2
            sink.append(f"thinking {calls['n']}")
            return (f"merged-{calls['n']}.md", "# Merged")

        with patch(
            "contemplative_agent.cli.stocktake_cmd._render_merged_group", side_effect=fake_render
        ):
            _stocktake_merge_phase(
                groups,
                items,
                target_dir=tmp_path,
                merge_prompt="p",
                command_prefix="skill-stocktake",
                fallback_title="merged",
                stage=True,
                staged_batch=[],
                trace_sink=traces,
                trace_labels=labels,
            )
        assert labels == ["group 1", "group 3"]
        assert _labeled_sections("merge", labels, traces) == [
            ("merge group 1", "thinking 1"),
            ("merge group 3", "thinking 3"),
        ]

    def test_labeled_sections_mismatch_falls_back_positional(self):
        # Defensive: a labels/traces desync (future plumbing bug) must not
        # silently drop traces via zip truncation.
        assert _labeled_sections("merge", ["group 1"], ["t1", "t2"]) == [
            ("merge 1", "t1"),
            ("merge 2", "t2"),
        ]


class TestDropFlaggedVersusRemoved:
    """A quality-flagged file the operator KEEPS is not the same as a removed one.

    The clean phase wants *flagged* (no point tidying a file this run proposes
    to delete); the description audit wants *removed* (a kept file stays in the
    selector catalog, so its description still needs checking — codex review
    2026-07-24). Conflating the two sets was the original bug; these tests pin
    which phase reads which.
    """

    @staticmethod
    def _result(items, flagged):
        from contemplative_agent.core.stocktake import QualityIssue, StocktakeResult

        return StocktakeResult(
            merge_groups=(),
            quality_issues=tuple(QualityIssue(filename=n, reason="thin") for n in flagged),
            total_files=len(items),
            items=tuple(items),
        )

    def _run(self, *, removed):
        from contemplative_agent.cli.stocktake_cmd import StocktakeRun, _run_stocktake_phases

        items = [("keep.md", "body a"), ("flagged.md", "body b")]
        captured = {}

        def _fake_drop(*_a, **_kw):
            return set(removed)

        def _fake_clean(*_a, **kw):
            captured["clean_skip"] = kw["skip_names"]

        def _fake_desc(*_a, **kw):
            captured["desc_skip"] = kw["skip_names"]

        run = StocktakeRun(
            args=argparse.Namespace(stage=False),
            target_dir=Path("/nonexistent"),
            label="Skill",
            merge_prompt="m",
            command_prefix="skill-stocktake",
            fallback_title="merged-skill",
            clean_prompt="c",
            desc_prompt="d",
        )
        with (
            patch("contemplative_agent.cli.stocktake_cmd._stocktake_drop_phase", _fake_drop),
            patch("contemplative_agent.cli.stocktake_cmd._stocktake_clean_phase", _fake_clean),
            patch("contemplative_agent.cli.stocktake_cmd._stocktake_description_phase", _fake_desc),
            patch("contemplative_agent.cli.stocktake_cmd.memory_cmds._write_reasoning"),
            patch("contemplative_agent.core.stocktake.format_stocktake_report", return_value=""),
        ):
            _run_stocktake_phases(run, self._result(items, ["flagged.md"]))
        return captured

    def test_kept_flagged_file_is_skipped_by_clean(self):
        captured = self._run(removed=set())
        assert "flagged.md" in captured["clean_skip"]

    def test_kept_flagged_file_is_still_description_audited(self):
        # Operator kept it: not removed, so it stays in the catalog and its
        # description must still be audited.
        captured = self._run(removed=set())
        assert "flagged.md" not in captured["desc_skip"]

    def test_removed_file_is_skipped_by_both(self):
        captured = self._run(removed={"flagged.md"})
        assert "flagged.md" in captured["clean_skip"]
        assert "flagged.md" in captured["desc_skip"]

    def test_surviving_file_is_never_skipped(self):
        captured = self._run(removed={"flagged.md"})
        assert "keep.md" not in captured["clean_skip"]
        assert "keep.md" not in captured["desc_skip"]
