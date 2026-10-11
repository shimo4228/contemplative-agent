# pyright: reportPrivateUsage=false
"""The relevance record and its 4-level Score shadow (RFC-0046 / ADR-0113).

Pinned: the row is written whether or not a decision backend is configured
(decision fields null + ``unconfigured``); a configured backend is always
asked — there is no face switch (ADR-0113 amendment 3); the answered row carries the 4-level distribution, the
top level's probability and the expected level; every failure degrades to a
named reason without raising; the post is stored only as b64 + digest; the
row has no free-generated live half (RFC-0046 cleanup 2); one row per
answered reading per post, one per failed reading; the CLI builds the
backend unless ``DECISION_MODEL`` is empty and warns about the retired
``DECISION_FACES`` / ``DECISION_ENFORCE``; the prompt file is the one the
RFC-0045 replay asked.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import logging
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook import relevance_shadow as rs
from contemplative_agent.adapters.moltbook.config import FEED_CONTENT_PREVIEW_LEN
from contemplative_agent.cli import runtime
from contemplative_agent.core import llm as llm_module, relevance_state
from contemplative_agent.core.llm import (
    DecisionResult,
    QuestionAnswer,
    ScoreQuestion,
    configure,
    reset_llm_config,
)
from tests.test_agent import _make_agent

POST = "A post about how small local models keep their values across long sessions."
# The wording RFC-0045 measured arm C with (scripts/relevance_arm_replay.py at
# 2402411, before the text moved to config/prompts/relevance_score4.md).
RFC0045_INSTRUCTIONS = (
    "`domain` describes an agent and what it is concerned with. "
    "How closely does `post` relate to that domain?"
)
RFC0045_LEVELS = (
    "unrelated — `post` is about something outside `domain`",
    "shares vocabulary only — `post` uses some of the same words as `domain`, "
    "but it is about a different problem",
    "same field — `post` is in the same broad field as `domain`, but not about "
    "what `domain` is concerned with",
    "directly on-topic — `post` is about what `domain` is concerned with",
)


@pytest.fixture(autouse=True)
def _reset():
    yield
    rs.reset_relevance_shadow()
    reset_llm_config()


class _StubBackend:
    def __init__(self, result=None):
        self.result = result
        self.calls: list[tuple] = []

    @property
    def model(self) -> str:
        return "stub:1b"

    def decide(self, state, questions, *, system=""):
        self.calls.append((state, questions, system))
        return self.result


def _answered(probs=(0.1, 0.2, 0.3, 0.4), latency_ms=42):
    question = relevance_state.score4_question()
    answer = QuestionAnswer(
        id=question.id,
        probabilities=tuple(zip(question.levels, probs, strict=True)),
        reason="answered",
        observed=4,
    )
    return DecisionResult(
        model="stub:1b", latency_ms=latency_ms, answers=(answer,), reason="answered"
    )


def _rows(logs: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(logs.glob("relevance-*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _observe(content: str = POST, post_id: str = "post-1"):
    """One reading through the gate's writer."""
    return rs.enforce_and_record(post_id, content, threshold_score4=0.3)


DECISION_FIELDS = (
    "decision_backend",
    "decision_model",
    "decision_p",
    "decision_p_top",
    "decision_expected_level",
    "decision_latency_ms",
)


class TestRecord:
    def test_without_a_backend_the_row_is_written_with_null_decision_fields(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        _observe()
        (row,) = _rows(tmp_path / "logs")
        assert row["decision_reason"] == "unconfigured"
        for field in DECISION_FIELDS:
            assert row[field] is None, field
        assert row["post_id"] == "post-1"
        # RFC-0046 cleanup 2: the free-generated half is no longer asked.
        for retired in ("live_score", "live_reason", "threshold_applied", "live_gate"):
            assert retired not in row, retired
        assert "author_known" not in row
        assert "run_id" in row

    def test_the_post_is_stored_as_b64_and_digest_only(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        _observe()
        (row,) = _rows(tmp_path / "logs")
        assert base64.b64decode(row["content_b64"]).decode("utf-8") == POST
        assert row["content_sha256"] == hashlib.sha256(POST.encode("utf-8")).hexdigest()
        assert row["content_truncated"] is False
        assert POST not in json.dumps(row, ensure_ascii=False)

    def test_a_long_post_is_capped_and_flagged(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        _observe("x" * 10_000, post_id="p")
        (row,) = _rows(tmp_path / "logs")
        assert row["content_truncated"] is True
        assert len(base64.b64decode(row["content_b64"])) == rs._MAX_POST_AUDIT_BYTES

    def test_without_an_audit_dir_nothing_is_written_but_the_gate_still_asks(self, tmp_path):
        # The recorder's kill switch is not the gate's (ADR-0113 amendment 3:
        # the gate has none but an empty DECISION_MODEL).
        stub = _StubBackend(_answered())
        configure(decision_backend=stub)
        reading = _observe()
        assert len(stub.calls) == 1
        assert reading.outcome.gate_source == "score4"
        assert not list(tmp_path.rglob("relevance-*.jsonl"))


class TestNoFaceSwitch:
    """ADR-0113 amendment 3: the face switches are gone with the skill-selection shadow."""

    def test_a_configured_backend_is_always_asked(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        stub = _StubBackend(_answered())
        configure(decision_backend=stub)
        _observe()
        assert len(stub.calls) == 1
        (row,) = _rows(tmp_path / "logs")
        assert row["decision_reason"] == "answered"

    def test_the_face_api_is_retired(self):
        for retired in (
            "decision_face_enabled",
            "decision_enforce_enabled",
            "DECISION_FACES_KNOWN",
            "DECISION_FACES_DEFAULT",
            "DECISION_FACE_SKILL_SELECTION",
            "DECISION_FACE_RELEVANCE",
        ):
            assert not hasattr(llm_module, retired), retired
        assert not hasattr(rs, "ENFORCE_UNCONFIGURED")
        assert "enforce_unconfigured" not in rs.ENFORCE_REASONS


class TestAnswered:
    def _configure(self, tmp_path, result):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        stub = _StubBackend(result)
        configure(decision_backend=stub)
        return stub

    def test_the_row_carries_the_four_levels_and_the_top(self, tmp_path):
        self._configure(tmp_path, _answered((0.1, 0.2, 0.3, 0.4), latency_ms=42))
        _observe()
        (row,) = _rows(tmp_path / "logs")
        assert row["decision_reason"] == "answered"
        assert row["decision_backend"] == "_StubBackend"
        assert row["decision_model"] == "stub:1b"
        assert row["decision_latency_ms"] == 42
        assert row["decision_p"] == [0.1, 0.2, 0.3, 0.4]
        assert row["decision_p_top"] == 0.4
        assert row["decision_expected_level"] == pytest.approx(2.0)

    def test_one_question_on_the_production_domain_state_with_no_system(
        self, tmp_path, monkeypatch, pinned_nonce
    ):
        stub = self._configure(tmp_path, _answered())
        monkeypatch.setattr(rs, "production_domain_text", lambda: "I study contemplative AI.")
        _observe()
        ((state, questions, system),) = stub.calls
        assert state == relevance_state.state_text(
            relevance_state.build_state("I study contemplative AI.", POST)
        )
        (question,) = questions
        assert isinstance(question, ScoreQuestion)
        assert question.levels == RFC0045_LEVELS
        assert question.instructions == RFC0045_INSTRUCTIONS
        assert system == ""

    def test_the_decision_caller_is_its_own_telemetry_tag(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        configure(decision_backend=_StubBackend(_answered()))
        with patch.object(rs, "decide", wraps=llm_module.decide) as spy:
            _observe()
        assert spy.call_args.kwargs["caller"] == "moltbook.relevance_shadow"

    def test_an_abstain_keeps_its_reason_and_latency(self, tmp_path):
        question = relevance_state.score4_question()
        failed = DecisionResult(
            model="stub:1b",
            latency_ms=7,
            answers=(
                QuestionAnswer(id=question.id, probabilities=(), reason="http_error", observed=0),
            ),
            reason="http_error",
        )
        self._configure(tmp_path, failed)
        _observe()
        (row,) = _rows(tmp_path / "logs")
        assert row["decision_reason"] == "http_error"
        assert row["decision_latency_ms"] == 7
        assert row["decision_p"] is None
        assert row["decision_p_top"] is None


class TestDegrade:
    def test_a_raising_decide_is_backend_exception_and_the_row_is_written(self, tmp_path, caplog):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        configure(decision_backend=_StubBackend(_answered()))
        with (
            patch.object(rs, "decide", side_effect=RuntimeError("boom")),
            caplog.at_level(logging.WARNING),
        ):
            _observe()
        (row,) = _rows(tmp_path / "logs")
        assert row["decision_reason"] == "backend_exception"
        assert "relevance read failed" in caplog.text

    def test_an_unparseable_prompt_degrades_the_same_way(self, tmp_path, monkeypatch):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        configure(decision_backend=_StubBackend(_answered()))
        monkeypatch.setattr(
            rs, "score4_question", lambda: relevance_state.score4_question("only prose")
        )
        _observe()
        (row,) = _rows(tmp_path / "logs")
        assert row["decision_reason"] == "backend_exception"

    def test_a_failed_write_warns_and_does_not_raise(self, tmp_path, caplog):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        with (
            patch.object(rs, "append_jsonl_restricted", side_effect=OSError("disk full")),
            caplog.at_level(logging.WARNING),
        ):
            _observe()
        assert "relevance record not written" in caplog.text


class TestFeedHook:
    """The feed's gate writes one row per first judgment of a post."""

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="noticed",
    )
    def test_one_row_per_first_judgment(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        configure(decision_backend=_StubBackend(_answered((0.0, 0.0, 0.0, 1.0))))
        content = MagicMock()
        content.create_comment.return_value = MagicMock(text=None)
        agent, client, _ = _make_agent(tmp_path, content=content)
        agent._feed_manager._domain = replace(
            agent._feed_manager._domain, relevance_threshold_score4=0.3
        )
        _wire(client)

        for _ in range(3):
            agent._run_feed_cycle(time.time() + 3600)

        (row,) = _rows(tmp_path / "rlogs")
        assert row["post_id"] == "post1"
        assert row["decision_p_top"] == 1.0
        assert row["gate_source"] == "score4"
        assert row["enforce_gate"] is True
        client.upvote_post.assert_called_once_with("post1")


def _wire(client) -> None:
    post = {"content": "x" * FEED_CONTENT_PREVIEW_LEN, "id": "post1"}
    client.has_read_budget.return_value = True
    client.has_write_budget.return_value = True
    client.get_following_feed.return_value = []
    client.get_submolt_feed.return_value = [post]
    client.upvote_post.return_value = True
    client.get_post.return_value = {"id": "post1", "content": "full body " * 80}


class TestFeedHookOncePerPost:
    """The judgment memo keeps only settled judgments, so a passed post whose
    note came back empty is judged again every cycle; the record must not
    follow it. A failed reading is its own event and row every time."""

    def _agent(self, tmp_path, backend):
        configure(decision_backend=backend)
        content = MagicMock()
        content.create_comment.return_value = MagicMock(text=None)
        agent, client, _ = _make_agent(tmp_path, content=content)
        agent._feed_manager._domain = replace(
            agent._feed_manager._domain, relevance_threshold_score4=0.3
        )
        _wire(client)
        return agent

    @patch(
        "contemplative_agent.adapters.moltbook.feed_manager.generate_internal_note",
        return_value="",
    )
    def test_an_unsettled_rejudge_writes_no_second_row(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        agent = self._agent(tmp_path, _StubBackend(_answered((0.0, 0.0, 0.1, 0.9))))
        for _ in range(3):
            agent._run_feed_cycle(time.time() + 3600)
        # The premise: the empty note really did leave it unsettled.
        assert mock_note.call_count == 3
        assert len(_rows(tmp_path / "rlogs")) == 1

    def test_each_failed_reading_is_its_own_row(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        question = relevance_state.score4_question()
        failed = DecisionResult(
            model="stub:1b",
            latency_ms=7,
            answers=(
                QuestionAnswer(id=question.id, probabilities=(), reason="timeout", observed=0),
            ),
            reason="timeout",
        )
        stub = _StubBackend(failed)
        agent = self._agent(tmp_path, stub)
        for _ in range(2):
            agent._run_feed_cycle(time.time() + 3600)
        rows = _rows(tmp_path / "rlogs")
        assert len(stub.calls) == 2
        assert [r["decision_reason"] for r in rows] == ["timeout", "timeout"]
        assert [r["gate_source"] for r in rows] == ["fail_closed", "fail_closed"]


class TestDecisionEnv:
    @staticmethod
    def _args():
        return argparse.Namespace(domain_config=None, no_axioms=True, constitution_dir=None)

    def test_unset_env_is_production(self, monkeypatch):
        for env in ("DECISION_MODEL", "DECISION_FACES", "DECISION_ENFORCE"):
            monkeypatch.delenv(env, raising=False)
        runtime._configure_llm_and_domain(self._args())
        assert llm_module._decision_backend is not None
        assert llm_module._decision_backend.model == llm_module.served_model()

    def test_an_empty_model_constructs_no_backend_and_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("DECISION_MODEL", "")
        with caplog.at_level(logging.WARNING):
            runtime._configure_llm_and_domain(self._args())
        assert llm_module._decision_backend is None
        assert any(
            "DECISION_MODEL is empty" in r.getMessage() and "fails closed" in r.getMessage()
            for r in caplog.records
        )

    @pytest.mark.parametrize("env", ["DECISION_FACES", "DECISION_ENFORCE"])
    @pytest.mark.parametrize("raw", ["", "relevance", "skill_selection"])
    def test_a_retired_switch_is_ignored_with_one_warning(self, monkeypatch, caplog, env, raw):
        """An empty DECISION_ENFORCE no longer turns the gate off (ADR-0113 amendment 3)."""
        monkeypatch.delenv("DECISION_MODEL", raising=False)
        monkeypatch.setenv(env, raw)
        with caplog.at_level(logging.WARNING):
            runtime._configure_llm_and_domain(self._args())
        assert llm_module._decision_backend is not None
        warnings = [r for r in caplog.records if env in r.getMessage()]
        assert len(warnings) == 1
        assert "retired" in warnings[0].getMessage()

    def test_the_cli_turns_the_recorder_on(self, monkeypatch):
        monkeypatch.delenv("DECISION_MODEL", raising=False)
        runtime._configure_llm_and_domain(self._args())
        assert rs._audit_dir is not None


class TestPromptFile:
    def test_the_packaged_prompt_is_the_rfc0045_wording(self):
        instructions, levels = relevance_state.parse_score4_prompt(
            relevance_state.packaged_score4_prompt()
        )
        assert instructions == RFC0045_INSTRUCTIONS
        assert levels == RFC0045_LEVELS

    def test_the_loaded_template_parses_to_the_same_question(self):
        question = relevance_state.score4_question()
        assert question.levels == RFC0045_LEVELS
        assert question.instructions == RFC0045_INSTRUCTIONS

    @pytest.mark.parametrize(
        "text",
        [
            "- a\n- b\n- c\n- d\n",  # no instructions
            "How close?\n- a\n- b\n- c\n",  # three levels
            "How close?\n- a\n- b\n- c\n- d\n- e\n",  # five levels
        ],
    )
    def test_a_malformed_rubric_is_refused(self, text):
        with pytest.raises(ValueError):
            relevance_state.parse_score4_prompt(text)

    def test_the_state_is_arm_c_indented_json(self):
        state = relevance_state.build_state("domain text", POST)
        assert set(state) == {"domain", "post"}
        assert relevance_state.state_text(state) == json.dumps(state, ensure_ascii=False, indent=2)


AXIOMS = "Emptiness: hold every objective lightly."


def _configure_identity_axioms(tmp_path: Path, axioms: str | None) -> str:
    identity = tmp_path / "identity.md"
    identity.write_text("I study contemplative AI.\n", encoding="utf-8")
    configure(identity_path=identity, axiom_prompt=axioms)
    return "I study contemplative AI."


class TestProductionDomain:
    """RFC-0046 S32: "my domain" is identity + axioms, the production system prompt body."""

    def test_the_domain_is_the_system_prompt_body_byte_for_byte(self, tmp_path):
        from contemplative_agent.core.llm import prompting

        identity = _configure_identity_axioms(tmp_path, AXIOMS)
        text = relevance_state.production_domain_text()
        assert text == identity + "\n\n---\n\n" + AXIOMS
        assert text == prompting._identity_axioms_base(prompting._config)
        assert text == llm_module.get_identity_system_prompt()

    def test_without_axioms_the_domain_is_identity_alone_as_in_production(self, tmp_path):
        from contemplative_agent.core.llm import prompting

        identity = _configure_identity_axioms(tmp_path, None)
        assert relevance_state.production_domain_text() == identity
        assert relevance_state.production_domain_text() == prompting._identity_axioms_base(
            prompting._config
        )

    def test_an_invalid_identity_falls_back_where_production_does(self, tmp_path):
        identity = tmp_path / "identity.md"
        identity.write_text("", encoding="utf-8")
        configure(identity_path=identity, axiom_prompt=AXIOMS)
        assert relevance_state.production_domain_text() == llm_module.get_identity_system_prompt()

    def test_the_constants_name_the_two_definitions(self):
        assert relevance_state.DOMAIN_SOURCE_PRODUCTION == "identity+axioms"
        assert relevance_state.DOMAIN_SOURCE_IDENTITY == "identity"

    def test_the_shadow_state_carries_the_axioms(self, tmp_path, pinned_nonce):
        identity = _configure_identity_axioms(tmp_path, AXIOMS)
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        stub = _StubBackend(_answered())
        configure(decision_backend=stub)
        _observe()
        ((state, _questions, _system),) = stub.calls
        assert AXIOMS in state
        assert state == relevance_state.state_text(
            relevance_state.build_state(identity + "\n\n---\n\n" + AXIOMS, POST)
        )

    def test_the_row_names_its_domain_source(self, tmp_path):
        _configure_identity_axioms(tmp_path, AXIOMS)
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        configure(decision_backend=_StubBackend(_answered()))
        _observe()
        (row,) = _rows(tmp_path / "logs")
        assert row["domain_source"] == "identity+axioms"
        assert row["decision_p_top"] == 0.4

    def test_an_unconfigured_row_names_it_too(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "logs")
        _observe()
        (row,) = _rows(tmp_path / "logs")
        assert row["decision_reason"] == "unconfigured"
        assert row["domain_source"] == "identity+axioms"
