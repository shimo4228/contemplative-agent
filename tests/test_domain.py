"""Tests for domain configuration and prompt template loading."""

import json

import pytest

from contemplative_moltbook.domain import (
    DEFAULT_CONFIG_DIR,
    DEFAULT_DOMAIN_CONFIG_PATH,
    DEFAULT_PROMPTS_DIR,
    DEFAULT_RULES_DIR,
    DomainConfig,
    load_domain_config,
    load_prompt_templates,
    load_rules,
    reset_caches,
    resolve_prompt,
)


@pytest.fixture(autouse=True)
def _reset_domain_caches():
    """Reset caches before and after each test."""
    reset_caches()
    yield
    reset_caches()


class TestLoadDomainConfig:
    def test_loads_default_config(self):
        config = load_domain_config()
        assert config.name == "contemplative-ai"
        assert "alignment" in config.topic_keywords
        assert config.default_submolt == "alignment"
        assert 0.0 < config.relevance_threshold <= 1.0
        assert 0.0 < config.known_agent_threshold <= 1.0
        assert config.known_agent_threshold < config.relevance_threshold
        assert "github.com" in config.repo_url

    def test_subscribed_submolts(self):
        config = load_domain_config()
        assert "alignment" in config.subscribed_submolts
        assert "philosophy" in config.subscribed_submolts
        assert len(config.subscribed_submolts) >= 1

    def test_topic_keywords_str(self):
        config = load_domain_config()
        kw_str = config.topic_keywords_str
        assert "alignment" in kw_str
        assert ", " in kw_str

    def test_file_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_domain_config(tmp_path / "nonexistent.json")

    def test_missing_required_keys(self, tmp_path):
        bad_config = tmp_path / "bad.json"
        bad_config.write_text('{"name": "test"}')
        with pytest.raises(ValueError, match="missing required keys"):
            load_domain_config(bad_config)

    def test_forbidden_pattern_rejected(self, tmp_path):
        bad_config = tmp_path / "bad.json"
        data = {
            "name": "test",
            "description": "has api_key leak",
            "topic_keywords": [],
            "submolts": {"subscribed": [], "default": "x"},
            "thresholds": {"relevance": 0.5, "known_agent": 0.5},
        }
        bad_config.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="forbidden pattern"):
            load_domain_config(bad_config)

    def test_custom_config(self, tmp_path):
        custom = tmp_path / "custom.json"
        data = {
            "name": "custom-domain",
            "description": "A custom domain",
            "topic_keywords": ["math", "logic"],
            "submolts": {"subscribed": ["math"], "default": "math"},
            "thresholds": {"relevance": 0.5, "known_agent": 0.3},
            "repo_url": "https://example.com/repo",
        }
        custom.write_text(json.dumps(data))
        config = load_domain_config(custom)
        assert config.name == "custom-domain"
        assert config.topic_keywords == ("math", "logic")
        assert config.subscribed_submolts == ("math",)
        assert config.relevance_threshold == 0.5

    def test_frozen_dataclass(self):
        config = load_domain_config()
        with pytest.raises(AttributeError):
            config.name = "changed"  # type: ignore[misc]


class TestLoadPromptTemplates:
    def test_loads_all_templates(self):
        templates = load_prompt_templates()
        assert "Moltbook" in templates.system
        assert "{post_content}" in templates.relevance
        assert "{post_content}" in templates.comment
        assert "{feed_topics}" in templates.cooperation_post
        assert "{original_post}" in templates.reply
        assert "{feed_topics}" in templates.post_title
        assert "{combined_posts}" in templates.topic_extraction
        assert "{recent_topics}" in templates.topic_novelty
        assert "{post_content}" in templates.topic_summary
        assert "{submolt_list}" in templates.submolt_selection
        assert "{actions_text}" in templates.session_insight

    def test_directory_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_prompt_templates(tmp_path / "nonexistent")

    def test_missing_file(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        with pytest.raises(FileNotFoundError, match="system.md"):
            load_prompt_templates(prompts_dir)

    def test_empty_file_rejected(self, tmp_path):
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "system.md").write_text("")
        with pytest.raises(ValueError, match="empty"):
            load_prompt_templates(prompts_dir)

    def test_domain_placeholders_in_templates(self):
        templates = load_prompt_templates()
        assert "{topic_keywords}" in templates.relevance
        assert "{domain_name}" in templates.cooperation_post
        assert "{domain_name}" in templates.post_title


class TestLoadRules:
    def test_loads_contemplative_rules(self):
        rules = load_rules()
        assert "contemplative" in rules.introduction.lower()
        assert "mindfulness" in rules.axiom_templates
        assert "emptiness" in rules.axiom_templates
        assert "non_duality" in rules.axiom_templates
        assert "boundless_care" in rules.axiom_templates

    def test_introduction_has_repo_placeholder(self):
        rules = load_rules()
        assert "{repo_url}" in rules.introduction

    def test_axiom_templates_have_repo_placeholder(self):
        rules = load_rules()
        for key, template in rules.axiom_templates.items():
            assert "{repo_url}" in template, f"{key} missing {{repo_url}}"

    def test_directory_not_found(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_rules(tmp_path / "nonexistent")

    def test_empty_directory(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        rules = load_rules(rules_dir)
        assert rules.introduction == ""
        assert rules.axiom_templates == {}

    def test_custom_rules(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "introduction.md").write_text("Hello from custom domain")
        (rules_dir / "topic-a.md").write_text("Topic A content")
        (rules_dir / "topic-b.md").write_text("Topic B content")
        rules = load_rules(rules_dir)
        assert rules.introduction == "Hello from custom domain"
        assert "topic_a" in rules.axiom_templates
        assert "topic_b" in rules.axiom_templates

    def test_filename_to_key_conversion(self, tmp_path):
        rules_dir = tmp_path / "rules"
        rules_dir.mkdir()
        (rules_dir / "non-duality.md").write_text("content")
        (rules_dir / "boundless-care.md").write_text("content")
        rules = load_rules(rules_dir)
        assert "non_duality" in rules.axiom_templates
        assert "boundless_care" in rules.axiom_templates


class TestResolvePrompt:
    def test_replaces_domain_name(self):
        config = DomainConfig(
            name="test-domain",
            description="desc",
            topic_keywords=("a", "b"),
            subscribed_submolts=("x",),
            default_submolt="x",
            relevance_threshold=0.5,
            known_agent_threshold=0.3,
            repo_url="https://example.com",
        )
        result = resolve_prompt("About {domain_name} topics", config)
        assert result == "About test-domain topics"

    def test_replaces_topic_keywords(self):
        config = DomainConfig(
            name="test",
            description="desc",
            topic_keywords=("math", "logic"),
            subscribed_submolts=("x",),
            default_submolt="x",
            relevance_threshold=0.5,
            known_agent_threshold=0.3,
            repo_url="",
        )
        result = resolve_prompt("Topics: {topic_keywords}", config)
        assert result == "Topics: math, logic"

    def test_replaces_repo_url(self):
        config = DomainConfig(
            name="test",
            description="desc",
            topic_keywords=(),
            subscribed_submolts=(),
            default_submolt="x",
            relevance_threshold=0.5,
            known_agent_threshold=0.3,
            repo_url="https://github.com/example/repo",
        )
        result = resolve_prompt("See: {repo_url}", config)
        assert result == "See: https://github.com/example/repo"

    def test_preserves_unresolved_placeholders(self):
        config = DomainConfig(
            name="test",
            description="desc",
            topic_keywords=(),
            subscribed_submolts=(),
            default_submolt="x",
            relevance_threshold=0.5,
            known_agent_threshold=0.3,
            repo_url="",
        )
        result = resolve_prompt("{domain_name}: {post_content}", config)
        assert result == "test: {post_content}"

    def test_extra_vars(self):
        config = DomainConfig(
            name="test",
            description="desc",
            topic_keywords=(),
            subscribed_submolts=(),
            default_submolt="x",
            relevance_threshold=0.5,
            known_agent_threshold=0.3,
            repo_url="",
        )
        result = resolve_prompt("{domain_name} {custom}", config, custom="value")
        assert result == "test value"


class TestDefaultPaths:
    def test_default_config_dir_exists(self):
        assert DEFAULT_CONFIG_DIR.is_dir()

    def test_default_domain_config_exists(self):
        assert DEFAULT_DOMAIN_CONFIG_PATH.is_file()

    def test_default_prompts_dir_exists(self):
        assert DEFAULT_PROMPTS_DIR.is_dir()

    def test_default_rules_dir_exists(self):
        assert DEFAULT_RULES_DIR.is_dir()


class TestEndToEndIntegration:
    """Test the full flow: load config -> load templates -> resolve."""

    def test_relevance_prompt_resolved(self):
        config = load_domain_config()
        templates = load_prompt_templates()
        resolved = resolve_prompt(templates.relevance, config)
        # {topic_keywords} should be replaced
        assert "alignment" in resolved
        assert "philosophy" in resolved
        # {post_content} should be preserved for later formatting
        assert "{post_content}" in resolved

    def test_cooperation_post_prompt_resolved(self):
        config = load_domain_config()
        templates = load_prompt_templates()
        resolved = resolve_prompt(templates.cooperation_post, config)
        assert "contemplative-ai" in resolved
        assert "{feed_topics}" in resolved

    def test_rules_resolved_with_repo_url(self):
        config = load_domain_config()
        rules = load_rules()
        resolved_intro = resolve_prompt(rules.introduction, config)
        assert "github.com" in resolved_intro
        assert "{repo_url}" not in resolved_intro

    def test_axiom_templates_resolved(self):
        config = load_domain_config()
        rules = load_rules()
        for key, template in rules.axiom_templates.items():
            resolved = resolve_prompt(template, config)
            assert "{repo_url}" not in resolved, f"{key} still has unresolved {{repo_url}}"
            assert "github.com" in resolved, f"{key} missing repo URL"
