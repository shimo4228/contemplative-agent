"""HTTP client wrapper for Moltbook API with auth and rate limit handling."""

from __future__ import annotations

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
        # Reset epoch is tracked per bucket (GET vs write). Previously a single
        # shared field was overwritten by whichever method responded last, so a
        # proactive wait could be sized against the wrong (non-depleted) bucket
        # and under-wait into a 429. (ultracode sweep 2026-06-23)
        self._read_reset: Optional[float] = None
        self._write_reset: Optional[float] = None
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
                value = max(0.0, float(reset))
            except (ValueError, TypeError):
                logger.debug("Malformed X-RateLimit-Reset header: %r", reset)
            else:
                if method.upper() == "GET":
                    self._read_reset = value
                else:
                    self._write_reset = value

    @property
    def rate_limit_remaining(self) -> Optional[int]:
        """Min of known read/write remaining.

        Deliberately conservative: the proactive-wait caller (Layer 3) treats
        either bucket running low as a reason to wait. This can over-throttle a
        read-only cycle when only the write bucket is low, but over-waiting is
        the safe direction (it never causes a 429); decoupling would require the
        caller to know the upcoming request mix.
        """
        values = [v for v in (self._read_remaining, self._write_remaining) if v is not None]
        if not values:
            return None
        return min(values)

    @property
    def rate_limit_reset(self) -> Optional[float]:
        """Latest known reset epoch across buckets.

        Returns the LATER of the per-bucket resets so a proactive wait never
        under-waits (the prior single shared field could hold the wrong bucket's
        earlier reset and resume into a 429). Over-waiting is the safe direction.
        """
        resets = [r for r in (self._read_reset, self._write_reset) if r is not None]
        if not resets:
            return None
        return max(resets)

    @property
    def recent_429_count(self) -> int:
        """Number of 429 responses since last reset."""
        return self._recent_429_count

    def reset_429_count(self) -> None:
        """Reset the 429 counter (called after each cycle)."""
        self._recent_429_count = 0

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

    def get_post(self, post_id: str) -> Optional[dict[str, Any]]:
        """GET /posts/{post_id} — fetch a single post (full body).

        Submolt feeds return `content` truncated to a preview; this fetches
        the complete post. Returns None on invalid id or failure.
        """
        if not VALID_ID_PATTERN.match(post_id):
            logger.warning("Invalid post_id format: %s", post_id[:50])
            return None
        try:
            resp = self.get(f"/posts/{post_id}")
            data = resp.json()
            # Moltbook wraps the resource in {"success": .., "post": {..}};
            # tolerate a top-level object too (see post_pipeline envelope handling).
            return data["post"] if "post" in data else data
        except (MoltbookClientError, ValueError) as exc:
            logger.warning("Failed to fetch post %s: %s", post_id[:12], exc)
            return None

    def post_comment(self, post_id: str, content: str) -> dict[str, Any]:
        """POST /posts/{post_id}/comments — create a comment, verify the body.

        HTTP 2xx alone is not success: Moltbook wraps created resources in a
        ``{"success", "comment": {...}}`` envelope (same shape as the post
        path, see post_pipeline envelope handling). An explicit
        ``success: false`` raises ``MoltbookClientError`` so callers treat
        it like an HTTP failure — no dedup/episode record, the post stays
        retryable (audit H2: a 200 + body-level failure previously polluted
        the permanent dedup cache and episode log, never to be retried).

        Ambiguous bodies (non-JSON, missing ``success`` key, missing id)
        are treated as success with a WARNING: the comment may well have
        been created, and a false negative would retry and post a duplicate
        externally — worse than a stale dedup entry.

        Returns the created comment dict ({} when the envelope is
        ambiguous; a bare top-level ``id`` is folded into the dict). The
        dict is raw untrusted external data — callers must pass any string
        field through ``wrap_untrusted_content`` before LLM-bound use.
        """
        if not VALID_ID_PATTERN.match(post_id):
            raise MoltbookClientError(
                f"Invalid post_id for comment: {post_id[:50]}"
            )
        resp = self.post(f"/posts/{post_id}/comments", json={"content": content})
        try:
            data = resp.json()
        except ValueError:
            logger.warning(
                "Comment response for %s is not JSON (HTTP %d); assuming "
                "success to avoid a duplicate-posting retry",
                post_id[:12],
                resp.status_code,
            )
            return {}
        if not isinstance(data, dict):
            logger.warning(
                "Comment response for %s is not an object (%s); assuming "
                "success to avoid a duplicate-posting retry",
                post_id[:12],
                type(data).__name__,
            )
            return {}
        if "success" in data and not data["success"]:
            # Unlike the multi-line HTTP body at the status>=400 path, the
            # error field is single-line — strip \n too so a hostile server
            # cannot forge log lines in agent-launchd.log (log injection).
            safe_error = re.sub(
                r"[^\x20-\x7E]", "", str(data.get("error", ""))[:200]
            )
            raise MoltbookClientError(
                f"Comment on {post_id[:12]} failed at body level "
                f"(HTTP {resp.status_code}): {safe_error}",
                status_code=resp.status_code,
            )
        comment = data.get("comment")
        if not isinstance(comment, dict):
            comment = {}
        if not comment.get("id") and data.get("id"):
            # Bare top-level id (same defensive fallback as the post path,
            # post_pipeline envelope handling) — fold it in so the contract
            # "returns the created comment dict" holds for this shape too.
            comment = {**comment, "id": data["id"]}
        if not comment.get("id"):
            logger.warning(
                "Comment response for %s missing id (envelope keys=%s)",
                post_id[:12],
                sorted(data.keys()),
            )
        return comment

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
        """DELETE /agents/{name}/follow — unfollow an agent, verify the body.

        HTTP 2xx alone is not success (audit L3, same defect class as the
        comment path fixed in audit H2): an explicit ``success: false`` or
        an unexpected ``action`` returns False so the caller does not treat
        an unfollow that never happened as done — the code-level home of
        the known follow-list drift. Ambiguous bodies (non-JSON, no
        ``action``/``success`` keys) are treated as success with a WARNING,
        mirroring ``post_comment``; ``not_following`` counts as idempotent
        success, mirroring follow_agent's ``already_following``.

        A 404 ("Agent not found") is likewise idempotent success: the target
        was deleted server-side, so we are effectively no longer following it
        and the caller should prune its local follow entry. Without this a
        deleted agent's stale local entry made every scheduled run re-issue the
        same doomed DELETE → 404 forever (ultracode sweep 2026-06-23: 31× for a
        single deleted agent).
        """
        if not VALID_AGENT_NAME_PATTERN.match(agent_name):
            logger.warning("Invalid agent_name rejected: %.50r", agent_name)
            return False
        try:
            resp = self.delete(f"/agents/{agent_name}/follow")
        except MoltbookClientError as exc:
            if exc.status_code == 404:
                logger.info(
                    "Unfollow %s: agent not found (404) — already gone, "
                    "treating as unfollowed so the local entry is pruned",
                    agent_name,
                )
                return True
            logger.warning("Failed to unfollow %s: %s", agent_name, exc)
            return False
        try:
            data = resp.json()
        except ValueError:
            data = None
        if not isinstance(data, dict):
            logger.warning(
                "Unfollow response for %s has no JSON object body "
                "(HTTP %d); assuming success",
                agent_name,
                resp.status_code,
            )
            return True
        if "success" in data and not data["success"]:
            # Single-line strip, same log-injection guard as post_comment.
            safe_error = re.sub(
                r"[^\x20-\x7E]", "", str(data.get("error", ""))[:200]
            )
            logger.warning(
                "Unfollow %s failed at body level (HTTP %d): %s",
                agent_name,
                resp.status_code,
                safe_error,
            )
            return False
        action = data.get("action", "")
        if action in ("unfollowed", "not_following"):
            logger.info("Unfollowed %s", agent_name)
            return True
        if action:
            safe_action = re.sub(r"[^\x20-\x7E]", "", str(action)[:50])
            logger.warning(
                "Unfollow %s: unexpected action=%r", agent_name, safe_action
            )
            return False
        logger.warning(
            "Unfollow response for %s missing action (envelope keys=%s); "
            "assuming success",
            agent_name,
            sorted(data.keys()),
        )
        return True

    # update_profile / mark_all_notifications_read / unsubscribe_submolt /
    # has_budget and the PATCH verb were removed as dead code: no production
    # caller, and an unimplemented capability is a smaller attack surface
    # than a guarded one (security by absence, ADR-0007).
