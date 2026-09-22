"""Conformance checks for the ``DecisionBackend`` contract (ADR-0112).

The decision twin of :mod:`.backend_contract`, and for the same measured
reason: a sibling that hand-copies a call shape stays green while the shape
moves. ``contemplative-agent-cloud`` went three months non-conforming holding
its own conformance test. So the canonical call is **derived from
``DecisionBackend.decide``'s own signature** here, in the shipped package,
rather than written down twice.

``isinstance`` is not the check. ``DecisionBackend`` is ``runtime_checkable``,
and a runtime-checkable Protocol only checks that members exist — never their
signature. A backend whose ``decide(state, questions)`` predates the ``system``
keyword satisfies the member check and raises ``TypeError`` at call time. What
is checked here is whether the backend can bind the call the caller issues.

Same dependency rule as the rest of this package: standard library plus
``contemplative_agent.core.llm``, nothing else (import-linter contract).

Note on the shared :class:`ConformanceReport`: its ``expected_ids`` property
answers for the generation kit's registry and is not meaningful on a decision
report. Read ``ok`` and ``failures``; the report type is shared so a sibling
handles one result shape, not two.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence

from contemplative_agent.core.llm import DecisionBackend, NoulQuestion

from .backend_contract import (
    ERRORED,
    FAILED,
    KIT_VERSION,
    LEVEL_STATIC,
    PASSED,
    SKIP_ABSORBED_BY_VAR_KEYWORD,
    SKIP_EXCLUDED,
    SKIP_PARAMETER_ABSENT,
    SKIP_SIGNATURE_UNAVAILABLE,
    SKIPPED,
    CheckResult,
    ConformanceReport,
)

# Check ids. Prefixed so a report that mixes both contracts stays readable.
CHECK_DECISION_PROTOCOL_MEMBERS = "decision.protocol.members"
CHECK_DECISION_MODEL_TYPE = "decision.model.type"
CHECK_DECIDE_BINDS = "decision.decide.binds_canonical_call"
CHECK_DECIDE_DEFAULTS = "decision.decide.kwonly_defaults"

# Members of the DecisionBackend Protocol. Hard-coded for the same reason the
# generation list is — ``typing.get_protocol_members()`` is 3.13+ and the
# package floor is 3.10 — and cross-checked against the Protocol by
# ``tests/test_decision_contract.py``, so drift is a red test in main rather
# than a silent hole in a sibling.
DECISION_BACKEND_MEMBERS = ("model", "decide")

# Only the placeholder VALUES are literal: they are call arguments, not
# contract, and a Protocol never declares them.
_CANONICAL_PLACEHOLDERS: dict[str, object] = {
    "state": "state",
    "questions": (NoulQuestion(id="q", instructions="?"),),
}


def _derive_canonical_call() -> tuple[inspect.Signature, tuple[object, ...], dict[str, object]]:
    """Split ``DecisionBackend.decide`` into positional args and kw-only defaults.

    Raises at import if the Protocol grows a positional parameter with no
    placeholder. Loud in main — where the Protocol is edited and the tests run
    — beats a silent hole in a sibling repository.
    """
    signature = inspect.signature(DecisionBackend.decide)
    signature = signature.replace(
        parameters=[p for name, p in signature.parameters.items() if name != "self"]
    )
    args: list[object] = []
    defaults: dict[str, object] = {}
    for name, parameter in signature.parameters.items():
        if parameter.kind is inspect.Parameter.KEYWORD_ONLY:
            defaults[name] = parameter.default
            continue
        if name not in _CANONICAL_PLACEHOLDERS:
            raise RuntimeError(
                f"DecisionBackend.decide grew positional parameter {name!r} with no "
                f"placeholder in _CANONICAL_PLACEHOLDERS; the conformance kit "
                f"cannot issue the canonical call"
            )
        args.append(_CANONICAL_PLACEHOLDERS[name])
    return signature, tuple(args), defaults


_CANONICAL_SIGNATURE, _CANONICAL_ARGS, _EXPECTED_DEFAULTS = _derive_canonical_call()

# The keyword half of the canonical call: the caller forwards every
# keyword-only parameter explicitly, at its declared default.
_CANONICAL_KWARGS: dict[str, object] = dict(_EXPECTED_DEFAULTS)


def _check_protocol_members(backend: object) -> CheckResult:
    missing = [name for name in DECISION_BACKEND_MEMBERS if not hasattr(backend, name)]
    satisfies = isinstance(backend, DecisionBackend)
    if missing or not satisfies:
        return CheckResult(
            CHECK_DECISION_PROTOCOL_MEMBERS,
            FAILED,
            f"missing DecisionBackend member(s): {missing or 'none by name'}; "
            f"isinstance(backend, DecisionBackend) is {satisfies}",
        )
    return CheckResult(CHECK_DECISION_PROTOCOL_MEMBERS, PASSED)


def _check_model_type(backend: object) -> CheckResult:
    value = getattr(backend, "model", None)
    if not isinstance(value, str) or not value.strip():
        return CheckResult(
            CHECK_DECISION_MODEL_TYPE,
            FAILED,
            f"expected a non-empty str served-model id, got {value!r}; "
            "the decision telemetry row and every record field group by it",
        )
    return CheckResult(CHECK_DECISION_MODEL_TYPE, PASSED)


def _decide_signature(backend: object) -> inspect.Signature | None:
    decide = getattr(backend, "decide", None)
    if not callable(decide):
        return None
    try:
        return inspect.signature(decide)
    except (TypeError, ValueError):
        return None


def _check_decide_binds(backend: object) -> CheckResult:
    signature = _decide_signature(backend)
    if signature is None:
        return CheckResult(
            CHECK_DECIDE_BINDS,
            SKIPPED,
            "decide() is missing or not introspectable",
            SKIP_SIGNATURE_UNAVAILABLE,
        )
    try:
        signature.bind(*_CANONICAL_ARGS, **_CANONICAL_KWARGS)
    except TypeError as exc:
        return CheckResult(
            CHECK_DECIDE_BINDS,
            FAILED,
            f"decide{signature} cannot bind the call the caller issues — "
            f"decide{_CANONICAL_SIGNATURE}: {exc}",
        )
    return CheckResult(CHECK_DECIDE_BINDS, PASSED)


def _check_decide_defaults(backend: object) -> CheckResult:
    signature = _decide_signature(backend)
    if signature is None:
        return CheckResult(
            CHECK_DECIDE_DEFAULTS,
            SKIPPED,
            "decide() is missing or not introspectable",
            SKIP_SIGNATURE_UNAVAILABLE,
        )
    declared = signature.parameters
    missing = [name for name in _EXPECTED_DEFAULTS if name not in declared]
    if missing:
        absorbs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in declared.values()
        )
        if absorbs:
            return CheckResult(
                CHECK_DECIDE_DEFAULTS,
                SKIPPED,
                f"{missing} taken via **kwargs, so no default is declared",
                SKIP_ABSORBED_BY_VAR_KEYWORD,
            )
        return CheckResult(
            CHECK_DECIDE_DEFAULTS,
            SKIPPED,
            f"{missing} absent from decide{signature}; see {CHECK_DECIDE_BINDS}",
            SKIP_PARAMETER_ABSENT,
        )
    wrong = {
        name: declared[name].default
        for name, expected in _EXPECTED_DEFAULTS.items()
        if declared[name].default != expected
    }
    if wrong:
        return CheckResult(
            CHECK_DECIDE_DEFAULTS,
            FAILED,
            f"expected defaults {_EXPECTED_DEFAULTS}, got {wrong}; a backend that "
            "defaults the judge's system prompt elsewhere judges under a prompt "
            "the caller did not choose",
        )
    return CheckResult(CHECK_DECIDE_DEFAULTS, PASSED)


# id -> check function. Flat: every decision check is static today, and a
# level/capability axis with one value in it would be scaffolding for a
# distinction this contract does not yet make.
_REGISTRY: dict[str, Callable[[object], CheckResult]] = {
    CHECK_DECISION_PROTOCOL_MEMBERS: _check_protocol_members,
    CHECK_DECISION_MODEL_TYPE: _check_model_type,
    CHECK_DECIDE_BINDS: _check_decide_binds,
    CHECK_DECIDE_DEFAULTS: _check_decide_defaults,
}

DECISION_CHECKS = tuple(_REGISTRY)


def check_decision_backend(
    backend: object,
    *,
    exclude: Sequence[str] = (),
) -> ConformanceReport:
    """Check *backend* against the ``DecisionBackend`` contract.

    Returns rather than raises, like :func:`check_backend`: the failure this
    addresses is accumulated drift, and raising on the first mismatch answers
    "is it broken" while destroying "how many ways, and which". Read
    :attr:`ConformanceReport.ok`, or ``assert report``.
    """
    excluded = set(exclude)
    results: list[CheckResult] = []
    for check_id, fn in _REGISTRY.items():
        if check_id in excluded:
            results.append(CheckResult(check_id, SKIPPED, "excluded by caller", SKIP_EXCLUDED))
            continue
        try:
            results.append(fn(backend))
        except Exception as exc:  # a check must never abort the run
            results.append(CheckResult(check_id, ERRORED, f"{type(exc).__name__}: {exc}"))
    return ConformanceReport(
        results=tuple(results),
        level_reached=LEVEL_STATIC,
        detected_capabilities=frozenset(),
        kit_version=KIT_VERSION,
    )
