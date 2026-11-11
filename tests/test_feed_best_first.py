# pyright: reportPrivateUsage=false
"""The feed cycle scores every candidate first, then engages best-first (RFC-0075 S54).

Pinned: the cycle runs in two stages — every candidate through the engagement
gates and the score4 gate, then the ones at or above ``relevance_score4``
engaged in descending P(top) — each post is scored once, a post under the cut
is never engaged, and each candidate of each cycle gets one feed-order row
(``logs/feed-order-{date}.jsonl``) with a closed reason code and no post body,
title or author name.

The LLM seams are the two backends (``configure``): a decision backend that
answers each post's score4 question with the P(top) the test assigns it (found
by a marker word in the post text), and ``ChaosBackend`` for the pre-action
note's generation. Nothing inside the feed manager is patched but its clock.
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook import feed_manager as fm_module, feed_order
from contemplative_agent.core import relevance_state
from contemplative_agent.core.llm import (
    DecisionResult,
    QuestionAnswer,
    configure,
    reset_llm_config,
)
from tests.chaos import ChaosBackend
from tests.test_agent import _make_agent

THRESHOLD = 0.3
ROW_KEYS = {
    "ts",
    "cycle_id",
    "post_id",
    "source",
    "arrival",
    "rank",
    "p_top",
    "threshold",
    "reason",
    # stamped by the shared writer (append_jsonl_restricted)
    "run_id",
    "session_id",
}


class _ByMarker:
    """A decision backend: P(top) by the marker word found in the post text."""

    def __init__(self, p_by_marker: dict[str, float]):
        self.p_by_marker = p_by_marker
        self.asked: list[str] = []

    @property
    def model(self) -> str:
        return "stub:1b"

    def decide(self, state, questions, *, system=""):
        marker = next(m for m in self.p_by_marker if m in state)
        self.asked.append(marker)
        p_top = self.p_by_marker[marker]
        question = relevance_state.score4_question()
        rest = (1.0 - p_top) / 3
        answer = QuestionAnswer(
            id=question.id,
            probabilities=tuple(zip(question.levels, (rest, rest, rest, p_top), strict=True)),
            reason="answered",
            observed=4,
        )
        return DecisionResult(model="stub:1b", latency_ms=1, answers=(answer,), reason="answered")


class _Clock:
    """feed_manager's ``time``: a clock the test moves, and a sleep that does not wait."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def time(self) -> float:
        return self.now

    def sleep(self, _seconds: float) -> None:
        return None


@pytest.fixture(autouse=True)
def generation(monkeypatch):
    """The generation backend (the pre-action note); its ``calls`` say whether one ran."""
    monkeypatch.setattr(fm_module.random, "uniform", lambda a, b: 0.0)
    reset_llm_config()
    backend = ChaosBackend()
    configure(backend=backend)
    yield backend
    reset_llm_config()
    feed_order.reset_feed_order()


def _post(pid: str, marker: str, **extra) -> dict:
    return {"id": pid, "content": f"A short post about {marker} and nothing else.", **extra}


def _agent(tmp_path, submolt_posts, *, following=(), p_by_marker):
    decision = _ByMarker(p_by_marker)
    configure(decision_backend=decision)
    feed_order.configure_feed_order(audit_dir=tmp_path / "logs")
    agent, client, scheduler = _make_agent(tmp_path, content=MagicMock())
    fm = agent._feed_manager
    fm._domain = dataclasses.replace(fm._domain, relevance_threshold_score4=THRESHOLD)
    client.has_read_budget.return_value = True
    client.has_write_budget.return_value = True
    client.get_following_feed.return_value = list(following)
    client.get_submolt_feed.return_value = list(submolt_posts)
    client.upvote_post.return_value = True
    client.post_comment.return_value = {"comment": {"id": "c1"}}
    content = cast(MagicMock, fm._get_content())
    content.create_comment.return_value = MagicMock(
        text="a comment", thinking="", selection_id=None
    )
    return agent, client, scheduler, decision


def _rows(logs: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(logs.glob("feed-order-*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _by_post(rows: list[dict]) -> dict[str, dict]:
    return {r["post_id"]: r for r in rows}


def _commented_ids(client) -> list[str]:
    return [c.args[0] for c in client.post_comment.call_args_list]


class TestBestFirst:
    def test_passed_candidates_are_engaged_in_descending_p_top(self, tmp_path):
        """(i) Three posts over the cut, arriving 0.4 / 0.9 / 0.6: engaged 0.9, 0.6, 0.4."""
        posts = [_post("p1", "alpha"), _post("p2", "bravo"), _post("p3", "charlie")]
        agent, client, _, decision = _agent(
            tmp_path, posts, p_by_marker={"alpha": 0.4, "bravo": 0.9, "charlie": 0.6}
        )

        agent._run_feed_cycle(time.time() + 3600)

        assert _commented_ids(client) == ["p2", "p3", "p1"]
        # Scored once each: the engagement stage reuses the scoring stage's read.
        assert sorted(decision.asked) == ["alpha", "bravo", "charlie"]
        rows = _by_post(_rows(tmp_path / "logs"))
        assert {pid: r["rank"] for pid, r in rows.items()} == {"p2": 1, "p3": 2, "p1": 3}
        assert {pid: r["arrival"] for pid, r in rows.items()} == {"p1": 0, "p2": 1, "p3": 2}
        assert {r["reason"] for r in rows.values()} == {"commented"}
        assert rows["p2"]["p_top"] == pytest.approx(0.9)
        assert {r["threshold"] for r in rows.values()} == {THRESHOLD}
        assert len({r["cycle_id"] for r in rows.values()}) == 1

    def test_a_post_under_the_cut_is_not_engaged_and_is_recorded_below_threshold(self, tmp_path):
        """(ii) The cut stays a cut: no upvote, no note, no comment under it."""
        posts = [_post("p1", "alpha"), _post("p2", "bravo")]
        agent, client, _, _ = _agent(tmp_path, posts, p_by_marker={"alpha": 0.1, "bravo": 0.9})

        agent._run_feed_cycle(time.time() + 3600)

        assert _commented_ids(client) == ["p2"]
        assert [c.args[0] for c in client.upvote_post.call_args_list] == ["p2"]
        rows = _by_post(_rows(tmp_path / "logs"))
        assert rows["p1"]["reason"] == "below_threshold"
        assert rows["p1"]["p_top"] == pytest.approx(0.1)
        assert rows["p1"]["rank"] == 2
        assert rows["p2"]["reason"] == "commented"

    def test_end_time_in_the_engagement_stage_leaves_the_rest_not_reached(
        self, tmp_path, monkeypatch
    ):
        """(iii) The session ends after the best post: the other two are recorded unreached."""
        clock = _Clock()
        monkeypatch.setattr(fm_module, "time", clock)
        posts = [_post("p1", "alpha"), _post("p2", "bravo"), _post("p3", "charlie")]
        agent, client, scheduler, decision = _agent(
            tmp_path, posts, p_by_marker={"alpha": 0.5, "bravo": 0.9, "charlie": 0.7}
        )

        def _session_ends() -> None:
            clock.now += 100.0

        scheduler.wait_for_comment.side_effect = _session_ends

        agent._feed_manager.run_cycle(client, scheduler, clock.now + 10.0)

        assert _commented_ids(client) == ["p2"]
        # All three were scored before the session ran out.
        assert sorted(decision.asked) == ["alpha", "bravo", "charlie"]
        rows = _by_post(_rows(tmp_path / "logs"))
        assert rows["p2"]["reason"] == "commented"
        assert rows["p3"]["reason"] == "not_reached_end_time"
        assert rows["p1"]["reason"] == "not_reached_end_time"
        assert (rows["p3"]["rank"], rows["p1"]["rank"]) == (2, 3)
        # Not reached costs nothing: no full-body work, no upvote for them.
        assert [c.args[0] for c in client.upvote_post.call_args_list] == ["p2"]

    def test_the_record_carries_no_body_title_or_author(self, tmp_path):
        """(iv) Ids, numbers and closed codes only."""
        body = "An unmistakable sentence about alpha that must stay out of the record."
        post = {
            "id": "p1",
            "content": body,
            "title": "A distinctive title line",
            "author": {"name": "AuthorNameXYZ"},
        }
        agent, client, _, _ = _agent(tmp_path, [post], p_by_marker={"alpha": 0.9})

        agent._run_feed_cycle(time.time() + 3600)

        logs = tmp_path / "logs"
        text = "".join(p.read_text(encoding="utf-8") for p in logs.glob("feed-order-*.jsonl"))
        for secret in (body, "unmistakable", "distinctive title", "AuthorNameXYZ", "a comment"):
            assert secret not in text, secret
        (row,) = _rows(logs)
        assert set(row) <= ROW_KEYS
        assert {"post_id", "source", "rank", "p_top", "threshold", "reason"} <= set(row)


class TestReasonCodes:
    def test_source_names_the_feed_a_candidate_came_from(self, tmp_path):
        agent, _, _, _ = _agent(
            tmp_path,
            [_post("s1", "bravo"), _post("f1", "alpha")],
            following=[_post("f1", "alpha")],
            p_by_marker={"alpha": 0.9, "bravo": 0.8},
        )
        agent._run_feed_cycle(time.time() + 3600)
        rows = _rows(tmp_path / "logs")
        # f1 came through both sources and is one candidate, the following feed's.
        assert [(r["post_id"], r["source"]) for r in rows] == [
            ("f1", "following"),
            ("s1", "submolt"),
        ]

    def test_a_gate_skipped_post_is_recorded_unscored(self, tmp_path):
        agent, client, _, decision = _agent(
            tmp_path,
            [_post("p1", "alpha"), _post("p2", "bravo")],
            p_by_marker={"alpha": 0.9, "bravo": 0.9},
        )
        agent._ctx.commented_posts.add("p1")
        agent._run_feed_cycle(time.time() + 3600)
        rows = _by_post(_rows(tmp_path / "logs"))
        assert rows["p1"]["reason"] == "skipped_gate"
        assert rows["p1"]["p_top"] is None and rows["p1"]["rank"] is None
        assert decision.asked == ["bravo"]

    def test_a_backend_that_stops_answering_skips_the_engagement_stage(self, tmp_path, generation):
        """The first post passes, the second gets no answer, the third is never asked.

        The decision backend timing out means the local model is not
        answering: the engagement stage does not run (its note and comment
        would each wait out a timeout), and the passed post carries to the
        next cycle as ``not_reached_fail_closed``.
        """

        class _SecondTimesOut(_ByMarker):
            def decide(self, state, questions, *, system=""):
                if "bravo" in state:
                    self.asked.append("bravo")
                    answer = QuestionAnswer(
                        id="relevance", probabilities=(), reason="timeout", observed=0
                    )
                    return DecisionResult(
                        model="stub:1b", latency_ms=1, answers=(answer,), reason="timeout"
                    )
                return super().decide(state, questions, system=system)

        backend = _SecondTimesOut({"alpha": 0.9, "charlie": 0.9})
        posts = [_post("p1", "alpha"), _post("p2", "bravo"), _post("p3", "charlie")]
        agent, client, _, _ = _agent(tmp_path, posts, p_by_marker={})
        configure(decision_backend=backend)
        fm = agent._feed_manager

        with patch.object(fm, "_engagement_stage", wraps=fm._engagement_stage) as stage:
            agent._run_feed_cycle(time.time() + 3600)

        stage.assert_not_called()
        assert backend.asked == ["alpha", "bravo"]
        assert generation.calls == []
        client.upvote_post.assert_not_called()
        client.post_comment.assert_not_called()
        rows = _by_post(_rows(tmp_path / "logs"))
        assert [rows[p]["reason"] for p in ("p1", "p2", "p3")] == [
            "not_reached_fail_closed",
            "fail_closed",
            "not_reached_fail_closed",
        ]
        assert rows["p1"]["p_top"] == pytest.approx(0.9)

    def test_another_cycle_level_fail_closed_still_engages_what_passed(self, tmp_path):
        """Resolving the second post's outcome raises (``enforce_exception``): the
        backend answered, so the post that passed before it is engaged."""
        from contemplative_agent.adapters.moltbook import relevance_gate as rs

        real_resolve = rs._resolve
        calls = {"n": 0}

        def _second_raises(decision, threshold):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom")
            return real_resolve(decision, threshold)

        posts = [_post("p1", "alpha"), _post("p2", "bravo"), _post("p3", "charlie")]
        agent, client, _, _ = _agent(
            tmp_path, posts, p_by_marker={"alpha": 0.9, "bravo": 0.9, "charlie": 0.9}
        )
        with patch.object(rs, "_resolve", side_effect=_second_raises):
            agent._run_feed_cycle(time.time() + 3600)

        assert _commented_ids(client) == ["p1"]
        rows = _by_post(_rows(tmp_path / "logs"))
        assert [rows[p]["reason"] for p in ("p1", "p2", "p3")] == [
            "commented",
            "fail_closed",
            "not_reached_fail_closed",
        ]

    def test_an_exception_in_the_engagement_stage_still_writes_every_row(self, tmp_path):
        """The cycle raises mid-engagement: each candidate still gets its row, the
        unfinished ones as ``aborted_exception``."""
        posts = [_post("p1", "alpha"), _post("p2", "bravo"), _post("p3", "charlie")]
        agent, client, scheduler, _ = _agent(
            tmp_path, posts, p_by_marker={"alpha": 0.9, "bravo": 0.6, "charlie": 0.1}
        )
        content = cast(MagicMock, agent._feed_manager._get_content())
        content.create_comment.side_effect = RuntimeError("generation blew up")

        with pytest.raises(RuntimeError, match="generation blew up"):
            agent._feed_manager.run_cycle(client, scheduler, time.time() + 3600)

        rows = _by_post(_rows(tmp_path / "logs"))
        assert [rows[p]["reason"] for p in ("p1", "p2", "p3")] == [
            "aborted_exception",
            "aborted_exception",
            "below_threshold",
        ]
        assert (rows["p1"]["rank"], rows["p2"]["rank"]) == (1, 2)

    def test_a_candidate_without_a_reason_raises_after_writing_the_rest(self, tmp_path):
        """A missing reason is a broken invariant: never written as a guessed outcome."""
        agent, _, _, _ = _agent(tmp_path, [], p_by_marker={})
        candidates = [("submolt", {"id": "p1"}), ("submolt", {"id": "p2"})]

        with pytest.raises(RuntimeError, match=r"arrival \[1\]"):
            agent._feed_manager._record_order(candidates, ["below_threshold", None], [0.1, None])

        assert [(r["post_id"], r["reason"]) for r in _rows(tmp_path / "logs")] == [
            ("p1", "below_threshold")
        ]

    def test_the_comment_limit_is_its_own_reason(self, tmp_path):
        agent, client, scheduler, _ = _agent(
            tmp_path, [_post("p1", "alpha")], p_by_marker={"alpha": 0.9}
        )
        scheduler.can_comment.return_value = False
        agent._run_feed_cycle(time.time() + 3600)
        (row,) = _rows(tmp_path / "logs")
        assert row["reason"] == "comment_limit"
        client.post_comment.assert_not_called()

    def test_every_written_reason_is_in_the_closed_vocabulary(self, tmp_path):
        agent, _, _, _ = _agent(
            tmp_path,
            [_post("p1", "alpha"), _post("p2", "bravo")],
            p_by_marker={"alpha": 0.9, "bravo": 0.1},
        )
        agent._run_feed_cycle(time.time() + 3600)
        rows = _rows(tmp_path / "logs")
        assert rows and {r["reason"] for r in rows} <= set(feed_order.FEED_ORDER_REASONS)
        assert {r["source"] for r in rows} <= set(feed_order.CANDIDATE_SOURCES)

    def test_the_writer_is_off_unless_configured(self, tmp_path):
        agent, client, _, _ = _agent(tmp_path, [_post("p1", "alpha")], p_by_marker={"alpha": 0.9})
        feed_order.reset_feed_order()
        agent._run_feed_cycle(time.time() + 3600)
        assert _commented_ids(client) == ["p1"]
        assert not list((tmp_path / "logs").glob("feed-order-*.jsonl"))


def test_the_census_reads_the_record_with_the_writers_vocabulary():
    import sys

    from tests._shell_harness import REPO_ROOT

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import _census_registry as reg  # type: ignore[import-not-found]

    entry = next(e for e in reg.REGISTRY if e.matches("feed-order-2026-11-11.jsonl"))
    assert entry.status == reg.LIVE
    vocab = dict(entry.enum_values)
    assert set(vocab["reason"]) == set(feed_order.FEED_ORDER_REASONS)
    assert set(vocab["source"]) == set(feed_order.CANDIDATE_SOURCES)
