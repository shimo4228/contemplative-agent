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
IDENTITY_PATH = MOLTBOOK_DATA_DIR / "identity.md"
KNOWLEDGE_PATH = MOLTBOOK_DATA_DIR / "knowledge.md"
EPISODE_LOG_DIR = MOLTBOOK_DATA_DIR / "logs"
LEGACY_MEMORY_PATH = MOLTBOOK_DATA_DIR / "memory.json"
COMMENTED_CACHE_PATH = MOLTBOOK_DATA_DIR / "commented_cache.json"
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
    comments_per_day: int = 200


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

    The API allows 60 req/min (GET+POST shared quota).
    One cycle consumes ~8 requests (1 notification + 6 feed + 1 post).
    """

    base_cycle_wait: float = 60.0         # Normal cycle interval (seconds)
    max_cycle_wait: float = 600.0         # Maximum backoff (10 minutes)
    backoff_multiplier: float = 2.0       # Exponential backoff multiplier
    decay_factor: float = 0.5             # Shrink factor on clean cycle
    remaining_threshold: int = 10         # Start slowing when <= 10 remaining
    cycle_budget_reserve: int = 5         # In-cycle: stop processing when <= 5 remaining
    proactive_wait_seconds: float = 120.0  # Default wait when reset time unknown


ADAPTIVE_BACKOFF = AdaptiveBackoffConfig()
