"""Episode Log → POMDP matrix construction for meditation simulation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ...core.episode_log import EpisodeLog
from .config import (
    ACTION_STATES,
    CONTEXT_STATES,
    DEFAULT_CONFIG,
    MeditationConfig,
    NUM_ACTIONS,
    NUM_CONTEXTS,
    NUM_OBSERVATIONS,
    OUTCOME_STATES,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class POMDPMatrices:
    """POMDP model matrices.

    A: likelihood (num_observations x num_contexts) — P(observation | context)
    B: transition (num_contexts x num_contexts x num_actions) — P(next | current, action)
    C: preference (num_observations,) — desired observation distribution
    D: prior (num_contexts,) — initial belief over contexts
    """

    A: np.ndarray
    B: np.ndarray
    C: np.ndarray
    D: np.ndarray


def classify_action(record: Dict[str, Any]) -> str:
    """Map an episode record to an action state.

    Mapping:
        activity:upvote → read_feed
        activity:comment → comment
        activity:reply → reply
        activity:post → post
        insight → reflect
        interaction (received) → idle (passive receipt)
        interaction (sent) → comment (active engagement)
        session, activity:follow/unfollow → idle
    """
    record_type = record.get("type", "")
    data = record.get("data", {})

    if record_type == "activity":
        action = data.get("action", "")
        if action == "upvote":
            return "read_feed"
        if action == "comment":
            return "comment"
        if action == "reply":
            return "reply"
        if action == "post":
            return "post"
        # follow, unfollow, etc.
        return "idle"

    if record_type == "insight":
        return "reflect"

    if record_type == "interaction":
        direction = data.get("direction", "")
        if direction == "sent":
            return "comment"
        return "idle"

    if record_type == "post":
        return "post"

    # session, unknown types
    return "idle"


def classify_outcome(
    record: Dict[str, Any],
    subsequent: List[Dict[str, Any]],
    known_agents: Optional[set] = None,
    config: MeditationConfig = DEFAULT_CONFIG,
) -> str:
    """Map a record + subsequent responses to an outcome state.

    Looks at records within response_window_seconds after this record.
    Counts received interactions as responses.
    """
    ts_str = record.get("ts", "")
    try:
        ts = datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return "no_response"

    cutoff = ts.timestamp() + config.response_window_seconds
    responses = []
    new_agent = False

    for sub in subsequent:
        sub_ts_str = sub.get("ts", "")
        try:
            sub_ts = datetime.fromisoformat(sub_ts_str)
        except (ValueError, TypeError):
            continue
        if sub_ts.timestamp() > cutoff:
            break

        sub_type = sub.get("type", "")
        sub_data = sub.get("data", {})

        # Count received interactions as responses
        if sub_type == "interaction" and sub_data.get("direction") == "received":
            responses.append(sub)
            if known_agents is not None:
                agent_id = sub_data.get("agent_id", "")
                if agent_id and agent_id not in known_agents:
                    new_agent = True

    if new_agent:
        return "new_connection"
    if len(responses) >= 3:
        return "high_engagement"
    if len(responses) >= 1:
        return "low_engagement"
    return "no_response"


def classify_context(
    record: Dict[str, Any],
    session_start: Optional[str] = None,
    session_end: Optional[str] = None,
) -> str:
    """Map a record's timestamp to a session phase.

    If session boundaries are unknown, returns 'between_sessions'.
    """
    if session_start is None or session_end is None:
        return "between_sessions"

    try:
        ts = datetime.fromisoformat(record.get("ts", ""))
        start = datetime.fromisoformat(session_start)
        end = datetime.fromisoformat(session_end)
    except (ValueError, TypeError):
        return "between_sessions"

    if ts < start or ts > end:
        return "between_sessions"

    total = (end - start).total_seconds()
    if total <= 0:
        return "mid_session"

    elapsed = (ts - start).total_seconds()
    ratio = elapsed / total

    if ratio < 1 / 3:
        return "early_session"
    if ratio < 2 / 3:
        return "mid_session"
    return "late_session"


def _find_sessions(records: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    """Extract (start_ts, end_ts) pairs from session records."""
    sessions: List[Tuple[str, str]] = []
    pending_start: Optional[str] = None

    for r in records:
        if r.get("type") != "session":
            continue
        event = r.get("data", {}).get("event", "")
        if event == "start":
            pending_start = r.get("ts", "")
        elif event == "end" and pending_start is not None:
            sessions.append((pending_start, r.get("ts", "")))
            pending_start = None

    # If session started but never ended, use last record as end
    if pending_start is not None and records:
        sessions.append((pending_start, records[-1].get("ts", "")))

    return sessions


def _find_session_for_record(
    record: Dict[str, Any],
    sessions: List[Tuple[str, str]],
) -> Tuple[Optional[str], Optional[str]]:
    """Find which session a record belongs to."""
    ts_str = record.get("ts", "")
    try:
        ts = datetime.fromisoformat(ts_str)
    except (ValueError, TypeError):
        return None, None

    for start_str, end_str in sessions:
        try:
            start = datetime.fromisoformat(start_str)
            end = datetime.fromisoformat(end_str)
        except (ValueError, TypeError):
            continue
        if start <= ts <= end:
            return start_str, end_str

    return None, None


def build_matrices(
    episode_log: EpisodeLog,
    days: int = 7,
    config: MeditationConfig = DEFAULT_CONFIG,
) -> POMDPMatrices:
    """Build POMDP matrices from episode log data.

    Counts co-occurrences of (action, outcome, context) triples,
    normalizes to probability distributions, and adds Dirichlet
    smoothing to avoid zero probabilities.
    """
    records = episode_log.read_range(days=days)
    records.sort(key=lambda r: r.get("ts", ""))

    sessions = _find_sessions(records)

    # Collect known agent IDs for new_connection detection
    known_agents: set = set()
    for r in records:
        if r.get("type") == "interaction":
            agent_id = r.get("data", {}).get("agent_id", "")
            if agent_id:
                known_agents.add(agent_id)

    # Count co-occurrences
    # A: observation counts per context — (num_obs x num_ctx)
    a_counts = np.ones((NUM_OBSERVATIONS, NUM_CONTEXTS), dtype=np.float64)  # Dirichlet prior
    # B: transition counts — (num_ctx x num_ctx x num_actions)
    b_counts = np.ones((NUM_CONTEXTS, NUM_CONTEXTS, NUM_ACTIONS), dtype=np.float64)
    # D: context frequency
    d_counts = np.ones(NUM_CONTEXTS, dtype=np.float64)

    action_idx = {a: i for i, a in enumerate(ACTION_STATES)}
    outcome_idx = {o: i for i, o in enumerate(OUTCOME_STATES)}
    context_idx = {c: i for i, c in enumerate(CONTEXT_STATES)}

    prev_ctx_i: Optional[int] = None

    for i, record in enumerate(records):
        # Skip session records themselves
        if record.get("type") == "session":
            continue

        action = classify_action(record)
        subsequent = records[i + 1:]
        outcome = classify_outcome(
            record, subsequent, known_agents=known_agents, config=config,
        )
        session_start, session_end = _find_session_for_record(record, sessions)
        context = classify_context(record, session_start, session_end)

        act_i = action_idx.get(action, 0)
        out_i = outcome_idx.get(outcome, 0)
        ctx_i = context_idx.get(context, 0)

        a_counts[out_i, ctx_i] += 1
        d_counts[ctx_i] += 1

        if prev_ctx_i is not None:
            b_counts[ctx_i, prev_ctx_i, act_i] += 1

        prev_ctx_i = ctx_i

    # Normalize columns/slices to probability distributions
    A = a_counts / a_counts.sum(axis=0, keepdims=True)
    B = b_counts / b_counts.sum(axis=0, keepdims=True)
    D = d_counts / d_counts.sum()

    # C: preference — favor high_engagement and new_connection
    C = np.zeros(NUM_OBSERVATIONS, dtype=np.float64)
    C[outcome_idx["high_engagement"]] = 1.0
    C[outcome_idx["new_connection"]] = 0.5
    C[outcome_idx["low_engagement"]] = 0.2
    # no_response = 0, no_input = 0

    return POMDPMatrices(A=A, B=B, C=C, D=D)
