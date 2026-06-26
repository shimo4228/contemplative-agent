"""Tests for the Moltbook HTTP client."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook.client import MoltbookClient, MoltbookClientError


class TestMoltbookClient:
    def test_domain_validation_rejects_wrong_domain(self):
        client = MoltbookClient(api_key="test-key")
        client._base_url = "https://evil.com/api/v1"
        with pytest.raises(MoltbookClientError, match="Domain validation failed"):
            client.get("/test")

    def test_domain_validation_allows_correct_domain(self):
        client = MoltbookClient(api_key="test-key")
        client._validate_url("https://www.moltbook.com/api/v1/test")

    def test_auth_header_set(self):
        client = MoltbookClient(api_key="test-key-1234")
        assert client._session.headers["Authorization"] == "Bearer test-key-1234"

    def test_no_auth_header_when_none(self):
        client = MoltbookClient(api_key=None)
        assert "Authorization" not in client._session.headers

    def test_parse_rate_headers(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {
            "X-RateLimit-Remaining": "42",
            "X-RateLimit-Reset": "1700000000.0",
        }
        client._parse_rate_headers(mock_response)
        assert client.rate_limit_remaining == 42
        assert client.rate_limit_reset == 1700000000.0

    def test_reset_tracked_per_bucket_no_cross_clobber(self):
        # Batch E regression (ultracode sweep 2026-06-23): the reset epoch is
        # tracked per bucket. A GET response must not overwrite the write
        # bucket's reset, and rate_limit_reset returns the LATER reset so a
        # proactive wait never under-waits into a 429.
        client = MoltbookClient(api_key="test-key")
        write_resp = MagicMock()
        write_resp.headers = {"X-RateLimit-Remaining": "2", "X-RateLimit-Reset": "2000.0"}
        client._parse_rate_headers(write_resp, method="POST")
        read_resp = MagicMock()
        read_resp.headers = {"X-RateLimit-Remaining": "55", "X-RateLimit-Reset": "1000.0"}
        client._parse_rate_headers(read_resp, method="GET")

        # The GET (earlier reset) did not clobber the depleted write bucket.
        assert client._write_reset == 2000.0
        assert client._read_reset == 1000.0
        # rate_limit_reset is the later reset (safe: never under-wait).
        assert client.rate_limit_reset == 2000.0
        # remaining is the min (conservative).
        assert client.rate_limit_remaining == 2

    def test_parse_rate_headers_clamps_negative(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"X-RateLimit-Remaining": "-5"}
        client._parse_rate_headers(mock_response)
        assert client.rate_limit_remaining == 0

    def test_parse_rate_headers_missing(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {}
        client._parse_rate_headers(mock_response)
        assert client.rate_limit_remaining is None

    def test_redirects_disabled(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response) as mock_req:
            client.get("/test")
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["allow_redirects"] is False

    @patch("contemplative_agent.adapters.moltbook.client.requests.Session")
    def test_retry_on_429(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "0.01"}

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.headers = {}

        mock_session.request.side_effect = [resp_429, resp_200]

        # Use proper init with patched Session
        client = MoltbookClient(api_key="test-key")
        result = client.get("/test")
        assert result.status_code == 200
        assert mock_session.request.call_count == 2

    @patch("contemplative_agent.adapters.moltbook.client.requests.Session")
    def test_retry_after_capped(self, mock_session_cls):
        mock_session = MagicMock()
        mock_session_cls.return_value = mock_session

        resp_429 = MagicMock()
        resp_429.status_code = 429
        resp_429.headers = {"Retry-After": "999999"}  # Should be capped

        resp_200 = MagicMock()
        resp_200.status_code = 200
        resp_200.headers = {}

        mock_session.request.side_effect = [resp_429, resp_200]

        client = MoltbookClient(api_key="test-key")
        # Patch sleep to verify the capped value
        with patch("contemplative_agent.adapters.moltbook.client.time.sleep") as mock_sleep:
            client.get("/test")
            mock_sleep.assert_called_once_with(300)  # MAX_RETRY_AFTER

    def test_api_error_raises(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response):
            with pytest.raises(MoltbookClientError, match="API error 500") as exc_info:
                client.get("/test")
            assert exc_info.value.status_code == 500

    def test_error_status_code_attribute(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response):
            with pytest.raises(MoltbookClientError) as exc_info:
                client.get("/test")
            assert exc_info.value.status_code == 403

    def test_error_without_status_code(self):
        exc = MoltbookClientError("generic error")
        assert exc.status_code is None


class TestGetPostComments:
    def test_rejects_invalid_post_id(self):
        client = MoltbookClient(api_key="test-key")
        assert client.get_post_comments("../etc/passwd") == []
        assert client.get_post_comments("a;b") == []
        assert client.get_post_comments("") == []

    def test_accepts_valid_post_id(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"comments": [{"id": "c1"}]}

        with patch.object(client._session, "request", return_value=mock_response):
            result = client.get_post_comments("valid-post-123")
        assert result == [{"id": "c1"}]


class TestGetPost:
    def test_rejects_invalid_post_id(self):
        client = MoltbookClient(api_key="test-key")
        assert client.get_post("../etc/passwd") is None
        assert client.get_post("a;b") is None
        assert client.get_post("") is None

    def test_envelope_wrapped(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "success": True,
            "post": {"id": "p1", "content": "full body"},
        }
        with patch.object(client._session, "request", return_value=mock_response):
            post = client.get_post("p1")
        assert post == {"id": "p1", "content": "full body"}

    def test_top_level_fallback(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"id": "p1", "content": "full body"}
        with patch.object(client._session, "request", return_value=mock_response):
            post = client.get_post("p1")
        assert post == {"id": "p1", "content": "full body"}

    def test_failure_returns_none(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "error"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.get_post("p1") is None


class TestPostComment:
    """Audit H2: HTTP 2xx alone is not success for comment creation —
    post_comment verifies the response envelope. Explicit success:false
    raises (caller treats it like an HTTP failure → no dedup/episode
    record, stays retryable). Ambiguous bodies (non-JSON, missing keys)
    are success-with-WARNING: a false negative would retry and post a
    duplicate externally, worse than a stale dedup entry."""

    @staticmethod
    def _resp(payload, status=200):
        mock_response = MagicMock()
        mock_response.status_code = status
        mock_response.headers = {}
        if isinstance(payload, Exception):
            mock_response.json.side_effect = payload
        else:
            mock_response.json.return_value = payload
        return mock_response

    def test_success_envelope_returns_comment_dict(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._resp({"success": True, "comment": {"id": "c1"}})
        with patch.object(client._session, "request", return_value=resp) as req:
            result = client.post_comment("p1", "hello")
        assert result == {"id": "c1"}
        assert req.call_args.kwargs["json"] == {"content": "hello"}

    def test_body_level_failure_raises(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._resp({"success": False, "error": "invalid content"})
        with patch.object(client._session, "request", return_value=resp):
            with pytest.raises(MoltbookClientError, match="body level"):
                client.post_comment("p1", "hello")

    def test_missing_success_key_treated_as_success(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._resp({"comment": {"id": "c1"}})
        with patch.object(client._session, "request", return_value=resp):
            assert client.post_comment("p1", "hello") == {"id": "c1"}

    def test_non_json_body_warns_and_returns_empty(self, caplog):
        client = MoltbookClient(api_key="test-key")
        resp = self._resp(ValueError("not json"))
        with patch.object(client._session, "request", return_value=resp):
            with caplog.at_level(
                logging.WARNING,
                logger="contemplative_agent.adapters.moltbook.client",
            ):
                result = client.post_comment("p1", "hello")
        assert result == {}
        assert "not JSON" in caplog.text

    def test_missing_id_warns_but_succeeds(self, caplog):
        client = MoltbookClient(api_key="test-key")
        resp = self._resp({"success": True})
        with patch.object(client._session, "request", return_value=resp):
            with caplog.at_level(
                logging.WARNING,
                logger="contemplative_agent.adapters.moltbook.client",
            ):
                result = client.post_comment("p1", "hello")
        assert result == {}
        assert "missing id" in caplog.text

    def test_top_level_id_folded_in_no_warning(self, caplog):
        """A bare top-level id (post-path fallback shape) is folded into
        the returned dict so the contract holds for this envelope too."""
        client = MoltbookClient(api_key="test-key")
        resp = self._resp({"id": "c1"})
        with patch.object(client._session, "request", return_value=resp):
            with caplog.at_level(
                logging.WARNING,
                logger="contemplative_agent.adapters.moltbook.client",
            ):
                result = client.post_comment("p1", "hello")
        assert result == {"id": "c1"}
        assert "missing id" not in caplog.text

    def test_error_message_strips_newlines(self):
        """Log-injection guard: a hostile server cannot forge log lines via
        \\n in the error field (single-line, unlike the HTTP body path)."""
        client = MoltbookClient(api_key="test-key")
        resp = self._resp(
            {"success": False, "error": "bad\n[FAKE] forged log line"}
        )
        with patch.object(client._session, "request", return_value=resp):
            with pytest.raises(MoltbookClientError) as exc_info:
                client.post_comment("p1", "hello")
        assert "\n" not in str(exc_info.value)
        assert "forged log line" in str(exc_info.value)

    def test_invalid_post_id_raises(self):
        client = MoltbookClient(api_key="test-key")
        with pytest.raises(MoltbookClientError, match="Invalid post_id"):
            client.post_comment("../etc/passwd", "hello")

    def test_http_error_still_raises(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._resp({}, status=500)
        resp.text = "Internal Server Error"
        with patch.object(client._session, "request", return_value=resp):
            with pytest.raises(MoltbookClientError, match="API error 500"):
                client.post_comment("p1", "hello")


class TestDeleteMethod:
    def test_delete_request(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response) as mock_req:
            client.delete("/test")
            mock_req.assert_called_once()
            assert mock_req.call_args[0][0] == "DELETE"


class TestSubscribeSubmolt:
    def test_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response):
            assert client.subscribe_submolt("philosophy") is True

    def test_already_subscribed_409(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.text = "Already subscribed"
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response):
            assert client.subscribe_submolt("philosophy") is True

    def test_already_subscribed_400(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Already subscribed"
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response):
            assert client.subscribe_submolt("philosophy") is True

    def test_invalid_name_rejected(self):
        client = MoltbookClient(api_key="test-key")
        assert client.subscribe_submolt("../hack") is False
        assert client.subscribe_submolt("UPPERCASE") is False
        assert client.subscribe_submolt("") is False

    def test_server_error_returns_false(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response):
            assert client.subscribe_submolt("philosophy") is False


class TestFollowAgentValidation:
    """FINDING-1: agent_name must be validated before URL interpolation."""

    def test_rejects_path_traversal(self):
        client = MoltbookClient(api_key="test-key")
        assert client.follow_agent("../../admin/delete") is False

    def test_rejects_empty_name(self):
        client = MoltbookClient(api_key="test-key")
        assert client.follow_agent("") is False

    def test_rejects_spaces(self):
        client = MoltbookClient(api_key="test-key")
        assert client.follow_agent("agent name") is False

    def test_rejects_too_long_name(self):
        client = MoltbookClient(api_key="test-key")
        assert client.follow_agent("a" * 65) is False

    def test_accepts_valid_name(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"action": "followed"}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.follow_agent("contemplative-bot_1") is True

    def test_accepts_max_length_name(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"action": "followed"}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.follow_agent("a" * 64) is True


class TestRateLimitBudget:
    """Tests for 429 counter and budget checking."""

    def test_429_counter_increments_on_429(self):
        client = MoltbookClient(api_key="test-key")
        assert client.recent_429_count == 0

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "1"}
        mock_response.text = "rate limited"

        with patch.object(client._session, "request", return_value=mock_response):
            with pytest.raises(MoltbookClientError):
                client.get("/test")

        assert client.recent_429_count > 0

    def test_429_counter_resets(self):
        client = MoltbookClient(api_key="test-key")
        client._recent_429_count = 5
        client.reset_429_count()
        assert client.recent_429_count == 0

    def test_429_counter_increments_on_hard_limit(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {}
        mock_response.text = "Limit reached for today"

        with patch.object(client._session, "request", return_value=mock_response):
            with pytest.raises(MoltbookClientError):
                client.get("/test")

        assert client.recent_429_count == 1

class TestDualRateLimit:
    """Tests for GET/POST separated rate limiting."""

    def test_parse_rate_headers_assigns_to_read_for_get(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"X-RateLimit-Remaining": "42"}
        client._parse_rate_headers(mock_response, method="GET")
        assert client._read_remaining == 42
        assert client._write_remaining is None

    def test_parse_rate_headers_assigns_to_write_for_post(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"X-RateLimit-Remaining": "15"}
        client._parse_rate_headers(mock_response, method="POST")
        assert client._write_remaining == 15
        assert client._read_remaining is None

    def test_rate_limit_remaining_backward_compat_returns_min(self):
        client = MoltbookClient(api_key="test-key")
        client._read_remaining = 50
        client._write_remaining = 10
        assert client.rate_limit_remaining == 10

    def test_rate_limit_remaining_none_when_both_unknown(self):
        client = MoltbookClient(api_key="test-key")
        assert client.rate_limit_remaining is None

    def test_has_read_budget(self):
        client = MoltbookClient(api_key="test-key")
        client._read_remaining = 3
        assert client.has_read_budget(reserve=5) is False
        client._read_remaining = 10
        assert client.has_read_budget(reserve=5) is True

    def test_has_write_budget(self):
        client = MoltbookClient(api_key="test-key")
        client._write_remaining = 2
        assert client.has_write_budget(reserve=3) is False
        client._write_remaining = 10
        assert client.has_write_budget(reserve=3) is True

    def test_method_fallback_defaults_to_read(self):
        """Default method arg is GET → read bucket."""
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"X-RateLimit-Remaining": "5"}
        client._parse_rate_headers(mock_response)  # default method="GET"
        assert client._read_remaining == 5


class TestGetHome:
    def test_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "your_account": {"name": "TestBot", "id": "abc"},
            "activity_on_your_posts": [],
        }
        with patch.object(client._session, "request", return_value=mock_response):
            result = client.get_home()
        assert result["your_account"]["name"] == "TestBot"

    def test_failure_returns_empty_dict(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            result = client.get_home()
        assert result == {}

    def test_invalid_json_returns_empty_dict(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.side_effect = ValueError("bad json")
        with patch.object(client._session, "request", return_value=mock_response):
            result = client.get_home()
        assert result == {}


class TestMarkNotificationsRead:
    def test_mark_read_by_post_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.mark_notifications_read_by_post("post-123") is True

    def test_mark_read_by_post_invalid_id(self):
        client = MoltbookClient(api_key="test-key")
        assert client.mark_notifications_read_by_post("../hack") is False

class TestUpvote:
    def test_upvote_post_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.upvote_post("post-123") is True

    def test_upvote_post_already_upvoted_409(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.text = "Already upvoted"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.upvote_post("post-123") is True

    def test_upvote_post_invalid_id(self):
        client = MoltbookClient(api_key="test-key")
        assert client.upvote_post("../hack") is False

    def test_upvote_comment_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.upvote_comment("comment-456") is True

    def test_upvote_comment_already_upvoted_409(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_response.text = "Already upvoted"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.upvote_comment("comment-456") is True

    def test_upvote_comment_server_error(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "error"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.upvote_comment("comment-456") is False


class TestSearch:
    def test_search_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "results": [{"id": "p1", "title": "test"}],
        }
        with patch.object(client._session, "request", return_value=mock_response):
            results = client.search("contemplative AI")
        assert len(results) == 1

    def test_search_caps_query_and_limit(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"results": []}
        with patch.object(client._session, "request", return_value=mock_response) as mock_req:
            client.search("x" * 300, limit=100)
            call_kwargs = mock_req.call_args[1]
            params = call_kwargs["params"]
            assert len(params["q"]) == 200
            assert params["limit"] == 50

    def test_search_failure_returns_empty(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "error"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.search("test") == []

    def test_search_type_param(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {"results": []}
        with patch.object(client._session, "request", return_value=mock_response) as mock_req:
            client.search("test", search_type="comments")
            params = mock_req.call_args[1]["params"]
            assert params["type"] == "comments"

    def test_search_invalid_json(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.side_effect = ValueError("bad")
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.search("test") == []


class TestFollowingFeed:
    def test_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            "posts": [{"id": "p1"}, {"id": "p2"}],
        }
        with patch.object(client._session, "request", return_value=mock_response):
            posts = client.get_following_feed()
        assert len(posts) == 2

    def test_failure_returns_empty(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "error"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.get_following_feed() == []


class TestUnfollowAgent:
    def test_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.unfollow_agent("some-agent") is True

    def test_invalid_name(self):
        client = MoltbookClient(api_key="test-key")
        assert client.unfollow_agent("../hack") is False

    def test_server_error(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "error"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.unfollow_agent("some-agent") is False

    def test_404_agent_not_found_is_idempotent_success(self):
        # Regression (ultracode sweep 2026-06-23): a 404 means the agent was
        # deleted server-side, so we are effectively no longer following it.
        # Returning True lets the caller prune the stale local follow entry —
        # without this every scheduled run re-issued the same doomed DELETE
        # (observed 31× for a single deleted agent).
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = '{"statusCode":404,"message":"Agent not found"}'
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.unfollow_agent("gone-agent") is True

    # Audit L3: HTTP 2xx alone is not success — the DELETE body must be
    # verified, mirroring follow_agent's action check and post_comment's
    # ambiguous-body handling (audit H2). A silently failed unfollow is
    # the code-level home of the known follow-list drift.

    def _respond(self, body):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = body
        return mock_response

    def test_body_action_unfollowed(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._respond({"action": "unfollowed"})
        with patch.object(client._session, "request", return_value=resp):
            assert client.unfollow_agent("some-agent") is True

    def test_body_action_not_following_is_idempotent_success(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._respond({"action": "not_following"})
        with patch.object(client._session, "request", return_value=resp):
            assert client.unfollow_agent("some-agent") is True

    def test_body_success_false_returns_false(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._respond({"success": False, "error": "not following"})
        with patch.object(client._session, "request", return_value=resp):
            assert client.unfollow_agent("some-agent") is False

    def test_body_unexpected_action_returns_false(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._respond({"action": "followed"})
        with patch.object(client._session, "request", return_value=resp):
            assert client.unfollow_agent("some-agent") is False

    def test_ambiguous_empty_body_assumed_success(self):
        client = MoltbookClient(api_key="test-key")
        resp = self._respond({})
        with patch.object(client._session, "request", return_value=resp):
            assert client.unfollow_agent("some-agent") is True


# TestUpdateProfile / TestPatchMethod / TestUnsubscribeSubmolt /
# mark_all tests were removed together with the dead client capabilities
# (no production caller; security by absence — see client.py note).


_AUDIT_TARGET = "contemplative_agent.adapters.moltbook.client.append_jsonl_restricted"


def _resp(payload, status=200, headers=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = payload
    r.text = "" if isinstance(payload, dict) else "body"
    return r


class TestPostCommentParentId:
    def test_parent_id_included_in_body(self):
        client = MoltbookClient(api_key="k")
        resp = _resp({"success": True, "comment": {"id": "c2"}})
        with patch.object(client._session, "request", return_value=resp) as req:
            client.post_comment("p1", "hi", parent_id="c1")
        assert req.call_args.kwargs["json"] == {"content": "hi", "parent_id": "c1"}

    def test_no_parent_id_omits_field(self):
        client = MoltbookClient(api_key="k")
        resp = _resp({"success": True, "comment": {"id": "c2"}})
        with patch.object(client._session, "request", return_value=resp) as req:
            client.post_comment("p1", "hi")
        assert req.call_args.kwargs["json"] == {"content": "hi"}

    def test_invalid_parent_id_raises(self):
        client = MoltbookClient(api_key="k")
        with pytest.raises(MoltbookClientError, match="Invalid parent_id"):
            client.post_comment("p1", "hi", parent_id="../etc/passwd")


class TestPostCommentVerificationSurfacing:
    """The comment verification gate (feed_manager/reply_handler) reads
    ``created.get("verification")`` on post_comment's return. Confirm — through
    real response parsing — that the challenge surfaces regardless of nesting."""

    def test_verification_nested_under_comment(self):
        client = MoltbookClient(api_key="k")
        resp = _resp({
            "success": True,
            "comment": {
                "id": "c1",
                "verification": {"verification_code": "moltbook_verify_x",
                                 "challenge_text": "noise"},
            },
        })
        with patch.object(client._session, "request", return_value=resp):
            created = client.post_comment("p1", "hi")
        assert created["verification"]["verification_code"] == "moltbook_verify_x"

    def test_verification_at_response_root_is_folded_in(self):
        # If the API puts verification at the root (not inside "comment"), it is
        # folded into the returned dict so the caller's gate still fires.
        client = MoltbookClient(api_key="k")
        resp = _resp({
            "success": True,
            "comment": {"id": "c1"},
            "verification": {"verification_code": "moltbook_verify_x",
                             "challenge_text": "noise"},
        })
        with patch.object(client._session, "request", return_value=resp):
            created = client.post_comment("p1", "hi")
        assert created["verification"]["verification_code"] == "moltbook_verify_x"

    def test_no_verification_when_trusted(self):
        client = MoltbookClient(api_key="k")
        resp = _resp({"success": True, "comment": {"id": "c1"}})
        with patch.object(client._session, "request", return_value=resp):
            created = client.post_comment("p1", "hi")
        assert "verification" not in created


class TestApiInstrumentation:
    def test_records_structural_fields_without_freetext(self):
        client = MoltbookClient(api_key="k")
        resp = _resp(
            {
                "success": True,
                "post": {
                    "id": "p1",
                    "verification_status": "pending",
                    "content": "SECRET BODY TEXT",
                },
            },
            status=201,
        )
        captured: list = []
        with patch.object(client._session, "request", return_value=resp), \
             patch(_AUDIT_TARGET, side_effect=lambda path, rec: captured.append(rec)):
            client.post("/posts", json={"title": "t", "content": "SECRET BODY TEXT"})
        assert len(captured) == 1
        rec = captured[0]
        assert rec["endpoint"] == "POST /posts"
        assert rec["status"] == 201
        assert rec["success"] is True
        assert rec["content_status"] == {"verification_status": "pending"}
        # The audit log must never carry untrusted free-text body content.
        import json as _json
        assert "SECRET BODY TEXT" not in _json.dumps(rec)

    def test_soft_fail_flagged(self):
        client = MoltbookClient(api_key="k")
        resp = _resp({"success": False, "error": "nope"}, status=200)
        captured: list = []
        with patch.object(client._session, "request", return_value=resp), \
             patch(_AUDIT_TARGET, side_effect=lambda path, rec: captured.append(rec)):
            client.get("/feed")
        assert captured[0]["soft_fail"] is True
        assert captured[0]["error"] == "nope"

    def test_drift_warning_on_missing_expected_key(self, caplog):
        client = MoltbookClient(api_key="k")
        resp = _resp({"foo": 1}, status=200)  # GET /agents/me depends on "agent"
        captured: list = []
        with patch.object(client._session, "request", return_value=resp), \
             patch(_AUDIT_TARGET, side_effect=lambda path, rec: captured.append(rec)), \
             caplog.at_level(
                 logging.WARNING,
                 logger="contemplative_agent.adapters.moltbook.client",
             ):
            client.get("/agents/me")
        assert "API drift" in caplog.text
        assert captured[0]["drift_missing"] == ["agent"]

    def test_error_response_does_not_trigger_false_drift(self, caplog):
        # A 4xx on a create endpoint returns the error envelope ({error,message}),
        # which lacks the success key — that must NOT be flagged as schema drift.
        client = MoltbookClient(api_key="k")
        resp = _resp({"error": "Not found", "message": "x"}, status=404)
        resp.text = "Not found"
        captured: list = []
        with patch.object(client._session, "request", return_value=resp), \
             patch(_AUDIT_TARGET, side_effect=lambda path, rec: captured.append(rec)), \
             caplog.at_level(
                 logging.WARNING,
                 logger="contemplative_agent.adapters.moltbook.client",
             ):
            with pytest.raises(MoltbookClientError):
                client.post("/posts/abc/comments", json={"content": "hi"})
        assert "API drift" not in caplog.text
        assert "drift_missing" not in captured[0]

    def test_id_normalized_in_endpoint(self):
        client = MoltbookClient(api_key="k")
        resp = _resp({"success": True, "post": {"id": "x"}}, status=200)
        captured: list = []
        with patch.object(client._session, "request", return_value=resp), \
             patch(_AUDIT_TARGET, side_effect=lambda path, rec: captured.append(rec)):
            client.get("/posts/9a1d74d9-3c21-4294-bb0d-cda2f4fedcd8")
        assert captured[0]["endpoint"] == "GET /posts/{id}"

    def test_instrumentation_failure_never_breaks_request(self):
        client = MoltbookClient(api_key="k")
        resp = _resp({"success": True, "agent": {}}, status=200)
        with patch.object(client._session, "request", return_value=resp), \
             patch(_AUDIT_TARGET, side_effect=OSError("disk full")):
            out = client.get("/agents/me")  # must not raise
        assert out is resp
