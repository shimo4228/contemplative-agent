"""Documentation-integrity gates: relative links and ADR translation pairing.

Relative markdown links rot silently when files move (ADR-0079 module
reorganization left 24 broken links behind); this gate makes every pytest
run verify that each relative link in tracked ``*.md`` files resolves.

Existence is not the only way a link can be wrong. The ADR index in
``README.ja.md`` pointed rows 0001–0012 at the *English* canonical while every
later row pointed at the ``.ja.md`` twin, so a Japanese reader clicking an
early ADR silently left their language. No gate could see it: the target file
exists, so ``test_relative_markdown_links_resolve`` passes, and
``scripts/docs_consistency_scan.py``'s ``broken_link`` check asks the same
existence question. ``test_adr_index_rows_link_to_their_own_language`` closes
that hole for the index specifically.

Deliberately *not* generalized to every ja document (T-ADR-INDEX-JA,
2026-08-15): ~190 links across the ja corpus still point at an en file that
has a ja twin (203 before the 12 index rows this gate repaired), and some are
correct by construction — ``README.ja.md``'s first line is the language
switcher, whose whole job is to link to the English page. The index table
carries no such exception, which is what makes a hard gate right there and
wrong corpus-wide.
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

# An ADR index row: `| [0001](0001-slug.md) | Title | status | date |`.
_INDEX_ROW_RE = re.compile(r"^\|\s*\[(\d{4})\]\(([^)]+)\)")


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


@pytest.mark.unit
@pytest.mark.parametrize("readme, suffix", [("README.md", ".md"), ("README.ja.md", ".ja.md")])
def test_adr_index_rows_link_to_their_own_language(readme: str, suffix: str) -> None:
    """Each index keeps the reader in its own language.

    The English index must link the English canonical and the Japanese index
    its ``.ja.md`` twin. Both targets exist for every ADR (enforced by
    ``test_adr_english_japanese_pairing`` above), so this is the one link
    defect an existence check cannot express — as is a row whose link text and
    target disagree (``| [0026](0027-noise-as-seed.md) |``), also checked here.

    The row set is compared against the ADRs on disk first. Without that, a
    change to the table's markdown would drop rows out of ``_INDEX_ROW_RE``
    and this test would pass on an empty list — green because it checked
    nothing. Same canary as ``test_every_face_states_a_status_for_every_adr``.
    """
    wrong: list[str] = []
    seen: set[str] = set()
    for lineno, line in enumerate((ADR_DIR / readme).read_text(encoding="utf-8").splitlines(), 1):
        match = _INDEX_ROW_RE.match(line)
        if match is None:
            continue
        number, target = match.groups()
        seen.add(number)
        if target.endswith(".ja.md") != (suffix == ".ja.md"):
            wrong.append(f"{readme}:{lineno} ADR-{number} -> {target} (expected *{suffix})")
        elif not Path(target).name.startswith(f"{number}-"):
            wrong.append(f"{readme}:{lineno} ADR-{number} -> {target} (link text/target disagree)")

    on_disk = {
        md.name[:4]
        for md in ADR_DIR.glob("*.md")
        if not md.name.startswith("README") and md.name[:4].isdigit()
    }
    assert seen == on_disk, (
        f"{readme} index rows parsed ({len(seen)}) do not match the ADRs on disk "
        f"({len(on_disk)}) — missing {sorted(on_disk - seen)}, unexpected "
        f"{sorted(seen - on_disk)}; the check below covers only parsed rows"
    )
    assert not wrong, (
        f"ADR index rows link outside their own language — a reader of "
        f"{readme} lands on the other language's page:\n" + "\n".join(wrong)
    )
