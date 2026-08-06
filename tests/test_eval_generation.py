"""Sample-generation loop (evals/generation.py).

Runs the real production path (``generate_comment``) against an injected
FakeBackend — the same seam contemplative-agent-cloud uses — and pins the
two properties the eval layer depends on: production parity (temperature
1.3 travels to the backend untouched) and failure separation (a None from
the backend becomes status=generation_failed, never a verdict).
"""

from __future__ import annotations

import pytest

from contemplative_agent.core.llm import configure, reset_llm_config
from evals.generation import SampleOutcome, generate_samples
from tests.test_llm_backend import FakeBackend

COMMENT = "A thoughtful reflection on the impermanence of held beliefs."


@pytest.fixture
def clean_llm_config():
    reset_llm_config()
    yield
    reset_llm_config()


class TestGenerateSamples:
    def test_collects_requested_ok_samples(self, clean_llm_config):
        backend = FakeBackend(responses=[COMMENT, COMMENT, COMMENT])
        configure(backend=backend)
        samples = generate_samples("What persists when a belief dissolves?", 3)
        assert [s.status for s in samples] == ["ok", "ok", "ok"]
        assert all(isinstance(s, SampleOutcome) for s in samples)
        assert all(s.text for s in samples)

    def test_backend_failure_is_generation_failed_not_a_verdict(self, clean_llm_config):
        backend = FakeBackend(responses=[COMMENT, None, COMMENT])
        configure(backend=backend)
        samples = generate_samples("post", 3)
        assert [s.status for s in samples] == ["ok", "generation_failed", "ok"]
        assert samples[1].text is None

    def test_production_temperature_reaches_backend(self, clean_llm_config):
        from contemplative_agent.adapters.moltbook.llm_functions import COMMENT_TEMPERATURE

        backend = FakeBackend(responses=[COMMENT])
        configure(backend=backend)
        generate_samples("post", 1)
        assert backend.calls[0]["temperature"] == COMMENT_TEMPERATURE

    def test_rejects_nonpositive_sample_count(self, clean_llm_config):
        with pytest.raises(ValueError):
            generate_samples("post", 0)
