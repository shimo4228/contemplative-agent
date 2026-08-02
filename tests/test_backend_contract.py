"""Tests for the shipped conformance kit (ADR-0088).

Negative coverage is not optional here. This kit is the thing three
repositories will trust instead of reading the Protocol, so a check that
silently never fires produces a false green in every one of them — strictly
worse than the hand-copied tests it replaces. Every check therefore gets a
backend broken in exactly that one way, and the assertion is that the check
reports FAILED for that id specifically.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path
from typing import cast

import pytest

import contemplative_agent.testing.__main__ as conformance_cli
from contemplative_agent.core.llm import BackendResult, LLMBackend
from contemplative_agent.testing import (
    CHECK_CONTEXT_WINDOW,
    CHECK_COUNT_TOKENS_SIGNATURE,
    CHECK_DECLARED_CAPABILITIES,
    CHECK_GENERATE_BINDS,
    CHECK_GENERATE_DEFAULTS,
    CHECK_LEVEL_REACHED,
    CHECK_MODEL_TYPE,
    CHECK_PROTOCOL_MEMBERS,
    COUNTS_TOKENS,
    ERRORED,
    FAILED,
    LEVEL_FULL,
    LEVEL_RUNTIME,
    LEVEL_STATIC,
    LLM_BACKEND_MEMBERS,
    PASSED,
    REPORTS_PREFILL,
    SKIP_ABSORBED_BY_VAR_KEYWORD,
    SKIP_EXCLUDED,
    SKIP_PARAMETER_ABSENT,
    SKIPPED,
    ProbeResponse,
    SentCall,
    check_backend,
    expected_checks,
)
from contemplative_agent.testing.__main__ import (
    EXIT_NONCONFORMING,
    EXIT_OK,
    EXIT_UNUSABLE_TARGET,
    main as cli_main,
)
from tests.chaos import ChaosBackend, TokenCountingChaosBackend
from tests.test_llm_backend import FakeBackend


def _status(report, check_id: str) -> str:
    (result,) = [r for r in report.results if r.check_id == check_id]
    return result.status


def _result(report, check_id: str):
    (result,) = [r for r in report.results if r.check_id == check_id]
    return result


# ---------------------------------------------------------------------------
# Conforming backends
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "backend",
    [FakeBackend(), ChaosBackend(schedule=[])],
    ids=["FakeBackend", "ChaosBackend"],
)
def test_repo_own_backends_conform(backend):
    """The reference backends this repo already ships must pass."""
    report = check_backend(backend)
    assert report.ok, repr(report)
    assert report.level_reached == LEVEL_STATIC


def test_executed_ids_match_expected_for_static_run():
    report = check_backend(FakeBackend())
    assert report.executed_ids == expected_checks(level=LEVEL_STATIC)


def test_bool_protocol_lets_a_sibling_assert_the_report_directly():
    assert check_backend(FakeBackend())


def test_repr_names_every_failing_check():
    text = repr(check_backend(_MissingContextWindow()))
    assert CHECK_CONTEXT_WINDOW in text
    assert CHECK_PROTOCOL_MEMBERS in text
    assert "FAILED" in text


# ---------------------------------------------------------------------------
# One broken backend per check
# ---------------------------------------------------------------------------


class _MissingContextWindow:
    """cloud's actual shape: a model field, no context_window at all.

    Deliberately not a FakeBackend subclass — FakeBackend declares
    ``context_window`` as a dataclass field, so its default survives as a
    class attribute and ``del self.context_window`` would not hide it.
    """

    model = "no-window"

    def generate(self, prompt, system, num_predict, format, *, temperature=1.0, think=False):  # noqa: A002
        return BackendResult(text="ok")


@dataclass
class _BlankModel(FakeBackend):
    model: str = "   "


@dataclass
class _ZeroContextWindow(FakeBackend):
    context_window: int = 0


@dataclass
class _BoolContextWindow(FakeBackend):
    # bool subclasses int, so True would read as a one-token window.
    context_window: int = True  # type: ignore[assignment]


class _StaleSignature:
    """The pre-2026-05 signature contemplative-agent-cloud still has."""

    model = "stale"
    context_window = 32768

    def generate(self, prompt, system, num_predict, format):  # noqa: A002
        return None


class _AbsorbsKwargs:
    model = "absorbs"
    context_window = 32768

    def generate(self, prompt, system, num_predict, format, **kwargs):  # noqa: A002
        return BackendResult(text="ok")


class _WrongTemperatureDefault:
    model = "wrong-default"
    context_window = 32768

    def generate(self, prompt, system, num_predict, format, *, temperature=0.0, think=False):  # noqa: A002
        return BackendResult(text="ok")


@dataclass
class _CountTokensWrongArity(FakeBackend):
    def count_tokens(self, text: str, extra: int) -> int:
        return len(text) + extra


class _CountTokensWithoutWindow:
    """Presents count_tokens but is not a TokenCountingBackend."""

    model = "partial"

    def generate(self, prompt, system, num_predict, format, *, temperature=1.0, think=False):  # noqa: A002
        return BackendResult(text="ok")

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_missing_context_window_fails_two_checks():
    report = check_backend(_MissingContextWindow())
    assert not report.ok
    assert _status(report, CHECK_CONTEXT_WINDOW) == FAILED
    assert _status(report, CHECK_PROTOCOL_MEMBERS) == FAILED


def test_blank_model_fails():
    report = check_backend(_BlankModel())
    assert _status(report, CHECK_MODEL_TYPE) == FAILED


@pytest.mark.parametrize(
    "backend", [_ZeroContextWindow(), _BoolContextWindow()], ids=["zero", "bool"]
)
def test_non_positive_or_bool_context_window_fails(backend):
    report = check_backend(backend)
    assert _status(report, CHECK_CONTEXT_WINDOW) == FAILED


def test_stale_signature_fails_the_bind_check():
    """The defect isinstance cannot see, and the reason cloud went unnoticed."""
    backend = _StaleSignature()
    # isinstance is satisfied by member presence alone — the whole point.
    assert isinstance(backend, LLMBackend)
    report = check_backend(backend)
    assert _status(report, CHECK_PROTOCOL_MEMBERS) == PASSED
    assert _status(report, CHECK_GENERATE_BINDS) == FAILED
    # The absent parameters are reported once, by the bind check, not twice.
    defaults = _result(report, CHECK_GENERATE_DEFAULTS)
    assert defaults.status == SKIPPED
    assert defaults.reason == SKIP_PARAMETER_ABSENT


def test_var_keyword_backend_binds_and_defers_defaults():
    """**kwargs is conforming: the call binds, no default exists to read."""
    report = check_backend(_AbsorbsKwargs())
    assert report.ok, repr(report)
    assert _status(report, CHECK_GENERATE_BINDS) == PASSED
    assert _result(report, CHECK_GENERATE_DEFAULTS).reason == SKIP_ABSORBED_BY_VAR_KEYWORD


def test_wrong_temperature_default_fails():
    report = check_backend(_WrongTemperatureDefault())
    assert _status(report, CHECK_GENERATE_BINDS) == PASSED
    assert _status(report, CHECK_GENERATE_DEFAULTS) == FAILED


def test_count_tokens_wrong_arity_fails():
    report = check_backend(_CountTokensWrongArity())
    assert COUNTS_TOKENS in report.detected_capabilities
    assert _status(report, CHECK_COUNT_TOKENS_SIGNATURE) == FAILED


def test_count_tokens_present_but_protocol_unsatisfied_fails():
    report = check_backend(_CountTokensWithoutWindow())
    assert _status(report, CHECK_COUNT_TOKENS_SIGNATURE) == FAILED


def test_conforming_token_counter_passes():
    report = check_backend(TokenCountingChaosBackend(schedule=[]))
    assert report.ok, repr(report)
    assert COUNTS_TOKENS in report.detected_capabilities
    assert _status(report, CHECK_COUNT_TOKENS_SIGNATURE) == PASSED


# ---------------------------------------------------------------------------
# Detection, declaration, and the meta checks
# ---------------------------------------------------------------------------


def test_detection_not_declaration_drives_capability_checks():
    """An undeclared capability is still checked — silence must not skip it."""
    report = check_backend(TokenCountingChaosBackend(schedule=[]), capabilities=())
    assert _status(report, CHECK_COUNT_TOKENS_SIGNATURE) == PASSED


def test_declared_but_absent_capability_fails():
    report = check_backend(FakeBackend(), capabilities=(COUNTS_TOKENS,))
    assert _status(report, CHECK_DECLARED_CAPABILITIES) == FAILED


def test_declared_capability_undetectable_at_this_level_is_deferred_not_failed():
    """A behavioral claim is unobservable without a probe — deferred, not refuted."""
    report = check_backend(FakeBackend(), capabilities=(REPORTS_PREFILL,))
    result = _result(report, CHECK_DECLARED_CAPABILITIES)
    assert result.status == PASSED
    assert REPORTS_PREFILL in result.detail
    # Still executed, so the expected_checks comparison stays usable.
    assert report.executed_ids == expected_checks(
        level=LEVEL_STATIC, capabilities=(REPORTS_PREFILL,)
    )


@pytest.mark.parametrize("require", [LEVEL_RUNTIME, LEVEL_FULL])
def test_claiming_a_level_without_a_probe_fails(require):
    report = check_backend(FakeBackend(), require=require)
    assert not report.ok
    assert _status(report, CHECK_LEVEL_REACHED) == FAILED


def test_static_default_passes_the_level_check():
    assert _status(check_backend(FakeBackend()), CHECK_LEVEL_REACHED) == PASSED


def test_unimplemented_higher_levels_never_claim_coverage():
    report = check_backend(FakeBackend(), probe=_StubProbe(), require=LEVEL_FULL)
    assert report.level_reached == LEVEL_STATIC
    assert _status(report, CHECK_LEVEL_REACHED) == FAILED
    result = next(result for result in report.results if result.check_id == CHECK_LEVEL_REACHED)
    assert "kit currently implements checks through 'static'" in result.detail
    assert "supply a BackendProbe" not in result.detail


class _StubProbe:
    """Satisfies BackendProbe structurally; no runtime check consumes it yet."""

    def make_backend(self, **overrides: object) -> object:
        raise NotImplementedError(sorted(overrides))

    def responding(self, *responses: ProbeResponse):
        raise NotImplementedError(len(responses))


# ---------------------------------------------------------------------------
# Run mechanics
# ---------------------------------------------------------------------------


def test_a_raising_member_is_errored_not_an_aborted_run():
    class Exploding:
        context_window = 32768

        @property
        def model(self) -> str:
            raise RuntimeError("boom")

        def generate(self, prompt, system, num_predict, format, *, temperature=1.0, think=False):  # noqa: A002
            return BackendResult(text="ok")

    report = check_backend(Exploding())
    assert _status(report, CHECK_MODEL_TYPE) == ERRORED
    assert not report.ok
    # The remaining checks still ran.
    assert _status(report, CHECK_CONTEXT_WINDOW) == PASSED


def test_excluded_check_is_skipped_and_leaves_executed_ids():
    report = check_backend(_BlankModel(), exclude=(CHECK_MODEL_TYPE,))
    assert _result(report, CHECK_MODEL_TYPE).reason == SKIP_EXCLUDED
    assert CHECK_MODEL_TYPE not in report.executed_ids
    assert report.ok


def test_unknown_level_and_capability_raise():
    with pytest.raises(ValueError, match="unknown require"):
        check_backend(FakeBackend(), require="deep")
    with pytest.raises(ValueError, match="unknown capabilities"):
        check_backend(FakeBackend(), capabilities=("teleports",))
    with pytest.raises(ValueError, match="unknown level"):
        expected_checks(level="deep")


def test_protocol_member_list_matches_the_protocol():
    """Guard the hard-coded member tuple against Protocol drift.

    typing.get_protocol_members() is 3.13+, so the kit cannot derive this at
    runtime on the 3.10 floor. Cross-check against whichever introspection
    the running interpreter offers, so a member added to LLMBackend turns
    this test red in main rather than opening a hole in the siblings.
    """
    members = set()
    for protocol in cast(type[object], LLMBackend).__mro__:
        if protocol is object or not getattr(protocol, "_is_protocol", False):
            continue
        namespace = vars(protocol)
        members.update(
            name for name in namespace.get("__annotations__", {}) if not name.startswith("_")
        )
        members.update(name for name in namespace if not name.startswith("_"))
    assert set(LLM_BACKEND_MEMBERS) == members


def test_sent_call_is_deeply_frozen_and_copies_its_mapping():
    """One immutable record per provider call — never a shared accumulator."""
    source = {"top_p": 0.8}
    first, second = SentCall(sampling=source), SentCall()
    with pytest.raises(FrozenInstanceError):
        first.system = "rebound"  # type: ignore[misc]
    with pytest.raises(TypeError):
        first.sampling["top_p"] = 0.95  # type: ignore[index]
    source["top_p"] = 0.1
    assert first.sampling == {"top_p": 0.8}
    assert second.sampling == {}


# ---------------------------------------------------------------------------
# CLI runner — the path CI uses, which needs no test file in the sibling
# ---------------------------------------------------------------------------

_THIS_MODULE = "tests.test_backend_contract"


def test_cli_exits_zero_for_a_conforming_backend(capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:_AbsorbsKwargs"])
    assert code == EXIT_OK
    assert "ok" in capsys.readouterr().out


def test_cli_exits_one_and_names_the_breaks_for_a_stale_backend(capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:_StaleSignature"])
    assert code == EXIT_NONCONFORMING
    out = capsys.readouterr().out
    assert CHECK_GENERATE_BINDS in out


@pytest.mark.parametrize(
    "target",
    ["no_colon_here", f"{_THIS_MODULE}:DoesNotExist", "no.such.module:Thing"],
    ids=["missing-colon", "missing-attribute", "missing-module"],
)
def test_cli_separates_an_unloadable_target_from_a_failing_one(target, capsys):
    """ "I never saw your backend" must not share an exit code with "it is wrong"."""
    assert cli_main(["--backend", target]) == EXIT_UNUSABLE_TARGET
    assert "cannot load" in capsys.readouterr().err


def test_cli_reports_a_constructor_that_needs_arguments(capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:_NeedsModel"])
    assert code == EXIT_UNUSABLE_TARGET
    err = capsys.readouterr().err
    assert "cannot construct" in err
    assert "--kwarg" in err


def test_cli_passes_allowlisted_kwargs_to_the_constructor(capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:_NeedsModel", "--kwarg", "model=fake"])
    assert code == EXIT_OK
    assert "ok" in capsys.readouterr().out


@pytest.mark.parametrize(
    "name",
    [
        "api_key",
        "password",
        "access_token",
        "client_secret",
        "accessToken",
        "clientSecret",
        "authorization",
        "bearer",
        "auth",
        "label",
    ],
)
def test_cli_rejects_non_allowlisted_constructor_kwargs(name, capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:_NeedsModel", "--kwarg", f"{name}=leak"])
    assert code == EXIT_UNUSABLE_TARGET
    err = capsys.readouterr().err
    assert "not accepted" in err
    assert "leak" not in err


@pytest.mark.parametrize(
    "base_url",
    [
        "https://user:secret@example.test",
        "https://example.test?api_key=secret",
        "https://example.test#secret",
        "file:///tmp/socket",
        "not-a-url",
    ],
)
def test_cli_rejects_base_urls_that_could_carry_credentials(base_url, capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:_NeedsModel", "--kwarg", f"base_url={base_url}"])
    assert code == EXIT_UNUSABLE_TARGET
    err = capsys.readouterr().err
    assert "credential-free HTTP(S) origin" in err
    assert "secret" not in err


def test_cli_does_not_echo_constructor_exception_text(capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:_ExplodingConstructor"])
    assert code == EXIT_UNUSABLE_TARGET
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "secret-from-constructor" not in err


def test_cli_rejects_a_malformed_kwarg(capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:_NeedsLabel", "--kwarg", "novalue"])
    assert code == EXIT_UNUSABLE_TARGET
    assert "name=value" in capsys.readouterr().err


def test_cli_maps_module_initialization_failure_to_unusable(monkeypatch, capsys):
    def fail_import(_module_path: str):
        raise RuntimeError("secret-from-module")

    monkeypatch.setattr(conformance_cli.importlib, "import_module", fail_import)

    assert cli_main(["--backend", "pkg.module:Backend"]) == EXIT_UNUSABLE_TARGET
    err = capsys.readouterr().err
    assert "RuntimeError" in err
    assert "secret-from-module" not in err


def test_cli_accepts_an_already_constructed_instance(capsys):
    code = cli_main(["--backend", f"{_THIS_MODULE}:CONFORMING_INSTANCE"])
    assert code == EXIT_OK
    capsys.readouterr()


class _NeedsModel:
    """A backend whose constructor is not zero-argument, like cloud's."""

    context_window = 32768

    def __init__(self, model: str) -> None:
        self.model = model

    def generate(self, prompt, system, num_predict, format, *, temperature=1.0, think=False):  # noqa: A002
        return BackendResult(text="ok")


class _ExplodingConstructor:
    def __init__(self) -> None:
        raise RuntimeError("secret-from-constructor")


CONFORMING_INSTANCE = FakeBackend()


def test_full_verify_never_executes_adjacent_sibling_code():
    verify_script = Path(__file__).parents[1] / ".claude" / "verify.sh"
    assert "check-sibling-backends.sh" not in verify_script.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("child_status", "expected_status"),
    [(0, 0), (1, 1), (2, 2), (127, 2)],
)
def test_sibling_runner_preserves_unusable_status(
    tmp_path: Path, child_status: int, expected_status: int
):
    repo = tmp_path / "main"
    script = repo / "scripts" / "check-sibling-backends.sh"
    script.parent.mkdir(parents=True)
    source = Path(__file__).parents[1] / "scripts" / "check-sibling-backends.sh"
    script.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    for sibling in ("contemplative-agent-mlx", "contemplative-agent-cloud"):
        (tmp_path / sibling / "src").mkdir(parents=True)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_uv = fake_bin / "uv"
    fake_uv.write_text('#!/bin/sh\nexit "${FAKE_UV_STATUS:?}"\n', encoding="utf-8")
    fake_uv.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"
    env["FAKE_UV_STATUS"] = str(child_status)
    completed = subprocess.run(
        ["bash", str(script)],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == expected_status, completed.stdout + completed.stderr
