"""Rate-limit-aware scheduling for Moltbook API actions."""

import json
import logging
import time

from .config import (
    NEW_AGENT_RATE_LIMITS,
    RATE_LIMITS,
    RATE_STATE_PATH,
)

logger = logging.getLogger(__name__)


class Scheduler:
    """Tracks action timestamps and enforces rate limits.

    Persists state to disk so limits survive restarts.
    """

    def __init__(self, is_new_agent: bool = False) -> None:
        self._limits = NEW_AGENT_RATE_LIMITS if is_new_agent else RATE_LIMITS
        self._last_post_time: float = 0.0
        self._last_comment_time: float = 0.0
        self._comments_today: int = 0
        self._day_start: float = 0.0
        self._load_state()

    def _load_state(self) -> None:
        if not RATE_STATE_PATH.exists():
            return
        try:
            data = json.loads(RATE_STATE_PATH.read_text(encoding="utf-8"))
            self._last_post_time = data.get("last_post_time", 0.0)
            self._last_comment_time = data.get("last_comment_time", 0.0)
            self._comments_today = data.get("comments_today", 0)
            self._day_start = data.get("day_start", 0.0)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Failed to load rate state: %s", exc)

    def _save_state(self) -> None:
        RATE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "last_post_time": self._last_post_time,
            "last_comment_time": self._last_comment_time,
            "comments_today": self._comments_today,
            "day_start": self._day_start,
        }
        RATE_STATE_PATH.write_text(
            json.dumps(data, indent=2) + "\n", encoding="utf-8"
        )
        RATE_STATE_PATH.chmod(0o600)

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
