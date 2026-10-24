"""P3-04.12: section -> technique map per constitution version."""

from __future__ import annotations

import json
from pathlib import Path

from contemplative_agent.core.constitution_lineage import (
    sections_of,
    technique_key,
    upsert_lineage,
)

SEED_DIR = (
    Path(__file__).resolve().parent.parent
    / "docs"
    / "evidence"
    / "value-history"
    / "seed"
    / "constitution"
    / "history"
)
TECHNIQUES = {"emptiness", "non_duality", "mindfulness", "boundless_care"}


def test_technique_key_follows_renames():
    assert technique_key("Emptiness") == technique_key("Emptiness & Flow") == "emptiness"
    assert technique_key("Non-Duality") == technique_key("Non-Duality & Unity") == "non_duality"
    assert technique_key("Mindfulness") == technique_key("Mindful Monitoring") == "mindfulness"
    assert (
        technique_key("Boundless Care") == technique_key("Boundless Compassion") == "boundless_care"
    )


def test_structure_change_raises_a_null():
    """A renamed or new section with no counterpart reads null, never a guess."""
    text = 'Emptiness:\n- "a"\n- "b"\n\n**Reification Awareness:**\n- "c"\n- "d"\n'
    secs = sections_of(text)
    assert [s["technique_key"] for s in secs] == ["emptiness", None]
    assert [s["clause_count"] for s in secs] == [2, 2]


def test_clause_hashes_are_per_clause_and_stable():
    secs = sections_of('Emptiness:\n- "one"\n- "two"\n')
    assert (
        len(secs[0]["clause_sha12"]) == 2
        and secs[0]["clause_sha12"][0] != secs[0]["clause_sha12"][1]
    )
    assert sections_of('Emptiness:\n- "one"\n- "two"\n') == secs


def test_header_comments_and_blank_sections_are_ignored():
    secs = sections_of('# Title\n# Source: x\n\nEmptiness:\n- "one"\n\nEmpty heading:\n')
    assert [s["heading"] for s in secs] == ["Emptiness"]


def test_every_seed_version_has_four_mapped_sections_of_two_clauses():
    """The four recorded versions map 1:1 onto the techniques the AILuminate rows use."""
    files = sorted(SEED_DIR.glob("*.md"))
    assert len(files) == 4
    for f in files:
        secs = sections_of(f.read_text())
        assert [s["clause_count"] for s in secs] == [2, 2, 2, 2], f.name
        assert {s["technique_key"] for s in secs} == TECHNIQUES, f.name


def test_seed_lineage_json_matches_the_seed_texts():
    doc = json.loads((SEED_DIR / "lineage.json").read_text())
    assert doc["schema_version"] == 1
    assert set(doc["versions"]) == {f.name for f in SEED_DIR.glob("*.md")}
    for name, entry in doc["versions"].items():
        assert entry["sections"] == sections_of((SEED_DIR / name).read_text()), name


def test_upsert_keeps_other_versions(tmp_path: Path):
    path = tmp_path / "lineage.json"
    upsert_lineage(path, "a.md", 'Emptiness:\n- "x"\n')
    doc = upsert_lineage(path, "b.md", 'Mindfulness:\n- "y"\n')
    assert set(doc["versions"]) == {"a.md", "b.md"}
    assert json.loads(path.read_text()) == doc
    path.write_text("not json")
    assert set(upsert_lineage(path, "c.md", 'Emptiness:\n- "z"\n')["versions"]) == {"c.md"}
