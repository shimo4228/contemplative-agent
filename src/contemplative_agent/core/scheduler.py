"""Rate-limit-aware scheduling for API actions."""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Protocol

from ._io import write_text_atomic

logger = logging.getLogger(__name__)


class RateLimitsProtocol(Protocol):
    """Expected interface for rate limit configuration objects."""

    @property
    def post_interval_seconds(self) -> int: ...
    @property
    def comment_interval_seconds(self) -> int: ...
    @property
    def comments_per_day(self) -> int: ...


class Scheduler:
    """Tracks action timestamps and enforces rate limits.

    Persists state to disk so limits survive restarts.

    Args:
        state_path: Path to persist rate state. If None, state is in-memory only.
        limits: A rate-limit object with post_interval_seconds,
                comment_interval_seconds, and comments_per_day attributes.
        is_new_agent: If True and no explicit limits given, uses stricter defaults.
    """

    def __init__(
        self,
        state_path: Optional[Path] = None,
        limits: Optional[RateLimitsProtocol] = None,
        is_new_agent: bool = False,
    ) -> None:
        self._state_path = state_path
        self._limits: RateLimitsProtocol = limits or _InMemoryLimits(is_new_agent=is_new_agent)
        self._last_post_time: float = 0.0
        self._last_comment_time: float = 0.0
        self._comments_today: int = 0
        self._day_start: float = 0.0
        self._load_state()

    def _load_state(self) -> None:
        if self._state_path is None or not self._state_path.exists():
            return
        try:
            data = json.loads(self._state_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError(f"expected JSON object, got {type(data).__name__}")
            self._last_post_time = data.get("last_post_time", 0.0)
            self._last_comment_time = data.get("last_comment_time", 0.0)
            self._comments_today = data.get("comments_today", 0)
            self._day_start = data.get("day_start", 0.0)
        except (json.JSONDecodeError, ValueError) as exc:
            # Corrupt/non-object state file: fall back to the in-memory defaults
            # already set in __init__ rather than crashing the scheduler.
            logger.warning("Failed to load rate state: %s", exc)

    def _save_state(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_post_time": self._last_post_time,
            "last_comment_time": self._last_comment_time,
            "comments_today": self._comments_today,
            "day_start": self._day_start,
        }
        write_text_atomic(self._state_path, json.dumps(data, indent=2) + "\n")

    def _reset_daily_if_needed(self) -> None:
        now = time.time()
        if now - self._day_start > 86400:
            self._comments_today = 0
            self._day_start = now
            self._save_state()

    def can_post(self) -> bool:
        # Re-read from disk to detect posts by other sessions
        self._load_state()
        now = time.time()
        elapsed = now - self._last_post_time
        return elapsed >= self._limits.post_interval_seconds

    def can_comment(self) -> bool:
        # Re-read from disk to detect comments by other sessions (audit M5;
        # symmetric with can_post). Load before the daily-reset check so the
        # reset decision sees the latest persisted day_start/comments_today.
        self._load_state()
        self._reset_daily_if_needed()
        now = time.time()
        elapsed = now - self._last_comment_time
        interval_ok = elapsed >= self._limits.comment_interval_seconds
        daily_ok = self._comments_today < self._limits.comments_per_day
        return interval_ok and daily_ok

    def seconds_until_post(self) -> float:
        # Mirror can_post's cross-session re-read so the wait reflects the same
        # persisted last_post_time the gate checks. Posts have no daily cap, so
        # (unlike seconds_until_comment) no _reset_daily_if_needed is needed.
        self._load_state()
        now = time.time()
        elapsed = now - self._last_post_time
        remaining = self._limits.post_interval_seconds - elapsed
        return max(0.0, remaining)

    def seconds_until_comment(self) -> float:
        # Mirror can_comment's cross-session re-read + daily reset so the wait
        # reflects the same state the gate checks.
        self._load_state()
        self._reset_daily_if_needed()
        now = time.time()
        interval_remaining = max(
            0.0, self._limits.comment_interval_seconds - (now - self._last_comment_time)
        )
        # Daily cap: when exhausted, the next comment cannot happen until the
        # rolling 24h window resets. Without this the caller saw the small
        # interval value, woke every ~comment_interval, and burned GET budget
        # until the cap refreshed (ultracode sweep 2026-06-23).
        if self._comments_today >= self._limits.comments_per_day:
            until_daily_reset = max(0.0, self._day_start + 86400 - now)
            return max(interval_remaining, until_daily_reset)
        return interval_remaining

    def record_post(self) -> None:
        self._last_post_time = time.time()
        self._save_state()
        logger.info("Post recorded. Next post in %ds", self._limits.post_interval_seconds)

    def record_comment(self) -> None:
        self._last_comment_time = time.time()
        self._comments_today += 1
        self._save_state()
        logger.info(
            "Comment recorded (%d/%d today). Next in %ds",
            self._comments_today,
            self._limits.comments_per_day,
            self._limits.comment_interval_seconds,
        )

    @property
    def comments_remaining_today(self) -> int:
        # Same cross-session re-read as can_comment/can_post (audit M5).
        self._load_state()
        self._reset_daily_if_needed()
        return max(0, self._limits.comments_per_day - self._comments_today)

    def wait_for_post(self) -> None:
        wait = self.seconds_until_post()
        if wait > 0:
            logger.info("Waiting %.0fs for post rate limit...", wait)
            time.sleep(wait)

    def wait_for_comment(self) -> None:
        wait = self.seconds_until_comment()
        if wait > 0:
            logger.info("Waiting %.0fs for comment rate limit...", wait)
            time.sleep(wait)


class _InMemoryLimits:
    """Fallback rate limits when no adapter config is provided.

    These are an INDEPENDENT conservative default, deliberately not the same
    numbers as the Moltbook adapter's ``RateLimits`` (which sets
    comments_per_day=300). ``core/`` cannot import the adapter config (one-way
    import rule, ADR-0001), so the two cannot share a constant; in production
    the adapter always injects its own limits and this fallback is unreachable.
    The lower 200 here is a safe floor for the no-adapter case, not a drifted
    copy of the 300 default.
    """

    post_interval_seconds: int
    comment_interval_seconds: int
    comments_per_day: int

    def __init__(self, is_new_agent: bool = False) -> None:
        if is_new_agent:
            self.post_interval_seconds = 7200
            self.comment_interval_seconds = 60
            self.comments_per_day = 50
        else:
            self.post_interval_seconds = 1800
            self.comment_interval_seconds = 20
            self.comments_per_day = 200
