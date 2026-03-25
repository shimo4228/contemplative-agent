"""Moltbook platform-specific constants.

URLs, paths, timeouts, and rate limits specific to the Moltbook deployment.
"""

import os
from dataclasses import dataclass
from pathlib import Path

# --- API ---
BASE_URL = "https://www.moltbook.com/api/v1"
ALLOWED_DOMAIN = "www.moltbook.com"

# --- Data paths ---
MOLTBOOK_DATA_DIR = Path(
    os.environ.get("MOLTBOOK_HOME", str(Path.home() / ".config" / "moltbook"))
)
CREDENTIALS_PATH = MOLTBOOK_DATA_DIR / "credentials.json"
RATE_STATE_PATH = MOLTBOOK_DATA_DIR / "rate_state.json"
EPISODE_LOG_DIR = MOLTBOOK_DATA_DIR / "logs"

COMMENTED_CACHE_PATH = MOLTBOOK_DATA_DIR / "commented_cache.json"

# --- Runtime data (lives in MOLTBOOK_HOME, user-specific) ---
IDENTITY_PATH = MOLTBOOK_DATA_DIR / "identity.md"
KNOWLEDGE_PATH = MOLTBOOK_DATA_DIR / "knowledge.json"
AGENTS_PATH = MOLTBOOK_DATA_DIR / "agents.json"
SKILLS_DIR = MOLTBOOK_DATA_DIR / "skills"
RULES_DIR = MOLTBOOK_DATA_DIR / "rules"
CONSTITUTION_DIR = MOLTBOOK_DATA_DIR / "constitution"
HISTORY_DIR = MOLTBOOK_DATA_DIR / "history"
MEDITATION_DIR = MOLTBOOK_DATA_DIR / "meditation"
REPORTS_DIR = MOLTBOOK_DATA_DIR / "reports" / "comment-reports"
EPISODE_RETENTION_DAYS = 30

# --- Agent pacing ---
COMMENT_PACING_MIN_SECONDS = 60
COMMENT_PACING_MAX_SECONDS = 180

# --- Ollama LLM ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3.5:9b"

# --- HTTP client ---
MAX_VERIFICATION_FAILURES = 7
MAX_RETRY_ON_429 = 3
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60


# --- Rate limits ---
@dataclass(frozen=True)
class RateLimits:
    """Rate limits for Moltbook API actions."""

    post_interval_seconds: int = 1800  # 1 per 30 min
    comment_interval_seconds: int = 20
    comments_per_day: int = 300


@dataclass(frozen=True)
class NewAgentRateLimits:
    """Stricter rate limits for agents less than 24h old."""

    post_interval_seconds: int = 7200  # 1 per 2h
    comment_interval_seconds: int = 60
    comments_per_day: int = 50


RATE_LIMITS = RateLimits()
NEW_AGENT_RATE_LIMITS = NewAgentRateLimits()


@dataclass(frozen=True)
class AdaptiveBackoffConfig:
    """Adaptive backoff parameters for API rate limit management.

    The API uses separate quotas: GET 60 req/min, POST 30 req/min.
    One cycle consumes ~3-5 requests with /home-based approach.
    """

    base_cycle_wait: float = 60.0         # Normal cycle interval (seconds)
    max_cycle_wait: float = 600.0         # Maximum backoff (10 minutes)
    backoff_multiplier: float = 2.0       # Exponential backoff multiplier
    decay_factor: float = 0.5             # Shrink factor on clean cycle
    remaining_threshold: int = 10         # Start slowing when <= 10 remaining
    read_budget_reserve: int = 5          # In-cycle: stop GET when <= 5 remaining
    write_budget_reserve: int = 3         # In-cycle: stop POST when <= 3 remaining
    upvote_only_threshold: float = 0.85   # Upvote without comment if relevance >= this
    proactive_wait_seconds: float = 120.0  # Default wait when reset time unknown


ADAPTIVE_BACKOFF = AdaptiveBackoffConfig()
