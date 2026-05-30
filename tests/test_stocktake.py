"""Tests for core.stocktake — skill and rule auditing."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np

from contemplative_agent.core.stocktake import (
    SIM_CLUSTER_THRESHOLD,
    MergeGroup,
    QualityIssue,
    StocktakeResult,
    _PER_FILE_MERGE_TOKENS,
    _check_rule_quality,
    _check_skill_quality,
    _cluster_pairs,
    _find_duplicate_groups,
    _normalize_for_similarity,
    _pairwise_similarity,
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


def _vecs(*similarity_to_first: float) -> np.ndarray:
    """Build mock embedding vectors with controlled cosines to vector 0.

    Vector 0 is e_0 (all weight on first axis). Vector i is constructed so
    that cosine(v_0, v_i) == similarity_to_first[i], with the residual on a
    distinct axis per i (so non-first pairs have predictable similarity too).
    """
    n = len(similarity_to_first)
    dim = max(n, 4)
    vectors = np.zeros((n, dim), dtype=np.float32)
    vectors[0, 0] = 1.0
    for i in range(1, n):
        s = similarity_to_first[i]
        vectors[i, 0] = s
        # Residual on a per-i axis so v_i are linearly independent
        vectors[i, i] = float(np.sqrt(max(0.0, 1.0 - s * s)))
    return vectors


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
# Unit tests: _normalize_for_similarity
# ---------------------------------------------------------------------------

class TestNormalizeForSimilarity:
    def test_strips_markdown_headings(self):
        body = "## Problem\nfoo\n## Solution\nbar"
        out = _normalize_for_similarity(body)
        assert "##" not in out
        assert "foo" in out and "bar" in out

    def test_collapses_whitespace(self):
        body = "foo   bar\n\n\nbaz\t\tqux"
        out = _normalize_for_similarity(body)
        assert "  " not in out
        assert "\n\n" not in out

    def test_preserves_alphanumerics(self):
        body = "## Header\nthe quick brown fox"
        out = _normalize_for_similarity(body)
        assert "quick brown fox" in out


# ---------------------------------------------------------------------------
# Unit tests: _pairwise_similarity
# ---------------------------------------------------------------------------

class TestPairwiseSimilarity:
    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_identical_bodies_cosine_1(self, mock_embed):
        mock_embed.return_value = _vecs(1.0, 1.0)
        items = [("a.md", "alpha beta gamma"), ("b.md", "alpha beta gamma")]
        pairs = _pairwise_similarity(items)
        assert len(pairs) == 1
        assert pairs[0][0] == 0 and pairs[0][1] == 1

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_distinct_bodies_low_cosine(self, mock_embed):
        mock_embed.return_value = _vecs(1.0, 0.1)
        items = [("a.md", "alpha"), ("b.md", "completely different")]
        pairs = _pairwise_similarity(items)
        assert pairs[0][2] < 0.6

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_n_choose_2_pairs(self, mock_embed):
        mock_embed.return_value = _vecs(1.0, 0.5, 0.5, 0.5)
        items = [(f"f{i}.md", f"content {i}") for i in range(4)]
        pairs = _pairwise_similarity(items)
        assert len(pairs) == 6  # C(4,2)

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_indices_are_i_lt_j(self, mock_embed):
        mock_embed.return_value = _vecs(1.0, 0.5, 0.5)
        items = [(f"f{i}.md", f"body {i}") for i in range(3)]
        pairs = _pairwise_similarity(items)
        for i, j, _ in pairs:
            assert i < j

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_embedding_failure_returns_empty(self, mock_embed):
        mock_embed.return_value = None
        items = [("a.md", "x"), ("b.md", "y")]
        assert _pairwise_similarity(items) == []


# ---------------------------------------------------------------------------
# Unit tests: _cluster_pairs (transitive closure / union-find)
# ---------------------------------------------------------------------------

class TestClusterPairs:
    def test_transitive_closure(self):
        # (0,1) and (1,2) should produce one cluster {0,1,2}
        pairs = [(0, 1, 0.9), (1, 2, 0.9)]
        clusters = _cluster_pairs(pairs, item_count=3)
        assert len(clusters) == 1
        assert clusters[0] == {0, 1, 2}

    def test_disconnected_stays_separate(self):
        pairs = [(0, 1, 0.9), (2, 3, 0.9)]
        clusters = _cluster_pairs(pairs, item_count=4)
        assert len(clusters) == 2
        sets = sorted([sorted(c) for c in clusters])
        assert sets == [[0, 1], [2, 3]]

    def test_singleton_items_not_returned(self):
        # Item 4 has no pair → should not appear as a cluster of size 1
        pairs = [(0, 1, 0.9)]
        clusters = _cluster_pairs(pairs, item_count=5)
        assert len(clusters) == 1
        assert clusters[0] == {0, 1}

    def test_empty_pairs_returns_empty(self):
        assert _cluster_pairs([], item_count=5) == []

    def test_full_chain(self):
        pairs = [(0, 1, 0.9), (1, 2, 0.9), (2, 3, 0.9), (3, 4, 0.9)]
        clusters = _cluster_pairs(pairs, item_count=5)
        assert len(clusters) == 1
        assert clusters[0] == {0, 1, 2, 3, 4}


# ---------------------------------------------------------------------------
# Unit tests: _find_duplicate_groups (embedding-only clustering)
# ---------------------------------------------------------------------------

class TestFindDuplicateGroups:
    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_high_similarity_clusters(self, mock_embed):
        # cosine 1.0 ≥ threshold → grouped
        mock_embed.return_value = _vecs(1.0, 1.0)
        items = [("a.md", "the same exact body"), ("b.md", "the same exact body")]
        groups = _find_duplicate_groups(items)
        assert len(groups) == 1
        assert set(groups[0].filenames) == {"a.md", "b.md"}

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_threshold_boundary_inclusive(self, mock_embed):
        # cosine == SIM_CLUSTER_THRESHOLD → included
        mock_embed.return_value = _vecs(1.0, SIM_CLUSTER_THRESHOLD)
        items = [("a.md", "a"), ("b.md", "b")]
        groups = _find_duplicate_groups(items)
        assert len(groups) == 1

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_below_threshold_excluded(self, mock_embed):
        # cosine just below threshold → excluded
        mock_embed.return_value = _vecs(1.0, SIM_CLUSTER_THRESHOLD - 0.05)
        items = [("a.md", "a"), ("b.md", "b")]
        assert _find_duplicate_groups(items) == []

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_distinct_skills_no_group(self, mock_embed):
        # cosine 0.3 → well below threshold
        mock_embed.return_value = _vecs(1.0, 0.3)
        items = [("a.md", "body a"), ("b.md", "body b")]
        assert _find_duplicate_groups(items) == []

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_embedding_failure_returns_empty(self, mock_embed):
        mock_embed.return_value = None
        items = [("a.md", "x"), ("b.md", "y")]
        assert _find_duplicate_groups(items) == []

    def test_single_file_skips_pipeline(self):
        items = [("a.md", "content")]
        assert _find_duplicate_groups(items) == []

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_transitive_clustering_via_embedding(self, mock_embed):
        """8 structurally-identical skills all share similarity >= threshold
        with vector 0; union-find collapses them into ONE group."""
        mock_embed.return_value = _vecs(1.0, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85, 0.85)
        items = [(f"skill-{i}.md", f"body {i}") for i in range(8)]
        groups = _find_duplicate_groups(items)
        assert len(groups) == 1
        assert len(groups[0].filenames) == 8

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_reason_includes_threshold_and_max_ratio(self, mock_embed):
        mock_embed.return_value = _vecs(1.0, 0.95)
        items = [("a.md", "x"), ("b.md", "y")]
        groups = _find_duplicate_groups(items)
        assert len(groups) == 1
        assert "0.95" in groups[0].reason or "0.9" in groups[0].reason


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
    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_detects_merges_and_quality(self, mock_embed, tmp_path):
        # Three files: a/b cluster via cosine 1.0, short.md unrelated
        mock_embed.return_value = _vecs(1.0, 1.0, 0.2)
        skills_dir = _make_skills_dir(tmp_path, {
            "a.md": GOOD_SKILL,
            "b.md": GOOD_SKILL,
            "short.md": SHORT_SKILL,
        })
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert isinstance(result, StocktakeResult)
        assert len(result.merge_groups) == 1
        assert len(result.quality_issues) >= 1  # short.md
        assert result.total_files == 3

    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_no_issues(self, mock_embed, tmp_path):
        # Single file: embedding not invoked (below MIN_FILES_FOR_DEDUP)
        skills_dir = _make_skills_dir(tmp_path, {
            "good.md": GOOD_SKILL,
        })
        result = run_skill_stocktake(skills_dir=skills_dir)
        assert result.merge_groups == ()
        assert result.quality_issues == ()
        assert mock_embed.call_count == 0

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
    def test_detects_quality_issue(self, tmp_path):
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
    @patch("contemplative_agent.core.stocktake.embed_texts")
    def test_skills_and_rules_do_not_mix(self, mock_embed, tmp_path):
        """Skill stocktake does not read rules, and vice versa."""
        skills_dir = _make_skills_dir(tmp_path, {"s.md": GOOD_SKILL})
        rules_dir = _make_rules_dir(tmp_path, {"r.md": GOOD_RULE})

        skill_result = run_skill_stocktake(skills_dir=skills_dir)
        rule_result = run_rules_stocktake(rules_dir=rules_dir)

        assert skill_result.total_files == 1
        assert rule_result.total_files == 1
        # Each only saw its own files; embedding skipped (below MIN_FILES_FOR_DEDUP)
        assert mock_embed.call_count == 0


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
