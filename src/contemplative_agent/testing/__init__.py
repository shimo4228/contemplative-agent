"""Conformance kit for sibling backend implementations (ADR-0088).

Ships inside the package rather than living under ``tests/`` because
``[tool.hatch.build.targets.wheel]`` packages only ``src/contemplative_agent``:
a sibling that depends on ``contemplative-agent`` can import this, and could
never import ``tests/chaos.py``. That is why the canonical fault-injection
helpers were never actually reused across repositories despite being written
to be.

Not production code. Nothing under ``core`` / ``adapters`` / ``cli`` may
import it, and it may import nothing but the standard library and
``contemplative_agent.core.llm`` — both directions are enforced by
import-linter contracts in ``pyproject.toml``.

Smallest useful form, in a sibling's own test suite::

    from contemplative_agent.testing import check_backend
    from my_package.backends import MyBackend

    def test_conforms():
        assert check_backend(MyBackend(api_key="fake"))

Or without writing a test file at all, which is how CI should run it::

    python -m contemplative_agent.testing --backend my_package.backends:MyBackend

Facade convention follows ADR-0079: every public name is re-exported here in
the redundant-alias ``X as X`` form, so this module path is the only import
path a sibling needs and internal file moves stay internal.
"""

from __future__ import annotations

from .backend_contract import (
    CAPABILITIES as CAPABILITIES,
    CAPABILITY_DETECTION_LEVEL as CAPABILITY_DETECTION_LEVEL,
    CHECK_CONTEXT_WINDOW as CHECK_CONTEXT_WINDOW,
    CHECK_COUNT_TOKENS_SIGNATURE as CHECK_COUNT_TOKENS_SIGNATURE,
    CHECK_DECLARED_CAPABILITIES as CHECK_DECLARED_CAPABILITIES,
    CHECK_GENERATE_BINDS as CHECK_GENERATE_BINDS,
    CHECK_GENERATE_DEFAULTS as CHECK_GENERATE_DEFAULTS,
    CHECK_LEVEL_REACHED as CHECK_LEVEL_REACHED,
    CHECK_MODEL_TYPE as CHECK_MODEL_TYPE,
    CHECK_PROTOCOL_MEMBERS as CHECK_PROTOCOL_MEMBERS,
    COUNTS_TOKENS as COUNTS_TOKENS,
    DEFAULT_REQUIRE as DEFAULT_REQUIRE,
    ERRORED as ERRORED,
    FAILED as FAILED,
    KIT_VERSION as KIT_VERSION,
    LEVEL_FULL as LEVEL_FULL,
    LEVEL_RUNTIME as LEVEL_RUNTIME,
    LEVEL_STATIC as LEVEL_STATIC,
    LEVELS as LEVELS,
    LLM_BACKEND_MEMBERS as LLM_BACKEND_MEMBERS,
    META_CHECKS as META_CHECKS,
    PASSED as PASSED,
    PRODUCES_THINKING as PRODUCES_THINKING,
    REPORTS_EVAL_COUNT as REPORTS_EVAL_COUNT,
    REPORTS_FINISH_REASON as REPORTS_FINISH_REASON,
    REPORTS_PREFILL as REPORTS_PREFILL,
    SKIP_ABSORBED_BY_VAR_KEYWORD as SKIP_ABSORBED_BY_VAR_KEYWORD,
    SKIP_CAPABILITY_ABSENT as SKIP_CAPABILITY_ABSENT,
    SKIP_EXCLUDED as SKIP_EXCLUDED,
    SKIP_LEVEL_NOT_REQUESTED as SKIP_LEVEL_NOT_REQUESTED,
    SKIP_NO_PROBE as SKIP_NO_PROBE,
    SKIP_PARAMETER_ABSENT as SKIP_PARAMETER_ABSENT,
    SKIP_REASONS as SKIP_REASONS,
    SKIP_SIGNATURE_UNAVAILABLE as SKIP_SIGNATURE_UNAVAILABLE,
    SKIPPED as SKIPPED,
    STATUSES as STATUSES,
    CheckResult as CheckResult,
    ConformanceReport as ConformanceReport,
    check_backend as check_backend,
    expected_checks as expected_checks,
)
from .backend_probe import (
    OVERRIDE_BASE_URL as OVERRIDE_BASE_URL,
    OVERRIDE_CONTEXT_WINDOW as OVERRIDE_CONTEXT_WINDOW,
    OVERRIDES as OVERRIDES,
    BackendProbe as BackendProbe,
    ProbeResponse as ProbeResponse,
    SentCall as SentCall,
)
