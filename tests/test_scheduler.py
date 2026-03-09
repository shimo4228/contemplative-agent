"""Tests for the rate-limit scheduler."""

import time

import pytest

from contemplative_moltbook.core.scheduler import Scheduler


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """Prevent tests from reading/writing the real rate state file."""
    monkeypatch.setattr(
        "contemplative_moltbook.core.scheduler.RATE_STATE_PATH",
        tmp_path / "rate_state.json",
    )


class TestScheduler:
    def test_initial_can_post(self):
        sched = Scheduler()
        assert sched.can_post()

    def test_initial_can_comment(self):
        sched = Scheduler()
        assert sched.can_comment()

    def test_cannot_post_after_recent_post(self):
        sched = Scheduler()
        sched._last_post_time = time.time()
        assert not sched.can_post()

    def test_cannot_comment_after_recent_comment(self):
        sched = Scheduler()
        sched._last_comment_time = time.time()
        assert not sched.can_comment()

    def test_record_post_updates_time(self):
        sched = Scheduler()
        sched.record_post()
        assert not sched.can_post()

    def test_record_comment_updates_count(self):
        sched = Scheduler()
        initial = sched.comments_remaining_today
        sched.record_comment()
        assert sched.comments_remaining_today == initial - 1

    def test_daily_limit_exceeded(self):
        sched = Scheduler()
        sched._comments_today = 200
        sched._day_start = time.time()
        sched._last_comment_time = 0.0
        assert not sched.can_comment()

    def test_daily_reset_after_24h(self):
        sched = Scheduler()
        sched._comments_today = 200
        sched._day_start = time.time() - 90000  # > 24h ago
        sched._last_comment_time = 0.0
        assert sched.can_comment()

    def test_seconds_until_post(self):
        sched = Scheduler()
        sched._last_post_time = time.time()
        remaining = sched.seconds_until_post()
        assert remaining > 0

    def test_seconds_until_post_when_available(self):
        sched = Scheduler()
        sched._last_post_time = 0.0
        assert sched.seconds_until_post() == 0.0

    def test_new_agent_stricter_limits(self):
        sched = Scheduler(is_new_agent=True)
        sched._last_post_time = time.time() - 3600  # 1h ago
        # New agent needs 2h between posts
        assert not sched.can_post()

    def test_comments_remaining_today(self):
        sched = Scheduler()
        sched._day_start = time.time()
        sched._comments_today = 10
        assert sched.comments_remaining_today == 190
