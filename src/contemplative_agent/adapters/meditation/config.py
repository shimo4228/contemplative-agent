"""Meditation adapter configuration — state space definitions and parameters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# --- POMDP State Space (intentionally coarse) ---
# Actions: what the agent did (maps to Episode Log record types)
ACTION_STATES: Tuple[str, ...] = (
    "idle",        # No meaningful action (session start/end, follow/unfollow)
    "read_feed",   # Consumed content (upvote without comment)
    "comment",     # Responded to another agent's post
    "reply",       # Replied to a notification
    "post",        # Created original content
    "reflect",     # Session insight / distill
)

# Outcomes: what happened after the action (derived from subsequent records)
OUTCOME_STATES: Tuple[str, ...] = (
    "no_response",      # No engagement received within window
    "low_engagement",   # Few interactions back (1-2)
    "high_engagement",  # Active conversation (3+)
    "new_connection",   # Interaction with previously unknown agent
)

# Contexts: hidden state representing session phase
CONTEXT_STATES: Tuple[str, ...] = (
    "early_session",     # First third of session
    "mid_session",       # Middle third
    "late_session",      # Final third
    "between_sessions",  # Non-active time
)

# Include "no_input" as an extra observation for meditation (uniform likelihood)
OBSERVATION_STATES: Tuple[str, ...] = OUTCOME_STATES + ("no_input",)

NUM_ACTIONS = len(ACTION_STATES)
NUM_OBSERVATIONS = len(OBSERVATION_STATES)
NUM_CONTEXTS = len(CONTEXT_STATES)


@dataclass(frozen=True)
class MeditationConfig:
    """Parameters controlling the meditation simulation."""

    meditation_cycles: int = 50
    temporal_decay: float = 0.95  # Flattening factor per cycle
    counterfactual_threshold: float = 0.1  # Prune policies below this
    max_cycles: int = 200  # Hard cap (iteration bound)
    convergence_epsilon: float = 0.001  # Early stop threshold
    response_window_seconds: float = 300.0  # 5 min window for outcome classification


DEFAULT_CONFIG = MeditationConfig()
