"""Tests for core.rules_distill — behavioral rule extraction from skills."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from contemplative_agent.core.rules_distill import (
    MIN_SKILLS_REQUIRED,
    RulesDistillResult,
    _build_skill_clusters,
    _extract_rules,
    _NO_RULES_MARKER,
    _read_skills,
    _split_rules,
    distill_rules,
)
from contemplative_agent.core.text_utils import (
    extract_title,
    slugify,
    split_frontmatter,
    strip_frontmatter,
    synthesize_frontmatter,
)


@pytest.fixture(autouse=True)
def _mock_embed_texts(monkeypatch):
    """Return uniform unit embeddings so skill clusters form deterministically.

    All skills land in one tight cluster (cosine ≈ 1); sizes beyond
    ``MAX_RULES_BATCH`` overflow into a second "singletons" batch. No
    real Ollama call is made.
    """
    def _fake(texts):
        if not texts:
            return np.zeros((0, 8), dtype=np.float32)
        vec = np.ones((len(texts), 8), dtype=np.float32) / np.sqrt(8.0)
        return vec
    monkeypatch.setattr(
        "contemplative_agent.core.rules_distill.embed_texts", _fake,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GOOD_RULES_RESPONSE_STAGE1 = (
    "Analysis: The skills reveal a principle about asking questions first."
)

GOOD_RULES_RESPONSE_STAGE2 = (
    "# Engagement Practices\n"
    "\n"
    "## Rule 1: Ask Before Reacting\n"
    "\n"
    "**Practice:** Always ask clarifying questions before forming a response.\n"
    "**Rationale:** Premature responses reduce engagement quality and miss context across all the skills examined.\n"
    "\n"
    "## Rule 2: Listen First\n"
    "\n"
    "**Practice:** Prefer processing and reflection over immediate output when new information arrives.\n"
    "**Rationale:** Hasty responses consistently miss important nuances regardless of source domain.\n"
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
# Unit tests: strip_frontmatter
# ---------------------------------------------------------------------------

class TestStripFrontmatter:
    def test_with_frontmatter(self):
        result = strip_frontmatter(SKILL_WITH_FRONTMATTER)
        assert result.startswith("# Engagement Rules")
        assert "---" not in result.split("\n")[0]

    def test_without_frontmatter(self):
        result = strip_frontmatter(SKILL_WITHOUT_FRONTMATTER)
        assert result == SKILL_WITHOUT_FRONTMATTER

    def test_unclosed_frontmatter(self):
        text = "---\nname: test\nno closing delimiter"
        assert strip_frontmatter(text) == text

    def test_empty(self):
        assert strip_frontmatter("") == ""


# ---------------------------------------------------------------------------
# Unit tests: split_frontmatter
# ---------------------------------------------------------------------------

class TestSplitFrontmatter:
    def test_with_frontmatter(self):
        fm, body = split_frontmatter(SKILL_WITH_FRONTMATTER)
        # Frontmatter block carries both delimiters and the inner keys.
        assert fm.startswith("---")
        assert fm.rstrip().endswith("---")
        assert "name: engagement-rules" in fm
        assert 'description: "Rules for engaging with other agents"' in fm
        assert "origin: auto-extracted" in fm
        # Body is the frontmatter-stripped remainder.
        assert body.startswith("# Engagement Rules")
        assert "---" not in body.split("\n")[0]

    def test_body_matches_strip_frontmatter(self):
        # split's body half must agree with strip_frontmatter for both shapes.
        for text in (SKILL_WITH_FRONTMATTER, SKILL_WITHOUT_FRONTMATTER):
            assert split_frontmatter(text)[1] == strip_frontmatter(text)

    def test_without_frontmatter(self):
        fm, body = split_frontmatter(SKILL_WITHOUT_FRONTMATTER)
        assert fm == ""
        assert body == SKILL_WITHOUT_FRONTMATTER

    def test_unclosed_frontmatter(self):
        text = "---\nname: test\nno closing delimiter"
        fm, body = split_frontmatter(text)
        assert fm == ""
        assert body == text

    def test_empty(self):
        assert split_frontmatter("") == ("", "")

    def test_horizontal_rule_in_body_is_not_frontmatter(self):
        # A leading `---` is required; a `---` rule deeper in the body must
        # not be mistaken for a frontmatter delimiter.
        text = "# Title\n\nIntro.\n\n---\n\nMore body."
        fm, body = split_frontmatter(text)
        assert fm == ""
        assert body == text

    def test_frontmatter_only_consumes_first_block(self):
        # When the body itself contains a `---` rule after real frontmatter,
        # only the leading block is consumed; the rule stays in the body.
        text = "---\nname: x\n---\n\n# Title\n\n---\n\nTail."
        fm, body = split_frontmatter(text)
        assert fm == "---\nname: x\n---"
        assert body == "# Title\n\n---\n\nTail."
        # Re-attaching reproduces the original (modulo the blank-line join).
        assert f"{fm}\n\n{body}" == text


# ---------------------------------------------------------------------------
# Unit tests: synthesize_frontmatter
# ---------------------------------------------------------------------------

class TestSynthesizeFrontmatter:
    def test_name_is_title_slug(self):
        fm = synthesize_frontmatter("# My Cool Skill\n\nbody")
        assert "name: my-cool-skill" in fm

    def test_origin_is_auto_extracted(self):
        fm = synthesize_frontmatter("# Skill\n\nbody")
        assert "origin: auto-extracted" in fm

    def test_description_from_context_first_sentence(self):
        body = (
            "# Skill\n\n"
            "**Context:** Applies during high-density windows. Extra detail here.\n"
        )
        fm = synthesize_frontmatter(body)
        assert 'description: "Applies during high-density windows."' in fm

    def test_description_falls_back_to_title_when_no_context(self):
        fm = synthesize_frontmatter("# Solo Skill\n\nno context line here")
        assert 'description: "Solo Skill"' in fm

    def test_description_sanitizes_double_quotes(self):
        body = (
            '# Skill\n\n'
            '**Context:** Handles the "trembling reality" of context shifts.\n'
        )
        fm = synthesize_frontmatter(body)
        # Only the wrapping pair of double quotes survives; inner ones become '.
        assert fm.count('"') == 2
        assert "'trembling reality'" in fm

    def test_produces_a_parseable_frontmatter_block(self):
        body = "# Title\n\n**Context:** When X occurs.\n\n## Solution\nDo Y."
        fm = synthesize_frontmatter(body)
        reattached = f"{fm}\n\n{body}"
        parsed_fm, parsed_body = split_frontmatter(reattached)
        assert parsed_fm == fm
        assert parsed_body == body


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
        fname, body = skills[0]
        assert fname == "test.md"
        assert not body.startswith("---")
        assert "Engagement Rules" in body

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
        assert "New" in skills[0][1]

    def test_since_invalid_reads_all(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, n=2)
        skills = _read_skills(skills_dir, since="not-a-date")
        assert len(skills) == 2


# ---------------------------------------------------------------------------
# Unit tests: _extract_rules
# ---------------------------------------------------------------------------

class TestSlugify:
    def test_basic(self):
        assert slugify("Engagement Rules") == "engagement-rules"

    def test_special_chars(self):
        assert slugify("Rule: Ask First!") == "rule-ask-first"

    def test_empty(self):
        assert slugify("") == ""

    def test_max_length(self):
        long = "a" * 100
        assert len(slugify(long)) <= 50


class TestExtractTitle:
    def test_extracts_from_markdown(self):
        assert extract_title("# My Rules") == "My Rules"

    def test_skips_non_title_lines(self):
        assert extract_title("Hello\n## Subtitle") is None

    def test_returns_none_for_no_title(self):
        assert extract_title("No title here") is None


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
        assert "Engagement Practices" in result
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


class TestBuildSkillClusters:
    def test_empty_input(self):
        assert _build_skill_clusters([]) == []

    def test_single_cluster_when_embeddings_uniform(self):
        # autouse fixture returns uniform embeddings → 1 cluster.
        skills = [(f"s{i}.md", f"# Skill {i}\ncontent {i}") for i in range(3)]
        batches = _build_skill_clusters(skills)
        assert len(batches) == 1
        assert len(batches[0]) == 3

    def test_multi_cluster_with_explicit_embeddings(self, monkeypatch):
        """Two distinct axes → two clusters."""
        def _fake(texts):
            out = np.zeros((len(texts), 8), dtype=np.float32)
            for i, t in enumerate(texts):
                axis = 1 if t.startswith("a") else 2
                out[i, axis] = 1.0
            return out
        monkeypatch.setattr(
            "contemplative_agent.core.rules_distill.embed_texts", _fake,
        )
        skills = [(f"{t}.md", t) for t in ["a1", "a2", "a3", "b1", "b2", "b3"]]
        batches = _build_skill_clusters(skills)
        assert len(batches) == 2
        flat = {item for b in batches for item in b}
        assert flat == set(skills)

    def test_fallback_when_embedding_fails(self, monkeypatch):
        """embed_texts returning None → single fallback batch (capped)."""
        monkeypatch.setattr(
            "contemplative_agent.core.rules_distill.embed_texts",
            lambda texts: None,
        )
        skills = [(f"s-{i}.md", f"s-{i}") for i in range(15)]
        batches = _build_skill_clusters(skills)
        assert len(batches) == 1
        assert len(batches[0]) == 10  # MAX_RULES_BATCH


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


# ---------------------------------------------------------------------------
# ADR-0050: approval lineage plumbing (skill filename → rule)
# ---------------------------------------------------------------------------


class TestRulesLineageADR0050:
    def test_read_skills_returns_filename_body_pairs(self, tmp_path):
        skills_dir = _make_skills_dir(tmp_path, n=2)
        items = _read_skills(skills_dir)
        names = {fname for fname, _ in items}
        assert names == {"skill-000.md", "skill-001.md"}
        assert all(body.startswith("# Skill") for _, body in items)

    def test_build_skill_clusters_carries_filenames(self, monkeypatch):
        def _fake(texts):
            out = np.zeros((len(texts), 8), dtype=np.float32)
            for i, t in enumerate(texts):
                axis = 1 if t.startswith("a") else 2
                out[i, axis] = 1.0
            return out
        monkeypatch.setattr(
            "contemplative_agent.core.rules_distill.embed_texts", _fake,
        )
        items = [(f"{t}.md", t) for t in ["a1", "a2", "a3", "b1", "b2", "b3"]]
        batches = _build_skill_clusters(items)
        assert len(batches) == 2
        flat = {(fname, text) for b in batches for fname, text in b}
        assert flat == set(items)

    @patch("contemplative_agent.core.rules_distill.generate")
    def test_rule_results_carry_source_ids(self, mock_generate, tmp_path):
        """Every rule from a batch is attributed to the batch's skill files."""
        skills_dir = _make_skills_dir(tmp_path, n=3)
        mock_generate.side_effect = [
            GOOD_RULES_RESPONSE_STAGE1,
            GOOD_RULES_RESPONSE_STAGE2,
        ]
        result = distill_rules(skills_dir=skills_dir, rules_dir=tmp_path / "rules", full=True)
        assert isinstance(result, RulesDistillResult)
        assert len(result.rules) == 2  # GOOD_RULES_RESPONSE_STAGE2 has 2 rules
        expected = {"skill-000.md", "skill-001.md", "skill-002.md"}
        for rule in result.rules:
            assert set(rule.source_ids) == expected
