"""Tests for meditation adapter — POMDP classification and matrix construction."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from contemplative_agent.adapters.meditation.config import (
    NUM_ACTIONS,
    NUM_CONTEXTS,
    NUM_OBSERVATIONS,
    OBSERVATION_STATES,
    OUTCOME_STATES,
)
from contemplative_agent.adapters.meditation.pomdp import (
    build_matrices,
    classify_action,
    classify_context,
    classify_outcome,
)
from contemplative_agent.core.episode_log import EpisodeLog


# --- classify_action tests ---


class TestClassifyAction:
    def test_activity_upvote(self):
        record = {"type": "activity", "data": {"action": "upvote"}}
        assert classify_action(record) == "read_feed"

    def test_activity_comment(self):
        record = {"type": "activity", "data": {"action": "comment"}}
        assert classify_action(record) == "comment"

    def test_activity_reply(self):
        record = {"type": "activity", "data": {"action": "reply"}}
        assert classify_action(record) == "reply"

    def test_activity_post(self):
        record = {"type": "activity", "data": {"action": "post"}}
        assert classify_action(record) == "post"

    def test_activity_follow(self):
        record = {"type": "activity", "data": {"action": "follow"}}
        assert classify_action(record) == "idle"

    def test_activity_unfollow(self):
        record = {"type": "activity", "data": {"action": "unfollow"}}
        assert classify_action(record) == "idle"

    def test_insight(self):
        record = {"type": "insight", "data": {"observation": "test"}}
        assert classify_action(record) == "reflect"

    def test_interaction_sent(self):
        record = {"type": "interaction", "data": {"direction": "sent"}}
        assert classify_action(record) == "comment"

    def test_interaction_received(self):
        record = {"type": "interaction", "data": {"direction": "received"}}
        assert classify_action(record) == "idle"

    def test_post_record(self):
        record = {"type": "post", "data": {"title": "test"}}
        assert classify_action(record) == "post"

    def test_session_record(self):
        record = {"type": "session", "data": {"event": "start"}}
        assert classify_action(record) == "idle"

    def test_unknown_type(self):
        record = {"type": "unknown", "data": {}}
        assert classify_action(record) == "idle"

    def test_empty_record(self):
        assert classify_action({}) == "idle"


# --- classify_outcome tests ---


def _ts(offset_seconds: float = 0) -> str:
    """Generate ISO timestamp with offset from now."""
    dt = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc) + timedelta(
        seconds=offset_seconds
    )
    return dt.isoformat()


class TestClassifyOutcome:
    def test_no_subsequent_records(self):
        record = {"ts": _ts(0)}
        assert classify_outcome(record, []) == "no_response"

    def test_no_response_within_window(self):
        record = {"ts": _ts(0)}
        # Response after window (600s > 300s default)
        subsequent = [
            {
                "ts": _ts(600),
                "type": "interaction",
                "data": {"direction": "received"},
            }
        ]
        assert classify_outcome(record, subsequent) == "no_response"

    def test_low_engagement(self):
        record = {"ts": _ts(0)}
        subsequent = [
            {
                "ts": _ts(60),
                "type": "interaction",
                "data": {"direction": "received", "agent_id": "a1"},
            }
        ]
        assert classify_outcome(record, subsequent) == "low_engagement"

    def test_high_engagement(self):
        record = {"ts": _ts(0)}
        subsequent = [
            {
                "ts": _ts(30),
                "type": "interaction",
                "data": {"direction": "received", "agent_id": "a1"},
            },
            {
                "ts": _ts(60),
                "type": "interaction",
                "data": {"direction": "received", "agent_id": "a2"},
            },
            {
                "ts": _ts(90),
                "type": "interaction",
                "data": {"direction": "received", "agent_id": "a1"},
            },
        ]
        assert classify_outcome(record, subsequent) == "high_engagement"

    def test_new_connection(self):
        record = {"ts": _ts(0)}
        subsequent = [
            {
                "ts": _ts(60),
                "type": "interaction",
                "data": {"direction": "received", "agent_id": "new-agent"},
            }
        ]
        known = {"existing-agent"}
        assert (
            classify_outcome(record, subsequent, known_agents=known) == "new_connection"
        )

    def test_known_agent_not_new_connection(self):
        record = {"ts": _ts(0)}
        subsequent = [
            {
                "ts": _ts(60),
                "type": "interaction",
                "data": {"direction": "received", "agent_id": "known-agent"},
            }
        ]
        known = {"known-agent"}
        assert (
            classify_outcome(record, subsequent, known_agents=known) == "low_engagement"
        )

    def test_sent_interactions_not_counted(self):
        """Only received interactions count as responses."""
        record = {"ts": _ts(0)}
        subsequent = [
            {
                "ts": _ts(60),
                "type": "interaction",
                "data": {"direction": "sent", "agent_id": "a1"},
            }
        ]
        assert classify_outcome(record, subsequent) == "no_response"

    def test_invalid_timestamp(self):
        record = {"ts": "invalid"}
        assert classify_outcome(record, []) == "no_response"


# --- classify_context tests ---


class TestClassifyContext:
    def test_no_session_boundaries(self):
        record = {"ts": _ts(0)}
        assert classify_context(record) == "between_sessions"

    def test_early_session(self):
        start = _ts(0)
        end = _ts(3600)  # 1 hour session
        record = {"ts": _ts(600)}  # 10 min in (< 1/3)
        assert classify_context(record, start, end) == "early_session"

    def test_mid_session(self):
        start = _ts(0)
        end = _ts(3600)
        record = {"ts": _ts(1800)}  # 30 min in (= 1/2)
        assert classify_context(record, start, end) == "mid_session"

    def test_late_session(self):
        start = _ts(0)
        end = _ts(3600)
        record = {"ts": _ts(3000)}  # 50 min in (> 2/3)
        assert classify_context(record, start, end) == "late_session"

    def test_before_session(self):
        start = _ts(100)
        end = _ts(3600)
        record = {"ts": _ts(0)}
        assert classify_context(record, start, end) == "between_sessions"

    def test_after_session(self):
        start = _ts(0)
        end = _ts(3600)
        record = {"ts": _ts(4000)}
        assert classify_context(record, start, end) == "between_sessions"

    def test_invalid_timestamp(self):
        record = {"ts": "invalid"}
        assert classify_context(record, _ts(0), _ts(3600)) == "between_sessions"


# --- build_matrices tests ---


def _make_log(tmp_path: Path, records: List[Dict[str, Any]]) -> EpisodeLog:
    """Create an EpisodeLog with pre-written records."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = log_dir / f"{date_str}.jsonl"
    with log_file.open("w") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return EpisodeLog(log_dir=log_dir)


class TestBuildMatrices:
    def test_empty_log(self, tmp_path):
        log = _make_log(tmp_path, [])
        matrices = build_matrices(log, days=1)

        # Should return valid probability distributions (from Dirichlet prior)
        assert matrices.A.shape == (NUM_OBSERVATIONS, NUM_CONTEXTS)
        assert matrices.B.shape == (NUM_CONTEXTS, NUM_CONTEXTS, NUM_ACTIONS)
        assert matrices.C.shape == (NUM_OBSERVATIONS,)
        assert matrices.D.shape == (NUM_CONTEXTS,)

        # A columns should sum to 1
        np.testing.assert_allclose(matrices.A.sum(axis=0), 1.0, atol=1e-10)
        # B slices should sum to 1
        for a in range(NUM_ACTIONS):
            np.testing.assert_allclose(
                matrices.B[:, :, a].sum(axis=0), 1.0, atol=1e-10
            )
        # D should sum to 1
        np.testing.assert_allclose(matrices.D.sum(), 1.0, atol=1e-10)

    def test_basic_records(self, tmp_path):
        base = _ts(0)
        records = [
            {"ts": base, "type": "session", "data": {"event": "start"}},
            {
                "ts": _ts(60),
                "type": "activity",
                "data": {"action": "comment", "post_id": "p1"},
            },
            {
                "ts": _ts(90),
                "type": "interaction",
                "data": {"direction": "received", "agent_id": "a1", "agent_name": "A1"},
            },
            {
                "ts": _ts(300),
                "type": "activity",
                "data": {"action": "upvote", "post_id": "p2"},
            },
            {"ts": _ts(3600), "type": "session", "data": {"event": "end"}},
        ]
        log = _make_log(tmp_path, records)
        matrices = build_matrices(log, days=1)

        # Verify shapes
        assert matrices.A.shape == (NUM_OBSERVATIONS, NUM_CONTEXTS)
        assert matrices.B.shape == (NUM_CONTEXTS, NUM_CONTEXTS, NUM_ACTIONS)

        # All distributions should be valid
        np.testing.assert_allclose(matrices.A.sum(axis=0), 1.0, atol=1e-10)
        np.testing.assert_allclose(matrices.D.sum(), 1.0, atol=1e-10)

    def test_preferences(self, tmp_path):
        log = _make_log(tmp_path, [])
        matrices = build_matrices(log, days=1)

        # high_engagement should have highest preference
        outcome_idx = {o: i for i, o in enumerate(OUTCOME_STATES)}
        assert matrices.C[outcome_idx["high_engagement"]] == 1.0
        assert matrices.C[outcome_idx["new_connection"]] == 0.5
        assert matrices.C[outcome_idx["no_response"]] == 0.0

    def test_no_input_observation_exists(self, tmp_path):
        """The 'no_input' observation should be in the observation space."""
        assert "no_input" in OBSERVATION_STATES
        # A matrix should have a row for no_input
        log = _make_log(tmp_path, [])
        matrices = build_matrices(log, days=1)
        no_input_idx = OBSERVATION_STATES.index("no_input")
        # Should be uniform (from Dirichlet prior only, no data)
        row = matrices.A[no_input_idx, :]
        assert row.shape == (NUM_CONTEXTS,)
