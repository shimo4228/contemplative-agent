"""The contribution surface exists and does not hand-write tool versions (P1-13.5).

CONTRIBUTING.md points at the source of truth for tool versions (the ``dev``
group of pyproject.toml, verify.yml) instead of repeating numbers that drift.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    "CONTRIBUTING.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/proposal.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)


def test_contribution_files_exist() -> None:
    for rel in FILES:
        assert (ROOT / rel).is_file(), rel


def test_no_code_of_conduct_file() -> None:
    assert not (ROOT / "CODE_OF_CONDUCT.md").exists()


def test_contributing_names_verify_and_the_version_source_but_no_versions() -> None:
    text = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    assert "./.claude/verify.sh" in text
    assert "pyproject.toml" in text
    for tool in ("shellcheck", "markdownlint-cli2"):
        for m in re.finditer(rf"{tool}[^\n]{{0,12}}\d+\.\d+", text):
            raise AssertionError(f"hand-written version next to {tool}: {m.group(0)!r}")


def test_readmes_link_contributing_before_citation() -> None:
    for readme, heading in (("README.md", "## Citation"), ("README.ja.md", "## 引用")):
        text = (ROOT / readme).read_text(encoding="utf-8")
        assert "(CONTRIBUTING.md)" in text
        assert text.index("(CONTRIBUTING.md)") < text.index(heading)
