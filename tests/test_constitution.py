"""Tests for constitution amendment."""

from unittest.mock import MagicMock, patch

from contemplative_agent.core.constitution import AmendmentResult, amend_constitution, MIN_PATTERNS_REQUIRED
from contemplative_agent.core.memory import KnowledgeStore


def _matching_view_registry():
    """Return a mock ViewRegistry whose 'constitutional' view matches all candidates.

    ADR-0026 Phase 2: amend_constitution retrieves patterns via
    ``view_registry.find_by_view('constitutional', ...)`` instead of a
    row-level category filter.
    """
    registry = MagicMock()
    registry.find_by_view.side_effect = (
        lambda name, candidates: list(candidates) if name == "constitutional" else []
    )
    return registry


def _empty_view_registry():
    """Return a mock ViewRegistry whose views match nothing (no constitutional pool)."""
    registry = MagicMock()
    registry.find_by_view.return_value = []
    return registry


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
    """Helper: create KnowledgeStore with n patterns (routed as constitutional via views).

    ADR-0026: the ``category`` field has been retired. The mock view
    registry returned by ``_matching_view_registry()`` matches every
    candidate against ``constitutional``, which is how the real
    ``amend_constitution`` now decides which patterns to feed to the
    amendment prompt.
    """
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(n):
        ks.add_learned_pattern(
            f"Constitutional pattern {i}: ethical insight about compassion and care number {i}",
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
            view_registry=_matching_view_registry(),
        )
        assert isinstance(result, str)
        assert "Insufficient" in result

    def test_requires_view_registry(self, tmp_path):
        """ADR-0026 Phase 2: missing view_registry is a clear error."""
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
        )
        assert isinstance(result, str)
        assert "ViewRegistry" in result

    def test_insufficient_patterns_returns_early(self, tmp_path):
        ks = KnowledgeStore(path=tmp_path / "knowledge.json")
        ks.add_learned_pattern("Single pattern about ethics and care")
        ks.save()
        ks2 = KnowledgeStore(path=tmp_path / "knowledge.json")
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks2, constitution_dir=const_dir,
            view_registry=_matching_view_registry(),
        )
        assert isinstance(result, str)
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
            view_registry=_matching_view_registry(),
        )
        assert isinstance(result, str)
        assert "No constitution file" in result

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    def test_no_constitution_dir_returns_early(self, tmp_path):
        ks = _make_constitutional_knowledge(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=None,
            view_registry=_matching_view_registry(),
        )
        assert isinstance(result, str)
        assert "No constitution directory" in result

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    @patch("contemplative_agent.core.constitution.generate")
    def test_returns_amendment_result(self, mock_generate, tmp_path):
        mock_generate.return_value = AMENDED_CONSTITUTION
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)
        original = (const_dir / "contemplative-axioms.md").read_text()

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
            view_registry=_matching_view_registry(),
        )
        assert isinstance(result, AmendmentResult)
        assert "refined with experience" in result.text
        assert result.target_path == const_dir / "contemplative-axioms.md"
        assert result.marker_dir == const_dir
        # Core function does not write — caller's responsibility
        assert (const_dir / "contemplative-axioms.md").read_text() == original
        assert not (const_dir / ".last_constitution_amend").exists()

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    @patch("contemplative_agent.core.constitution.generate", return_value=None)
    def test_llm_failure_returns_error(self, mock_generate, tmp_path):
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)
        original = (const_dir / "contemplative-axioms.md").read_text()

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
            view_registry=_matching_view_registry(),
        )
        assert isinstance(result, str)
        assert "LLM failed" in result
        assert (const_dir / "contemplative-axioms.md").read_text() == original

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT",
           "Amend: {current_constitution}\nPatterns: {constitutional_patterns}")
    @patch("contemplative_agent.core.constitution.generate")
    def test_forbidden_pattern_returns_string(self, mock_generate, tmp_path):
        mock_generate.return_value = "My api_key is secret."
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)
        original = (const_dir / "contemplative-axioms.md").read_text()

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
            view_registry=_matching_view_registry(),
        )
        # Validation failure returns str, not AmendmentResult
        assert isinstance(result, str)
        assert "api_key" in result
        assert (const_dir / "contemplative-axioms.md").read_text() == original

    @patch("contemplative_agent.core.constitution.CONSTITUTION_AMEND_PROMPT", "")
    def test_missing_prompt_template(self, tmp_path):
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
            view_registry=_matching_view_registry(),
        )
        assert isinstance(result, str)
        assert "prompt template not found" in result

    def test_empty_view_returns_early(self, tmp_path):
        """ADR-0026 Phase 2: patterns exist but no view match → Insufficient."""
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
            view_registry=_empty_view_registry(),
        )
        assert isinstance(result, str)
        assert "Insufficient" in result


class TestAmendConstitutionLineageADR0050:
    @patch("contemplative_agent.core.constitution.generate")
    def test_amendment_result_carries_lineage(self, mock_generate, tmp_path):
        """pattern_ids + epistemic_counts come from the view-matched list."""
        from contemplative_agent.core.knowledge_store import pattern_id

        mock_generate.return_value = AMENDED_CONSTITUTION
        ks = _make_constitutional_knowledge(tmp_path)
        const_dir = _setup_constitution(tmp_path)

        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir,
            view_registry=_matching_view_registry(),
        )
        assert isinstance(result, AmendmentResult)
        ks.load()
        live = ks.get_live_patterns()
        assert set(result.pattern_ids) == {pattern_id(p) for p in live}
        # Default provenance is unknown → everything tallies as unknown.
        assert result.epistemic_counts == {
            "observed": 0, "generated": 0, "unknown": len(live),
        }
