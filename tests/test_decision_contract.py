"""Tests for the shipped ``DecisionBackend`` conformance kit (ADR-0112).

The kit's whole job is to notice drift between a sibling's ``decide`` and the
Protocol. So the tests that matter are the two that would otherwise go
unnoticed: that the hard-coded member tuple still matches the Protocol, and
that a backend carrying yesterday's signature is caught by the bind check
rather than by an ``isinstance`` that cannot see signatures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from contemplative_agent.core.llm import (
    DecisionBackend,
    DecisionQuestion,
    DecisionResult,
    OllamaLogprobsDecisionBackend,
)
from contemplative_agent.testing import (
    CHECK_DECIDE_BINDS,
    CHECK_DECISION_MODEL_TYPE,
    CHECK_DECISION_PROTOCOL_MEMBERS,
    DECISION_BACKEND_MEMBERS,
    DECISION_CHECKS,
    FAILED,
    PASSED,
    SKIP_EXCLUDED,
    check_decision_backend,
)
from contemplative_agent.testing.__main__ import (
    EXIT_NONCONFORMING,
    EXIT_OK,
    EXIT_UNUSABLE_TARGET,
    main as cli_main,
)

_THIS_MODULE = "tests.test_decision_contract"


@dataclass(frozen=True)
class _Conforming:
    model: str = "judge:1b"

    def decide(
        self,
        state: str,
        questions: tuple[DecisionQuestion, ...],
        *,
        system: str = "",
    ) -> DecisionResult | None:
        return DecisionResult(model=self.model, latency_ms=0, answers=(), reason="answered")


class _StaleSignature:
    """A backend written before ``system`` joined the call — the drift shape."""

    model = "judge:1b"

    def decide(self, state, questions):  # noqa: ANN001, ANN201
        return None


class _AbsorbsKwargs:
    model = "judge:1b"

    def decide(self, state, questions, **kwargs):  # noqa: ANN001, ANN003, ANN201
        return None


class _BlankModel:
    """Conforming call shape, unusable served-model id."""

    model = "   "

    def decide(self, state, questions, *, system=""):  # noqa: ANN001, ANN003, ANN201
        return None


CONFORMING_INSTANCE = _Conforming()


def _result(report, check_id):
    return next(r for r in report.results if r.check_id == check_id)


def test_member_list_matches_the_protocol():
    """Guard the hard-coded tuple against Protocol drift.

    ``typing.get_protocol_members()`` is 3.13+, so the kit cannot derive this
    at runtime on the 3.10 floor. Cross-check against whichever introspection
    the running interpreter offers, so a member added to DecisionBackend turns
    this test red in main rather than opening a hole in the siblings.
    """
    members = set()
    for protocol in cast(type[object], DecisionBackend).__mro__:
        if protocol is object or not getattr(protocol, "_is_protocol", False):
            continue
        namespace = vars(protocol)
        members.update(
            name for name in namespace.get("__annotations__", {}) if not name.startswith("_")
        )
        members.update(name for name in namespace if not name.startswith("_"))
    assert set(DECISION_BACKEND_MEMBERS) == members


def test_the_shipped_ollama_backend_conforms():
    report = check_decision_backend(OllamaLogprobsDecisionBackend(model="judge:1b"))
    assert report, repr(report)
    assert report.executed_ids >= set(DECISION_CHECKS)


def test_a_conforming_stub_passes_every_check():
    report = check_decision_backend(_Conforming())
    assert report.ok
    assert _result(report, CHECK_DECIDE_BINDS).status == PASSED


def test_a_stale_signature_fails_the_bind_check_isinstance_cannot_see():
    backend = _StaleSignature()
    # The member check passes: a runtime-checkable Protocol sees names only.
    assert isinstance(backend, DecisionBackend)
    report = check_decision_backend(backend)
    assert not report.ok
    assert _result(report, CHECK_DECISION_PROTOCOL_MEMBERS).status == PASSED
    failure = _result(report, CHECK_DECIDE_BINDS)
    assert failure.status == FAILED
    assert "system" in failure.detail


def test_var_keyword_absorbs_the_keyword_half():
    report = check_decision_backend(_AbsorbsKwargs())
    assert report.ok


def test_a_blank_model_id_fails():
    report = check_decision_backend(_BlankModel())
    assert _result(report, CHECK_DECISION_MODEL_TYPE).status == FAILED
    assert not report.ok


def test_excluding_a_check_reports_it_as_skipped():
    report = check_decision_backend(_Conforming(), exclude=(CHECK_DECISION_MODEL_TYPE,))
    assert _result(report, CHECK_DECISION_MODEL_TYPE).reason == SKIP_EXCLUDED
    assert report.ok


def test_a_check_that_raises_does_not_abort_the_run():
    class _Exploding:
        model = "judge:1b"

        def decide(self, state, questions, *, system=""):  # noqa: ANN001, ANN003, ANN201
            return None

        def __getattribute__(self, name):
            if name == "model":
                raise RuntimeError("boom")
            return object.__getattribute__(self, name)

    report = check_decision_backend(_Exploding())
    assert not report.ok
    assert _result(report, CHECK_DECIDE_BINDS).status == PASSED


class TestCli:
    def test_conforming_target_exits_zero(self, capsys):
        assert cli_main(["--decision", f"{_THIS_MODULE}:_Conforming"]) == EXIT_OK
        assert "ok" in capsys.readouterr().out

    def test_stale_target_exits_one_and_names_the_break(self, capsys):
        code = cli_main(["--decision", f"{_THIS_MODULE}:_StaleSignature"])
        assert code == EXIT_NONCONFORMING
        assert CHECK_DECIDE_BINDS in capsys.readouterr().out

    def test_an_already_constructed_instance_works(self, capsys):
        assert cli_main(["--decision", f"{_THIS_MODULE}:CONFORMING_INSTANCE"]) == EXIT_OK
        capsys.readouterr()

    def test_an_unloadable_target_is_a_distinct_exit_code(self, capsys):
        assert cli_main(["--decision", "no.such.module:Judge"]) == EXIT_UNUSABLE_TARGET
        assert "cannot load" in capsys.readouterr().err

    @pytest.mark.parametrize("extra", [["--require", "runtime"], ["--capability", "counts_tokens"]])
    def test_generation_only_flags_are_refused_not_ignored(self, capsys, extra):
        code = cli_main(["--decision", f"{_THIS_MODULE}:_Conforming", *extra])
        assert code == EXIT_UNUSABLE_TARGET
        assert "--backend only" in capsys.readouterr().err

    def test_exactly_one_contract_per_run(self):
        with pytest.raises(SystemExit):
            cli_main([])
        with pytest.raises(SystemExit):
            cli_main(
                [
                    "--backend",
                    f"{_THIS_MODULE}:_Conforming",
                    "--decision",
                    f"{_THIS_MODULE}:_Conforming",
                ]
            )
