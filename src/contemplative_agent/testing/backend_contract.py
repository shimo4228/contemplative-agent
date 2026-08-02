"""Conformance checks for the ``LLMBackend`` contract (ADR-0088).

The canonical copy of "what an injected backend must do" lives here, in the
shipped package, so a sibling imports it instead of hand-copying it. The
failure this exists to prevent is measured, not hypothetical:
``contemplative-agent-cloud`` went three months non-conforming while holding
its own conformance test, because that test was a hand-copy that never
learned about the current callable shape. Static checks catch that shape;
runtime result semantics such as ``BackendResult`` are catalogued for the
next stage and are not claimed by this release.

Two properties of that failure shape this module.

**``isinstance`` is not enough.** ``LLMBackend`` is ``runtime_checkable``,
and a runtime-checkable Protocol only checks that members *exist* — never
their signature, never their return type. The cloud backend's
``generate(prompt, system, num_predict, format) -> Optional[str]`` satisfies
the member check. So the load-bearing check here is not membership but
whether the backend can *bind the call the caller actually issues*.

**A kit nobody runs changes nothing.** Hence ``python -m
contemplative_agent.testing``, which the explicit human release gate runs
without the sibling writing a test file at all.

Dependency rule: this package ships, so it may import only the standard
library and ``contemplative_agent.core.llm``. pytest, hypothesis, and
responses are dev-group-only and unavailable here; ``tests/chaos.py``
already demonstrates that reusable test parts do not need them.

Authoring rule for new checks: **assert only against symbols
``contemplative_agent.core.llm`` publicly re-exports.** A check that
hard-codes a telemetry field name or an estimator constant turns every
internal rename into three red repositories for no contractual reason.
Route such values through a constant this module exports, or derive them
(e.g. size an over-budget prompt from ``backend.context_window``, never
from the estimator's chars-per-token).
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from contemplative_agent.core.llm import LLMBackend, TokenCountingBackend

from .backend_probe import BackendProbe

# Bump on any change to the check set. Exposed as
# :attr:`ConformanceReport.kit_version` so a sibling can tell "my backend
# broke" from "the kit grew a check". Deliberately not the package version:
# what a sibling needs to correlate against is the check set, which changes
# on its own schedule.
KIT_VERSION = "1"

# ---------------------------------------------------------------------------
# Result vocabulary
# ---------------------------------------------------------------------------

PASSED = "passed"
FAILED = "failed"
# A precondition was absent (no probe, capability not present, level not
# requested, check excluded). Does NOT sink the report — coverage is
# governed by `require=`, not by counting skips.
SKIPPED = "skipped"
# The check itself blew up. Scored with FAILED: an unreadable backend is
# not a conforming one.
ERRORED = "errored"

STATUSES = (PASSED, FAILED, SKIPPED, ERRORED)

# Reasons attached to SKIPPED results.
SKIP_NO_PROBE = "no_probe"  # check needs a BackendProbe; none was supplied
SKIP_LEVEL_NOT_REQUESTED = "level_not_requested"
SKIP_CAPABILITY_ABSENT = "capability_absent"
SKIP_EXCLUDED = "excluded"  # caller passed the id in exclude=
SKIP_SIGNATURE_UNAVAILABLE = "signature_unavailable"  # not introspectable
# The parameter is swallowed by **kwargs, so no default is declared to read.
# Binding still succeeded, which is the contract that matters.
SKIP_ABSORBED_BY_VAR_KEYWORD = "absorbed_by_var_keyword"
# The parameter is simply not there and no **kwargs absorbs it. That is a
# real defect, but `generate.binds_canonical_call` is already reporting it;
# failing here too would count one break as two and bury the diagnosis.
SKIP_PARAMETER_ABSENT = "parameter_absent"

SKIP_REASONS = (
    SKIP_NO_PROBE,
    SKIP_LEVEL_NOT_REQUESTED,
    SKIP_CAPABILITY_ABSENT,
    SKIP_EXCLUDED,
    SKIP_SIGNATURE_UNAVAILABLE,
    SKIP_ABSORBED_BY_VAR_KEYWORD,
    SKIP_PARAMETER_ABSENT,
)

# ---------------------------------------------------------------------------
# Levels — how far a sibling declares its coverage reaches
# ---------------------------------------------------------------------------

LEVEL_STATIC = "static"  # the object alone; generate() is never called
LEVEL_RUNTIME = "runtime"  # + a probe that can serve canned responses
LEVEL_FULL = "full"  # + a probe whose make_backend honors overrides

LEVELS = (LEVEL_STATIC, LEVEL_RUNTIME, LEVEL_FULL)

_LEVEL_ORDER = {name: index for index, name in enumerate(LEVELS)}

# `require=LEVEL_STATIC` is FROZEN as the default, permanently. Raising a
# default turns a release into a red build for siblings that changed
# nothing — the one breakage a kit meant to reduce drift must never cause.
# Coverage is raised by editing the sibling's own call, where it is greppable.
DEFAULT_REQUIRE = LEVEL_STATIC

# ---------------------------------------------------------------------------
# Capabilities — optional parts of the contract
# ---------------------------------------------------------------------------

COUNTS_TOKENS = "counts_tokens"  # TokenCountingBackend (ADR-0087)
REPORTS_EVAL_COUNT = "reports_eval_count"  # fills BackendResult.eval_count
REPORTS_PREFILL = "reports_prefill"  # fills prompt_tokens + cached_tokens
# Fills finish_reason. Its ABSENCE is the interesting case: the caller's
# fail-closed truncation gate (audit M2) keys on finish_reason == "length",
# so a backend that never reports one publishes truncated text with the gate
# silently inert. Naming it a capability turns that from an accident into a
# declared fact (see T-FINISHREASON-GATE).
REPORTS_FINISH_REASON = "reports_finish_reason"
PRODUCES_THINKING = "produces_thinking"  # fills thinking under think=True

CAPABILITIES = (
    COUNTS_TOKENS,
    REPORTS_EVAL_COUNT,
    REPORTS_PREFILL,
    REPORTS_FINISH_REASON,
    PRODUCES_THINKING,
)

# The lowest level at which each capability can be DETECTED. Below it a
# capability is neither confirmed nor refuted, so a declaration of it is
# neither honored nor faulted — without this, a static-only run would fault
# every behavioral capability a sibling truthfully declared.
CAPABILITY_DETECTION_LEVEL = {
    COUNTS_TOKENS: LEVEL_STATIC,
    REPORTS_EVAL_COUNT: LEVEL_RUNTIME,
    REPORTS_PREFILL: LEVEL_RUNTIME,
    REPORTS_FINISH_REASON: LEVEL_RUNTIME,
    PRODUCES_THINKING: LEVEL_RUNTIME,
}

# ---------------------------------------------------------------------------
# Check ids
# ---------------------------------------------------------------------------

# Meta — always run; they report on the run rather than on the backend.
CHECK_LEVEL_REACHED = "meta.level_reached"
CHECK_DECLARED_CAPABILITIES = "meta.declared_capabilities_present"

# Static.
CHECK_PROTOCOL_MEMBERS = "protocol.members"
CHECK_MODEL_TYPE = "model.type"
CHECK_CONTEXT_WINDOW = "context_window.positive_int"
CHECK_GENERATE_BINDS = "generate.binds_canonical_call"
CHECK_GENERATE_DEFAULTS = "generate.kwonly_defaults"
CHECK_COUNT_TOKENS_SIGNATURE = "count_tokens.signature"

# Members of the LLMBackend Protocol. Hard-coded because
# typing.get_protocol_members() is 3.13+ and __protocol_attrs__ is a CPython
# internal; tests/test_backend_contract.py cross-checks this tuple against
# whichever introspection the running interpreter offers, so drift here is a
# red test in main rather than a silent hole in the siblings.
LLM_BACKEND_MEMBERS = ("model", "context_window", "generate")

# The call `_generate_via_backend` actually issues (core/llm/__init__.py).
# Four positional, two keyword-only. Binding THIS is the check; matching
# parameter names is not, so a backend taking **kwargs stays conforming.
_CANONICAL_ARGS: tuple[object, ...] = ("prompt", "system", 256, None)
_CANONICAL_KWARGS: dict[str, object] = {"temperature": 1.0, "think": False}

# Declared defaults for the keyword-only half of that call.
_EXPECTED_DEFAULTS: dict[str, object] = {"temperature": 1.0, "think": False}


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    """One check's verdict."""

    check_id: str
    status: str
    # Read on failure. Carries expected AND observed — a detail line that
    # only says what was wrong sends the reader back to the source.
    detail: str = ""
    # One of SKIP_REASONS when status is SKIPPED, else "".
    reason: str = ""


@dataclass(frozen=True)
class ConformanceReport:
    """The verdict of one :func:`check_backend` run.

    Returned rather than raised. The failure being addressed is three months
    of accumulated drift, not a single bug: raising on the first mismatch
    would answer "is it broken" while destroying "how many ways, and which".
    """

    results: tuple[CheckResult, ...]
    level_reached: str
    detected_capabilities: frozenset[str]
    kit_version: str = KIT_VERSION

    @property
    def ok(self) -> bool:
        """True when nothing failed or errored. Skips do not sink a report."""
        return not any(r.status in (FAILED, ERRORED) for r in self.results)

    @property
    def failures(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status in (FAILED, ERRORED))

    @property
    def skipped(self) -> tuple[CheckResult, ...]:
        return tuple(r for r in self.results if r.status == SKIPPED)

    @property
    def executed_ids(self) -> frozenset[str]:
        """Ids that actually ran — neither skipped nor excluded.

        Compare against :func:`expected_checks` to catch the quiet failure
        mode where the kit grew a check but this environment lacks the
        precondition to run it.
        """
        return frozenset(r.check_id for r in self.results if r.status != SKIPPED)

    def __bool__(self) -> bool:
        # Lets a sibling write `assert check_backend(b)`. pytest's assertion
        # rewriting prints __repr__ on failure, so the one-line form still
        # names every failing check.
        return self.ok

    def __repr__(self) -> str:
        head = (
            f"<ConformanceReport {'ok' if self.ok else 'FAILED'} "
            f"level={self.level_reached} kit={self.kit_version} "
            f"capabilities={sorted(self.detected_capabilities) or '[]'}>"
        )
        lines = [head]
        for result in self.failures:
            lines.append(f"  {result.status.upper()} {result.check_id}: {result.detail}")
        for result in self.skipped:
            lines.append(f"  skipped {result.check_id} ({result.reason})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_protocol_members(backend: object) -> CheckResult:
    missing = [name for name in LLM_BACKEND_MEMBERS if not hasattr(backend, name)]
    if missing or not isinstance(backend, LLMBackend):
        return CheckResult(
            CHECK_PROTOCOL_MEMBERS,
            FAILED,
            f"missing LLMBackend member(s): {missing or 'none by name'}; "
            f"isinstance(backend, LLMBackend) is "
            f"{isinstance(backend, LLMBackend)}",
        )
    return CheckResult(CHECK_PROTOCOL_MEMBERS, PASSED)


def _check_model_type(backend: object) -> CheckResult:
    value = getattr(backend, "model", None)
    if not isinstance(value, str) or not value.strip():
        return CheckResult(
            CHECK_MODEL_TYPE,
            FAILED,
            f"expected a non-empty str served-model id, got {value!r}; "
            "per-call telemetry groups by this value",
        )
    return CheckResult(CHECK_MODEL_TYPE, PASSED)


def _check_context_window(backend: object) -> CheckResult:
    value = getattr(backend, "context_window", None)
    # bool subclasses int; True would otherwise read as a 1-token window.
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return CheckResult(
            CHECK_CONTEXT_WINDOW,
            FAILED,
            f"expected a positive non-bool int, got {value!r}; the C2 "
            "pre-flight guard skips its check entirely without one, so "
            "over-window input reaches the backend unguarded",
        )
    return CheckResult(CHECK_CONTEXT_WINDOW, PASSED)


def _generate_signature(backend: object) -> inspect.Signature | None:
    generate = getattr(backend, "generate", None)
    if not callable(generate):
        return None
    try:
        return inspect.signature(generate)
    except (TypeError, ValueError):
        return None


def _check_generate_binds(backend: object) -> CheckResult:
    signature = _generate_signature(backend)
    if signature is None:
        return CheckResult(
            CHECK_GENERATE_BINDS,
            SKIPPED,
            "generate() is missing or not introspectable",
            SKIP_SIGNATURE_UNAVAILABLE,
        )
    try:
        signature.bind(*_CANONICAL_ARGS, **_CANONICAL_KWARGS)
    except TypeError as exc:
        return CheckResult(
            CHECK_GENERATE_BINDS,
            FAILED,
            f"generate{signature} cannot bind the call the caller issues — "
            f"generate(prompt, system, num_predict, format, *, "
            f"temperature=..., think=...): {exc}",
        )
    return CheckResult(CHECK_GENERATE_BINDS, PASSED)


def _check_generate_defaults(backend: object) -> CheckResult:
    signature = _generate_signature(backend)
    if signature is None:
        return CheckResult(
            CHECK_GENERATE_DEFAULTS,
            SKIPPED,
            "generate() is missing or not introspectable",
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
                CHECK_GENERATE_DEFAULTS,
                SKIPPED,
                f"{missing} taken via **kwargs, so no default is declared",
                SKIP_ABSORBED_BY_VAR_KEYWORD,
            )
        return CheckResult(
            CHECK_GENERATE_DEFAULTS,
            SKIPPED,
            f"{missing} absent from generate{signature}; see {CHECK_GENERATE_BINDS}",
            SKIP_PARAMETER_ABSENT,
        )
    wrong = {
        name: declared[name].default
        for name, expected in _EXPECTED_DEFAULTS.items()
        if declared[name].default != expected
    }
    if wrong:
        return CheckResult(
            CHECK_GENERATE_DEFAULTS,
            FAILED,
            f"expected defaults {_EXPECTED_DEFAULTS}, got {wrong}; a backend "
            "defaulting temperature elsewhere changes sampling for any "
            "direct caller",
        )
    return CheckResult(CHECK_GENERATE_DEFAULTS, PASSED)


def _check_count_tokens_signature(backend: object) -> CheckResult:
    if not isinstance(backend, TokenCountingBackend):
        return CheckResult(
            CHECK_COUNT_TOKENS_SIGNATURE,
            FAILED,
            "count_tokens exists but the object does not satisfy "
            "TokenCountingBackend; the guard resolves the capability "
            "structurally and would ignore it",
        )
    try:
        signature = inspect.signature(backend.count_tokens)
    except (TypeError, ValueError):
        return CheckResult(
            CHECK_COUNT_TOKENS_SIGNATURE,
            SKIPPED,
            "count_tokens() is not introspectable",
            SKIP_SIGNATURE_UNAVAILABLE,
        )
    try:
        signature.bind("text")
    except TypeError as exc:
        return CheckResult(
            CHECK_COUNT_TOKENS_SIGNATURE,
            FAILED,
            f"count_tokens{signature} cannot bind count_tokens(text): {exc}",
        )
    return CheckResult(CHECK_COUNT_TOKENS_SIGNATURE, PASSED)


# id -> (level, required capability or None, check function)
_REGISTRY: dict[str, tuple[str, str | None, Callable[[object], CheckResult]]] = {
    CHECK_PROTOCOL_MEMBERS: (LEVEL_STATIC, None, _check_protocol_members),
    CHECK_MODEL_TYPE: (LEVEL_STATIC, None, _check_model_type),
    CHECK_CONTEXT_WINDOW: (LEVEL_STATIC, None, _check_context_window),
    CHECK_GENERATE_BINDS: (LEVEL_STATIC, None, _check_generate_binds),
    CHECK_GENERATE_DEFAULTS: (LEVEL_STATIC, None, _check_generate_defaults),
    CHECK_COUNT_TOKENS_SIGNATURE: (
        LEVEL_STATIC,
        COUNTS_TOKENS,
        _check_count_tokens_signature,
    ),
}

_MAX_IMPLEMENTED_LEVEL = max(
    (level for level, _capability, _check in _REGISTRY.values()),
    key=_LEVEL_ORDER.__getitem__,
)

META_CHECKS = (CHECK_LEVEL_REACHED, CHECK_DECLARED_CAPABILITIES)


# ---------------------------------------------------------------------------
# Capability detection
# ---------------------------------------------------------------------------


def _detect_capabilities(backend: object, level: str) -> frozenset[str]:
    """Capabilities observable on *backend* at *level*.

    Detection — not declaration — decides which capability-gated checks run,
    so forgetting to declare one never quietly removes coverage.
    """
    # Behavioral capabilities need a probe; the runtime checks detect them
    # once those land, and they are simply not observable below that level.
    del level
    found = set()
    if callable(getattr(backend, "count_tokens", None)):
        found.add(COUNTS_TOKENS)
    return frozenset(found)


def _level_at_least(level: str, minimum: str) -> bool:
    return _LEVEL_ORDER[level] >= _LEVEL_ORDER[minimum]


def _reachable_level(probe: BackendProbe | None) -> str:
    """The highest level both the probe and registered checks support.

    Whether ``make_backend`` honors a given override is not knowable until
    it is called; an override it has no concept of raises
    ``NotImplementedError`` and skips that one check. This function answers
    only the coarser question of which methods exist.
    """
    if probe is None or not callable(getattr(probe, "responding", None)):
        probe_level = LEVEL_STATIC
    elif callable(getattr(probe, "make_backend", None)):
        probe_level = LEVEL_FULL
    else:
        probe_level = LEVEL_RUNTIME
    reached_index = min(_LEVEL_ORDER[probe_level], _LEVEL_ORDER[_MAX_IMPLEMENTED_LEVEL])
    return LEVELS[reached_index]


def expected_checks(*, level: str, capabilities: Sequence[str] = ()) -> frozenset[str]:
    """Ids that should execute for a given *level* and *capabilities* set.

    Lets a sibling assert ``report.executed_ids == expected_checks(...)`` and
    so notice a check that the kit added but this environment silently
    skipped. ``require=`` catches an unmet level; this catches a hole inside
    a level that was met.
    """
    if level not in _LEVEL_ORDER:
        raise ValueError(f"unknown level {level!r}; expected one of {LEVELS}")
    declared = set(capabilities)
    ids: set[str] = set(META_CHECKS)
    for check_id, (check_level, capability, _fn) in _REGISTRY.items():
        if not _level_at_least(level, check_level):
            continue
        if capability is not None and capability not in declared:
            continue
        ids.add(check_id)
    return frozenset(ids)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def check_backend(
    backend: object,
    *,
    probe: BackendProbe | None = None,
    capabilities: Sequence[str] = (),
    require: str = DEFAULT_REQUIRE,
    telemetry_dir: Path | None = None,
    exclude: Sequence[str] = (),
) -> ConformanceReport:
    """Check *backend* against the ``LLMBackend`` contract.

    *probe* supplies the injection points every check above ``LEVEL_STATIC``
    needs. *capabilities* is a **lower bound the caller asserts**: declaring
    one that is not detected fails the run, so a provider change that
    silently drops prefill accounting turns red. Detecting one that was not
    declared is not a failure — otherwise adding a capability constant to
    this module would redden three repositories for a purely declarative
    reason. What was found is reported in
    :attr:`ConformanceReport.detected_capabilities`.

    *require* is the coverage level the caller claims; falling short of it
    fails ``meta.level_reached``. *telemetry_dir* is where core-path checks
    write per-call telemetry (a plain ``Path`` — this package cannot know
    about pytest's ``tmp_path``, so the caller passes one). *exclude* drops
    ids from the run, reporting them as skipped.

    Never raises for a non-conforming backend: read
    :attr:`ConformanceReport.ok`, or ``assert report``.
    """
    if require not in _LEVEL_ORDER:
        raise ValueError(f"unknown require={require!r}; expected one of {LEVELS}")
    unknown = sorted(set(capabilities) - set(CAPABILITIES))
    if unknown:
        raise ValueError(f"unknown capabilities {unknown}; expected {CAPABILITIES}")

    del telemetry_dir  # consumed by the core-path checks (not yet landed)

    declared = set(capabilities)
    excluded = set(exclude)
    reached = _reachable_level(probe)
    detected = _detect_capabilities(backend, reached)

    results: list[CheckResult] = [
        _check_level_reached(require, reached),
        _check_declared_capabilities(declared, detected, reached),
    ]

    for check_id, (check_level, capability, fn) in _REGISTRY.items():
        if check_id in excluded:
            results.append(CheckResult(check_id, SKIPPED, "excluded by caller", SKIP_EXCLUDED))
            continue
        if not _level_at_least(reached, check_level):
            results.append(
                CheckResult(
                    check_id,
                    SKIPPED,
                    f"needs level {check_level}, reached {reached}",
                    SKIP_NO_PROBE if probe is None else SKIP_LEVEL_NOT_REQUESTED,
                )
            )
            continue
        if capability is not None and capability not in detected:
            results.append(
                CheckResult(
                    check_id,
                    SKIPPED,
                    f"backend does not present capability {capability!r}",
                    SKIP_CAPABILITY_ABSENT,
                )
            )
            continue
        try:
            results.append(fn(backend))
        except Exception as exc:  # a check must never abort the run
            results.append(CheckResult(check_id, ERRORED, f"{type(exc).__name__}: {exc}"))

    return ConformanceReport(
        results=tuple(results),
        level_reached=reached,
        detected_capabilities=detected,
    )


def _check_level_reached(require: str, reached: str) -> CheckResult:
    if not _level_at_least(reached, require):
        if not _level_at_least(_MAX_IMPLEMENTED_LEVEL, require):
            detail = (
                f"caller declared require={require!r}, but the kit currently implements "
                f"checks through {_MAX_IMPLEMENTED_LEVEL!r}"
            )
        else:
            detail = (
                f"caller declared require={require!r} but only {reached!r} is "
                "reachable — supply a BackendProbe to cover the rest"
            )
        return CheckResult(
            CHECK_LEVEL_REACHED,
            FAILED,
            detail,
        )
    return CheckResult(CHECK_LEVEL_REACHED, PASSED)


def _check_declared_capabilities(
    declared: set[str], detected: frozenset[str], reached: str
) -> CheckResult:
    observable = {
        name for name in declared if _level_at_least(reached, CAPABILITY_DETECTION_LEVEL[name])
    }
    missing = sorted(observable - detected)
    if missing:
        return CheckResult(
            CHECK_DECLARED_CAPABILITIES,
            FAILED,
            f"declared but not detected: {missing}; detected {sorted(detected)}",
        )
    # A declaration this level cannot observe is deferred, not refuted, so
    # the check passes. Reporting it as SKIPPED instead would drop the id
    # out of `executed_ids` and break the `expected_checks` comparison for
    # every static run that truthfully declares a behavioral capability.
    deferred = sorted(declared - observable)
    detail = f"deferred (not observable at level {reached}): {deferred}" if deferred else ""
    return CheckResult(CHECK_DECLARED_CAPABILITIES, PASSED, detail)
