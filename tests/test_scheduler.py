"""Tests for the rate-limit scheduler."""

import time

from contemplative_agent.core.scheduler import Scheduler


class TestScheduler:
    """Tests for Scheduler with no disk persistence (state_path=None)."""

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

    def test_state_persistence_with_path(self, tmp_path):
        """Test that state persists to disk when state_path is given."""
        state_path = tmp_path / "rate_state.json"
        sched = Scheduler(state_path=state_path)
        sched.record_post()
        assert state_path.exists()

        # New scheduler reads persisted state
        sched2 = Scheduler(state_path=state_path)
        assert not sched2.can_post()
