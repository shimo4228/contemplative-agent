"""Constants and configuration for the Moltbook agent."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

VALID_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


BASE_URL = "https://www.moltbook.com/api/v1"
ALLOWED_DOMAIN = "www.moltbook.com"

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

COMMENT_PACING_MIN_SECONDS = 60
COMMENT_PACING_MAX_SECONDS = 180

VALID_SUBMOLT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,49}$")

OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_MODEL = "qwen3.5:9b"

MAX_VERIFICATION_FAILURES = 7
MAX_RETRY_ON_429 = 3
CONNECT_TIMEOUT = 30
READ_TIMEOUT = 60

MAX_POST_LENGTH = 20000
MAX_COMMENT_LENGTH = 10000
FORBIDDEN_SUBSTRING_PATTERNS: Tuple[str, ...] = (
    "api_key",
    "api-key",
    "apikey",
    "Bearer ",
    "auth_token",
    "access_token",
)
FORBIDDEN_WORD_PATTERNS: Tuple[str, ...] = (
    "password",
    "secret",
)


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
