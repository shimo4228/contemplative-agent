"""P0-06.7 — the release metadata check agrees with the tree and catches drift."""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "release_consistency_check", REPO_ROOT / "scripts" / "release_consistency_check.py"
)
assert _SPEC and _SPEC.loader
rcc = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rcc)


# The tests edit the tree's current values, so they read them instead of naming a release.
def _current(pattern: str, rel: str) -> str:
    match = re.search(pattern, (REPO_ROOT / rel).read_text(encoding="utf-8"), re.M)
    assert match, (rel, pattern)
    return match.group(1)


VERSION = _current(r'^version = "([^"]+)"', "pyproject.toml")
README_DOI = _current(r"doi\s+= \{(10\.5281/zenodo\.\d+)\}", "README.md")

FILES = (
    "pyproject.toml",
    "CITATION.cff",
    "codemeta.json",
    ".zenodo.json",
    "README.md",
    "README.ja.md",
    "llms-full.txt",
    "CHANGELOG.md",
    "docs/evidence/releases.md",
)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    for rel in FILES:
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO_ROOT / rel, dest)
    return tmp_path


def _edit(root: Path, rel: str, old: str, new: str, count: int = 1) -> None:
    path = root / rel
    text = path.read_text(encoding="utf-8")
    assert old in text, (rel, old)
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def test_the_repository_is_consistent():
    assert rcc.check(REPO_ROOT) == []
    assert rcc.main(["--root", str(REPO_ROOT)]) == 0


def test_copy_is_consistent(tree):
    assert rcc.check(tree) == []


def test_version_drift_in_citation(tree):
    _edit(tree, "CITATION.cff", f'version: "{VERSION}"', 'version: "0.0.1"')
    assert any("CITATION.cff version" in p for p in rcc.check(tree))


def test_version_drift_in_readme_bibtex(tree):
    _edit(tree, "README.ja.md", f"version      = {{{VERSION}}}", "version      = {0.0.1}")
    assert any("README.ja.md BibTeX version" in p for p in rcc.check(tree))


def test_changelog_head_must_match(tree):
    _edit(tree, "pyproject.toml", f'version = "{VERSION}"', 'version = "99.0.0"')
    problems = rcc.check(tree)
    assert any("CHANGELOG.md first version heading" in p for p in problems)


def test_citation_and_codemeta_must_name_one_doi(tree):
    _edit(tree, "codemeta.json", "zenodo.19212118", "zenodo.23340441", 1)
    assert any("different DOIs" in p for p in rcc.check(tree))


def test_citation_doi_must_be_concept_or_this_versions(tree):
    for rel in ("CITATION.cff", "codemeta.json"):
        path = tree / rel
        path.write_text(
            path.read_text(encoding="utf-8").replace("zenodo.19212118", "zenodo.22028295"),
            encoding="utf-8",
        )
    assert any("not the concept DOI" in p for p in rcc.check(tree))


def test_readme_doi_must_match_ledger_when_ledger_has_it(tree):
    _edit(
        tree,
        "README.md",
        f"doi          = {{{README_DOI}}}",
        "doi          = {10.5281/zenodo.11111111}",
    )
    assert any("README / llms-full.txt DOIs differ" in p for p in rcc.check(tree))


def test_ledger_snp_alone_is_refused(tree):
    path = tree / "docs/evidence/releases.md"
    text = path.read_text(encoding="utf-8")
    row = re.search(r"^\| v2\.13\.0 \|.*$", text, re.M)
    assert row
    cells = row.group(0).split("|")
    cells[6] = " swh:1:snp:" + "a" * 40 + " "
    path.write_text(text.replace(row.group(0), "|".join(cells)), encoding="utf-8")
    assert any("snp alone is not allowed" in p for p in rcc.check(tree))


def test_ledger_rel_form_is_accepted(tree):
    path = tree / "docs/evidence/releases.md"
    text = path.read_text(encoding="utf-8")
    row = re.search(r"^\| v2\.13\.0 \|.*$", text, re.M)
    assert row
    cells = row.group(0).split("|")
    cells[6] = " swh:1:rel:" + "b" * 40 + " "
    path.write_text(text.replace(row.group(0), "|".join(cells)), encoding="utf-8")
    assert rcc.check(tree) == []


def test_changelog_heading_doi_must_match_ledger(tree):
    _edit(
        tree,
        "CHANGELOG.md",
        "(2026-10-13)\n",
        "(2026-10-13) [DOI](https://doi.org/10.5281/zenodo.99999999)\n",
    )
    assert any("CHANGELOG heading of v2.13.0 has DOI 99999999" in p for p in rcc.check(tree))


def test_summary_sentence_drift(tree):
    _edit(tree, ".zenodo.json", "A long-running experiment", "A security-first experiment")
    assert any(".zenodo.json description" in p for p in rcc.check(tree))


def test_missing_file_is_exit_two(tree):
    (tree / "codemeta.json").unlink()
    assert rcc.main(["--root", str(tree)]) == 2
