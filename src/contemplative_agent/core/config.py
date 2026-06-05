"""Core security constants and content limits.

These constants are platform-independent and shared across all adapters.
"""

import re
from typing import Tuple

VALID_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
VALID_SUBMOLT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,49}$")

FORBIDDEN_SUBSTRING_PATTERNS: Tuple[str, ...] = (
    "api_key",
    "api-key",
    "apikey",
    "Bearer ",
    "auth_token",
    "access_token",
    "private_key",
    "-----BEGIN",
)
FORBIDDEN_WORD_PATTERNS: Tuple[str, ...] = (
    "password",
    "secret",
)

# Output sanitization redacts credential *assignments* only ("password: x",
# "secret = y"). Bare word occurrences ("the secret to success") are
# legitimate prose and must survive ``_sanitize_output`` (audit L1: the old
# word replace corrupted published text). The fail-closed gates — identity
# validation and the GUARDED content filter — keep the stricter bare-word
# check via FORBIDDEN_WORD_PATTERNS above: there a false positive blocks an
# action instead of mutating it.
# Separator class includes the fullwidth colon ： (CJK output path —
# qwen3.5 emits it in Japanese text; security review 2026-06-05).
FORBIDDEN_ASSIGNMENT_RE = re.compile(
    r"\b(?:" + "|".join(FORBIDDEN_WORD_PATTERNS) + r")\s*[:=：]\s*\S+",
    re.IGNORECASE,
)

# Moltbook API char limits (verified via skill.md, 2026-05-04):
# - Post body: 40,000 chars
# - Post title: 300 chars
# - Comment / Reply: not specified (10,000 retained as conservative cap)
MAX_POST_LENGTH = 40000
MAX_POST_TITLE_LENGTH = 300
MAX_COMMENT_LENGTH = 10000
