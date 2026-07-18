"""Documentation-integrity gates: relative links and ADR translation pairing.

Relative markdown links rot silently when files move (ADR-0079 module
reorganization left 24 broken links behind); this gate makes every pytest
run verify that each relative link in tracked ``*.md`` files resolves.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ADR_DIR = PROJECT_ROOT / "docs" / "adr"

# Directories that hold generated or third-party content, never doc targets.
_EXCLUDED_PARTS = {".venv", ".notes", "dist", "node_modules", ".git"}

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)#\s]+)(#[^)]*)?\)")
_EXTERNAL_PREFIXES = ("http://", "https://", "mailto:")


def _markdown_files() -> list[Path]:
    return [p for p in PROJECT_ROOT.rglob("*.md") if not _EXCLUDED_PARTS.intersection(p.parts)]


@pytest.mark.unit
def test_relative_markdown_links_resolve() -> None:
    broken: list[str] = []
    for md in _markdown_files():
        text = md.read_text(encoding="utf-8", errors="replace")
        for match in _LINK_RE.finditer(text):
            target = match.group(1)
            if target.startswith(_EXTERNAL_PREFIXES):
                continue
            # GitHub renders /-prefixed targets relative to the repo root;
            # pathlib would otherwise resolve them against filesystem root.
            base = PROJECT_ROOT if target.startswith("/") else md.parent
            if not (base / target.lstrip("/")).resolve().exists():
                rel = md.relative_to(PROJECT_ROOT)
                broken.append(f"{rel}: {target}")
    assert not broken, (
        "Broken relative markdown links (fix the path, or de-link retired "
        "targets with an inline-code note as in ADR-0070 sweeps):\n" + "\n".join(broken)
    )


@pytest.mark.unit
def test_adr_english_japanese_pairing() -> None:
    """Every ADR ships as an en/ja pair — catch forgotten translations."""
    unpaired: list[str] = []
    for md in sorted(ADR_DIR.glob("*.md")):
        if md.name.startswith("README"):
            continue
        if md.name.endswith(".ja.md"):
            english = md.with_name(md.name.removesuffix(".ja.md") + ".md")
            if not english.exists():
                unpaired.append(f"orphan translation: {md.name}")
        else:
            japanese = md.with_name(md.name.removesuffix(".md") + ".ja.md")
            if not japanese.exists():
                unpaired.append(f"missing translation: {md.name}")
    assert not unpaired, "ADR en<->ja pairing violations:\n" + "\n".join(unpaired)
