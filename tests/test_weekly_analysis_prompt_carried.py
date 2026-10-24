"""P2-06.1: the Exceptions section folds carried rows onto one marked line.

The rule lives in ``config/prompts/weekly-analysis.md`` (a fixed apparatus the
writer session reads), so what can be pinned deterministically is the text the
writer is given: the fold shape, the mandatory ``(since W)`` mark, and that the
Inventory count and the zero-exceptions line still hold. The two-consecutive-
weeks-of-fewer-lines reading is a production reading, not a test.
"""

from __future__ import annotations

from pathlib import Path

PROMPT = Path(__file__).resolve().parent.parent / "config" / "prompts" / "weekly-analysis.md"


def _exceptions_section() -> str:
    text = PROMPT.read_text(encoding="utf-8")
    start = text.index("\n## Exceptions\n")
    end = text.index("\n## Sample\n", start)
    return text[start:end]


def test_carried_fold_line_has_a_mandatory_since_mark():
    section = _exceptions_section()
    assert "`Carried: " in section
    assert "(since W)" in section
    assert "mandatory" in section


def test_a_changed_value_is_not_carried():
    assert "is not carried" in _exceptions_section()


def test_inventory_count_rule_and_zero_line_are_kept():
    section = _exceptions_section()
    assert "`Exceptions: 0.`" in section
    assert "exceptions N" in section


def test_rule_adds_no_evaluative_or_repair_vocabulary():
    # Binding rule 1 / 6: the fold is a format rule, not a recommendation.
    section = _exceptions_section().lower()
    for word in ("should be fixed", "we recommend", "concerning", "worrying"):
        assert word not in section
