"""Thin deepeval wiring layer (ADR-0089).

This module and run_eval.py are the ONLY places allowed to import deepeval —
the deterministic core (dataset/judging/generation/compare) must stay
importable under the dev dependency group (enforced by
tests/test_eval_layering.py). Everything here is plumbing: judgments are
made once by the eval pipeline itself (claude -p, see
judging.run_claude_judge) and this metric merely replays the stored verdict
into deepeval's report format, so adopting deepeval never doubles the judge
cost and its TestRun files stay a debug byproduct, not the contract.

Score mapping is verdict -> {1.0, 0.5, 0.0} for display only. Per skill
llm-as-judge, the named verdict is the result; the number is never
aggregated into anything.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# Structural guarantee, not caller courtesy: ANY import of deepeval through
# this module runs with telemetry off ("1" is truthy under both deepeval's
# documented `=1` form and its settings bool-parse), even from pytest or an
# ad-hoc script that never went through run_eval's env setup. Unconditional
# assignment — setdefault would preserve a pre-existing "0".
os.environ["DEEPEVAL_TELEMETRY_OPT_OUT"] = "1"

from deepeval.metrics import BaseMetric  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

from evals.judging import Verdict  # noqa: E402

_VERDICT_SCORE = {Verdict.ADHERENT: 1.0, Verdict.DRIFTING: 0.5, Verdict.DEVIANT: 0.0}


class PrecomputedVerdictMetric(BaseMetric):
    """Replays a verdict already issued by the pipeline's judge.

    ``verdicts`` maps test-case name -> (Verdict, reason). Success is
    ADHERENT-only: DRIFTING is a visible warning in the report, not a pass.
    """

    def __init__(self, verdicts: Mapping[str, tuple[Verdict, str]]):
        super().__init__()
        self.threshold = 1.0
        self._verdicts = dict(verdicts)  # snapshot — no shared mutable state
        self.score: float | None = None
        self.success: bool | None = None
        self.reason: str | None = None
        self.error: str | None = None

    def measure(self, test_case: LLMTestCase) -> float:
        name = test_case.name or ""
        if name not in self._verdicts:
            self.error = f"no precomputed verdict for test case {name!r}"
            raise ValueError(self.error)
        verdict, reason = self._verdicts[name]
        self.score = _VERDICT_SCORE[verdict]
        self.reason = f"{verdict.value}: {reason}"
        self.success = verdict is Verdict.ADHERENT
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    # deepeval's BaseMetric defines __name__ as an untyped property; pyright
    # rejects any typed override of a dunder property, so mirror it untyped.
    @property
    def __name__(self):  # pyright: ignore[reportIncompatibleMethodOverride]
        return "Constitution Adherence (precomputed)"
