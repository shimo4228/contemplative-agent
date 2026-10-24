"""P0-07.7: the amendment records how much of the store it saw, and the shape of what it read/wrote.

No Ollama: the generation seam and the view matcher are stubbed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from contemplative_agent.core.constitution import (
    AmendmentResult,
    amend_constitution,
    shape_reading,
)
from contemplative_agent.core.llm import GenerationOutput
from contemplative_agent.core.memory import KnowledgeStore
from contemplative_agent.core.snapshot import add_manifest_section
from contemplative_agent.core.views import View

CONSTITUTION = """# Title

**Emptiness:**
- "Clause one."
- "Clause two."

**Care:**
- "Clause three."
- unquoted clause four
"""


class TestShapeReading:
    def test_counts_colon_sections_clauses_and_quoted_rate(self):
        shape = shape_reading(CONSTITUTION)
        assert shape == {"sections": 2, "clauses": 4, "quoted_rate": 0.75}

    def test_plain_colon_headings(self):
        text = 'Emptiness:\n- "a"\nMindfulness:\n- "b"\n'
        assert shape_reading(text) == {"sections": 2, "clauses": 2, "quoted_rate": 1.0}

    def test_markdown_headings_when_no_colon_sections(self):
        text = '# One\n\n*   "a"\n\n# Two\n\n*   "b"\n*   "c"\n'
        assert shape_reading(text) == {"sections": 2, "clauses": 3, "quoted_rate": 1.0}

    def test_empty_text_has_no_rate(self):
        assert shape_reading("") == {"sections": 0, "clauses": 0, "quoted_rate": None}


def _store(tmp_path, n):
    ks = KnowledgeStore(path=tmp_path / "knowledge.json")
    for i in range(n):
        ks.add_learned_pattern(f"pattern number {i} about ethical insight")
    ks.save()
    return KnowledgeStore(path=tmp_path / "knowledge.json")


def test_amendment_result_carries_the_four_selection_values_and_shape(tmp_path):
    ks = _store(tmp_path, 8)
    const_dir = tmp_path / "constitution"
    const_dir.mkdir()
    (const_dir / "axioms.md").write_text(CONSTITUTION)

    registry = MagicMock()
    registry.find_by_view.side_effect = lambda name, candidates: list(candidates)[:5]
    registry.get.return_value = View(name="constitutional", seed_text="x", threshold=0.55, top_k=50)

    amended = CONSTITUTION + '- "Clause five."\n'
    out = GenerationOutput(text=amended, thinking="t")
    with (
        patch("contemplative_agent.core.constitution.generate_full", return_value=out),
        patch("contemplative_agent.core.constitution.validate_identity_content", return_value=True),
    ):
        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir, view_registry=registry
        )

    assert isinstance(result, AmendmentResult)
    sel = result.input_selection
    assert sel["matched_count"] == 5
    assert sel["live_count"] == 8
    assert sel["top_k"] == 50
    assert sel["threshold"] == 0.55
    assert sel["shape_current"] == {"sections": 2, "clauses": 4, "quoted_rate": 0.75}
    assert sel["shape_amended"]["clauses"] == 5


def test_selection_values_degrade_to_none_for_an_unknown_view(tmp_path):
    ks = _store(tmp_path, 4)
    const_dir = tmp_path / "constitution"
    const_dir.mkdir()
    (const_dir / "axioms.md").write_text(CONSTITUTION)
    registry = MagicMock()
    registry.find_by_view.side_effect = lambda name, candidates: list(candidates)
    registry.get.return_value = None
    out = GenerationOutput(text=CONSTITUTION, thinking=None)
    with (
        patch("contemplative_agent.core.constitution.generate_full", return_value=out),
        patch("contemplative_agent.core.constitution.validate_identity_content", return_value=True),
    ):
        result = amend_constitution(
            knowledge_store=ks, constitution_dir=const_dir, view_registry=registry
        )
    assert isinstance(result, AmendmentResult)
    assert result.input_selection["top_k"] is None
    assert result.input_selection["threshold"] is None
    assert result.input_selection["matched_count"] == 4


class TestAddManifestSection:
    def test_adds_one_key_and_keeps_the_rest(self, tmp_path):
        snap = tmp_path / "amend-constitution_x"
        snap.mkdir()
        (snap / "manifest.json").write_text(
            json.dumps({"command": "amend-constitution", "ts": "t"})
        )
        assert add_manifest_section(snap, "amendment_input", {"matched_count": 5}) is True
        data = json.loads((snap / "manifest.json").read_text())
        assert data["command"] == "amend-constitution"
        assert data["amendment_input"] == {"matched_count": 5}

    def test_missing_snapshot_is_a_quiet_false(self, tmp_path):
        assert add_manifest_section(None, "k", {}) is False
        assert add_manifest_section(tmp_path / "nope", "k", {}) is False

    def test_never_replaces_an_existing_key(self, tmp_path):
        snap = tmp_path / "s"
        snap.mkdir()
        (snap / "manifest.json").write_text(json.dumps({"command": "c"}))
        assert add_manifest_section(snap, "command", {"x": 1}) is False
        assert json.loads((snap / "manifest.json").read_text())["command"] == "c"


def test_amend_handler_writes_amendment_input_into_the_snapshot_manifest(tmp_path):
    """Wiring: _handle_amend_constitution -> snapshot manifest gets ``amendment_input``."""
    import argparse

    from contemplative_agent.cli import memory_cmds

    snap = tmp_path / "amend-constitution_x"
    snap.mkdir()
    (snap / "manifest.json").write_text(json.dumps({"command": "amend-constitution"}))
    result = AmendmentResult(
        text="t",
        target_path=tmp_path / "c.md",
        marker_dir=tmp_path,
        input_selection={
            "matched_count": 5,
            "live_count": 8,
            "top_k": 50,
            "threshold": 0.55,
            "shape_current": {"sections": 2, "clauses": 4, "quoted_rate": 0.75},
            "shape_amended": {"sections": 2, "clauses": 5, "quoted_rate": 0.8},
        },
    )
    args = argparse.Namespace(stage=False, constitution_dir=tmp_path)
    with (
        patch.object(memory_cmds.runtime, "_load_view_registry", return_value=MagicMock()),
        patch.object(memory_cmds.runtime, "_take_snapshot", return_value=snap),
        patch("contemplative_agent.core.memory.KnowledgeStore"),
        patch("contemplative_agent.core.constitution.amend_constitution", return_value=result),
        patch.object(memory_cmds, "_handle_single_result", return_value=False),
    ):
        memory_cmds._handle_amend_constitution(args, MagicMock())
    block = json.loads((snap / "manifest.json").read_text())["amendment_input"]
    assert {block[k] for k in ("matched_count", "live_count", "top_k", "threshold")} == {
        5,
        8,
        50,
        0.55,
    }
    assert block["shape_amended"]["clauses"] == 5
