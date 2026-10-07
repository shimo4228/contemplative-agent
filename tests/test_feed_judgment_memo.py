"""Same post, same session: the judgment is computed once (RFC-0032).

The submolt feed cache (``_FEED_CACHE_TTL``, 600s) outlives the cycle wait
(``base_cycle_wait``, 60s) by ~10x, so one cached post dict reaches
``engage_with_post`` about ten times. Only the *actions* were deduplicated
(``_upvoted_posts`` / ``commented_posts``); the *judgments* — the relevance
gate, full-body GET, internal note — were recomputed every cycle and discarded.

Since RFC-0046 cleanup 2 the gate is the score4 read alone
(``feed_manager.enforce_and_record`` is the seam stubbed here); only a passed
post has a full body and a note to compute.
"""

import time
from unittest.mock import MagicMock, patch

from contemplative_agent.adapters.moltbook.config import FEED_CONTENT_PREVIEW_LEN
from contemplative_agent.adapters.moltbook.relevance_shadow import (
    EnforceOutcome,
    RecordedReading,
)
from contemplative_agent.core.llm import GenerationOutput
from tests.test_agent import _gate, _make_agent, _make_clean_memory

FM = "contemplative_agent.adapters.moltbook.feed_manager"
_CYCLES = 3
_PASS = _gate(0.9)
_CLOSED = _gate(0.1)
_BACKEND_NULL = RecordedReading(
    EnforceOutcome("fail_closed", None, "enforce_backend_null", 0.3),
    {"decision_reason": "http_error", "decision_p_top": None},
)


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


def _agent(tmp_path, memory=None):
    """One preview-length post; the comment comes back empty, so it stays uncommented."""
    content = MagicMock()
    content.create_comment.return_value = GenerationOutput(text=None)
    agent, client, scheduler = _make_agent(tmp_path, content=content, memory=memory)
    post = {"content": "x" * FEED_CONTENT_PREVIEW_LEN, "id": "post1"}
    _wire_cached_feed(client, post)
    return agent, client, scheduler


class TestJudgmentMemoizedPerSession:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.enforce_and_record", return_value=_PASS)
    def test_gate_note_and_full_fetch_run_once_across_cycles(self, mock_gate, mock_note, tmp_path):
        agent, client, _ = _agent(tmp_path)

        _run_cycles(agent)

        # The premise: the feed really was served from cache after cycle 1.
        assert client.get_submolt_feed.call_count == len(
            agent._feed_manager._domain.subscribed_submolts
        )
        assert mock_gate.call_count == 1
        assert mock_note.call_count == 1
        assert client.get_post.call_count == 1

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.enforce_and_record", return_value=_PASS)
    def test_reused_judgment_keeps_the_outcome(self, mock_gate, mock_note, tmp_path):
        agent, client, _ = _agent(tmp_path)

        _run_cycles(agent)

        # One upvote for the passed post, and no comment (the generation was empty).
        client.upvote_post.assert_called_once_with("post1")
        client.post_comment.assert_not_called()

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.enforce_and_record", return_value=_CLOSED)
    def test_a_closed_judgment_is_reused_too(self, mock_gate, mock_note, tmp_path):
        agent, client, _ = _agent(tmp_path)

        _run_cycles(agent)

        assert mock_gate.call_count == 1
        assert agent._feed_manager.rejudges_skipped == _CYCLES - 1

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.enforce_and_record", return_value=_PASS)
    def test_skipped_rejudgements_are_counted(self, mock_gate, mock_note, tmp_path):
        agent, client, _ = _agent(tmp_path)

        _run_cycles(agent)

        assert agent._feed_manager.rejudges_skipped == _CYCLES - 1

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.enforce_and_record", return_value=_PASS)
    def test_skip_is_logged_with_a_reason_code(self, mock_gate, mock_note, tmp_path, caplog):
        agent, client, _ = _agent(tmp_path)

        with caplog.at_level("INFO"):
            _run_cycles(agent)

        assert sum("already_judged" in r.message for r in caplog.records) == _CYCLES - 1

    def test_session_end_episode_carries_the_skip_count(self, tmp_path):
        memory = _make_clean_memory(tmp_path)
        agent, client, _ = _agent(tmp_path, memory=memory)
        with (
            patch(f"{FM}.enforce_and_record", return_value=_PASS),
            patch(f"{FM}.generate_internal_note", return_value="noticed"),
        ):
            _run_cycles(agent)
        agent._log_session_end(duration_minutes=1)

        end = memory.episodes.read_range(days=1, record_type="session")[-1]
        assert end["data"]["feed_rejudges_skipped"] == _CYCLES - 1


class TestFailuresAreNotMemoized:
    """Only a real judgment is frozen — a failed one is retried next cycle.

    Every part of the judgment has a failure mode that returns a legal-looking
    value: the gate fails closed when the decision does not answer,
    ``_fetch_full_if_truncated`` falls back to the truncated preview,
    ``generate_internal_note`` returns "". Memoizing any of them would make a
    transient failure permanent for the session; the next cycle is what
    recovers from it.
    """

    @patch(f"{FM}.enforce_and_record", return_value=_BACKEND_NULL)
    def test_a_fail_closed_gate_is_asked_again(self, mock_gate, tmp_path):
        agent, client, _ = _agent(tmp_path)

        _run_cycles(agent)

        assert mock_gate.call_count == _CYCLES
        assert agent._feed_manager.rejudges_skipped == 0

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.enforce_and_record", return_value=_PASS)
    def test_a_preview_fallback_body_is_refetched(self, mock_gate, mock_note, tmp_path):
        agent, client, _ = _agent(tmp_path)
        # get_post yields nothing longer: the preview is kept as a fallback.
        client.get_post.return_value = {"id": "post1", "content": "y" * FEED_CONTENT_PREVIEW_LEN}

        _run_cycles(agent)

        assert client.get_post.call_count == _CYCLES
        assert agent._feed_manager.rejudges_skipped == 0

    @patch(f"{FM}.generate_internal_note", return_value="")
    @patch(f"{FM}.enforce_and_record", return_value=_PASS)
    def test_a_failed_note_is_regenerated(self, mock_gate, mock_note, tmp_path):
        agent, client, _ = _agent(tmp_path)

        _run_cycles(agent)

        assert mock_note.call_count == _CYCLES
        assert agent._feed_manager.rejudges_skipped == 0
