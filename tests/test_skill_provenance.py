"""Skills copied from a standalone repo record where they came from (P1-13.8).

Every tracked project skill either declares ``upstream:`` and ``edition:`` in
its frontmatter (a copy of a standalone repo's skill) or is one of the
repository-specific skills that have no upstream. The population is
``git ls-files '.claude/skills/*/SKILL.md'`` (tracked only), so an untracked
local skill cannot make CI and a laptop disagree. CLAUDE.md's skills table
carries the same ``edition`` word per row.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EDITIONS = ("ca-specific", "verbatim")
REPO_SPECIFIC = {
    "agent-run",
    "apple-silicon-local-llm-serving",
    "llm-pipeline-layering",
    "weekly-gate",
    "weekly-report",
}


def _tracked_skills() -> dict[str, str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", ".claude/skills/*/SKILL.md"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("git unavailable")
    return {Path(rel).parent.name: (ROOT / rel).read_text(encoding="utf-8") for rel in out.split()}


def _frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md has no frontmatter"
    return dict(re.findall(r"^([A-Za-z_-]+):[ \t]*(.*)$", m.group(1), re.M))


def test_every_tracked_skill_declares_provenance_or_is_repo_specific() -> None:
    skills = _tracked_skills()
    assert skills, "no tracked skills found"
    for name, text in skills.items():
        fm = _frontmatter(text)
        if name in REPO_SPECIFIC:
            assert "upstream" not in fm, f"{name}: repo-specific skill must not name an upstream"
            continue
        assert fm.get("upstream"), f"{name}: missing upstream (or add it to REPO_SPECIFIC)"
        assert fm.get("edition") in EDITIONS, f"{name}: edition must be one of {EDITIONS}"


def test_claude_md_table_carries_each_edition() -> None:
    skills = _tracked_skills()
    table = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    for name, text in skills.items():
        row = next((ln for ln in table.splitlines() if ln.startswith(f"| `{name}` |")), None)
        if row is None:
            continue  # rows for new skills are P1-09.2's count check, not this test
        edition = _frontmatter(text).get("edition")
        cell = row.rstrip().rstrip("|").rsplit("|", 1)[-1]
        if edition:
            assert f"`{edition}`" in cell, f"{name}: CLAUDE.md edition cell disagrees"
        else:
            assert "`verbatim`" not in cell and "`ca-specific`" not in cell
