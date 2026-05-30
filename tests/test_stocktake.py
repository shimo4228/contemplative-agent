"""Tests for core.stocktake — skill and rule auditing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from contemplative_agent.core.stocktake import (
    MergeGroup,
    QualityIssue,
    StocktakeResult,
    _PER_FILE_MERGE_TOKENS,
    _check_rule_quality,
    _check_skill_quality,
    _find_duplicate_groups,
    _parse_groups,
    _read_files,
    format_stocktake_report,
    is_merge_rejected,
    merge_group,
    run_rules_stocktake,
    run_skill_stocktake,
)


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
LLM_MERGE_RESPONSE = json.dumps({
    "groups": [
        {"files": ["skill-a.md", "skill-b.md"], "reason": "Both describe the same response loop"},
    ]
})
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
# Unit tests: _read_files
# ---------------------------------------------------------------------------

class TestReadFiles:
    def test_reads_and_strips_frontmatter(self, tmp_path):
        d = tmp_path / "files"
        d.mkdir()
        (d / "test.md").write_text(GOOD_SKILL)
        items = _read_files(d)
        assert len(items) == 1
        assert not items[0][1].startswith("---")

    def test_skips_dotfiles(self, tmp_path):
        d = tmp_path / "files"
        d.mkdir()
        (d / ".hidden").write_text("hidden")
        (d / "visible.md").write_text("# Visible\nContent here.")
        items = _read_files(d)
        assert len(items) == 1

    def test_empty_dir(self, tmp_path):
        d = tmp_path / "files"
        d.mkdir()
        assert _read_files(d) == []

    def test_nonexistent_dir(self, tmp_path):
        assert _read_files(tmp_path / "nope") == []


# ---------------------------------------------------------------------------
# Unit tests: _parse_groups
# ---------------------------------------------------------------------------

class TestParseGroups:
    def test_valid_json(self):
        groups = _parse_groups(LLM_MERGE_RESPONSE)
        assert len(groups) == 1
        assert groups[0].filenames == ("skill-a.md", "skill-b.md")

    def test_empty_groups(self):
        assert _parse_groups(LLM_NO_MERGE_RESPONSE) == []

    def test_json_in_code_fence(self):
        raw = f"```json\n{LLM_MERGE_RESPONSE}\n```"
        groups = _parse_groups(raw)
        assert len(groups) == 1

    def test_json_embedded_in_prose(self):
        raw = f"Here are the groups:\n{LLM_MERGE_RESPONSE}\nDone."
        groups = _parse_groups(raw)
        assert len(groups) == 1

    def test_invalid_json(self):
        assert _parse_groups("not json at all") == []

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
    @patch("contemplative_agent.core.stocktake.generate")
    def test_returns_merge_groups(self, mock_generate):
        mock_generate.return_value = LLM_MERGE_RESPONSE
        items = [("a.md", "content a"), ("b.md", "content b")]
        groups = _find_duplicate_groups(items, "prompt {items}")
        assert len(groups) == 1
        assert mock_generate.call_count == 1

    @patch("contemplative_agent.core.stocktake.generate")
    def test_no_duplicates_returns_empty(self, mock_generate):
        mock_generate.return_value = LLM_NO_MERGE_RESPONSE
        items = [("a.md", "content a"), ("b.md", "content b")]
        assert _find_duplicate_groups(items, "prompt {items}") == []

    @patch("contemplative_agent.core.stocktake.generate")
    def test_multiple_groups_not_collapsed(self, mock_generate):
        """Distinct families stay separate — the grouping call can return
        several small groups rather than one over-merged blob."""
        mock_generate.return_value = json.dumps({"groups": [
            {"files": ["a.md", "b.md"], "reason": "family one"},
            {"files": ["c.md", "d.md"], "reason": "family two"},
        ]})
        items = [(f"{c}.md", f"body {c}") for c in "abcd"]
        groups = _find_duplicate_groups(items, "prompt {items}")
        assert len(groups) == 2

    @patch("contemplative_agent.core.stocktake.generate")
    def test_llm_failure_returns_empty(self, mock_generate):
        mock_generate.return_value = None
        items = [("a.md", "content a"), ("b.md", "content b")]
        assert _find_duplicate_groups(items, "prompt {items}") == []

    def test_single_file_skips_llm(self):
        items = [("a.md", "content a")]
        assert _find_duplicate_groups(items, "prompt {items}") == []

    @patch("contemplative_agent.core.stocktake.generate")
    def test_grouping_token_budget_has_floor(self, mock_generate):
        """Small stores still get a generous budget so the JSON is not
        truncated (truncation would corrupt parsing and drop groups)."""
        mock_generate.return_value = LLM_NO_MERGE_RESPONSE
        items = [("a.md", "x"), ("b.md", "y")]
        _find_duplicate_groups(items, "prompt {items}")
        assert mock_generate.call_args.kwargs["num_predict"] == 3000


# ---------------------------------------------------------------------------
# Unit tests: merge_group + is_merge_rejected
# ---------------------------------------------------------------------------

class TestMergeGroup:
    @patch("contemplative_agent.core.stocktake.generate")
    def test_returns_merged_text(self, mock_generate):
        mock_generate.return_value = "# Merged Skill\n\n## Problem\nCombined.\n\n## Solution\nUnified."
        items = [("a.md", "content a"), ("b.md", "content b")]
        result = merge_group(items, "merge {candidates}")
        assert result is not None
        assert "# Merged Skill" in result

    @patch("contemplative_agent.core.stocktake.generate")
    def test_llm_failure(self, mock_generate):
        mock_generate.return_value = None
        items = [("a.md", "content a"), ("b.md", "content b")]
        assert merge_group(items, "merge {candidates}") is None

    @patch("contemplative_agent.core.stocktake.generate")
    def test_cannot_merge_returned_verbatim(self, mock_generate):
        """LLM reject path: CANNOT_MERGE is returned as-is for caller inspection."""
        mock_generate.return_value = "CANNOT_MERGE: distinct behaviors."
        items = [("a.md", "content a"), ("b.md", "content b")]
        result = merge_group(items, "merge {candidates}")
        assert result is not None
        assert result.startswith("CANNOT_MERGE:")

    @patch("contemplative_agent.core.stocktake.generate")
    def test_small_group_keeps_floor_budget(self, mock_generate):
        """A 2-file merge keeps the 3000-token floor (prior behavior)."""
        mock_generate.return_value = "# Merged\n\n## Problem\np\n\n## Solution\ns"
        items = [("a.md", "x"), ("b.md", "y")]
        merge_group(items, "merge {candidates}")
        assert mock_generate.call_args.kwargs["num_predict"] == 3000

    @patch("contemplative_agent.core.stocktake.generate")
    def test_token_budget_scales_with_group_size(self, mock_generate):
        """Pattern-preserving merge output grows with inputs, so the token
        budget scales above the floor — preventing truncation that would
        silently drop the distinct patterns the merge exists to preserve."""
        mock_generate.return_value = "# Merged\n\n## Problem\np\n\n## Solution\ns"
        items = [(f"f{i}.md", f"body {i}") for i in range(12)]
        merge_group(items, "merge {candidates}")
        assert mock_generate.call_args.kwargs["num_predict"] == _PER_FILE_MERGE_TOKENS * 12

    @patch("contemplative_agent.core.stocktake.generate")
    def test_token_budget_capped_at_ceiling(self, mock_generate):
        """Very large groups are capped at 8192 (num_ctx headroom)."""
        mock_generate.return_value = "# Merged\n\n## Problem\np\n\n## Solution\ns"
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
# Integration tests: run_skill_stocktake
# ---------------------------------------------------------------------------

class TestRunSkillStocktake:
    @patch("contemplative_agent.core.stocktake.generate")
    def test_detects_merges_and_quality(self, mock_generate, tmp_path):
        mock_generate.return_value = json.dumps({
            "groups": [{"files": ["a.md", "b.md"], "reason": "overlap"}]
        })
        skills_dir = _make_skills_dir(tmp_path, {
            "a.md": GOOD_SKILL,
            "b.md": GOOD_SKILL_NO_FRONTMATTER,
            "short.md": SHORT_SKILL,
        })
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert isinstance(result, StocktakeResult)
        assert len(result.merge_groups) == 1
        assert len(result.quality_issues) >= 1  # short.md
        assert result.total_files == 3

    @patch("contemplative_agent.core.stocktake.generate")
    def test_no_issues(self, mock_generate, tmp_path):
        # Single file: below MIN_FILES_FOR_DEDUP, so grouping LLM not invoked
        skills_dir = _make_skills_dir(tmp_path, {
            "good.md": GOOD_SKILL,
        })
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
    @patch("contemplative_agent.core.stocktake.generate")
    def test_detects_quality_issue(self, mock_generate, tmp_path):
        mock_generate.return_value = LLM_NO_MERGE_RESPONSE
        rules_dir = _make_rules_dir(tmp_path, {
            "good.md": GOOD_RULE,
            "bad.md": MISSING_PRACTICE_RULE,
        })
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
    @patch("contemplative_agent.core.stocktake.generate")
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
