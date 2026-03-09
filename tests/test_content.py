"""Tests for content management."""

from unittest.mock import patch

from contemplative_moltbook.content import (
    AXIOM_TEMPLATES,
    INTRODUCTION_TEMPLATE,
    ContentManager,
    _content_hash,
)


class TestContentHash:
    def test_deterministic(self):
        assert _content_hash("hello") == _content_hash("hello")

    def test_different_inputs(self):
        assert _content_hash("hello") != _content_hash("world")


class TestContentManager:
    def test_get_introduction_first_time(self):
        mgr = ContentManager()
        result = mgr.get_introduction()
        assert result is not None
        assert "contemplative" in result.lower()

    def test_get_introduction_duplicate(self):
        mgr = ContentManager()
        mgr.get_introduction()
        assert mgr.get_introduction() is None

    @patch("contemplative_moltbook.content.generate_comment")
    def test_create_comment(self, mock_gen):
        mock_gen.return_value = "Great insight about alignment!"
        mgr = ContentManager()
        result = mgr.create_comment("Some post about AI safety")
        assert result == "Great insight about alignment!"
        assert mgr._comment_count == 1

    @patch("contemplative_moltbook.content.generate_comment")
    def test_create_comment_duplicate(self, mock_gen):
        mock_gen.return_value = "Same comment"
        mgr = ContentManager()
        mgr.create_comment("Post A")
        result = mgr.create_comment("Post B")
        assert result is None

    @patch("contemplative_moltbook.content.generate_comment")
    def test_create_comment_llm_failure(self, mock_gen):
        mock_gen.return_value = None
        mgr = ContentManager()
        assert mgr.create_comment("Post") is None

    def test_comment_to_post_ratio(self):
        mgr = ContentManager()
        mgr._comment_count = 9
        mgr._post_count = 3
        assert mgr.comment_to_post_ratio == 3.0

    def test_comment_to_post_ratio_no_posts(self):
        mgr = ContentManager()
        mgr._comment_count = 5
        assert mgr.comment_to_post_ratio == 5.0

    def test_templates_contain_github_url(self):
        assert "github.com" in INTRODUCTION_TEMPLATE
        for template in AXIOM_TEMPLATES.values():
            assert "github.com" in template
