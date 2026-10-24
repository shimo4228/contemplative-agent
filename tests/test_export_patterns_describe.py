"""P3-05.4: ``--describe`` schema tables, the id formula, unknown-field WARNING."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import logging
from pathlib import Path

from contemplative_agent.core.knowledge_store import KnowledgeStore, pattern_id

ROOT = Path(__file__).resolve().parent.parent


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "export_patterns_jsonl", ROOT / "scripts" / "export-patterns-jsonl.py"
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


ROWS = [
    {
        "pattern": "a",
        "distilled": "2026-04-01T10:00+00:00",
        "source": "2026-04-01",
        "gated": True,
        "provenance": {"source_type": "self_reflection"},
        "valid_from": "2026-04-01T10:00+00:00",
        "valid_until": None,
    },
    {
        "pattern": "b",
        "distilled": "2026-07-01T10:00+00:00",
        "source": "2026-07-01",
        "provenance": {
            "source_type": "mixed",
            "pipeline_version": "distill@0.60",
            "source_episode_ids": ["e"],
        },
        "valid_from": "2026-07-01T10:00+00:00",
        "valid_until": "2026-08-01T00:00+00:00",
    },
]


def test_datacard_id_formula_reproduces_the_store_id() -> None:
    mod = _load_script()
    for row in ROWS:
        raw = f"{row['distilled']}|{row['pattern']}"
        assert mod.pattern_id(row) == hashlib.sha256(raw.encode()).hexdigest()[:12]
        assert mod.pattern_id(row) == pattern_id(row)


def test_describe_counts_columns_and_versions(tmp_path: Path) -> None:
    mod = _load_script()
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps(ROWS), encoding="utf-8")
    out = mod.describe(path)
    assert "rows: 2" in out
    assert "| `gated` | 1 | 2026-04-01 | 2026-04-01 | ADR-0011 |" in out
    assert "| `provenance.pipeline_version` | 1 | 2026-07-01 |" in out
    assert "| `<none>` | 1 |" in out and "| `distill@0.60` | 1 |" in out
    assert "valid_until` non-null (soft-invalidated): 1" in out
    assert mod.ID_FORMULA in out
    assert mod.describe(path) == out  # deterministic


def test_unknown_row_field_logs_one_counted_warning(tmp_path: Path, caplog) -> None:
    path = tmp_path / "knowledge.json"
    rows = [dict(ROWS[0], mystery=1), dict(ROWS[1], mystery=2, importance=0.5)]
    path.write_text(json.dumps(rows), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        KnowledgeStore(path).load()
    msgs = [r.getMessage() for r in caplog.records if "unknown field" in r.getMessage()]
    assert len(msgs) == 1
    assert "'mystery': 2" in msgs[0]
    assert "importance" not in msgs[0]  # retired keys are dropped on purpose, not unknown


def test_known_and_retired_keys_do_not_warn(tmp_path: Path, caplog) -> None:
    path = tmp_path / "knowledge.json"
    path.write_text(json.dumps([dict(ROWS[0], importance=0.5, trust_score=0.9)]), encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        KnowledgeStore(path).load()
    assert not [r for r in caplog.records if "unknown field" in r.getMessage()]
