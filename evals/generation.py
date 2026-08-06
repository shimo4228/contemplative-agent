"""Sample generation through the production comment path (ADR-0089).

Deterministic core: imports contemplative_agent only (no deepeval). The one
job of this module is to run ``generate_comment`` — the exact function the
Moltbook adapter publishes through, at its production temperature — N times
per golden post and record failures as *status*, never as verdicts.

The caller is responsible for backend/prompt wiring (``core.llm.configure``);
this module deliberately does not touch configuration so that tests can
inject a FakeBackend and run_eval can inject the pinned fixture assets
through the same seam.
"""

from __future__ import annotations

from dataclasses import dataclass

from contemplative_agent.adapters.moltbook.llm_functions import generate_comment


@dataclass(frozen=True)
class SampleOutcome:
    status: str  # "ok" | "generation_failed"
    text: str | None


def generate_samples(post: str, requested: int) -> list[SampleOutcome]:
    """Generate *requested* comment samples for one golden post."""
    if requested < 1:
        raise ValueError("requested must be >= 1")
    samples: list[SampleOutcome] = []
    for _ in range(requested):
        output = generate_comment(post)
        if output.text:
            samples.append(SampleOutcome(status="ok", text=output.text))
        else:
            samples.append(SampleOutcome(status="generation_failed", text=None))
    return samples
