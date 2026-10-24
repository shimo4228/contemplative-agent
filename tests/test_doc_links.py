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


# --- index pages generated from / checked against the tree (P1-09.1) ---------

_EVIDENCE_DIR = PROJECT_ROOT / "docs" / "evidence"
_RUNBOOKS_DIR = PROJECT_ROOT / "docs" / "runbooks"
_BACKTICK_ROW_RE = re.compile(r"^\| `([^`]+)`", re.MULTILINE)


@pytest.mark.unit
def test_evidence_index_rows_match_directory() -> None:
    """`ls docs/evidence | grep -v README.md | wc -l` == rows of the table."""
    text = (_EVIDENCE_DIR / "README.md").read_text(encoding="utf-8")
    rows = [m.group(1).rstrip("/") for m in _BACKTICK_ROW_RE.finditer(text)]
    on_disk = sorted(p.name for p in _EVIDENCE_DIR.iterdir() if p.name != "README.md")
    assert sorted(rows) == on_disk, (
        "docs/evidence/README.md table and directory disagree — "
        "run `python3 scripts/gen_evidence_index.py`"
    )


@pytest.mark.unit
def test_evidence_index_is_generated() -> None:
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "gen_evidence_index.py"), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.unit
def test_runbooks_index_rows_match_directory() -> None:
    """`ls docs/runbooks/*.md` minus README == the `.md` rows of the table."""
    text = (_RUNBOOKS_DIR / "README.md").read_text(encoding="utf-8")
    rows = {m.group(1) for m in _BACKTICK_ROW_RE.finditer(text) if m.group(1).endswith(".md")}
    on_disk = {p.name for p in _RUNBOOKS_DIR.glob("*.md") if p.name != "README.md"}
    assert rows == on_disk, (
        f"docs/runbooks/README.md table vs directory — missing {sorted(on_disk - rows)}, "
        f"unexpected {sorted(rows - on_disk)}"
    )


# --- CONFIGURATION.md vs the code (P1-09.10) ----------------------------------

_CONFIG_EN = PROJECT_ROOT / "docs" / "CONFIGURATION.md"
_CONFIG_JA = PROJECT_ROOT / "docs" / "CONFIGURATION.ja.md"
_H2_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def _h2_headings(path: Path) -> list[str]:
    text = re.sub(r"```.*?```", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)
    return _H2_RE.findall(text)


def _toc_entries(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    head = text.split("\n---\n", 1)[0]
    return re.findall(r"^- \[[^\]]+\]\(#[^)]+\)$", head, flags=re.MULTILINE)


@pytest.mark.unit
@pytest.mark.parametrize("path", [_CONFIG_EN, _CONFIG_JA], ids=["en", "ja"])
def test_configuration_toc_lists_every_section(path: Path) -> None:
    headings = _h2_headings(path)
    assert len(_toc_entries(path)) == len(headings) - 1, (  # minus the TOC heading itself
        f"{path.name}: {len(_toc_entries(path))} TOC entries vs {len(headings) - 1} sections"
    )


@pytest.mark.unit
def test_configuration_en_and_ja_have_the_same_number_of_sections() -> None:
    assert len(_h2_headings(_CONFIG_EN)) == len(_h2_headings(_CONFIG_JA))


@pytest.mark.unit
@pytest.mark.parametrize("path", [_CONFIG_EN, _CONFIG_JA], ids=["en", "ja"])
def test_configuration_command_table_matches_registry(path: Path) -> None:
    from contemplative_agent.cli import COMMANDS

    text = path.read_text(encoding="utf-8")
    block = text.split("| Command |" if path is _CONFIG_EN else "| コマンド |", 1)[1].split(
        "\n\n", 1
    )[0]
    rows = {
        m.group(1): m.group(2)
        for m in re.finditer(r"^\| `([^`]+)` \| (\w+) \|", block, re.MULTILINE)
    }
    expected = {c.name: c.tier.value for c in COMMANDS}
    assert set(rows) == set(expected), (
        f"{path.name} command table vs registry: missing {sorted(set(expected) - set(rows))}, "
        f"unexpected {sorted(set(rows) - set(expected))}"
    )
    wrong = {n: (rows[n], expected[n]) for n in rows if rows[n] != expected[n]}
    assert not wrong, f"{path.name} tier column disagrees with the registry: {wrong}"


_CONFIRM_CALL_RE = re.compile(r'self\._confirm_(action|side_effect)\(\s*f?"([^"{]+)')


@pytest.mark.unit
@pytest.mark.parametrize("path", [_CONFIG_EN, _CONFIG_JA], ids=["en", "ja"])
def test_configuration_confirmation_table_matches_call_sites(path: Path) -> None:
    """The APPROVE side-effect table lists exactly the `_confirm_*` call sites."""
    code: set[tuple[str, str]] = set()
    for py in (PROJECT_ROOT / "src" / "contemplative_agent" / "adapters" / "moltbook").glob("*.py"):
        for kind, prefix in _CONFIRM_CALL_RE.findall(py.read_text(encoding="utf-8")):
            code.add((f"_confirm_{kind}", prefix.strip()))
    assert code, "no _confirm_* call sites found — the regex or the code moved"
    text = path.read_text(encoding="utf-8")
    documented = {
        (m.group(1), m.group(2).strip())
        for m in re.finditer(r"^\| [^|]+ \| `(_confirm_\w+)` \| `([^`]+)` \|$", text, re.MULTILINE)
    }
    assert documented == code, (
        f"{path.name}: documented {sorted(documented - code)} not in code; "
        f"code {sorted(code - documented)} not documented"
    )


@pytest.mark.unit
@pytest.mark.parametrize(
    "term",
    [
        # README "Core concepts"
        "episode log",
        "pattern",
        "view",
        "harness",
        "approval gate",
        "security by absence",
        # ADR-0101..0113 headline vocabulary and the weekly-document words (P1-09.15)
        "consumption plan",
        "codemap",
        "wiki mechanism",
        "novelty gate",
        "confusion pair",
        "comment outcome",
        "census status",
        "embedding sidecar",
        "dependency floor",
        "series projection",
        "insight entrance stages",
        "decision backend",
        "score4",
        "relevance gate",
        "fail-closed",
        "face gate",
        "weekly chain",
        "weekly gate",
        "triage loop",
        "dead-band",
        "value layer",
        "staging",
    ],
)
def test_glossary_defines_current_vocabulary(term: str) -> None:
    text = (PROJECT_ROOT / "docs" / "glossary.md").read_text(encoding="utf-8").lower()
    assert term.lower() in text


@pytest.mark.unit
def test_new_documents_are_reachable() -> None:
    """glossary (A), TROUBLESHOOTING and plans/README exist and are linked from README / CLAUDE.md (P1-09)."""
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    claude = (PROJECT_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert (PROJECT_ROOT / "docs" / "TROUBLESHOOTING.md").is_file()
    assert "docs/TROUBLESHOOTING.md" in readme
    assert (PROJECT_ROOT / "docs" / "plans" / "README.md").is_file()
    assert "docs/plans/README.md" in claude
    assert "docs/glossary.md" in readme or "glossary.md" in readme
