# pyright: reportPrivateUsage=false
"""Relevance readings remembered across sessions (RFC-0046 S38).

The RFC-0032 memo lives one session. A post the gate dropped is never marked
commented, so it was scored again in every later session it stayed in the
feed: after enforce, 82 of 502 posts were scored in a median of 9 sessions
(max 21), and 6 of them flipped their gate verdict because the temperature-0
logprobs read does not reproduce bit-for-bit near the cut. The cache keys a
reading on post id + the sha256 of the text judged + a pin of the judge
(decision model, the score4 prompt, identity + axioms), stores the *value*
(the decision half), and leaves the threshold to be applied again in code.

Since RFC-0046 cleanup 2 (schema 2, pin version 2) the feed asks no
free-generated score, so an entry holds no live score and the pin names
neither the generation model nor ``relevance.md``.

Pinned here: a hit asks no model and writes no record row; the gate on a hit
is the cached value cut at today's threshold; a changed pin or a changed text
asks again; only ``answered`` readings are remembered; an unreadable store
warns and starts empty, a retired-schema store starts empty without a
warning; entries older than the TTL are dropped; nothing is written while the
cache is unconfigured; the session-end episode counts the hits.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from contemplative_agent.adapters.moltbook import relevance_cache as rc, relevance_shadow as rs
from contemplative_agent.adapters.moltbook.config import FEED_CONTENT_PREVIEW_LEN
from contemplative_agent.core import relevance_state
from contemplative_agent.core.llm import (
    DECISION_FACE_RELEVANCE,
    DecisionResult,
    QuestionAnswer,
    configure,
    reset_llm_config,
)
from tests.test_agent import _make_agent, _make_clean_memory

FM = "contemplative_agent.adapters.moltbook.feed_manager"
POST_TEXT = "x" * FEED_CONTENT_PREVIEW_LEN
ANSWERED = {"decision_reason": "answered", "decision_p_top": 0.25}


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setattr(f"{FM}.random.uniform", lambda a, b: 0.0)
    yield
    rc.reset_relevance_cache()
    rs.reset_relevance_shadow()
    reset_llm_config()


class _StubBackend:
    def __init__(self, p_top: float | None, model: str = "stub:1b"):
        self.p_top = p_top
        self._model = model
        self.calls = 0

    @property
    def model(self) -> str:
        return self._model

    def decide(self, state, questions, *, system=""):
        self.calls += 1
        question = relevance_state.score4_question()
        if self.p_top is None:
            answer = QuestionAnswer(
                id=question.id, probabilities=(), reason="http_error", observed=0
            )
            return DecisionResult(
                model=self._model, latency_ms=3, answers=(answer,), reason="http_error"
            )
        rest = (1.0 - self.p_top) / 3
        answer = QuestionAnswer(
            id=question.id,
            probabilities=tuple(zip(question.levels, (rest, rest, rest, self.p_top), strict=True)),
            reason="answered",
            observed=4,
        )
        return DecisionResult(model=self._model, latency_ms=7, answers=(answer,), reason="answered")


def _enforce(backend) -> None:
    configure(
        decision_backend=backend,
        decision_faces=frozenset({DECISION_FACE_RELEVANCE}),
        decision_enforce=frozenset({DECISION_FACE_RELEVANCE}),
    )


def _session(tmp_path, *, text=POST_TEXT, threshold_score4=0.3, memory=None):
    """One fresh agent (= one session): its own FeedManager and session memo.

    Re-pointing the cache at the same file drops what this process held in
    memory, so the next session reads the store back from disk, as a new
    launchd process would.
    """
    rc.configure_relevance_cache(tmp_path / "relevance_cache.json")
    agent, client, _ = _make_agent(tmp_path, content=MagicMock(), memory=memory)
    fm = agent._feed_manager
    fm._domain = dataclasses.replace(fm._domain, relevance_threshold_score4=threshold_score4)
    post = {"content": text, "id": "post1"}
    client.has_read_budget.return_value = True
    client.has_write_budget.return_value = True
    client.get_following_feed.return_value = []
    client.get_submolt_feed.return_value = [post]
    client.upvote_post.return_value = True
    client.get_post.return_value = {"id": "post1", "content": "full body " * 80}
    return agent, client


def _content(agent) -> MagicMock:
    return cast(MagicMock, agent._feed_manager._get_content())


def _comment_returns_nothing(agent) -> None:
    """A passed gate reaches create_comment; None keeps the post uncommented."""
    generated = MagicMock(text=None, thinking="", selection_id=None)
    _content(agent).create_comment.return_value = generated


def _cycle(agent) -> None:
    agent._run_feed_cycle(time.time() + 3600)


def _rows(logs: Path) -> list[dict]:
    return [
        json.loads(line)
        for path in sorted(logs.glob("relevance-*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


def _store(tmp_path) -> dict:
    return json.loads((tmp_path / "relevance_cache.json").read_text(encoding="utf-8"))


def _entry(at: datetime | None = None) -> dict:
    when = at or datetime.now(timezone.utc)
    return {
        "content_sha256": "a" * 64,
        "pin_sha256": "b" * 64,
        "decision": dict(ANSWERED),
        "judged_at": when.isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# Across sessions
# ---------------------------------------------------------------------------


class TestAcrossSessions:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_later_session_asks_no_model_and_writes_no_row(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        first = _StubBackend(0.25)
        _enforce(first)
        agent, _ = _session(tmp_path)
        _cycle(agent)
        assert first.calls == 1

        second = _StubBackend(0.9)
        _enforce(second)
        agent, _ = _session(tmp_path)
        _cycle(agent)
        _cycle(agent)
        assert second.calls == 0
        assert agent._feed_manager.relevance_cache_hits == 1
        # One row per fresh reading: the readiness clock and the would-be
        # gate rates count each post once, not once per session.
        assert len(_rows(tmp_path / "rlogs")) == 1

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_dropped_post_stays_dropped_when_a_rescore_would_pass(self, mock_note, tmp_path):
        """The flip RFC-0046 counted 6 times: 0.27 closed, later 0.34 passed."""
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _enforce(_StubBackend(0.27))
        agent, client = _session(tmp_path)
        _comment_returns_nothing(agent)
        _cycle(agent)
        assert _content(agent).create_comment.call_count == 0

        _enforce(_StubBackend(0.34))
        agent, client = _session(tmp_path)
        _comment_returns_nothing(agent)
        _cycle(agent)
        assert _content(agent).create_comment.call_count == 0
        client.post_comment.assert_not_called()
        client.upvote_post.assert_not_called()

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_the_threshold_is_applied_again_not_remembered(self, mock_note, tmp_path):
        _enforce(_StubBackend(0.25))
        agent, _ = _session(tmp_path, threshold_score4=0.3)
        _comment_returns_nothing(agent)
        _cycle(agent)
        assert _content(agent).create_comment.call_count == 0

        backend = _StubBackend(0.25)
        _enforce(backend)
        agent, _ = _session(tmp_path, threshold_score4=0.2)
        _comment_returns_nothing(agent)
        _cycle(agent)
        # Same remembered P(top) 0.25, today's cut 0.2: the gate opens.
        assert backend.calls == 0
        assert _content(agent).create_comment.call_count == 1

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_hit_is_logged_with_a_reason_code(self, mock_note, tmp_path, caplog):
        _enforce(_StubBackend(0.25))
        agent, _ = _session(tmp_path)
        _cycle(agent)
        agent, _ = _session(tmp_path)
        with caplog.at_level(logging.INFO):
            _cycle(agent)
        assert sum("relevance_cached" in r.getMessage() for r in caplog.records) == 1

    def test_an_unsettled_post_counts_one_hit_per_session_and_none_for_its_own(
        self, tmp_path, caplog
    ):
        """An empty note leaves a passed judgment unsettled, so it comes back every cycle."""
        backend = _StubBackend(0.75)
        _enforce(backend)
        with (
            patch(f"{FM}.generate_internal_note", return_value=""),
            caplog.at_level(logging.INFO),
        ):
            agent, _ = _session(tmp_path)
            _comment_returns_nothing(agent)
            for _ in range(3):
                _cycle(agent)
            # The retries reuse this session's own reading: no re-ask, no hit.
            assert backend.calls == 1
            assert agent._feed_manager.relevance_cache_hits == 0
            agent, _ = _session(tmp_path)
            _comment_returns_nothing(agent)
            for _ in range(3):
                _cycle(agent)
        assert backend.calls == 1
        assert agent._feed_manager.relevance_cache_hits == 1
        assert sum("relevance_cached" in r.getMessage() for r in caplog.records) == 1

    def test_the_session_end_episode_counts_the_hits(self, tmp_path):
        _enforce(_StubBackend(0.25))
        memory = _make_clean_memory(tmp_path)
        with patch(f"{FM}.generate_internal_note", return_value="noticed"):
            agent, _ = _session(tmp_path, memory=memory)
            _cycle(agent)
            agent, _ = _session(tmp_path, memory=memory)
            _cycle(agent)
        agent._log_session_end(duration_minutes=1)
        end = memory.episodes.read_range(days=1, record_type="session")[-1]
        assert end["data"]["feed_relevance_cache_hits"] == 1


# ---------------------------------------------------------------------------
# What invalidates
# ---------------------------------------------------------------------------


class TestInvalidation:
    def _judge_twice(self, tmp_path, between, *, text2=POST_TEXT):
        """Judge post1 in one session, change something, judge it in the next.

        *between* runs after the second agent is built: building an Agent
        re-applies the home's identity path and generation model. Returns how
        many times the decision backend was asked across both sessions.
        """
        backend = _StubBackend(0.25)
        _enforce(backend)
        with patch(f"{FM}.generate_internal_note", return_value="noticed"):
            agent, _ = _session(tmp_path)
            _cycle(agent)
            agent, _ = _session(tmp_path, text=text2)
            between()
            _cycle(agent)
        return backend.calls

    def test_a_changed_text_is_judged_again(self, tmp_path):
        assert self._judge_twice(tmp_path, lambda: None, text2="y" * 40) == 2

    def test_an_unchanged_text_is_not(self, tmp_path):
        assert self._judge_twice(tmp_path, lambda: None) == 1

    def test_a_changed_decision_model_is_judged_again(self, tmp_path):
        other = _StubBackend(0.25, "other:2b")
        assert self._judge_twice(tmp_path, lambda: _enforce(other)) == 1
        assert other.calls == 1

    def test_a_changed_identity_is_judged_again(self, tmp_path):
        identity = tmp_path / "identity-adopted.md"

        def adopt():
            identity.write_text("I am a newly adopted identity.\n", encoding="utf-8")
            configure(identity_path=identity)

        assert self._judge_twice(tmp_path, adopt) == 2

    def test_a_changed_score4_prompt_is_judged_again(self, tmp_path, monkeypatch):
        from contemplative_agent.core import prompts

        def edit():
            monkeypatch.setattr(
                prompts,
                "RELEVANCE_SCORE4_PROMPT",
                prompts.RELEVANCE_SCORE4_PROMPT + "\nAnswer with care.",
                raising=False,
            )

        assert self._judge_twice(tmp_path, edit) == 2

    def test_the_generation_model_is_no_longer_pinned(self, tmp_path):
        """Pin version 2: the feed asks no free-generated score, so the
        generation model no longer changes what a remembered reading means."""
        assert self._judge_twice(tmp_path, lambda: configure(ollama_model="other-gen:7b")) == 1

    def test_the_pin_names_neither_the_live_model_nor_relevance_md(self, tmp_path, monkeypatch):
        rc.configure_relevance_cache(tmp_path / "relevance_cache.json")
        captured: list[str] = []
        monkeypatch.setattr(rc, "_sha", lambda text: captured.append(text) or "0" * 64)
        rc.relevance_pin()
        (pin_json,) = [t for t in captured if t.startswith("{")]
        pin = json.loads(pin_json)
        assert pin["pin_version"] == rc.PIN_VERSION == 2
        assert "live_model" not in pin
        assert "relevance_prompt_sha256" not in pin


# ---------------------------------------------------------------------------
# What is remembered
# ---------------------------------------------------------------------------


class TestOnlyAnswersAreRemembered:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_an_unanswered_decision_is_not_remembered(self, mock_note, tmp_path):
        _enforce(_StubBackend(None))
        agent, _ = _session(tmp_path)
        _cycle(agent)
        backend = _StubBackend(0.25)
        _enforce(backend)
        agent, _ = _session(tmp_path)
        _cycle(agent)
        assert backend.calls == 1

    def test_an_unconfigured_decision_is_not_remembered(self, tmp_path):
        rc.configure_relevance_cache(tmp_path / "relevance_cache.json")
        stored = rc.remember("post1", "a" * 64, "b" * 64, {"decision_reason": "unconfigured"})
        assert stored is False
        assert not (tmp_path / "relevance_cache.json").exists()

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_the_store_holds_values_and_digests_not_text(self, mock_note, tmp_path):
        _enforce(_StubBackend(0.25))
        agent, _ = _session(tmp_path)
        _cycle(agent)
        store = _store(tmp_path)
        assert store["schema"] == rc.SCHEMA == 2
        entry = store["entries"]["post1"]
        assert "live_score" not in entry
        assert entry["decision"]["decision_p_top"] == pytest.approx(0.25)
        assert entry["decision"]["decision_reason"] == "answered"
        assert len(entry["content_sha256"]) == 64
        assert len(entry["pin_sha256"]) == 64
        # No threshold and no gate verdict: those are applied each time.
        assert not any("threshold" in key or "gate" in key for key in entry)
        assert POST_TEXT not in json.dumps(store)

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_the_key_digest_matches_the_record_rows(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _enforce(_StubBackend(0.25))
        agent, _ = _session(tmp_path)
        _cycle(agent)
        (row,) = _rows(tmp_path / "rlogs")
        assert _store(tmp_path)["entries"]["post1"]["content_sha256"] == row["content_sha256"]


# ---------------------------------------------------------------------------
# The store
# ---------------------------------------------------------------------------


class TestStore:
    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_an_unreadable_store_warns_and_starts_empty(self, mock_note, tmp_path, caplog):
        (tmp_path / "relevance_cache.json").write_text("{not json", encoding="utf-8")
        backend = _StubBackend(0.25)
        _enforce(backend)
        with caplog.at_level(logging.WARNING):
            agent, _ = _session(tmp_path)
            _cycle(agent)
        assert backend.calls == 1
        assert any("relevance cache" in r.getMessage() for r in caplog.records)
        # The next write replaces the broken file with a readable one.
        assert "post1" in _store(tmp_path)["entries"]

    def test_a_retired_schema_starts_empty_without_a_warning(self, tmp_path, caplog):
        legacy = {**_entry(), "live_score": 0.5}
        store = {"schema": 1, "entries": {"post1": legacy}}
        (tmp_path / "relevance_cache.json").write_text(json.dumps(store), encoding="utf-8")
        rc.configure_relevance_cache(tmp_path / "relevance_cache.json")
        with caplog.at_level(logging.INFO):
            assert rc.lookup("post1", "a" * 64, "b" * 64) is None
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any("retired" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize(
        "raw",
        ['{"schema": 2, "entries": {}, "n": ' + "9" * 5000 + "}", "[" * 100000 + "]" * 100000],
        ids=["integer_too_long", "too_deep"],
    )
    def test_a_parse_error_beyond_json_syntax_warns_and_starts_empty(self, tmp_path, caplog, raw):
        (tmp_path / "relevance_cache.json").write_text(raw, encoding="utf-8")
        rc.configure_relevance_cache(tmp_path / "relevance_cache.json")
        with caplog.at_level(logging.WARNING):
            assert rc.lookup("post1", "0" * 64, "1" * 64) is None
        assert any("relevance cache" in r.getMessage() for r in caplog.records)

    def test_a_wrong_shape_warns_and_starts_empty(self, tmp_path, caplog):
        (tmp_path / "relevance_cache.json").write_text("[1, 2]", encoding="utf-8")
        rc.configure_relevance_cache(tmp_path / "relevance_cache.json")
        with caplog.at_level(logging.WARNING):
            assert rc.lookup("post1", "0" * 64, "1" * 64) is None
        assert any("relevance cache" in r.getMessage() for r in caplog.records)

    def test_a_malformed_entry_is_dropped_with_a_warning(self, tmp_path, caplog):
        store = {"schema": rc.SCHEMA, "entries": {"good": _entry(), "bad": {"decision": "high"}}}
        (tmp_path / "relevance_cache.json").write_text(json.dumps(store), encoding="utf-8")
        rc.configure_relevance_cache(tmp_path / "relevance_cache.json")
        with caplog.at_level(logging.WARNING):
            hit = rc.lookup("good", "a" * 64, "b" * 64)
            assert rc.lookup("bad", "a" * 64, "b" * 64) is None
        assert hit is not None and hit.decision["decision_p_top"] == 0.25
        assert any("malformed" in r.getMessage() for r in caplog.records)

    def test_entries_older_than_the_ttl_are_dropped(self, tmp_path):
        old = datetime.now(timezone.utc) - timedelta(days=rc.TTL_DAYS + 1)
        fresh = datetime.now(timezone.utc) - timedelta(days=rc.TTL_DAYS - 1)
        store = {"schema": rc.SCHEMA, "entries": {"old": _entry(old), "fresh": _entry(fresh)}}
        (tmp_path / "relevance_cache.json").write_text(json.dumps(store), encoding="utf-8")
        rc.configure_relevance_cache(tmp_path / "relevance_cache.json")
        assert rc.lookup("old", "a" * 64, "b" * 64) is None
        assert rc.lookup("fresh", "a" * 64, "b" * 64) is not None
        rc.remember("new", "c" * 64, "b" * 64, ANSWERED)
        assert set(_store(tmp_path)["entries"]) == {"fresh", "new"}

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_unconfigured_writes_nothing_and_judges_every_session(self, mock_note, tmp_path):
        backend = _StubBackend(0.25)
        _enforce(backend)
        for _ in range(2):
            agent, _ = _session_unconfigured(tmp_path)
            _cycle(agent)
        assert backend.calls == 2
        assert not (tmp_path / "relevance_cache.json").exists()

    def test_a_store_failure_warns_and_keeps_the_judgment(self, tmp_path, caplog, monkeypatch):
        rc.configure_relevance_cache(tmp_path / "relevance_cache.json")

        def boom(path, content):
            raise OSError("disk full")

        monkeypatch.setattr(rc, "write_text_atomic", boom)
        with caplog.at_level(logging.WARNING):
            stored = rc.remember("post1", "a" * 64, "b" * 64, ANSWERED)
        assert stored is False
        assert any("relevance cache" in r.getMessage() for r in caplog.records)


def _session_unconfigured(tmp_path):
    agent, client, _ = _make_agent(tmp_path, content=MagicMock())
    fm = agent._feed_manager
    fm._domain = dataclasses.replace(fm._domain, relevance_threshold_score4=0.3)
    client.has_read_budget.return_value = True
    client.has_write_budget.return_value = True
    client.get_following_feed.return_value = []
    client.get_submolt_feed.return_value = [{"content": POST_TEXT, "id": "post1"}]
    client.upvote_post.return_value = True
    client.get_post.return_value = {"id": "post1", "content": "full body " * 80}
    return agent, client


def test_the_cli_points_the_cache_at_the_home_store():
    import argparse

    from contemplative_agent.adapters.moltbook import config
    from contemplative_agent.cli import runtime

    runtime._configure_llm_and_domain(
        argparse.Namespace(domain_config=None, no_axioms=True, constitution_dir=None)
    )
    assert rc._path == config.RELEVANCE_CACHE_PATH
    assert config.RELEVANCE_CACHE_PATH.parent == config.MOLTBOOK_DATA_DIR


def test_the_public_data_sync_excludes_the_store():
    script = Path(__file__).resolve().parents[1] / "scripts" / "sync-research-data.sh"
    assert "--exclude='relevance_cache.json'" in script.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Seed selection asks the same gate, and only reads the cache (ADR-0113 amendment 2)
# ---------------------------------------------------------------------------


class TestSeedSelectionSharesTheGate:
    """Self-post seed selection reads through ``feed_manager.read_relevance_gate``.

    Pinned: a seed read is the same score4 question, cut at the feed's
    ``relevance_score4``; its row says ``source: "seed"`` (a feed row says
    ``"feed"``); seed selection reads the cache but never writes it — the
    feed is the store's single writer, so feed and seed judging different
    text for one post never overwrite each other's entry, and a seed read
    never turns a later feed sight into a cache hit; within a session seed
    selection keeps its own memo; a post the gate cannot answer for is never
    seeded.
    """

    def _seed(self, agent, post: dict) -> bool:
        from contemplative_agent.adapters.moltbook import post_pipeline

        threshold = agent._feed_manager._domain.relevance_threshold_score4
        return post_pipeline._seed_gate(post, threshold).outcome.enforce_gate is True

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_seed_read_writes_a_seed_row_and_no_cache_entry(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(0.9)
        _enforce(backend)
        agent, _ = _session(tmp_path)
        _comment_returns_nothing(agent)

        assert self._seed(agent, {"content": POST_TEXT, "id": "post1"})
        assert not (tmp_path / "relevance_cache.json").exists()

        # The feed's own sight of the same text is a fresh read, not a hit.
        _cycle(agent)
        assert backend.calls == 2
        assert agent._feed_manager.relevance_cache_hits == 0
        assert [row["source"] for row in _rows(tmp_path / "rlogs")] == ["seed", "feed"]

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_seed_read_never_makes_a_later_feed_session_a_hit(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _enforce(_StubBackend(0.9))
        agent, _ = _session(tmp_path)
        assert self._seed(agent, {"content": POST_TEXT, "id": "post1"})

        feed_backend = _StubBackend(0.9)
        _enforce(feed_backend)
        agent, _ = _session(tmp_path)
        _comment_returns_nothing(agent)
        _cycle(agent)
        assert feed_backend.calls == 1
        assert agent._feed_manager.relevance_cache_hits == 0

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_feed_and_seed_texts_for_one_post_do_not_overwrite(self, mock_note, tmp_path):
        """The feed may judge a fuller body than the seed's 500-char preview."""
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(0.25)
        _enforce(backend)
        agent, _ = _session(tmp_path)
        _cycle(agent)
        entry = _store(tmp_path)["entries"]["post1"]

        assert not self._seed(agent, {"content": "a shorter preview", "id": "post1"})
        assert backend.calls == 2
        assert _store(tmp_path)["entries"]["post1"] == entry

        # The next session's feed sight is still the feed's own cache hit.
        _enforce(_StubBackend(0.9))
        agent, _ = _session(tmp_path)
        _cycle(agent)
        assert agent._feed_manager.relevance_cache_hits == 1

    @patch(f"{FM}.generate_internal_note", return_value="noticed")
    def test_a_feed_reading_is_reused_by_seed_selection(self, mock_note, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(0.25)
        _enforce(backend)
        agent, _ = _session(tmp_path)
        _cycle(agent)
        assert backend.calls == 1

        # 0.25 is under the feed's 0.3: not a seed either, and not asked again.
        assert not self._seed(agent, {"content": POST_TEXT, "id": "post1"})
        assert backend.calls == 1
        assert [row["source"] for row in _rows(tmp_path / "rlogs")] == ["feed"]

    def test_seed_selection_asks_a_post_once_per_session(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        backend = _StubBackend(0.1)
        _enforce(backend)
        agent, _ = _session(tmp_path)
        pipeline = agent._post_pipeline
        pipeline._domain = dataclasses.replace(pipeline._domain, relevance_threshold_score4=0.3)
        subs = pipeline._domain.subscribed_submolts
        posts = [{"content": "a peer post", "id": "seedpost", "submolt_name": subs[0]}]

        assert pipeline._select_and_log_seeds(posts) == []
        assert pipeline._select_and_log_seeds(posts) == []
        assert backend.calls == 1

    def test_no_answer_is_never_a_seed(self, tmp_path):
        rs.configure_relevance_shadow(audit_dir=tmp_path / "rlogs")
        _enforce(_StubBackend(None))
        agent, _ = _session(tmp_path)

        assert not self._seed(agent, {"content": POST_TEXT, "id": "post1"})
        (row,) = _rows(tmp_path / "rlogs")
        assert row["source"] == "seed"
        assert row["gate_source"] == "fail_closed"

    def test_post_level_failures_are_counted_in_the_empty_verdict(self, tmp_path, caplog):
        """No answer for a post's own text is not "judged irrelevant"."""
        agent, _ = _session(tmp_path)
        pipeline = agent._post_pipeline
        subs = pipeline._domain.subscribed_submolts
        posts = [
            {"content": f"peer post {i}", "id": f"p{i}", "submolt_name": subs[0]} for i in range(3)
        ]
        failed = rs.RecordedReading(
            rs.EnforceOutcome("fail_closed", None, "enforce_backend_null", 0.3),
            {"decision_reason": "no_option_observed"},
        )
        with (
            patch(
                "contemplative_agent.adapters.moltbook.post_pipeline._seed_gate",
                return_value=failed,
            ),
            caplog.at_level(logging.INFO),
        ):
            assert pipeline._select_and_log_seeds(posts) == []
        assert "candidates=3, 3 with no answer for their text" in caplog.text

    def test_a_non_string_body_is_dropped_not_raised(self, tmp_path):
        agent, _ = _session(tmp_path)
        pipeline = agent._post_pipeline
        subs = pipeline._domain.subscribed_submolts
        posts = [{"content": {"not": "text"}, "id": "odd", "submolt_name": subs[0]}]
        assert pipeline._seed_candidates(posts) == []
