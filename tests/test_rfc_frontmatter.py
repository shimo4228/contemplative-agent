"""The RFC ledger keeps one frontmatter form, and rfcs/README.md is generated from it.

``rfcs/README.md`` says the frontmatter is the single source of truth, but the
body used to carry a second ``## Status`` that drifted (38 of 45 disagreed
with the frontmatter on 2026-10-24) and the index table had no state column.
ROADMAP P1-02.1-.4. ``scripts/rfc_index.py`` owns the format check and the
index; the real-ledger tests below run it over every ``rfcs/NNNN-*.md``, the
synthetic ones pin each rule on its own.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rfc_index as ri  # type: ignore[import-not-found]  # noqa: E402

LEDGER = ri.load(ri.RFC_DIR)


_HYPHEN = {"review_when": "review-when", "admitted_by": "admitted-by"}


def _rfc(tmp_path: Path, **overrides: str | None) -> ri.Rfc:
    """A conforming open RFC, with fields overridden (None removes one)."""
    fields = {
        "title": "t",
        "state": "draft",
        "state_since": "2026-10-01",
        "review-when": "something changes",
        "alignment": "repair",
    }
    for key, value in overrides.items():
        key = _HYPHEN.get(key, key)
        if value is None:
            fields.pop(key, None)
        else:
            fields[key] = value
    text = "---\n" + "\n".join(f"{k}: {v}" for k, v in fields.items()) + "\n---\n\n## Summary\n\nx\n"
    path = tmp_path / "0999-x.md"
    path.write_text(text, encoding="utf-8")
    return ri.parse(path)


def test_ledger_is_not_empty() -> None:
    assert len(LEDGER) >= 54


@pytest.mark.parametrize("rfc", LEDGER, ids=lambda r: r.path.name)
def test_every_rfc_conforms(rfc: ri.Rfc) -> None:
    assert ri.validate(rfc) == []


def test_body_status_matches_frontmatter() -> None:
    """The one section that used to restate state either agrees or is gone."""
    stale = {
        r.path.name: (ri.body_status_first_word(r), r.state)
        for r in LEDGER
        if ri.body_status_first_word(r) not in (None, r.state)
    }
    assert stale == {}


def test_index_is_generated() -> None:
    readme = (ri.RFC_DIR / "README.md").read_text(encoding="utf-8")
    assert ri.splice(readme, ri.render(LEDGER)) == readme, "run python3 scripts/rfc_index.py"


def test_blocked_rfcs_carry_a_deadline_and_a_next_check() -> None:
    blocked = [r for r in LEDGER if r.state == "blocked"]
    for r in blocked:
        assert r.fields["decide_by"] >= r.fields["next_check"], r.path.name


def test_accepted_and_done_have_an_admission_field() -> None:
    for r in LEDGER:
        if r.state in ("accepted", "done"):
            assert "admitted-by" in r.fields, r.path.name


# --- each rule on a synthetic RFC --------------------------------------------


def test_conforming_synthetic_rfc_passes(tmp_path: Path) -> None:
    assert ri.validate(_rfc(tmp_path)) == []


def test_state_must_be_one_bare_word(tmp_path: Path) -> None:
    assert any("state" in p for p in ri.validate(_rfc(tmp_path, state="done 2026-09-05")))


def test_state_since_is_required(tmp_path: Path) -> None:
    assert any("state_since" in p for p in ri.validate(_rfc(tmp_path, state_since=None)))


def test_review_when_required_unless_terminal(tmp_path: Path) -> None:
    assert any("review-when" in p for p in ri.validate(_rfc(tmp_path, review_when=None)))
    done = _rfc(tmp_path, state="withdrawn", review_when=None, alignment=None)
    assert ri.validate(done) == []


def test_blocked_requires_decide_by_and_next_check(tmp_path: Path) -> None:
    problems = ri.validate(_rfc(tmp_path, state="blocked"))
    assert any("decide_by" in p for p in problems)
    assert any("next_check" in p for p in problems)
    ok = _rfc(tmp_path, state="blocked", decide_by="2027-01-09", next_check="2026-12-05")
    assert ri.validate(ok) == []
    late = _rfc(tmp_path, state="blocked", decide_by="2026-12-05", next_check="2027-01-09")
    assert any("later than decide_by" in p for p in ri.validate(late))


def test_accepted_requires_admitted_by_in_a_fixed_shape(tmp_path: Path) -> None:
    assert any("admitted-by" in p for p in ri.validate(_rfc(tmp_path, state="accepted")))
    for good in ("unrecorded", "alice 2026-10-12"):
        assert ri.validate(_rfc(tmp_path, state="accepted", admitted_by=good)) == []
    assert any(
        "admitted-by" in p
        for p in ri.validate(_rfc(tmp_path, state="done", admitted_by="2026-10-12", alignment=None))
    )


def test_open_rfc_needs_a_known_alignment(tmp_path: Path) -> None:
    assert any("alignment" in p for p in ri.validate(_rfc(tmp_path, alignment=None)))
    assert any("alignment" in p for p in ri.validate(_rfc(tmp_path, alignment="growth")))


def test_body_status_word_must_match(tmp_path: Path) -> None:
    rfc = _rfc(tmp_path)
    path = rfc.path
    path.write_text(path.read_text() + "\n## Status\n\nblocked — waiting\n", encoding="utf-8")
    assert any("Status" in p for p in ri.validate(ri.parse(path)))
    path.write_text(path.read_text().replace("blocked — waiting", "draft — fresh"), encoding="utf-8")
    assert ri.validate(ri.parse(path)) == []


def test_index_lists_state_and_awaiting_owner(tmp_path: Path) -> None:
    rfc = _rfc(tmp_path, decision_needed="ship it?")
    block = ri.render([rfc], adr_dir=tmp_path / "no-adr")
    assert "| draft |" in block
    assert "ship it?" in block
    assert "- repair: 1（RFC-0999）" in block


def test_awaiting_owner_reads_adr_marker(tmp_path: Path) -> None:
    adr = tmp_path / "0500-x.md"
    adr.write_text("a\nDeferred — 未決, revisit later\n", encoding="utf-8")
    (tmp_path / "0500-x.ja.md").write_text("Deferred — 未決\n", encoding="utf-8")
    assert [(n, line) for n, line, _ in ri.awaiting_from_adrs(tmp_path)] == [("0500-x.md", 2)]
