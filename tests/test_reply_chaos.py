"""Chaos fault-injection tests for the reply loops (ADR-0077).

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

Determinism: explicit single-fault schedules (``NONE`` — a backend hard
failure, already a member of ``CIRCUIT_FAILING_FAULTS``), no test sleeps, and
no wall-clock dependence beyond an ``end_time`` an hour out.
"""

from __future__ import annotations

import time

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
