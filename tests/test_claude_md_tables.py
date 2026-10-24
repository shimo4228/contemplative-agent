"""CLAUDE.md tables vs the tree (P1-09.2): skills, sibling repos, docs layout."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")

_SIBLINGS = (
    "contemplative-agent-rules",
    "contemplative-agent-data",
    "contemplative-agent-cloud",
    "contemplative-agent-mlx",
    "contemplative-agent-otel",
    "agent-knowledge-cycle",
    "agent-attribution-practice",
)


def _tracked_skills() -> set[str]:
    # tracked files only, so an untracked local skill cannot split local and CI results
    out = subprocess.run(
        ["git", "ls-files", ".claude/skills/*/SKILL.md"], cwd=ROOT, capture_output=True, text=True
    )
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return {line.split("/")[2] for line in out.stdout.splitlines() if line}


@pytest.mark.unit
def test_skills_table_rows_equal_tracked_skills() -> None:
    section = CLAUDE.split("## プロジェクト固有 skills", 1)[1].split("\n## ", 1)[0]
    rows = set(re.findall(r"^\| `([^`]+)` \|", section, flags=re.MULTILINE))
    assert rows == _tracked_skills()


@pytest.mark.unit
@pytest.mark.parametrize("doc", ["CLAUDE.md", "README.md"])
def test_sibling_repositories_are_listed(doc: str) -> None:
    text = (ROOT / doc).read_text(encoding="utf-8")
    missing = [r for r in _SIBLINGS if f"/{r}" not in text]
    assert not missing, f"{doc} does not list {missing}"


@pytest.mark.unit
def test_docs_layout_names_every_docs_entry() -> None:
    section = CLAUDE.split("## ドキュメント配置", 1)[1].split("\n## ", 1)[0]
    entries = {p.name for p in (ROOT / "docs").iterdir() if not p.name.endswith(".ja.md")}
    missing = sorted(n for n in entries if f"docs/{n}" not in section)
    assert not missing, f"CLAUDE.md 配置節 does not name docs/{missing}"
