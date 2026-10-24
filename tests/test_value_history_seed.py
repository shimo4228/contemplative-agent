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
    assert len(_seed_files()) >= 8


def test_each_non_reconstructed_file_hashes_to_its_name():
    checked = 0
    for path in _seed_files():
        if "reconstructed" in path.name:
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


def test_constitution_versions_match_the_adr_0090_provenance():
    names = {p.name for p in (SEED / "constitution" / "history").glob("*.md")}
    assert "2026-05-05-3d8a8503509e.md" in names
    assert "2026-08-09-37e3556a40ea.md" in names
    assert "0000-initial-e3b556eac759.md" in names
