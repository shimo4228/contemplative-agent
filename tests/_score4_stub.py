"""A decision backend for the score4 gate: P(top) by a marker word in the text read.

The relevance gate's seam is the decision backend (``configure(decision_backend=...)``,
ADR-0112); this stub answers its one question, the 4-level Score, with the P(top)
a test assigns to a marker word found in the state text, and ``default`` when no
marker is there. ``asked`` lists the marker each read matched (``None`` for the
default), so a test can count reads.

Used by the reply cycle's tests (RFC-0075 S57) and by the ``reply_gate_open``
fixture (``tests/conftest.py``), which answers every read P(top) 1.0 so a reply
test that is not about the gate gets the reply path it tested before the gate.
"""

from __future__ import annotations

from contemplative_agent.core import relevance_state
from contemplative_agent.core.llm import DecisionResult, QuestionAnswer


class Score4ByMarker:
    def __init__(self, p_by_marker: dict[str, float], *, default: float | None = None):
        self.p_by_marker = p_by_marker
        self.default = default
        self.asked: list[str | None] = []

    @property
    def model(self) -> str:
        return "stub:1b"

    def decide(self, state, questions, *, system=""):
        marker = next((m for m in self.p_by_marker if m in state), None)
        if marker is None and self.default is None:
            raise AssertionError("no marker in the state text and no default P(top)")
        self.asked.append(marker)
        p_top = self.p_by_marker[marker] if marker is not None else self.default
        assert p_top is not None
        question = relevance_state.score4_question()
        rest = (1.0 - p_top) / 3
        answer = QuestionAnswer(
            id=question.id,
            probabilities=tuple(zip(question.levels, (rest, rest, rest, p_top), strict=True)),
            reason="answered",
            observed=4,
        )
        return DecisionResult(model="stub:1b", latency_ms=1, answers=(answer,), reason="answered")
