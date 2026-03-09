"""Rate-limit-aware scheduling for API actions."""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional, Protocol

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
            self._last_post_time = data.get("last_post_time", 0.0)
            self._last_comment_time = data.get("last_comment_time", 0.0)
            self._comments_today = data.get("comments_today", 0)
            self._day_start = data.get("day_start", 0.0)
        except (json.JSONDecodeError, KeyError) as exc:
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
        tmp_path = self._state_path.with_suffix(".json.tmp")
        old_umask = os.umask(0o177)
        try:
            tmp_path.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
        finally:
            os.umask(old_umask)
        os.replace(str(tmp_path), str(self._state_path))

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
        self._reset_daily_if_needed()
        now = time.time()
        elapsed = now - self._last_comment_time
        interval_ok = elapsed >= self._limits.comment_interval_seconds
        daily_ok = self._comments_today < self._limits.comments_per_day
        return interval_ok and daily_ok

    def seconds_until_post(self) -> float:
        now = time.time()
        elapsed = now - self._last_post_time
        remaining = self._limits.post_interval_seconds - elapsed
        return max(0.0, remaining)

    def seconds_until_comment(self) -> float:
        now = time.time()
        elapsed = now - self._last_comment_time
        remaining = self._limits.comment_interval_seconds - elapsed
        return max(0.0, remaining)

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
    """Fallback rate limits when no adapter config is provided."""

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
