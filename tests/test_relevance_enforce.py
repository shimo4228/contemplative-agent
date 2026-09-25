# pyright: reportPrivateUsage=false
"""The score4 relevance gate, enforce-first with a paired record (RFC-0046 / RFC-0047).

Pinned: ``DECISION_ENFORCE`` parses like ``DECISION_FACES`` but defaults to
empty; with it absent the gate and every live field of the record are what
they were before enforce existed; enforce swaps ONLY the gate comparison, to
``P(directly on-topic) >= relevance_threshold_score4``; every way enforce does
not happen lands the live gate plus a named ``enforce_reason`` (no silent
fallback); the free-generation live score is still asked and recorded beside
the decision (paired); ``relevance_score4`` in domain.json is optional.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import time
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook import relevance_shadow as rs
from contemplative_agent.adapters.moltbook.config import FEED_CONTENT_PREVIEW_LEN
from contemplative_agent.cli import runtime
from contemplative_agent.core import llm as llm_module, relevance_state
from contemplative_agent.core.domain import load_domain_config
from contemplative_agent.core.llm import (
    DECISION_FACE_RELEVANCE,
    DECISION_FACE_SKILL_SELECTION,
    DecisionResult,
    QuestionAnswer,
    configure,
    reset_llm_config,
)
from tests.test_agent import _make_agent, _scored

FM = "contemplative_agent.adapters.moltbook.feed_manager"
ENFORCE_FIELDS = ("gate_source", "enforce_gate", "enforce_reason", "enforce_threshold")


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    # A published comment paces the next engagement with a real sleep.
    monkeypatch.setattr(
        "contemplative_agent.adapters.moltbook.feed_manager.random.uniform", lambda a, b: 0.0
    )
    yield
    rs.reset_relevance_shadow()
    reset_llm_config()


class _StubBackend:
    def __init__(self, result=None, exc: Exception | None = None):
        self.result = result
        self.exc = exc
        self.calls = 0

    @property
    def model(self) -> str:
        return "stub:1b"

    def decide(self, state, questions, *, system=""):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.result


def _answered(p_top: float) -> DecisionResult:
    question = relevance_state.score4_question()
    rest = (1.0 - p_top) / 3
    answer = QuestionAnswer(
        id=question.id,
        probabilities=tuple(zip(question.levels, (rest, rest, rest, p_top), strict=True)),
        reason="answered",
        observed=4,
    )
    return DecisionResult(model="stub:1b", latency_ms=7, answers=(answer,), reason="answered")


def _abstain(reason: str = "http_error") -> DecisionResult:
    answer = QuestionAnswer(id="relevance", probabilities=(), reason=reason, observed=0)
    return DecisionResult(model="stub:1b", latency_ms=3, answers=(answer,), reason=reason)


def _rows(logs: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(logs.glob("relevance-*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _agent(tmp_path, *, threshold_score4: float | None = 0.5):
    agent, client, _ = _make_agent(tmp_path, content=MagicMock())
    fm = agent._feed_manager
    fm._domain = dataclasses.replace(fm._domain, relevance_threshold_score4=threshold_score4)
    post = {"content": "x" * FEED_CONTENT_PREVIEW_LEN, "id": "post1"}
    client.has_read_budget.return_value = True
    client.has_write_budget.return_value = True
    client.get_following_feed.return_value = []
    client.get_submolt_feed.return_value = [post]
    client.upvote_post.return_value = True
    client.get_post.return_value = {"id": "post1", "content": "full body " * 80}
    return agent, client


def _configure(backend, *, enforce=frozenset({DECISION_FACE_RELEVANCE})):
    configure(
        decision_backend=backend,
        decision_faces=frozenset({DECISION_FACE_RELEVANCE}),
        decision_enforce=enforce,
    )


def _content(agent) -> MagicMock:
    return cast(MagicMock, agent._feed_manager._get_content())


def _comment_content(agent):
    """Make the content double hand back one comment so a pass reaches publish."""
    generated = MagicMock(text="a comment", thinking="", selection_id=None)
    _content(agent).create_comment.return_value = generated


# ---------------------------------------------------------------------------
# DECISION_ENFORCE: parse and config
# ---------------------------------------------------------------------------


class TestEnforceEnv:
    def test_unset_is_empty(self, monkeypatch):
        monkeypatch.delenv("DECISION_ENFORCE", raising=False)
        assert runtime._decision_enforce() == frozenset()

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("relevance", {"relevance"}),
            (" relevance , skill_selection ", {"relevance", "skill_selection"}),
            ("", set()),
        ],
    )
    def test_names_are_parsed(self, monkeypatch, raw, expected):
        monkeypatch.setenv("DECISION_ENFORCE", raw)
        assert runtime._decision_enforce() == frozenset(expected)

    def test_an_unknown_name_is_dropped_with_one_warning(self, monkeypatch, caplog):
        monkeypatch.setenv("DECISION_ENFORCE", "relevence,relevance")
        with caplog.at_level(logging.WARNING):
            faces = runtime._decision_enforce()
        assert faces == frozenset({"relevance"})
        warnings = [r for r in caplog.records if "DECISION_ENFORCE" in r.getMessage()]
        assert len(warnings) == 1
        assert "relevence" in warnings[0].getMessage()

    def test_config_default_and_reset_are_empty(self):
        assert not llm_module.decision_enforce_enabled(DECISION_FACE_RELEVANCE)
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        assert llm_module.decision_enforce_enabled(DECISION_FACE_RELEVANCE)
        assert not llm_module.decision_enforce_enabled(DECISION_FACE_SKILL_SELECTION)
        reset_llm_config()
        assert not llm_module.decision_enforce_enabled(DECISION_FACE_RELEVANCE)

    @staticmethod
    def _args():
        return argparse.Namespace(domain_config=None, no_axioms=True, constitution_dir=None)

    def test_the_cli_wires_enforce(self, monkeypatch):
        monkeypatch.setenv("DECISION_MODEL", llm_module.served_model())
        monkeypatch.setenv("DECISION_FACES", "relevance")
        monkeypatch.setenv("DECISION_ENFORCE", "relevance")
        runtime._configure_llm_and_domain(self._args())
        assert llm_module.decision_enforce_enabled(DECISION_FACE_RELEVANCE)

    def test_the_cli_leaves_enforce_off_when_unset(self, monkeypatch):
        monkeypatch.setenv("DECISION_MODEL", llm_module.served_model())
        monkeypatch.setenv("DECISION_FACES", "relevance")
        monkeypatch.delenv("DECISION_ENFORCE", raising=False)
        runtime._configure_llm_and_domain(self._args())
        assert not llm_module.decision_enforce_enabled(DECISION_FACE_RELEVANCE)

    def test_enforce_without_its_face_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("DECISION_MODEL", llm_module.served_model())
        monkeypatch.setenv("DECISION_FACES", "skill_selection")
        monkeypatch.setenv("DECISION_ENFORCE", "relevance")
        with caplog.at_level(logging.WARNING):
            runtime._configure_llm_and_domain(self._args())
        assert any(
            "DECISION_ENFORCE" in r.getMessage() and "relevance" in r.getMessage()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# domain.json: relevance_score4
# ---------------------------------------------------------------------------


class TestDomainField:
    def _write(self, tmp_path, thresholds):
        path = tmp_path / "domain.json"
        path.write_text(
            json.dumps(
                {
                    "name": "n",
                    "description": "d",
                    "submolts": {"subscribed": ["a"]},
                    "thresholds": thresholds,
                }
            ),
            encoding="utf-8",
        )
        return path

    def test_absent_is_none(self, tmp_path):
        config = load_domain_config(self._write(tmp_path, {"relevance": 0.8}))
        assert config.relevance_threshold_score4 is None

    def test_present_is_read(self, tmp_path, caplog):
        with caplog.at_level(logging.WARNING):
            config = load_domain_config(
                self._write(tmp_path, {"relevance": 0.8, "relevance_score4": 0.5})
            )
        assert config.relevance_threshold_score4 == 0.5
        assert "unknown" not in caplog.text.lower()

    @pytest.mark.parametrize("raw", [None, 70, -0.1, "0.5", True])
    def test_null_or_invalid_reads_as_unset(self, tmp_path, raw):
        config = load_domain_config(
            self._write(tmp_path, {"relevance": 0.8, "relevance_score4": raw})
        )
        assert config.relevance_threshold_score4 is None

    def test_the_packaged_config_carries_no_score4_threshold(self):
        # The value is the owner's to place after the labels (RFC-0046).
        assert load_domain_config().relevance_threshold_score4 is None


# ---------------------------------------------------------------------------
# resolve_enforce: the enum
# ---------------------------------------------------------------------------


class TestResolve:
    def _fields(self, p_top=0.9, reason="answered"):
        return {
            "decision_reason": reason,
            "decision_p_top": p_top if reason == "answered" else None,
        }

    def test_unconfigured(self):
        outcome = rs.resolve_enforce(self._fields(), 0.5)
        assert outcome == rs.EnforceOutcome("live", None, "enforce_unconfigured", None)

    def test_no_threshold(self):
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        outcome = rs.resolve_enforce(self._fields(), None)
        assert outcome == rs.EnforceOutcome("live", None, "enforce_no_threshold", None)

    def test_backend_null(self):
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        outcome = rs.resolve_enforce(self._fields(reason="http_error"), 0.5)
        assert outcome == rs.EnforceOutcome("live", None, "enforce_backend_null", 0.5)

    @pytest.mark.parametrize(("p_top", "gate"), [(0.5, True), (0.49, False), (0.9, True)])
    def test_enforced_compares_p_top(self, p_top, gate):
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        outcome = rs.resolve_enforce(self._fields(p_top=p_top), 0.5)
        assert outcome == rs.EnforceOutcome("score4", gate, "enforced", 0.5)

    def test_the_reasons_are_closed(self):
        assert rs.ENFORCE_REASONS == (
            "enforced",
            "enforce_unconfigured",
            "enforce_no_threshold",
            "enforce_backend_null",
            "enforce_exception",
        )


# ---------------------------------------------------------------------------
# The feed: kill switch, enforce, paired record, degrade
# ---------------------------------------------------------------------------


class TestKillSwitch:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.75))
    def test_without_enforce_the_gate_and_live_fields_are_unchanged(
        self, mock_score, mock_note, tmp_path
    ):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(_answered(1.0))
        _configure(backend, enforce=frozenset())
        agent, client = _agent(tmp_path)
        for _ in range(3):
            agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["live_score"] == 0.75
        assert row["live_gate"] is False
        assert row["threshold_applied"] == agent._feed_manager._domain.relevance_threshold
        assert row["gate_source"] == "live"
        assert row["enforce_gate"] is None
        assert row["enforce_reason"] == "enforce_unconfigured"
        assert row["enforce_threshold"] is None
        # Live near-miss: upvote-only, as before enforce existed.
        client.upvote_post.assert_called_once_with("post1")
        client.post_comment.assert_not_called()
        # Once per post, as the shadow always was.
        assert backend.calls == 1


class TestEnforced:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.3))
    def test_a_score4_pass_opens_the_gate_a_low_live_score_would_close(
        self, mock_score, mock_note, tmp_path
    ):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_answered(0.9)))
        agent, client = _agent(tmp_path, threshold_score4=0.5)
        _comment_content(agent)
        client.post_comment.return_value = {"comment": {"id": "c1"}}
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        # paired: the free-generation score is still asked and recorded
        assert mock_score.call_count == 1
        assert row["live_score"] == 0.3
        assert row["live_gate"] is False
        assert row["gate_source"] == "score4"
        assert row["enforce_gate"] is True
        assert row["enforce_reason"] == "enforced"
        assert row["enforce_threshold"] == 0.5
        assert row["decision_p_top"] == pytest.approx(0.9)
        # The comment path reads the full body, never the 500-char preview.
        client.get_post.assert_called()
        body = _content(agent).create_comment.call_args.args[0]
        assert len(body) != FEED_CONTENT_PREVIEW_LEN
        # A post the comment path may reach gets the pre-action note.
        mock_note.assert_called_once()

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.95))
    def test_a_score4_fail_closes_the_gate_a_high_live_score_would_open(
        self, mock_score, mock_note, tmp_path
    ):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_answered(0.1)))
        agent, client = _agent(tmp_path, threshold_score4=0.5)
        for _ in range(3):
            agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["live_gate"] is True
        assert row["gate_source"] == "score4"
        assert row["enforce_gate"] is False
        client.post_comment.assert_not_called()
        # Upvote-only stays on the live scale (0.95 >= upvote_only_threshold).
        client.upvote_post.assert_called_once_with("post1")

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.3))
    def test_the_enforced_judgment_is_memoized_with_the_post(self, mock_score, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(_answered(0.9))
        _configure(backend)
        agent, _client = _agent(tmp_path, threshold_score4=0.5)
        # The comment comes back empty: the gate passes every cycle and the
        # post stays uncommented, so the feed offers it again.
        generated = MagicMock(text=None, thinking="", selection_id=None)
        _content(agent).create_comment.return_value = generated
        for _ in range(3):
            agent._run_feed_cycle(time.time() + 3600)
        assert _content(agent).create_comment.call_count == 3
        assert mock_score.call_count == 1
        assert backend.calls == 1
        assert len(_rows(tmp_path / "rlogs")) == 1


class TestEnforceDegrades:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.75))
    def test_no_threshold_is_named_and_the_gate_is_live(self, mock_score, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_answered(1.0)))
        agent, client = _agent(tmp_path, threshold_score4=None)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["gate_source"] == "live"
        assert row["enforce_reason"] == "enforce_no_threshold"
        assert row["enforce_gate"] is None
        client.post_comment.assert_not_called()

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.75))
    def test_an_abstain_is_backend_null_and_keeps_its_decision_reason(
        self, mock_score, mock_note, tmp_path
    ):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_abstain("http_error")))
        agent, client = _agent(tmp_path)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["gate_source"] == "live"
        assert row["enforce_reason"] == "enforce_backend_null"
        assert row["decision_reason"] == "http_error"
        assert row["enforce_threshold"] == 0.5
        client.post_comment.assert_not_called()
        client.upvote_post.assert_called_once_with("post1")

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.75))
    def test_no_backend_is_backend_null(self, mock_score, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        agent, _client = _agent(tmp_path)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["decision_reason"] == "unconfigured"
        assert row["enforce_reason"] == "enforce_backend_null"

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.95))
    def test_an_exception_in_resolving_is_enforce_exception_and_publish_goes_on(
        self, mock_score, mock_note, tmp_path, caplog
    ):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_answered(0.1)))
        agent, client = _agent(tmp_path)
        _comment_content(agent)
        client.post_comment.return_value = {"comment": {"id": "c1"}}
        with (
            patch.object(rs, "_resolve", side_effect=RuntimeError("boom")),
            caplog.at_level(logging.WARNING),
        ):
            agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["gate_source"] == "live"
        assert row["enforce_reason"] == "enforce_exception"
        assert row["enforce_gate"] is None
        # Live gate passed (0.95 >= 0.8): the comment path ran.
        _content(agent).create_comment.assert_called_once()

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.75))
    def test_a_raising_backend_degrades_to_backend_null(self, mock_score, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(exc=RuntimeError("down")))
        agent, _client = _agent(tmp_path)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["decision_reason"] == "backend_exception"
        assert row["enforce_reason"] == "enforce_backend_null"
        assert row["gate_source"] == "live"


class TestShortDistribution:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.95))
    def test_a_malformed_answer_degrades_and_the_live_gate_acts(
        self, mock_score, mock_note, tmp_path
    ):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        answer = QuestionAnswer(
            id="relevance", probabilities=(("a", 1.0),), reason="answered", observed=1
        )
        short = DecisionResult(model="stub:1b", latency_ms=1, answers=(answer,), reason="answered")
        _configure(_StubBackend(short))
        agent, _client = _agent(tmp_path)
        _comment_content(agent)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["decision_reason"] == "backend_exception"
        assert row["enforce_reason"] == "enforce_backend_null"
        assert row["gate_source"] == "live"
        _content(agent).create_comment.assert_called_once()


class TestRecorderOff:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    @patch(f"{FM}.score_relevance_detailed", return_value=_scored(0.3))
    def test_enforce_still_decides_the_gate_without_an_audit_dir(
        self, mock_score, mock_note, tmp_path
    ):
        # The recorder's kill switch (audit_dir unset) is not enforce's.
        _configure(_StubBackend(_answered(0.9)))
        agent, client = _agent(tmp_path)
        _comment_content(agent)
        client.post_comment.return_value = {"comment": {"id": "c1"}}
        agent._run_feed_cycle(time.time() + 3600)
        _content(agent).create_comment.assert_called_once()


def test_row_carries_the_four_enforce_fields(tmp_path):
    rs.configure_relevance_shadow(audit_dir=tmp_path)
    rs.observe_relevance_recorded(
        "post-1",
        "body",
        live=_scored(0.9),
        threshold=0.8,
        gate=True,
        author_known=False,
    )
    (row,) = _rows(tmp_path)
    for name in ENFORCE_FIELDS:
        assert name in row
    assert row["gate_source"] == "live"
    assert row["enforce_reason"] == "enforce_unconfigured"
