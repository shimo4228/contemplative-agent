"""Sibling repositories are named, with a state word, on the list surfaces (P1-11.1).

D-P1-11-1..6 (owner, 2026-10-24): cloud / mlx / otel are Frozen, rules is kept as
the calibration dependency. CLAUDE.md's related-repositories list is the
canonical list surface; the release gate's TARGETS and the ADR-0015 addendum
must agree with it.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAUDE = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
SIBLINGS = ("rules", "cloud", "mlx", "otel")


def _entry(name: str) -> str:
    m = re.search(rf"^- \[contemplative-agent-{name}\].*$", CLAUDE, re.MULTILINE)
    assert m, f"contemplative-agent-{name} missing from CLAUDE.md related repositories"
    return m.group(0)


def test_every_sibling_has_a_state_word_on_the_list_surface() -> None:
    for name in SIBLINGS:
        line = _entry(name)
        assert "**状態:" in line, name
    for name in ("cloud", "mlx", "otel"):
        assert "Frozen as of contemplative-agent" in _entry(name)


def test_gate_targets_are_listed_siblings_and_states_agree() -> None:
    script = (ROOT / "scripts" / "check-sibling-backends.sh").read_text(encoding="utf-8")
    pattern = r'^\s+"(frozen|active)\|contemplative-agent-(\w+)\|'
    for state, repo in re.findall(pattern, script, re.M):
        assert repo in SIBLINGS
        if state == "frozen":
            assert "Frozen" in _entry(repo)


def test_adr_0015_unit_sentence_is_mirrored_in_claude_md() -> None:
    adr = next((ROOT / "docs" / "adr").glob("0015-*.md"))
    adr_text = adr.read_text(encoding="utf-8")
    assert "tests/test_shell_egress_allowlist.py" in adr_text
    assert "tests/test_shell_egress_allowlist.py" in CLAUDE
    assert "ADR-0015 追補" in CLAUDE
