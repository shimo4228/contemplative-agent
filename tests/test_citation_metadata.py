"""P3-05.2 / P3-05.13: machine-readable citation metadata stays consistent."""

from __future__ import annotations

import json
from pathlib import Path

import tomllib

ROOT = Path(__file__).resolve().parent.parent
DATASET_DOI = "10.5281/zenodo.20732894"


def _json(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def test_zenodo_declares_the_dataset_and_has_no_mutable_main_url() -> None:
    raw = (ROOT / ".zenodo.json").read_text(encoding="utf-8")
    assert "/main/" not in raw
    rel = {(r["identifier"], r["relation"]) for r in _json(".zenodo.json")["related_identifiers"]}
    assert (DATASET_DOI, "isSupplementedBy") in rel


def test_huggingface_ids_are_lowercase_in_metadata_and_docs() -> None:
    for name in (".zenodo.json", "README.md", "README.ja.md", "CLAUDE.md"):
        assert "Shimo4228/" not in (ROOT / name).read_text(encoding="utf-8"), name


def test_citation_cff_references_the_dataset() -> None:
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    assert f'doi: "{DATASET_DOI}"' in text


def test_codemeta_carries_the_added_keys() -> None:
    data = _json("codemeta.json")
    for key in (
        "programmingLanguage",
        "runtimePlatform",
        "operatingSystem",
        "softwareRequirements",
        "issueTracker",
        "readme",
        "releaseNotes",
    ):
        assert data.get(key), key


def test_pyproject_urls_have_changelog_and_doi() -> None:
    urls = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["urls"]
    assert "Changelog" in urls and "DOI" in urls


def test_readme_citation_table_names_all_four_records_in_both_languages() -> None:
    for name in ("README.md", "README.ja.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for doi in ("19212118", DATASET_DOI.split(".")[-1], "19652013", "19200726"):
            assert f"10.5281/zenodo.{doi}" in text, (name, doi)


def test_graph_root_version_tracks_pyproject() -> None:
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    graph = _json("graph.jsonld")
    assert graph["version"] == version
    assert graph["dateModified"]
