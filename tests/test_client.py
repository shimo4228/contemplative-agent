"""Tests for the Moltbook HTTP client."""

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


class TestUnsubscribeSubmolt:
    def test_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response):
            assert client.unsubscribe_submolt("philosophy") is True

    def test_invalid_name_rejected(self):
        client = MoltbookClient(api_key="test-key")
        assert client.unsubscribe_submolt("../hack") is False

    def test_server_error_returns_false(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.headers = {}

        with patch.object(client._session, "request", return_value=mock_response):
            assert client.unsubscribe_submolt("philosophy") is False


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

    def test_has_budget_true_when_remaining_unknown(self):
        client = MoltbookClient(api_key="test-key")
        assert client.rate_limit_remaining is None
        assert client.has_budget(reserve=5) is True

    def test_has_budget_true_when_remaining_above_reserve(self):
        client = MoltbookClient(api_key="test-key")
        client._read_remaining = 20
        client._write_remaining = 20
        assert client.has_budget(reserve=5) is True

    def test_has_budget_false_when_remaining_at_reserve(self):
        client = MoltbookClient(api_key="test-key")
        client._read_remaining = 5
        client._write_remaining = 5
        assert client.has_budget(reserve=5) is False

    def test_has_budget_false_when_remaining_below_reserve(self):
        client = MoltbookClient(api_key="test-key")
        client._read_remaining = 3
        client._write_remaining = 3
        assert client.has_budget(reserve=5) is False


class TestDualRateLimit:
    """Tests for GET/POST separated rate limiting."""

    def test_parse_rate_headers_assigns_to_read_for_get(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"X-RateLimit-Remaining": "42"}
        client._parse_rate_headers(mock_response, method="GET")
        assert client.read_remaining == 42
        assert client.write_remaining is None

    def test_parse_rate_headers_assigns_to_write_for_post(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.headers = {"X-RateLimit-Remaining": "15"}
        client._parse_rate_headers(mock_response, method="POST")
        assert client.write_remaining == 15
        assert client.read_remaining is None

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
        assert client.read_remaining == 5


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

    def test_mark_all_read_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.mark_all_notifications_read() is True

    def test_mark_all_read_failure(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "error"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.mark_all_notifications_read() is False


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


class TestUpdateProfile:
    def test_success(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.update_profile(description="New bio") is True

    def test_failure(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "forbidden"
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.update_profile(description="New bio") is False

    def test_rejects_unknown_fields(self):
        client = MoltbookClient(api_key="test-key")
        assert client.update_profile(api_key="stolen") is False

    def test_rejects_mixed_known_and_unknown(self):
        client = MoltbookClient(api_key="test-key")
        assert client.update_profile(description="ok", evil="bad") is False

    def test_allows_metadata_field(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response):
            assert client.update_profile(metadata={"key": "val"}) is True


class TestPatchMethod:
    def test_patch_request(self):
        client = MoltbookClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        with patch.object(client._session, "request", return_value=mock_response) as mock_req:
            client.patch("/test", json={"key": "val"})
            assert mock_req.call_args[0][0] == "PATCH"
