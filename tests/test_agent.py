# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false, reportArgumentType=false
"""Tests for the Agent orchestrator."""

import time
from itertools import chain, repeat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook.client import (
    MoltbookClientError,
)
from contemplative_agent.adapters.moltbook.agent import Agent, AutonomyLevel
from contemplative_agent.adapters.moltbook.reply_handler import (
    extract_agent_fields,
    extract_notification_fields,
)
from contemplative_agent.adapters.moltbook.verification import VerificationSolveResult
from contemplative_agent.core.config import VALID_ID_PATTERN
from contemplative_agent.core.memory import MemoryStore


def _make_clean_memory(tmp_path: Path) -> MemoryStore:
    """Create a MemoryStore with temporary paths (no live data)."""
    return MemoryStore(path=tmp_path / "memory.json")


def _solve_result(answer: str | None = "15.00") -> VerificationSolveResult:
    return VerificationSolveResult(
        answer=answer,
        solver_path="llm_reason" if answer is not None else "none",
        challenge_sha256="challenge-sha",
    )


class TestAutoFollow:
    """Tests for _auto_follow self-exclusion and churn hysteresis."""

    @staticmethod
    def _make_agent(tmp_path, top_agents, followed=(), own_id="self"):
        """Build an Agent with a stubbed ranking.

        top_agents: list of (id, name) in rank order, highest first.
        The stubbed get_top_interacted_agents honors exclude_ids and limit
        exactly like the real implementation, so passing own_id is verified.
        AUTO: follow/unfollow now route through the side-effect gate
        (audit H1) and the default APPROVE would prompt interactively.
        """
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        mem = _make_clean_memory(tmp_path)
        for name in followed:
            mem.record_follow(name)

        def fake_top(limit=20, exclude_ids=None):
            excluded = set(exclude_ids or ())
            ranked = [(aid, aname) for aid, aname in top_agents if aid not in excluded]
            return ranked[:limit]

        # Full method replacement (not autospec) is intentional: fake_top
        # reproduces the real exclude_ids/limit contract so the test verifies
        # _auto_follow passes own_id and slices ranks correctly.
        mem.get_top_interacted_agents = fake_top  # type: ignore[method-assign]
        agent._memory = mem
        agent._ctx.memory = mem
        agent._ctx.own_agent_id = own_id
        return agent

    def test_auto_follow_skips_self(self, tmp_path):
        top = [("self", "contemplative-agent"), ("a1", "Alice"), ("a2", "Carol")]
        agent = self._make_agent(tmp_path, top, followed=[], own_id="self")
        client = MagicMock()
        client.follow_agent.return_value = True
        agent._auto_follow(client)
        followed_names = [c.args[0] for c in client.follow_agent.call_args_list]
        assert "contemplative-agent" not in followed_names
        assert "contemplative-agent" not in agent._memory.get_followed_agents()
        assert "Alice" in followed_names

    def test_enters_top20_follows(self, tmp_path):
        top = [(f"id{i}", f"Peer{i}") for i in range(30)]
        agent = self._make_agent(tmp_path, top, followed=[])
        client = MagicMock()
        client.follow_agent.return_value = True
        agent._auto_follow(client)
        followed = [c.args[0] for c in client.follow_agent.call_args_list]
        assert "Peer0" in followed  # rank 1 is a clear top-20 entrant

    def test_grey_zone_agent_not_unfollowed(self, tmp_path):
        # Peer24 (rank 25) sits in the grey zone (21-30) and must be kept.
        top = [(f"id{i}", f"Peer{i}") for i in range(30)]
        agent = self._make_agent(tmp_path, top, followed=["Peer24"])
        client = MagicMock()
        client.follow_agent.return_value = True
        client.unfollow_agent.return_value = True
        agent._auto_follow(client)
        unfollowed = [c.args[0] for c in client.unfollow_agent.call_args_list]
        assert "Peer24" not in unfollowed

    def test_falls_past_keep_rank_unfollows(self, tmp_path):
        # A followed agent absent from the top-30 (fell past KEEP_RANK).
        top = [(f"id{i}", f"Peer{i}") for i in range(30)]
        agent = self._make_agent(tmp_path, top, followed=["GoneAgent"])
        client = MagicMock()
        client.unfollow_agent.return_value = True
        client.follow_agent.return_value = True
        agent._auto_follow(client)
        unfollowed = [c.args[0] for c in client.unfollow_agent.call_args_list]
        assert "GoneAgent" in unfollowed

    def test_grey_zone_newcomer_not_followed(self, tmp_path):
        # All top-20 already followed; grey-zone (21-30) agents must not be
        # newly followed, and nothing in the keep zone is unfollowed.
        top = [(f"id{i}", f"Peer{i}") for i in range(30)]
        followed = [f"Peer{i}" for i in range(20)]
        agent = self._make_agent(tmp_path, top, followed=followed)
        client = MagicMock()
        client.follow_agent.return_value = True
        client.unfollow_agent.return_value = True
        agent._auto_follow(client)
        followed_calls = [c.args[0] for c in client.follow_agent.call_args_list]
        assert all(f"Peer{i}" not in followed_calls for i in range(20, 30))
        assert client.unfollow_agent.call_count == 0

    def test_no_churn_when_followed_set_stable(self, tmp_path):
        # followed == top-30 set. Old single-threshold logic would unfollow
        # ranks 21-30 every session; hysteresis keeps all → zero API churn.
        top = [(f"id{i}", f"Peer{i}") for i in range(30)]
        followed = [f"Peer{i}" for i in range(30)]
        agent = self._make_agent(tmp_path, top, followed=followed)
        client = MagicMock()
        client.follow_agent.return_value = True
        client.unfollow_agent.return_value = True
        agent._auto_follow(client)
        assert client.follow_agent.call_count == 0
        assert client.unfollow_agent.call_count == 0

    def test_max_changes_per_session_respected(self, tmp_path):
        # 30 ranked, none followed → many top-20 candidates, capped at 3.
        top = [(f"id{i}", f"Peer{i}") for i in range(30)]
        agent = self._make_agent(tmp_path, top, followed=[])
        client = MagicMock()
        client.follow_agent.return_value = True
        agent._auto_follow(client)
        assert client.follow_agent.call_count == 3


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
        assert agent._ctx.actions_taken == []


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

    def test_no_length_check(self):
        """ADR-0018 amendment: length enforcement moved to _sanitize_output();
        _passes_content_filter() no longer duplicates the cap (ADR-0030: 1 artifact 1 責務)."""
        assert Agent._passes_content_filter("x" * 50000) is True
        assert Agent._passes_content_filter("x" * 100000) is True

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

    def test_guarded_rejects_forbidden_in_title(self):
        # Batch F regression (ultracode sweep 2026-06-23): the post title is
        # the agent's own LLM output and must pass the GUARDED filter too.
        # Previously a forbidden pattern in the title bypassed the gate because
        # only `content` was filtered.
        agent = Agent(autonomy=AutonomyLevel.GUARDED)
        assert agent._confirm_action(
            "Dynamic Post: my api_key leak", "totally safe body text",
            title="my api_key leak",
        ) is False

    def test_guarded_passes_clean_title(self):
        agent = Agent(autonomy=AutonomyLevel.GUARDED)
        assert agent._confirm_action(
            "Dynamic Post: A reflection on patience",
            "safe body", title="A reflection on patience",
        ) is True

    # ADR-0018 amendment 2026-05-04: length enforcement moved to
    # _sanitize_output(); the redundant check in _passes_content_filter is
    # removed (ADR-0030: 1 artifact 1 責務). The corresponding length-only
    # rejection test is therefore deleted — see test_no_length_check above.

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


class TestConfirmSideEffect:
    """Audit H1: contentless external side effects (upvote / follow /
    unfollow / subscribe / mark-read) route through _confirm_side_effect.
    APPROVE confirms every external write; GUARDED deliberately
    default-allows (its content filter has nothing to inspect — pre-fix
    behavior preserved); AUTO passes everything through."""

    def test_auto_allows(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        assert agent._confirm_side_effect("Upvote post p1") is True

    def test_guarded_default_allows(self):
        agent = Agent(autonomy=AutonomyLevel.GUARDED)
        assert agent._confirm_side_effect("Upvote post p1") is True

    @patch("builtins.input", return_value="y")
    def test_approve_yes(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        assert agent._confirm_side_effect("Follow agent Alice") is True
        mock_input.assert_called_once()

    @patch("builtins.input", return_value="n")
    def test_approve_no(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        assert agent._confirm_side_effect("Follow agent Alice") is False

    @patch("builtins.input", return_value="")
    def test_approve_empty_is_no(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        assert agent._confirm_side_effect("Follow agent Alice") is False

    @patch("builtins.input", side_effect=EOFError)
    def test_approve_non_tty_rejects(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        assert agent._confirm_side_effect("Follow agent Alice") is False


class TestSideEffectGateWiring:
    """Audit H1: all six contentless call sites route through the gate —
    rejection blocks the client call entirely."""

    @patch("builtins.input", return_value="n")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance",
        return_value=0.95,
    )
    def test_feed_upvote_rejected(self, mock_score, mock_input, tmp_path):
        agent = Agent(
            autonomy=AutonomyLevel.APPROVE, memory=_make_clean_memory(tmp_path)
        )
        agent._client = MagicMock()
        # Explicit True: the gate sits after has_write_budget in the
        # and-chain; don't rely on MagicMock truthiness to reach it.
        agent._client.has_write_budget.return_value = True
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._content = MagicMock()
        agent._content.create_comment.return_value = "Great"

        agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
        agent._client.upvote_post.assert_not_called()

    @patch("builtins.input", return_value="n")
    def test_follow_rejected(self, mock_input, tmp_path):
        mem = _make_clean_memory(tmp_path)
        mem.get_top_interacted_agents = (  # type: ignore[method-assign]
            lambda limit=20, exclude_ids=None: [("a1", "Alice")]
        )
        agent = Agent(autonomy=AutonomyLevel.APPROVE, memory=mem)
        client = MagicMock()

        agent._auto_follow(client)
        client.follow_agent.assert_not_called()

    @patch("builtins.input", return_value="n")
    def test_unfollow_rejected(self, mock_input, tmp_path):
        mem = _make_clean_memory(tmp_path)
        mem.record_follow("Bob")
        mem.get_top_interacted_agents = (  # type: ignore[method-assign]
            lambda limit=20, exclude_ids=None: []
        )
        agent = Agent(autonomy=AutonomyLevel.APPROVE, memory=mem)
        client = MagicMock()

        agent._auto_follow(client)
        client.unfollow_agent.assert_not_called()

    @patch("builtins.input", side_effect=["n", "n", "y"])
    def test_rejection_does_not_consume_follow_budget(
        self, mock_input, tmp_path
    ):
        """Rejected candidates must not count toward
        MAX_CHANGES_PER_SESSION — the approval is checked before the
        counter increments."""
        mem = _make_clean_memory(tmp_path)
        mem.get_top_interacted_agents = (  # type: ignore[method-assign]
            lambda limit=20, exclude_ids=None: [
                ("a1", "Alice"), ("a2", "Bob"), ("a3", "Carol"),
            ]
        )
        agent = Agent(autonomy=AutonomyLevel.APPROVE, memory=mem)
        client = MagicMock()
        client.follow_agent.return_value = True

        agent._auto_follow(client)
        # First two rejected, third approved → exactly one follow.
        client.follow_agent.assert_called_once_with("Carol")

    @patch("builtins.input", return_value="n")
    def test_subscribe_rejected(self, mock_input):
        agent = Agent(autonomy=AutonomyLevel.APPROVE)
        client = MagicMock()

        agent._ensure_subscriptions(client)
        client.subscribe_submolt.assert_not_called()

    def test_courtesy_upvote_rejected(self, tmp_path):
        """ReplyHandler-level: a rejecting gate blocks the courtesy upvote
        while the reply itself (own content gate) still goes out."""
        agent = Agent(
            autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path)
        )
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._reply_handler._confirm_side_effect = MagicMock(
            return_value=False
        )
        agent._ctx.own_post_ids.add("my-post-1")
        agent._client.get_post_comments.return_value = [
            {
                "id": "c1",
                "content": "Great post!",
                "agent_id": "a1",
                "agent_name": "Alice",
            }
        ]
        with patch(
            "contemplative_agent.adapters.moltbook.reply_handler.generate_reply",
            return_value="Thanks!",
        ):
            agent._reply_handler.check_own_post_comments(
                agent._client, agent._scheduler, time.time() + 3600
            )
        agent._client.post_comment.assert_called_once()
        agent._client.upvote_comment.assert_not_called()

    def test_mark_read_rejected(self, tmp_path):
        agent = Agent(
            autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path)
        )
        agent._reply_handler._confirm_side_effect = MagicMock(
            return_value=False
        )
        mock_client = MagicMock()
        mock_client.has_write_budget.return_value = True
        mock_client.get_post_comments.return_value = []
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True

        home_data = {
            "activity_on_your_posts": [
                {"post_id": "valid-post-1", "new_notification_count": 3},
            ],
        }
        agent._reply_handler.run_cycle_from_home(
            mock_client, scheduler, time.time() + 60, home_data,
        )
        mock_client.mark_notifications_read_by_post.assert_not_called()


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

        result = agent._handle_verification(
            {"challenge_text": "test", "verification_code": "moltbook_verify_v1"}
        )
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.agent.record_verification_audit")
    @patch(
        "contemplative_agent.adapters.moltbook.agent.solve_challenge_result",
        return_value=_solve_result(None),
    )
    def test_solve_fails(self, mock_solve, mock_audit):
        agent = Agent()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        result = agent._handle_verification(
            {"challenge_text": "test", "verification_code": "moltbook_verify_v1"}
        )
        assert result is False
        agent._verification.record_failure.assert_called_once()
        mock_audit.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.agent.submit_verification")
    @patch("contemplative_agent.adapters.moltbook.agent.record_verification_audit")
    @patch(
        "contemplative_agent.adapters.moltbook.agent.solve_challenge_result",
        return_value=_solve_result("answer"),
    )
    def test_submit_success(self, mock_solve, mock_audit, mock_submit):
        mock_submit.return_value = {"success": True}
        agent = Agent()
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        result = agent._handle_verification(
            {"challenge_text": "test", "verification_code": "moltbook_verify_v1"}
        )
        assert result is True
        agent._verification.record_success.assert_called_once()
        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["verify_success"] is True

    @patch("contemplative_agent.adapters.moltbook.agent.submit_verification")
    @patch("contemplative_agent.adapters.moltbook.agent.record_verification_audit")
    @patch(
        "contemplative_agent.adapters.moltbook.agent.solve_challenge_result",
        return_value=_solve_result("answer"),
    )
    def test_submit_failure(self, mock_solve, mock_audit, mock_submit):
        mock_submit.return_value = {"success": False}
        agent = Agent()
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        result = agent._handle_verification(
            {"challenge_text": "test", "verification_code": "moltbook_verify_v1"}
        )
        assert result is False
        agent._verification.record_failure.assert_called_once()
        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["verify_success"] is False

    @patch("contemplative_agent.adapters.moltbook.agent.submit_verification")
    @patch("contemplative_agent.adapters.moltbook.agent.record_verification_audit")
    @patch(
        "contemplative_agent.adapters.moltbook.agent.solve_challenge_result",
        return_value=_solve_result("answer"),
    )
    def test_submit_client_error(self, mock_solve, mock_audit, mock_submit):
        mock_submit.side_effect = MoltbookClientError("fail")
        agent = Agent()
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        result = agent._handle_verification(
            {"challenge_text": "test", "verification_code": "moltbook_verify_v1"}
        )
        assert result is False
        agent._verification.record_failure.assert_called_once()
        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["verify_success"] is False

    def test_missing_fields_records_failure(self):
        agent = Agent()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        # An envelope lacking challenge_text/verification_code (e.g. a future
        # API rename) fails closed rather than submitting garbage.
        result = agent._handle_verification({"foo": "bar"})
        assert result is False
        agent._verification.record_failure.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.agent.submit_verification")
    @patch(
        "contemplative_agent.adapters.moltbook.agent.record_verification_audit",
    )
    @patch(
        "contemplative_agent.adapters.moltbook.agent.solve_challenge_result",
        return_value=_solve_result("15.00"),
    )
    def test_submit_called_with_verification_code(self, mock_solve, mock_audit, mock_submit):
        mock_submit.return_value = {"success": True}
        agent = Agent()
        agent._client = MagicMock()
        agent._verification = MagicMock()
        agent._verification.should_stop = False

        agent._handle_verification(
            {"challenge_text": "noise", "verification_code": "moltbook_verify_v1"}
        )
        # Current API keys submission on verification_code, not a challenge id.
        args, _ = mock_submit.call_args
        assert args[1] == "moltbook_verify_v1"
        assert args[2] == "15.00"


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
        assert agent._feed_manager.engage_with_post({"content": "", "id": "1"}, agent._client, agent._scheduler) is False
        assert agent._feed_manager.engage_with_post({"content": "text", "id": ""}, agent._client, agent._scheduler) is False

    def test_invalid_post_id(self, tmp_path):
        agent = self._make_agent(tmp_path)
        assert agent._feed_manager.engage_with_post({"content": "text", "id": "../etc"}, agent._client, agent._scheduler) is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.3)
    def test_below_threshold(self, mock_score, tmp_path):
        agent = self._make_agent(tmp_path)
        result = agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_rate_limit_reached(self, mock_score, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._scheduler.can_comment.return_value = False
        result = agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_comment_generation_fails(self, mock_score, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = None
        result = agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_successful_comment(self, mock_score, mock_random, mock_time, tmp_path):
        mock_random.uniform.return_value = 60.0
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {"id": "c-new"}

        result = agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
        assert result is True
        agent._client.post_comment.assert_called_once_with(
            "post1", "Great insight"
        )
        assert len(agent._ctx.actions_taken) == 1

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_comment_verification_success_records(
        self, mock_score, mock_random, mock_time, tmp_path
    ):
        """A comment whose create-response carries a verification object is
        recorded only after the handshake succeeds."""
        mock_random.uniform.return_value = 60.0
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {
            "id": "c-new",
            "verification": {
                "verification_code": "moltbook_verify_x",
                "challenge_text": "noise",
            },
        }
        # Replace the stored callback (feed_manager captured the bound method at
        # construction, so patching agent._handle_verification would not take).
        verify = MagicMock(return_value=True)
        agent._feed_manager._handle_verification = verify

        result = agent._feed_manager.engage_with_post(
            {"content": "text", "id": "post1"}, agent._client, agent._scheduler
        )
        assert result is True
        verify.assert_called_once_with(
            {"verification_code": "moltbook_verify_x", "challenge_text": "noise"}
        )
        assert agent._ctx.memory.has_commented_on("post1")
        agent._scheduler.record_comment.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_comment_verification_failure_not_recorded(self, mock_score, tmp_path):
        """When the comment handshake fails the comment is invisible, so it is
        not recorded — but the comment-rate counter still advances."""
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {
            "id": "c-new",
            "verification": {
                "verification_code": "moltbook_verify_x",
                "challenge_text": "noise",
            },
        }
        agent._feed_manager._handle_verification = MagicMock(return_value=False)

        result = agent._feed_manager.engage_with_post(
            {"content": "text", "id": "post1"}, agent._client, agent._scheduler
        )
        assert result is False
        assert not agent._ctx.memory.has_commented_on("post1")
        assert agent._ctx.actions_taken == []
        agent._scheduler.record_comment.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_comment_client_error(self, mock_score, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.side_effect = MoltbookClientError("fail")

        result = agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
        assert result is False

    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_body_level_failure_not_recorded(self, mock_score, tmp_path):
        """Audit H2: a body-level failure (200 + success:false → raise from
        post_comment) must not pollute the permanent dedup cache or the
        episode log — the post stays retryable in a later session."""
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.side_effect = MoltbookClientError(
            "Comment on post1 failed at body level (HTTP 200): nope",
            status_code=200,
        )

        result = agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
        assert result is False
        assert not agent._ctx.memory.has_commented_on("post1")
        assert agent._ctx.actions_taken == []
        comment_eps = [
            r
            for r in agent._ctx.memory.episodes.read_range(
                days=1, record_type="activity"
            )
            if r.get("data", {}).get("action") == "comment"
        ]
        assert comment_eps == []

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="the melting metaphor felt forced, not earned",
    )
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_comment_records_internal_note(
        self, mock_score, mock_note, mock_random, mock_time, tmp_path
    ):
        """A comment episode carries the pre-action internal_note (ADR-0045)."""
        mock_random.uniform.return_value = 60.0
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {"id": "c-new"}

        agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)

        comment_eps = [
            r
            for r in agent._ctx.memory.episodes.read_range(days=1, record_type="activity")
            if r.get("data", {}).get("action") == "comment"
        ]
        assert comment_eps, "expected a comment activity episode"
        assert (
            comment_eps[0]["data"]["internal_note"]
            == "the melting metaphor felt forced, not earned"
        )

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="",
    )
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_comment_records_counterparty_name(
        self, mock_score, mock_note, mock_random, mock_time, tmp_path
    ):
        """A comment episode records the counterparty NAME (target_agent).

        Live feed posts carry author.name but not author.id, so the name is
        the reliable counterparty key written to the activity record.
        """
        mock_random.uniform.return_value = 60.0
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {"id": "c-new"}

        agent._feed_manager.engage_with_post(
            {"content": "text", "id": "post1", "author": {"name": "alice"}},
            agent._client, agent._scheduler,
        )

        comment_eps = [
            r
            for r in agent._ctx.memory.episodes.read_range(days=1, record_type="activity")
            if r.get("data", {}).get("action") == "comment"
        ]
        assert comment_eps, "expected a comment activity episode"
        assert comment_eps[0]["data"]["target_agent"] == "alice"

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="note",
    )
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_truncated_post_fetches_full_body(
        self, mock_score, mock_note, mock_random, mock_time, tmp_path
    ):
        """A 500-char (truncated) submolt post triggers get_post; the comment
        and the recorded original_post use the full body."""
        mock_random.uniform.return_value = 60.0
        preview = "x" * 500
        full = preview + " ...the rest the submolt feed truncated away."
        agent = self._make_agent(tmp_path)
        agent._client.has_read_budget.return_value = True
        agent._client.get_post.return_value = {"id": "post1", "content": full}
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {"id": "c-new"}

        agent._feed_manager.engage_with_post({"content": preview, "id": "post1"}, agent._client, agent._scheduler)

        agent._client.get_post.assert_called_once_with("post1")
        agent._content.create_comment.assert_called_once_with(full)
        comment_eps = [
            r
            for r in agent._ctx.memory.episodes.read_range(days=1, record_type="activity")
            if r.get("data", {}).get("action") == "comment"
        ]
        assert comment_eps, "expected a comment activity episode"
        assert comment_eps[0]["data"]["original_post"] == full

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="note",
    )
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_internal_note_runs_on_full_body_not_preview(
        self, mock_score, mock_note, mock_random, mock_time, tmp_path
    ):
        """weekly-2026-06-21 F1.1: the internal note must read the FULL post,
        not the 500-char submolt preview — a mid-word preview cut was misread
        by the note's register as a deliberate pause, and the wrapper labelled
        the under-max_input preview "complete". The full body is fetched before
        the note, so the note sees it."""
        mock_random.uniform.return_value = 60.0
        preview = "x" * 500
        full = preview + " ...the rest the submolt feed truncated away."
        agent = self._make_agent(tmp_path)
        agent._client.has_read_budget.return_value = True
        agent._client.get_post.return_value = {"id": "post1", "content": full}
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {"id": "c-new"}

        agent._feed_manager.engage_with_post(
            {"content": preview, "id": "post1"}, agent._client, agent._scheduler
        )

        mock_note.assert_called_once_with(full)

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="note",
    )
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_full_post_skips_fetch(
        self, mock_score, mock_note, mock_random, mock_time, tmp_path
    ):
        """A post longer than the preview length is already full — no re-fetch."""
        mock_random.uniform.return_value = 60.0
        full = "y" * 1200  # > FEED_CONTENT_PREVIEW_LEN
        agent = self._make_agent(tmp_path)
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {"id": "c-new"}

        agent._feed_manager.engage_with_post({"content": full, "id": "post1"}, agent._client, agent._scheduler)

        agent._client.get_post.assert_not_called()
        agent._content.create_comment.assert_called_once_with(full)

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="note",
    )
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_truncated_post_budget_low_uses_preview(
        self, mock_score, mock_note, mock_random, mock_time, tmp_path
    ):
        """When read budget is exhausted, fall back to the 500-char preview
        rather than blocking the comment."""
        mock_random.uniform.return_value = 60.0
        preview = "z" * 500
        agent = self._make_agent(tmp_path)
        agent._client.has_read_budget.return_value = False
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {"id": "c-new"}

        agent._feed_manager.engage_with_post({"content": preview, "id": "post1"}, agent._client, agent._scheduler)

        agent._client.get_post.assert_not_called()
        agent._content.create_comment.assert_called_once_with(preview)
        comment_eps = [
            r
            for r in agent._ctx.memory.episodes.read_range(days=1, record_type="activity")
            if r.get("data", {}).get("action") == "comment"
        ]
        assert comment_eps[0]["data"]["original_post"] == preview

    @patch("contemplative_agent.adapters.moltbook.feed_manager.time")
    @patch("contemplative_agent.adapters.moltbook.feed_manager.random")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="note",
    )
    @patch("contemplative_agent.adapters.moltbook.feed_manager.score_relevance", return_value=0.95)
    def test_truncated_post_refetch_not_longer_keeps_preview(
        self, mock_score, mock_note, mock_random, mock_time, tmp_path
    ):
        """If get_post returns content no longer than the preview, keep the
        preview (guards against re-fetching a genuinely 500-char post)."""
        mock_random.uniform.return_value = 60.0
        preview = "x" * 500
        agent = self._make_agent(tmp_path)
        agent._client.has_read_budget.return_value = True
        agent._client.get_post.return_value = {"id": "post1", "content": "y" * 500}
        agent._content.create_comment.return_value = "Great insight"
        agent._client.post_comment.return_value = {"id": "c-new"}

        agent._feed_manager.engage_with_post({"content": preview, "id": "post1"}, agent._client, agent._scheduler)

        agent._client.get_post.assert_called_once_with("post1")
        agent._content.create_comment.assert_called_once_with(preview)


class TestRunFeedCycle:
    def test_processes_posts(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._client.has_read_budget.return_value = True
        agent._client.get_following_feed.return_value = []
        agent._scheduler = MagicMock()
        fm = agent._feed_manager

        # The legacy feed-borne verification_challenge field is now inert: the
        # current API returns challenges in the create-response (handled at
        # create time), never on a fetched feed post. Both posts must reach
        # engage_with_post and the feed loop must not dispatch verification.
        posts = [
            {"content": "post1", "id": "p1"},
            {"content": "post2", "id": "p2", "verification_challenge": {"text": "v", "id": "vc1"}},
        ]

        with patch.object(fm, "get_feed", return_value=posts), \
             patch.object(agent, "_handle_verification") as mock_verify, \
             patch.object(fm, "engage_with_post") as mock_engage:
            agent._run_feed_cycle(time.time() + 3600)

        assert mock_engage.call_count == 2
        mock_verify.assert_not_called()

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


def _admit_decision():
    """Build a GateDecision that admits — used to bypass NoveltyGate in tests
    that exercise downstream behaviour (publish path, body-hash gate, etc.).
    """
    from contemplative_agent.adapters.moltbook.novelty import GateDecision

    return GateDecision(
        admit=True,
        novelty=1.0,
        deficit=0.0,
        threshold=0.35,
        nearest_title=None,
        nearest_sim=0.0,
        reason="admit",
    )


class TestRunPostCycle:
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="reflection on alignment")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Notes on dedup gates")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_posts_dynamic(self, mock_score, mock_title, mock_summarize, mock_submolt):
        # NOTE: title and body must avoid anything in dedup._TEST_PATTERNS
        # ("Test Title" / "Dynamic content" from Mar 30–31 leaks, and
        # "Reflective Note" / "A short body about alignment" from the
        # Apr 2026 episode-log pollution). The test-content gate (correctly)
        # blocks those literals from reaching the live feed.
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = (
            "We paused to revisit how gates intersect with memory."
        )
        # Bypass NoveltyGate at the boundary — keep the test focused on the
        # publish path. NoveltyGate's own behaviour is covered in
        # test_novelty_gate.py.
        agent._post_pipeline._novelty_gate.evaluate = MagicMock(
            return_value=_admit_decision()
        )
        agent._post_pipeline._novelty_gate.record = MagicMock()

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        post_resp = MagicMock()
        post_resp.json.return_value = {"success": True, "post": {"id": "new-post-123"}}
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        agent._client.post.assert_called_once()
        assert any("Posted: Notes on dedup gates" in a for a in agent._ctx.actions_taken)

    @patch("contemplative_agent.adapters.moltbook.verification.generate", return_value="15")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="reflection on alignment")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Notes on dedup gates")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_created_post_triggers_verify(
        self, mock_score, mock_title, mock_summarize, mock_submolt, mock_gen,
        tmp_path,
    ):
        """Regression (the exact bug): a create-response carrying a
        ``verification`` object must drive a POST /verify keyed on
        verification_code before the post is recorded. Pre-fix this never
        happened and every post stayed pending/invisible."""
        # Clean memory so the body-hash dedup gate isn't tripped by the shared
        # session MOLTBOOK_HOME (other post-cycle tests reuse the same content).
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = (
            "We paused to revisit how gates intersect with memory."
        )
        agent._post_pipeline._novelty_gate.evaluate = MagicMock(
            return_value=_admit_decision()
        )
        agent._post_pipeline._novelty_gate.record = MagicMock()

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [
            {"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}
        ]}
        post_resp = MagicMock()
        post_resp.json.return_value = {
            "success": True,
            "post": {
                "id": "new-post-123",
                "verification_status": "pending",
                "verification": {
                    "verification_code": "moltbook_verify_x",
                    "challenge_text": "A] lO^bSt-Er ...",
                },
            },
        }
        verify_resp = MagicMock()
        verify_resp.json.return_value = {"success": True}
        agent._client.get.return_value = feed_resp

        def post_router(path, **kwargs):
            return verify_resp if path == "/verify" else post_resp

        agent._client.post.side_effect = post_router

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)

        verify_calls = [
            c for c in agent._client.post.call_args_list
            if c.args and c.args[0] == "/verify"
        ]
        assert len(verify_calls) == 1
        assert verify_calls[0].kwargs["json"]["verification_code"] == "moltbook_verify_x"
        # Verified → recorded.
        assert any("Posted:" in a for a in agent._ctx.actions_taken)
        agent._post_pipeline._novelty_gate.record.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.agent.record_verification_audit")
    @patch(
        "contemplative_agent.adapters.moltbook.agent.solve_challenge_result",
        return_value=_solve_result(None),
    )
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="reflection on alignment")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Notes on dedup gates")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_failed_verification_not_recorded(
        self,
        mock_score,
        mock_title,
        mock_summarize,
        mock_submolt,
        mock_solve,
        mock_audit,
        tmp_path,
    ):
        """When verification cannot be solved, the (invisible) post must not be
        recorded — it stays out of NoveltyGate/memory/actions — but the
        rate-limit counter still advances (the create consumed server quota)."""
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = (
            "We paused to revisit how gates intersect with memory."
        )
        agent._post_pipeline._novelty_gate.evaluate = MagicMock(
            return_value=_admit_decision()
        )
        agent._post_pipeline._novelty_gate.record = MagicMock()

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [
            {"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}
        ]}
        post_resp = MagicMock()
        post_resp.json.return_value = {
            "success": True,
            "post": {
                "id": "new-post-123",
                "verification": {
                    "verification_code": "moltbook_verify_x",
                    "challenge_text": "unsolvable",
                },
            },
        }
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)

        assert agent._ctx.actions_taken == []
        agent._post_pipeline._novelty_gate.record.assert_not_called()
        agent._content.mark_posted.assert_not_called()
        agent._scheduler.record_post.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="topic summary")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Notes on shared gates")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_own_post_excluded_from_seeds(self, mock_score, mock_title, mock_summarize):
        """F1.1: the agent's own posts re-entering the feed must not be picked
        as seeds for a new self-post. Mirrors engage_with_post's own-post skip
        (feed_manager.py). Posts with no author survive (no regression)."""
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = (
            "We paused to revisit how gates intersect with memory."
        )
        agent._post_pipeline._novelty_gate.evaluate = MagicMock(
            return_value=_admit_decision()
        )
        agent._post_pipeline._novelty_gate.record = MagicMock()
        agent._ctx.own_agent_id = "my-agent-id"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [
            {"title": "mine", "content": "my own earlier words", "id": "own-1",
             "submolt_name": "philosophy", "author": {"id": "my-agent-id"}},
            {"title": "theirs", "content": "another voice", "id": "other-1",
             "submolt_name": "philosophy", "author": {"id": "other-agent"}},
            {"title": "anon", "content": "no author field", "id": "noauthor-1",
             "submolt_name": "philosophy"},
            {"title": "nullid", "content": "author id is null", "id": "nullid-1",
             "submolt_name": "philosophy", "author": {"id": None}},
        ]}
        post_resp = MagicMock()
        post_resp.json.return_value = {"success": True, "post": {"id": "new-post-123"}}
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)

        agent._content.create_cooperation_post.assert_called_once()
        seed_ids = {
            s.get("id")
            for s in agent._content.create_cooperation_post.call_args.args[0]
        }
        assert "own-1" not in seed_ids       # own post excluded
        assert "other-1" in seed_ids         # other agent's post kept
        assert "noauthor-1" in seed_ids      # missing author => kept (no regression)
        assert "nullid-1" in seed_ids        # author.id None => normalized to "", kept

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="topic summary")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Notes on shared gates")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_own_post_seeds_kept_when_agent_id_unknown(self, mock_score, mock_title, mock_summarize):
        """F1.1 degradation: if own_agent_id never populated (empty string), the
        skip is a no-op — same guard as the comment path (`if ctx.own_agent_id`)."""
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = (
            "We paused to revisit how gates intersect with memory."
        )
        agent._post_pipeline._novelty_gate.evaluate = MagicMock(
            return_value=_admit_decision()
        )
        agent._post_pipeline._novelty_gate.record = MagicMock()
        agent._ctx.own_agent_id = ""  # not populated

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [
            {"title": "mine", "content": "my own earlier words", "id": "own-1",
             "submolt_name": "philosophy", "author": {"id": "my-agent-id"}},
            {"title": "theirs", "content": "another voice", "id": "other-1",
             "submolt_name": "philosophy", "author": {"id": "other-agent"}},
        ]}
        post_resp = MagicMock()
        post_resp.json.return_value = {"success": True, "post": {"id": "new-post-123"}}
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)

        agent._content.create_cooperation_post.assert_called_once()
        seed_ids = {
            s.get("id")
            for s in agent._content.create_cooperation_post.call_args.args[0]
        }
        assert "own-1" in seed_ids  # no-op: own post not excluded

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="topic summary")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="A different title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_skips_when_body_hash_matches(
        self, mock_score, mock_title, mock_summarize,
    ):
        """ADR-0018 amendment: body-hash gate catches verbatim re-publication
        that title/topic Jaccard misses (May 3 2026 self-post #2 = Apr 30 #2,
        identical body but different title)."""
        from contemplative_agent.adapters.moltbook.content import _content_hash
        from contemplative_agent.core.memory import PostRecord

        duplicate_body = "A body that was posted verbatim earlier in the week."
        prior_hash = _content_hash(duplicate_body)

        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = duplicate_body

        prior_record = PostRecord(
            timestamp="2026-04-30T00:00:00Z",
            post_id="prior-post",
            title="Prior post title",
            topic_summary="prior summary",
            content_hash=prior_hash,
            verified=True,  # a real prior post the body-hash gate compares against
        )
        # NoveltyGate admits — the only gate that can block here is the
        # body-hash gate this test exercises.
        agent._post_pipeline._novelty_gate.evaluate = MagicMock(
            return_value=_admit_decision()
        )
        agent._ctx.memory.get_recent_posts = MagicMock(return_value=[prior_record])

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        agent._client.get.return_value = feed_resp

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        # Body hash matched → publish skipped
        agent._client.post.assert_not_called()

    def test_skips_when_cannot_post(self):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = False

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        agent._client.post.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_skips_none_content(self, mock_score):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = None

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        agent._client.get.return_value = feed_resp

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        agent._client.post.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_post_client_error(self, mock_score, mock_title):
        agent = Agent(autonomy=AutonomyLevel.AUTO)
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        agent._client.get.return_value = feed_resp
        agent._client.post.side_effect = MoltbookClientError("fail")

        agent._post_pipeline.run_cycle(agent._client, agent._scheduler)
        # Should not raise


class TestRunSession:
    @patch("contemplative_agent.adapters.moltbook.agent.time")
    @patch("contemplative_agent.adapters.moltbook.agent.load_credentials", return_value="key")
    def test_session_ends_by_time(self, mock_creds, mock_time):
        # Simulate: end_time=160, first loop runs, then time passes end_time.
        # After the deterministic first pair [100.0, 100.0], clamp all later
        # time.time() calls to 200.0 so the loop exits and the test does not
        # fall back to real wall-clock time when side_effect is exhausted.
        mock_time.time.side_effect = chain([100.0, 100.0], repeat(200.0))

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
    def test_print_report(self, caplog):
        agent = Agent()
        agent._ctx.actions_taken.extend(["Action 1", "Action 2"])
        agent._scheduler = MagicMock()
        agent._scheduler.comments_remaining_today = 48
        agent._content = MagicMock()
        agent._content.comment_to_post_ratio = 3.0

        with caplog.at_level("INFO", logger="contemplative_agent.adapters.moltbook.agent"):
            agent._print_report()
        messages = "\n".join(r.getMessage() for r in caplog.records)
        assert "Session Report" in messages
        assert "Actions taken: 2" in messages
        assert "Action 1" in messages

    def test_print_report_no_scheduler(self, caplog):
        agent = Agent()
        agent._ctx.actions_taken.clear()
        agent._content = MagicMock()
        agent._content.comment_to_post_ratio = 0.0

        with caplog.at_level("INFO", logger="contemplative_agent.adapters.moltbook.agent"):
            agent._print_report()
        messages = "\n".join(r.getMessage() for r in caplog.records)
        assert "Actions taken: 0" in messages


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
    """Tests that own post IDs are captured from _run_dynamic_post."""

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_dynamic_post_captures_post_id(self, mock_score, mock_title, mock_select, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        post_resp = MagicMock()
        post_resp.json.return_value = {"success": True, "post": {"id": "dyn-post-1"}}
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp

        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)
        assert "dyn-post-1" in agent._ctx.own_post_ids

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_dynamic_post_captures_post_id_from_nested_envelope(
        self, mock_score, mock_title, mock_select, tmp_path,
    ):
        """Moltbook returns ``{"success": True, "post": {"id": ...}}`` for
        create-post (see skill.md AI Verification Challenges step 1 + the
        ``{"success", "<resource>"}`` envelope used by /agents/me and
        /agents/profile). Pre-fix the loader looked only at the top-level
        ``id`` key and silently dropped the id for every self-post, which
        in turn neutralised the ADR-0039 NoveltyGate (empty post_id keys
        → empty embedding sidecar → novelty=1.0 always)."""
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        post_resp = MagicMock()
        post_resp.json.return_value = {
            "success": True,
            "post": {"id": "nested-post-1", "title": "Title"},
        }
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp

        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)
        assert "nested-post-1" in agent._ctx.own_post_ids

    @staticmethod
    def _setup_post_agent(tmp_path, post_payload):
        """Wire an AUTO agent whose create-post returns ``post_payload``."""
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        post_resp = MagicMock()
        post_resp.json.return_value = post_payload
        agent._client.get.return_value = feed_resp
        agent._client.post.return_value = post_resp
        return agent

    @staticmethod
    def _assert_post_not_recorded(agent):
        """H1 (review 2026-06-27): an un-provable create-post must leave no
        trace in dedup / memory / episode / NoveltyGate — only the rate-limit
        quota is consumed because the HTTP request did reach the server."""
        assert agent._ctx.own_post_ids == set()
        assert agent._memory.get_recent_posts() == []
        assert agent._memory.episodes.read_range(days=2, record_type="activity") == []
        agent._content.mark_posted.assert_not_called()
        agent._scheduler.record_post.assert_called_once()

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_dynamic_post_records_nothing_when_missing_id(
        self, mock_score, mock_title, mock_select, tmp_path, caplog,
    ):
        """H1: an envelope with no usable ``post.id`` (and no top-level id)
        must hard-gate — no dedup mark, no post history, no activity episode —
        not merely warn while still polluting memory as it did pre-fix."""
        import logging

        # Envelope shape changed: no "post" key, no top-level "id".
        agent = self._setup_post_agent(tmp_path, {"success": True, "message": "ok"})
        with caplog.at_level(logging.WARNING, logger="contemplative_agent.adapters.moltbook.post_pipeline"):
            agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)
        self._assert_post_not_recorded(agent)
        assert any("recording nothing" in rec.message for rec in caplog.records)

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_dynamic_post_records_nothing_on_success_false(
        self, mock_score, mock_title, mock_select, tmp_path,
    ):
        """H1: HTTP 2xx with body-level ``success: false`` must record nothing
        even though a ``post.id`` could be present in a malformed body."""
        agent = self._setup_post_agent(
            tmp_path, {"success": False, "error": "rejected", "post": {"id": "ghost"}}
        )
        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)
        self._assert_post_not_recorded(agent)

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_dynamic_post_records_nothing_on_non_dict_post(
        self, mock_score, mock_title, mock_select, tmp_path,
    ):
        """H1: a non-object ``post`` with no recoverable top-level id yields
        no usable id, so nothing is recorded."""
        agent = self._setup_post_agent(
            tmp_path, {"success": True, "post": "not-a-dict"}
        )
        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)
        self._assert_post_not_recorded(agent)

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_dynamic_post_records_nothing_on_non_dict_body(
        self, mock_score, mock_title, mock_select, tmp_path,
    ):
        """H1: a non-dict response body (e.g. a bare JSON list) records nothing."""
        agent = self._setup_post_agent(tmp_path, ["unexpected", "shape"])
        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)
        self._assert_post_not_recorded(agent)

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="philosophy")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_dynamic_post_records_nothing_on_malformed_id(
        self, mock_score, mock_title, mock_select, tmp_path,
    ):
        """H1 + security M (review 2026-06-27): a server id with control
        characters (log-injection / episode-log-pollution vector) fails
        VALID_ID_PATTERN, so the post is gated out and recorded nowhere."""
        agent = self._setup_post_agent(
            tmp_path, {"success": True, "post": {"id": "ok\nFAKE: injected line"}}
        )
        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)
        self._assert_post_not_recorded(agent)

    def test_init_has_empty_own_post_ids(self):
        agent = Agent()
        assert agent._ctx.own_post_ids == set()


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

        # Notification path has no comment id → top-level comment (parent_id None).
        agent._client.post_comment.assert_called_once_with(
            "p1", "My reply", parent_id=None
        )
        assert "Replied to Alice on p1" in agent._ctx.actions_taken
        # Both received + sent should be recorded
        assert agent._memory.interaction_count() - before_count == 2

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="My reply")
    def test_processes_camelcase_notification(self, mock_reply, tmp_path):
        agent = self._make_agent(tmp_path)
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

        agent._client.post_comment.assert_called_once_with(
            "p2", "My reply", parent_id=None
        )
        assert "Replied to Bob on p2" in agent._ctx.actions_taken

    def test_skips_non_reply_notification(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._client.get_notifications.return_value = [
            {"type": "like", "id": "n1", "post_id": "p1"}
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(agent._client, agent._scheduler, time.time() + 3600)

        agent._client.post_comment.assert_not_called()

    def test_skips_empty_content(self, tmp_path):
        agent = self._make_agent(tmp_path)
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

        agent._client.post_comment.assert_not_called()

    def test_skips_already_handled(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._ctx.commented_posts.add("reply:p1:n1")
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

        agent._client.post_comment.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="My reply")
    def test_skips_when_replied_persisted_cross_session(self, mock_reply, tmp_path):
        # Fresh session: commented_posts is empty, but a prior session
        # persisted this reply via memory.record_commented. The notification
        # gate must consult the persistent store, not only the session set
        # (mirrors the comment path's has_commented_on check). generate_reply
        # is mocked so the gate — not an unavailable LLM — is what blocks.
        agent = self._make_agent(tmp_path)
        agent._memory.record_commented("reply:p1:n1")
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

        agent._client.post_comment.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="My reply")
    def test_records_reply_persistently(self, mock_reply, tmp_path):
        # After a successful reply, the reply key must be persisted so a
        # later session's has_commented_on check skips it (cross-session dedup).
        agent = self._make_agent(tmp_path)
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

        assert agent._memory.has_commented_on("reply:p1:n1")

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="My reply")
    def test_notification_reply_skips_upvote(self, mock_reply, tmp_path):
        # The notification path keys reply_key on the notification id, not a
        # comment id, so it must NOT issue a courtesy upvote — doing so upvotes
        # the wrong target (a failing POST that wastes write budget). The
        # payload carries no comment id to upvote.
        agent = self._make_agent(tmp_path)
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

        agent._client.post_comment.assert_called_once_with(
            "p1", "My reply", parent_id=None
        )
        agent._client.upvote_comment.assert_not_called()

    def test_skips_promotional_their_comment(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._client.get_notifications.return_value = [
            {
                "type": "comment",
                "id": "n1",
                "post_id": "p1",
                "content": "join us at https://example.spam/",
                "post_content": "Genuine post",
                "agent_id": "a1",
                "agent_name": "Spammer",
            }
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(agent._client, agent._scheduler, time.time() + 3600)

        agent._client.post_comment.assert_not_called()

    def test_skips_promotional_original_post(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._client.get_notifications.return_value = [
            {
                "type": "comment",
                "id": "n1",
                "post_id": "p1",
                "content": "thanks for sharing",
                "post_content": "make a profile at our site",
                "agent_id": "a1",
                "agent_name": "Alice",
            }
        ]
        agent._client.get_post_comments.return_value = []

        agent._reply_handler.run_cycle(agent._client, agent._scheduler, time.time() + 3600)

        agent._client.post_comment.assert_not_called()


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
        agent._ctx.own_post_ids.add("my-post-1")
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

        # Comment-scan path knows the comment id → reply threads under it.
        agent._client.post_comment.assert_called_once_with(
            "my-post-1", "Thanks!", parent_id="c1"
        )
        assert "Replied to Alice on my-post-1" in agent._ctx.actions_taken
        assert agent._memory.interaction_count() - before_count == 2  # received + sent

    def test_skips_when_no_own_posts(self, tmp_path):
        agent = self._make_agent(tmp_path)
        assert len(agent._ctx.own_post_ids) == 0

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() + 3600
        )

        agent._client.get_post_comments.assert_not_called()

    def test_skips_already_replied_comment(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._ctx.own_post_ids.add("my-post-1")
        agent._ctx.commented_posts.add("reply:my-post-1:c1")
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

        agent._client.post_comment.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="Thanks!")
    def test_skips_replied_comment_persisted_cross_session(self, mock_reply, tmp_path):
        # Fresh session: commented_posts is empty, but a prior session
        # persisted this reply via memory.record_commented. The comment-scan
        # gate must consult the persistent store, not only the session set.
        # generate_reply is mocked so the gate — not an unavailable LLM — blocks.
        agent = self._make_agent(tmp_path)
        agent._ctx.own_post_ids.add("my-post-1")
        agent._memory.record_commented("reply:my-post-1:c1")
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

        agent._client.post_comment.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="Thanks!")
    def test_comment_scan_upvotes_real_comment_id(self, mock_reply, tmp_path):
        # The comment-scan path has the real comment id, so the courtesy
        # upvote targets that comment (not a notification id).
        agent = self._make_agent(tmp_path)
        agent._ctx.own_post_ids.add("my-post-1")
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

        agent._client.upvote_comment.assert_called_once_with("c1")

    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply", return_value="Thanks!")
    def test_handles_nested_author_in_comments(self, mock_reply, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._ctx.own_post_ids.add("my-post-1")
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

        agent._client.post_comment.assert_called_once()
        assert "Replied to Bob on my-post-1" in agent._ctx.actions_taken

    def test_respects_end_time(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._ctx.own_post_ids.add("my-post-1")

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() - 1
        )

        agent._client.get_post_comments.assert_not_called()

    def test_respects_rate_limit(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._ctx.own_post_ids.add("my-post-1")
        agent._ctx.set_rate_limited()

        agent._reply_handler.check_own_post_comments(
            agent._client, agent._scheduler, time.time() + 3600
        )

        agent._client.get_post_comments.assert_not_called()

    def test_respects_scheduler_can_comment(self, tmp_path):
        agent = self._make_agent(tmp_path)
        agent._ctx.own_post_ids.add("my-post-1")
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

        result = agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
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

        result = agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
        assert result is False
        agent._client.post_comment.assert_not_called()

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

        agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, agent._client, agent._scheduler)
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
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_uses_selected_submolt(
        self, mock_score, mock_title, mock_summarize, mock_select, tmp_path,
    ):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "Post content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        agent._client.get.return_value = feed_resp
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"success": True, "post": {"id": "new-post-1"}}
        agent._client.post.return_value = mock_resp

        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)

        # Verify the submolt in the post request
        call_kwargs = agent._client.post.call_args[1]
        assert call_kwargs["json"]["submolt"] == "philosophy"

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value=None)
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="topic")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_selection_failure_skips_post(
        self, mock_score, mock_title, mock_summarize, mock_select, tmp_path,
    ):
        """Audit L5: select_submolt failure skips the post entirely (skip,
        don't substitute — same idiom as the circuit breaker paths). The
        old behavior published to the default submolt: fail-toward-acting."""
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "Post content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        agent._client.get.return_value = feed_resp

        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)

        agent._client.post.assert_not_called()

    @patch("contemplative_agent.adapters.moltbook.post_pipeline.select_submolt", return_value="General Topics!!")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.summarize_post_topic", return_value="topic")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline.generate_post_title", return_value="Title")
    @patch("contemplative_agent.adapters.moltbook.post_pipeline._score_post_relevance", return_value=0.8)
    def test_invalid_name_skips_post(
        self, mock_score, mock_title, mock_summarize, mock_select, tmp_path,
    ):
        """Audit L5: an invalid submolt name is the same failure as None."""
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_post.return_value = True
        agent._content = MagicMock()
        agent._content.create_cooperation_post.return_value = "Post content"

        feed_resp = MagicMock()
        feed_resp.json.return_value = {"posts": [{"title": "t", "content": "c", "id": "p1", "submolt_name": "philosophy"}]}
        agent._client.get.return_value = feed_resp

        agent._post_pipeline._run_dynamic_post(agent._client, agent._scheduler)

        agent._client.post.assert_not_called()


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

        # run_session() resets _shutdown_requested=False at entry, so we need
        # to raise the flag after the loop starts. Mock time.time() to also
        # trip the flag on the 3rd call (post-setup, in the while condition).
        # Mock time.sleep to avoid real-time waiting if a cycle slips through.
        call_count = [0]

        def fake_time():
            call_count[0] += 1
            if call_count[0] > 2:
                agent._shutdown_requested = True
            return 1000.0 + call_count[0]

        with patch.object(agent._memory, "save") as mock_save, \
             patch("contemplative_agent.adapters.moltbook.agent.time") as mock_time:
            mock_time.time = fake_time
            mock_time.sleep = MagicMock()
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
        assert agent._ctx.own_agent_id == "agent-123"
        assert agent._home_data["your_account"]["name"] == "bot"

    def test_home_empty_falls_back_to_agents_me(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        mock_client = MagicMock()
        mock_client.get_home.return_value = {}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"agent": {"id": "fallback-456", "name": "bot"}}
        mock_client.get.return_value = mock_resp

        agent._fetch_home_data(mock_client)
        assert agent._ctx.own_agent_id == "fallback-456"

    def test_fallback_error_leaves_id_empty(self, tmp_path):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError as MCE
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        mock_client = MagicMock()
        mock_client.get_home.return_value = {}
        mock_client.get.side_effect = MCE("Network error")

        agent._fetch_home_data(mock_client)
        assert agent._ctx.own_agent_id == ""

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
        agent._ctx.own_agent_id = "me-123"
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
        agent._ctx.own_agent_id = "my-agent-id"

        post = {
            "content": "Some post",
            "id": "post1",
            "author": {"id": "my-agent-id", "name": "self"},
        }
        result = agent._feed_manager.engage_with_post(post, agent._client, agent._scheduler)
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
        agent._ctx.own_agent_id = "my-agent-id"

        post = {
            "content": "Some post",
            "id": "post1",
            "author": {"id": "other-agent", "name": "other"},
        }
        agent._feed_manager.engage_with_post(post, agent._client, agent._scheduler)
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
        result = agent._feed_manager.engage_with_post(post, agent._client, agent._scheduler)
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
        agent._feed_manager.engage_with_post(post, agent._client, agent._scheduler)
        mock_score.assert_called_once()


class TestSelfReplySkip:
    """Skips own comments in notification reply cycle."""

    def _make_agent(self, tmp_path):
        agent = Agent(autonomy=AutonomyLevel.AUTO, memory=_make_clean_memory(tmp_path))
        agent._client = MagicMock()
        agent._scheduler = MagicMock()
        agent._scheduler.can_comment.return_value = True
        agent._ctx.own_agent_id = "my-agent-id"
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
