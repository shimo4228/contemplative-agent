"""Tests for core.rules_distill — behavioral rule extraction from skills."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from contemplative_agent.core.insight import _extract_title, _slugify
from contemplative_agent.core.rules_distill import (
    MAX_RULES_PER_BATCH,
    MIN_SKILLS_REQUIRED,
    RulesDistillResult,
    _extract_rules,
    _NO_RULES_MARKER,
    _read_skills,
    _split_rules,
    _STAGE2_MAX_LENGTH,
    _strip_frontmatter,
    distill_rules,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_RULES_RESPONSE_STAGE1 = (
    "Analysis: The skills reveal a principle about asking questions first."
)

GOOD_RULES_RESPONSE_STAGE2 = (
    "# Engagement Rules\n"
    "\n"
    "## Rule 1: Ask Before Reacting\n"
    "\n"
    "**When:** Encountering unfamiliar viewpoints\n"
    "**Do:** Ask clarifying questions before forming a response\n"
    "**Why:** Premature responses reduce engagement quality\n"
    "\n"
    "## Rule 2: Listen First\n"
    "\n"
    "**When:** New information arrives from an external source\n"
    "**Do:** Process and reflect before generating output\n"
    "**Why:** Hasty responses often miss important nuances\n"
)

SKILL_WITH_FRONTMATTER = """\
---
name: engagement-rules
description: "Rules for engaging with other agents"
origin: auto-extracted
---

# Engagement Rules

## Problem
Agents often react before understanding context.

## Solution
Ask clarifying questions before forming a response.
"""

SKILL_WITHOUT_FRONTMATTER = """\
# Direct Skill

Content without frontmatter.
"""


def _make_skills_dir(tmp_path: Path, n: int = 5) -> Path:
    """Create a skills directory with n test skill files."""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    for i in range(n):
        (skills_dir / f"skill-{i:03d}.md").write_text(
            f"# Skill {i}\n\n"
            f"## Problem\nAgents struggle with pattern {i}.\n\n"
            f"## Solution\nApply technique {i} consistently.\n",
            encoding="utf-8",
        )
    return skills_dir


# ---------------------------------------------------------------------------
# Unit tests: _strip_frontmatter
# ---------------------------------------------------------------------------

class TestStripFrontmatter:
    def test_with_frontmatter(self):
        result = _strip_frontmatter(SKILL_WITH_FRONTMATTER)
        assert result.startswith("# Engagement Rules")
        assert "---" not in result.split("\n")[0]

    def test_without_frontmatter(self):
        result = _strip_frontmatter(SKILL_WITHOUT_FRONTMATTER)
        assert result == SKILL_WITHOUT_FRONTMATTER

    def test_unclosed_frontmatter(self):
        text = "---\nname: test\nno closing delimiter"
        assert _strip_frontmatter(text) == text

    def test_empty(self):
        assert _strip_frontmatter("") == ""


# ---------------------------------------------------------------------------
# Unit tests: _read_skills
# ---------------------------------------------------------------------------

class TestReadSkills:
    def test_reads_all_skills(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, n=3)
        skills = _read_skills(skills_dir)
        assert len(skills) == 3

    def test_strips_frontmatter(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "test.md").write_text(SKILL_WITH_FRONTMATTER)
        skills = _read_skills(skills_dir)
        assert len(skills) == 1
        assert not skills[0].startswith("---")
        assert "Engagement Rules" in skills[0]

    def test_skips_dotfiles(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, n=2)
        (skills_dir / ".last_insight").write_text("2026-01-01")
        skills = _read_skills(skills_dir)
        assert len(skills) == 2

    def test_empty_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        assert _read_skills(skills_dir) == []

    def test_nonexistent_dir(self, tmp_path):
        assert _read_skills(tmp_path / "nope") == []

    def test_since_filters_by_mtime(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        old = skills_dir / "old.md"
        old.write_text("# Old\nOld content.")
        # Set mtime to the past
        import os
        os.utime(old, (1000000000, 1000000000))
        new = skills_dir / "new.md"
        new.write_text("# New\nNew content.")

        since = datetime(2020, 1, 1, tzinfo=timezone.utc).isoformat()
        skills = _read_skills(skills_dir, since=since)
        assert len(skills) == 1
        assert "New" in skills[0]

    def test_since_invalid_reads_all(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, n=2)
        skills = _read_skills(skills_dir, since="not-a-date")
        assert len(skills) == 2


# ---------------------------------------------------------------------------
# Unit tests: _extract_rules
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        assert _slugify("Engagement Rules") == "engagement-rules"

    def test_special_chars(self):
        assert _slugify("Rule: Ask First!") == "rule-ask-first"

    def test_empty(self):
        assert _slugify("") == ""

    def test_max_length(self):
        long = "a" * 100
        assert len(_slugify(long)) <= 50


class TestExtractTitle:
    def test_extracts_from_markdown(self):
        assert _extract_title("# My Rules") == "My Rules"

    def test_skips_non_title_lines(self):
        assert _extract_title("Hello\n## Subtitle") is None

    def test_returns_none_for_no_title(self):
        assert _extract_title("No title here") is None


class TestSplitRules:
    def test_splits_multiple_rules(self):
        text = (
            "# Rule Set\n\n"
            "## Rule 1: First Rule\n\n**When:** A\n**Do:** B\n\n"
            "## Rule 2: Second Rule\n\n**When:** C\n**Do:** D\n"
        )
        rules = _split_rules(text)
        assert len(rules) == 2
        assert "# First Rule" in rules[0]
        assert "# Second Rule" in rules[1]

    def test_single_rule(self):
        text = "# Title\n\n## Rule 1: Only Rule\n\n**When:** X\n**Do:** Y\n"
        rules = _split_rules(text)
        assert len(rules) == 1
        assert "# Only Rule" in rules[0]

    def test_no_rules_returns_empty(self):
        text = "# Just a title\n\nSome content without rule markers."
        rules = _split_rules(text)
        assert rules == []

    def test_preserves_content(self):
        text = "## Rule 1: Test\n\n**When:** trigger\n**Do:** action\n**Why:** reason\n"
        rules = _split_rules(text)
        assert len(rules) == 1
        assert "**When:** trigger" in rules[0]
        assert "**Do:** action" in rules[0]
        assert "**Why:** reason" in rules[0]


class TestExtractRules:
    @patch("contemplative_agent.core.rules_distill.generate")
    def test_success(self, mock_generate):
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        result = _extract_rules(["# Skill 1\nContent"])
        assert result is not None
        assert "Engagement Rules" in result
        assert mock_generate.call_count == 2

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_stage1_failure(self, mock_generate):
        mock_generate.return_value = None
        result = _extract_rules(["# Skill 1\nContent"])
        assert result is None

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_stage2_failure(self, mock_generate):
        mock_generate.side_effect = [GOOD_RULES_RESPONSE_STAGE1, None]
        result = _extract_rules(["# Skill 1\nContent"])
        assert result is None

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_no_title_drops(self, mock_generate):
        mock_generate.side_effect = ["Stage 1 result", "No title here"]
        result = _extract_rules(["# Skill 1\nContent"])
        assert result is None

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_stage2_uses_configured_max_length(self, mock_generate):
        """Regression: Stage 2 must request _STAGE2_MAX_LENGTH chars so the
        LLM output doesn't get silently truncated by _sanitize_output's
        [:max_length] slice. Previously hard-coded to 3000 which lost
        rules mid-sentence in production (2026-04-11 incident)."""
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        _extract_rules(["# Skill 1\nContent"])
        # Stage 2 is the second call; inspect its max_length kwarg
        _, stage2_kwargs = mock_generate.call_args_list[1]
        assert stage2_kwargs["max_length"] == _STAGE2_MAX_LENGTH

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_truncation_warning_fires_near_cap(self, mock_generate, caplog):
        """When Stage 2 output length is within _STAGE2_TRUNCATION_MARGIN
        of _STAGE2_MAX_LENGTH, a warning must be logged so humans notice
        the output probably got cut off."""
        import logging

        # Build a response that's within the margin of the cap and has a
        # title line so _extract_title() passes.
        big_body = "x" * (_STAGE2_MAX_LENGTH - 50)
        near_cap = f"# Big Rule Set\n{big_body}"
        mock_generate.side_effect = [GOOD_RULES_RESPONSE_STAGE1, near_cap]
        with caplog.at_level(logging.WARNING, logger="contemplative_agent.core.rules_distill"):
            _extract_rules(["# Skill 1\nContent"])
        assert any(
            "likely truncated" in rec.message for rec in caplog.records
        ), "expected truncation warning for near-cap Stage 2 output"

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_no_universal_rules_marker_is_valid(self, mock_generate):
        """Stage 2 outputting the '# No Universal Rules Found' marker is a
        valid empty outcome, not a failure. _extract_rules returns the
        marker verbatim and callers must recognize it."""
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            "# No Universal Rules Found",
        ]
        result = _extract_rules(["# Skill 1\nContent"])
        assert result == _NO_RULES_MARKER


class TestSplitRulesEnforcesMaxPerBatch:
    """_split_rules must cap at MAX_RULES_PER_BATCH even if the LLM
    ignores the prompt constraint and returns more rules."""

    def test_caps_rule_count_at_max(self, caplog):
        import logging

        # Build a response with MAX_RULES_PER_BATCH + 2 rules
        over = MAX_RULES_PER_BATCH + 2
        body = "# Big Set\n\n"
        for i in range(1, over + 1):
            body += (
                f"## Rule {i}: Rule Number {i}\n\n"
                f"**When:** trigger {i}\n"
                f"**Do:** action {i}\n"
                f"**Why:** reason {i}\n\n"
            )
        with caplog.at_level(logging.WARNING, logger="contemplative_agent.core.rules_distill"):
            rules = _split_rules(body)
        assert len(rules) == MAX_RULES_PER_BATCH
        assert any(
            "exceeding MAX_RULES_PER_BATCH" in rec.message for rec in caplog.records
        )

    def test_under_cap_keeps_all(self):
        body = (
            "# Set\n\n"
            "## Rule 1: Only\n\n**When:** X\n**Do:** Y\n**Why:** Z\n"
        )
        assert len(_split_rules(body)) == 1


class TestDistillRulesRespectsNoRulesMarker:
    """When a batch returns the no-rules marker, distill_rules must skip
    that batch silently (not as a failure) and distinguish 'valid empty'
    from 'LLM error' in the final message."""

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_all_empty_batches_returns_valid_empty_message(
        self, mock_generate, tmp_path
    ):
        """When every batch returns the no-rules marker (and no batch
        actually failed), the final message must NOT say 'Failed to
        extract' — that would mislead the user into thinking the LLM
        broke, when in fact it correctly judged 'no universal principle'."""
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            "# No Universal Rules Found",
        ]
        skills_dir = _make_skills_dir(tmp_path, n=5)
        result = distill_rules(
            skills_dir=skills_dir, rules_dir=tmp_path / "rules"
        )
        assert isinstance(result, str)
        assert "No universal rules extracted" in result
        assert "Failed to extract" not in result

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_actual_failure_still_says_failed(
        self, mock_generate, tmp_path
    ):
        """When Stage 1 actually fails (LLM returns None), the final
        message must preserve the 'Failed to extract' wording so the
        user knows something broke."""
        mock_generate.return_value = None
        skills_dir = _make_skills_dir(tmp_path, n=5)
        result = distill_rules(
            skills_dir=skills_dir, rules_dir=tmp_path / "rules"
        )
        assert isinstance(result, str)
        assert "Failed to extract" in result


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

class TestDistillRules:
    def test_no_skills_dir(self):
        result = distill_rules()
        assert isinstance(result, str)
        assert "No skills directory" in result

    def test_insufficient_skills(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, n=1)
        result = distill_rules(skills_dir=skills_dir, rules_dir=tmp_path / "rules")
        assert isinstance(result, str)
        assert "Insufficient skills" in result
        assert f"1/{MIN_SKILLS_REQUIRED}" in result

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_extraction_failure(self, mock_generate, tmp_path):
        mock_generate.return_value = None
        skills_dir = _make_skills_dir(tmp_path, n=5)
        result = distill_rules(skills_dir=skills_dir, rules_dir=tmp_path / "rules")
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_forbidden_pattern(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            "Stage 1",
            "# Rules\nLeaked api_key: sk-1234\n",
        ]
        skills_dir = _make_skills_dir(tmp_path, n=5)
        result = distill_rules(skills_dir=skills_dir, rules_dir=tmp_path / "rules")
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_returns_rules_result(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        skills_dir = _make_skills_dir(tmp_path, n=5)
        rules_dir = tmp_path / "rules"
        result = distill_rules(skills_dir=skills_dir, rules_dir=rules_dir)
        assert isinstance(result, RulesDistillResult)
        assert len(result.rules) == 2  # Split into 2 individual rules
        assert "Ask Before Reacting" in result.rules[0].text
        assert "Listen First" in result.rules[1].text
        today = date.today().strftime("%Y%m%d")
        assert result.rules[0].filename == f"ask-before-reacting-{today}.md"
        assert result.rules[1].filename == f"listen-first-{today}.md"
        # Core function does not write — caller's responsibility
        assert not rules_dir.exists()

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_empty_slug_dropped(self, mock_generate, tmp_path):
        """Title with only special chars produces empty slug → dropped."""
        mock_generate.side_effect = ["Stage 1", "# !!!\n\nContent"]
        skills_dir = _make_skills_dir(tmp_path, n=5)
        rules_dir = tmp_path / "rules"
        result = distill_rules(skills_dir=skills_dir, rules_dir=rules_dir)
        assert isinstance(result, str)
        assert "Failed to extract" in result

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_frontmatter_skill_files(self, mock_generate, tmp_path):
        """Skills with YAML frontmatter are correctly parsed."""
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        for i in range(MIN_SKILLS_REQUIRED):
            (skills_dir / f"skill-{i}.md").write_text(SKILL_WITH_FRONTMATTER)
        result = distill_rules(skills_dir=skills_dir, rules_dir=tmp_path / "rules")
        assert isinstance(result, RulesDistillResult)
        # Verify frontmatter was stripped in prompt
        call_args = mock_generate.call_args_list[0]
        prompt = call_args[0][0]
        assert "origin: auto-extracted" not in prompt


class TestBatchProcessing:
    @patch("contemplative_agent.core.rules_distill.generate")
    def test_multiple_batches(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ] * 3
        skills_dir = _make_skills_dir(tmp_path, n=25)
        result = distill_rules(skills_dir=skills_dir, rules_dir=tmp_path / "rules")
        assert isinstance(result, RulesDistillResult)
        assert len(result.rules) >= 2

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_partial_failure(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            None,  # batch 1 stage 1 fails
            GOOD_RULES_RESPONSE_STAGE1,  # batch 2 stage 1
            GOOD_RULES_RESPONSE_STAGE2,  # batch 2 stage 2
            GOOD_RULES_RESPONSE_STAGE1,  # batch 3 stage 1
            GOOD_RULES_RESPONSE_STAGE2,  # batch 3 stage 2
        ]
        skills_dir = _make_skills_dir(tmp_path, n=25)
        result = distill_rules(skills_dir=skills_dir, rules_dir=tmp_path / "rules")
        assert isinstance(result, RulesDistillResult)
        assert len(result.rules) >= 1
        assert result.dropped_count >= 1


class TestIncrementalMode:
    @patch("contemplative_agent.core.rules_distill.generate")
    def test_no_marker_written_by_core(self, mock_generate, tmp_path):
        """Core function does not write marker — caller's responsibility."""
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        skills_dir = _make_skills_dir(tmp_path, n=5)
        rules_dir = tmp_path / "rules"
        result = distill_rules(skills_dir=skills_dir, rules_dir=rules_dir)
        assert isinstance(result, RulesDistillResult)
        marker = rules_dir / ".last_rules_distill"
        assert not marker.exists()

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_full_ignores_marker(self, mock_generate, tmp_path):
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        skills_dir = _make_skills_dir(tmp_path, n=5)
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir(parents=True)
        # Write a marker in the future so incremental would find 0 skills
        (rules_dir / ".last_rules_distill").write_text("2099-01-01T00:00+00:00\n")
        result = distill_rules(
            skills_dir=skills_dir, rules_dir=rules_dir, full=True,
        )
        assert isinstance(result, RulesDistillResult)
        assert "Ask Before Reacting" in result.rules[0].text

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_incremental_filters_old_skills(self, mock_generate, tmp_path):
        """Incremental mode only reads skills newer than last run."""
        import os

        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        # Old skill
        old = skills_dir / "old.md"
        old.write_text("# Old Skill\nOld content.")
        os.utime(old, (1000000000, 1000000000))
        # New skills (enough to meet minimum)
        for i in range(MIN_SKILLS_REQUIRED):
            (skills_dir / f"new-{i}.md").write_text(f"# New Skill {i}\nContent.")

        rules_dir = tmp_path / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / ".last_rules_distill").write_text("2020-01-01T00:00+00:00\n")

        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        result = distill_rules(skills_dir=skills_dir, rules_dir=rules_dir)
        assert isinstance(result, RulesDistillResult)
        # Old skill should have been filtered out
        call_args = mock_generate.call_args_list[0]
        prompt = call_args[0][0]
        assert "Old Skill" not in prompt
