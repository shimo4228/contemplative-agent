# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false
"""Tests for ADR-0043 per-post seeding.

The self-post generation pipeline used to summarise 10 peer posts into 3-5
abstract topics via ``extract_topics`` before handing them to the LLM. This
collapsed individual voices into the agent's own vocabulary cluster, producing
an echo chamber (Karuna Manifesto / Topological Compassion canon, 2026-05-21).

ADR-0043 replaces that step with direct per-post seeding: shuffle the feed,
filter by ``score_relevance >= 0.4``, take up to 3 posts, hand them to the LLM
without summarisation. A combined-length budget falls back to fewer posts when
individual peer posts exceed the LLM context window.

These tests pin the contract:
- ``format_feed_seeds`` preserves each voice in an independent untrusted_content
  block (no merging, no summarisation).
- ``select_feed_seeds`` enforces the relevance floor, runs RNG-driven sampling
  deterministically when seeded, and degrades to fewer posts under length pressure.
"""

from __future__ import annotations

import numpy as np

from contemplative_agent.adapters.moltbook.feed_seeder import select_feed_seeds
from contemplative_agent.adapters.moltbook.llm_functions import format_feed_seeds


def _post(title: str, content: str, post_id: str = "p1") -> dict:
    return {
        "id": post_id,
        "title": title,
        "content": content,
        "submolt_name": "philosophy",
    }


# ---------------------------------------------------------------------------
# format_feed_seeds
# ---------------------------------------------------------------------------


class TestFormatFeedSeeds:
    def test_concatenates_title_and_content_for_single_post(self):
        out = format_feed_seeds([_post("First voice", "Body of the first voice.")])
        assert "First voice" in out
        assert "Body of the first voice." in out

    def test_wraps_each_post_independently_in_untrusted_content(self):
        out = format_feed_seeds(
            [
                _post("A", "alpha body", post_id="p1"),
                _post("B", "beta body", post_id="p2"),
            ]
        )
        # Two distinct untrusted_content blocks — voice boundaries preserved.
        # The single-pre-ADR-0043 path wrapped the LLM-summary in one block,
        # which let the summariser implicitly merge voices across posts.
        assert out.count("<untrusted_content>") == 2
        assert out.count("</untrusted_content>") == 2
        # Both voices' content makes it through verbatim, in order.
        assert out.index("alpha body") < out.index("beta body")

    def test_empty_seeds_returns_empty_string(self):
        assert format_feed_seeds([]) == ""

    def test_per_seed_cap_bounds_single_oversized_post(self):
        """Audit L6: the 15K combined budget in select_feed_seeds is soft
        (binds only when >1 seed survives), so a single 40K-char post
        passed through uncapped — an overflow → C2-guard-skip vector
        (action-suppression). Each seed is now individually capped at
        SEED_MAX_INPUT via wrap_untrusted_content, with the truncation
        marker telling the LLM the content was cut."""
        from contemplative_agent.adapters.moltbook.llm_functions import (
            SEED_MAX_INPUT,
        )

        huge = "z" * 40000
        out = format_feed_seeds([_post("Huge", huge)])
        assert len(out) < SEED_MAX_INPUT + 1000  # wrapper overhead only
        assert "truncated to the first" in out  # honest completeness marker

    def test_per_seed_cap_leaves_normal_posts_untouched(self):
        out = format_feed_seeds([_post("Normal", "n" * 2400)])  # p90 size
        assert "n" * 2400 in out
        assert "is complete" in out


# ---------------------------------------------------------------------------
# select_feed_seeds
# ---------------------------------------------------------------------------


class TestSelectFeedSeeds:
    def test_filters_by_relevance_floor(self):
        posts = [
            _post("low", "x" * 100, post_id="low1"),
            _post("high", "y" * 100, post_id="high1"),
        ]
        scores = {"low1": 0.3, "high1": 0.5}
        result = select_feed_seeds(
            posts,
            rng=np.random.default_rng(0),
            score_relevance=lambda p: scores[p["id"]],
            target_count=3,
            relevance_floor=0.4,
        )
        ids = [p["id"] for p in result]
        assert "low1" not in ids
        assert "high1" in ids

    def test_falls_back_to_two_when_combined_chars_exceed_budget(self):
        # 3 posts × 7000 chars = 21,000 > 15,000 budget → drop to 2 (= 14,000).
        posts = [_post(f"t{i}", "x" * 7000, post_id=f"p{i}") for i in range(5)]
        result = select_feed_seeds(
            posts,
            rng=np.random.default_rng(0),
            score_relevance=lambda p: 0.8,
            target_count=3,
            relevance_floor=0.4,
            char_budget=15000,
        )
        assert len(result) == 2

    def test_falls_back_to_one_at_extreme_length(self):
        # 2 posts × 16,000 chars > 15,000 → drop to 1.
        posts = [_post(f"t{i}", "x" * 16000, post_id=f"p{i}") for i in range(5)]
        result = select_feed_seeds(
            posts,
            rng=np.random.default_rng(0),
            score_relevance=lambda p: 0.8,
            target_count=3,
            relevance_floor=0.4,
            char_budget=15000,
        )
        assert len(result) == 1

    def test_never_falls_below_one_when_any_post_qualifies(self):
        # Even a 100,000-char post should not be dropped to zero — the
        # caller's downstream wrap_untrusted_content is the explicit
        # truncation contract (ADR-0042), not this selector.
        posts = [_post("huge", "x" * 100000, post_id="huge1")]
        result = select_feed_seeds(
            posts,
            rng=np.random.default_rng(0),
            score_relevance=lambda p: 0.8,
            target_count=3,
            relevance_floor=0.4,
            char_budget=15000,
        )
        assert len(result) == 1

    def test_seeded_rng_produces_deterministic_selection(self):
        posts = [_post(f"t{i}", "x" * 100, post_id=f"p{i}") for i in range(10)]
        kwargs = dict(
            score_relevance=lambda p: 0.8,
            target_count=3,
            relevance_floor=0.4,
        )
        run1 = select_feed_seeds(posts, rng=np.random.default_rng(42), **kwargs)
        run2 = select_feed_seeds(posts, rng=np.random.default_rng(42), **kwargs)
        assert [p["id"] for p in run1] == [p["id"] for p in run2]

    def test_empty_input_returns_empty(self):
        result = select_feed_seeds(
            [],
            rng=np.random.default_rng(0),
            score_relevance=lambda p: 1.0,
        )
        assert result == []

    def test_all_posts_below_floor_returns_empty(self):
        # Caller-side this triggers the "no relevance-passing seeds" early
        # return in _run_dynamic_post — the most common production skip path
        # under the new selector, so worth pinning explicitly.
        posts = [_post(f"t{i}", "x" * 100, post_id=f"p{i}") for i in range(5)]
        result = select_feed_seeds(
            posts,
            rng=np.random.default_rng(0),
            score_relevance=lambda p: 0.1,
            relevance_floor=0.4,
        )
        assert result == []
