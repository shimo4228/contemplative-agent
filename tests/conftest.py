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

from tests._llm_sentinel import _unmocked_llm_guard  # noqa: E402,F401  (autouse fixture)

_hyp_settings.register_profile(
    "ci", derandomize=True, max_examples=50, deadline=None, database=None
)
_hyp_settings.load_profile("ci")


@pytest.fixture(autouse=True)
def _clean_sandbox_home():
    """Start every test with an empty sandbox ``MOLTBOOK_HOME`` (P1-08.9).

    The sandbox is one tempdir for the whole session (its path is frozen into
    module constants at import, see the module docstring), so a test that
    records a post, stages a skill or appends a log leaves it for whichever
    test runs next: under ``-p randomly`` seed 12345 a leftover post record made
    ``TestRunPostCycle::test_posts_dynamic`` hit the dedup gate. Emptying the
    directory (not replacing it, the constants keep pointing at it) restores
    the order-free start the suite assumed.
    """
    import shutil

    for child in _MOLTBOOK_TEST_HOME.iterdir():
        if child.name == ".hypothesis":
            continue
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
    yield


@pytest.fixture(autouse=True)
def _reset_llm_and_selection_globals():
    """Reset the LLM config and skill-selection module globals around each test.

    ``configure(decision_backend=...)`` and ``configure_skill_selection(...)``
    set module-level state; left behind, a later test reads a stranger's
    backend (seed 777 in the P1-08.9 measurement: ``assert None ==
    'StubDecisionBackend'`` and ``'unconfigured' == 'http_error'`` in
    ``TestShadowDecision``). Autouse for the same reason as the resets below.
    """
    from contemplative_agent.core import skill_selection
    from contemplative_agent.core.llm import reset_llm_config

    reset_llm_config()
    skill_selection.reset_skill_selection()
    yield
    reset_llm_config()
    skill_selection.reset_skill_selection()


@pytest.fixture(autouse=True)
def _serving_probe_offline(request, monkeypatch):
    """Answer the serving-environment probe as "Ollama unreachable" without a socket.

    ``serving_environment()`` (P1-07.12) asks Ollama for the weights' digest and
    is now reached from the relevance-cache pin, the embedding calibration note
    and runtime setup. Against the suite's sentinel URL that is a refused
    connect, which the unmocked-LLM detector (P1-08.8) counts. The answer is the
    same one the refused connect produced (``ollama_unreachable``), raised at the
    requests layer; a test that patches ``core.llm.requests.get`` itself (the
    serving-environment tests) still reaches its mock, and a test marked
    ``allow_unmocked_llm`` keeps the real connect.
    """
    if request.node.get_closest_marker("allow_unmocked_llm") is not None:
        return
    from unittest import mock

    import requests
    import requests.adapters

    from contemplative_agent.core import llm

    real = llm._ollama_metadata
    real_send = requests.adapters.HTTPAdapter.send

    def offline(path: str) -> object:
        # A test that mocks the requests layer (``patch(...requests.get)`` or the
        # ``responses`` library, which replaces ``HTTPAdapter.send``) gets its mock.
        if (
            isinstance(llm.requests.get, mock.Base)
            or requests.adapters.HTTPAdapter.send is not real_send
        ):
            return real(path)
        raise requests.ConnectionError("serving-environment probe is offline in tests")

    monkeypatch.setattr(llm, "_ollama_metadata", offline)


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
def _reset_untrusted_guard():
    """Reset the untrusted wrapper's module state between tests.

    Both fields leak in the same direction if left set: a pinned
    ``nonce_source`` makes a later test's delimiter predictable, and a stale
    ``audit_dir`` points a later test's detection lines at a torn-down tmpdir.
    Autouse rather than per-test try/finally so a new suite is isolated by
    default — the same reason the circuit-breaker reset below is autouse.
    """
    from contemplative_agent.core.llm import reset_untrusted_guard

    reset_untrusted_guard()
    yield
    reset_untrusted_guard()


@pytest.fixture
def pinned_nonce():
    """Pin the delimiter nonce so a test can assert on an exact string.

    Production draws one per call from the system CSPRNG, which is the whole
    point (see ``TestUntrustedDelimiterForgery``); byte-identical assertions
    need it fixed. The injectable source exists for this and for offline
    replay of a recorded frame. Teardown is handled by the autouse reset above.
    """
    from contemplative_agent.core.llm import configure_untrusted_guard

    value = "0123456789abcdef"
    configure_untrusted_guard(nonce_source=lambda: value)
    return value


@pytest.fixture(autouse=True)
def _reset_llm_circuit_breaker():
    """Reset the LLM circuit breaker between tests.

    With OLLAMA_BASE_URL forced to an unreachable port, any un-mocked
    generate() call records a failure; once CIRCUIT_FAILURE_THRESHOLD
    is reached, subsequent tests that *do* mock requests.post see
    "Circuit breaker open" and return early before hitting the mock.
    """
    from contemplative_agent.core.llm import circuit_breaker

    circuit_breaker.reset()
    yield
    circuit_breaker.reset()


@pytest.fixture(autouse=True)
def _reset_relevance_gate():
    """Keep the relevance recorder and cache off unless a test turns them on (RFC-0046).

    ``cli.runtime._configure_llm_and_domain`` turns both on, and several tests
    call that; without the reset every later feed test would append rows to
    the sandbox home's logs, and reuse readings another test left in the
    sandbox home's ``relevance_cache.json`` (S38).
    """
    from contemplative_agent.adapters.moltbook.relevance_cache import reset_relevance_cache
    from contemplative_agent.adapters.moltbook.relevance_gate import reset_relevance_gate

    reset_relevance_gate()
    reset_relevance_cache()
    yield
    reset_relevance_gate()
    reset_relevance_cache()


# ---------------------------------------------------------------------------
# Expected-skip table (P1-08.2): a full run fails on a skip nobody expected.

_OBSERVED_SKIPS: list[tuple[str, str]] = []


def pytest_runtest_logreport(report) -> None:
    if report.skipped:
        longrepr = report.longrepr
        reason = longrepr[2] if isinstance(longrepr, tuple) else str(longrepr)
        _OBSERVED_SKIPS.append((report.nodeid, reason.removeprefix("Skipped: ")))


def _is_full_run(config) -> bool:
    option = config.option
    if getattr(option, "keyword", "") or getattr(option, "markexpr", ""):
        return False
    if getattr(option, "deselect", None) or getattr(option, "lf", False):
        return False
    args = [a for a in config.args if not a.startswith("-")]
    return not args or [a.rstrip("/").rsplit("/", 1)[-1] for a in args] == ["tests"]


def pytest_sessionfinish(session, exitstatus) -> None:
    from tests import _expected_skips

    if not _is_full_run(session.config) or hasattr(session.config, "workerinput"):
        return
    problems = _expected_skips.compare(
        _OBSERVED_SKIPS, _expected_skips.platform(), _expected_skips.is_root()
    )
    if problems:
        print("\n[expected-skips] " + "\n[expected-skips] ".join(problems))
        if session.exitstatus == 0:
            session.exitstatus = 1
