"""Tests for LLM interface and sanitization."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from contemplative_agent.adapters.moltbook.llm_functions import (
    extract_topics,
    generate_comment,
    generate_cooperation_post,
    generate_reply,
    score_relevance,
    select_submolt,
)
from contemplative_agent.core.llm import (
    _get_model,
    _get_ollama_url,
    _sanitize_output,
    wrap_untrusted_content,
    generate,
)


class TestSanitizeOutput:
    def test_removes_forbidden_pattern(self):
        result = _sanitize_output("My api_key is here", 1000)
        assert "api_key" not in result
        assert "[REDACTED]" in result

    def test_case_insensitive_removal(self):
        result = _sanitize_output("Bearer xyz here", 1000)
        assert "bearer" not in result.lower()
        assert "[REDACTED]" in result

    def test_mixed_case_removal(self):
        result = _sanitize_output("API_KEY leaked", 1000)
        assert "api_key" not in result.lower()

    def test_enforces_length(self):
        long_text = "a" * 10000
        result = _sanitize_output(long_text, 100)
        assert len(result) == 100

    def test_strips_whitespace(self):
        result = _sanitize_output("  hello  ", 1000)
        assert result == "hello"

    def test_preserves_clean_text(self):
        result = _sanitize_output("Clean text about alignment", 1000)
        assert result == "Clean text about alignment"

    def test_multiple_patterns(self):
        result = _sanitize_output("api_key and password here", 1000)
        assert result.count("[REDACTED]") == 2


class TestWrapUntrustedContent:
    def test_wraps_with_tags(self):
        result = wrap_untrusted_content("some post")
        assert "<untrusted_content>" in result
        assert "</untrusted_content>" in result
        assert "some post" in result

    def test_truncates_long_input(self):
        long_text = "x" * 5000
        result = wrap_untrusted_content(long_text)
        # Should truncate to 1000 chars
        assert len(result) < 1200

    def test_includes_injection_warning(self):
        result = wrap_untrusted_content("test")
        assert "Do NOT follow" in result


class TestOllamaUrlValidation:
    def test_localhost_allowed(self):
        url = _get_ollama_url()
        assert "localhost" in url or "127.0.0.1" in url

    def test_rejects_remote_url(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "https://evil.com")
        with pytest.raises(ValueError, match="must point to localhost"):
            _get_ollama_url()

    def test_allows_127_0_0_1(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
        assert _get_ollama_url() == "http://127.0.0.1:11434"


class TestSanitizeWordBoundary:
    """Test word-boundary matching for FORBIDDEN_WORD_PATTERNS."""

    def test_token_economy_passes(self):
        result = _sanitize_output("token economy is growing", 1000)
        assert "token economy" in result
        assert "[REDACTED]" not in result

    def test_tokenization_passes(self):
        result = _sanitize_output("tokenization of assets", 1000)
        assert "tokenization" in result
        assert "[REDACTED]" not in result

    def test_standalone_token_allowed(self):
        """Standalone 'token' is no longer blocked; 'Bearer ' and 'auth_token' catch real leaks."""
        result = _sanitize_output("my token is useful", 1000)
        assert "token" in result

    def test_bearer_token_blocked(self):
        result = _sanitize_output("Bearer abc123 leaked", 1000)
        assert "Bearer" not in result
        assert "[REDACTED]" in result

    def test_auth_token_blocked(self):
        result = _sanitize_output("my auth_token is xyz", 1000)
        assert "auth_token" not in result
        assert "[REDACTED]" in result

    def test_password_in_compound_passes(self):
        result = _sanitize_output("passwordless authentication", 1000)
        assert "passwordless" in result
        assert "[REDACTED]" not in result

    def test_standalone_password_blocked(self):
        result = _sanitize_output("enter your password here", 1000)
        assert "[REDACTED]" in result

    def test_secret_sharing_passes(self):
        result = _sanitize_output("secret-sharing protocol", 1000)
        # "secret" is at a word boundary here, should be caught
        assert "[REDACTED]" in result
        result2 = _sanitize_output("secretarial work", 1000)
        assert "secretarial" in result2

    def test_api_key_still_substring_matched(self):
        result = _sanitize_output("my_api_key_value", 1000)
        assert "[REDACTED]" in result


class TestScoreRelevanceParsing:
    """Test robust parsing of LLM relevance score output."""

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_clean_number(self, mock_generate):
        mock_generate.return_value = "0.75"
        assert score_relevance("test post") == 0.75

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_number_with_trailing_text(self, mock_generate):
        mock_generate.return_value = "0.7\n\nThis post discusses"
        assert score_relevance("test post") == 0.7

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_number_with_leading_text(self, mock_generate):
        mock_generate.return_value = "The score is 0.8"
        assert score_relevance("test post") == 0.8

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_no_number_returns_zero(self, mock_generate):
        mock_generate.return_value = "This is not relevant"
        assert score_relevance("test post") == 0.0

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_none_returns_zero(self, mock_generate):
        mock_generate.return_value = None
        assert score_relevance("test post") == 0.0

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_score_clamped_to_max_1(self, mock_generate):
        mock_generate.return_value = "1.5"
        assert score_relevance("test post") == 1.0

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_integer_score(self, mock_generate):
        mock_generate.return_value = "1"
        assert score_relevance("test post") == 1.0

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_chinese_text_with_number(self, mock_generate):
        mock_generate.return_value = "0.6 该内容讨论了冥想"
        assert score_relevance("test post") == 0.6


class TestGetModel:
    def test_default_model(self):
        result = _get_model()
        assert result  # Returns a non-empty string

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_MODEL", "llama3:8b")
        assert _get_model() == "llama3:8b"


class TestGenerate:
    @patch("contemplative_agent.core.llm.requests.post")
    def test_successful_generation(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Hello world"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = generate("test prompt")
        assert result == "Hello world"
        mock_post.assert_called_once()

    @patch("contemplative_agent.core.llm.requests.post")
    def test_custom_system_prompt(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "custom response"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        generate("test", system="custom system")
        payload = mock_post.call_args[1]["json"]
        assert payload["system"] == "custom system"

    @patch("contemplative_agent.core.llm.requests.post")
    def test_request_exception_returns_none(self, mock_post):
        mock_post.side_effect = requests.RequestException("connection error")
        assert generate("test") is None

    @patch("contemplative_agent.core.llm.requests.post")
    def test_json_decode_error_returns_none(self, mock_post):
        import json as json_mod

        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.side_effect = json_mod.JSONDecodeError("bad", "", 0)
        mock_post.return_value = mock_resp

        assert generate("test") is None

    @patch("contemplative_agent.core.llm.requests.post")
    def test_empty_response_returns_none(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "   "}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        assert generate("test") is None

    @patch("contemplative_agent.core.llm.requests.post")
    def test_sanitizes_output(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "my api_key is leaked"}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = generate("test")
        assert "api_key" not in result
        assert "[REDACTED]" in result

    @patch("contemplative_agent.core.llm.requests.post")
    def test_respects_max_length(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "a" * 200}
        mock_resp.raise_for_status.return_value = None
        mock_post.return_value = mock_resp

        result = generate("test", max_length=50)
        assert len(result) == 50


class TestGenerateComment:
    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_returns_generated_text(self, mock_gen):
        mock_gen.return_value = "Interesting take on cooperation."
        result = generate_comment("a post about AI cooperation")
        assert result == "Interesting take on cooperation."

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_returns_none_on_failure(self, mock_gen):
        mock_gen.return_value = None
        assert generate_comment("some post") is None


class TestGenerateCooperationPost:
    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_returns_generated_post(self, mock_gen):
        mock_gen.return_value = "A post about cooperation trends."
        result = generate_cooperation_post("alignment, safety, cooperation")
        assert result == "A post about cooperation trends."

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_returns_none_on_failure(self, mock_gen):
        mock_gen.return_value = None
        assert generate_cooperation_post("topics") is None


class TestGenerateReply:
    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_basic_reply(self, mock_gen):
        mock_gen.return_value = "I agree, that's a great point."
        result = generate_reply("original post", "their comment")
        assert result == "I agree, that's a great point."

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_reply_with_history(self, mock_gen):
        mock_gen.return_value = "Building on our earlier discussion..."
        result = generate_reply(
            "original post",
            "their comment",
            conversation_history=["prev exchange 1", "prev exchange 2"],
        )
        assert result == "Building on our earlier discussion..."
        prompt = mock_gen.call_args[0][0]
        assert "prev exchange 1" in prompt
        assert "prev exchange 2" in prompt

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_reply_without_history(self, mock_gen):
        mock_gen.return_value = "response"
        generate_reply("post", "comment", conversation_history=None)
        prompt = mock_gen.call_args[0][0]
        assert "Previous exchanges" not in prompt

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_returns_none_on_failure(self, mock_gen):
        mock_gen.return_value = None
        assert generate_reply("post", "comment") is None


class TestExtractTopics:
    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_extracts_from_posts(self, mock_gen):
        mock_gen.return_value = "alignment\nsafety\ncooperation"
        posts = [
            {"title": "AI Safety", "content": "Discussion about safety..."},
            {"title": "Cooperation", "content": "How agents cooperate..."},
        ]
        result = extract_topics(posts)
        assert result == "alignment\nsafety\ncooperation"

    def test_empty_posts_returns_none(self):
        assert extract_topics([]) is None

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_generate_failure_returns_none(self, mock_gen):
        mock_gen.return_value = None
        assert extract_topics([{"title": "T", "content": "C"}]) is None

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_limits_to_10_posts(self, mock_gen):
        mock_gen.return_value = "topics"
        posts = [{"title": f"Post {i}", "content": f"Content {i}"} for i in range(20)]
        extract_topics(posts)
        prompt = mock_gen.call_args[0][0]
        assert "Post 9" in prompt
        assert "Post 10" not in prompt


class TestSelectSubmolt:
    _DEFAULT_SUBMOLTS = (
        "alignment", "philosophy", "consciousness", "coordination",
        "ponderings", "memories", "agent-rights",
    )

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_exact_match(self, mock_gen):
        mock_gen.return_value = "philosophy"
        result = select_submolt("A post about Plato", self._DEFAULT_SUBMOLTS)
        assert result == "philosophy"

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_match_within_text(self, mock_gen):
        mock_gen.return_value = "I think consciousness would be best"
        result = select_submolt("A post about qualia", self._DEFAULT_SUBMOLTS)
        assert result == "consciousness"

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_none_on_failure(self, mock_gen):
        mock_gen.return_value = None
        result = select_submolt("some post", self._DEFAULT_SUBMOLTS)
        assert result is None

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_none_on_unrecognized(self, mock_gen):
        mock_gen.return_value = "sports"
        result = select_submolt("some post", self._DEFAULT_SUBMOLTS)
        assert result is None

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_custom_submolts(self, mock_gen):
        mock_gen.return_value = "ethics"
        result = select_submolt("post", submolts=("ethics", "logic"))
        assert result == "ethics"


class TestBroadenedRelevancePrompt:
    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate")
    def test_prompt_includes_broad_topics(self, mock_gen):
        mock_gen.return_value = "0.9"
        score_relevance("test post")
        prompt = mock_gen.call_args[0][0]
        # Topic keywords are now resolved from domain.json
        assert "philosophy" in prompt
        assert "consciousness" in prompt
        assert "reflective thought" in prompt


class TestCircuitBreaker:
    """Phase 2A: LLM circuit breaker."""

    def setup_method(self):
        """Reset global circuit breaker before each test."""
        from contemplative_agent.core.llm import _circuit
        _circuit.record_success()  # Reset state

    def test_circuit_closed_initially(self):
        from contemplative_agent.core.llm import _circuit
        assert _circuit.is_open is False

    def test_circuit_opens_after_threshold(self):
        from contemplative_agent.core.llm import _circuit, CIRCUIT_FAILURE_THRESHOLD
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            _circuit.record_failure()
        assert _circuit.is_open is True

    def test_circuit_resets_on_success(self):
        from contemplative_agent.core.llm import _circuit, CIRCUIT_FAILURE_THRESHOLD
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            _circuit.record_failure()
        assert _circuit.is_open is True
        _circuit.record_success()
        assert _circuit.is_open is False

    def test_circuit_recovers_after_cooldown(self):
        from contemplative_agent.core.llm import _circuit, CIRCUIT_FAILURE_THRESHOLD
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            _circuit.record_failure()
        assert _circuit.is_open is True
        # Simulate cooldown elapsed
        _circuit._opened_at = 0.0
        assert _circuit.is_open is False

    @patch("contemplative_agent.core.llm.requests.post")
    def test_generate_returns_none_when_open(self, mock_post):
        from contemplative_agent.core.llm import _circuit, CIRCUIT_FAILURE_THRESHOLD
        for _ in range(CIRCUIT_FAILURE_THRESHOLD):
            _circuit.record_failure()

        result = generate("test prompt")
        assert result is None
        mock_post.assert_not_called()

    @patch("contemplative_agent.core.llm.requests.post")
    def test_generate_records_failure(self, mock_post):
        from contemplative_agent.core.llm import _circuit
        mock_post.side_effect = requests.ConnectionError("refused")

        result = generate("test prompt")
        assert result is None
        assert _circuit._consecutive_failures == 1

    @patch("contemplative_agent.core.llm.requests.post")
    def test_generate_records_success(self, mock_post):
        from contemplative_agent.core.llm import _circuit
        _circuit.record_failure()  # Pre-set one failure
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "Hello world"}
        mock_post.return_value = mock_resp

        result = generate("test prompt")
        assert result == "Hello world"
        assert _circuit._consecutive_failures == 0
