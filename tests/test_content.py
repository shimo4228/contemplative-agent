"""Tests for content management."""

from unittest.mock import patch

from contemplative_agent.adapters.moltbook.content import (
    ContentManager,
    _content_hash,
)
from contemplative_agent.core.llm import GenerationOutput


class TestContentHash:
    def test_deterministic(self):
        assert _content_hash("hello") == _content_hash("hello")

    def test_different_inputs(self):
        assert _content_hash("hello") != _content_hash("world")


class TestContentManager:
    @patch("contemplative_agent.adapters.moltbook.content.generate_comment")
    def test_create_comment(self, mock_gen):
        mock_gen.return_value = GenerationOutput(text="Great insight about alignment!")
        mgr = ContentManager()
        result = mgr.create_comment("Some post about AI safety")
        assert result.text == "Great insight about alignment!"
        assert mgr._comment_count == 1

    @patch("contemplative_agent.adapters.moltbook.content.generate_comment")
    def test_create_comment_surfaces_thinking(self, mock_gen):
        # The reasoning trace rides along on the GenerationOutput so the caller
        # can persist it to the comment episode.
        mock_gen.return_value = GenerationOutput(
            text="A comment", thinking="weighing the post's framing"
        )
        mgr = ContentManager()
        result = mgr.create_comment("Some post", think=True)
        assert result.text == "A comment"
        assert result.thinking == "weighing the post's framing"
        mock_gen.assert_called_once()
        assert mock_gen.call_args.kwargs["think"] is True

    @patch("contemplative_agent.adapters.moltbook.content.generate_comment")
    def test_create_comment_duplicate_after_posted(self, mock_gen):
        # Dedup is against POSTED content: a comment is only skipped as a
        # duplicate once an identical text has been mark_posted (i.e. actually
        # published), not merely generated.
        mock_gen.return_value = GenerationOutput(text="Same comment")
        mgr = ContentManager()
        first = mgr.create_comment("Post A")
        assert first.text == "Same comment"
        mgr.mark_posted(first.text)
        result = mgr.create_comment("Post B")
        assert result.text is None

    @patch("contemplative_agent.adapters.moltbook.content.generate_comment")
    def test_create_comment_not_duplicate_until_posted(self, mock_gen):
        # A generated-but-not-yet-posted comment must NOT poison a same-session
        # retry of the same text (the gate may have rejected it, or posting may
        # have failed) — regression guard for the dedup-on-generate bug.
        mock_gen.return_value = GenerationOutput(text="Same comment")
        mgr = ContentManager()
        assert mgr.create_comment("Post A").text == "Same comment"
        assert mgr.create_comment("Post B").text == "Same comment"

    @patch("contemplative_agent.adapters.moltbook.content.generate_comment")
    def test_create_comment_llm_failure(self, mock_gen):
        mock_gen.return_value = GenerationOutput(text=None)
        mgr = ContentManager()
        assert mgr.create_comment("Post").text is None

    def test_comment_to_post_ratio(self):
        mgr = ContentManager()
        mgr._comment_count = 9
        mgr._post_count = 3
        assert mgr.comment_to_post_ratio == 3.0

    def test_comment_to_post_ratio_no_posts(self):
        mgr = ContentManager()
        mgr._comment_count = 5
        assert mgr.comment_to_post_ratio == 5.0
