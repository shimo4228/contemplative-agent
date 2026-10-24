"""The AI-assisted-development disclosure reads the same on three faces.

README.md ("For tools and AI assistants" Facts), CITATION.cff ``notes`` and
.zenodo.json ``notes`` carry one sentence set (P1-13.4). A reader who meets only
the Zenodo record or only the citation file must not get a different account of
who writes the code than a reader of the README.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_LEAD = "AI-assisted development:"


def _readme_disclosure() -> str:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    m = re.search(rf"^- ({re.escape(_LEAD)}.*)$", text, flags=re.MULTILINE)
    assert m, "README.md Facts has no AI-assisted development line"
    return m.group(1)


def test_three_faces_carry_the_same_disclosure() -> None:
    readme = _readme_disclosure()
    cff_text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    m = re.search(r'^notes: "(.*)"$', cff_text, flags=re.MULTILINE)
    assert m, "CITATION.cff has no top-level notes"
    zenodo = json.loads((ROOT / ".zenodo.json").read_text(encoding="utf-8"))
    assert m.group(1) == readme
    assert zenodo["notes"] == readme


def test_japanese_readme_has_the_disclosure_line() -> None:
    text = (ROOT / "README.ja.md").read_text(encoding="utf-8")
    assert re.search(r"^- AI 支援開発:", text, flags=re.MULTILINE)


def test_disclosure_names_no_model_identifier() -> None:
    readme = _readme_disclosure()
    for banned in ("Opus", "Sonnet", "Haiku", "claude-"):
        assert banned not in readme
