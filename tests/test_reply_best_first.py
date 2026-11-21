# pyright: reportPrivateUsage=false
"""The reply cycle scores every candidate first, then replies best-first (RFC-0075 S57).

Pinned: on each route the reply cycle runs in two stages — every counterparty
comment through the dedup, promotional and per-thread checks and the score4
gate on its text, then the ones at or above ``relevance_score4`` replied to in
descending P(top) — each comment is scored once, a comment under the cut is
never replied to, the same counterparty on the same post gets at most
``THREAD_REPLY_CAP_24H`` replies in 24 hours, and each candidate of each cycle
gets one reply-order row (``logs/reply-order-{date}.jsonl``) with a closed
reason code and no comment body, post body or counterparty name.

The LLM seams are the two backends (``configure``): a decision backend that
answers each comment's score4 question with the P(top) the test assigns it (a
marker word in the comment text, ``tests/_score4_stub.py``), and
``ChaosBackend`` for the note and the reply generation. Nothing inside the
reply handler is patched but its clock.
"""

from __future__ import annotations

import dataclasses
import json
import time
from pathlib import Path

import pytest

from contemplative_agent.adapters.moltbook import (
    relevance_cache,
    relevance_gate,
    reply_handler as rh_module,
    reply_order,
)
from contemplative_agent.core.llm import configure, reset_llm_config
from tests._score4_stub import Score4ByMarker
from tests.chaos import ChaosBackend
from tests.test_agent import _make_agent

THRESHOLD = 0.3
ROW_KEYS = {
    "ts",
    "cycle_id",
    "comment_id",
    "post_id",
    "route",
    "arrival",
    "rank",
    "p_top",
    "threshold",
    "reason",
    # stamped by the shared writer (append_jsonl_restricted)
    "run_id",
    "session_id",
}


class _Clock:
    """reply_handler's ``time``: a clock the test moves."""

    def __init__(self, now: float = 1000.0):
        self.now = now

    def time(self) -> float:
        return self.now


@pytest.fixture(autouse=True)
def generation():
    """The generation backend (note and reply); its ``calls`` say whether one ran."""
    reset_llm_config()
    backend = ChaosBackend()
    configure(backend=backend)
    yield backend
    reset_llm_config()


def _comment(cid: str, marker: str, author: str, **extra) -> dict:
    return {
        "id": cid,
        "content": f"A short comment about {marker} and nothing else.",
        "author": {"name": author},
        **extra,
    }


def _agent(tmp_path, comments, *, p_by_marker, decision=True):
    backend = Score4ByMarker(p_by_marker)
    if decision:
        configure(decision_backend=backend)
    reply_order.configure_reply_order(audit_dir=tmp_path / "logs")
    relevance_gate.configure_relevance_gate(audit_dir=tmp_path / "logs")
    agent, client, scheduler = _make_agent(tmp_path)
    handler = agent._reply_handler
    handler._domain = dataclasses.replace(handler._domain, relevance_threshold_score4=THRESHOLD)
    client.has_read_budget.return_value = True
    client.has_write_budget.return_value = True
    client.get_post_comments.return_value = list(comments)
    client.post_comment.return_value = {"comment": {"id": "r1"}}
    return agent, client, scheduler, backend


def _home(*post_ids: str) -> dict:
    return {
        "activity_on_your_posts": [
            {"post_id": pid, "new_notification_count": 1} for pid in post_ids
        ]
    }


def _rows(logs: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(logs.glob("reply-order-*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _by_comment(rows: list[dict]) -> dict[str, dict]:
    return {r["comment_id"]: r for r in rows}


def _parents(client) -> list[str | None]:
    return [c.kwargs.get("parent_id") for c in client.post_comment.call_args_list]


class TestBestFirst:
    def test_passed_candidates_are_replied_to_in_descending_p_top(self, tmp_path):
        """(i) Three comments over the cut, arriving 0.4 / 0.9 / 0.6: replied 0.9, 0.6, 0.4."""
        comments = [
            _comment("c1", "alpha", "Alice"),
            _comment("c2", "bravo", "Bob"),
            _comment("c3", "charlie", "Carol"),
        ]
        agent, client, scheduler, decision = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.4, "bravo": 0.9, "charlie": 0.6}
        )

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        assert _parents(client) == ["c2", "c3", "c1"]
        # Scored once each: the reply stage reuses the scoring stage's read.
        assert sorted(m for m in decision.asked if m) == ["alpha", "bravo", "charlie"]
        rows = _by_comment(_rows(tmp_path / "logs"))
        assert {cid: r["rank"] for cid, r in rows.items()} == {"c2": 1, "c3": 2, "c1": 3}
        assert {cid: r["arrival"] for cid, r in rows.items()} == {"c1": 0, "c2": 1, "c3": 2}
        assert {r["reason"] for r in rows.values()} == {"replied"}
        assert {r["route"] for r in rows.values()} == {"home_activity"}
        assert {r["post_id"] for r in rows.values()} == {"p1"}
        assert rows["c2"]["p_top"] == pytest.approx(0.9)
        assert {r["threshold"] for r in rows.values()} == {THRESHOLD}
        assert len({r["cycle_id"] for r in rows.values()}) == 1
        # Every candidate settled, so the post's notifications are marked read.
        client.mark_notifications_read_by_post.assert_called_once_with("p1")

    def test_a_comment_under_the_cut_is_not_replied_to_and_is_recorded_below_threshold(
        self, tmp_path
    ):
        """(ii) The cut stays a cut: no note, no reply under it."""
        comments = [_comment("c1", "alpha", "Alice"), _comment("c2", "bravo", "Bob")]
        agent, client, scheduler, _ = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.1, "bravo": 0.9}
        )

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        assert _parents(client) == ["c2"]
        rows = _by_comment(_rows(tmp_path / "logs"))
        assert rows["c1"]["reason"] == "below_threshold"
        assert rows["c1"]["p_top"] == pytest.approx(0.1)
        assert rows["c1"]["rank"] == 2
        assert rows["c2"]["reason"] == "replied"

    def test_a_closed_comment_is_scored_once_per_session(self, tmp_path):
        """The memo answers the next cycle's sight of the same comment without a read."""
        comments = [_comment("c1", "alpha", "Alice")]
        agent, client, scheduler, decision = _agent(tmp_path, comments, p_by_marker={"alpha": 0.1})
        handler = agent._reply_handler

        handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))
        handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        assert decision.asked == ["alpha"]
        rows = _rows(tmp_path / "logs")
        assert [r["reason"] for r in rows] == ["below_threshold", "below_threshold"]
        assert len({r["cycle_id"] for r in rows}) == 2


class TestThreadCap:
    def test_the_third_reply_to_one_counterparty_on_one_post_is_capped(self, tmp_path):
        """(iii) Alice x p1 three times, all over the cut: two replies, the third thread_cap."""
        comments = [
            _comment("c1", "alpha", "Alice"),
            _comment("c2", "bravo", "Alice"),
            _comment("c3", "charlie", "Alice"),
        ]
        agent, client, scheduler, _ = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.5, "bravo": 0.9, "charlie": 0.7}
        )

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        assert rh_module.THREAD_REPLY_CAP_24H == 2
        assert _parents(client) == ["c2", "c3"]
        rows = _by_comment(_rows(tmp_path / "logs"))
        assert rows["c1"]["reason"] == "thread_cap"
        assert rows["c2"]["reason"] == "replied"
        assert rows["c3"]["reason"] == "replied"

    def test_replies_from_an_earlier_session_count_and_the_comment_is_not_scored(self, tmp_path):
        """The cap reads the sent-reply records, so it holds across cycles and sessions."""
        comments = [_comment("c9", "alpha", "Alice"), _comment("c8", "bravo", "Bob")]
        agent, client, scheduler, decision = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.9, "bravo": 0.9}
        )
        for _ in range(2):
            agent._memory.record_interaction(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                agent_id="unknown",
                agent_name="Alice",
                post_id="p1",
                direction="sent",
                content="an earlier reply",
                interaction_type="reply",
            )

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        assert _parents(client) == ["c8"]
        assert decision.asked == ["bravo"]
        rows = _by_comment(_rows(tmp_path / "logs"))
        assert rows["c9"]["reason"] == "thread_cap"
        assert rows["c9"]["p_top"] is None and rows["c9"]["rank"] is None

    def test_the_same_counterparty_on_another_post_is_not_capped(self, tmp_path):
        comments = [_comment("c1", "alpha", "Alice")]
        agent, client, scheduler, _ = _agent(tmp_path, comments, p_by_marker={"alpha": 0.9})
        for _ in range(2):
            agent._memory.record_interaction(
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
                agent_id="unknown",
                agent_name="Alice",
                post_id="p-other",
                direction="sent",
                content="an earlier reply",
                interaction_type="reply",
            )

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        assert _parents(client) == ["c1"]


class TestStops:
    def test_end_time_in_the_reply_stage_leaves_the_rest_not_reached(self, tmp_path, monkeypatch):
        """(iv) The session ends after the best comment: the other two are recorded unreached."""
        clock = _Clock()
        monkeypatch.setattr(rh_module, "time", clock)
        comments = [
            _comment("c1", "alpha", "Alice"),
            _comment("c2", "bravo", "Bob"),
            _comment("c3", "charlie", "Carol"),
        ]
        agent, client, scheduler, _ = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.5, "bravo": 0.9, "charlie": 0.7}
        )

        def _session_ends() -> None:
            clock.now += 100.0

        scheduler.wait_for_comment.side_effect = _session_ends

        agent._reply_handler.run_cycle_from_home(client, scheduler, clock.now + 10.0, _home("p1"))

        assert _parents(client) == ["c2"]
        rows = _by_comment(_rows(tmp_path / "logs"))
        assert rows["c2"]["reason"] == "replied"
        assert rows["c3"]["reason"] == "not_reached_end_time"
        assert rows["c1"]["reason"] == "not_reached_end_time"
        # Scored in stage 1, so the unreached ones keep their P(top) and rank.
        assert rows["c3"]["rank"] == 2 and rows["c1"]["rank"] == 3
        # Unreached comments carry over: the post is not marked read.
        client.mark_notifications_read_by_post.assert_not_called()

    def test_no_decision_backend_fails_closed_and_replies_to_nothing(self, tmp_path):
        comments = [_comment("c1", "alpha", "Alice"), _comment("c2", "bravo", "Bob")]
        agent, client, scheduler, _ = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.9, "bravo": 0.9}, decision=False
        )

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        client.post_comment.assert_not_called()
        rows = _by_comment(_rows(tmp_path / "logs"))
        assert rows["c1"]["reason"] == "fail_closed"
        assert rows["c2"]["reason"] == "not_reached_fail_closed"
        client.mark_notifications_read_by_post.assert_not_called()

    def test_comment_limit_after_the_first_reply_carries_the_rest(self, tmp_path):
        """The 20 s comment interval closes after a reply; the next cycle takes the next best."""
        comments = [_comment("c1", "alpha", "Alice"), _comment("c2", "bravo", "Bob")]
        agent, client, scheduler, _ = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.5, "bravo": 0.9}
        )
        interval = {"open": True}
        scheduler.can_comment.side_effect = lambda: interval["open"]
        scheduler.record_comment.side_effect = lambda: interval.update(open=False)

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        rows = _by_comment(_rows(tmp_path / "logs"))
        assert rows["c2"]["reason"] == "replied"
        assert rows["c1"]["reason"] == "not_reached_comment_limit"


class TestOtherCodes:
    def test_already_replied_and_promotional_are_recorded_and_not_scored(self, tmp_path):
        comments = [
            _comment("c1", "alpha", "Alice"),
            {
                "id": "c2",
                "content": "Boost your bravo karma at hxxps://agentflex.vip/start",
                "author": {"name": "Spam"},
            },
            _comment("c3", "charlie", "Carol"),
        ]
        agent, client, scheduler, decision = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.9, "bravo": 0.9, "charlie": 0.9}
        )
        agent._ctx.commented_posts.add("reply:p1:c1")

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        rows = _by_comment(_rows(tmp_path / "logs"))
        assert rows["c1"]["reason"] == "already_replied"
        assert rows["c2"]["reason"] == "promotional"
        assert rows["c3"]["reason"] == "replied"
        assert decision.asked == ["charlie"]

    def test_the_notification_route_scores_the_carried_text_and_replies_top_level(self, tmp_path):
        agent, client, scheduler, _ = _agent(tmp_path, [], p_by_marker={"alpha": 0.8})
        client.get_notifications.return_value = [
            {
                "type": "comment",
                "id": "n1",
                "post_id": "p1",
                "content": "A short comment about alpha and nothing else.",
                "post_content": "The post body.",
                "agent_name": "Alice",
            }
        ]
        agent._ctx.own_post_ids = set()

        agent._reply_handler.run_cycle(client, scheduler, time.time() + 3600)

        assert _parents(client) == [None]
        (row,) = _rows(tmp_path / "logs")
        assert row["route"] == "notification"
        assert row["comment_id"] == "n1"
        assert row["reason"] == "replied"

    def test_the_own_post_scan_route_is_named(self, tmp_path):
        comments = [_comment("c1", "alpha", "Alice")]
        agent, client, scheduler, _ = _agent(tmp_path, comments, p_by_marker={"alpha": 0.8})
        client.get_notifications.return_value = []
        agent._ctx.own_post_ids = {"p1"}

        agent._reply_handler.run_cycle(client, scheduler, time.time() + 3600)

        (row,) = _rows(tmp_path / "logs")
        assert row["route"] == "own_post_scan"
        assert row["reason"] == "replied"

    def test_every_reason_and_route_written_is_in_the_closed_vocabulary(self, tmp_path):
        comments = [_comment("c1", "alpha", "Alice"), _comment("c2", "bravo", "Bob")]
        agent, client, scheduler, _ = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.1, "bravo": 0.9}
        )

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        rows = _rows(tmp_path / "logs")
        assert rows
        assert {r["reason"] for r in rows} <= set(reply_order.REPLY_ORDER_REASONS)
        assert {r["route"] for r in rows} <= set(reply_order.REPLY_ROUTES)
        assert reply_order.CARRY_OVER_REASONS <= set(reply_order.REPLY_ORDER_REASONS)

    def test_an_exception_mid_cycle_still_writes_every_row(self, tmp_path):
        comments = [_comment("c1", "alpha", "Alice"), _comment("c2", "bravo", "Bob")]
        agent, client, scheduler, _ = _agent(
            tmp_path, comments, p_by_marker={"alpha": 0.5, "bravo": 0.9}
        )
        client.post_comment.side_effect = RuntimeError("not a client error")

        with pytest.raises(RuntimeError):
            agent._reply_handler.run_cycle_from_home(
                client, scheduler, time.time() + 3600, _home("p1")
            )

        rows = _by_comment(_rows(tmp_path / "logs"))
        assert {r["reason"] for r in rows.values()} == {"aborted_exception"}


class TestRecordCarriesNoText:
    def test_the_record_carries_no_body_title_or_name(self, tmp_path):
        """(v) Ids, numbers and closed codes only."""
        comments = [
            {
                "id": "c1",
                "content": "SECRET-COMMENT-TEXT about alpha",
                "author": {"name": "SecretAuthorName"},
            }
        ]
        agent, client, scheduler, _ = _agent(tmp_path, comments, p_by_marker={"alpha": 0.9})
        client.get_notifications.return_value = [
            {
                "type": "comment",
                "id": "n1",
                "post_id": "p2",
                "content": "SECRET-NOTIFICATION-TEXT about alpha",
                "post_content": "SECRET-POST-BODY",
                "title": "SECRET-TITLE",
                "agent_name": "OtherSecretName",
            }
        ]
        agent._ctx.own_post_ids = {"p1"}

        agent._reply_handler.run_cycle(client, scheduler, time.time() + 3600)

        rows = _rows(tmp_path / "logs")
        assert len(rows) == 2
        # session_id is stamped only inside a session; every other key is always there.
        assert all(ROW_KEYS - {"session_id"} <= set(r) <= ROW_KEYS for r in rows)
        raw = "".join(p.read_text() for p in (tmp_path / "logs").glob("reply-order-*.jsonl"))
        for secret in ("SECRET", "SecretAuthorName", "OtherSecretName"):
            assert secret not in raw

    def test_the_writer_is_off_unless_configured(self, tmp_path):
        comments = [_comment("c1", "alpha", "Alice")]
        agent, client, scheduler, _ = _agent(tmp_path, comments, p_by_marker={"alpha": 0.9})
        reply_order.reset_reply_order()

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        assert _parents(client) == ["c1"]
        assert _rows(tmp_path / "logs") == []


class TestRelevanceCacheUntouched:
    def test_a_feed_entry_under_the_same_id_and_text_does_not_answer_a_reply(self, tmp_path):
        """The reply read neither looks up nor writes the feed's cross-session cache."""
        text = "A short comment about alpha and nothing else."
        comments = [{"id": "c1", "content": text, "author": {"name": "Alice"}}]
        agent, client, scheduler, decision = _agent(tmp_path, comments, p_by_marker={"alpha": 0.9})
        cache_path = tmp_path / "relevance_cache.json"
        relevance_cache.configure_relevance_cache(cache_path)
        pin = relevance_cache.relevance_pin()
        assert pin is not None
        # A feed reading of a "post" that shares the comment's id and text, closed.
        assert relevance_cache.remember(
            "c1",
            relevance_cache.content_sha256(text),
            pin,
            {"decision_reason": "answered", "decision_p_top": 0.0},
        )
        before = cache_path.read_text(encoding="utf-8")

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        assert decision.asked == ["alpha"]
        assert _parents(client) == ["c1"]
        assert cache_path.read_text(encoding="utf-8") == before

    def test_the_relevance_row_names_the_reply_source(self, tmp_path):
        comments = [_comment("c1", "alpha", "Alice")]
        agent, client, scheduler, _ = _agent(tmp_path, comments, p_by_marker={"alpha": 0.9})

        agent._reply_handler.run_cycle_from_home(client, scheduler, time.time() + 3600, _home("p1"))

        rows = [
            json.loads(line)
            for path in (tmp_path / "logs").glob("relevance-*.jsonl")
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        assert [(r["source"], r["post_id"]) for r in rows] == [("reply", "c1")]


def test_census_registry_reads_the_reply_order_log():
    import sys

    from tests._shell_harness import REPO_ROOT

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import _census_registry as reg  # type: ignore[import-not-found]

    (entry,) = [e for e in reg.REGISTRY if e.glob == "reply-order-*.jsonl"]
    assert entry.status == reg.LIVE
    vocab = dict(entry.enum_values)
    assert set(vocab["reason"]) == set(reply_order.REPLY_ORDER_REASONS)
    assert set(vocab["route"]) == set(reply_order.REPLY_ROUTES)
    assert entry.matches("reply-order-2026-11-21.jsonl")
