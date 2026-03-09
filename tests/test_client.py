"""Tests for the Moltbook HTTP client."""

from unittest.mock import MagicMock, patch

import pytest

from contemplative_moltbook.adapters.moltbook.client import MoltbookClient, MoltbookClientError


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

    @patch("contemplative_moltbook.adapters.moltbook.client.requests.Session")
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

    @patch("contemplative_moltbook.adapters.moltbook.client.requests.Session")
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
        with patch("contemplative_moltbook.adapters.moltbook.client.time.sleep") as mock_sleep:
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
