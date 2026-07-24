"""Shared file I/O utilities for core modules.

Provides restricted-permission file writes, JSONL append, UTC timestamp,
and text truncation helpers used across core / adapters.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import logging
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


SUMMARY_MAX_LENGTH = 200


def truncate(text: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    """Truncate text to max_length, appending '...' if trimmed."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


_SENTENCE_SEPS = ("。", "！", "？", ".\n", ". ", "! ", "? ")


def truncate_boundary(text: str, max_length: int, marker: str = "…[truncated]") -> str:
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
            best = max(best, cand)
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
    """Atomically write content to a file with 0600 permissions.

    Uses umask to ensure the file is never world-readable, even briefly.
    Note: os.umask() is process-wide and not thread-safe.

    Atomic since bug-audit 2026-07-06 M11 (``.tmp`` sibling + ``os.replace``):
    a process interruption mid-write previously left a truncated
    skill/rule/constitution file that the next curation run silently
    consumed. On failure the temp file is removed and the ``OSError``
    re-raised.
    """
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    old_umask = os.umask(0o177)
    try:
        tmp_path.write_text(content, encoding="utf-8")
        os.replace(str(tmp_path), str(path))
    except OSError:
        tmp_path.unlink(missing_ok=True)
        raise
    finally:
        os.umask(old_umask)


def append_jsonl_restricted(path: Path, record: dict[str, Any]) -> None:
    """Append one JSON record to a JSONL file with 0600 permissions.

    Creates the parent directory if missing. Serialises with
    ``ensure_ascii=False`` so unicode content stays readable in the log.
    Unlike ``write_restricted`` this opens in append mode, so the umask
    only affects files that do not exist yet — pre-existing files keep
    their current permission bits.

    Every record is stamped with the process ``run_id`` (and ``session_id``
    while an agent session is active) so offline tooling can group records
    by execution instead of inferring runs from time gaps (ADR-0078
    follow-up). Stamping happens here — the single writer all audit logs
    share — so no producer can forget it. Caller-supplied values win.
    """
    from .run_context import RUN_ID, current_session_id

    stamped = dict(record)
    stamped.setdefault("run_id", RUN_ID)
    session_id = current_session_id()
    if session_id is not None:
        stamped.setdefault("session_id", session_id)

    path.parent.mkdir(parents=True, exist_ok=True)
    old_umask = os.umask(0o177)
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(stamped, ensure_ascii=False) + "\n")
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


def strip_to_printable(value: object, max_len: int, *, keep_newline: bool = False) -> str:
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


def b64_audit_fields(
    name: str,
    text: str | None,
    *,
    max_bytes: int,
    sha256: str | None = None,
) -> dict[str, Any]:
    """Replay-safe storage bundle for one untrusted text field (ADR-0075).

    Emits ``{name}_sha256`` over the *full* text, ``{name}_b64`` of the kept
    prefix, ``{name}_bytes`` (full byte length), and an explicit
    ``{name}_truncated`` flag, so an offline replay can tell a bounded record
    from a complete one instead of silently reading a cut-off payload as whole.

    Single owner for the encoding so the three audit writers (insight-novelty,
    skill-selection, verification) cannot drift in replay format. ``max_bytes``
    stays per-caller — the cap is each log's size budget, not a shared
    constant. ``sha256`` overrides the digest for callers that already
    computed it upstream over the same text.

    ``text is None`` yields only ``{name}_b64: None`` (no digest / length /
    flag): the field was never produced, which is distinct from "produced and
    empty".

    The prefix is cut on a **codepoint** boundary. A raw ``raw[:max_bytes]``
    slice can end mid-sequence, and a consumer doing
    ``b64decode(rec[f"{name}_b64"]).decode("utf-8")`` then raises
    ``UnicodeDecodeError`` — a live hazard for this project's Japanese
    payloads. Re-encoding the ignore-decoded prefix drops only the trailing
    partial sequence, since the input is valid UTF-8 by construction.
    """
    if text is None:
        return {f"{name}_b64": None}
    raw = text.encode("utf-8", "replace")
    kept = raw[:max_bytes]
    if len(kept) < len(raw):
        kept = kept.decode("utf-8", "ignore").encode("utf-8")
    return {
        f"{name}_sha256": sha256 if sha256 is not None else hashlib.sha256(raw).hexdigest(),
        f"{name}_encoding": "base64:utf-8",
        f"{name}_b64": base64.b64encode(kept).decode("ascii"),
        f"{name}_bytes": len(raw),
        f"{name}_truncated": len(kept) < len(raw),
    }


def ensure_aware(dt: datetime) -> datetime:
    """Coerce a tz-naive datetime to UTC; tz-aware inputs pass through."""
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def parse_aware_utc(value: str) -> datetime:
    """Parse an ISO timestamp, coercing a tz-naive result to UTC.

    Raises the same exceptions as :func:`datetime.fromisoformat`; callers
    keep their own ``try/except`` so each decides which inputs to skip.
    """
    return ensure_aware(datetime.fromisoformat(value))


def age_days(dt: datetime, *, now: datetime | None = None) -> float:
    """Non-negative age in days of an aware datetime versus *now* (UTC)."""
    ref = now if now is not None else datetime.now(timezone.utc)
    return max(0.0, (ref - dt).total_seconds() / 86400.0)


def write_text_atomic(path: Path, content: str) -> None:
    """Atomically write *content* with 0600 perms.

    Since bug-audit 2026-07-06 M11 this is a thin alias of
    :func:`write_restricted`, which performs the ``.tmp`` sibling +
    ``os.replace`` dance itself; kept so existing call sites keep their
    intent-revealing name. On failure the temp file is removed and the
    ``OSError`` re-raised; callers decide whether to log-and-swallow or
    propagate (the raise-vs-warn policy stays at the call site).
    """
    write_restricted(path, content)


def read_run_marker(directory: Path | None, name: str) -> str | None:
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
