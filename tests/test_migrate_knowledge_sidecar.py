"""Tests for scripts/migrate-knowledge-sidecar.py — the ADR-0108 cutover tool.

The script adds no migration logic of its own (the load/save path is the
migration); what it owns is the operator contract — refuse on a failed load,
write nothing on --dry-run, and report the half-states by name.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from contemplative_agent.core.knowledge_store import KnowledgeStore, pattern_id
from contemplative_agent.core.pattern_embeddings import PatternEmbeddingStore, sidecar_path_for

_SPEC = importlib.util.spec_from_file_location(
    "migrate_knowledge_sidecar",
    Path(__file__).resolve().parent.parent / "scripts" / "migrate-knowledge-sidecar.py",
)
assert _SPEC is not None and _SPEC.loader is not None
mks = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mks)


def _inline(tmp_path: Path, n: int = 3) -> Path:
    rows = [
        {
            "pattern": f"an inline pattern number {i}",
            "distilled": f"2026-09-0{i + 1}T00:00:00+00:00",
            "embedding": [float(i), float(i) + 0.5],
            "valid_until": None,
        }
        for i in range(n)
    ]
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


class TestMigrate:
    def test_moves_vectors_and_leaves_text_behind(self, tmp_path: Path, capsys):
        path = _inline(tmp_path)
        assert mks.migrate(path) == 3

        rows = json.loads(path.read_text(encoding="utf-8"))
        assert all("embedding" not in r for r in rows)
        assert PatternEmbeddingStore(sidecar_path_for(path)).count() == 3
        assert "inline_legacy" in capsys.readouterr().out

    def test_is_idempotent(self, tmp_path: Path):
        path = _inline(tmp_path)
        mks.migrate(path)
        first = path.read_text(encoding="utf-8")
        assert mks.migrate(path) == 3
        assert path.read_text(encoding="utf-8") == first

    def test_vectors_survive_the_migration(self, tmp_path: Path):
        path = _inline(tmp_path)
        mks.migrate(path)
        store = KnowledgeStore(path=path)
        store.load()
        assert [p["embedding"] for p in store.get_raw_patterns()] == [
            [0.0, 0.5],
            [1.0, 1.5],
            [2.0, 2.5],
        ]

    def test_dry_run_writes_nothing(self, tmp_path: Path):
        path = _inline(tmp_path)
        before = path.read_text(encoding="utf-8")
        mks.migrate(path, dry_run=True)
        assert path.read_text(encoding="utf-8") == before
        assert not sidecar_path_for(path).exists()

    def test_refuses_a_failed_load(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(SystemExit):
            mks.migrate(path)
        assert path.read_text(encoding="utf-8") == "{not json"

    def test_prune_removes_orphans_only_when_asked(self, tmp_path: Path):
        path = _inline(tmp_path)
        mks.migrate(path)
        sidecar = PatternEmbeddingStore(sidecar_path_for(path))
        sidecar.upsert_many([("deadbeefdead", np.zeros(2, dtype=np.float32))])

        mks.migrate(path)  # no --prune
        assert sidecar.count() == 4

        mks.migrate(path, prune=True)
        assert sidecar.count() == 3

    def test_reports_rows_with_no_vector_on_either_side(self, tmp_path: Path, capsys):
        path = tmp_path / "knowledge.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "pattern": "a pattern with no vector anywhere",
                        "distilled": "2026-09-01T00:00:00+00:00",
                        "valid_until": None,
                    }
                ]
            ),
            encoding="utf-8",
        )
        assert mks.migrate(path) == 0
        out = capsys.readouterr().out
        assert "sidecar_absent" in out
        assert "restore-embed-knowledge.py" in out


class TestMain:
    def test_missing_store_exits(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            mks.main(["--home", str(tmp_path)])

    def test_end_to_end_through_argv(self, tmp_path: Path):
        path = _inline(tmp_path)
        assert mks.main(["--home", str(tmp_path)]) == 0
        stored = PatternEmbeddingStore(sidecar_path_for(path)).get_all()
        assert stored is not None
        assert list(stored) == [pattern_id(r) for r in json.loads(path.read_text(encoding="utf-8"))]


class TestRefusesToShedRows:
    """A save rewrites the whole array, so a row the parser drops is deleted.

    This script is pointed at production data, so that must be a refusal, not
    a side effect of migrating something else (code review 2026-09-12).
    """

    def test_refuses_when_the_file_holds_unparseable_elements(self, tmp_path: Path):
        path = tmp_path / "knowledge.json"
        path.write_text(
            json.dumps(
                [
                    {"pattern": "a real row", "distilled": "2026-09-01T00:00:00+00:00"},
                    {"this_is": "not a pattern row"},
                ]
            ),
            encoding="utf-8",
        )
        before = path.read_text(encoding="utf-8")
        with pytest.raises(SystemExit):
            mks.migrate(path)
        assert path.read_text(encoding="utf-8") == before
        assert not sidecar_path_for(path).exists()
