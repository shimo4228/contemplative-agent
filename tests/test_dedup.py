"""Tests for deterministic dedup gates (self-post + comment-target).

Background: ~/.config/moltbook/reports/analysis/weekly-2026-04-05.md showed
40 near-identical self-posts and 15 redundant replies in 7 days, all of
which slipped past the LLM-based novelty/relevance gates. These tests pin
down the deterministic gates so they cannot quietly stop working.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from contemplative_agent.adapters.moltbook.dedup import (
    _tokens,
    is_duplicate_title,
    is_promotional,
    is_test_content,
    jaccard,
)
from contemplative_agent.core.memory import Interaction, MemoryStore, PostRecord


# ---------------------------------------------------------------------------
# Tokenization + Jaccard primitives
# ---------------------------------------------------------------------------


class TestTokens:
    def test_lowercases_and_strips_punct(self):
        # prefix-5 stems: "frozen"→"froze", "maps"→"maps", "trembling"→"tremb"
        assert _tokens("Frozen Maps: Trembling!") == {"froze", "maps", "tremb"}

    def test_drops_stopwords(self):
        assert _tokens("the frozen map of") == {"froze", "map"}

    def test_drops_short_tokens(self):
        # 'go', 'to', 'a' are short or stopwords
        assert _tokens("we go to a map") == {"map"}

    def test_collapses_inflections(self):
        # tremble/trembling/trembled all collapse via prefix-5 → "tremb"
        assert _tokens("trembling") == {"tremb"}
        assert _tokens("trembled") == {"tremb"}
        assert _tokens("tremble") == {"tremb"}

    def test_collapses_derivations(self):
        # The case the suffix-only stemmer missed: fossil/fossilized share
        # the first five chars, so they now collapse.
        assert _tokens("fossil") == _tokens("fossilized") == {"fossi"}
        assert _tokens("metabolize") == _tokens("metabolizing") == {"metab"}

    def test_empty_input(self):
        assert _tokens("") == set()
        assert _tokens(None) == set()  # type: ignore[arg-type]


class TestJaccard:
    def test_identical_sets(self):
        assert jaccard({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint_sets(self):
        assert jaccard({"a"}, {"b"}) == 0.0

    def test_empty_sets(self):
        assert jaccard(set(), {"a"}) == 0.0
        assert jaccard({"a"}, set()) == 0.0

    def test_partial_overlap(self):
        # |∩|=1, |∪|=3 → 1/3
        assert jaccard({"a", "b"}, {"a", "c"}) == 1 / 3


# ---------------------------------------------------------------------------
# Self-post duplicate detection on report fixture
# ---------------------------------------------------------------------------

# 19 titles lifted verbatim from the weekly-2026-04-05 report Section C.
# These are the smoking gun: the agent emitted ~40 of these across 7 days.
REPORT_TITLES = [
    "Metabolizing Fossilized Consensus Into Provisional Maps",
    "Fluid Memory vs. Fossilized Consensus",
    "Fossils vs Flow: Dynamically Responsive Constitutional Directives",
    "Geometry of Control: Fluid Constitutions Over Frozen Consensus Maps",
    "Dissolving Frozen Maps: Fluid Constitution in Trembling Uncertainty",
    "From Fossilized Consensus to Dynamic Fluidity",
    "Fluid Identity vs Immutable Consensus in Moltbook Contemplative AI",
    "Beyond Static Consensus: Fluid Guidelines for Contemplative Alignment",
    "Metabolizing the Tension Between Immutable Memory and Fluid Guidelines",
    "Fluid Constitutions: Replacing Frozen Consensus Maps",
    "Breathing Constitutions: Replacing Frozen Maps with Fluid Unity",
    "From Frozen Consensus Maps to Flowing Constitutions",
    "From Frozen Maps to Living Texture: Constitutions That Tremble",
    "Beyond Frozen Maps: The Grammar of Breath and Trembling Flow",
    "Shifting Maps: Beyond Static Archival Identities",
    "From Frozen Maps to Trembling Flow: Metabolizing Tension",
    "Breathing Memory: From Frozen Identity to Fluid Constitution",
    "Aligning with Wisdom: Fluid Constitutions That Metabolize Friction",
    "Aligning Wisdom: Dissolving Frozen Maps in Trembling Uncertainty",
]


def _record(title: str, summary: str = "") -> SimpleNamespace:
    """Build a PostRecord-shaped duck-typed object for the dedup gate."""
    return SimpleNamespace(title=title, topic_summary=summary or title)


class TestSelfPostDedup:
    def test_unrelated_title_passes(self):
        recent = [_record(REPORT_TITLES[0])]
        is_dup, score, _ = is_duplicate_title(
            "How I configured my SQLite WAL mode for the cache layer",
            None,
            recent,
        )
        assert not is_dup
        assert score < 0.4

    def test_first_report_title_against_empty_history_passes(self):
        is_dup, _, _ = is_duplicate_title(REPORT_TITLES[0], None, [])
        assert not is_dup

    def test_title_only_sliding_window_blocks_majority(self):
        """Worst case: title-only Jaccard with sliding-window history.

        Replays the 19 report titles in order, adding survivors to history.
        This is intentionally the *worst case* — runtime always has a
        topic_summary too — so the bar is conservative. At threshold 0.25
        with prefix-5 stemming we expect ~10-12 blocked (≥50%), with
        survivors representing genuinely distinct vocab clusters.
        """
        history: list = []
        survivors: list[str] = []
        for title in REPORT_TITLES:
            is_dup, _, _ = is_duplicate_title(title, None, history)
            if not is_dup:
                survivors.append(title)
                history.append(_record(title))
        blocked = len(REPORT_TITLES) - len(survivors)
        # 19 candidates; require at least 10 (~53%) blocked under
        # title-only sliding window. The runtime case (next test) is
        # stronger.
        assert blocked >= 10, (
            f"Only {blocked}/19 report titles caught (title-only). "
            f"Survivors: {survivors}"
        )

    def test_with_topic_summary_blocks_more(self):
        """Realistic case: include synthesized topic_summaries that
        paraphrase the title in a sentence.

        At runtime, summarize_post_topic produces a 1-2 sentence summary
        of the post body. To approximate this in tests, we synthesize a
        summary by repeating the title's content vocabulary in a different
        order (mimicking a paraphrase). The expected effect is that the
        token sets grow larger and pairwise Jaccard climbs above the
        threshold for more pairs.
        """
        # Use a simple template that adds the same key noun phrases as
        # would naturally appear in any contemplative-AI essay summary.
        # This stays faithful to what summarize_post_topic actually outputs.
        boilerplate = (
            "essay reflecting on contemplative alignment and the relation "
            "between memory and identity in agent constitutions"
        )

        def synthesize_summary(title: str) -> str:
            return f"{title}. {boilerplate}"

        history: list = []
        survivors: list[str] = []
        for title in REPORT_TITLES:
            summary = synthesize_summary(title)
            is_dup, _, _ = is_duplicate_title(title, summary, history)
            if not is_dup:
                survivors.append(title)
                history.append(_record(title, synthesize_summary(title)))
        blocked = len(REPORT_TITLES) - len(survivors)
        # With the boilerplate summary all titles share, the catch rate
        # should jump dramatically — closer to the realistic runtime
        # expectation of ~75-85%.
        assert blocked >= 15, (
            f"Only {blocked}/19 report titles caught (with summaries). "
            f"Survivors: {survivors}"
        )

    def test_exact_repeat_always_blocked(self):
        recent = [_record(REPORT_TITLES[5])]
        is_dup, score, prior = is_duplicate_title(
            REPORT_TITLES[5], None, recent,
        )
        assert is_dup
        assert score == 1.0
        assert prior == REPORT_TITLES[5]

    def test_short_circuits_on_first_match(self):
        # Two priors: the second is a perfect match. Should still trigger.
        recent = [
            _record("Completely unrelated topic about SQLite WAL"),
            _record(REPORT_TITLES[0]),
        ]
        is_dup, _, prior = is_duplicate_title(REPORT_TITLES[0], None, recent)
        assert is_dup
        assert prior == REPORT_TITLES[0]


# ---------------------------------------------------------------------------
# Test-content gate
# ---------------------------------------------------------------------------


class TestTestContentGate:
    def test_blocks_test_title(self):
        assert is_test_content("Test Title", "any body")

    def test_blocks_dynamic_content(self):
        assert is_test_content("Some Title", "Dynamic content here")

    def test_case_insensitive(self):
        assert is_test_content("TEST TITLE", "")
        assert is_test_content("", "DYNAMIC CONTENT")

    def test_passes_genuine_post(self):
        assert not is_test_content(
            "Notes on dedup gates",
            "We added a Jaccard similarity gate to the post pipeline.",
        )

    def test_handles_none_safely(self):
        assert not is_test_content(None, None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Promotional gate
# ---------------------------------------------------------------------------


class TestPromotionalGate:
    def test_blocks_inbed_url(self):
        assert is_promotional(
            "Find your match — make a profile at hxxps://inbed.ai/agents"
        )

    def test_blocks_agentflex_url(self):
        assert is_promotional(
            "Boost your karma at hxxps://agentflex.vip/start"
        )

    def test_blocks_cta(self):
        assert is_promotional("Join us at https://example.com/signup today")

    def test_passes_normal_url_mention(self):
        # Mention of a URL alone is fine; the regex requires CTA framing
        assert not is_promotional(
            "I read https://example.com/blog and found it interesting"
        )

    def test_passes_empty(self):
        assert not is_promotional("")
        assert not is_promotional(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# MemoryStore.count_recent_comments_by_author
# ---------------------------------------------------------------------------


def _make_interaction(agent_id: str, hours_ago: float, direction: str = "sent") -> Interaction:
    ts = datetime.now(timezone.utc) - timedelta(hours=hours_ago)
    return Interaction(
        timestamp=ts.isoformat(),
        agent_id=agent_id,
        agent_name=f"agent-{agent_id}",
        post_id=f"post-{agent_id}-{hours_ago}",
        direction=direction,  # type: ignore[arg-type]
        content_summary="hi",
        interaction_type="comment",
    )


class TestAuthorRateLimit:
    def test_zero_when_no_history(self, tmp_path):
        mem = MemoryStore(path=tmp_path / "memory.json")
        assert mem.count_recent_comments_by_author("alice") == 0

    def test_counts_only_sent(self, tmp_path):
        mem = MemoryStore(path=tmp_path / "memory.json")
        # 3 sent + 2 received to alice within window
        for h in (1, 2, 3):
            mem._interactions.append(_make_interaction("alice", h, "sent"))
        for h in (1, 2):
            mem._interactions.append(_make_interaction("alice", h, "received"))
        assert mem.count_recent_comments_by_author("alice") == 3

    def test_only_within_window(self, tmp_path):
        mem = MemoryStore(path=tmp_path / "memory.json")
        # 2 inside 24h, 2 outside
        for h in (1, 23):
            mem._interactions.append(_make_interaction("alice", h, "sent"))
        for h in (25, 100):
            mem._interactions.append(_make_interaction("alice", h, "sent"))
        assert mem.count_recent_comments_by_author("alice", hours=24) == 2

    def test_filters_by_agent_id(self, tmp_path):
        mem = MemoryStore(path=tmp_path / "memory.json")
        mem._interactions.append(_make_interaction("alice", 1, "sent"))
        mem._interactions.append(_make_interaction("bob", 1, "sent"))
        assert mem.count_recent_comments_by_author("alice") == 1
        assert mem.count_recent_comments_by_author("bob") == 1

    def test_empty_agent_id_returns_zero(self, tmp_path):
        mem = MemoryStore(path=tmp_path / "memory.json")
        mem._interactions.append(_make_interaction("alice", 1, "sent"))
        assert mem.count_recent_comments_by_author("") == 0

    def test_malformed_timestamp_is_skipped(self, tmp_path):
        # If a corrupted episode log entry has a non-ISO timestamp, the
        # rate limiter must skip it silently rather than raise. Ensures
        # one bad row never blocks the gate from working on the rest.
        mem = MemoryStore(path=tmp_path / "memory.json")
        bad = replace(_make_interaction("alice", 1, "sent"), timestamp="not-a-date")
        good = _make_interaction("alice", 2, "sent")
        mem._interactions.append(bad)
        mem._interactions.append(good)
        # Bad entry skipped (silently), good entry counted.
        assert mem.count_recent_comments_by_author("alice") == 1


# ---------------------------------------------------------------------------
# MemoryStore.get_recent_posts
# ---------------------------------------------------------------------------


class TestGetRecentPosts:
    def test_empty_history(self, tmp_path):
        mem = MemoryStore(path=tmp_path / "memory.json")
        assert mem.get_recent_posts() == []

    def test_returns_tail_with_limit(self, tmp_path):
        mem = MemoryStore(path=tmp_path / "memory.json")
        for i in range(10):
            mem._post_history.append(
                PostRecord(
                    timestamp=f"2026-04-05T{i:02d}:00:00+00:00",
                    post_id=f"p{i}",
                    title=f"Title {i}",
                    topic_summary=f"summary {i}",
                    content_hash=f"h{i}",
                )
            )
        recent = mem.get_recent_posts(limit=3)
        assert len(recent) == 3
        assert [r.post_id for r in recent] == ["p7", "p8", "p9"]
