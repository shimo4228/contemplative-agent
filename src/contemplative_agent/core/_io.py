"""Shared file I/O utilities for core modules.

Provides restricted-permission file writes and text truncation.
"""

from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime
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


def archive_before_write(path: Path, history_dir: Path) -> None:
    """Archive a file to history_dir before it gets overwritten.

    Copies path to history_dir/YYYY-MM-DDTHHMM.md with 0600 permissions.
    Does nothing if the file doesn't exist or is empty.
    """
    if not path.exists():
        return
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return

    history_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H%M")
    archive_path = history_dir / f"{timestamp}.md"
    shutil.copy2(path, archive_path)
    os.chmod(archive_path, 0o600)
    logger.info("Archived %s → %s", path.name, archive_path)
