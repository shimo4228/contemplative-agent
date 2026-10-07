# pyright: reportPrivateUsage=false
"""The score4 relevance gate: the feed's one judge, fail-closed (RFC-0046 / RFC-0047).

Pinned: ``DECISION_ENFORCE`` parses like ``DECISION_FACES`` and defaults to
empty; the gate is ``P(directly on-topic) >= relevance_threshold_score4`` and
it is the only relevance judgment the feed acts on (RFC-0046 cleanup 2, owner
decision 2026-10-07): a passed post gets the full body, the note, the upvote
and the comment path; a closed post gets none of them — the upvote-only band
below the gate is gone; the free-generated score is never asked by the feed;
every way the gate has no answer fails closed with a named ``enforce_reason``
(no silent fallback), engages with nothing, ends the cycle and is asked again
next cycle; the known-author threshold is gone; the comment episode carries
the gate's value under ``relevance_p_top`` and no ``relevance`` key;
``relevance_score4`` in domain.json is optional.
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

from contemplative_agent.adapters.moltbook import (
    feed_manager as fm_module,
    relevance_shadow as rs,
)
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
from tests.test_agent import _make_agent

FM = "contemplative_agent.adapters.moltbook.feed_manager"
ENFORCE_FIELDS = ("gate_source", "enforce_gate", "enforce_reason", "enforce_threshold")
RETIRED_ROW_FIELDS = ("live_score", "live_reason", "threshold_applied", "live_gate", "author_known")


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


def _agent(tmp_path, *, threshold_score4: float | None = 0.5, posts: int = 1, author=None):
    agent, client, _ = _make_agent(tmp_path, content=MagicMock())
    fm = agent._feed_manager
    fm._domain = dataclasses.replace(fm._domain, relevance_threshold_score4=threshold_score4)
    feed = [
        {"content": "x" * FEED_CONTENT_PREVIEW_LEN, "id": f"post{i + 1}", "author": author or {}}
        for i in range(posts)
    ]
    client.has_read_budget.return_value = True
    client.has_write_budget.return_value = True
    client.get_following_feed.return_value = []
    client.get_submolt_feed.return_value = feed
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


def _comment_content(agent, text: str | None = "a comment"):
    """Make the content double hand back one comment so a pass reaches publish."""
    generated = MagicMock(text=text, thinking="", selection_id=None)
    _content(agent).create_comment.return_value = generated


def _assert_nothing_engaged(agent, client, mock_note) -> None:
    """Nothing beyond the gate's own read: no GET, no note, no upvote, no comment."""
    client.get_post.assert_not_called()
    mock_note.assert_not_called()
    client.upvote_post.assert_not_called()
    _content(agent).create_comment.assert_not_called()
    client.post_comment.assert_not_called()


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
            "DECISION_ENFORCE" in r.getMessage()
            and "relevance" in r.getMessage()
            and "fails closed" in r.getMessage()
            for r in caplog.records
        )


# ---------------------------------------------------------------------------
# domain.json: relevance_score4, and known_agent retired
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

    def test_the_packaged_config_carries_the_owners_score4_threshold(self):
        # The owner placed it after the labels (RFC-0046, S35 readings 2026-09-28:
        # the pre-registered rule picked t = 0.3). A change is the owner's again.
        assert load_domain_config().relevance_threshold_score4 == 0.3

    def test_known_agent_is_retired(self, tmp_path, caplog):
        """e1: the known-author threshold is gone from the config and the loader."""
        assert not hasattr(load_domain_config(), "known_agent_threshold")
        packaged = json.loads(
            (Path(__file__).resolve().parents[1] / "config" / "domain.json").read_text()
        )
        assert "known_agent" not in packaged["thresholds"]
        with caplog.at_level(logging.WARNING):
            load_domain_config(self._write(tmp_path, {"relevance": 0.8, "known_agent": 0.7}))
        assert "known_agent" in caplog.text


# ---------------------------------------------------------------------------
# resolve_enforce: the enum
# ---------------------------------------------------------------------------


class TestResolve:
    def _fields(self, p_top=0.9, reason="answered"):
        return {
            "decision_reason": reason,
            "decision_p_top": p_top if reason == "answered" else None,
        }

    def test_unconfigured_fails_closed(self):
        outcome = rs.resolve_enforce(self._fields(), 0.5)
        assert outcome == rs.EnforceOutcome("fail_closed", None, "enforce_unconfigured", None)

    def test_no_threshold_fails_closed(self):
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        outcome = rs.resolve_enforce(self._fields(), None)
        assert outcome == rs.EnforceOutcome("fail_closed", None, "enforce_no_threshold", None)

    def test_backend_null_fails_closed(self):
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        outcome = rs.resolve_enforce(self._fields(reason="http_error"), 0.5)
        assert outcome == rs.EnforceOutcome("fail_closed", None, "enforce_backend_null", 0.5)

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
        assert rs.CONFIGURATION_REASONS == {"enforce_unconfigured", "enforce_no_threshold"}

    def test_no_outcome_names_the_retired_live_gate(self):
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        for fields, threshold in [
            (self._fields(), 0.5),
            (self._fields(), None),
            (self._fields(reason="http_error"), 0.5),
        ]:
            assert rs.resolve_enforce(fields, threshold).gate_source != "live"


# ---------------------------------------------------------------------------
# The feed: one judge
# ---------------------------------------------------------------------------


class TestOneJudge:
    def test_the_feed_no_longer_holds_the_free_generated_scorer(self):
        assert not hasattr(fm_module, "score_relevance_detailed")
        for retired in ("_author_known", "_relevance_threshold", "_handle_below_threshold"):
            assert not hasattr(fm_module.FeedManager, retired), retired

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_feed_cycle_never_asks_the_free_generated_score(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_answered(0.9)))
        agent, client = _agent(tmp_path, posts=2)
        _comment_content(agent, text=None)
        with patch(
            "contemplative_agent.adapters.moltbook.llm_functions.score_relevance_detailed"
        ) as live:
            for _ in range(2):
                agent._run_feed_cycle(time.time() + 3600)
        live.assert_not_called()


class TestEnforced:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_pass_reads_the_full_body_notes_upvotes_and_comments(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_answered(0.9)))
        agent, client = _agent(tmp_path, threshold_score4=0.5)
        _comment_content(agent)
        client.post_comment.return_value = {"comment": {"id": "c1"}}
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["gate_source"] == "score4"
        assert row["enforce_gate"] is True
        assert row["enforce_reason"] == "enforced"
        assert row["enforce_threshold"] == 0.5
        assert row["decision_p_top"] == pytest.approx(0.9)
        # The comment path reads the full body, never the 500-char preview.
        client.get_post.assert_called_once_with("post1")
        body = _content(agent).create_comment.call_args.args[0]
        assert len(body) != FEED_CONTENT_PREVIEW_LEN
        mock_note.assert_called_once()
        client.upvote_post.assert_called_once_with("post1")
        client.post_comment.assert_called_once()

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_closed_post_gets_no_upvote_no_note_and_no_full_fetch(
        self, mock_note, tmp_path, caplog
    ):
        """b1: the upvote-only band below the gate is gone (Jev: S35 2/67, S36 0/71 on-topic)."""
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(_answered(0.29))
        _configure(backend)
        agent, client = _agent(tmp_path, threshold_score4=0.3)
        with caplog.at_level(logging.INFO):
            for _ in range(3):
                agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["gate_source"] == "score4"
        assert row["enforce_gate"] is False
        _assert_nothing_engaged(agent, client, mock_note)
        # A real verdict: memoized, asked once.
        assert backend.calls == 1
        assert "score4 gate closed" in caplog.text

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_the_enforced_judgment_is_memoized_with_the_post(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(_answered(0.9))
        _configure(backend)
        agent, _client = _agent(tmp_path, threshold_score4=0.5)
        # The comment comes back empty: the gate passes every cycle and the
        # post stays uncommented, so the feed offers it again.
        _comment_content(agent, text=None)
        for _ in range(3):
            agent._run_feed_cycle(time.time() + 3600)
        assert _content(agent).create_comment.call_count == 3
        assert backend.calls == 1
        assert len(_rows(tmp_path / "rlogs")) == 1

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_known_author_gets_no_lower_bar(self, mock_note, tmp_path):
        """e1: interacting with an author before no longer lowers the cut."""
        _configure(_StubBackend(_answered(0.25)))
        agent, client = _agent(tmp_path, threshold_score4=0.3, author={"id": "a1", "name": "Al"})
        with patch.object(agent._ctx.memory, "has_interacted_with", return_value=True):
            agent._run_feed_cycle(time.time() + 3600)
        _assert_nothing_engaged(agent, client, mock_note)


class TestEpisodeKey:
    """g2: the comment episode carries the gate's value under its own key."""

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_the_comment_episode_has_relevance_p_top_and_no_relevance(self, mock_note, tmp_path):
        _configure(_StubBackend(_answered(0.87654)))
        agent, client = _agent(tmp_path, threshold_score4=0.3)
        _comment_content(agent)
        client.post_comment.return_value = {"comment": {"id": "c1"}}
        agent._run_feed_cycle(time.time() + 3600)
        (episode,) = [
            r
            for r in agent._ctx.memory.episodes.read_range(days=1, record_type="activity")
            if r.get("data", {}).get("action") == "comment"
        ]
        assert episode["data"]["relevance_p_top"] == pytest.approx(0.8765)
        assert "relevance" not in episode["data"]
        assert agent._ctx.actions_taken == ["Commented on post1 (relevance P(top): 0.88)"]


# ---------------------------------------------------------------------------
# The feed: fail-closed
# ---------------------------------------------------------------------------


class TestFailClosed:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_without_enforce_the_feed_engages_with_nothing(self, mock_note, tmp_path, caplog):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(_answered(1.0))
        _configure(backend, enforce=frozenset())
        agent, client = _agent(tmp_path)
        with caplog.at_level(logging.WARNING):
            for _ in range(3):
                agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["gate_source"] == "fail_closed"
        assert row["enforce_gate"] is None
        assert row["enforce_reason"] == "enforce_unconfigured"
        assert row["enforce_threshold"] is None
        _assert_nothing_engaged(agent, client, mock_note)
        # The answered read is reused in the session (one row), never memoized
        # as a verdict, and the configuration cause is one WARNING per session.
        assert backend.calls == 1
        assert agent._feed_manager.rejudges_skipped == 0
        warnings = [r for r in caplog.records if "enforce_unconfigured" in r.getMessage()]
        assert len(warnings) == 1 and warnings[0].levelno == logging.WARNING

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_no_threshold_is_named_and_engages_with_nothing(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_answered(1.0)))
        agent, client = _agent(tmp_path, threshold_score4=None)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["gate_source"] == "fail_closed"
        assert row["enforce_reason"] == "enforce_no_threshold"
        assert row["enforce_gate"] is None
        _assert_nothing_engaged(agent, client, mock_note)

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_an_abstain_is_asked_again_next_cycle_and_never_memoized(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(_abstain("http_error"))
        _configure(backend)
        agent, client = _agent(tmp_path)
        for _ in range(3):
            agent._run_feed_cycle(time.time() + 3600)
        rows = _rows(tmp_path / "rlogs")
        assert [r["enforce_reason"] for r in rows] == ["enforce_backend_null"] * 3
        assert {r["gate_source"] for r in rows} == {"fail_closed"}
        assert rows[0]["decision_reason"] == "http_error"
        assert rows[0]["enforce_threshold"] == 0.5
        assert backend.calls == 3
        assert agent._feed_manager.rejudges_skipped == 0
        _assert_nothing_engaged(agent, client, mock_note)

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_fail_closed_post_ends_the_cycle(self, mock_note, tmp_path, caplog):
        """No answer, no engagement this cycle: the rest of the feed is not asked."""
        backend = _StubBackend(_abstain("timeout"))
        _configure(backend)
        agent, client = _agent(tmp_path, posts=3)
        with caplog.at_level(logging.INFO):
            agent._run_feed_cycle(time.time() + 3600)
        assert backend.calls == 1
        assert "ending this feed cycle" in caplog.text
        # The next cycle starts over and asks again.
        agent._run_feed_cycle(time.time() + 3600)
        assert backend.calls == 2

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_post_level_abstain_skips_the_post_not_the_cycle(self, mock_note, tmp_path):
        """``no_option_observed`` comes from the post's text: ending the cycle on
        it would starve every later post while it stays in the feed."""

        class _FirstPostUnreadable(_StubBackend):
            def decide(self, state, questions, *, system=""):
                self.calls += 1
                if self.calls == 1:
                    return _abstain("no_option_observed")
                return _answered(0.9)

        backend = _FirstPostUnreadable()
        _configure(backend)
        agent, client = _agent(tmp_path, posts=3)
        _comment_content(agent, text=None)
        agent._run_feed_cycle(time.time() + 3600)
        assert backend.calls == 3
        assert client.upvote_post.call_count == 2
        assert {c.args[0] for c in client.upvote_post.call_args_list} == {"post2", "post3"}

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_no_backend_is_backend_null(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        configure(decision_enforce=frozenset({DECISION_FACE_RELEVANCE}))
        agent, client = _agent(tmp_path)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["decision_reason"] == "unconfigured"
        assert row["enforce_reason"] == "enforce_backend_null"
        assert row["gate_source"] == "fail_closed"
        _assert_nothing_engaged(agent, client, mock_note)

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_an_exception_in_resolving_fails_closed(self, mock_note, tmp_path, caplog):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(_answered(0.9)))
        agent, client = _agent(tmp_path)
        _comment_content(agent)
        with (
            patch.object(rs, "_resolve", side_effect=RuntimeError("boom")),
            caplog.at_level(logging.WARNING),
        ):
            agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["gate_source"] == "fail_closed"
        assert row["enforce_reason"] == "enforce_exception"
        assert row["enforce_gate"] is None
        _assert_nothing_engaged(agent, client, mock_note)
        assert "fails closed" in caplog.text

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_raising_backend_degrades_to_backend_null(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _configure(_StubBackend(exc=RuntimeError("down")))
        agent, client = _agent(tmp_path)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["decision_reason"] == "backend_exception"
        assert row["enforce_reason"] == "enforce_backend_null"
        assert row["gate_source"] == "fail_closed"
        _assert_nothing_engaged(agent, client, mock_note)

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_malformed_answer_fails_closed(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        answer = QuestionAnswer(
            id="relevance", probabilities=(("a", 1.0),), reason="answered", observed=1
        )
        short = DecisionResult(model="stub:1b", latency_ms=1, answers=(answer,), reason="answered")
        _configure(_StubBackend(short))
        agent, client = _agent(tmp_path)
        _comment_content(agent)
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "rlogs")
        assert row["decision_reason"] == "backend_exception"
        assert row["enforce_reason"] == "enforce_backend_null"
        assert row["gate_source"] == "fail_closed"
        _assert_nothing_engaged(agent, client, mock_note)


class TestRecorderOff:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_enforce_still_decides_the_gate_without_an_audit_dir(self, mock_note, tmp_path):
        # The recorder's kill switch (audit_dir unset) is not the gate's.
        _configure(_StubBackend(_answered(0.9)))
        agent, client = _agent(tmp_path)
        _comment_content(agent)
        client.post_comment.return_value = {"comment": {"id": "c1"}}
        agent._run_feed_cycle(time.time() + 3600)
        _content(agent).create_comment.assert_called_once()

    def test_with_recorder_and_gate_off_nothing_is_asked(self):
        backend = _StubBackend(_answered(0.9))
        configure(decision_backend=backend, decision_faces=frozenset({DECISION_FACE_RELEVANCE}))
        reading = rs.enforce_and_record("post-1", "body", threshold_score4=0.3)
        assert reading == rs.RecordedReading(rs.CLOSED_UNCONFIGURED, None)
        assert backend.calls == 0


def test_row_carries_the_four_enforce_fields_and_no_live_half(tmp_path):
    rs.configure_relevance_shadow(audit_dir=tmp_path)
    rs.enforce_and_record("post-1", "body", threshold_score4=0.3)
    (row,) = _rows(tmp_path)
    for name in ENFORCE_FIELDS:
        assert name in row
    for name in RETIRED_ROW_FIELDS:
        assert name not in row, name
    assert row["gate_source"] == "fail_closed"
    assert row["enforce_reason"] == "enforce_unconfigured"
