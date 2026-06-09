"""Tests for core/text_utils — deterministic markdown/string transforms."""

import pytest

from contemplative_agent.core.text_utils import (
    MAX_SLUG_LENGTH,
    extract_title,
    slugify,
    split_frontmatter,
    strip_frontmatter,
    synthesize_frontmatter,
)


class TestSlugify:
    @pytest.mark.parametrize(
        "title,expected",
        [
            ("Hello World", "hello-world"),
            ("Already-Slugged", "already-slugged"),
            ("  !!Spaces & Symbols!!  ", "spaces-symbols"),
            ("Café Notes", "cafe-notes"),
            ("日本語タイトル", ""),
            ("Mix 日本語 and English", "mix-and-english"),
            ("", ""),
        ],
        ids=[
            "ascii-lowercase-hyphen",
            "already-slugged",
            "symbol-runs-collapsed-and-trimmed",
            "nfkd-accent-folding",
            "japanese-only-empty",
            "mixed-keeps-ascii-parts",
            "empty-string",
        ],
    )
    def test_slugify(self, title, expected):
        assert slugify(title) == expected

    def test_caps_at_max_slug_length(self):
        slug = slugify("word " * 30)
        assert len(slug) <= MAX_SLUG_LENGTH


class TestExtractTitle:
    def test_leading_heading_extracted_and_stripped(self):
        assert extract_title("# My Title  \nbody") == "My Title"

    def test_h2_not_matched(self):
        assert extract_title("## Subheading\nbody") is None

    def test_heading_on_later_line_detected(self):
        assert extract_title("intro line\n\n# Late Title\nbody") == "Late Title"

    def test_no_heading_returns_none(self):
        assert extract_title("just prose\nno heading") is None


class TestSplitFrontmatter:
    def test_no_frontmatter_returns_empty_block(self):
        text = "# Title\nbody"
        assert split_frontmatter(text) == ("", text)

    def test_normal_block_split(self):
        text = "---\nname: x\n---\n\n# Title\nbody"
        frontmatter, body = split_frontmatter(text)
        assert frontmatter == "---\nname: x\n---"
        assert body == "# Title\nbody"

    def test_unclosed_block_returns_text_unchanged(self):
        text = "---\nname: x\n# Title"
        assert split_frontmatter(text) == ("", text)

    def test_strip_equals_split_body(self):
        text = "---\nname: x\n---\nbody"
        assert strip_frontmatter(text) == split_frontmatter(text)[1]

    def test_round_trip(self):
        original = "---\nname: x\norigin: shimo4228\n---\n\n# Title\nbody"
        frontmatter, body = split_frontmatter(original)
        rejoined = f"{frontmatter}\n{body}"
        assert split_frontmatter(rejoined) == (frontmatter, body)


class TestSynthesizeFrontmatter:
    BODY = (
        "# Skill Title\n\n"
        "**Context:** First sentence here. Second sentence ignored.\n\n"
        "Details follow."
    )

    def test_full_body_fields(self):
        block = synthesize_frontmatter(self.BODY, origin="auto-extracted")
        assert "name: skill-title" in block
        assert 'description: "First sentence here."' in block
        assert "origin: auto-extracted" in block

    def test_missing_title_falls_back_to_skill(self):
        block = synthesize_frontmatter("**Context:** Something useful.\n")
        assert "name: skill" in block

    def test_missing_context_falls_back_to_title(self):
        block = synthesize_frontmatter("# Only Title\n\nbody")
        assert 'description: "Only Title"' in block

    def test_double_quotes_neutralised(self):
        body = '# T\n\n**Context:** Says "quoted" things.\n'
        block = synthesize_frontmatter(body)
        assert "description: \"Says 'quoted' things.\"" in block

    def test_round_trip_block_recovered(self):
        body = "# T\n\n**Context:** A summary.\n"
        block = synthesize_frontmatter(body)
        frontmatter, recovered_body = split_frontmatter(f"{block}\n\n{body}")
        assert frontmatter == block
        assert recovered_body == body
