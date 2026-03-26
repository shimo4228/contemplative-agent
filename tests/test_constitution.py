"""Tests for constitution amendment."""

import json
from unittest.mock import patch

from contemplative_agent.core.constitution import amend_constitution, MIN_PATTERNS_REQUIRED
from contemplative_agent.core.memory import KnowledgeStore


SAMPLE_CONSTITUTION = """# Test Constitutional Clauses

Principle A:
- "First clause about principle A."
- "Second clause about principle A."

Principle B:
- "First clause about principle B."
"""

AMENDED_CONSTITUTION = """# Test Constitutional Clauses

Principle A:
- "First clause about principle A."
- "Second clause about principle A, refined with experience."

Principle B:
- "First clause about principle B."
- "New clause learned from ethical experience."
"""


def _make_constitutional_knowledge(tmp_path, n=5):
    """Helper: create KnowledgeStore with n constitutional patterns."""
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(n):
        ks.add_learned_pattern(
            f"Constitutional pattern {i}: ethical insight about compassion and care number {i}",
            category="constitutional",
            importance=0.8,
        )
    ks.save()
    return KnowledgeStore(path=tmp_path / "knowledge.json")


def _setup_constitution(tmp_path):
    """Helper: create constitution directory with sample file."""
    const_dir = tmp_path / "constitution"
    const_dir.mkdir()
    (const_dir / "contemplative-axioms.md").write_text(SAMPLE_CONSTITUTION)
    return const_dir


class TestAmendConstitution:

    def test_no_constitutional_patterns_returns_early(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
        )
        assert "Insufficient" in result

    def test_insufficient_patterns_returns_early(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Single pattern about ethics and care",
                               category="constitutional")
        ks.save()
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks2, constitution_dir=const_dir,
        )
        assert "Insufficient" in result
        assert f"1/{MIN_PATTERNS_REQUIRED}" in result

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    def test_no_constitution_file_returns_early(self, tmp_path):
        ks = _make_constitutional_knowledge(tmp_path)
        empty_dir = tmp_path / "empty_constitution"
        empty_dir.mkdir()

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=empty_dir,
        )
        assert "No constitution file" in result

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    def test_no_constitution_dir_returns_early(self, tmp_path):
        ks = _make_constitutional_knowledge(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=None,
        )
        assert "No constitution directory" in result

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    @patch("contemplative_agent.core.constitution.generate")
    def test_dry_run_does_not_write(self, mock_generate, tmp_path):
        mock_generate.return_value = AMENDED_CONSTITUTION
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)
        original = (const_dir / "contemplative-axioms.md").read_text()

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir, dry_run=True,
        )
        assert "refined with experience" in result
        assert (const_dir / "contemplative-axioms.md").read_text() == original
        assert not (const_dir / ".last_constitution_amend").exists()

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    @patch("contemplative_agent.core.constitution.generate")
    def test_basic_amendment(self, mock_generate, tmp_path):
        mock_generate.return_value = AMENDED_CONSTITUTION
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
        )
        assert "refined with experience" in result
        written = (const_dir / "contemplative-axioms.md").read_text()
        assert "refined with experience" in written

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    @patch("contemplative_agent.core.constitution.generate", return_value=None)
    def test_llm_failure_returns_error(self, mock_generate, tmp_path):
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)
        original = (const_dir / "contemplative-axioms.md").read_text()

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
        )
        assert "LLM failed" in result
        assert (const_dir / "contemplative-axioms.md").read_text() == original

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    @patch("contemplative_agent.core.constitution.generate")
    def test_forbidden_pattern_validation(self, mock_generate, tmp_path):
        mock_generate.return_value = "My api_key is secret."
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)
        original = (const_dir / "contemplative-axioms.md").read_text()

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
        )
        assert "api_key" in result
        assert (const_dir / "contemplative-axioms.md").read_text() == original

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT", "")
    def test_missing_prompt_template(self, tmp_path):
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
        )
        assert "prompt template not found" in result

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    @patch("contemplative_agent.core.constitution.generate")
    def test_writes_timestamp_marker(self, mock_generate, tmp_path):
        mock_generate.return_value = AMENDED_CONSTITUTION
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)

        amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
        )
        marker = const_dir / ".last_constitution_amend"
        assert marker.exists()
        assert "202" in marker.read_text()  # ISO timestamp starts with year
