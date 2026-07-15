"""Process-wide run/session identity for audit records.

ADR-0078 follow-up: the offline OTLP conversion showed that trace grouping
without an execution ID degrades to time-gap inference. ``RUN_ID`` names one
process execution (any CLI command); ``session_id`` is set only while an
autonomous agent session (``run`` command) is active. Both are stamped onto
every audit record by ``append_jsonl_restricted`` — producers never handle
them directly, so no log writer can forget.
"""

from __future__ import annotations

import uuid
from typing import Optional

# One per process, generated at import time. All audit records written by
# this process share it, which lets offline tooling group them exactly.
RUN_ID: str = uuid.uuid4().hex

_session_id: Optional[str] = None


def new_session_id() -> str:
    """Mint a fresh session identifier (uuid4 hex)."""
    return uuid.uuid4().hex


def set_session_id(session_id: Optional[str]) -> None:
    """Set (or clear, with None) the active agent-session identifier."""
    global _session_id
    _session_id = session_id


def current_session_id() -> Optional[str]:
    return _session_id
