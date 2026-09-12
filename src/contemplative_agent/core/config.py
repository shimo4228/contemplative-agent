"""Core security constants and content limits.

These constants are platform-independent and shared across all adapters.
"""

import re

VALID_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

# Ids become log keys and file-free join keys, and VALID_ID_PATTERN bounds the
# alphabet but not the length — a legal 1 MB id would be written verbatim into
# the audit logs (code review 2026-09-09). Platform ids observed in
# logs/api-audit.jsonl are well under this.
MAX_ID_CHARS = 128


def is_valid_id(value: object) -> bool:
    """Whether an id off an untrusted response may be kept as a join key.

    Both halves belong together and were drifting apart: three frames applied
    the pattern, only two also applied the cap, and the one that did not
    (``parse_created_post_response``) feeds the same audit rows as the ones
    that did. The rule is the id's, not each reader's, so it lives with the
    pattern it is half of.

    Two things depend on it: the outcome log stays free of plaintext
    attacker-chosen strings — the invariant that lets this repo classify
    ``logs/*.jsonl`` as readable, since untrusted *bodies* are base64 — and
    the reading's join key stays a bounded token (security review
    2026-09-09). Takes ``object`` because every caller reads it out of
    server-controlled JSON, where a non-string is one of the shapes to reject.
    """
    return (
        isinstance(value, str)
        and 0 < len(value) <= MAX_ID_CHARS
        and bool(VALID_ID_PATTERN.match(value))
    )


VALID_SUBMOLT_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,49}$")

FORBIDDEN_SUBSTRING_PATTERNS: tuple[str, ...] = (
    "api_key",
    "api-key",
    "apikey",
    "Bearer ",
    "auth_token",
    "access_token",
    "private_key",
    "-----BEGIN",
)
FORBIDDEN_WORD_PATTERNS: tuple[str, ...] = (
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

# Bare-word form of the same list, for the fail-closed gates (identity
# validation, the GUARDED content filter) that reject rather than redact. One
# compiled alternation so a caller does not rebuild a pattern per word per call.
FORBIDDEN_WORD_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in FORBIDDEN_WORD_PATTERNS) + r")\b",
    re.IGNORECASE,
)

# One compiled alternation over the substring patterns, so a caller scanning a
# whole file does not have to build a lowercased copy of it (knowledge.json is
# ~190 MB with embeddings inline; the copy cost more than the scan).
_FORBIDDEN_SUBSTRING_RE = re.compile(
    "|".join(re.escape(p) for p in FORBIDDEN_SUBSTRING_PATTERNS), re.IGNORECASE
)


def first_forbidden_substring(text: str) -> str | None:
    """Return the first forbidden substring present in *text*, else None.

    Case-insensitive, matching the per-pattern ``pat.lower() in text.lower()``
    checks this replaces. Callers decide the policy (refuse the load, skip the
    file, reject the value) — this only answers whether one is present.
    """
    match = _FORBIDDEN_SUBSTRING_RE.search(text)
    return match.group(0) if match else None


# Moltbook API char limits (verified via skill.md, 2026-05-04):
# - Post body: 40,000 chars
# - Post title: 300 chars
# - Comment / Reply: not specified (10,000 retained as conservative cap)
MAX_POST_LENGTH = 40000
MAX_POST_TITLE_LENGTH = 300
MAX_COMMENT_LENGTH = 10000
