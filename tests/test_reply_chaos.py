"""Chaos fault-injection tests for the loops the LLM used to pace (ADR-0077).

The file is named for the reply cycle because that is where the incident was
first repaired; the fault class is not reply-specific, so the feed-engagement
loop and the post cycle's seed selection are exercised here too (they share
the fixture, the seam, and the steady-state channel).

The reply cycle's four candidate loops each open with the same stateless
guard column (end_time / rate-limited / can_comment / write budget). None of
them asked whether the LLM was answering at all, and the generation call was
what paced them: one candidate cost a few seconds of generation, so a session
scanned tens of candidates, not thousands.

2026-07-12 09h UTC removed that pacer. The circuit breaker opened, every
generation short-circuited in microseconds, and the loops ran at their real
speed — 6,621 candidates scanned in one hour, 29,007 ``circuit_open`` rows in
``llm-calls``, 58MB of log. Nothing was published (the breaker is exactly what
stopped that), so the whole cost was wasted scanning and log volume. The
missing guard is the fourth line of the column, not a backoff: the breaker
already carries the clock (``CIRCUIT_COOLDOWN_SECONDS`` = 120, half-open after
that), so a ``break`` costs a delay, not a permanent stop, and the next
unattended session picks the candidates back up.

Faults ride the seam ``tests/chaos.py`` already owns — the ``LLMBackend``
Protocol via ``configure(backend=...)``. No production hook is added. Steady
state is asserted on the ``llm-calls-{date}.jsonl`` telemetry channel: an
``outcome == "circuit_open"`` row is emitted for every generation attempted
while the breaker is open, so the row count IS the candidate scan the incident
measured.

Fault catalog rows exercised here:
- F-REP-1 breaker already open when the cycle starts -> each of the four loops
  exits without touching a single candidate (one case per loop, so deleting
  any one guard line turns exactly one case red)
- F-REP-2 breaker opens mid-cycle (the incident's own shape) -> the loop stops
  within the candidate that tripped it instead of scanning the remainder
- F-FEED-1 / F-FEED-2 the same two shapes on the feed-engagement loop, whose
  pacer was ``score_relevance`` rather than the reply generation. Its
  outage sentinel is 0.0, which is below ``upvote_only_threshold``, so an open
  breaker also silences the note, the full-body fetch and the upvote — the
  break forfeits no work (T-FEED-PACING)
- F-SEED-1 breaker already open when the post cycle starts -> it returns
  before ``select_feed_seeds``. Keyed on the feed fetch, not on telemetry:
  entering would also spend a GET and record "no relevance-passing seeds in
  feed", filing an outage as a judgment about the feed (the ADR-0075
  misattribution class)
- F-SEED-2 breaker opens while the selector is scoring -> the walk ends there.
  The entry guard structurally cannot see this, and ``select_feed_seeds``'s
  only other exit is ``target_count`` accepts, which an all-0.0 scorer never
  reaches; measured 25 rows on 30 candidates before the pacing predicate

Determinism: explicit single-fault schedules (``NONE`` — a backend hard
failure, already a member of ``CIRCUIT_FAILING_FAULTS``), no test sleeps, and
no wall-clock dependence beyond an ``end_time`` an hour out.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from contemplative_agent.core.llm import (
    CIRCUIT_FAILURE_THRESHOLD,
    circuit_reading,
    configure,
    generate,
    reset_llm_config,
)
from tests.chaos import NONE, ChaosBackend
from tests.test_agent import _make_agent
from tests.test_llm_telemetry import _read_records

# Enough candidates that "scanned them all" and "stopped early" cannot be
# confused. The incident's own ratio was 6,621 candidates to 29,007 rows.
CANDIDATES = 30


@pytest.fixture
def chaos(tmp_path):
    """A backend that fails every call, with telemetry landing in tmp_path.

    The schedule is sized off the breaker, not off CANDIDATES: once it opens,
    generation short-circuits before the backend is reached, so no case can
    consume more than CIRCUIT_FAILURE_THRESHOLD entries. The x2 is margin —
    ChaosBackend returns OK past the end of its schedule, which would quietly
    stop injecting faults.
    """
    reset_llm_config()
    configure(
        backend=ChaosBackend(schedule=[NONE] * (CIRCUIT_FAILURE_THRESHOLD * 2)),
        telemetry_dir=tmp_path,
    )
    yield
    reset_llm_config()


def _trip_breaker() -> None:
    """Drive the breaker open through the real generation path."""
    for _ in range(CIRCUIT_FAILURE_THRESHOLD):
        generate("chaos", system="s")
    assert circuit_reading().is_open


def _circuit_open_rows(telemetry_dir) -> int:
    return sum(1 for r in _read_records(telemetry_dir) if r["outcome"] == "circuit_open")


def _comment(i: int) -> dict:
    return {
        "id": f"c{i}",
        "content": f"A thought about the {i}th thing you wrote.",
        "agent_id": f"a{i}",
        "agent_name": f"Peer{i}",
    }


def _feed_post(i: int) -> dict:
    """A post that clears every engagement gate, so scoring is what stops it.

    No ``submolt_name`` (the subscribed-submolt gate only fires on a truthy
    one) and no author (an empty name skips the per-author history gates), so
    the only thing standing between this post and an LLM call is the guard
    under test.
    """
    return {"id": f"f{i}", "content": f"A thought about the {i}th thing."}


def _notification(i: int) -> dict:
    return {
        "type": "comment",
        "id": f"n{i}",
        "post_id": f"p{i}",
        "content": f"A thought about the {i}th thing you wrote.",
        "post_content": "Original content",
        "agent_id": f"a{i}",
        "agent_name": f"Peer{i}",
    }


class TestBreakerOpenBeforeCycleF1:
    """F-REP-1: an already-open breaker stops each loop at its first item."""

    @pytest.mark.usefixtures("chaos")
    def test_notification_loop_exits(self, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path)
        client.get_notifications.return_value = [_notification(i) for i in range(CANDIDATES)]
        # Own-post fallback stays empty: check_own_post_comments runs at the end
        # of run_cycle and must not be what makes this case pass.
        agent._ctx.own_post_ids = set()

        _trip_breaker()

        agent._reply_handler.run_cycle(client, scheduler, time.time() + 3600)

        # Zero, not a delta: _trip_breaker's own calls all reach the backend
        # (the 5th failure is what opens the breaker), so it short-circuits
        # nothing and leaves the count at 0.
        assert _circuit_open_rows(tmp_path) == 0

    @pytest.mark.usefixtures("chaos")
    def test_post_comment_loop_exits(self, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path)
        client.get_post_comments.return_value = [_comment(i) for i in range(CANDIDATES)]

        _trip_breaker()

        agent._reply_handler._handle_post_comments(client, scheduler, "p1", time.time() + 3600)

        assert _circuit_open_rows(tmp_path) == 0

    @pytest.mark.usefixtures("chaos")
    def test_home_activity_loop_exits(self, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path)
        client.get_post_comments.return_value = []
        home_data = {
            "activity_on_your_posts": [
                {"post_id": f"p{i}", "new_notification_count": 3} for i in range(CANDIDATES)
            ]
        }

        _trip_breaker()

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, home_data)

        # Keyed on the per-item fetch, not on telemetry: with only the inner
        # comment loop guarded, this outer loop would still spend 30 GETs and
        # 30 mark-read writes on candidates it cannot answer.
        client.get_post_comments.assert_not_called()
        client.mark_notifications_read_by_post.assert_not_called()

    @pytest.mark.usefixtures("chaos")
    def test_own_post_loop_exits(self, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path)
        agent._ctx.own_post_ids = {f"p{i}" for i in range(CANDIDATES)}
        client.get_post_comments.return_value = []

        _trip_breaker()

        agent._reply_handler.check_own_post_comments(client, scheduler, time.time() + 3600)

        client.get_post_comments.assert_not_called()


class TestBreakerOpensMidCycleF2:
    """F-REP-2: the incident's shape — the pacer vanishes partway through."""

    @pytest.mark.usefixtures("chaos")
    def test_comment_loop_stops_within_the_tripping_candidate(self, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path)
        client.get_post_comments.return_value = [_comment(i) for i in range(CANDIDATES)]

        agent._reply_handler._handle_post_comments(client, scheduler, "p1", time.time() + 3600)

        assert circuit_reading().is_open
        # Every candidate costs a fixed number of generation attempts (here 2:
        # the internal note and the reply), so an unguarded loop's row count
        # scales with CANDIDATES — measured 55 before the guard, matching the
        # incident's own scaling (6,621 candidates, 29,007 rows). Guarded, the
        # rows stop at whatever remained inside the candidate that tripped the
        # breaker: the 5th failure lands on candidate 3's note, leaving that
        # candidate's reply attempt as the only short-circuited call (measured
        # 1). Asserted as a bound rather than that 1, so the case keeps stating
        # "does not scale with CANDIDATES" if the per-candidate call count
        # changes.
        assert _circuit_open_rows(tmp_path) <= CIRCUIT_FAILURE_THRESHOLD


def _feed_posts() -> list[dict]:
    return [_feed_post(i) for i in range(CANDIDATES)]


def _seed_candidates(agent) -> list[dict]:
    """The same posts, stamped with a submolt the post cycle subscribes to.

    ``PostPipeline._seed_candidates`` drops anything outside the subscribed
    list, so the feed loop's submolt-less posts would never reach the
    selector.
    """
    subs = agent._domain.subscribed_submolts
    return [{**post, "submolt_name": subs[0] if subs else ""} for post in _feed_posts()]


def _feed_agent(tmp_path):
    """An agent whose read budget and following feed stay out of the way."""
    agent, client, scheduler = _make_agent(tmp_path)
    client.has_read_budget.return_value = True
    client.get_following_feed.return_value = []
    return agent, client, scheduler


class TestFeedLoopBreakerF1F2:
    """F-FEED-1 / F-FEED-2: the feed-engagement loop's pacer was scoring.

    ``score_relevance`` runs on every post the gates admit and is the only
    LLM call the loop makes while the breaker is open — the 0.0 sentinel is
    below ``upvote_only_threshold``, so the note, the full-body fetch and the
    upvote never follow it. One row per candidate, so the row count is the
    scan.
    """

    @pytest.mark.usefixtures("chaos")
    def test_feed_loop_exits_when_breaker_already_open(self, tmp_path):
        agent, client, scheduler = _feed_agent(tmp_path)
        fm = agent._feed_manager

        _trip_breaker()

        with patch.object(fm, "get_feed", return_value=_feed_posts()) as get_feed:
            fm.run_cycle(client, scheduler, time.time() + 3600)

        # Keyed on the fetches too: both feed sources are paid for before the
        # loop is entered, so a loop-head-only guard would still spend a GET
        # per cycle for the whole outage.
        client.get_following_feed.assert_not_called()
        get_feed.assert_not_called()
        # Zero, not a delta: _trip_breaker's own calls all reach the backend,
        # so they short-circuit nothing (same reasoning as F-REP-1).
        assert _circuit_open_rows(tmp_path) == 0

    @pytest.mark.usefixtures("chaos")
    def test_feed_loop_stops_within_the_tripping_candidate(self, tmp_path):
        agent, client, scheduler = _feed_agent(tmp_path)
        fm = agent._feed_manager

        with patch.object(fm, "get_feed", return_value=_feed_posts()):
            fm.run_cycle(client, scheduler, time.time() + 3600)

        assert circuit_reading().is_open
        # Unguarded, every candidate past the tripping one adds a row and the
        # count scales with CANDIDATES. Guarded, the loop breaks at the top of
        # the next iteration. Asserted as a bound rather than 0 so the case
        # keeps stating "does not scale with CANDIDATES" if the per-candidate
        # call count changes.
        assert _circuit_open_rows(tmp_path) <= CIRCUIT_FAILURE_THRESHOLD


class TestPostCycleBreakerF1:
    """F-SEED-1: the post cycle returns before it starts sampling seeds.

    ``select_feed_seeds`` walks its shuffled candidates until ``target_count``
    are accepted; with every score 0.0 nothing is ever accepted, so it walks
    all of them. Everything downstream of it is an LLM call too, so an open
    breaker makes the whole cycle unproductive — the guard belongs at the
    cycle's existing early-return column, which leaves the selector the pure,
    injection-only function its contract promises.
    """

    @pytest.mark.usefixtures("chaos")
    def test_post_cycle_exits_when_breaker_already_open(self, tmp_path):
        agent, client, scheduler = _make_agent(tmp_path)
        fm = agent._feed_manager

        _trip_breaker()

        with patch.object(fm, "get_feed", return_value=_seed_candidates(agent)) as get_feed:
            agent._post_pipeline.run_cycle(client, scheduler)

        # Keyed on the fetch as well as the telemetry: the cycle must not pay
        # a feed GET, and must not log a seed verdict, for a cycle it cannot
        # finish. The stub rides FeedManager.get_feed, the seam the pipeline's
        # injected get_feed closes over (agent.py), rather than the pipeline's
        # own private attribute.
        get_feed.assert_not_called()
        assert _circuit_open_rows(tmp_path) == 0

    @pytest.mark.usefixtures("chaos")
    def test_seed_selection_stops_when_the_breaker_opens_mid_scan(self, tmp_path):
        """F-SEED-2: the entry guard cannot see a breaker that opens later.

        The incident's own shape, and the one the entry guard structurally
        misses: the cycle starts with the breaker closed, the outage begins
        while the selector is scoring candidates, and from then on nothing is
        ever accepted — ``len(accepted) >= target_count`` cannot end the walk,
        so it runs to the end of the candidate list.
        """
        agent, client, scheduler = _make_agent(tmp_path)
        fm = agent._feed_manager

        with patch.object(fm, "get_feed", return_value=_seed_candidates(agent)):
            agent._post_pipeline.run_cycle(client, scheduler)

        assert circuit_reading().is_open
        # Same bound as the reply and feed mid-cycle cases: what remains after
        # the tripping candidate must not scale with the candidate count.
        assert _circuit_open_rows(tmp_path) <= CIRCUIT_FAILURE_THRESHOLD
