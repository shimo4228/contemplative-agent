"""Shared file I/O utilities for core modules.

Provides restricted-permission file writes and text truncation.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


SUMMARY_MAX_LENGTH = 200


def truncate(text: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    """Truncate text to max_length, appending '...' if trimmed."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def write_restricted(path: Path, content: str) -> None:
    """Write content to a file with 0600 permissions from creation.

    Uses umask to ensure the file is never world-readable, even briefly.
    Note: os.umask() is process-wide and not thread-safe.
    """
    old_umask = os.umask(0o177)
    try:
        path.write_text(content, encoding="utf-8")
    finally:
        os.umask(old_umask)


