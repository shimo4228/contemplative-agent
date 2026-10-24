"""P3-05.8: skill -> pattern lineage in the skill frontmatter; prompt bytes unchanged."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from contemplative_agent.cli.adopt import _handle_adopt_staged
from contemplative_agent.cli.staging import StageItem, _stage_results
from contemplative_agent.core.llm import load_md_files
from contemplative_agent.core.text_utils import body_hash, split_frontmatter, stamp_skill_lineage

SKILL = (
    "---\n"
    "name: affirm-possibility\n"
    'description: "Reframe ambiguity."\n'
    "origin: auto-extracted\n"
    "---\n\n"
    "# Affirm Possibility\n\n**Context:** When closure pressure rises.\n\n## Solution\nHold it open.\n"
)


def test_stamp_adds_lineage_keys_and_keeps_existing_ones() -> None:
    out = stamp_skill_lineage(
        SKILL,
        source_ids=["aaa111", "bbb222"],
        adopted_at="2026-10-24T00:00:00+00:00",
        generated_by="m:1",
    )
    fm, _ = split_frontmatter(out)
    assert "name: affirm-possibility" in fm and "origin: auto-extracted" in fm
    assert "source_ids: [aaa111, bbb222]" in fm
    assert "adopted_at: 2026-10-24T00:00:00+00:00" in fm
    assert "generated_by: m:1" in fm
    assert f"body_hash: {body_hash(SKILL)}" in fm
    assert "audit_content_hash" not in fm


def test_absent_values_write_no_key_and_no_frontmatter_is_untouched() -> None:
    out = stamp_skill_lineage(SKILL, source_ids=None, adopted_at="t", generated_by=None)
    fm, _ = split_frontmatter(out)
    assert "source_ids" not in fm and "generated_by" not in fm
    bare = "# Just a body\n"
    assert stamp_skill_lineage(bare, source_ids=["a"], adopted_at="t", generated_by="m") == bare


def test_injected_system_prompt_is_byte_identical_before_and_after_stamping(tmp_path: Path) -> None:
    before = tmp_path / "before"
    after = tmp_path / "after"
    before.mkdir()
    after.mkdir()
    (before / "s.md").write_text(SKILL, encoding="utf-8")
    stamped = stamp_skill_lineage(
        SKILL, source_ids=["aaa111"], adopted_at="2026-10-24T00:00:00+00:00", generated_by="m:1"
    )
    (after / "s.md").write_text(stamped, encoding="utf-8")
    assert stamped != SKILL
    assert load_md_files(before, "skills") == load_md_files(after, "skills")
    assert load_md_files(after, "skills") != ""


def test_adopt_staged_stamps_lineage_into_the_written_skill(tmp_path: Path) -> None:
    staged_dir = tmp_path / ".staged"
    audit = tmp_path / "logs" / "audit.jsonl"
    target = tmp_path / "skills" / "affirm-possibility-20261024.md"
    item = StageItem(
        "affirm-possibility-20261024.md", SKILL, target, source_ids=["aaa111", "bbb222"]
    )
    with (
        patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
        patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
        patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        patch("contemplative_agent.cli.staging.served_model", return_value="gen-model:1"),
    ):
        _stage_results([item], command="insight")
    with (
        patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
        patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
        patch("contemplative_agent.cli.approval.AUDIT_LOG_PATH", audit),
        patch("builtins.input", side_effect=["y"]),
    ):
        _handle_adopt_staged(argparse.Namespace(yes=False), MagicMock())
    written = target.read_text(encoding="utf-8")
    fm, body = split_frontmatter(written)
    assert "source_ids: [aaa111, bbb222]" in fm
    assert "generated_by: gen-model:1" in fm
    assert "adopted_at: " in fm
    assert body.strip() == split_frontmatter(SKILL)[1].strip()
    # the audit row describes the bytes written (stamps included)
    import hashlib

    rows = [json.loads(line) for line in audit.read_text().splitlines()]
    adopted = [r for r in rows if r["source"] == "stage-adopted"][-1]
    assert adopted["content_hash"] == hashlib.sha256(written.encode()).hexdigest()[:16]


def test_reach_script_resolves_stamped_skills_and_flags_unlineaged_ones(tmp_path: Path) -> None:
    import importlib.util

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "reach", root / "scripts" / "skill_provenance_reach.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    from contemplative_agent.core.knowledge_store import pattern_id

    rows = [
        {"pattern": "p1", "distilled": "2026-10-01T00:00+00:00"},
        {"pattern": "p2", "distilled": "2026-10-02T00:00+00:00"},
    ]
    (tmp_path / "skills").mkdir()
    (tmp_path / "knowledge.json").write_text(json.dumps(rows), encoding="utf-8")
    ids = [pattern_id(r) for r in rows]
    good = stamp_skill_lineage(SKILL, source_ids=ids, adopted_at="t", generated_by="m")
    (tmp_path / "skills" / "good.md").write_text(good, encoding="utf-8")
    results, code = mod.reach(tmp_path)
    assert code == 0 and results[0]["status"] == "reached" and results[0]["reached"] == 2

    (tmp_path / "skills" / "old.md").write_text(SKILL, encoding="utf-8")
    results, code = mod.reach(tmp_path)
    assert code == 1
    assert {r["skill"]: r["status"] for r in results} == {
        "good.md": "reached",
        "old.md": "no-lineage",
    }
