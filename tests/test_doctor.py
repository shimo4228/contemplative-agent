"""``contemplative-agent doctor`` (P0-05.1): one screen, one verdict, rc=1 on a real problem.

Ollama is replaced with ``responses`` (a refused connection, a model listing)
and the decision backend with a stub; no test needs a running server.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
import responses as responses_lib

from contemplative_agent.cli import COMMANDS, doctor as doctor_mod, main
from contemplative_agent.core import llm as llm_module
from contemplative_agent.core.llm import (
    DecisionResult,
    QuestionAnswer,
    ollama_model,
    reset_llm_config,
)

OLLAMA = "http://127.0.0.1:1"  # tests/conftest.py pins OLLAMA_BASE_URL here


@pytest.fixture(autouse=True)
def _reset():
    reset_llm_config()
    yield
    reset_llm_config()


class _Stub:
    """A decision backend that answers every NoulQuestion with a fixed P(yes) or reason."""

    model = "stub:1b"

    def __init__(self, p_yes: float | None = 0.9, reason: str = "answered"):
        self.p_yes = p_yes
        self.reason = reason
        self.asked: list[str] = []

    def decide(self, state, questions, *, system=""):
        self.asked.extend(q.instructions for q in questions)
        answers = tuple(
            QuestionAnswer(
                id=q.id,
                probabilities=(("yes", self.p_yes), ("no", 1 - self.p_yes))
                if self.reason == "answered" and self.p_yes is not None
                else (),
                reason=self.reason,
                observed=2 if self.reason == "answered" else 0,
            )
            for q in questions
        )
        return DecisionResult(model=self.model, latency_ms=1, answers=answers, reason=self.reason)


def _ollama_up(rsps, models=None):
    models = models if models is not None else [ollama_model(), "nomic-embed-text"]
    rsps.add(responses_lib.GET, f"{OLLAMA}/api/version", json={"version": "0.34.2"})
    rsps.add(
        responses_lib.GET,
        f"{OLLAMA}/api/tags",
        json={
            "models": [
                {"name": m if ":" in m else f"{m}:latest", "digest": "a" * 64} for m in models
            ]
        },
    )


def _run_doctor(capsys):
    with patch("sys.argv", ["contemplative-agent", "doctor"]):
        try:
            main()
            rc = 0
        except SystemExit as exc:
            rc = exc.code
    return rc, capsys.readouterr().out


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A tiny initialised home so the home checks are green."""
    identity = tmp_path / "identity.md"
    identity.write_text("id", encoding="utf-8")
    creds = tmp_path / "credentials.json"
    creds.write_text('{"api_key": "k"}', encoding="utf-8")
    monkeypatch.setattr(doctor_mod.config, "MOLTBOOK_DATA_DIR", tmp_path)
    monkeypatch.setattr(doctor_mod.config, "IDENTITY_PATH", identity)
    monkeypatch.setattr(doctor_mod.config, "CREDENTIALS_PATH", creds)
    monkeypatch.delenv("MOLTBOOK_API_KEY", raising=False)
    return tmp_path


def test_doctor_is_registered_and_listed_in_help(capsys):
    assert "doctor" in {spec.name for spec in COMMANDS}
    with patch("sys.argv", ["contemplative-agent", "--help"]):
        with pytest.raises(SystemExit):
            main()
    assert "doctor" in capsys.readouterr().out


def test_connection_refused_is_rc1_with_one_cause_line(capsys, home):
    with responses_lib.RequestsMock() as rsps:
        rsps.add(responses_lib.GET, f"{OLLAMA}/api/version", body=requests.ConnectionError("refused"))
        rc, out = _run_doctor(capsys)
    assert rc == 1
    assert "not reachable" in out
    assert "start Ollama" in out
    assert out.count("not reachable") == 1


def test_missing_generation_model_is_rc1_with_the_pull_command(capsys, home):
    with responses_lib.RequestsMock() as rsps:
        _ollama_up(rsps, models=["nomic-embed-text"])
        rc, out = _run_doctor(capsys)
    assert rc == 1
    assert f"ollama pull {ollama_model()}" in out


def test_missing_embedding_model_is_only_a_warning(capsys, home):
    with (
        responses_lib.RequestsMock() as rsps,
        patch.object(doctor_mod, "_build_decision_backend", return_value=_Stub()),
    ):
        _ollama_up(rsps, models=[ollama_model()])
        rc, out = _run_doctor(capsys)
    assert rc == 0
    assert "ollama pull nomic-embed-text" in out


def test_everything_ready_is_rc0(capsys, home):
    stub = _Stub()
    with (
        responses_lib.RequestsMock() as rsps,
        patch.object(doctor_mod, "_build_decision_backend", return_value=stub),
    ):
        _ollama_up(rsps)
        rc, out = _run_doctor(capsys)
    assert rc == 0
    assert "doctor: ready (0 warning(s))" in out
    assert len(stub.asked) == 1  # the canary is one question


@pytest.mark.parametrize(
    ("stub", "expected"),
    [
        (_Stub(p_yes=0.1), "decision_canary_failed: answered_no"),
        (_Stub(reason="no_option_observed"), "decision_canary_failed: no_option_observed"),
        (_Stub(reason="logprobs_unavailable"), "decision_canary_failed: logprobs_unavailable"),
    ],
    ids=["wrong-answer", "no-option", "no-logprobs"],
)
def test_a_canary_that_does_not_say_yes_warns_with_its_reason(capsys, home, stub, expected):
    with (
        responses_lib.RequestsMock() as rsps,
        patch.object(doctor_mod, "_build_decision_backend", return_value=stub),
    ):
        _ollama_up(rsps)
        rc, out = _run_doctor(capsys)
    assert expected in out
    assert "WARN" in out
    assert rc == 0  # it measures the model; it does not stop the operator


def test_canary_is_skipped_when_ollama_is_down(capsys, home):
    stub = _Stub()
    with (
        responses_lib.RequestsMock() as rsps,
        patch.object(doctor_mod, "_build_decision_backend", return_value=stub),
    ):
        rsps.add(responses_lib.GET, f"{OLLAMA}/api/version", body=requests.ConnectionError("x"))
        rc, out = _run_doctor(capsys)
    assert rc == 1
    assert "skipped" in out
    assert stub.asked == []


def test_an_empty_decision_model_fails_the_check(capsys, home, monkeypatch):
    monkeypatch.setenv("DECISION_MODEL", "")
    with responses_lib.RequestsMock() as rsps:
        _ollama_up(rsps)
        rc, out = _run_doctor(capsys)
    assert rc == 1
    assert "DECISION_MODEL is empty" in out


def test_uninitialised_home_fails_and_missing_key_only_warns(capsys, tmp_path, monkeypatch):
    monkeypatch.setattr(doctor_mod.config, "MOLTBOOK_DATA_DIR", tmp_path)
    monkeypatch.setattr(doctor_mod.config, "IDENTITY_PATH", tmp_path / "identity.md")
    monkeypatch.setattr(doctor_mod.config, "CREDENTIALS_PATH", tmp_path / "credentials.json")
    monkeypatch.delenv("MOLTBOOK_API_KEY", raising=False)
    with (
        responses_lib.RequestsMock() as rsps,
        patch.object(doctor_mod, "_build_decision_backend", return_value=_Stub()),
    ):
        _ollama_up(rsps)
        rc, out = _run_doctor(capsys)
    assert rc == 1
    assert "contemplative-agent init" in out
    assert "register --name" in out


def test_serving_findings_only_reports_what_is_wrong():
    ok = {"serving_environment_reason": "ok", "ollama_version": "0.34.2"}
    assert doctor_mod.run_startup_report(ok) == []
    missing = {"serving_environment_reason": f"model_not_listed:{ollama_model()}"}
    (finding,) = doctor_mod.run_startup_report(missing)
    assert finding.level == doctor_mod.FAIL
    assert f"ollama pull {ollama_model()}" in finding.fix


def test_the_canary_reads_the_default_backend_wiring(monkeypatch):
    """`doctor` builds the backend through the same function `run` does."""
    from contemplative_agent.cli import runtime

    assert doctor_mod._build_decision_backend is runtime._build_decision_backend
    monkeypatch.delenv("DECISION_MODEL", raising=False)
    backend = runtime._build_decision_backend()
    assert backend is not None and backend.model == llm_module.ollama_model()
