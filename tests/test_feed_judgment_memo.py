# pyright: reportPrivateUsage=false
"""Same post, same session: the judgment is computed once (RFC-0032).

The submolt feed cache (``_FEED_CACHE_TTL``, 600s) outlives the cycle wait
(``base_cycle_wait``, 60s) by ~10x, so one cached post dict reaches
``engage_with_post`` about ten times. Only the *actions* were deduplicated
(``_upvoted_posts`` / ``commented_posts``); the *judgments* — relevance score,
full-body GET, internal note — were recomputed every cycle and discarded.
"""

import time
from dataclasses import replace
from unittest.mock import MagicMock, patch

from contemplative_agent.adapters.moltbook.config import FEED_CONTENT_PREVIEW_LEN
from contemplative_agent.adapters.moltbook.llm_functions import RelevanceScore
from tests.test_agent import _make_agent, _make_clean_memory, _scored

# Near-miss band: above upvote_only_threshold (0.70) so the full-body GET and
# the internal note both fire, below relevance_threshold (0.80) so no comment
# is posted — the highest-frequency repeat path the RFC names.
_NEAR_MISS = 0.75
_CYCLES = 3


def _wire_cached_feed(client, post):
    """One post, served from the submolt feed cache on every later cycle."""
    client.has_read_budget.return_value = True
    client.has_write_budget.return_value = True
    client.get_following_feed.return_value = []
    client.get_submolt_feed.return_value = [post]
    client.upvote_post.return_value = True
    client.get_post.return_value = {"id": post["id"], "content": "full body " * 80}


def _run_cycles(agent, n=_CYCLES):
    for _ in range(n):
        agent._run_feed_cycle(time.time() + 3600)


class TestJudgmentMemoizedPerSession:
    def _agent(self, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path, content=MagicMock())
        post = {"content": "x" * FEED_CONTENT_PREVIEW_LEN, "id": "post1"}
        _wire_cached_feed(client, post)
        return agent, client, scheduler

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="noticed",
    )
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(_NEAR_MISS),
    )
    def test_score_note_and_full_fetch_run_once_across_cycles(
        self, mock_score, mock_note, tmp_path
    ):
        agent, client, _ = self._agent(tmp_path)

        _run_cycles(agent)

        # The premise: the feed really was served from cache after cycle 1.
        assert client.get_submolt_feed.call_count == len(
            agent._feed_manager._domain.subscribed_submolts
        )
        assert mock_score.call_count == 1
        assert mock_note.call_count == 1
        assert client.get_post.call_count == 1

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="noticed",
    )
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(_NEAR_MISS),
    )
    def test_reused_judgment_keeps_the_upvote_only_outcome(self, mock_score, mock_note, tmp_path):
        agent, client, _ = self._agent(tmp_path)

        _run_cycles(agent)

        # Behaviour is unchanged: still one upvote, still no comment.
        client.upvote_post.assert_called_once_with("post1")
        client.post_comment.assert_not_called()

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="noticed",
    )
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(_NEAR_MISS),
    )
    def test_skipped_rejudgements_are_counted(self, mock_score, mock_note, tmp_path):
        agent, client, _ = self._agent(tmp_path)

        _run_cycles(agent)

        assert agent._feed_manager.rejudges_skipped == _CYCLES - 1

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="noticed",
    )
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(_NEAR_MISS),
    )
    def test_skip_is_logged_with_a_reason_code(self, mock_score, mock_note, tmp_path, caplog):
        agent, client, _ = self._agent(tmp_path)

        with caplog.at_level("INFO"):
            _run_cycles(agent)

        assert sum("already_judged" in r.message for r in caplog.records) == _CYCLES - 1

    def test_session_end_episode_carries_the_skip_count(self, tmp_path):
        memory = _make_clean_memory(tmp_path)
        agent, client, _ = _make_agent(tmp_path, memory=memory, content=MagicMock())
        post = {"content": "x" * FEED_CONTENT_PREVIEW_LEN, "id": "post1"}
        _wire_cached_feed(client, post)
        with (
            patch(
                "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
                return_value=_scored(_NEAR_MISS),
            ),
            patch(
                "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
                return_value="noticed",
            ),
        ):
            _run_cycles(agent)
        agent._log_session_end(duration_minutes=1)

        end = memory.episodes.read_range(days=1, record_type="session")[-1]
        assert end["data"]["feed_rejudges_skipped"] == _CYCLES - 1


class TestJudgmentUpgradesWhenTheBarDrops:
    """A judgment taken below the engage bar is completed if the bar drops.

    ``_relevance_threshold`` returns ``known_agent_threshold`` once we have
    interacted with the author, which can lower ``engage_bar``. A score cached
    below the old bar must then get its full body — without paying for a second
    ``score_relevance``. (Unreachable on the shipped domain.json,
    where known_agent == upvote_only == 0.70; reachable for any config that
    sets known_agent lower, so the branch is tested at that config.)
    """

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="noticed",
    )
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(0.68),
    )
    def test_full_fetch_fires_once_after_the_bar_drops(self, mock_score, mock_note, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path, content=MagicMock())
        fm = agent._feed_manager
        fm._domain = replace(fm._domain, known_agent_threshold=0.60)
        post = {
            "content": "x" * FEED_CONTENT_PREVIEW_LEN,
            "id": "post1",
            "author": {"id": "author-1", "name": "Alice"},
        }
        _wire_cached_feed(client, post)
        scheduler.can_comment.return_value = False  # stop before the comment path

        # Bar is min(0.70, 0.80) = 0.70 > 0.68: scored, nothing else.
        fm.engage_with_post(post, client, scheduler)
        assert mock_note.call_count == 0
        assert client.get_post.call_count == 0

        # Author now known: threshold 0.60, bar min(0.70, 0.60) = 0.60 <= 0.68.
        with patch.object(fm._ctx.memory, "has_interacted_with", return_value=True):
            fm.engage_with_post(post, client, scheduler)
            fm.engage_with_post(post, client, scheduler)

        assert mock_score.call_count == 1  # the score itself is never recomputed
        assert client.get_post.call_count == 1  # the bar-gated half ran, once
        # The note keeps its own, unchanged bar (upvote_only_threshold = 0.70),
        # which 0.68 still misses — dropping the comment threshold must not
        # start generating notes for posts that never earned one.
        assert mock_note.call_count == 0


class TestFailuresAreNotMemoized:
    """Only a real judgment is frozen — a failed one is retried next cycle.

    Every part of the judgment has a failure mode that returns a legal-looking
    value: ``score_relevance_detailed`` returns 0.0 with a non-``scored``
    reason, ``_fetch_full_if_truncated`` falls back to the truncated preview,
    ``generate_internal_note`` returns "". Memoizing any of them would make a
    transient failure permanent for the session; before the memo existed the
    next cycle is what recovered from it.
    """

    def _agent(self, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path, content=MagicMock())
        post = {"content": "x" * FEED_CONTENT_PREVIEW_LEN, "id": "post1"}
        _wire_cached_feed(client, post)
        return agent, client, scheduler

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=RelevanceScore(0.0, "llm_unavailable"),
    )
    def test_a_failure_sentinel_score_is_rescored(self, mock_score, tmp_path):
        agent, client, _ = self._agent(tmp_path)

        _run_cycles(agent)

        assert mock_score.call_count == _CYCLES
        assert agent._feed_manager.rejudges_skipped == 0

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="noticed",
    )
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(_NEAR_MISS),
    )
    def test_a_preview_fallback_body_is_refetched(self, mock_score, mock_note, tmp_path):
        agent, client, _ = self._agent(tmp_path)
        # get_post yields nothing longer: the preview is kept as a fallback.
        client.get_post.return_value = {"id": "post1", "content": "y" * FEED_CONTENT_PREVIEW_LEN}

        _run_cycles(agent)

        assert client.get_post.call_count == _CYCLES
        assert agent._feed_manager.rejudges_skipped == 0

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="",
    )
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(_NEAR_MISS),
    )
    def test_a_failed_note_is_regenerated(self, mock_score, mock_note, tmp_path):
        agent, client, _ = self._agent(tmp_path)

        _run_cycles(agent)

        assert mock_note.call_count == _CYCLES
        assert agent._feed_manager.rejudges_skipped == 0
