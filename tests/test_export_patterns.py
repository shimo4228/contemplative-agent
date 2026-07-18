"""Tests for scripts/export-patterns-jsonl.py — embedding-free projections.

The exporter is the single seam where knowledge.json leaves MOLTBOOK_HOME:
the HF mirror (jsonl) and the contemplative-agent-data repo copy (json)
both must drop the model-locked, re-derivable ``embedding`` field so the
public artifacts stay far under GitHub/HF file-size limits.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "export_patterns_jsonl",
    Path(__file__).resolve().parent.parent / "scripts" / "export-patterns-jsonl.py",
)
assert _SPEC is not None and _SPEC.loader is not None
epj = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(epj)

_ROWS = [
    {
        "pattern": "first pattern",
        "distilled": "2026-07-01T00:00+00:00",
        "embedding": [0.1] * 8,
        "valid_from": "2026-07-01T00:00+00:00",
        "valid_until": None,
    },
    {
        "pattern": "second pattern",
        "distilled": "2026-07-02T00:00+00:00",
        "embedding": [0.2] * 8,
        "valid_from": "2026-07-02T00:00+00:00",
        "valid_until": "2026-07-03T00:00+00:00",
    },
]


def _write_knowledge(tmp_path: Path) -> Path:
    knowledge = tmp_path / "knowledge.json"
    knowledge.write_text(json.dumps(_ROWS), encoding="utf-8")
    return knowledge


class TestJsonlExport:
    def test_drops_embedding_keeps_other_fields(self, tmp_path):
        out = tmp_path / "patterns.jsonl"
        count = epj.export(_write_knowledge(tmp_path), out)
        assert count == 2
        lines = out.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        for line, src in zip(lines, _ROWS, strict=True):
            row = json.loads(line)
            assert "embedding" not in row
            assert row["pattern"] == src["pattern"]
            assert row["valid_until"] == src["valid_until"]


class TestJsonExport:
    def test_writes_json_array_without_embedding(self, tmp_path):
        out = tmp_path / "knowledge.json"
        count = epj.export(_write_knowledge(tmp_path), out, fmt="json")
        assert count == 2
        rows = json.loads(out.read_text(encoding="utf-8"))
        assert isinstance(rows, list) and len(rows) == 2
        for row, src in zip(rows, _ROWS, strict=True):
            assert "embedding" not in row
            assert row["pattern"] == src["pattern"]
            assert row["valid_until"] == src["valid_until"]

    def test_json_export_is_reparseable_and_much_smaller(self, tmp_path):
        knowledge = _write_knowledge(tmp_path)
        out = tmp_path / "out.json"
        epj.export(knowledge, out, fmt="json")
        assert out.stat().st_size < knowledge.stat().st_size

    def test_rejects_unknown_format(self, tmp_path):
        with pytest.raises(ValueError):
            epj.export(_write_knowledge(tmp_path), tmp_path / "x", fmt="csv")
