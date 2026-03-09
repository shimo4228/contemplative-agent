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
        self._rate_limit_remaining: Optional[int] = None
        self._rate_limit_reset: Optional[float] = None

    def _validate_url(self, url: str) -> None:
        """Ensure the URL points to the allowed domain only."""
        parsed = urlparse(url)
        if parsed.hostname != ALLOWED_DOMAIN:
            raise MoltbookClientError(
                f"Domain validation failed: {parsed.hostname} "
                f"is not {ALLOWED_DOMAIN}"
            )

    def _parse_rate_headers(self, response: requests.Response) -> None:
        """Extract rate limit info from response headers."""
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                self._rate_limit_remaining = max(0, int(remaining))
            except (ValueError, TypeError):
                logger.debug("Malformed X-RateLimit-Remaining header: %r", remaining)

        reset = response.headers.get("X-RateLimit-Reset")
        if reset is not None:
            try:
                self._rate_limit_reset = max(0.0, float(reset))
            except (ValueError, TypeError):
                logger.debug("Malformed X-RateLimit-Reset header: %r", reset)

    @property
    def rate_limit_remaining(self) -> Optional[int]:
        return self._rate_limit_remaining

    @property
    def rate_limit_reset(self) -> Optional[float]:
        return self._rate_limit_reset

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

        self._parse_rate_headers(response)

        if response.status_code == 429:
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
