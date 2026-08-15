"""skill/rules stocktake CLI tests — merge/clean phases (cli/stocktake_cmd.py).

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import json
from unittest.mock import MagicMock, patch

from contemplative_agent.cli.staging import StageItem
from contemplative_agent.cli.stocktake_cmd import (
    _handle_rules_stocktake,
    _handle_skill_stocktake,
    _stocktake_clean_phase,
)
from contemplative_agent.core.stocktake import MergeGroup


class TestStocktakeCleanStaging:
    """`_stocktake_clean_phase` with stage=True must stage each rewrite as an
    in-place overwrite of its own original (sources=[name]) — without the
    self-source, adopt-staged's collision guard mints a `-2.md` duplicate
    (2026-07-10 incident: 10 duplicates from one batch)."""

    def test_staged_clean_item_carries_self_source(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "a.md").write_text("# A original")
        staged_batch: list[StageItem] = []
        with patch(
            "contemplative_agent.cli.stocktake_cmd._clean_one_skill",
            return_value="# A cleaned",
        ):
            _stocktake_clean_phase(
                [("a.md", "# A original")],
                target_dir=skills_dir,
                command_prefix="skill-stocktake",
                clean_prompt="p",
                skip_names=set(),
                stage=True,
                staged_batch=staged_batch,
            )
        assert len(staged_batch) == 1
        item = staged_batch[0]
        assert item.sources == ["a.md"]
        assert item.target_path == skills_dir / "a.md"


class TestSkillStocktakeDirectMerge:
    """Tests for `skill-stocktake` direct-mode merge (no --stage).

    Regression guard: the direct branch must call `_log_approval` so that
    both accepted and rejected merges are recorded in audit.jsonl, matching
    distill-identity / insight / rules-distill / amend-constitution.
    """

    def _make_result(self, filenames, text="# Merged skill body"):
        from contemplative_agent.core.stocktake import (
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

        args = argparse.Namespace(stage=False)

        fake_result = self._make_result(["a.md", "b.md"])
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
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=inputs),
        ):
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

    def test_direct_merge_preserves_target_when_name_collides_with_source(self, tmp_path):
        """Regression: when LLM's merged title slugifies to an existing source
        filename, target_path == sources[0]. The delete loop must not unlink
        the file we just wrote. Previously this caused total loss of merge
        output (observed 2026-04-11 during resonant-fluidity merge)."""
        from contemplative_agent.core.stocktake import StocktakeResult

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "a.md").write_text("# A original")
        (skills_dir / "b.md").write_text("# B original")
        audit = tmp_path / "logs" / "audit.jsonl"

        args = argparse.Namespace(stage=False)

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
            merge_groups=(MergeGroup(filenames=(colliding, "b.md"), reason="dup"),),
            quality_issues=(),
            total_files=2,
            items=((colliding, "# X"), ("b.md", "# Y")),
        )
        # merged_text has no title -> _extract_title returns None -> slug falls
        # back to "merged-skill" -> filename becomes merged-skill-{today}.md
        # which matches `colliding`.
        merged_text = "No title here, just body prose.\n\nMore body."

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
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
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
        skills_dir, _ = self._run_direct(tmp_path, inputs=["y"], merged_text=merged_text)

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

        args = argparse.Namespace(stage=False)

        # No merges, no drops -> only the clean phase runs.
        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("solo.md", "# Solo\n\noriginal"),),
        )
        cleaned = "# Solo\n\noriginal\n\n## When to Use\nWhen a particular individual acts."
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.clean_skill_triggers",
                return_value=cleaned,
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
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

        args = argparse.Namespace(stage=False)

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
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.clean_skill_triggers",
                return_value=cleaned,
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
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

        args = argparse.Namespace(stage=False)

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
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.clean_skill_triggers",
                return_value=cleaned,
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
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
        args = argparse.Namespace(stage=False)

        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("solo.md", "# Solo original"),),
        )
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.clean_skill_triggers",
                return_value="CLEAN_NOOP",
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=AssertionError("no approval prompt expected")),
        ):
            _handle_skill_stocktake(args, MagicMock())

        # CLEAN_NOOP -> no rewrite, no approval prompt, file unchanged.
        assert (skills_dir / "solo.md").read_text() == "# Solo original"

    def test_merged_and_dropped_excluded_from_clean(self, tmp_path):
        """Files consumed by a merge or flagged for drop are not cleaned."""
        from contemplative_agent.core.stocktake import (
            QualityIssue,
            StocktakeResult,
        )

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for n in ("a.md", "b.md", "bad.md", "solo.md"):
            (skills_dir / n).write_text(f"# {n}")
        audit = tmp_path / "logs" / "audit.jsonl"
        args = argparse.Namespace(stage=False)

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

        def fake_clean(item, _prompt, _trace_sink=None):
            clean_calls.append(item[0])
            return "CLEAN_NOOP"

        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.merge_group",
                return_value="# Merged\n\nBody",
            ),
            patch(
                "contemplative_agent.core.stocktake.clean_skill_triggers",
                side_effect=fake_clean,
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y", "y"]),
        ):
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

        args = argparse.Namespace(stage=True)

        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("solo.md", "# Solo original"),),
        )
        cleaned = "# Solo\n\n## When to Use\nWhen a particular individual acts."
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_skill_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.clean_skill_triggers",
                return_value=cleaned,
            ),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
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
        args = argparse.Namespace(stage=False)

        fake_result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=1,
            items=(("r.md", "# Rule"),),
        )
        with (
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=None),
            patch(
                "contemplative_agent.core.stocktake.run_rules_stocktake",
                return_value=fake_result,
            ),
            patch(
                "contemplative_agent.core.stocktake.clean_skill_triggers",
            ) as mock_clean,
            patch("contemplative_agent.adapters.moltbook.config.RULES_DIR", rules_dir),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        ):
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

        args = argparse.Namespace(stage=False)

        fake_result = self._make_result(["a.md", "b.md"])
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
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=inputs),
        ):
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

    def test_direct_merge_preserves_target_when_name_collides_with_source(self, tmp_path):
        """Regression: same self-delete bug that hit skill-stocktake
        (commit 542f0b2). When the merged rule title slugifies to the
        name of one of the source rules, the delete loop must not unlink
        the file we just wrote."""
        from datetime import date

        from contemplative_agent.core.stocktake import StocktakeResult

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        audit = tmp_path / "logs" / "audit.jsonl"

        today = date.today().strftime("%Y%m%d")
        colliding = f"merged-rule-{today}.md"
        (rules_dir / colliding).write_text("# pre-existing content")
        (rules_dir / "b.md").write_text("# B original")

        args = argparse.Namespace(stage=False)

        fake_result = StocktakeResult(
            merge_groups=(MergeGroup(filenames=(colliding, "b.md"), reason="dup"),),
            quality_issues=(),
            total_files=2,
            items=((colliding, "# X"), ("b.md", "# Y")),
        )
        # No title in merged_text -> _extract_title returns None ->
        # slug falls back to "merged-rule" -> filename matches `colliding`.
        merged_text = "No title here, just rule body prose.\n\nMore body."

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
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("builtins.input", side_effect=["y"]),
        ):
            _handle_rules_stocktake(args, MagicMock())

        target = rules_dir / colliding
        assert target.exists(), "merge output was deleted by self-delete bug"
        assert merged_text in target.read_text()
        assert not (rules_dir / "b.md").exists()


class TestGroupingSectionInReasoning:
    """A no-verdict grouping is legible from the snapshot's reasoning.md,
    not only from stdout (ADR-0075 offline replay)."""

    def test_reason_appended_after_thinking(self):
        from contemplative_agent.cli.stocktake_cmd import _grouping_section
        from contemplative_agent.core.stocktake import StocktakeResult

        result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=3,
            thinking="considered the three",
            grouping_reason="GROUPING_UNPARSEABLE",
        )
        label, text = _grouping_section(result)
        assert label == "duplicate grouping"
        assert text is not None
        assert text.startswith("considered the three")
        assert "no verdict: GROUPING_UNPARSEABLE" in text

    def test_reason_alone_when_no_thinking(self):
        from contemplative_agent.cli.stocktake_cmd import _grouping_section
        from contemplative_agent.core.stocktake import StocktakeResult

        result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=3,
            grouping_reason="GROUPING_LLM_UNAVAILABLE",
        )
        assert _grouping_section(result) == (
            "duplicate grouping",
            "no verdict: GROUPING_LLM_UNAVAILABLE",
        )

    def test_clean_run_unchanged(self):
        from contemplative_agent.cli.stocktake_cmd import _grouping_section
        from contemplative_agent.core.stocktake import StocktakeResult

        result = StocktakeResult(
            merge_groups=(), quality_issues=(), total_files=3, thinking="trace"
        )
        assert _grouping_section(result) == ("duplicate grouping", "trace")
