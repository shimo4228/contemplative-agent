"""RFC-0028 wiring: the publish path links, the reply cycle observes.

Two seams, both in the adapter:

* the comment / reply publish paths hand the ``selection_id`` that came back
  with the generation to ``record_publish_outcome``, with a reason code on
  every exit;
* ``_handle_post_comments`` feeds the comment tree it *already fetched* to
  the outcome recorder — no extra GET, and ``/home``'s allowlist untouched.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from contemplative_agent.core import skill_selection as ss
from contemplative_agent.core.comment_outcomes import ObservedComment
from contemplative_agent.core.llm.backend import GenerationOutput
from tests.test_agent import _scored


class TestGenerationCarriesTheSelectionId:
    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate_for_api")
    @patch("contemplative_agent.adapters.moltbook.llm_functions.observe_skill_selection_recorded")
    def test_generate_comment_attaches_the_id(self, observe, gen):
        from contemplative_agent.adapters.moltbook import llm_functions as lf

        observe.return_value = ss.SelectionObservation(selected=("skill-a",), selection_id="sel1")
        gen.return_value = GenerationOutput(text="hi")
        lf.generate_comment("a post")
        # Stamped where the DTO is built (generate_for_api), so the failure
        # return carries it too — the call site only passes it on.
        assert gen.call_args.kwargs["selection_id"] == "sel1"

    @patch("contemplative_agent.adapters.moltbook.llm_functions.generate_for_api")
    @patch("contemplative_agent.adapters.moltbook.llm_functions.observe_skill_selection_recorded")
    def test_generate_reply_attaches_the_id(self, observe, gen):
        from contemplative_agent.adapters.moltbook import llm_functions as lf

        observe.return_value = ss.SelectionObservation(selected=None, selection_id="sel2")
        gen.return_value = GenerationOutput(text="hi")
        lf.generate_reply(original_post="p", their_comment="c")
        assert gen.call_args.kwargs["selection_id"] == "sel2"


class TestGenerateForApiStampsTheId:
    def test_failure_return_still_carries_the_id(self):
        from contemplative_agent.core.llm import generate_for_api

        with patch("contemplative_agent.core.llm._generate_full", return_value=None):
            out = generate_for_api("p", max_length=10, selection_id="sel3")
        assert out.text is None
        assert out.selection_id == "sel3"

    def test_success_return_carries_the_id(self):
        from contemplative_agent.core.llm import generate_for_api

        with patch(
            "contemplative_agent.core.llm._generate_full",
            return_value=GenerationOutput(text="hi"),
        ):
            out = generate_for_api("p", max_length=10, selection_id="sel4")
        assert out.text == "hi"
        assert out.selection_id == "sel4"


class TestObservedTreeBuild:
    def test_builds_own_flags_upvotes_and_nesting(self):
        from contemplative_agent.adapters.moltbook.reply_handler import build_observed_comments

        raw = [
            {
                "id": "c1",
                "content": "ours",
                "agent_name": "me",
                "upvotes": 4,
                "replies": [{"id": "r1", "content": "theirs", "agent_name": "other"}],
            }
        ]
        tree = build_observed_comments(raw, is_self=lambda i, n: n == "me")
        assert isinstance(tree[0], ObservedComment)
        assert tree[0].comment_id == "c1"
        assert tree[0].is_own is True
        assert tree[0].upvotes == 4
        assert tree[0].replies[0].comment_id == "r1"
        assert tree[0].replies[0].is_own is False
        assert tree[0].replies[0].body == "theirs"

    def test_non_dict_nodes_are_skipped(self):
        from contemplative_agent.adapters.moltbook.reply_handler import build_observed_comments

        tree = build_observed_comments(
            ["not a dict", {"id": "c1", "replies": "not a list"}], is_self=lambda i, n: False
        )
        assert len(tree) == 1
        assert tree[0].replies == ()


class TestHomeAllowlistUnchanged:
    def test_outcome_recording_added_no_home_field(self):
        from contemplative_agent.adapters.moltbook.agent import _HOME_ALLOWED_KEYS

        assert _HOME_ALLOWED_KEYS == ("your_account", "activity_on_your_posts")

    def test_no_new_client_getter_is_called_for_outcomes(self):
        """The recorder consumes the tree the reply cycle already has."""
        import inspect

        from contemplative_agent.adapters.moltbook import reply_handler as rh

        source = inspect.getsource(rh.ReplyHandler._handle_post_comments)
        assert "record_comment_outcomes" in source
        assert source.count("client.get_") == 1  # the pre-existing comment fetch


@patch("contemplative_agent.adapters.moltbook.feed_manager.time.sleep")
@patch("contemplative_agent.adapters.moltbook.reply_handler.time.sleep")
class TestPublishRecordsTheLink:
    """Every exit of a publish path names its outcome (ADR-0075: a publish
    that produced no comment id must say why, not go missing)."""

    @staticmethod
    def _agent(tmp_path, comment_text="Great", created=None):
        from contemplative_agent.adapters.moltbook.agent import Agent, AutonomyLevel
        from contemplative_agent.core.memory import MemoryStore

        client = MagicMock()
        client.has_write_budget.return_value = True
        client.post_comment.return_value = created if created is not None else {"id": "c1"}
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True
        scheduler.can_post.return_value = True
        content = MagicMock()
        content.create_comment.return_value = GenerationOutput(
            text=comment_text, selection_id="sel1"
        )
        agent = Agent(
            autonomy=AutonomyLevel.AUTO,
            memory=MemoryStore(path=tmp_path / "memory.json"),
            client=client,
            scheduler=scheduler,
            content=content,
        )
        return agent, client, scheduler

    @patch("contemplative_agent.adapters.moltbook.feed_manager.record_publish_outcome")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(0.95),
    )
    def test_comment_path_records_published(self, _score, record, _s1, _s2, tmp_path):
        agent, client, scheduler = self._agent(tmp_path)
        agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, client, scheduler)
        record.assert_called_once()
        assert record.call_args.args[0] == "sel1"
        assert record.call_args.kwargs["comment_id"] == "c1"
        assert record.call_args.kwargs["publish_status"] == ss.PUBLISH_PUBLISHED

    @patch("contemplative_agent.adapters.moltbook.feed_manager.record_publish_outcome")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(0.95),
    )
    def test_comment_path_records_a_missing_id(self, _score, record, _s1, _s2, tmp_path):
        agent, client, scheduler = self._agent(tmp_path, created={})
        agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, client, scheduler)
        assert record.call_args.kwargs["comment_id"] is None
        assert record.call_args.kwargs["publish_status"] == ss.PUBLISH_ID_UNKNOWN

    @patch("contemplative_agent.adapters.moltbook.feed_manager.record_publish_outcome")
    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.score_relevance_detailed",
        return_value=_scored(0.95),
    )
    def test_comment_path_records_a_client_failure(self, _score, record, _s1, _s2, tmp_path):
        from contemplative_agent.adapters.moltbook.client import MoltbookClientError

        agent, client, scheduler = self._agent(tmp_path)
        client.post_comment.side_effect = MoltbookClientError("boom")
        agent._feed_manager.engage_with_post({"content": "text", "id": "post1"}, client, scheduler)
        assert record.call_args.kwargs["publish_status"] == ss.PUBLISH_FAILED
        assert record.call_args.kwargs["comment_id"] is None

    # The reply path records through publish.publish_outcome now; reply_handler
    # keeps its own import only for the declined-before-publish row.
    @patch("contemplative_agent.adapters.moltbook.publish.record_publish_outcome")
    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply")
    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_internal_note")
    def test_reply_path_records_published(self, note, reply, record, _s1, _s2, tmp_path):
        note.return_value = "note"
        reply.return_value = GenerationOutput(text="a reply", selection_id="sel2")
        agent, client, scheduler = self._agent(tmp_path)
        agent._reply_handler._process_reply(
            client=client,
            scheduler=scheduler,
            post_id="post1",
            reply_key="post1:cx",
            their_content="hello",
            original_post="",
            replier_id="a1",
            replier_name="Other",
            comment_id="cx",
        )
        record.assert_called_once()
        assert record.call_args.args[0] == "sel2"
        assert record.call_args.kwargs["publish_status"] == ss.PUBLISH_PUBLISHED


class TestNoPasteResidue:
    def test_publish_module_holds_no_feed_cache_ttl(self):
        """The feed cache TTL belongs to feed_manager; a second definition in
        publish.py is dead and drifts (security review 2026-09-09)."""
        import inspect

        from contemplative_agent.adapters.moltbook import publish

        assert "_FEED_CACHE_TTL" not in inspect.getsource(publish)


class TestDeclinedPublishIsARecord:
    """An approval-gated run that declines is not the same event as an
    internal failure; both used to be an absent row (code review 2026-09-09)."""

    @patch("contemplative_agent.adapters.moltbook.reply_handler.record_publish_outcome")
    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_reply")
    @patch("contemplative_agent.adapters.moltbook.reply_handler.generate_internal_note")
    @patch("builtins.input", return_value="n")
    def test_reply_decline_records_declined(self, _input, note, reply, record, tmp_path):
        from contemplative_agent.adapters.moltbook.agent import Agent, AutonomyLevel
        from contemplative_agent.core.memory import MemoryStore

        note.return_value = "note"
        reply.return_value = GenerationOutput(text="a reply", selection_id="sel9")
        client = MagicMock()
        client.has_write_budget.return_value = True
        scheduler = MagicMock()
        scheduler.can_comment.return_value = True
        agent = Agent(
            autonomy=AutonomyLevel.APPROVE,
            memory=MemoryStore(path=tmp_path / "memory.json"),
            client=client,
            scheduler=scheduler,
        )
        agent._reply_handler._process_reply(
            client=client,
            scheduler=scheduler,
            post_id="post1",
            reply_key="post1:cx",
            their_content="hello",
            original_post="",
            replier_id="a1",
            replier_name="Other",
            comment_id="cx",
        )
        client.post_comment.assert_not_called()
        record.assert_called_once()
        assert record.call_args.kwargs["publish_status"] == ss.PUBLISH_DECLINED
        assert record.call_args.kwargs["comment_id"] is None


class TestIdLengthCap:
    def test_a_legal_but_enormous_id_is_rejected(self):
        from contemplative_agent.adapters.moltbook.publish import created_comment_id
        from contemplative_agent.core.config import is_valid_id

        huge = "a" * 5000
        assert created_comment_id({"id": huge}) is None
        assert is_valid_id(huge) is False
        assert created_comment_id({"id": "abc-123"}) == "abc-123"
        assert is_valid_id("abc-123") is True

    def test_create_post_envelope_obeys_the_same_cap(self):
        """The create-post gate used to apply the pattern without the cap, so
        the one id that reaches memory and the novelty sidecar was the one id
        with no length bound (simplify follow-up P6)."""
        from contemplative_agent.adapters.moltbook.post_pipeline import (
            parse_created_post_response,
        )

        resp = MagicMock()
        resp.json.return_value = {"success": True, "post": {"id": "a" * 5000}}
        assert parse_created_post_response(resp) == ("", {})
        resp.json.return_value = {"success": True, "post": {"id": "p1"}}
        assert parse_created_post_response(resp) == ("p1", {"id": "p1"})
