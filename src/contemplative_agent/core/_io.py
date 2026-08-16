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
import tempfile
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
    """Atomically write *content* to *path* with mode 0600.

    Publishes through a unique temp file in the target's own directory plus
    ``os.replace``, so a reader never observes a partial file (bug-audit
    2026-07-06 M11 — process interruption, not power loss; there is no
    ``fsync``). On any failure the temp file is removed and the exception
    re-raised; callers keep their own raise-vs-warn policy.

    ``os.replace`` is symlink-safe (it swaps a symlinked *target* itself,
    which ``cli/adopt.py::_replaces_canonical_target`` depends on), so the
    temp file was the only write here that could be redirected. It comes from
    ``tempfile.mkstemp`` — ``O_CREAT|O_EXCL|O_NOFOLLOW``, mode 0600 — rather
    than a ``Path.write_text`` to a predictable ``<target>.tmp``, which
    followed whatever symlink or hardlink was planted there. The
    unpredictable NAME is what makes those flags unfalsifiable: there is no
    path left for an attacker to occupy in advance, and no shared name for
    two concurrent writers to truncate each other through
    (T-WRITE-TMP-NOFOLLOW; see the commit for the four failure modes the
    fixed name carried).

    Two costs, both deliberate. A unique name is not self-cleaning: an
    interruption between create and replace leaves an orphan
    ``<name>.<random>.tmp`` that no later write reuses, which is why the
    publish scripts exclude ``*.tmp``. And 0600 is pinned with ``fchmod`` on
    the fd rather than a process-wide ``os.umask`` — umask is not
    thread-safe, and it makes the mode exactly 0600 instead of "at most"
    (an ambient 0o200 would leave the agent unable to rewrite its identity).
    ``append_jsonl_restricted`` below still takes the umask route; its append
    mode only touches permissions when creating the file.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name + ".", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        handle = os.fdopen(fd, "w", encoding="utf-8")
    except BaseException:
        # ``fdopen`` takes ownership of the fd only once it returns; until
        # then this frame owns it, and the file it names is already on disk.
        os.close(fd)
        tmp_path.unlink(missing_ok=True)
        raise
    try:
        with handle:
            handle.write(content)
        os.replace(str(tmp_path), str(path))
    except BaseException:
        # NOT ``except OSError``: encoding the content raises
        # ``UnicodeEncodeError`` (a ValueError), and with a unique name the
        # orphan it left was permanent rather than reclaimed by the next
        # write. Reachable from `cli/adopt.py::_mark_sidecar_held`, which
        # re-serialises a user-writable sidecar, so a lone surrogate in it
        # produced one orphan per attempt (both reviews, 2026-08-15).
        tmp_path.unlink(missing_ok=True)
        raise


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

    Deliberate cost, since callers use this for human-readable previews:
    ASCII-only means em dashes, curly quotes and any non-Latin script are
    DELETED, not transliterated. A preview of non-ASCII text can therefore
    come out empty — silently, because the argument count is still right.
    That is accepted here: these strings go to logs and audit records whose
    canonical source is stored elsewhere, and the same width that drops a
    Japanese sentence is what drops ANSI escapes and homoglyphs. If a caller
    needs meaning preserved rather than bytes bounded, it wants
    ``text_utils.log_preview`` (collapses whitespace, keeps Unicode) instead.
    """
    pattern = _PRINTABLE_KEEP_NL_RE if keep_newline else _PRINTABLE_RE
    return pattern.sub("", str(value)[:max_len])


# C0 (TAB and LF included), DEL, C1, and the Unicode format characters that
# act as line breaks or reorder a rendered line.
#
# TAB and LF were excluded until 2026-08-08 (the class was
# ``[\x00-\x08\x0b-\x1f\x7f]``, which straddles both). That held only because
# every caller happened to feed it text already split on newlines. It stopped
# holding when the skill-selection rejected-name tally began rendering one
# report line per entry: a single embedded ``\n`` forges an additional,
# indistinguishable row — demonstrated end-to-end by two independent reviews.
# The same hole was live in ``load_skill_catalog``'s description scrub, where
# ``_render_catalog`` joins on ``\n``. It is live again wherever an
# externally-authored name is rendered into a structured line, which is why
# ``episode_render.safe_peer_name`` joined in 2026-08-16.
#
# The bidi and zero-width block earns its place wherever a human is expected
# to compare two rendered strings by eye: RLO/ZWSP defeat exactly that
# comparison while leaving two visually identical rows distinct.
CONTROL_CHARS_RE = re.compile(
    "["
    "\x00-\x1f\x7f-\x9f"  # C0 (incl. TAB/LF), DEL, C1
    "\u200b-\u200f"  # zero-width space/joiners, LRM/RLM
    "\u2028\u2029"  # line/paragraph separator
    "\u202a-\u202e"  # bidi embedding/override
    "\u2060-\u2064\u2066-\u2069"  # word joiner, invisible ops, bidi isolates
    "\ufeff"  # BOM / zero-width no-break space
    "]"
)


def scrub_control(value: str, max_len: int) -> str:
    """Collapse whitespace, drop control characters, cap length.

    CJK-preserving counterpart to ``strip_to_printable`` for fields where
    non-ASCII content is legitimate (peer display names, descriptions,
    hallucinated names). ``strip_to_printable`` is ASCII-only by design and
    would delete a Japanese name outright — correct for a log preview whose
    canonical source is stored elsewhere, wrong for anything the model reads
    as content.

    Whitespace is collapsed before the character class runs so the result is
    guaranteed to be a single line: "no control characters" is a weaker
    promise than "cannot span lines", and the class alone would still let a
    future addition to it be forgotten.

    Lives here, next to ``strip_to_printable`` / ``log_safe_identifier``,
    because it is the third member of that family; it was written twice
    independently first (``skill_selection._scrub_control`` 2026-08-08,
    ``stocktake._scrub_reason`` security review 2026-07-24).
    """
    return CONTROL_CHARS_RE.sub("", " ".join(value.split()))[:max_len]


IDENTIFIER_MAX_CHARS = 64


def log_safe_identifier(value: object, placeholder: str = "<unprintable>") -> str:
    """Bound an externally-authored identifier (agent / author name) for a log.

    Display names are attacker-controlled the same way post bodies are, and
    they were the gap the 2026-08-01 security review found after the body
    leak was closed: a name containing a newline plus a word the log-anomaly
    sweep treats as level-agnostic signal ("backoff", "429") reproduces the
    prefix-less-continuation-line attack through the name field instead of
    the body field. These reach `logs/agent-launchd.log` at INFO, so they are
    not covered by dropping ``-v``.

    Differs from a bare ``strip_to_printable`` only in the fallback: a name
    that is entirely non-ASCII sanitises to the empty string, which turns
    "Replied to X on Y" into a sentence with a hole in it. Say so instead.
    """
    safe = strip_to_printable(value, IDENTIFIER_MAX_CHARS)
    return safe if safe.strip() else placeholder


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
