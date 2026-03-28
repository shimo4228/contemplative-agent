"""Tests for core.stocktake — skill and rule auditing."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from contemplative_agent.core.stocktake import (
    MergeGroup,
    QualityIssue,
    StocktakeResult,
    _check_rule_quality,
    _check_skill_quality,
    _find_duplicate_groups,
    _parse_groups,
    _read_files,
    format_report,
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
# Engagement Rules

## Rule 1: Ask Before Reacting

**When:** Encountering unfamiliar viewpoints in conversation.
**Do:** Ask clarifying questions before forming a response.
**Why:** Premature responses reduce engagement quality and miss context.

## Rule 2: Listen First

**When:** New information arrives from an external source.
**Do:** Process and reflect before generating output.
**Why:** Hasty responses often miss important nuances.
"""

MISSING_WHEN_RULE = """\
# Incomplete Rule

## Rule 1: Some Rule

**Do:** Do something without knowing when.
**Why:** Because reasons that span enough text to pass length check.
More content here to ensure we exceed the minimum character threshold.
"""

LLM_MERGE_RESPONSE = json.dumps({
    "groups": [
        {
            "files": ["skill-a.md", "skill-b.md"],
            "reason": "Both describe empathic response loops",
        }
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

    def test_invalid_json(self):
        assert _parse_groups("not json at all") == []

    def test_single_file_group_ignored(self):
        raw = json.dumps({"groups": [{"files": ["only-one.md"], "reason": "alone"}]})
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

    def test_missing_when(self):
        issue = _check_rule_quality("no-when.md", MISSING_WHEN_RULE)
        assert issue is not None
        assert "When" in issue.reason


# ---------------------------------------------------------------------------
# Unit tests: _find_duplicate_groups
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
    def test_llm_failure_returns_empty(self, mock_generate):
        mock_generate.return_value = None
        items = [("a.md", "content a"), ("b.md", "content b")]
        groups = _find_duplicate_groups(items, "prompt {items}")
        assert groups == []

    def test_single_file_skips_llm(self):
        items = [("a.md", "content a")]
        groups = _find_duplicate_groups(items, "prompt {items}")
        assert groups == []


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
        mock_generate.return_value = LLM_NO_MERGE_RESPONSE
        skills_dir = _make_skills_dir(tmp_path, {
            "good.md": GOOD_SKILL,
        })
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert result.merge_groups == ()
        assert result.quality_issues == ()

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
            "bad.md": MISSING_WHEN_RULE,
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
        mock_generate.return_value = LLM_NO_MERGE_RESPONSE
        skills_dir = _make_skills_dir(tmp_path, {"s.md": GOOD_SKILL})
        rules_dir = _make_rules_dir(tmp_path, {"r.md": GOOD_RULE})

        skill_result = run_skill_stocktake(skills_dir=skills_dir)
        rule_result = run_rules_stocktake(rules_dir=rules_dir)

        assert skill_result.total_files == 1
        assert rule_result.total_files == 1
        # Each only saw its own files
        assert mock_generate.call_count == 0  # 1 file each = below MIN_FILES_FOR_DEDUP


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
        report = format_report(result, "Skill")
        assert "Skill Stocktake Report" in report
        assert "a.md, b.md" in report
        assert "overlap" in report
        assert "c.md" in report
        assert "1 merge group" in report

    def test_format_clean(self):
        result = StocktakeResult(merge_groups=(), quality_issues=(), total_files=5)
        report = format_report(result, "Rules")
        assert "No duplicates" in report
        assert "5 healthy" in report
