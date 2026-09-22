"""Tests for the ``DecisionBackend`` seam and its Ollama logprobs default (ADR-0112).

The boundaries pinned here are the ones a later reader cannot re-derive from
the code: the payload shape the readout depends on (``logprobs`` on,
``top_logprobs`` inside Ollama's cap of 20, ``num_predict`` 1, temperature 0,
an explicit ``num_ctx``), the two ``keep_alive: 0`` sends that keep the
decision model and the generation model out of memory at the same time, the
wall-clock batch budget, and the closed reason vocabulary each failure maps
to.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from dataclasses import FrozenInstanceError

import pytest
import responses as responses_lib

from contemplative_agent.cli import runtime
from contemplative_agent.core import llm as llm_module
from contemplative_agent.core.llm import (
    DECISION_REASONS,
    NUM_CTX,
    ChoiceQuestion,
    DecisionBackend,
    DecisionResult,
    NoulQuestion,
    OllamaLogprobsDecisionBackend,
    QuestionAnswer,
    ScoreQuestion,
    circuit_reading,
    configure,
    decide,
    reset_llm_config,
)

# conftest pins OLLAMA_BASE_URL to an unreachable port; the backend resolves
# the same allow-listed origin the generation path does.
OLLAMA_URL = f"{llm_module._get_ollama_url()}/api/generate"


@pytest.fixture(autouse=True)
def _reset():
    yield
    reset_llm_config()


def _logprob_body(pairs, **extra):
    """An Ollama ``/api/generate`` body carrying one first-token distribution.

    *pairs* is ``[(token, logprob), ...]`` in the server's own descending
    order, which the reading relies on for "first surface wins".
    """
    return {
        "response": "x",
        "logprobs": [
            {
                "token": pairs[0][0] if pairs else "",
                "top_logprobs": [{"token": t, "logprob": lp} for t, lp in pairs],
            }
        ],
        **extra,
    }


def _noul(id_="skill-a"):
    return NoulQuestion(id=id_, instructions=f"Does `{id_}` apply?")


def _patch_clock(monkeypatch, ticks, spent=99.0):
    """Drive the backend's wall clock from a fixed list.

    Reads past the end return *spent*, so a test states only the reads it
    cares about and a budget that is exhausted stays exhausted.
    """
    clock = iter(ticks)
    monkeypatch.setattr(
        llm_module.decision.time,  # type: ignore[attr-defined]
        "monotonic",
        lambda: next(clock, spent),
    )


def _sent_payloads():
    return [json.loads(call.request.body or "{}") for call in responses_lib.calls]


# ---------------------------------------------------------------------------
# DTOs
# ---------------------------------------------------------------------------


class TestDecisionTypes:
    def test_every_dto_is_frozen(self):
        answer = QuestionAnswer(
            id="q", probabilities=(("yes", 1.0),), reason="answered", observed=1
        )
        with pytest.raises(FrozenInstanceError):
            answer.reason = "bad"  # type: ignore[misc]
        question = _noul()
        with pytest.raises(FrozenInstanceError):
            question.id = "other"  # type: ignore[misc]

    def test_reason_vocabulary_is_closed_and_complete(self):
        assert isinstance(DECISION_REASONS, tuple)
        assert set(DECISION_REASONS) == {
            "answered",
            "unconfigured",
            "circuit_open",
            "http_error",
            "bad_json",
            "logprobs_unavailable",
            "no_option_observed",
            "label_alphabet_exceeded",
            "budget_exceeded",
            "backend_exception",
        }

    def test_as_dict_projects_the_pairs(self):
        answer = QuestionAnswer(
            id="q", probabilities=(("yes", 0.8), ("no", 0.2)), reason="answered", observed=2
        )
        assert answer.as_dict() == {"yes": 0.8, "no": 0.2}

    def test_expected_level_is_the_probability_weighted_index(self):
        answer = QuestionAnswer(
            id="q",
            probabilities=(("low", 0.5), ("mid", 0.0), ("high", 0.5)),
            reason="answered",
            observed=2,
        )
        assert answer.expected_level() == pytest.approx(1.0)

    def test_expected_level_is_none_without_observed_mass(self):
        assert (
            QuestionAnswer(id="q", probabilities=(), reason="budget_exceeded", observed=0)
        ).expected_level() is None

    def test_the_ollama_backend_satisfies_the_protocol(self):
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        assert isinstance(backend, DecisionBackend)
        assert backend.model == "judge:1b"


# ---------------------------------------------------------------------------
# Payload shape
# ---------------------------------------------------------------------------


class TestPayload:
    @responses_lib.activate
    def test_noul_payload_pins_the_readout_settings(self):
        responses_lib.add(
            responses_lib.POST,
            OLLAMA_URL,
            json=_logprob_body([("yes", -0.1), ("no", -2.3)]),
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("THE STATE", (_noul(),))
        assert result is not None
        (payload,) = _sent_payloads()
        assert payload["logprobs"] is True
        assert payload["top_logprobs"] <= 20
        assert payload["options"]["num_predict"] == 1
        assert payload["options"]["temperature"] == 0
        assert payload["options"]["num_ctx"] == NUM_CTX
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["model"] == "judge:1b"
        # State is the prefix so Ollama's prefix cache carries it across the
        # per-entry calls.
        assert payload["prompt"].startswith("THE STATE")
        assert "yes or no" in payload["prompt"]
        # The system prompt is an argument, not the identity prompt.
        assert payload["system"] == ""

    @responses_lib.activate
    def test_the_caller_supplied_system_is_sent(self):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("yes", -0.1), ("no", -2.0)])
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        backend.decide("state", (_noul(),), system="IDENTITY")
        (payload,) = _sent_payloads()
        assert payload["system"] == "IDENTITY"

    @responses_lib.activate
    def test_nineteen_options_stay_inside_the_top_logprobs_cap(self):
        options = tuple(f"option-{i}" for i in range(19))
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("A", -0.2), ("B", -1.0)])
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        backend.decide("state", (ChoiceQuestion(id="c", instructions="pick", options=options),))
        (payload,) = _sent_payloads()
        assert payload["top_logprobs"] == 19
        assert payload["top_logprobs"] <= 20

    @responses_lib.activate
    def test_twenty_one_options_abstain_without_any_http(self):
        options = tuple(f"option-{i}" for i in range(21))
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide(
            "state", (ChoiceQuestion(id="c", instructions="pick", options=options),)
        )
        assert result is not None
        (answer,) = result.answers
        assert answer.reason == "label_alphabet_exceeded"
        assert answer.probabilities == ()
        assert answer.observed == 0
        assert len(responses_lib.calls) == 0


# ---------------------------------------------------------------------------
# Reading the distribution
# ---------------------------------------------------------------------------


class TestReading:
    @responses_lib.activate
    def test_yes_no_surfaces_are_read_case_insensitively(self):
        responses_lib.add(
            responses_lib.POST,
            OLLAMA_URL,
            json=_logprob_body([(" Yes", -0.2), ("junk", -1.0), ("NO", -1.2)]),
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("state", (_noul(),))
        assert result is not None
        (answer,) = result.answers
        assert answer.reason == "answered"
        assert answer.observed == 2
        expected = math.exp(-0.2) / (math.exp(-0.2) + math.exp(-1.2))
        assert answer.as_dict()["yes"] == pytest.approx(expected)
        assert answer.as_dict()["no"] == pytest.approx(1 - expected)

    @responses_lib.activate
    def test_one_observed_side_is_information_not_a_half(self):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("no", -0.01), ("maybe", -3.0)])
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("state", (_noul(),))
        assert result is not None
        (answer,) = result.answers
        assert answer.as_dict()["yes"] == 0.0
        assert answer.observed == 1

    @responses_lib.activate
    def test_neither_surface_observed_is_no_option_observed(self):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("maybe", -0.1), ("hmm", -1.0)])
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("state", (_noul(),))
        assert result is not None
        (answer,) = result.answers
        assert answer.reason == "no_option_observed"
        assert answer.probabilities == ()
        assert result.reason == "no_option_observed"

    @responses_lib.activate
    def test_choice_softmaxes_observed_labels_and_marks_truncation(self):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("A", -0.2), ("C", -1.2)])
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide(
            "state",
            (ChoiceQuestion(id="c", instructions="pick", options=("alpha", "beta", "gamma")),),
        )
        assert result is not None
        (answer,) = result.answers
        assert answer.reason == "answered"
        assert answer.truncated is True
        assert answer.observed == 2
        probabilities = answer.as_dict()
        assert probabilities["beta"] == 0.0
        total = math.exp(-0.2) + math.exp(-1.2)
        assert probabilities["alpha"] == pytest.approx(math.exp(-0.2) / total)
        assert probabilities["gamma"] == pytest.approx(math.exp(-1.2) / total)
        assert sum(probabilities.values()) == pytest.approx(1.0)

    @responses_lib.activate
    def test_a_fully_observed_choice_is_not_truncated(self):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("A", -0.2), ("B", -1.2)])
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide(
            "state", (ChoiceQuestion(id="c", instructions="pick", options=("alpha", "beta")),)
        )
        assert result is not None
        assert result.answers[0].truncated is False

    @responses_lib.activate
    def test_a_score_question_reads_its_levels(self):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("A", -1.0), ("B", -1.0)])
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide(
            "state", (ScoreQuestion(id="s", instructions="rate", levels=("low", "high")),)
        )
        assert result is not None
        (answer,) = result.answers
        assert answer.as_dict() == {"low": pytest.approx(0.5), "high": pytest.approx(0.5)}
        assert answer.expected_level() == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Failure vocabulary
# ---------------------------------------------------------------------------


class TestFailures:
    @responses_lib.activate
    def test_missing_logprobs_is_logprobs_unavailable(self):
        responses_lib.add(responses_lib.POST, OLLAMA_URL, json={"response": "yes"})
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("state", (_noul(),))
        assert result is not None
        assert result.answers[0].reason == "logprobs_unavailable"

    @responses_lib.activate
    def test_http_400_is_http_error(self):
        responses_lib.add(responses_lib.POST, OLLAMA_URL, json={"error": "nope"}, status=400)
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("state", (_noul(),))
        assert result is not None
        assert result.answers[0].reason == "http_error"

    @responses_lib.activate
    def test_unparsable_body_is_bad_json(self):
        responses_lib.add(responses_lib.POST, OLLAMA_URL, body="not json", status=200)
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("state", (_noul(),))
        assert result is not None
        assert result.answers[0].reason == "bad_json"

    @responses_lib.activate
    def test_an_untrusted_url_is_refused_without_any_http(self):
        backend = OllamaLogprobsDecisionBackend(model="judge:1b", base_url="http://evil.example")
        result = backend.decide("state", (_noul(),))
        assert result is not None
        assert result.reason == "http_error"
        assert [a.reason for a in result.answers] == ["http_error"]
        assert len(responses_lib.calls) == 0

    @responses_lib.activate
    def test_the_row_reason_is_the_first_failure_in_question_order(self):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("yes", -0.1), ("no", -2.0)])
        )
        responses_lib.add(responses_lib.POST, OLLAMA_URL, json={"response": "yes"})
        responses_lib.add(responses_lib.POST, OLLAMA_URL, json={"error": "nope"}, status=400)
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("state", (_noul("a"), _noul("b"), _noul("c")))
        assert result is not None
        assert [a.reason for a in result.answers] == [
            "answered",
            "logprobs_unavailable",
            "http_error",
        ]
        assert result.reason == "logprobs_unavailable"

    @responses_lib.activate
    def test_all_answered_is_the_only_answered_row(self):
        for _ in range(2):
            responses_lib.add(
                responses_lib.POST, OLLAMA_URL, json=_logprob_body([("yes", -0.1), ("no", -2.0)])
            )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b")
        result = backend.decide("state", (_noul("a"), _noul("b")))
        assert result is not None
        assert result.reason == "answered"


# ---------------------------------------------------------------------------
# No co-residence: the two keep_alive sends
# ---------------------------------------------------------------------------


class TestExclusiveEviction:
    @responses_lib.activate
    def test_a_swap_batch_evicts_the_generation_model_first_and_itself_last(self):
        for _ in range(3):
            responses_lib.add(
                responses_lib.POST, OLLAMA_URL, json=_logprob_body([("yes", -0.1), ("no", -2.0)])
            )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b", exclusive=True)
        backend.decide("state", (_noul("a"), _noul("b")))
        first, *rest = _sent_payloads()
        assert first == {"model": llm_module.served_model(), "keep_alive": 0}
        assert "keep_alive" not in rest[0]
        assert rest[-1]["keep_alive"] == 0
        assert rest[-1]["model"] == "judge:1b"

    @responses_lib.activate
    def test_the_same_model_sends_no_keep_alive_at_all(self):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("yes", -0.1), ("no", -2.0)])
        )
        backend = OllamaLogprobsDecisionBackend(model="judge:1b", exclusive=False)
        backend.decide("state", (_noul(),))
        (payload,) = _sent_payloads()
        assert "keep_alive" not in payload


# ---------------------------------------------------------------------------
# Batch budget
# ---------------------------------------------------------------------------


class TestBudget:
    @responses_lib.activate
    def test_the_budget_stops_the_http_and_names_the_rest(self, monkeypatch):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("yes", -0.1), ("no", -2.0)])
        )
        # started, then the per-question elapsed checks: the first question is
        # inside the budget and every later read is past it.
        _patch_clock(monkeypatch, [0.0, 0.0])
        backend = OllamaLogprobsDecisionBackend(model="judge:1b", batch_budget_s=10.0)
        result = backend.decide("state", (_noul("a"), _noul("b"), _noul("c")))
        assert result is not None
        assert [a.reason for a in result.answers] == [
            "answered",
            "budget_exceeded",
            "budget_exceeded",
        ]
        assert len(responses_lib.calls) == 1
        assert result.answers[1].probabilities == ()
        assert result.answers[1].observed == 0

    @responses_lib.activate
    def test_the_decision_model_is_evicted_even_when_the_budget_ran_out(self, monkeypatch):
        responses_lib.add(
            responses_lib.POST, OLLAMA_URL, json=_logprob_body([("yes", -0.1), ("no", -2.0)])
        )
        _patch_clock(monkeypatch, [0.0, 0.0])
        backend = OllamaLogprobsDecisionBackend(
            model="judge:1b", exclusive=True, batch_budget_s=10.0
        )
        backend.decide("state", (_noul("a"), _noul("b")))
        payloads = _sent_payloads()
        assert payloads[0] == {"model": llm_module.served_model(), "keep_alive": 0}
        assert payloads[-1] == {"model": "judge:1b", "keep_alive": 0}


# ---------------------------------------------------------------------------
# The core wrapper
# ---------------------------------------------------------------------------


class _StubBackend:
    def __init__(self, result=None, raises=None):
        self.result = result
        self.raises = raises
        self.calls: list[tuple] = []

    @property
    def model(self) -> str:
        return "stub:1b"

    def decide(self, state, questions, *, system=""):
        self.calls.append((state, questions, system))
        if self.raises is not None:
            raise self.raises
        return self.result


def _records(telemetry_dir):
    return [
        json.loads(line)
        for path in sorted(telemetry_dir.glob("llm-calls-*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


class TestCoreWrapper:
    @responses_lib.activate
    def test_unconfigured_returns_none_and_posts_nothing(self, tmp_path):
        configure(telemetry_dir=tmp_path)
        assert decide("state", (_noul(),), caller="test") is None
        assert len(responses_lib.calls) == 0
        assert _records(tmp_path) == []

    def test_an_open_circuit_is_respected_without_touching_the_counters(self, tmp_path):
        stub = _StubBackend(
            result=DecisionResult(model="stub:1b", latency_ms=1, answers=(), reason="answered")
        )
        configure(decision_backend=stub, telemetry_dir=tmp_path)
        for _ in range(llm_module.CIRCUIT_FAILURE_THRESHOLD):
            llm_module._circuit.record_failure()
        before = circuit_reading()
        assert before.is_open
        result = decide("state", (_noul(),), caller="test")
        assert result is not None
        assert result.reason == "circuit_open"
        assert stub.calls == []
        assert circuit_reading() == before

    def test_a_backend_exception_degrades_to_a_reason_code(self, tmp_path):
        stub = _StubBackend(raises=RuntimeError("boom"))
        configure(decision_backend=stub, telemetry_dir=tmp_path)
        result = decide("state", (_noul(),), caller="test")
        assert result is not None
        assert result.reason == "backend_exception"

    def test_one_telemetry_row_per_batch_not_per_question(self, tmp_path):
        answers = tuple(
            QuestionAnswer(
                id=name, probabilities=(("yes", 0.9), ("no", 0.1)), reason="answered", observed=2
            )
            for name in ("a", "b", "c")
        )
        stub = _StubBackend(
            result=DecisionResult(
                model="stub:1b", latency_ms=42, answers=answers, reason="answered"
            )
        )
        configure(decision_backend=stub, telemetry_dir=tmp_path)
        decide("THE STATE", tuple(_noul(n) for n in "abc"), caller="core.test")
        (record,) = _records(tmp_path)
        assert record["kind"] == "decision"
        assert record["caller"] == "core.test"
        assert record["model"] == "stub:1b"
        assert record["question_count"] == 3
        assert record["answered_count"] == 3
        assert record["num_predict"] == 1
        assert record["temperature"] == 0.0
        assert record["decision_reason"] == "answered"
        assert record["prompt_chars"] == len("THE STATE")
        assert record["prompt_norm_sha256"]
        assert isinstance(record["duration_ms"], int)
        assert record["outcome"] == "ok"
        # The record carries call metadata only, never the state body.
        assert "THE STATE" not in json.dumps(record)

    def test_the_configured_system_reaches_the_backend(self, tmp_path):
        stub = _StubBackend(
            result=DecisionResult(model="stub:1b", latency_ms=1, answers=(), reason="answered")
        )
        configure(decision_backend=stub, telemetry_dir=tmp_path)
        decide("state", (_noul(),), caller="test", system="IDENTITY")
        assert stub.calls[0][2] == "IDENTITY"

    def test_reset_clears_the_backend(self, tmp_path):
        configure(decision_backend=_StubBackend(), telemetry_dir=tmp_path)
        reset_llm_config()
        assert decide("state", (_noul(),), caller="test") is None


# ---------------------------------------------------------------------------
# CLI wiring — DECISION_MODEL is the kill switch
# ---------------------------------------------------------------------------


class TestCliWiring:
    @staticmethod
    def _args():
        return argparse.Namespace(domain_config=None, no_axioms=True, constitution_dir=None)

    def test_without_the_env_var_the_path_stays_off(self, monkeypatch):
        monkeypatch.delenv("DECISION_MODEL", raising=False)
        runtime._configure_llm_and_domain(self._args())
        assert llm_module._decision_backend is None

    def test_a_model_that_differs_from_the_served_one_runs_exclusive(self, monkeypatch):
        monkeypatch.setenv("DECISION_MODEL", "judge:1b")
        monkeypatch.setenv("DECISION_BUDGET_S", "7.5")
        runtime._configure_llm_and_domain(self._args())
        backend = llm_module._decision_backend
        assert isinstance(backend, OllamaLogprobsDecisionBackend)
        assert backend.model == "judge:1b"
        assert backend.exclusive is True
        assert backend.batch_budget_s == 7.5

    def test_the_served_model_needs_no_swap(self, monkeypatch):
        monkeypatch.setenv("DECISION_MODEL", llm_module.served_model())
        monkeypatch.delenv("DECISION_BUDGET_S", raising=False)
        runtime._configure_llm_and_domain(self._args())
        backend = llm_module._decision_backend
        assert isinstance(backend, OllamaLogprobsDecisionBackend)
        assert backend.exclusive is False
        assert backend.batch_budget_s == 120.0

    @pytest.mark.parametrize("raw", ["abc", "0", "-3"])
    def test_an_unusable_budget_falls_back_loudly(self, monkeypatch, caplog, raw):
        monkeypatch.setenv("DECISION_MODEL", "judge:1b")
        monkeypatch.setenv("DECISION_BUDGET_S", raw)
        with caplog.at_level(logging.WARNING):
            runtime._configure_llm_and_domain(self._args())
        backend = llm_module._decision_backend
        assert isinstance(backend, OllamaLogprobsDecisionBackend)
        assert backend.batch_budget_s == 120.0
        assert "DECISION_BUDGET_S" in caplog.text
