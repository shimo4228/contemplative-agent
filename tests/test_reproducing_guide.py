"""P3-05.10: docs/REPRODUCING.md classifies every evidence script and instrument."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUIDE = (ROOT / "docs" / "REPRODUCING.md").read_text(encoding="utf-8")


def _scripts() -> list[Path]:
    found = sorted((ROOT / "docs" / "evidence").glob("*/*.py")) + sorted(
        (ROOT / "scripts").glob("*.py")
    )
    return [p.relative_to(ROOT) for p in found]


def test_every_evidence_script_and_instrument_is_in_the_guide() -> None:
    missing = [str(p) for p in _scripts() if f"`{p}`" not in GUIDE]
    assert missing == [], f"add these to a tier table in docs/REPRODUCING.md: {missing}"


def test_each_script_is_listed_in_exactly_one_tier_table() -> None:
    sections = GUIDE.split("### ")
    tier_sections = [s for s in sections if s.startswith(("Tier 1", "Tier 2", "Libraries"))]
    assert len(tier_sections) == 3
    for p in _scripts():
        hits = sum(1 for s in tier_sections if f"`{p}`" in s)
        assert hits >= 1, p
        # Tier 3 holds evals/ only; a script must not sit in both tier 1 and 2.
        assert not (f"`{p}`" in tier_sections[0] and f"`{p}`" in tier_sections[1]), p


def test_the_run_record_the_guide_cites_exists() -> None:
    assert (ROOT / "docs" / "evidence" / "p3-05" / "repro-run-20261024.md").is_file()
