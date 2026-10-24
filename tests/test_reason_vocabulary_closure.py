"""Closure of the score4 gate's reason-code vocabularies (P1-08.12).

Three parties name the same codes: the writer's constant, the ADR that
documents them, and the census that reads the log. A code added to or dropped
from one of them without the others makes a row in the log mean something no
reader expects. The pairs checked:

- ``ENFORCE_REASONS`` (``relevance_gate.py``) == the list ADR-0113 amendment 3
  gives, and ``DECISION_REASONS`` (``core/llm/decision.py``) == the list
  ADR-0112 Decision 1 gives;
- the census registry's relevance entry takes both constants as its closed
  vocabulary, and a row with a value outside them is flagged in the report.
"""

from __future__ import annotations

import re
import sys

from tests._shell_harness import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "scripts"))

import _census_registry as reg  # type: ignore[import-not-found]  # noqa: E402

from contemplative_agent.adapters.moltbook.relevance_gate import ENFORCE_REASONS  # noqa: E402
from contemplative_agent.core.llm.decision import DECISION_REASONS  # noqa: E402

ADR = REPO_ROOT / "docs" / "adr"


def _flat(path: str) -> str:
    return re.sub(r"\s+", " ", (ADR / path).read_text(encoding="utf-8"))


def _codes_after(text: str, anchor: str, until: str) -> set[str]:
    """Backticked snake_case tokens between *anchor* and the next *until*."""
    start = text.index(anchor) + len(anchor)
    end = text.index(until, start)
    return set(re.findall(r"`([a-z_]+)`", text[start:end]))


def test_enforce_reasons_match_adr_0113():
    text = _flat("0113-decision-faces-and-relevance-score4-shadow.md")
    documented = _codes_after(text, "`ENFORCE_REASONS` is now", "; rows written before")
    assert documented == set(ENFORCE_REASONS)


def test_decision_reasons_match_adr_0112():
    text = _flat("0112-decision-backend-seam-and-shadow-skill-decision.md")
    anchor = "`unconfigured`"
    window = text[text.index(anchor) : text.index("`backend_exception`", text.index(anchor)) + 20]
    documented = set(re.findall(r"`([a-z_]+)`", window))
    # "answered" is the success code and sits outside that sentence; the others are the abstains
    assert documented == set(DECISION_REASONS) - {"answered"}


def test_the_census_entry_takes_both_constants_as_vocabulary():
    (entry,) = [e for e in reg.REGISTRY if e.glob == "relevance-*.jsonl"]
    vocab = dict(entry.enum_values)
    assert set(vocab["decision_reason"]) == set(DECISION_REASONS)
    assert set(ENFORCE_REASONS) <= set(vocab["enforce_reason"])


def test_a_value_outside_the_vocabulary_is_named_in_the_census_report():
    import pandas as pd

    (entry,) = [e for e in reg.REGISTRY if e.glob == "relevance-*.jsonl"]
    frame = pd.Series(["answered", "http_error", "made_up_reason", None])
    assert entry.unknown_values("decision_reason", frame) == ["made_up_reason"]
    assert entry.unknown_values("gate_source", frame) == []  # no vocabulary declared
