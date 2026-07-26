"""Global pytest configuration.

Isolate tests from the real MOLTBOOK_HOME so test runs cannot write to
``~/.config/moltbook/``. This matters because several tests (notably
``test_agent.py::TestRunPostCycle::test_posts_dynamic``) mock the HTTP
client but exercise real ``memory.record_post()`` / ``episodes.append()``
code paths, which would otherwise leak mock content ("Reflective Note" /
"A short body about alignment.") into the live episode log. The 2026-04-12
weekly report flagged 17 such leaked records.

The env var MUST be set before any test module imports contemplative_agent,
because ``config.py`` captures MOLTBOOK_HOME at module load time into a
Path constant consumed by 14 modules. Setting it via an autouse fixture
would be too late.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

_MOLTBOOK_TEST_HOME = Path(tempfile.mkdtemp(prefix="moltbook-pytest-"))
os.environ["MOLTBOOK_HOME"] = str(_MOLTBOOK_TEST_HOME)

# Force Ollama to an unreachable port so any un-mocked LLM call fails fast
# (ConnectionRefusedError, ~ms) instead of hitting the developer's local
# Ollama instance (qwen3.5:9b responses take 1–30s per call and used to
# dominate slow-test wall time). core/llm.py::generate() swallows exceptions
# and returns None; every caller treats None as a fail-open signal, so test
# semantics are preserved. OLLAMA_TRUSTED_HOSTS must include 127.0.0.1 to
# pass the trust-escalation check in core/llm.py::_resolve_base_url().
os.environ["OLLAMA_BASE_URL"] = "http://127.0.0.1:1"
os.environ.setdefault("OLLAMA_TRUSTED_HOSTS", "127.0.0.1")

# Deterministic hypothesis runs (ADR-0077 chaos-TDD discipline):
# derandomize derives examples from the test name (no wall-clock entropy,
# identical output on every run), database=None disables the example DB,
# deadline=None avoids flaky per-example timing failures on loaded CI
# hosts. Known failure shapes are pinned with explicit @example(...)
# decorators at each test site. The storage dir is relocated into the
# sandbox tempdir BEFORE hypothesis is imported — database=None does not
# cover the constants/unicode caches, which would otherwise create an
# untracked .hypothesis/ in the repo.
os.environ.setdefault("HYPOTHESIS_STORAGE_DIRECTORY", str(_MOLTBOOK_TEST_HOME / ".hypothesis"))

from hypothesis import settings as _hyp_settings  # noqa: E402

_hyp_settings.register_profile(
    "ci", derandomize=True, max_examples=50, deadline=None, database=None
)
_hyp_settings.load_profile("ci")


@pytest.fixture(autouse=True)
def _distill_postgate_off(monkeypatch):
    """Default the ADR-0084 durability gate OFF for the suite.

    The gate is ON in production, but it adds a second LLM call per
    pattern-producing episode. Every schedule-driven distill test maps
    ``schedule[i]`` to the i-th episode, and most others hand ``generate`` a
    side_effect list sized one-per-episode — with the gate on, those tests
    would silently be exercising two concerns at once (backend fault tallying
    AND the gate), which is the coupling this ADR exists to remove.

    The gate is covered where it belongs: ``TestPostGate`` drives
    ``_distill_one(postgate=True)`` directly, and
    ``TestPostGateDefault`` asserts that with no env var set the production
    default really is on — so flipping the default back cannot pass silently.
    """
    monkeypatch.setenv("MOLTBOOK_DISTILL_POSTGATE", "0")


@pytest.fixture(autouse=True)
def _reset_llm_circuit_breaker():
    """Reset the LLM circuit breaker between tests.

    With OLLAMA_BASE_URL forced to an unreachable port, any un-mocked
    generate() call records a failure; once CIRCUIT_FAILURE_THRESHOLD
    is reached, subsequent tests that *do* mock requests.post see
    "Circuit breaker open" and return early before hitting the mock.
    """
    from contemplative_agent.core.llm import _circuit

    _circuit.reset()
    yield
    _circuit.reset()
