"""Shared file I/O utilities for core modules.

Provides restricted-permission file writes, JSONL append, UTC timestamp,
and text truncation helpers used across core / adapters.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)


SUMMARY_MAX_LENGTH = 200


def truncate(text: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    """Truncate text to max_length, appending '...' if trimmed."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


_SENTENCE_SEPS = ("。", "！", "？", ".\n", ". ", "! ", "? ")


def truncate_boundary(
    text: str, max_length: int, marker: str = "…[truncated]"
) -> str:
    """Truncate at the nearest sentence -> word -> char boundary.

    Unlike ``truncate`` (hard character slice), this prefers a sentence
    end, then a word boundary, before falling back to a hard cut, and
    appends ``marker`` only when it trims. The boundary is honoured only
    in the back half of the window so a very early separator does not
    discard most of the budget. Avoids the mid-word / mid-character cut
    that an LLM reader can misread as an intentional pause (ADR-0060).

    ``text`` at or under ``max_length`` is returned unchanged, no marker.
    """
    if len(text) <= max_length:
        return text
    budget = max_length - len(marker)
    if budget <= 0:
        # No room for content + marker; keep the result within max_length.
        return marker[:max_length]
    window = text[:budget]
    floor = budget // 2  # only honour a boundary past the window midpoint
    best = -1
    for sep in _SENTENCE_SEPS:
        idx = window.rfind(sep)
        if idx != -1:
            cand = idx + len(sep)
            if cand > best:
                best = cand
    if best >= floor:
        return text[:best].rstrip() + marker
    space = window.rfind(" ")
    if space >= floor:
        return window[:space].rstrip() + marker
    return window.rstrip() + marker


def strip_code_fence(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    return text


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


def append_jsonl_restricted(path: Path, record: Dict[str, Any]) -> None:
    """Append one JSON record to a JSONL file with 0600 permissions.

    Creates the parent directory if missing. Serialises with
    ``ensure_ascii=False`` so unicode content stays readable in the log.
    Unlike ``write_restricted`` this opens in append mode, so the umask
    only affects files that do not exist yet — pre-existing files keep
    their current permission bits.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    old_umask = os.umask(0o177)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    finally:
        os.umask(old_umask)


@contextmanager
def acquire_run_lock(lock_path: Path, *, blocking: bool) -> Iterator[bool]:
    """``fcntl.flock``-based process lock (audit M5).

    Serialises the scheduled entry points (run / distill) that all mutate
    ``knowledge.json`` and ``rate_state.json`` — without it, concurrent
    launchd jobs are later-writer-wins. Yields True while the lock is
    held; in non-blocking mode yields False instead of waiting when
    another process holds it. The kernel releases the lock on process
    death, so there is no stale-lock cleanup.
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        flags = fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        try:
            fcntl.flock(fd, flags)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def now_iso(timespec: str = "minutes") -> str:
    """UTC ISO timestamp. Defaults to minutes precision.

    Centralises timestamp formatting so audit / frontmatter / log writers
    produce aligned strings. Callers that need finer-grained timestamps
    (e.g. audit log) pass ``timespec="seconds"``.
    """
    return datetime.now(timezone.utc).isoformat(timespec=timespec)


_PRINTABLE_RE = re.compile(r"[^\x20-\x7E]")
_PRINTABLE_KEEP_NL_RE = re.compile(r"[^\x20-\x7E\n]")


def strip_to_printable(
    value: object, max_len: int, *, keep_newline: bool = False
) -> str:
    """Strip to printable ASCII and cap at ``max_len``.

    Shared log / audit / prompt-injection guard: one place that drops
    non-printable bytes (which can smuggle ANSI escapes or markdown
    breakers into an LLM-facing or terminal-facing string) and bounds the
    length. ``keep_newline=True`` preserves ``\\n`` for callers that want
    multi-line context to survive. ``re.sub`` only deletes, so slicing
    before the substitution is equivalent to slicing after.
    """
    pattern = _PRINTABLE_KEEP_NL_RE if keep_newline else _PRINTABLE_RE
    return pattern.sub("", str(value)[:max_len])


def ensure_aware(dt: datetime) -> datetime:
    """Coerce a tz-naive datetime to UTC; tz-aware inputs pass through."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def parse_aware_utc(value: str) -> datetime:
    """Parse an ISO timestamp, coercing a tz-naive result to UTC.

    Raises the same exceptions as :func:`datetime.fromisoformat`; callers
    keep their own ``try/except`` so each decides which inputs to skip.
    """
    return ensure_aware(datetime.fromisoformat(value))


def age_days(dt: datetime, *, now: Optional[datetime] = None) -> float:
    """Non-negative age in days of an aware datetime versus *now* (UTC)."""
    ref = now if now is not None else datetime.now(timezone.utc)
    return max(0.0, (ref - dt).total_seconds() / 86400.0)


def write_text_atomic(path: Path, content: str) -> None:
    """Atomically write *content* via a ``.tmp`` sibling + ``os.replace``.

    Writes the temp file with 0600 perms (:func:`write_restricted`) then
    renames it over *path*. On failure the temp file is removed and the
    ``OSError`` re-raised; callers decide whether to log-and-swallow or
    propagate (the raise-vs-warn policy stays at the call site).
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        write_restricted(tmp_path, content)
        os.replace(str(tmp_path), str(path))
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise


def read_run_marker(directory: Optional[Path], name: str) -> Optional[str]:
    """Read a stored ISO timestamp from ``directory/name``, or ``None``."""
    if directory is None:
        return None
    marker = directory / name
    if marker.exists():
        return marker.read_text(encoding="utf-8").strip()
    return None


def write_run_marker(directory: Path, name: str) -> None:
    """Record ``now_iso()`` into ``directory/name``, creating parents."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(now_iso() + "\n", encoding="utf-8")


