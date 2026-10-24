"""The shipped value-history seed is verbatim: each file hashes to the name it carries."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

SEED = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "value-history" / "seed"
_NAME = re.compile(r"-([0-9a-f]{12})\.md$")


def _seed_files() -> list[Path]:
    return sorted(SEED.rglob("*.md"))


def test_seed_is_present():
    assert len(_seed_files()) >= 9


def test_each_non_reconstructed_file_hashes_to_its_name():
    checked = 0
    for path in _seed_files():
        if "reconstructed" in path.name or path.name == "CHANGELOG.md":
            continue
        m = _NAME.search(path.name)
        assert m, f"{path.name}: no sha12 suffix"
        assert hashlib.sha256(path.read_bytes()).hexdigest()[:12] == m.group(1), path.name
        checked += 1
    assert checked >= 7


def test_reconstruction_declares_itself_and_has_no_hash_in_its_name():
    (path,) = [p for p in _seed_files() if "reconstructed" in p.name]
    assert not _NAME.search(path.name)
    assert path.read_text().startswith("# RECONSTRUCTED, NOT THE ADOPTED BYTES")


def test_value_layer_changelog_is_never_directly_under_constitution():
    """The runtime concatenates constitution/*.md; the ledger must live in history/."""
    assert (SEED / "constitution" / "history" / "CHANGELOG.md").is_file()
    assert not (SEED / "constitution" / "CHANGELOG.md").exists()


def test_changelog_final_constitution_row_matches_the_live_hash():
    text = (SEED / "constitution" / "history" / "CHANGELOG.md").read_text()
    live = next(SEED.glob("constitution/history/2026-08-09-*.md"))
    sha16 = hashlib.sha256(live.read_bytes()).hexdigest()[:16]
    assert f"`{sha16}`" in text
    assert "2026-08-09 (12:10:35Z)" in text


def test_constitution_versions_match_the_adr_0090_provenance():
    names = {p.name for p in (SEED / "constitution" / "history").glob("*.md")}
    assert "2026-05-05-3d8a8503509e.md" in names
    assert "2026-08-09-37e3556a40ea.md" in names
    assert "0000-initial-e3b556eac759.md" in names
