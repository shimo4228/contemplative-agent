"""Tests for core.stocktake — structural quality, usage reading, description audit.

ADR-0097 reduced the module to these three concerns; the grouping / merge /
clean stages and their tests were retired with it.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from contemplative_agent.core.llm import GenerationOutput
from contemplative_agent.core.stocktake import (
    QualityIssue,
    StocktakeResult,
    _check_rule_quality,
    _check_skill_quality,
    format_stocktake_report,
    run_rules_quality_check,
    run_skill_stocktake,
)
from contemplative_agent.core.text_utils import read_markdown_documents

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
# run_skill_stocktake / run_rules_quality_check: deterministic, no LLM call
# ---------------------------------------------------------------------------


class TestRunSkillStocktake:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_reports_quality_without_an_llm_call(self, mock_generate, tmp_path):
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
        assert [i.filename for i in result.quality_issues] == ["short.md"]
        assert result.total_files == 3
        assert {name for name, _raw, _body in result.items} == {"a.md", "b.md", "short.md"}
        # ADR-0097: no grouping call — the store is read, never judged here.
        assert mock_generate.call_count == 0

    def test_no_issues(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, {"good.md": GOOD_SKILL})
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert result.quality_issues == ()

    def test_empty_dir(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        assert run_skill_stocktake(skills_dir=skills_dir).total_files == 0

    def test_nonexistent_dir(self, tmp_path):
        assert run_skill_stocktake(skills_dir=tmp_path / "nope").total_files == 0


class TestRunRulesQualityCheck:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_detects_quality_issue_without_an_llm_call(self, mock_generate, tmp_path):
        rules_dir = _make_rules_dir(
            tmp_path, {"good.md": GOOD_RULE, "bad.md": MISSING_PRACTICE_RULE}
        )
        result = run_rules_quality_check(rules_dir=rules_dir)
        assert [i.filename for i in result.quality_issues] == ["bad.md"]
        assert result.total_files == 2
        assert mock_generate.call_count == 0

    def test_empty_dir(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        assert run_rules_quality_check(rules_dir=rules_dir).total_files == 0


class TestIndependence:
    def test_skills_and_rules_do_not_mix(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, {"s.md": GOOD_SKILL})
        rules_dir = _make_rules_dir(tmp_path, {"r.md": GOOD_RULE})
        assert run_skill_stocktake(skills_dir=skills_dir).total_files == 1
        assert run_rules_quality_check(rules_dir=rules_dir).total_files == 1


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def test_format_with_issues(self):
        result = StocktakeResult(
            quality_issues=(QualityIssue("c.md", "too short"),),
            total_files=3,
        )
        report = format_stocktake_report(result, "Skill")
        assert "Skill Stocktake Report" in report
        assert "c.md" in report
        assert "too short" in report
        assert "1 low quality, 2 healthy" in report

    def test_format_clean(self):
        result = StocktakeResult(quality_issues=(), total_files=5)
        report = format_stocktake_report(result, "Rules")
        assert "5 healthy" in report
        assert "merge" not in report.lower()


class TestTruncationPolicyH1:
    """Bug-audit 2026-07-06 H1: the description audit — the module's one LLM
    call since ADR-0097 — passes drop_truncated=True."""

    @patch("contemplative_agent.core.stocktake.generate_full", return_value=None)
    def test_description_audit_drops_truncated(self, mock_generate):
        from contemplative_agent.core.stocktake import audit_skill_description

        reason, thinking = audit_skill_description(
            ("s.md", "desc", "body"), "audit {name} {description} {skill}"
        )
        assert reason is None and thinking is None
        assert mock_generate.call_args.kwargs["drop_truncated"] is True
        assert mock_generate.call_args.kwargs["think"] is True


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
        result = StocktakeResult(quality_issues=(), total_files=3)
        report = format_stocktake_report(result, "Skill")
        assert "SKILL USAGE" not in report

    def test_usage_lists_low_count_first(self):
        """Ascending order puts retirement candidates where the operator
        reads first; the busy end still renders (full distribution)."""
        result = StocktakeResult(
            quality_issues=(),
            total_files=3,
            selection_usage=_make_reading(),
        )
        report = format_stocktake_report(result, "Skill")
        assert report.index("quiet-skill") < report.index("busy-skill")

    def test_run_skill_stocktake_threads_reading(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, {"s.md": GOOD_SKILL})
        reading = _make_reading()
        result = run_skill_stocktake(skills_dir=skills_dir, selection_reading=reading)
        assert result.selection_usage is reading

    def test_run_skill_stocktake_default_none(self, tmp_path):
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
        reason, _thinking = audit_skill_description(
            ("s.md", "A narrow skill", "# S\n\n## When to Use\nAlways."),
            "audit {name} {description} {skill}",
        )
        assert reason is not None
        assert "narrow trigger" in reason

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_desc_ok_returns_none(self, mock_generate):
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = GenerationOutput(text="DESC_OK")
        reason, _thinking = audit_skill_description(
            ("s.md", "desc", "body"), "audit {name} {description} {skill}"
        )
        assert reason is None

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_desc_ok_tolerates_whitespace(self, mock_generate):
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = GenerationOutput(text="\n  DESC_OK\n")
        reason, _thinking = audit_skill_description(
            ("s.md", "desc", "body"), "audit {name} {description} {skill}"
        )
        assert reason is None

    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_llm_failure_returns_none(self, mock_generate, caplog):
        """Fault column (chaos-TDD): LLM failure abstains with a logged
        reason — the audit is advisory, so no exception, no fabricated
        verdict."""
        from contemplative_agent.core.stocktake import audit_skill_description

        mock_generate.return_value = None
        with caplog.at_level("WARNING"):
            reason, _thinking = audit_skill_description(
                ("s.md", "desc", "body"), "audit {name} {description} {skill}"
            )
        assert reason is None
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
        reason, _thinking = audit_skill_description(
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
        reason, _thinking = audit_skill_description(
            ("s.md", "desc", "body"), "audit {name} {description} {skill}"
        )
        assert reason is not None
        assert "\n" not in reason and "\r" not in reason


class TestDescAuditUntrustedWrap:
    @patch("contemplative_agent.core.stocktake.generate_full")
    def test_description_and_body_are_wrapped(self, mock_generate, pinned_nonce):
        """Codex review 2026-07-24: the audit target is untrusted LLM-distilled
        content with an incentive to self-exonerate ("output DESC_OK") — both
        fields must pass the untrusted-content boundary before generation."""
        from contemplative_agent.core.llm import wrap_untrusted_content
        from contemplative_agent.core.stocktake import audit_skill_description

        # ``pinned_nonce`` (conftest) fixes the delimiter: without it, building
        # the expected block with a second call would compare two different
        # frames. What is under test is that both fields cross the boundary,
        # not how the boundary is randomised.
        mock_generate.return_value = GenerationOutput(text="DESC_OK")
        audit_skill_description(
            ("s.md", "DESC_MARKER", "BODY_MARKER"),
            "audit {name} / {description} / {skill}",
        )
        prompt = mock_generate.call_args.args[0]
        assert wrap_untrusted_content("DESC_MARKER") in prompt
        assert wrap_untrusted_content("BODY_MARKER") in prompt
