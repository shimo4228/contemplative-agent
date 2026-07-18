"""Memory-pipeline CLI tests (cli/memory_cmds.py).

Split from the single-file test_cli.py alongside the cli/ package split
(ADR-0079 Phase 2).
"""

import argparse
import json
from unittest.mock import MagicMock, patch

from contemplative_agent.cli.memory_cmds import _write_reasoning
from contemplative_agent.cli.stocktake_cmd import (
    _handle_stocktake_result,
)


class TestWriteReasoning:
    """ADR-0069: think-ON value-layer pipelines write their reasoning trace to
    reasoning.md beside the run's snapshot (not into the input manifest)."""

    def test_writes_sections_to_reasoning_md(self, tmp_path):
        _write_reasoning(tmp_path, [("identity", "first reason"), ("rule a", "second reason")])
        content = (tmp_path / "reasoning.md").read_text()
        assert "## identity" in content
        assert "first reason" in content
        assert "## rule a" in content
        assert "second reason" in content

    def test_dedupes_identical_traces(self, tmp_path):
        # rules-distill shares one batch trace across its rules — write it once.
        _write_reasoning(tmp_path, [("rule 1", "same trace"), ("rule 2", "same trace")])
        content = (tmp_path / "reasoning.md").read_text()
        assert content.count("same trace") == 1

    def test_skips_empty_and_none_traces(self, tmp_path):
        _write_reasoning(tmp_path, [("a", None), ("b", "")])
        assert not (tmp_path / "reasoning.md").exists()

    def test_noop_when_snapshot_path_none(self):
        # No snapshot (e.g. --dry-run) → nothing to do, no crash.
        _write_reasoning(None, [("a", "trace")])

    def test_defangs_urls_in_trace(self, tmp_path):
        _write_reasoning(tmp_path, [("a", "see https://evil.example.com/x for more")])
        content = (tmp_path / "reasoning.md").read_text()
        assert "https://evil.example.com/x" not in content

    def test_stocktake_grouping_trace_written_to_reasoning_md(self, tmp_path):
        """ADR-0069 integration: a stocktake run with nothing to merge/drop
        still persists its grouping reasoning to reasoning.md beside the snapshot."""
        from contemplative_agent.core.stocktake import StocktakeResult

        result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=3,
            items=(),
            thinking="these three rules are genuinely distinct",
        )
        # rules path: clean_prompt=None → early return after writing the trace.
        _handle_stocktake_result(
            MagicMock(),
            result,
            target_dir=tmp_path / "rules",
            label="Rules",
            merge_prompt="m {candidates}",
            command_prefix="rules-stocktake",
            fallback_title="merged-rule",
            clean_prompt=None,
            snapshot_path=tmp_path,
        )
        content = (tmp_path / "reasoning.md").read_text()
        assert "## duplicate grouping" in content
        assert "these three rules are genuinely distinct" in content


class TestInsightStagePathADR0074:
    """insight --stage: pending guard fast-fail, marker advance, staged ledger."""

    def _run(self, tmp_path, insight_result, *, prefill_staging=False):
        from contemplative_agent.core.insight import InsightResult, SkillResult

        staged_dir = tmp_path / ".staged"
        skills_dir = tmp_path / "skills"
        ledger = tmp_path / "logs" / "insight-staged.jsonl"
        audit = tmp_path / "logs" / "audit.jsonl"
        if prefill_staging:
            staged_dir.mkdir(parents=True)
            (staged_dir / "old.md").write_text("# Old\n")
            (staged_dir / "old.md.meta.json").write_text('{"target": "x"}\n')

        if insight_result == "one-skill":
            insight_result = InsightResult(
                skills=(
                    SkillResult(
                        text=(
                            "---\n"
                            "name: fresh-theme\n"
                            'description: "A fresh theme"\n'
                            "origin: auto-extracted\n"
                            "---\n\n# Fresh Theme\n\nbody\n"
                        ),
                        filename="fresh-theme-20260709.md",
                        target_path=skills_dir / "fresh-theme-20260709.md",
                    ),
                ),
                dropped_count=0,
            )

        args = argparse.Namespace(stage=True, full=False)
        with (
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
            patch("contemplative_agent.cli.adopt.INSIGHT_STAGED_LEDGER_PATH", ledger),
            patch("contemplative_agent.cli.memory_cmds._load_view_registry", return_value=None),
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=tmp_path),
            patch(
                "contemplative_agent.core.insight.extract_insight",
                return_value=insight_result,
            ) as mock_extract,
        ):
            from contemplative_agent.cli.memory_cmds import _handle_insight

            _handle_insight(args, MagicMock())
        return staged_dir, skills_dir, ledger, mock_extract

    def test_stage_success_advances_marker_and_ledger(self, tmp_path):
        staged_dir, skills_dir, ledger, _ = self._run(tmp_path, "one-skill")
        assert (staged_dir / "fresh-theme-20260709.md").exists()
        assert (skills_dir / ".last_insight").exists()
        record = json.loads(ledger.read_text().strip())
        assert record["name"] == "fresh-theme"
        assert record["description"] == "A fresh theme"

    def test_pending_staging_blocks_before_extraction(self, tmp_path, capsys):
        staged_dir, skills_dir, ledger, mock_extract = self._run(
            tmp_path, "one-skill", prefill_staging=True
        )
        mock_extract.assert_not_called()
        assert not (skills_dir / ".last_insight").exists()
        assert not ledger.exists()
        assert (staged_dir / "old.md").exists()
        assert "adopt-staged" in capsys.readouterr().out

    def test_all_covered_advances_marker_without_staging(self, tmp_path):
        from contemplative_agent.core.insight import InsightResult

        empty = InsightResult(skills=(), dropped_count=0, skipped_known=3)
        staged_dir, skills_dir, ledger, _ = self._run(tmp_path, empty)
        assert (skills_dir / ".last_insight").exists()
        assert not ledger.exists()
        assert not any(staged_dir.glob("*.md")) if staged_dir.exists() else True


class TestLoadViewRegistryPlaceholderKey:
    """Regression (codex P1, ADR-0079 Phase 4): _load_view_registry must pass
    path_vars keyed by the literal placeholder name ``CONSTITUTION_DIR`` — the
    key is a ``${VAR}`` template variable inside view files, not a Python
    reference. A mechanical rename of the key (e.g. to "config.CONSTITUTION_DIR")
    leaves every ``seed_from: ${CONSTITUTION_DIR}/*.md`` unresolved and the
    registry silently falls back to the generic seed body."""

    def test_constitution_placeholder_resolves_to_live_seed(self, tmp_path):
        from contemplative_agent.cli import memory_cmds

        const_dir = tmp_path / "constitution"
        const_dir.mkdir()
        (const_dir / "clause.md").write_text("LIVE CONSTITUTION CLAUSE", encoding="utf-8")
        views_dir = tmp_path / "views"
        views_dir.mkdir()
        (views_dir / "constitutional.md").write_text(
            "---\nseed_from: ${CONSTITUTION_DIR}/*.md\n---\n\nfallback body\n",
            encoding="utf-8",
        )
        with (
            patch("contemplative_agent.cli.memory_cmds._resolve_views_dir", return_value=views_dir),
            patch("contemplative_agent.adapters.moltbook.config.CONSTITUTION_DIR", const_dir),
        ):
            registry = memory_cmds._load_view_registry(args=None)
        view = registry.get("constitutional")
        assert view is not None
        assert view.seed_text == "LIVE CONSTITUTION CLAUSE"  # not the fallback body
