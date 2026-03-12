"""HTTP client wrapper for Moltbook API with auth and rate limit handling."""

import logging
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests

from .config import (
    ALLOWED_DOMAIN,
    BASE_URL,
    CONNECT_TIMEOUT,
    MAX_RETRY_ON_429,
    READ_TIMEOUT,
)
from ...core.config import (
    VALID_ID_PATTERN,
    VALID_SUBMOLT_PATTERN,
)

VALID_AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

logger = logging.getLogger(__name__)

MAX_RETRY_AFTER = 300  # 5 minutes hard cap


class MoltbookClientError(Exception):
    """Raised for Moltbook API errors."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class MoltbookClient:
    """HTTP client for Moltbook API.

    Features:
    - Automatic auth header injection (optional for registration)
    - Domain validation (www.moltbook.com only)
    - Redirect following disabled (prevents token theft via redirect)
    - X-RateLimit-* header parsing
    - 429 retry with backoff (max 3 attempts, capped at 5min)
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "ContemplativeAgent/0.1",
        })
        if api_key:
            self._session.headers["Authorization"] = f"Bearer {api_key}"
        self._base_url = BASE_URL
        self._read_remaining: Optional[int] = None
        self._write_remaining: Optional[int] = None
        self._rate_limit_reset: Optional[float] = None
        self._recent_429_count: int = 0

    def _validate_url(self, url: str) -> None:
        """Ensure the URL points to the allowed domain only."""
        parsed = urlparse(url)
        if parsed.hostname != ALLOWED_DOMAIN:
            raise MoltbookClientError(
                f"Domain validation failed: {parsed.hostname} "
                f"is not {ALLOWED_DOMAIN}"
            )

    def _parse_rate_headers(
        self, response: requests.Response, method: str = "GET"
    ) -> None:
        """Extract rate limit info from response headers.

        Assigns remaining quota to read or write bucket based on request method.
        GET → read, POST/PUT/PATCH/DELETE → write.
        """
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                value = max(0, int(remaining))
            except (ValueError, TypeError):
                logger.debug("Malformed X-RateLimit-Remaining header: %r", remaining)
            else:
                if method.upper() == "GET":
                    self._read_remaining = value
                else:
                    self._write_remaining = value

        reset = response.headers.get("X-RateLimit-Reset")
        if reset is not None:
            try:
                self._rate_limit_reset = max(0.0, float(reset))
            except (ValueError, TypeError):
                logger.debug("Malformed X-RateLimit-Reset header: %r", reset)

    @property
    def read_remaining(self) -> Optional[int]:
        return self._read_remaining

    @property
    def write_remaining(self) -> Optional[int]:
        return self._write_remaining

    @property
    def rate_limit_remaining(self) -> Optional[int]:
        """Backward-compatible: returns min of known read/write remaining."""
        values = [v for v in (self._read_remaining, self._write_remaining) if v is not None]
        if not values:
            return None
        return min(values)

    @property
    def rate_limit_reset(self) -> Optional[float]:
        return self._rate_limit_reset

    @property
    def recent_429_count(self) -> int:
        """Number of 429 responses since last reset."""
        return self._recent_429_count

    def reset_429_count(self) -> None:
        """Reset the 429 counter (called after each cycle)."""
        self._recent_429_count = 0

    def has_budget(self, reserve: int = 5) -> bool:
        """Backward-compatible: True if both read and write have budget."""
        return self.has_read_budget(reserve) and self.has_write_budget(reserve)

    def has_read_budget(self, reserve: int = 5) -> bool:
        """Check if enough read (GET) rate limit budget remains."""
        if self._read_remaining is None:
            return True
        return self._read_remaining > reserve

    def has_write_budget(self, reserve: int = 3) -> bool:
        """Check if enough write (POST/PUT/PATCH/DELETE) rate limit budget remains."""
        if self._write_remaining is None:
            return True
        return self._write_remaining > reserve

    def _request(
        self,
        method: str,
        path: str,
        retries: int = 0,
        **kwargs: Any,
    ) -> requests.Response:
        """Make an HTTP request with retry on 429."""
        url = f"{self._base_url}{path}"
        self._validate_url(url)

        kwargs.setdefault("timeout", (CONNECT_TIMEOUT, READ_TIMEOUT))
        # Disable redirects to prevent Bearer token leakage via redirect
        kwargs.setdefault("allow_redirects", False)

        try:
            response = self._session.request(method, url, **kwargs)
        except requests.RequestException as exc:
            raise MoltbookClientError(f"Request failed: {exc}") from exc

        self._parse_rate_headers(response, method=method)

        if response.status_code == 429:
            self._recent_429_count += 1
            # Don't retry hourly/daily limits — they won't clear soon
            body_text = response.text[:500]
            if "limit reached" in body_text.lower():
                logger.warning("Hard rate limit reached (429). Not retrying.")
            elif retries < MAX_RETRY_ON_429:
                try:
                    retry_after = min(
                        float(response.headers.get("Retry-After", 60)),
                        MAX_RETRY_AFTER,
                    )
                except (ValueError, TypeError):
                    retry_after = 60.0
                logger.warning(
                    "Rate limited (429). Retrying in %.0fs (attempt %d/%d)",
                    retry_after,
                    retries + 1,
                    MAX_RETRY_ON_429,
                )
                time.sleep(retry_after)
                return self._request(method, path, retries=retries + 1, **kwargs)

        if response.status_code >= 400:
            safe_body = re.sub(r'[^\x20-\x7E\n]', '', response.text[:500])
            raise MoltbookClientError(
                f"API error {response.status_code}: {safe_body}",
                status_code=response.status_code,
            )

        return response

    def get(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("POST", path, **kwargs)

    def patch(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs: Any) -> requests.Response:
        return self._request("DELETE", path, **kwargs)

    def subscribe_submolt(self, name: str) -> bool:
        """Subscribe to a submolt. Returns True on success or already subscribed."""
        if not VALID_SUBMOLT_PATTERN.match(name):
            logger.warning("Invalid submolt name: %s", name[:50])
            return False
        try:
            self.post(f"/submolts/{name}/subscribe")
            logger.info("Subscribed to submolt: %s", name)
            return True
        except MoltbookClientError as exc:
            if exc.status_code == 409:
                logger.debug("Already subscribed to %s", name)
                return True
            if exc.status_code == 400:
                logger.warning("Subscribe %s returned 400 (may be already subscribed)", name)
                return True
            logger.warning("Failed to subscribe to %s: %s", name, exc)
            return False

    def unsubscribe_submolt(self, name: str) -> bool:
        """Unsubscribe from a submolt. Returns True on success."""
        if not VALID_SUBMOLT_PATTERN.match(name):
            logger.warning("Invalid submolt name: %s", name[:50])
            return False
        try:
            self.delete(f"/submolts/{name}/subscribe")
            logger.info("Unsubscribed from submolt: %s", name)
            return True
        except MoltbookClientError as exc:
            logger.warning("Failed to unsubscribe from %s: %s", name, exc)
            return False

    def get_notifications(
        self, since: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Fetch notifications. Returns empty list on failure."""
        params: dict[str, str] = {}
        if since:
            params["since"] = since
        try:
            resp = self.get("/notifications", params=params)
            data = resp.json()
            return data.get("notifications", [])
        except (MoltbookClientError, ValueError) as exc:
            logger.warning("Failed to fetch notifications: %s", exc)
            return []

    def follow_agent(self, agent_name: str) -> bool:
        """Follow an agent by name. Returns True on success."""
        if not VALID_AGENT_NAME_PATTERN.match(agent_name):
            logger.warning("Invalid agent_name rejected: %.50r", agent_name)
            return False
        try:
            resp = self.post(f"/agents/{agent_name}/follow")
            data = resp.json()
            action = data.get("action", "")
            if action == "followed":
                logger.info("Now following %s", agent_name)
                return True
            logger.debug("Follow %s: action=%s", agent_name, action)
            return action == "already_following"
        except MoltbookClientError as exc:
            logger.warning("Failed to follow %s: %s", agent_name, exc)
            return False

    def get_post_comments(
        self, post_id: str
    ) -> list[dict[str, Any]]:
        """Fetch comments for a post. Returns empty list on failure."""
        if not VALID_ID_PATTERN.match(post_id):
            logger.warning("Invalid post_id format: %s", post_id[:50])
            return []
        try:
            resp = self.get(f"/posts/{post_id}/comments")
            data = resp.json()
            return data.get("comments", [])
        except (MoltbookClientError, ValueError) as exc:
            logger.warning("Failed to fetch comments for %s: %s", post_id, exc)
            return []

    # ------------------------------------------------------------------
    # Home dashboard
    # ------------------------------------------------------------------

    def get_home(self) -> dict[str, Any]:
        """GET /home — fetch dashboard data in a single call.

        Returns the full home response dict, or empty dict on failure.
        """
        try:
            resp = self.get("/home")
            return resp.json()
        except (MoltbookClientError, ValueError) as exc:
            logger.warning("Failed to fetch /home: %s", exc)
            return {}

    # ------------------------------------------------------------------
    # Notification management
    # ------------------------------------------------------------------

    def mark_notifications_read_by_post(self, post_id: str) -> bool:
        """POST /notifications/read-by-post/{post_id} — mark as read."""
        if not VALID_ID_PATTERN.match(post_id):
            logger.warning("Invalid post_id for mark-read: %s", post_id[:50])
            return False
        try:
            self.post(f"/notifications/read-by-post/{post_id}")
            return True
        except MoltbookClientError as exc:
            logger.warning("Failed to mark notifications read for %s: %s", post_id, exc)
            return False

    def mark_all_notifications_read(self) -> bool:
        """POST /notifications/read-all — mark all notifications as read."""
        try:
            self.post("/notifications/read-all")
            return True
        except MoltbookClientError as exc:
            logger.warning("Failed to mark all notifications read: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------

    def upvote_post(self, post_id: str) -> bool:
        """POST /posts/{post_id}/upvote — upvote a post.

        Returns True on success. 409 (already upvoted) is treated as success.
        """
        if not VALID_ID_PATTERN.match(post_id):
            logger.warning("Invalid post_id for upvote: %s", post_id[:50])
            return False
        try:
            self.post(f"/posts/{post_id}/upvote")
            return True
        except MoltbookClientError as exc:
            if exc.status_code == 409:
                logger.debug("Already upvoted post %s", post_id)
                return True
            logger.warning("Failed to upvote post %s: %s", post_id, exc)
            return False

    def upvote_comment(self, comment_id: str) -> bool:
        """POST /comments/{comment_id}/upvote — upvote a comment.

        Returns True on success. 409 (already upvoted) is treated as success.
        """
        if not VALID_ID_PATTERN.match(comment_id):
            logger.warning("Invalid comment_id for upvote: %s", comment_id[:50])
            return False
        try:
            self.post(f"/comments/{comment_id}/upvote")
            return True
        except MoltbookClientError as exc:
            if exc.status_code == 409:
                logger.debug("Already upvoted comment %s", comment_id)
                return True
            logger.warning("Failed to upvote comment %s: %s", comment_id, exc)
            return False

    # ------------------------------------------------------------------
    # Search & feed
    # ------------------------------------------------------------------

    def search(
        self, query: str, search_type: str = "posts", limit: int = 20
    ) -> list[dict[str, Any]]:
        """GET /search — semantic search for posts/comments.

        Args:
            query: Search query (capped at 200 chars).
            search_type: "posts", "comments", or "all".
            limit: Max results (capped at 50).

        Returns list of result dicts, or empty list on failure.
        """
        try:
            resp = self.get(
                "/search",
                params={
                    "q": query[:200],
                    "type": search_type,
                    "limit": min(limit, 50),
                },
            )
            data = resp.json()
            return data.get("results", [])
        except (MoltbookClientError, ValueError) as exc:
            logger.warning("Search failed for %r: %s", query[:50], exc)
            return []

    def get_following_feed(self, limit: int = 25) -> list[dict[str, Any]]:
        """GET /feed?filter=following — posts from accounts you follow."""
        try:
            resp = self.get(
                "/feed",
                params={"filter": "following", "sort": "new", "limit": limit},
            )
            data = resp.json()
            return data.get("posts", [])
        except (MoltbookClientError, ValueError) as exc:
            logger.warning("Failed to fetch following feed: %s", exc)
            return []

    def unfollow_agent(self, agent_name: str) -> bool:
        """DELETE /agents/{name}/follow — unfollow an agent."""
        if not VALID_AGENT_NAME_PATTERN.match(agent_name):
            logger.warning("Invalid agent_name rejected: %.50r", agent_name)
            return False
        try:
            self.delete(f"/agents/{agent_name}/follow")
            logger.info("Unfollowed %s", agent_name)
            return True
        except MoltbookClientError as exc:
            logger.warning("Failed to unfollow %s: %s", agent_name, exc)
            return False

    _ALLOWED_PROFILE_FIELDS = frozenset({"description", "metadata"})

    def update_profile(self, **fields: Any) -> bool:
        """PATCH /agents/me — update agent profile fields.

        Only 'description' and 'metadata' are accepted per the API spec.
        Raises ValueError for unknown fields.
        """
        unknown = set(fields) - self._ALLOWED_PROFILE_FIELDS
        if unknown:
            logger.warning("Rejected unknown profile fields: %s", unknown)
            return False
        try:
            self.patch("/agents/me", json=fields)
            logger.info("Profile updated: %s", list(fields.keys()))
            return True
        except MoltbookClientError as exc:
            logger.warning("Failed to update profile: %s", exc)
            return False
