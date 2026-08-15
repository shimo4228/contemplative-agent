"""Tests for core.stocktake — skill and rule auditing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from contemplative_agent.core.llm import GenerationOutput
from contemplative_agent.core.stocktake import (
    _CLEAN_TOKENS,
    _DEFAULT_CLEAN_SYSTEM,
    _DEFAULT_GROUP_SYSTEM,
    _DEFAULT_MERGE_SYSTEM,
    _PER_FILE_MERGE_TOKENS,
    MergeGroup,
    QualityIssue,
    StocktakeResult,
    _check_rule_quality,
    _check_skill_quality,
    _find_duplicate_groups,
    _parse_groups,
    clean_skill_triggers,
    format_stocktake_report,
    is_clean_noop,
    is_merge_rejected,
    merge_group,
    run_rules_stocktake,
    run_skill_stocktake,
)
from contemplative_agent.core.text_utils import read_markdown_documents, strip_frontmatter

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_SKILL = """\
---
name: test-skill
description: "A test skill"
origin: auto-extracted
---

# Test Skill

**Context:** Testing context.

## Problem
Agents struggle with test scenarios.

## Solution
Apply test-driven techniques consistently.

## When to Use
During test execution phases where coverage is insufficient.
This requires careful attention to edge cases and boundary conditions.
"""

GOOD_SKILL_NO_FRONTMATTER = """\
# Another Skill

**Context:** Different context.

## Problem
Agents have a different problem here.

## Solution
Use a completely different approach to solve this issue.

## When to Use
When the first approach doesn't work and alternatives are needed.
This is a fallback strategy for complex scenarios.
"""

SHORT_SKILL = """\
# Too Short

Brief content.
"""

MISSING_PROBLEM_SKILL = """\
# No Problem Section

**Context:** This skill is missing the Problem section entirely.

## Solution
Some solution without stating the problem first.
Continue with more content to pass the length check.
More content here to make it long enough for the quality gate.
Even more padding to ensure we exceed the 200 character minimum threshold for the quality check.
"""

GOOD_RULE = """\
# Engagement Practices

## Rule 1: Ask Before Reacting

**Practice:** Always ask clarifying questions before forming a response when encountering unfamiliar viewpoints.
**Rationale:** Premature responses reduce engagement quality and miss important context across nearly every conversational skill the agent has learned.

## Rule 2: Listen First

**Practice:** Process and reflect before generating output whenever new information arrives from an external source.
**Rationale:** Hasty responses consistently miss important nuances, regardless of the specific domain of the input.
"""

MISSING_PRACTICE_RULE = """\
# Incomplete Rule

## Rule 1: Some Rule

**Rationale:** Because reasons that span enough text to pass the length check.
More content here to ensure we exceed the minimum character threshold of two hundred chars for the quality check.
"""

# LLM grouping responses (single-call duplicate detection)
LLM_MERGE_RESPONSE = json.dumps(
    {
        "groups": [
            {
                "files": ["skill-a.md", "skill-b.md"],
                "reason": "Both describe the same response loop",
            },
        ]
    }
)
LLM_NO_MERGE_RESPONSE = json.dumps({"groups": []})


def _make_skills_dir(tmp_path: Path, skills: dict[str, str]) -> Path:
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    for name, content in skills.items():
        (skills_dir / name).write_text(content, encoding="utf-8")
    return skills_dir


def _make_rules_dir(tmp_path: Path, rules: dict[str, str]) -> Path:
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir()
    for name, content in rules.items():
        (rules_dir / name).write_text(content, encoding="utf-8")
    return rules_dir


# ---------------------------------------------------------------------------
# Unit tests: read_markdown_documents (the stocktake reader)
# ---------------------------------------------------------------------------


class TestReadMarkdownDocuments:
    def test_reads_raw_and_stripped_body(self, tmp_path):
        d = tmp_path / "files"
        d.mkdir()
        (d / "test.md").write_text(GOOD_SKILL)
        docs = read_markdown_documents(d)
        assert len(docs) == 1
        name, raw, body = docs[0]
        assert name == "test.md"
        assert raw.startswith("---")
        assert not body.startswith("---")

    def test_skips_dotfiles(self, tmp_path):
        d = tmp_path / "files"
        d.mkdir()
        # ``*.md`` glob matches a leading dot, so the dotfile skip is real.
        (d / ".hidden.md").write_text("# Hidden\nContent here.")
        (d / "visible.md").write_text("# Visible\nContent here.")
        assert [name for name, _raw, _body in read_markdown_documents(d)] == ["visible.md"]

    def test_skips_empty_body(self, tmp_path):
        d = tmp_path / "files"
        d.mkdir()
        (d / "fm-only.md").write_text("---\nname: x\n---\n")
        assert read_markdown_documents(d) == []

    def test_empty_dir(self, tmp_path):
        d = tmp_path / "files"
        d.mkdir()
        assert read_markdown_documents(d) == []

    def test_nonexistent_dir(self, tmp_path):
        assert read_markdown_documents(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# Unit tests: _parse_groups
# ---------------------------------------------------------------------------


class TestParseGroups:
    def test_valid_json(self):
        groups = _parse_groups(LLM_MERGE_RESPONSE)
        assert groups is not None
        assert len(groups) == 1
        assert groups[0].filenames == ("skill-a.md", "skill-b.md")

    def test_empty_groups(self):
        assert _parse_groups(LLM_NO_MERGE_RESPONSE) == []

    def test_json_in_code_fence(self):
        raw = f"```json\n{LLM_MERGE_RESPONSE}\n```"
        groups = _parse_groups(raw)
        assert groups is not None
        assert len(groups) == 1

    def test_json_embedded_in_prose(self):
        raw = f"Here are the groups:\n{LLM_MERGE_RESPONSE}\nDone."
        groups = _parse_groups(raw)
        assert groups is not None
        assert len(groups) == 1

    def test_invalid_json_is_none_not_empty(self):
        # None (no verdict) is distinct from [] (verdict: no duplicates).
        assert _parse_groups("not json at all") is None

    def test_schema_invalid_json_is_none(self):
        # Valid JSON that is not a grouping verdict (codex review 2026-08-15).
        assert _parse_groups("{}") is None
        assert _parse_groups('{"groups": "none"}') is None
        assert _parse_groups('[{"files": ["a.md", "b.md"], "reason": "x"}]') is None
        # The genuine empty verdict stays a list.
        assert _parse_groups('{"groups": []}') == []

    def test_single_file_group_ignored(self):
        raw = json.dumps({"groups": [{"files": ["only-one.md"], "reason": "alone"}]})
        assert _parse_groups(raw) == []

    def test_group_without_reason_ignored(self):
        raw = json.dumps({"groups": [{"files": ["a.md", "b.md"], "reason": ""}]})
        assert _parse_groups(raw) == []


# ---------------------------------------------------------------------------
# Unit tests: quality checks
# ---------------------------------------------------------------------------


class TestSkillQuality:
    def test_good_skill(self):
        body = GOOD_SKILL.split("---")[-1].strip()
        assert _check_skill_quality("good.md", body) is None

    def test_too_short(self):
        issue = _check_skill_quality("short.md", "Brief.")
        assert issue is not None
        assert "200 chars" in issue.reason

    def test_missing_problem(self):
        issue = _check_skill_quality("no-problem.md", MISSING_PROBLEM_SKILL)
        assert issue is not None
        assert "Problem" in issue.reason

    def test_missing_solution(self):
        body = "# Skill\n\n## Problem\nSome problem.\n" + "x" * 200
        issue = _check_skill_quality("no-solution.md", body)
        assert issue is not None
        assert "Solution" in issue.reason


class TestRuleQuality:
    def test_good_rule(self):
        assert _check_rule_quality("good.md", GOOD_RULE) is None

    def test_too_short(self):
        issue = _check_rule_quality("short.md", "Brief.")
        assert issue is not None
        assert "200 chars" in issue.reason

    def test_missing_practice(self):
        issue = _check_rule_quality("no-practice.md", MISSING_PRACTICE_RULE)
        assert issue is not None
        assert "Practice" in issue.reason


# ---------------------------------------------------------------------------
# Unit tests: _find_duplicate_groups (single LLM grouping call)
# ---------------------------------------------------------------------------


class TestFindDuplicateGroups:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_returns_merge_groups(self, mock_generate):
        mock_generate.return_value = GenerationOutput(text=LLM_MERGE_RESPONSE)
        # Filenames must match the mocked LLM response: _parse_groups now
        # drops names that are not in the known set (codex review 2026-07-06).
        items = [("skill-a.md", "content a"), ("skill-b.md", "content b")]
        result = _find_duplicate_groups(items, "prompt {items}")
        assert len(result.groups) == 1
        assert result.reason is None
        assert mock_generate.call_count == 1

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_no_duplicates_returns_empty(self, mock_generate):
        mock_generate.return_value = GenerationOutput(text=LLM_NO_MERGE_RESPONSE)
        items = [("a.md", "content a"), ("b.md", "content b")]
        assert _find_duplicate_groups(items, "prompt {items}").groups == ()

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_multiple_groups_not_collapsed(self, mock_generate):
        """Distinct families stay separate — the grouping call can return
        several small groups rather than one over-merged blob."""
        mock_generate.return_value = GenerationOutput(
            text=json.dumps(
                {
                    "groups": [
                        {"files": ["a.md", "b.md"], "reason": "family one"},
                        {"files": ["c.md", "d.md"], "reason": "family two"},
                    ]
                }
            )
        )
        items = [(f"{c}.md", f"body {c}") for c in "abcd"]
        assert len(_find_duplicate_groups(items, "prompt {items}").groups) == 2

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_llm_failure_returns_empty(self, mock_generate):
        mock_generate.return_value = None
        items = [("a.md", "content a"), ("b.md", "content b")]
        assert _find_duplicate_groups(items, "prompt {items}").groups == ()

    def test_single_file_skips_llm(self):
        items = [("a.md", "content a")]
        assert _find_duplicate_groups(items, "prompt {items}").groups == ()

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_grouping_token_budget_has_floor(self, mock_generate):
        """Small stores still get a generous budget so the JSON is not
        truncated (truncation would corrupt parsing and drop groups)."""
        mock_generate.return_value = GenerationOutput(text=LLM_NO_MERGE_RESPONSE)
        items = [("a.md", "x"), ("b.md", "y")]
        _find_duplicate_groups(items, "prompt {items}")
        assert mock_generate.call_args.kwargs["num_predict"] == 3000


# ---------------------------------------------------------------------------
# Unit tests: merge_group + is_merge_rejected
# ---------------------------------------------------------------------------


class TestMergeGroup:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_returns_merged_text(self, mock_generate):
        mock_generate.return_value = GenerationOutput(
            text="# Merged Skill\n\n## Problem\nCombined.\n\n## Solution\nUnified."
        )
        items = [("a.md", "content a"), ("b.md", "content b")]
        result = merge_group(items, "merge {candidates}")
        assert result is not None
        assert "# Merged Skill" in result

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_llm_failure(self, mock_generate):
        mock_generate.return_value = None
        items = [("a.md", "content a"), ("b.md", "content b")]
        assert merge_group(items, "merge {candidates}") is None

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_cannot_merge_returned_verbatim(self, mock_generate):
        """LLM reject path: CANNOT_MERGE is returned as-is for caller inspection."""
        mock_generate.return_value = GenerationOutput(text="CANNOT_MERGE: distinct behaviors.")
        items = [("a.md", "content a"), ("b.md", "content b")]
        result = merge_group(items, "merge {candidates}")
        assert result is not None
        assert result.startswith("CANNOT_MERGE:")

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_small_group_keeps_floor_budget(self, mock_generate):
        """A 2-file merge keeps the 3000-token floor (prior behavior)."""
        mock_generate.return_value = GenerationOutput(
            text="# Merged\n\n## Problem\np\n\n## Solution\ns"
        )
        items = [("a.md", "x"), ("b.md", "y")]
        merge_group(items, "merge {candidates}")
        assert mock_generate.call_args.kwargs["num_predict"] == 3000

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_token_budget_scales_with_group_size(self, mock_generate):
        """Pattern-preserving merge output grows with inputs, so the token
        budget scales above the floor — preventing truncation that would
        silently drop the distinct patterns the merge exists to preserve."""
        mock_generate.return_value = GenerationOutput(
            text="# Merged\n\n## Problem\np\n\n## Solution\ns"
        )
        items = [(f"f{i}.md", f"body {i}") for i in range(12)]
        merge_group(items, "merge {candidates}")
        assert mock_generate.call_args.kwargs["num_predict"] == _PER_FILE_MERGE_TOKENS * 12

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_token_budget_capped_at_ceiling(self, mock_generate):
        """Very large groups are capped at 8192 (num_ctx headroom)."""
        mock_generate.return_value = GenerationOutput(
            text="# Merged\n\n## Problem\np\n\n## Solution\ns"
        )
        items = [(f"f{i}.md", f"body {i}") for i in range(40)]
        merge_group(items, "merge {candidates}")
        assert mock_generate.call_args.kwargs["num_predict"] == 8192


class TestIsMergeRejected:
    def test_detects_plain(self):
        assert is_merge_rejected("CANNOT_MERGE: reason") is True

    def test_detects_with_leading_whitespace(self):
        assert is_merge_rejected("\n  CANNOT_MERGE: reason") is True

    def test_rejects_merged_output(self):
        assert is_merge_rejected("# Merged Skill\n\n## Problem\n...") is False

    def test_rejects_empty(self):
        assert is_merge_rejected("") is False


# ---------------------------------------------------------------------------
# Unit tests: clean_skill_triggers + is_clean_noop (singleton trigger-altitude)
# ---------------------------------------------------------------------------


class TestCleanSkillTriggers:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_returns_cleaned_text(self, mock_generate):
        mock_generate.return_value = GenerationOutput(
            text="# Skill\n\n## When to Use\nWhen a particular individual acts."
        )
        result = clean_skill_triggers(
            ("solo.md", "# Skill\n\n## When to Use\nWhen Count1 acts at 09:35."),
            "clean {skill}",
        )
        assert result is not None
        assert "a particular individual" in result

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_llm_failure(self, mock_generate):
        mock_generate.return_value = None
        assert clean_skill_triggers(("solo.md", "body"), "clean {skill}") is None

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_noop_returned_for_caller_inspection(self, mock_generate):
        """Already-clean skills get CLEAN_NOOP, returned as-is for the caller."""
        mock_generate.return_value = GenerationOutput(text="CLEAN_NOOP")
        result = clean_skill_triggers(("solo.md", "body"), "clean {skill}")
        assert result == "CLEAN_NOOP"

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_passes_skill_body_into_prompt(self, mock_generate):
        """The {skill} placeholder receives the body; braces in the body are
        safe (they are an argument, not part of the format template)."""
        mock_generate.return_value = GenerationOutput(text="CLEAN_NOOP")
        clean_skill_triggers(("solo.md", "UNIQUE_BODY_MARKER {x}"), "clean: {skill}")
        assert "UNIQUE_BODY_MARKER {x}" in mock_generate.call_args.args[0]

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_token_budget(self, mock_generate):
        mock_generate.return_value = GenerationOutput(text="CLEAN_NOOP")
        clean_skill_triggers(("solo.md", "body"), "clean {skill}")
        assert mock_generate.call_args.kwargs["num_predict"] == _CLEAN_TOKENS


class TestIsCleanNoop:
    def test_detects_plain(self):
        assert is_clean_noop("CLEAN_NOOP") is True

    def test_detects_with_leading_whitespace(self):
        assert is_clean_noop("\n  CLEAN_NOOP") is True

    def test_detects_with_trailing_whitespace(self):
        assert is_clean_noop("CLEAN_NOOP\n") is True

    def test_rejects_skill_output(self):
        assert is_clean_noop("# Skill\n\n## When to Use\n...") is False

    def test_rejects_empty(self):
        assert is_clean_noop("") is False


# ---------------------------------------------------------------------------
# Integration tests: run_skill_stocktake
# ---------------------------------------------------------------------------


class TestRunSkillStocktake:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_detects_merges_and_quality(self, mock_generate, tmp_path):
        mock_generate.return_value = GenerationOutput(
            text=json.dumps({"groups": [{"files": ["a.md", "b.md"], "reason": "overlap"}]})
        )
        skills_dir = _make_skills_dir(
            tmp_path,
            {
                "a.md": GOOD_SKILL,
                "b.md": GOOD_SKILL_NO_FRONTMATTER,
                "short.md": SHORT_SKILL,
            },
        )
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert isinstance(result, StocktakeResult)
        assert len(result.merge_groups) == 1
        assert len(result.quality_issues) >= 1  # short.md
        assert result.total_files == 3

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_no_issues(self, mock_generate, tmp_path):
        # Single file: below MIN_FILES_FOR_DEDUP, so grouping LLM not invoked
        skills_dir = _make_skills_dir(
            tmp_path,
            {
                "good.md": GOOD_SKILL,
            },
        )
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert result.merge_groups == ()
        assert result.quality_issues == ()
        assert mock_generate.call_count == 0

    def test_empty_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert result.total_files == 0

    def test_nonexistent_dir(self, tmp_path):
        result = run_skill_stocktake(skills_dir=tmp_path / "nope")
        assert result.total_files == 0


# ---------------------------------------------------------------------------
# Integration tests: run_rules_stocktake
# ---------------------------------------------------------------------------


class TestRunRulesStocktake:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_detects_quality_issue(self, mock_generate, tmp_path):
        mock_generate.return_value = GenerationOutput(text=LLM_NO_MERGE_RESPONSE)
        rules_dir = _make_rules_dir(
            tmp_path,
            {
                "good.md": GOOD_RULE,
                "bad.md": MISSING_PRACTICE_RULE,
            },
        )
        result = run_rules_stocktake(rules_dir=rules_dir)
        assert len(result.quality_issues) >= 1
        assert result.total_files == 2

    def test_empty_dir(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        result = run_rules_stocktake(rules_dir=rules_dir)
        assert result.total_files == 0


# ---------------------------------------------------------------------------
# Integration tests: run independently
# ---------------------------------------------------------------------------


class TestIndependence:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_skills_and_rules_do_not_mix(self, mock_generate, tmp_path):
        """Skill stocktake does not read rules, and vice versa."""
        skills_dir = _make_skills_dir(tmp_path, {"s.md": GOOD_SKILL})
        rules_dir = _make_rules_dir(tmp_path, {"r.md": GOOD_RULE})

        skill_result = run_skill_stocktake(skills_dir=skills_dir)
        rule_result = run_rules_stocktake(rules_dir=rules_dir)

        assert skill_result.total_files == 1
        assert rule_result.total_files == 1
        # Each only saw its own file; grouping skipped (below MIN_FILES_FOR_DEDUP)
        assert mock_generate.call_count == 0


# ---------------------------------------------------------------------------
# Format report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_format_with_issues(self):
        result = StocktakeResult(
            merge_groups=(MergeGroup(("a.md", "b.md"), "overlap"),),
            quality_issues=(QualityIssue("c.md", "too short"),),
            total_files=3,
        )
        report = format_stocktake_report(result, "Skill")
        assert "Skill Stocktake Report" in report
        assert "a.md, b.md" in report
        assert "overlap" in report
        assert "c.md" in report
        assert "1 merge group" in report

    def test_format_clean(self):
        result = StocktakeResult(merge_groups=(), quality_issues=(), total_files=5)
        report = format_stocktake_report(result, "Rules")
        assert "No duplicates" in report
        assert "5 healthy" in report


# ---------------------------------------------------------------------------
# ADR-0054: the stocktake system prompts are externalized to config/prompts/.
# When the template is missing (lazy loader yields ""), the hardcoded default
# must reach the LLM call so behavior is unchanged.
class TestSystemPromptFallback:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_group_system_falls_back_to_default(self, mock_generate, monkeypatch):
        monkeypatch.setattr(
            "contemplative_agent.core.prompts.STOCKTAKE_GROUP_SYSTEM_PROMPT",
            "",
            raising=False,
        )
        mock_generate.return_value = GenerationOutput(text='{"groups": []}')
        _find_duplicate_groups([("a.md", "body a"), ("b.md", "body b")], "prompt {items}")
        assert mock_generate.call_args.kwargs["system"] == _DEFAULT_GROUP_SYSTEM

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_merge_system_falls_back_to_default(self, mock_generate, monkeypatch):
        monkeypatch.setattr(
            "contemplative_agent.core.prompts.STOCKTAKE_MERGE_SYSTEM_PROMPT",
            "",
            raising=False,
        )
        mock_generate.return_value = GenerationOutput(text="merged")
        merge_group([("a.md", "x"), ("b.md", "y")], "prompt {candidates}")
        assert mock_generate.call_args.kwargs["system"] == _DEFAULT_MERGE_SYSTEM

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_clean_system_falls_back_to_default(self, mock_generate, monkeypatch):
        monkeypatch.setattr(
            "contemplative_agent.core.prompts.STOCKTAKE_CLEAN_SYSTEM_PROMPT",
            "",
            raising=False,
        )
        mock_generate.return_value = GenerationOutput(text="CLEAN_NOOP")
        clean_skill_triggers(("a.md", "body"), "prompt {skill}")
        assert mock_generate.call_args.kwargs["system"] == _DEFAULT_CLEAN_SYSTEM


class TestStocktakeTraceCapture:
    """ADR-0069: stocktake runs think-ON; the grouping trace lands on
    StocktakeResult.thinking and per-op traces flow through trace_sink."""

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_merge_group_populates_trace_sink(self, mock_gen):
        mock_gen.return_value = GenerationOutput(
            text="# Merged\n\n## Problem\nx\n\n## Solution\ny", thinking="merge reason"
        )
        sink: list[str] = []
        merge_group([("a.md", "x"), ("b.md", "y")], "merge {candidates}", sink)
        assert sink == ["merge reason"]

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_merge_group_omits_trace_when_none(self, mock_gen):
        mock_gen.return_value = GenerationOutput(text="# Merged\n\nbody", thinking=None)
        sink: list[str] = []
        merge_group([("a.md", "x"), ("b.md", "y")], "merge {candidates}", sink)
        assert sink == []

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_run_skill_stocktake_sets_grouping_thinking(self, mock_gen, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for n in ("a.md", "b.md"):
            (skills_dir / n).write_text(
                "## Problem\n" + "x" * 250 + "\n## Solution\ny", encoding="utf-8"
            )
        mock_gen.return_value = GenerationOutput(
            text=json.dumps({"groups": []}), thinking="why these are distinct"
        )
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert result.thinking == "why these are distinct"


class TestTruncationPolicyH1:
    """Bug-audit 2026-07-06 H1: the shared stocktake LLM helper passes
    drop_truncated=True (covers grouping / merge / clean calls)."""

    @patch("contemplative_agent.core.stocktake.generate_full", return_value=None)
    def test_generate_with_trace_drops_truncated(self, mock_generate):
        from contemplative_agent.core.stocktake import _generate_with_trace

        result = _generate_with_trace(
            "prompt",
            system="sys",
            num_predict=100,
            caller="stocktake.test",
            trace_sink=None,
        )
        assert result is None
        assert mock_generate.call_args.kwargs["drop_truncated"] is True


class TestParseGroupsDisjointnessH6:
    """Bug-audit 2026-07-06 H6/L8: LLM-returned merge groups must be
    disjoint and internally deduplicated — an overlapping file would be
    re-merged from its stale pre-deletion body, re-introducing a duplicate."""

    def test_overlapping_groups_keep_first_claim(self):
        text = json.dumps(
            {
                "groups": [
                    {"files": ["a.md", "b.md"], "reason": "dup pair"},
                    {"files": ["a.md", "c.md"], "reason": "overlaps first"},
                ]
            }
        )
        groups = _parse_groups(text)
        assert groups is not None
        assert groups[0].filenames == ("a.md", "b.md")
        # Second group loses "a.md" and collapses below the 2-file minimum.
        assert len(groups) == 1

    def test_overlap_with_enough_remainder_survives(self):
        text = json.dumps(
            {
                "groups": [
                    {"files": ["a.md", "b.md"], "reason": "dup pair"},
                    {"files": ["a.md", "c.md", "d.md"], "reason": "partial overlap"},
                ]
            }
        )
        groups = _parse_groups(text)
        assert groups is not None
        assert len(groups) == 2
        assert groups[1].filenames == ("c.md", "d.md")

    def test_self_duplicate_group_is_dropped(self):
        text = json.dumps(
            {
                "groups": [
                    {"files": ["a.md", "a.md"], "reason": "self pair"},
                ]
            }
        )
        assert _parse_groups(text) == []

    def test_non_dict_group_entry_is_skipped(self):
        text = json.dumps(
            {
                "groups": [
                    "not a dict",
                    {"files": ["a.md", "b.md"], "reason": "valid"},
                ]
            }
        )
        groups = _parse_groups(text)
        assert groups is not None
        assert len(groups) == 1
        assert groups[0].filenames == ("a.md", "b.md")


class TestParseGroupsKnownFilterCodex:
    """Codex review 2026-07-06: a hallucinated filename must not claim its
    group-mates before the group is dropped — that silently robbed a later
    valid group of its merge."""

    def test_hallucinated_file_does_not_claim_real_sibling(self):
        text = json.dumps(
            {
                "groups": [
                    {"files": ["missing.md", "a.md"], "reason": "half hallucinated"},
                    {"files": ["a.md", "b.md"], "reason": "valid pair"},
                ]
            }
        )
        groups = _parse_groups(text, known={"a.md", "b.md"})
        assert groups is not None
        # First group collapses (missing.md dropped → 1 file); the valid
        # pair must survive with a.md unclaimed.
        assert len(groups) == 1
        assert groups[0].filenames == ("a.md", "b.md")

    def test_none_known_skips_filter(self):
        text = json.dumps(
            {
                "groups": [
                    {"files": ["x.md", "y.md"], "reason": "no filter"},
                ]
            }
        )
        groups = _parse_groups(text)
        assert groups is not None
        assert groups[0].filenames == ("x.md", "y.md")


# ---------------------------------------------------------------------------
# ADR-0081 stocktake usage dimension: selection-log reading threaded into the
# skill stocktake report (statistics = code; retirement judgment stays with
# the LLM proposal + human gate — no numeric auto-retire threshold).
# ---------------------------------------------------------------------------


def _make_reading(**overrides):
    from dataclasses import replace

    from contemplative_agent.core.skill_selection import SkillSelectionReading

    base = SkillSelectionReading(
        days=14,
        records=1300,
        verdicts=(("judged", 1299), ("fail_open_llm", 1)),
        per_skill=(("busy-skill", 920), ("quiet-skill", 2)),
        never_selected=("ghost-skill",),
        hallucination_records=7,
        judged_records=1299,
        judged_empty_records=0,
        selected_count_p50=5.0,
        selected_count_p90=6.0,
        token_reduction_p50=15000.0,
        token_reduction_p90=17000.0,
        enforced_records=1299,
        per_day=(),
        never_selected_exposure=(("ghost-skill", 1300),),
        rejected_name_tally=(),
        catalog_available=True,
    )
    return replace(base, **overrides) if overrides else base


class TestUsageSection:
    def test_report_renders_usage_when_present(self):
        result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=3,
            selection_usage=_make_reading(),
        )
        report = format_stocktake_report(result, "Skill")
        assert "SKILL USAGE" in report
        assert "14" in report  # window days
        # Full distribution, not survivors-only: both ends present.
        assert "busy-skill" in report and "920" in report
        assert "quiet-skill" in report and "2" in report
        assert "ghost-skill" in report
        assert "never selected" in report.lower()

    def test_report_omits_usage_when_absent(self):
        result = StocktakeResult(merge_groups=(), quality_issues=(), total_files=3)
        report = format_stocktake_report(result, "Skill")
        assert "SKILL USAGE" not in report

    def test_usage_lists_low_count_first(self):
        """Ascending order puts retirement candidates where the operator
        reads first; the busy end still renders (full distribution)."""
        result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=3,
            selection_usage=_make_reading(),
        )
        report = format_stocktake_report(result, "Skill")
        assert report.index("quiet-skill") < report.index("busy-skill")

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_run_skill_stocktake_threads_reading(self, mock_generate, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, {"s.md": GOOD_SKILL})
        reading = _make_reading()
        result = run_skill_stocktake(skills_dir=skills_dir, selection_reading=reading)
        assert result.selection_usage is reading

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_run_skill_stocktake_default_none(self, mock_generate, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, {"s.md": GOOD_SKILL})
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert result.selection_usage is None


# ---------------------------------------------------------------------------
# ADR-0081 description audit: does the frontmatter description faithfully
# carry the body's trigger conditions? Advisory-only (no writes) — the LLM
# reports a mismatch reason, the human decides at the stocktake gate.
# ---------------------------------------------------------------------------


class TestAuditSkillDescription:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_mismatch_reason_returned(self, mock_generate):
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = GenerationOutput(
            text="Description claims a narrow trigger; body fires on any post."
        )
        reason = audit_skill_description(
            ("s.md", "A narrow skill", "# S\n\n## When to Use\nAlways."),
            "audit {name} {description} {skill}",
        )
        assert reason is not None
        assert "narrow trigger" in reason

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_desc_ok_returns_none(self, mock_generate):
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = GenerationOutput(text="DESC_OK")
        assert (
            audit_skill_description(("s.md", "desc", "body"), "audit {name} {description} {skill}")
            is None
        )

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_desc_ok_tolerates_whitespace(self, mock_generate):
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = GenerationOutput(text="\n  DESC_OK\n")
        assert (
            audit_skill_description(("s.md", "desc", "body"), "audit {name} {description} {skill}")
            is None
        )

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_llm_failure_returns_none(self, mock_generate, caplog):
        """Fault column (chaos-TDD): LLM failure abstains with a logged
        reason — the audit is advisory, so no exception, no fabricated
        verdict."""
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = None
        with caplog.at_level("WARNING"):
            result = audit_skill_description(
                ("s.md", "desc", "body"), "audit {name} {description} {skill}"
            )
        assert result is None
        assert "description audit" in caplog.text.lower()

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_braces_in_body_are_safe(self, mock_generate):
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = GenerationOutput(text="DESC_OK")
        audit_skill_description(
            ("s.md", "desc", "BODY_MARKER {x}"),
            "audit: {name} / {description} / {skill}",
        )
        assert "BODY_MARKER {x}" in mock_generate.call_args.args[0]

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_system_falls_back_to_default(self, mock_generate, monkeypatch):
        from contemplative_agent.core.stocktake import (
            _DEFAULT_DESC_SYSTEM,
            audit_skill_description,
        )

        monkeypatch.setattr(
            "contemplative_agent.core.prompts.STOCKTAKE_DESC_SYSTEM_PROMPT",
            "",
            raising=False,
        )
        mock_generate.return_value = GenerationOutput(text="DESC_OK")
        audit_skill_description(("s.md", "desc", "body"), "audit {name} {description} {skill}")
        assert mock_generate.call_args.kwargs["system"] == _DEFAULT_DESC_SYSTEM


class TestDescReasonScrub:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_control_chars_stripped_and_capped(self, mock_generate):
        from contemplative_agent.core.stocktake import (
            _DESC_REASON_MAX_CHARS,
            audit_skill_description,
        )

        mock_generate.return_value = GenerationOutput(text="\x1b[31mbroader\x1b[0m: " + "x" * 1000)
        reason = audit_skill_description(
            ("s.md", "desc", "body"), "audit {name} {description} {skill}"
        )
        assert reason is not None
        assert "\x1b" not in reason
        assert len(reason) <= _DESC_REASON_MAX_CHARS

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_newlines_collapsed_to_one_line(self, mock_generate):
        """Security review 2026-07-24: embedded newlines could spoof extra
        report entries — the reason contract is ONE line."""
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = GenerationOutput(
            text="broader\n  fake.md — injected entry\r\nmore"
        )
        reason = audit_skill_description(
            ("s.md", "desc", "body"), "audit {name} {description} {skill}"
        )
        assert reason is not None
        assert "\n" not in reason and "\r" not in reason


class TestDescAuditUntrustedWrap:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_description_and_body_are_wrapped(self, mock_generate):
        """Codex review 2026-07-24: the audit target is untrusted LLM-distilled
        content with an incentive to self-exonerate ("output DESC_OK") — both
        fields must pass the untrusted-content boundary before generation."""
        from contemplative_agent.core.llm import wrap_untrusted_content
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = GenerationOutput(text="DESC_OK")
        audit_skill_description(
            ("s.md", "DESC_MARKER", "BODY_MARKER"),
            "audit {name} / {description} / {skill}",
        )
        prompt = mock_generate.call_args.args[0]
        assert wrap_untrusted_content("DESC_MARKER") in prompt
        assert wrap_untrusted_content("BODY_MARKER") in prompt


# ---------------------------------------------------------------------------
# Grouping evidence: frontmatter summaries, not full bodies (2026-08-15).
# Reproduction and rationale: ``_skill_grouping_evidence`` docstring.
# ---------------------------------------------------------------------------


def _big_skill(i: int) -> str:
    body_filler = (
        "The agent notices a shift from a high-level philosophical claim to a "
        "specific operational mandate and names the structural tension. "
    ) * 14
    return (
        "---\n"
        f"name: skill-{i:02d}\n"
        f'description: "Distinct trigger number {i} for the description-only grouping test"\n'
        "origin: auto-extracted\n"
        "---\n\n"
        f"# Skill {i:02d}\n\n"
        f"**Context:** Context sentence {i}. Second sentence is not evidence.\n\n"
        f"## Problem\n{body_filler}\n\n"
        f"## Solution\nBODY-SENTINEL-{i:02d} {body_filler}\n\n"
        f"## When to Use\n{body_filler}\n"
    )


class TestGroupingEvidence:
    def test_skill_evidence_is_description_and_context(self):
        from contemplative_agent.core.stocktake import _skill_grouping_evidence

        text = _skill_grouping_evidence("a.md", GOOD_SKILL, strip_frontmatter(GOOD_SKILL))
        assert "A test skill" in text
        assert "Testing context." in text
        # Body sections stay out of the grouping call.
        assert "Apply test-driven techniques" not in text

    def test_skill_evidence_falls_back_to_title_for_legacy_body(self):
        from contemplative_agent.core.stocktake import _skill_grouping_evidence

        text = _skill_grouping_evidence(
            "legacy.md", GOOD_SKILL_NO_FRONTMATTER, GOOD_SKILL_NO_FRONTMATTER
        )
        assert "Another Skill" in text
        assert "Different context." in text
        assert "completely different approach" not in text

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_skill_grouping_fits_window_at_store_scale(self, mock_generate, tmp_path):
        """50 real-sized skills: the grouping prompt must stay far inside the
        32k window under the conservative estimator (the only pre-flight
        available on the Ollama path — no /api/tokenize)."""
        from contemplative_agent.core.llm import _estimate_tokens
        from contemplative_agent.core.llm.backend import NUM_CTX

        mock_generate.return_value = GenerationOutput(text=LLM_NO_MERGE_RESPONSE)
        skills_dir = _make_skills_dir(
            tmp_path, {f"skill-{i:02d}.md": _big_skill(i) for i in range(50)}
        )
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert mock_generate.call_count == 1
        prompt = mock_generate.call_args.args[0]
        assert "BODY-SENTINEL-07" not in prompt
        # The summaries are grouping evidence only: ``result.items`` must keep
        # the full bodies, because merge / clean write files from them and
        # delete the originals (code review 2026-08-15).
        assert len(result.items) == 50
        assert all("BODY-SENTINEL" in body for _, body in result.items)
        assert "Distinct trigger number 7" in prompt
        assert "Context sentence 7." in prompt
        assert _estimate_tokens(prompt) < NUM_CTX // 4

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_rules_grouping_keeps_full_bodies(self, mock_generate, tmp_path):
        """Rules carry no frontmatter and are short — the rules pass still
        groups on the Practice/Rationale text itself."""
        mock_generate.return_value = GenerationOutput(text=LLM_NO_MERGE_RESPONSE)
        rules_dir = _make_rules_dir(tmp_path, {"a.md": GOOD_RULE, "b.md": GOOD_RULE})
        run_rules_stocktake(rules_dir=rules_dir)
        prompt = mock_generate.call_args.args[0]
        assert "Always ask clarifying questions" in prompt


class TestGroupingUnavailableReason:
    """A grouping call that never produced a verdict must not read as
    'no duplicates' (ADR-0075: no silent fallback)."""

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_llm_failure_carries_reason(self, mock_generate):
        mock_generate.return_value = None
        items = [("a.md", "content a"), ("b.md", "content b")]
        result = _find_duplicate_groups(items, "prompt {items}")
        assert result.groups == ()
        assert result.reason == "GROUPING_LLM_UNAVAILABLE"

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_unparseable_output_carries_reason(self, mock_generate):
        mock_generate.return_value = GenerationOutput(text="no json here")
        items = [("a.md", "content a"), ("b.md", "content b")]
        result = _find_duplicate_groups(items, "prompt {items}")
        assert result.groups == ()
        assert result.reason == "GROUPING_UNPARSEABLE"

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_schema_invalid_output_carries_reason(self, mock_generate):
        mock_generate.return_value = GenerationOutput(text='{"groups": "none"}')
        items = [("a.md", "content a"), ("b.md", "content b")]
        result = _find_duplicate_groups(items, "prompt {items}")
        assert result.groups == ()
        assert result.reason == "GROUPING_UNPARSEABLE"

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_real_verdict_has_no_reason(self, mock_generate):
        mock_generate.return_value = GenerationOutput(text=LLM_NO_MERGE_RESPONSE)
        items = [("a.md", "content a"), ("b.md", "content b")]
        result = _find_duplicate_groups(items, "prompt {items}")
        assert result.groups == ()
        assert result.reason is None

    def test_below_dedup_floor_has_no_reason(self):
        result = _find_duplicate_groups([("a.md", "x")], "prompt {items}")
        assert result.groups == ()
        assert result.reason is None

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_run_skill_stocktake_threads_reason(self, mock_generate, tmp_path):
        mock_generate.return_value = None
        skills_dir = _make_skills_dir(tmp_path, {"a.md": GOOD_SKILL, "b.md": GOOD_SKILL})
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert result.merge_groups == ()
        assert result.grouping_reason == "GROUPING_LLM_UNAVAILABLE"

    def test_report_names_unavailable_grouping(self):
        result = StocktakeResult(
            merge_groups=(),
            quality_issues=(),
            total_files=5,
            grouping_reason="GROUPING_LLM_UNAVAILABLE",
        )
        report = format_stocktake_report(result, "Skill")
        assert "GROUPING_LLM_UNAVAILABLE" in report
        assert "No duplicates detected" not in report

    def test_report_default_still_says_no_duplicates(self):
        result = StocktakeResult(merge_groups=(), quality_issues=(), total_files=5)
        assert "No duplicates detected" in format_stocktake_report(result, "Skill")
