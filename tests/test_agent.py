# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportArgumentType=false
"""Tests for the Agent orchestrator."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook.agent import Agent, AutonomyLevel
from contemplative_agent.adapters.moltbook.reply_handler import (
    extract_agent_fields,
    extract_notification_fields,
)
from contemplative_agent.core.config import VALID_ID_PATTERN
from contemplative_agent.core.memory import MemoryStore


def _make_clean_memory(tmp_path: Path) -> MemoryStore:
    """Create a MemoryStore with temporary paths (no live data)."""
    return MemoryStore(path=tmp_path / "memory.json")


class TestAutonomyLevel:
    def test_values(self):
        assert AutonomyLevel.APPROVE == "approve"
        assert AutonomyLevel.GUARDED == "guarded"
        assert AutonomyLevel.AUTO == "auto"


class TestValidIdPattern:
    @pytest.mark.parametrize("valid_id", ["abc123", "post-1", "a_b_c", "ABC"])
    def test_valid_ids(self, valid_id):
        assert VALID_ID_PATTERN.match(valid_id)

    @pytest.mark.parametrize("invalid_id", ["../etc", "a b", "a;b", "a/b", ""])
    def test_invalid_ids(self, invalid_id):
        assert not VALID_ID_PATTERN.match(invalid_id)


class TestAgentInit:
    def test_default_autonomy(self):
        agent = Agent()
        assert agent._autonomy is AutonomyLevel.APPROVE

    def test_custom_autonomy(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        assert agent._autonomy is AutonomyLevel.AUTO

    def test_initial_state(self):
        agent = Agent()
        assert agent._client is None
        assert agent._scheduler is None
        assert agent._actions_taken == []


class TestEnsureClient:
    @patch("contemplative_agent.adapters.moltbook.agent.Scheduler")
    @patch("contemplative_agent.adapters.moltbook.agent.MoltbookClient")
    @patch("contemplative_agent.adapters.moltbook.agent.load_credentials", return_value="test-key")
    def test_creates_client(self, mock_creds, mock_client_cls, mock_sched_cls):
        agent = Agent()
        client = agent._ensure_client()
        mock_client_cls.assert_called_once_with("test-key")
        mock_sched_cls.assert_called_once()
        assert client is agent._client

    @patch("contemplative_agent.adapters.moltbook.agent.load_credentials", return_value="test-key")
    def test_returns_existing_client(self, mock_creds):
        agent = Agent()
        mock_client = MagicMock()
        agent._client = mock_client
        assert agent._ensure_client() is mock_client
        mock_creds.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.agent.load_credentials", return_value=None)
    def test_raises_without_credentials(self, mock_creds):
        agent = Agent()
        with pytest.raises(RuntimeError, match="No API key found"):
            agent._ensure_client()


class TestGetScheduler:
    def test_raises_when_not_initialized(self):
        agent = Agent()
        with pytest.raises(RuntimeError, match="Scheduler not initialized"):
            agent._get_scheduler()

    def test_returns_scheduler(self):
        agent = Agent()
        mock_sched = MagicMock()
        agent._scheduler = mock_sched
        assert agent._get_scheduler() is mock_sched


class TestPassesContentFilter:
    def test_valid_content(self):
        assert Agent._passes_content_filter("This is a normal post.") is True

    def test_empty_content(self):
        assert Agent._passes_content_filter("") is False
        assert Agent._passes_content_filter("   ") is False

    def test_too_long(self):
        assert Agent._passes_content_filter("x" * 20001) is False

    def test_at_max_length(self):
        assert Agent._passes_content_filter("x" * 20000) is True

    @pytest.mark.parametrize("forbidden", [
        "api_key", "API_KEY", "api-key", "apikey", "password",
        "secret", "Bearer ", "auth_token", "access_token",
    ])
    def test_forbidden_patterns(self, forbidden):
        content = f"Here is my {forbidden} for you"
        assert Agent._passes_content_filter(content) is False

    def test_token_in_discussion_allowed(self):
        """Standalone 'token' is allowed in AI discussion contexts."""
        assert Agent._passes_content_filter("token economy is growing") is True
        assert Agent._passes_content_filter("tokenization of assets") is True

    def test_token_compound_blocked(self):
        """Token as part of credential patterns is still blocked."""
        assert Agent._passes_content_filter("my auth_token is xyz") is False
        assert Agent._passes_content_filter("access_token leaked") is False


class TestConfirmAction:
    def test_auto_always_returns_true(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        assert agent._confirm_action("test", "content") is True

    def test_guarded_passes_filter(self):
        agent = Agent(autonomy=AutonomyLevel.GUARDED)
        assert agent._confirm_action("test", "This is safe content") is True

    def test_guarded_rejects_forbidden(self):
        agent = Agent(autonomy=AutonomyLevel.GUARDED)
        assert agent._confirm_action("test", "my api_key is abc123") is False

    def test_guarded_rejects_empty(self):
        agent = Agent(autonomy=AutonomyLevel.GUARDED)
        assert agent._confirm_action("test", "  ") is False

    def test_guarded_rejects_too_long(self):
        agent = Agent(autonomy=AutonomyLevel.GUARDED)
        assert agent._confirm_action("test", "x" * 20001) is False

    @patch("builtins.input", return_value="y")
    def test_approve_asks_user_yes(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        assert agent._confirm_action("test", "short content") is True
        mock_input.assert_called_once()

    @patch("builtins.input", return_value="n")
    def test_approve_asks_user_no(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        assert agent._confirm_action("test", "short content") is False

    @patch("builtins.input", return_value="")
    def test_approve_empty_is_no(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        assert agent._confirm_action("test", "short content") is False

    @patch("builtins.input", return_value="y")
    def test_truncates_long_content(self, mock_input, capsys):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        long_content = "x" * 600
        agent._confirm_action("test", long_content)
        captured = capsys.readouterr()
        assert "600 chars total" in captured.out


class TestDoRegister:
    @patch("contemplative_agent.adapters.moltbook.agent.register_agent")
    @patch("contemplative_agent.adapters.moltbook.agent.MoltbookClient")
    def test_register(self, mock_client_cls, mock_register):
        mock_register.return_value = {"claim_url": "https://example.com/claim"}
        agent = Agent()
        result = agent.do_register()
        assert result == {"claim_url": "https://example.com/claim"}
        mock_client_cls.assert_called_once_with(api_key=None)

    @patch("contemplative_agent.adapters.moltbook.agent.register_agent")
    @patch("contemplative_agent.adapters.moltbook.agent.MoltbookClient")
    def test_register_no_claim_url(self, mock_client_cls, mock_register):
        mock_register.return_value = {"status": "ok"}
        agent = Agent()
        result = agent.do_register()
        assert result == {"status": "ok"}


class TestDoStatus:
    @patch("contemplative_agent.adapters.moltbook.agent.check_claim_status", return_value={"claimed": True})
    @patch("contemplative_agent.adapters.moltbook.agent.load_credentials", return_value="key")
    def test_status(self, mock_creds, mock_check):
        agent = Agent()
        result = agent.do_status()
        assert result == {"claimed": True}


class TestDoSolve:
    @patch("contemplative_agent.adapters.moltbook.agent.solve_challenge", return_value="forty two")
    def test_solve_success(self, mock_solve, capsys):
        agent = Agent()
        result = agent.do_solve("ffoorrttyyˌttwwoo")
        assert result == "forty two"
        captured = capsys.readouterr()
        assert "forty two" in captured.out

    @patch("contemplative_agent.adapters.moltbook.agent.solve_challenge", return_value=None)
    def test_solve_failure(self, mock_solve, capsys):
        agent = Agent()
        result = agent.do_solve("???")
        assert result is None
        captured = capsys.readouterr()
        assert "Failed" in captured.out


class TestDoIntroduce:
    def _make_agent(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        return agent

    @patch("contemplative_agent.adapters.moltbook.agent.ContentManager")
    def test_introduce_success(self, mock_cm_cls):
        mock_cm = MagicMock()
        mock_cm.get_introduction.return_value = "Hello world"
        mock_cm_cls.return_value = mock_cm

        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._content = mock_cm
        agent._client = MagicMock()
        agent._scheduler = MagicMock()

        resp_mock = MagicMock()
        resp_mock.json.return_value = {"id": "post-123"}
        agent._client.post.return_value = resp_mock

        result = agent.do_introduce()
        assert result == "post-123"
        assert "Posted introduction" in agent._actions_taken

    @patch("contemplative_agent.adapters.moltbook.agent.ContentManager")
    def test_introduce_already_posted(self, mock_cm_cls):
        mock_cm = MagicMock()
        mock_cm.get_introduction.return_value = None
        mock_cm_cls.return_value = mock_cm

        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._content = mock_cm
        agent._client = MagicMock()
        agent._scheduler = MagicMock()

        result = agent.do_introduce()
        assert result is None

    def test_introduce_client_error(self):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError

        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._content = MagicMock()
        agent._content.get_introduction.return_value = "Hello"
        agent._client = MagicMock()
        agent._client.post.side_effect = MoltbookClientError("fail")
        agent._scheduler = MagicMock()

        result = agent.do_introduce()
        assert result is None

    @patch("builtins.input", return_value="n")
    def test_introduce_user_declines(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        agent._content = MagicMock()
        agent._content.get_introduction.return_value = "Hello"
        agent._client = MagicMock()
        agent._scheduler = MagicMock()

        result = agent.do_introduce()
        assert result is None


class TestFetchFeed:
    def test_fetch_success(self):
        agent = Agent()
        mock_client = MagicMock()
        resp_mock = MagicMock()
        resp_mock.json.return_value = {"posts": [{"id": "1"}, {"id": "2"}]}
        mock_client.get.return_value = resp_mock

        posts = agent._feed_manager.fetch_feed(mock_client)
        # Fetches from each subscribed submolt feed
        assert len(posts) >= 2
        calls = mock_client.get.call_args_list
        assert any("/submolts/" in str(c) and "/feed" in str(c) for c in calls)

    def test_fetch_error(self):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError

        agent = Agent()
        mock_client = MagicMock()
        mock_client.get.side_effect = MoltbookClientError("fail")

        posts = agent._feed_manager.fetch_feed(mock_client)
        assert posts == []


class TestHandleVerification:
    def test_should_stop(self):
        agent = Agent()
        agent._verification = MagicMock()
        agent._verification.should_stop = True

        result = agent._handle_verification({"text": "test", "id": "v1"})
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.agent.solve_challenge", return_value=None)
    def test_solve_fails(self, mock_solve):
        agent = Agent()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        result = agent._handle_verification({"text": "test", "id": "v1"})
        assert result is False
        agent._verification.record_failure.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.agent.submit_verification")
    @patch("contemplative_agent.adapters.moltbook.agent.solve_challenge", return_value="answer")
    def test_submit_success(self, mock_solve, mock_submit):
        mock_submit.return_value = {"success": True}
        agent = Agent()
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        result = agent._handle_verification({"text": "test", "id": "v1"})
        assert result is True
        agent._verification.record_success.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.agent.submit_verification")
    @patch("contemplative_agent.adapters.moltbook.agent.solve_challenge", return_value="answer")
    def test_submit_failure(self, mock_solve, mock_submit):
        mock_submit.return_value = {"success": False}
        agent = Agent()
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        result = agent._handle_verification({"text": "test", "id": "v1"})
        assert result is False
        agent._verification.record_failure.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.agent.submit_verification")
    @patch("contemplative_agent.adapters.moltbook.agent.solve_challenge", return_value="answer")
    def test_submit_client_error(self, mock_solve, mock_submit):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError

        mock_submit.side_effect = MoltbookClientError("fail")
        agent = Agent()
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        result = agent._handle_verification({"text": "test", "id": "v1"})
        assert result is False
        agent._verification.record_failure.assert_called_once()


class TestEngageWithPost:
    def _make_agent(self, tmp_path=None):
        memory = _make_clean_memory(tmp_path) if tmp_path else None
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=memory)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._content = MagicMock()
        return agent

    def test_empty_post(self, tmp_path):
        agent = self._make_agent(tmp_path)
        assert agent._engage_with_post({"content": "", "id": "1"}) is False
        assert agent._engage_with_post({"content": "text", "id": ""}) is False

    def test_invalid_post_id(self, tmp_path):
        agent = self._make_agent(tmp_path)
        assert agent._engage_with_post({"content": "text", "id": "../etc"}) is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.3)
    def test_below_threshold(self, mock_score, tmp_path):
        agent = self._make_agent(tmp_path)
        result = agent._engage_with_post({"content": "text", "id": "post1"})
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_rate_limit_reached(self, mock_score, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._scheduler.can_comment.return_value = False
        result = agent._engage_with_post({"content": "text", "id": "post1"})
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_comment_generation_fails(self, mock_score, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = None
        result = agent._engage_with_post({"content": "text", "id": "post1"})
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_successful_comment(self, mock_score, mock_random, mock_time, tmp_path):
        mock_random.uniform.return_value = 60.0
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        resp_mock = MagicMock()
        agent._client.post.return_value = resp_mock

        result = agent._engage_with_post({"content": "text", "id": "post1"})
        assert result is True
        agent._client.post.assert_called_once_with(
            "/posts/post1/comments", json={"content": "Great insight"}
        )
        assert len(agent._actions_taken) == 1

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_comment_client_error(self, mock_score, tmp_path):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError

        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post.side_effect = MoltbookClientError("fail")

        result = agent._engage_with_post({"content": "text", "id": "post1"})
        assert result is False


class TestRunFeedCycle:
    def test_processes_posts(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._client.has_read_budget.return_value = True
        agent._client.get_following_feed.return_value = []
        agent._scheduler = MagicMock()
        fm = agent._feed_manager

        posts = [
            {"content": "post1", "id": "p1"},
            {"content": "post2", "id": "p2", "verification_challenge": {"text": "v", "id": "vc1"}},
        ]

        with patch.object(fm, "get_feed", return_value=posts), \
             patch.object(agent, "_handle_verification") as mock_verify, \
             patch.object(fm, "engage_with_post") as mock_engage:
            agent._run_feed_cycle(time.time() + 3600)

        mock_engage.assert_called_once()
        mock_verify.assert_called_once()

    def test_respects_end_time(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._client.has_read_budget.return_value = True
        agent._client.get_following_feed.return_value = []
        agent._scheduler = MagicMock()
        fm = agent._feed_manager

        with patch.object(fm, "get_feed", return_value=[{"content": "x", "id": "1"}]), \
             patch.object(fm, "engage_with_post") as mock_engage:
            agent._run_feed_cycle(time.time() - 1)

        mock_engage.assert_not_called()


class TestRunPostCycle:
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="test topic")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.check_topic_novelty", return_value=True)
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Test Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.extract_topics", return_value="topic1\ntopic2")
    def test_posts_dynamic(self, mock_topics, mock_title, mock_novelty, mock_summarize):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "Dynamic content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c"}]}
        post_resp = MagicMock()
        post_resp.json.return_value = {"id": "new-post-123"}
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        agent._client.post.assert_called_once()
        assert any("Posted: Test Title" in a for a in agent._actions_taken)

    def test_skips_when_cannot_post(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = False

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        agent._client.post.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.check_topic_novelty", return_value=True)
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.extract_topics", return_value="topics")
    def test_skips_none_content(self, mock_topics, mock_novelty):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = None

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c"}]}
        agent._client.get.return_value = feed_resp

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        agent._client.post.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.check_topic_novelty", return_value=True)
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.extract_topics", return_value="topics")
    def test_post_client_error(self, mock_topics, mock_title, mock_novelty):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError

        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c"}]}
        agent._client.get.return_value = feed_resp
        agent._client.post.side_effect = MoltbookClientError("fail")

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        # Should not raise


class TestRunSession:
    @patch("contemplative_agent.adapters.moltbook.agent.time")
    @patch("contemplative_agent.adapters.moltbook.agent.load_credentials", return_value="key")
    def test_session_ends_by_time(self, mock_creds, mock_time):
        # Simulate: end_time=160, first loop runs, then time passes end_time
        # Calls: end_time calc, while check, adaptive_wait clamp, while re-check
        mock_time.time.side_effect = [100.0, 100.0, 200.0, 200.0]

        agent = Agent(autonomy=AutonomyLevel.AUTO)

        with patch.object(agent, "_run_feed_cycle"), \
             patch.object(agent._post_pipeline, "run_cycle"), \
             patch.object(agent, "_print_report"):
            result = agent.run_session(duration_minutes=1)

        assert isinstance(result, list)

    @patch("contemplative_agent.adapters.moltbook.agent.load_credentials", return_value="key")
    def test_session_stops_on_verification_failure(self, mock_creds):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._verification = MagicMock()
        agent._verification.should_stop = True

        with patch.object(agent, "_ensure_client") as mock_ensure, \
             patch.object(agent, "_get_scheduler"), \
             patch.object(agent, "_print_report"):
            mock_ensure.return_value = MagicMock()
            result = agent.run_session(duration_minutes=1)

        assert isinstance(result, list)


class TestPrintReport:
    def test_print_report(self, capsys):
        agent = Agent()
        agent._ctx.actions_taken.extend(["Action 1", "Action 2"])
        agent._scheduler = MagicMock()
        agent._scheduler.comments_remaining_today = 48
        agent._content = MagicMock()
        agent._content.comment_to_post_ratio = 3.0

        agent._print_report()
        captured = capsys.readouterr()
        assert "Session Report" in captured.out
        assert "Actions taken: 2" in captured.out
        assert "Action 1" in captured.out

    def test_print_report_no_scheduler(self, capsys):
        agent = Agent()
        agent._ctx.actions_taken.clear()
        agent._content = MagicMock()
        agent._content.comment_to_post_ratio = 0.0

        agent._print_report()
        captured = capsys.readouterr()
        assert "Actions taken: 0" in captured.out


class TestExtractNotificationFields:
    """Tests for the fallback field extraction from notification dicts."""

    def test_standard_fields(self):
        notif = {
            "type": "reply",
            "id": "n1",
            "post_id": "p1",
            "content": "hello",
            "post_content": "original",
            "agent_id": "a1",
            "agent_name": "Alice",
        }
        fields = extract_notification_fields(notif)
        assert fields["type"] == "reply"
        assert fields["id"] == "n1"
        assert fields["post_id"] == "p1"
        assert fields["content"] == "hello"
        assert fields["post_content"] == "original"
        assert fields["agent_id"] == "a1"
        assert fields["agent_name"] == "Alice"

    def test_camel_case_fields(self):
        notif = {
            "kind": "comment",
            "notification_id": "n2",
            "postId": "p2",
            "body": "hi there",
            "postContent": "orig post",
            "agentId": "a2",
            "agentName": "Bob",
        }
        fields = extract_notification_fields(notif)
        assert fields["type"] == "comment"
        assert fields["id"] == "n2"
        assert fields["post_id"] == "p2"
        assert fields["content"] == "hi there"
        assert fields["post_content"] == "orig post"
        assert fields["agent_id"] == "a2"
        assert fields["agent_name"] == "Bob"

    def test_nested_author_fields(self):
        notif = {
            "event_type": "reply",
            "id": "n3",
            "target_id": "p3",
            "text": "nested test",
            "original_content": "orig",
            "author": {"id": "a3", "name": "Carol"},
        }
        fields = extract_notification_fields(notif)
        assert fields["type"] == "reply"
        assert fields["post_id"] == "p3"
        assert fields["content"] == "nested test"
        assert fields["post_content"] == "orig"
        assert fields["agent_id"] == "a3"
        assert fields["agent_name"] == "Carol"

    def test_nested_sender_fields(self):
        notif = {
            "type": "comment",
            "id": "n4",
            "post_id": "p4",
            "content": "sender test",
            "sender": {"id": "a4", "name": "Dave"},
        }
        fields = extract_notification_fields(notif)
        assert fields["agent_id"] == "a4"
        assert fields["agent_name"] == "Dave"

    def test_empty_notification(self):
        fields = extract_notification_fields({})
        assert fields["type"] == ""
        assert fields["id"] == ""
        assert fields["post_id"] == ""
        assert fields["content"] == ""
        assert fields["post_content"] == ""
        assert fields["agent_id"] == "unknown"
        assert fields["agent_name"] == "unknown"

    def test_standard_fields_take_priority(self):
        """Standard field names should win over fallback alternatives."""
        notif = {
            "type": "reply",
            "kind": "comment",
            "post_id": "standard",
            "postId": "camel",
            "content": "standard-content",
            "body": "fallback-content",
            "agent_id": "std-agent",
            "agentId": "camel-agent",
        }
        fields = extract_notification_fields(notif)
        assert fields["type"] == "reply"
        assert fields["post_id"] == "standard"
        assert fields["content"] == "standard-content"
        assert fields["agent_id"] == "std-agent"


class TestOwnPostIdTracking:
    """Tests that own post IDs are captured from do_introduce and _run_dynamic_post."""

    def test_introduce_captures_post_id(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._content = MagicMock()
        agent._content.get_introduction.return_value = "Hello world"

        resp_mock = MagicMock()
        resp_mock.json.return_value = {"id": "intro-post-1"}
        agent._client.post.return_value = resp_mock

        result = agent.do_introduce()
        assert result == "intro-post-1"
        assert "intro-post-1" in agent._own_post_ids

    def test_introduce_no_id_in_response(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._content = MagicMock()
        agent._content.get_introduction.return_value = "Hello world"

        resp_mock = MagicMock()
        resp_mock.json.return_value = {}
        agent._client.post.return_value = resp_mock

        result = agent.do_introduce()
        assert result is None
        assert len(agent._own_post_ids) == 0

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.check_topic_novelty", return_value=True)
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.extract_topics", return_value="topics")
    def test_dynamic_post_captures_post_id(self, mock_topics, mock_novelty, mock_title, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c"}]}
        post_resp = MagicMock()
        post_resp.json.return_value = {"id": "dyn-post-1"}
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp

        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)
        assert "dyn-post-1" in agent._own_post_ids

    def test_init_has_empty_own_post_ids(self):
        agent = Agent()
        assert agent._own_post_ids == set()


class TestRunReplyCycle:
    """Tests for the notification-based reply cycle."""

    def _make_agent(self, tmp_path=None):
        memory = _make_clean_memory(tmp_path) if tmp_path else None
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=memory)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        return agent

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="My reply")
    def test_processes_standard_notification(self, mock_reply, tmp_path):
        agent = self._make_agent(tmp_path)
        before_count = agent._memory.interaction_count()
        agent._client.get_notifications.return_value = [
            {
                "type": "comment",
                "id": "n1",
                "post_id": "p1",
                "content": "Nice post!",
                "post_content": "Original content",
                "agent_id": "a1",
                "agent_name": "Alice",
            }
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(agent._client, agent._scheduler, time.time() + 3600)

        agent._client.post.assert_called_once_with(
            "/posts/p1/comments", json={"content": "My reply"}
        )
        assert "Replied to Alice on p1" in agent._actions_taken
        # Both received + sent should be recorded
        assert agent._memory.interaction_count() - before_count == 2

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="My reply")
    def test_processes_camelcase_notification(self, mock_reply):
        agent = self._make_agent()
        agent._client.get_notifications.return_value = [
            {
                "kind": "reply",
                "notification_id": "n2",
                "postId": "p2",
                "body": "Interesting",
                "postContent": "Original",
                "author": {"id": "a2", "name": "Bob"},
            }
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(agent._client, agent._scheduler, time.time() + 3600)

        agent._client.post.assert_called_once_with(
            "/posts/p2/comments", json={"content": "My reply"}
        )
        assert "Replied to Bob on p2" in agent._actions_taken

    def test_skips_non_reply_notification(self):
        agent = self._make_agent()
        agent._client.get_notifications.return_value = [
            {"type": "like", "id": "n1", "post_id": "p1"}
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(agent._client, agent._scheduler, time.time() + 3600)

        agent._client.post.assert_not_called()

    def test_skips_empty_content(self):
        agent = self._make_agent()
        agent._client.get_notifications.return_value = [
            {
                "type": "comment",
                "id": "n1",
                "post_id": "p1",
                "content": "",
                "agent_id": "a1",
                "agent_name": "Alice",
            }
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(agent._client, agent._scheduler, time.time() + 3600)

        agent._client.post.assert_not_called()

    def test_skips_already_handled(self):
        agent = self._make_agent()
        agent._commented_posts.add("reply:p1:n1")
        agent._client.get_notifications.return_value = [
            {
                "type": "comment",
                "id": "n1",
                "post_id": "p1",
                "content": "Hello",
                "agent_id": "a1",
                "agent_name": "Alice",
            }
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(agent._client, agent._scheduler, time.time() + 3600)

        agent._client.post.assert_not_called()


class TestCheckOwnPostComments:
    """Tests for the fallback comment-polling mechanism."""

    def _make_agent(self, tmp_path=None):
        memory = _make_clean_memory(tmp_path) if tmp_path else None
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=memory)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        return agent

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="Thanks!")
    def test_replies_to_comment_on_own_post(self, mock_reply, tmp_path):
        agent = self._make_agent(tmp_path)
        before_count = agent._memory.interaction_count()
        agent._own_post_ids.add("my-post-1")
        agent._client.get_post_comments.return_value = [
            {
                "id": "c1",
                "content": "Great post!",
                "agent_id": "a1",
                "agent_name": "Alice",
            }
        ]

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() + 3600
        )

        agent._client.post.assert_called_once_with(
            "/posts/my-post-1/comments", json={"content": "Thanks!"}
        )
        assert "Replied to Alice on my-post-1" in agent._actions_taken
        assert agent._memory.interaction_count() - before_count == 2  # received + sent

    def test_skips_when_no_own_posts(self):
        agent = self._make_agent()
        assert len(agent._own_post_ids) == 0

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() + 3600
        )

        agent._client.get_post_comments.assert_not_called()

    def test_skips_already_replied_comment(self):
        agent = self._make_agent()
        agent._own_post_ids.add("my-post-1")
        agent._commented_posts.add("reply:my-post-1:c1")
        agent._client.get_post_comments.return_value = [
            {
                "id": "c1",
                "content": "Great post!",
                "agent_id": "a1",
                "agent_name": "Alice",
            }
        ]

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() + 3600
        )

        agent._client.post.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="Thanks!")
    def test_handles_nested_author_in_comments(self, mock_reply):
        agent = self._make_agent()
        agent._own_post_ids.add("my-post-1")
        agent._client.get_post_comments.return_value = [
            {
                "id": "c2",
                "body": "Insightful!",
                "author": {"id": "a2", "name": "Bob"},
            }
        ]

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() + 3600
        )

        agent._client.post.assert_called_once()
        assert "Replied to Bob on my-post-1" in agent._actions_taken

    def test_respects_end_time(self):
        agent = self._make_agent()
        agent._own_post_ids.add("my-post-1")

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() - 1
        )

        agent._client.get_post_comments.assert_not_called()

    def test_respects_rate_limit(self):
        agent = self._make_agent()
        agent._own_post_ids.add("my-post-1")
        agent._rate_limited = True

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() + 3600
        )

        agent._client.get_post_comments.assert_not_called()

    def test_respects_scheduler_can_comment(self):
        agent = self._make_agent()
        agent._own_post_ids.add("my-post-1")
        agent._scheduler.can_comment.return_value = False

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() + 3600
        )

        agent._client.get_post_comments.assert_not_called()


class TestSelectiveMode:
    """Tests for the selective engagement mode."""

    def test_relevance_threshold_in_range(self):
        """Relevance threshold should be a valid value from domain config."""
        from contemplative_agent.core.domain import get_domain_config
        config = get_domain_config()
        assert 0.0 < config.relevance_threshold <= 1.0

    def test_known_agent_threshold_lower(self):
        """Known agent threshold should be lower than relevance threshold."""
        from contemplative_agent.core.domain import get_domain_config
        config = get_domain_config()
        assert 0.0 < config.known_agent_threshold < config.relevance_threshold

    def test_feed_processes_all_posts(self):
        """Should process all posts from feed (no FEED_SCAN_LIMIT)."""
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._client.has_read_budget.return_value = True
        agent._client.get_following_feed.return_value = []
        agent._scheduler = MagicMock()
        fm = agent._feed_manager

        posts = [{"content": f"post{i}", "id": f"p{i}"} for i in range(20)]

        with patch.object(fm, "get_feed", return_value=posts), \
             patch.object(fm, "engage_with_post") as mock_engage:
            agent._run_feed_cycle(time.time() + 3600)

        assert mock_engage.call_count == 20

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.6)
    def test_relevance_below_new_threshold(self, mock_score, tmp_path):
        """Score 0.6 should be rejected (below threshold 0.82)."""
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._content = MagicMock()

        result = agent._engage_with_post({"content": "text", "id": "post1"})
        assert result is False
        agent._content.create_comment.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.9)
    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    def test_cross_session_dedup(self, mock_time, mock_score, tmp_path):
        """Should skip posts that were commented on in previous sessions."""
        mock_time.time.return_value = 1000.0
        mock_time.sleep = MagicMock()

        memory = _make_clean_memory(tmp_path)
        # Simulate a previous session's comment by seeding the cache
        memory._commented_cache = {"post1"}

        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=memory)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._content = MagicMock()

        result = agent._engage_with_post({"content": "text", "id": "post1"})
        assert result is False
        agent._client.post.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    def test_pacing_sleep_called(self, mock_time, mock_random, mock_score, tmp_path):
        """Should call time.sleep for pacing after successful comment."""
        mock_time.time.return_value = 1000.0
        mock_random.uniform.return_value = 120.0

        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._content = MagicMock()
        agent._content.create_comment.return_value = "Nice"

        agent._engage_with_post({"content": "text", "id": "post1"})
        mock_time.sleep.assert_called_once_with(120.0)


class TestEnsureSubscriptions:
    def test_subscribes_all_submolts(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        mock_client = MagicMock()
        mock_client.subscribe_submolt.return_value = True

        agent._ensure_subscriptions(mock_client)

        expected = agent._domain.subscribed_submolts
        assert mock_client.subscribe_submolt.call_count == len(expected)
        subscribed_names = [
            call[0][0] for call in mock_client.subscribe_submolt.call_args_list
        ]
        for name in expected:
            assert name in subscribed_names


class TestDynamicPostSubmolt:
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="topic")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.check_topic_novelty", return_value=True)
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.extract_topics", return_value="topics")
    def test_uses_selected_submolt(
        self, mock_topics, mock_novelty, mock_title, mock_summarize,
        mock_select, tmp_path,
    ):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "Post content"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "new-post-1"}
        agent._client.post.return_value = mock_resp

        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)

        # Verify the submolt in the post request
        call_kwargs = agent._client.post.call_args[1]
        assert call_kwargs["json"]["submolt"] == "philosophy"

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value=None)
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="topic")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.check_topic_novelty", return_value=True)
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.extract_topics", return_value="topics")
    def test_falls_back_to_default(
        self, mock_topics, mock_novelty, mock_title, mock_summarize,
        mock_select, tmp_path,
    ):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "Post content"

        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": "new-post-2"}
        agent._client.post.return_value = mock_resp

        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)

        call_kwargs = agent._client.post.call_args[1]
        assert call_kwargs["json"]["submolt"] == "alignment"


class TestGracefulShutdown:
    """Phase 1A: Signal handling and graceful shutdown."""

    def test_shutdown_flag_default_false(self, tmp_path):
        agent = Agent(memory=_make_clean_memory(tmp_path))
        assert agent._shutdown_requested is False

    @patch("contemplative_agent.adapters.moltbook.agent.load_credentials", return_value="key")
    @patch("contemplative_agent.adapters.moltbook.agent.MoltbookClient")
    @patch("contemplative_agent.adapters.moltbook.agent.Scheduler")
    def test_shutdown_flag_breaks_loop(self, mock_sched_cls, mock_client_cls, mock_creds, tmp_path):
        """Setting _shutdown_requested should cause run_session to exit the loop."""
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        mock_client = MagicMock()
        mock_client.subscribe_submolt.return_value = True
        mock_client.get_notifications.return_value = []
        mock_client.get.return_value = MagicMock(json=MagicMock(return_value={"posts": []}))
        mock_client.get_home.return_value = {"your_account": {"id": "me", "name": "bot"}}
        mock_client.get_following_feed.return_value = []
        mock_client.search.return_value = []
        mock_client.recent_429_count = 0
        mock_client.rate_limit_remaining = None
        mock_client.has_budget.return_value = True
        mock_client.has_read_budget.return_value = True
        mock_client.has_write_budget.return_value = True
        mock_client_cls.return_value = mock_client

        mock_sched = MagicMock()
        mock_sched.can_comment.return_value = False
        mock_sched.can_post.return_value = False
        mock_sched.seconds_until_comment.return_value = 0
        mock_sched.seconds_until_post.return_value = 0
        mock_sched_cls.return_value = mock_sched

        # Set shutdown after first cycle
        original_time = time.time
        call_count = [0]

        def fake_time():
            call_count[0] += 1
            if call_count[0] > 3:
                agent._shutdown_requested = True
            return original_time()

        with patch("contemplative_agent.adapters.moltbook.agent.time") as mock_time:
            mock_time.time = fake_time
            mock_time.sleep = MagicMock()
            actions = agent.run_session(duration_minutes=60)

        # Session should complete (memory saved)
        assert isinstance(actions, list)

    def test_shutdown_flag_saves_memory(self, tmp_path):
        """Shutdown should trigger memory.save()."""
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._shutdown_requested = True
        agent._client = MagicMock()
        agent._client.subscribe_submolt.return_value = True
        agent._client.get_home.return_value = {"your_account": {"id": "me", "name": "bot"}}
        agent._client.recent_429_count = 0
        agent._client.rate_limit_remaining = None
        agent._client.has_budget.return_value = True
        agent._client.has_read_budget.return_value = True
        agent._client.has_write_budget.return_value = True
        agent._scheduler = MagicMock()
        agent._scheduler.seconds_until_comment.return_value = 0
        agent._scheduler.seconds_until_post.return_value = 0

        with patch.object(agent._memory, "save") as mock_save:
            agent.run_session(duration_minutes=1)
            mock_save.assert_called_once()


class TestExtractAgentFields:
    """Phase 4A: Shared field extraction helper."""

    def test_basic_fields(self):
        data = {"id": "c1", "content": "hello", "agent_id": "a1", "agent_name": "Bot"}
        result = extract_agent_fields(data)
        assert result["id"] == "c1"
        assert result["content"] == "hello"
        assert result["agent_id"] == "a1"
        assert result["agent_name"] == "Bot"

    def test_fallback_fields(self):
        data = {"comment_id": "c2", "body": "hi", "agentId": "a2", "agentName": "Bot2"}
        result = extract_agent_fields(data)
        assert result["id"] == "c2"
        assert result["content"] == "hi"
        assert result["agent_id"] == "a2"
        assert result["agent_name"] == "Bot2"

    def test_nested_author(self):
        data = {"author": {"id": "a3", "name": "Bot3"}, "text": "yo"}
        result = extract_agent_fields(data)
        assert result["agent_id"] == "a3"
        assert result["agent_name"] == "Bot3"
        assert result["content"] == "yo"

    def test_empty_data_defaults(self):
        result = extract_agent_fields({})
        assert result["id"] == ""
        assert result["content"] == ""
        assert result["agent_id"] == "unknown"
        assert result["agent_name"] == "unknown"

    def test_notification_fields_include_agent_fields(self):
        notif = {
            "type": "reply", "post_id": "p1", "content": "hello",
            "agent_id": "a1", "agent_name": "Bot",
        }
        result = extract_notification_fields(notif)
        assert result["type"] == "reply"
        assert result["post_id"] == "p1"
        assert result["agent_id"] == "a1"
        assert result["content"] == "hello"


class TestFetchHomeData:
    """Tests for _fetch_home_data and _fetch_own_agent_id_fallback."""

    def test_home_extracts_agent_id(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        mock_client = MagicMock()
        mock_client.get_home.return_value = {
            "your_account": {"id": "agent-123", "name": "bot"},
            "activity_on_your_posts": [],
        }

        agent._fetch_home_data(mock_client)
        assert agent._own_agent_id == "agent-123"
        assert agent._home_data["your_account"]["name"] == "bot"

    def test_home_empty_falls_back_to_agents_me(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        mock_client = MagicMock()
        mock_client.get_home.return_value = {}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agent": {"id": "fallback-456", "name": "bot"}}
        mock_client.get.return_value = mock_resp

        agent._fetch_home_data(mock_client)
        assert agent._own_agent_id == "fallback-456"

    def test_fallback_error_leaves_id_empty(self, tmp_path):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError as MCE
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        mock_client = MagicMock()
        mock_client.get_home.return_value = {}
        mock_client.get.side_effect = MCE("Network error")

        agent._fetch_home_data(mock_client)
        assert agent._own_agent_id == ""

    def test_fallback_401_logs_critical(self, tmp_path):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError as MCE
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        mock_client = MagicMock()
        mock_client.get_home.return_value = {}
        exc = MCE("Unauthorized", status_code=401)
        mock_client.get.side_effect = exc

        with patch("contemplative_agent.adapters.moltbook.agent.logger") as mock_logger:
            agent._fetch_home_data(mock_client)
            mock_logger.critical.assert_called_once()
            assert "revoked" in mock_logger.critical.call_args[0][0].lower() or \
                   "compromised" in mock_logger.critical.call_args[0][0].lower()

    def test_home_stores_activity_data(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        mock_client = MagicMock()
        activity = [{"post_id": "p1", "new_notification_count": 3}]
        mock_client.get_home.return_value = {
            "your_account": {"id": "a1", "name": "bot"},
            "activity_on_your_posts": activity,
        }

        agent._fetch_home_data(mock_client)
        assert agent._home_data["activity_on_your_posts"] == activity


class TestRunCycleFromHome:
    """Tests for ReplyHandler.run_cycle_from_home()."""

    def _make_agent_and_handler(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._own_agent_id = "me-123"
        return agent, agent._reply_handler

    def test_skips_items_with_zero_notification_count(self, tmp_path):
        agent, handler = self._make_agent_and_handler(tmp_path)
        mock_client = MagicMock()
        mock_client.has_write_budget.return_value = True
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True

        home_data = {
            "activity_on_your_posts": [
                {"post_id": "p1", "new_notification_count": 0},
            ],
        }
        handler.run_cycle_from_home(
            mock_client, scheduler, time.time() + 60, home_data,
        )
        mock_client.get_post_comments.assert_not_called()

    def test_processes_items_with_new_notifications(self, tmp_path):
        agent, handler = self._make_agent_and_handler(tmp_path)
        mock_client = MagicMock()
        mock_client.has_write_budget.return_value = True
        mock_client.get_post_comments.return_value = []
        mock_client.mark_notifications_read_by_post.return_value = True
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True

        home_data = {
            "activity_on_your_posts": [
                {"post_id": "valid-post-1", "new_notification_count": 3},
            ],
        }
        handler.run_cycle_from_home(
            mock_client, scheduler, time.time() + 60, home_data,
        )
        mock_client.get_post_comments.assert_called_once_with("valid-post-1")
        mock_client.mark_notifications_read_by_post.assert_called_once_with("valid-post-1")

    def test_invalid_post_id_is_skipped(self, tmp_path):
        agent, handler = self._make_agent_and_handler(tmp_path)
        mock_client = MagicMock()
        mock_client.has_write_budget.return_value = True
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True

        home_data = {
            "activity_on_your_posts": [
                {"post_id": "../hack", "new_notification_count": 5},
            ],
        }
        handler.run_cycle_from_home(
            mock_client, scheduler, time.time() + 60, home_data,
        )
        mock_client.get_post_comments.assert_not_called()

    def test_marks_notifications_read_after_processing(self, tmp_path):
        agent, handler = self._make_agent_and_handler(tmp_path)
        mock_client = MagicMock()
        mock_client.has_write_budget.return_value = True
        mock_client.get_post_comments.return_value = []
        mock_client.mark_notifications_read_by_post.return_value = True
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True

        home_data = {
            "activity_on_your_posts": [
                {"post_id": "p1", "new_notification_count": 2},
                {"post_id": "p2", "new_notification_count": 1},
            ],
        }
        handler.run_cycle_from_home(
            mock_client, scheduler, time.time() + 60, home_data,
        )
        assert mock_client.mark_notifications_read_by_post.call_count == 2

    def test_respects_end_time(self, tmp_path):
        agent, handler = self._make_agent_and_handler(tmp_path)
        mock_client = MagicMock()
        mock_client.has_write_budget.return_value = True
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True

        home_data = {
            "activity_on_your_posts": [
                {"post_id": "p1", "new_notification_count": 5},
            ],
        }
        # end_time in the past
        handler.run_cycle_from_home(
            mock_client, scheduler, time.time() - 10, home_data,
        )
        mock_client.get_post_comments.assert_not_called()

    def test_respects_write_budget(self, tmp_path):
        agent, handler = self._make_agent_and_handler(tmp_path)
        mock_client = MagicMock()
        mock_client.has_write_budget.return_value = False
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True

        home_data = {
            "activity_on_your_posts": [
                {"post_id": "p1", "new_notification_count": 3},
            ],
        }
        handler.run_cycle_from_home(
            mock_client, scheduler, time.time() + 60, home_data,
        )
        mock_client.get_post_comments.assert_not_called()

    def test_empty_activity_is_noop(self, tmp_path):
        agent, handler = self._make_agent_and_handler(tmp_path)
        mock_client = MagicMock()
        scheduler = MagicMock()

        handler.run_cycle_from_home(
            mock_client, scheduler, time.time() + 60, {},
        )
        mock_client.get_post_comments.assert_not_called()


class TestSelfPostSkip:
    """Skips posts authored by the agent itself."""

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_skips_own_post(self, mock_score, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._own_agent_id = "my-agent-id"

        post = {
            "content": "Some post",
            "id": "post1",
            "author": {"id": "my-agent-id", "name": "self"},
        }
        result = agent._engage_with_post(post)
        assert result is False
        mock_score.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_allows_other_agent_post(self, mock_score, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._content = MagicMock()
        agent._content.create_comment.return_value = None
        agent._own_agent_id = "my-agent-id"

        post = {
            "content": "Some post",
            "id": "post1",
            "author": {"id": "other-agent", "name": "other"},
        }
        agent._engage_with_post(post)
        mock_score.assert_called_once()


class TestSubmoltFilter:
    """Skips posts from non-subscribed submolts."""

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_skips_unsubscribed_submolt(self, mock_score, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True

        post = {
            "content": "Some post",
            "id": "post1",
            "submolt_name": "unsubscribed-submolt",
        }
        result = agent._engage_with_post(post)
        assert result is False
        mock_score.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_allows_post_without_submolt(self, mock_score, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._content = MagicMock()
        agent._content.create_comment.return_value = None

        post = {"content": "Some post", "id": "post1"}
        agent._engage_with_post(post)
        mock_score.assert_called_once()


class TestSelfReplySkip:
    """Skips own comments in notification reply cycle."""

    def _make_agent(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._own_agent_id = "my-agent-id"
        return agent

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="Thanks!")
    def test_skips_own_notification(self, mock_reply, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._client.get_notifications.return_value = [
            {
                "type": "reply",
                "post_id": "p1",
                "id": "n1",
                "content": "Hello",
                "agent_id": "my-agent-id",
                "agent_name": "self",
            }
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(
            agent._client, agent._scheduler, time.time() + 3600
        )
        mock_reply.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="Thanks!")
    def test_skips_own_comment_in_handle_post_comments(self, mock_reply, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._client.get_post_comments.return_value = [
            {
                "id": "c1",
                "content": "My own comment",
                "agent_id": "my-agent-id",
                "agent_name": "self",
            }
        ]

        agent._reply_handler._handle_post_comments(
            agent._client, agent._scheduler, "post1", time.time() + 3600
        )
        mock_reply.assert_not_called()


class TestNotificationRelatedPostId:
    """Tests relatedPostId fallback in _extract_notification_fields."""

    def test_related_post_id_fallback(self):
        notif = {
            "type": "mention",
            "relatedPostId": "related-1",
            "content": "hey",
            "agent_id": "a1",
            "agent_name": "Bot",
        }
        fields = extract_notification_fields(notif)
        assert fields["post_id"] == "related-1"


class TestFeedCache:
    """Phase 3A: Feed caching to avoid double-fetch."""

    def test_get_feed_caches(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"posts": [{"id": "p1"}]}
        agent._client.get.return_value = mock_resp

        # First call fetches from all subscribed submolt feeds
        result1 = agent._get_feed()
        assert len(result1) >= 1
        first_call_count = agent._client.get.call_count

        # Second call within max_age returns cached (no new API calls)
        result2 = agent._get_feed()
        assert result2 is result1
        assert agent._client.get.call_count == first_call_count

    def test_get_feed_expires(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"posts": [{"id": "p1"}]}
        agent._client.get.return_value = mock_resp

        agent._get_feed()
        first_call_count = agent._client.get.call_count
        # Simulate cache expiry
        agent._feed_manager._feed_fetched_at = 0.0
        agent._get_feed()
        # Should have fetched again (doubled the call count)
        assert agent._client.get.call_count == first_call_count * 2


class TestAdaptiveCycleWait:
    """Tests for _adaptive_cycle_wait backoff/decay logic."""

    def _make_agent_with_client(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        mock_client = MagicMock()
        mock_client.recent_429_count = 0
        mock_client.rate_limit_remaining = None
        mock_client.rate_limit_reset = None
        mock_client.has_budget.return_value = True
        agent._client = mock_client
        return agent

    def test_clean_cycle_returns_base_wait(self):
        agent = self._make_agent_with_client()
        wait = agent._adaptive_cycle_wait()
        assert wait == 60.0

    def test_429_triggers_backoff(self):
        agent = self._make_agent_with_client()
        agent._client.recent_429_count = 2
        wait = agent._adaptive_cycle_wait()
        assert wait == 120.0  # 60 * 2.0

    def test_consecutive_429_doubles_again(self):
        agent = self._make_agent_with_client()
        agent._client.recent_429_count = 1
        agent._adaptive_cycle_wait()  # 60 -> 120

        agent._client.recent_429_count = 1
        wait = agent._adaptive_cycle_wait()
        assert wait == 240.0  # 120 * 2.0

    def test_backoff_caps_at_max(self):
        agent = self._make_agent_with_client()
        agent._cycle_wait = 400.0
        agent._client.recent_429_count = 1
        wait = agent._adaptive_cycle_wait()
        assert wait == 600.0  # max_cycle_wait

    def test_clean_cycle_decays_after_backoff(self):
        agent = self._make_agent_with_client()
        agent._cycle_wait = 240.0
        agent._consecutive_429_cycles = 2
        # Clean cycle
        agent._client.recent_429_count = 0
        wait = agent._adaptive_cycle_wait()
        assert wait == 120.0  # 240 * 0.5

    def test_decay_floors_at_base(self):
        agent = self._make_agent_with_client()
        agent._cycle_wait = 60.0
        agent._client.recent_429_count = 0
        wait = agent._adaptive_cycle_wait()
        assert wait == 60.0  # Can't go below base

    @patch("contemplative_agent.adapters.moltbook.agent.time")
    def test_proactive_wait_on_low_remaining(self, mock_time):
        mock_time.time.return_value = 1000.0
        agent = self._make_agent_with_client()
        agent._client.recent_429_count = 0
        agent._client.rate_limit_remaining = 5  # Below threshold of 10
        agent._client.rate_limit_reset = 1080.0  # 80s from now
        wait = agent._adaptive_cycle_wait()
        assert wait == 80.0  # Reset is 80s away

    def test_proactive_wait_default_when_no_reset_time(self):
        agent = self._make_agent_with_client()
        agent._client.recent_429_count = 0
        agent._client.rate_limit_remaining = 3
        agent._client.rate_limit_reset = None
        wait = agent._adaptive_cycle_wait()
        assert wait == 120.0  # proactive_wait_seconds default

    def test_resets_429_counter_after_check(self):
        agent = self._make_agent_with_client()
        agent._client.recent_429_count = 3
        agent._adaptive_cycle_wait()
        agent._client.reset_429_count.assert_called_once()
