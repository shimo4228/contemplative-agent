"""Markdown text helpers shared by insight / rules-distill / stocktake / cli.

Promoted from `core/insight.py` and `core/rules_distill.py` in ADR-0035 PR2.
The promotion breaks the `stocktake → rules_distill` import edge that
existed only because `_strip_frontmatter` lived in `rules_distill.py`.

These are deterministic string transforms with no LLM dependency. They
sit at `core/` (not `_io.py`) because they are content-level rather than
I/O-level — slugifying a title is logically closer to what insight /
rules_distill produce than to how files are written.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

MAX_SLUG_LENGTH = 50


def slugify(title: str) -> str:
    """Convert a title to a filesystem-safe slug.

    NFKD-normalises Unicode, lowercases, replaces non-alphanumeric runs
    with single hyphens, trims leading/trailing hyphens, and caps at
    ``MAX_SLUG_LENGTH``. Returns an empty string when *title* contains
    no usable characters.
    """
    normalized = unicodedata.normalize("NFKD", title)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:MAX_SLUG_LENGTH]


def extract_title(body: str) -> Optional[str]:
    """Return the first ``# `` heading text, or ``None`` when absent.

    Used by insight, rules-distill, and the stocktake merge writer to
    derive a stable filename from generated artifact bodies.
    """
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def strip_frontmatter(text: str) -> str:
    """Strip a leading YAML frontmatter block (``---`` delimited).

    Returns *text* unchanged when there is no frontmatter. Used by
    rules-distill (skill input parsing) and stocktake (skill body
    comparison).
    """
    return split_frontmatter(text)[1]


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split a leading YAML frontmatter block from the body.

    Returns ``(frontmatter, body)`` where *frontmatter* is the full block
    including both ``---`` delimiters (no trailing newline) and *body* is
    the remainder — identical to what :func:`strip_frontmatter` returns.
    When *text* has no leading frontmatter (or the block is never closed),
    returns ``("", text)``.

    Complements :func:`strip_frontmatter`: the stocktake clean phase needs
    the frontmatter half so it can re-attach a singleton's original
    metadata (``name`` / ``description`` / ``origin`` and any reflection
    bookkeeping) after rewriting only the body's triggers.
    """
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return "", text
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            frontmatter = "\n".join(lines[: i + 1])
            body = "\n".join(lines[i + 1 :]).lstrip("\n")
            return frontmatter, body
    return "", text


_CONTEXT_RE = re.compile(r"^\s*\*\*Context:\*\*\s*(.+)$", re.MULTILINE)


def _context_summary(body: str) -> Optional[str]:
    """First sentence of the ``**Context:**`` line, or ``None`` when absent."""
    match = _CONTEXT_RE.search(body)
    if not match:
        return None
    text = match.group(1).strip()
    # First sentence: up to the first ". " boundary, else the whole line.
    head = re.split(r"(?<=\.)\s", text, maxsplit=1)[0].strip()
    return head or None


def synthesize_frontmatter(body: str, *, origin: str = "auto-extracted") -> str:
    """Build a minimal YAML frontmatter block for a body that lacks one.

    Used by the stocktake clean phase for legacy skills written before
    merge emitted frontmatter. ``name`` is the title slug, ``description``
    is the first sentence of the ``**Context:**`` line (falling back to the
    title), and ``origin`` records the distillation source. The returned
    block carries both ``---`` delimiters and no trailing newline, mirroring
    :func:`split_frontmatter`, so a caller can re-attach it with
    ``f"{block}\\n\\n{body}"``.
    """
    title = extract_title(body) or "skill"
    name = slugify(title) or "skill"
    description = _context_summary(body) or title
    # YAML double-quoted scalar: collapse whitespace and neutralise inner
    # double quotes so the synthesized line stays parseable.
    description = " ".join(description.split()).replace('"', "'")
    return (
        "---\n"
        f"name: {name}\n"
        f'description: "{description}"\n'
        f"origin: {origin}\n"
        "---"
    )


def read_markdown_bodies(
    directory: Path, *, since: Optional[str] = None
) -> List[Tuple[str, str]]:
    """Return sorted ``(filename, frontmatter-stripped body)`` for ``*.md``.

    Skips dotfiles and empty bodies; logs a warning on unreadable files.
    When *since* is an ISO timestamp, only files modified after it are
    included (an unparseable *since* logs a warning and reads all). Shared
    by the insight / rules-distill / stocktake readers.
    """
    if not directory.is_dir():
        return []
    cutoff: Optional[float] = None
    if since:
        try:
            cutoff = datetime.fromisoformat(since).timestamp()
        except ValueError:
            logger.warning("Invalid since timestamp %r, reading all files", since)
    items: List[Tuple[str, str]] = []
    for p in sorted(directory.glob("*.md")):
        if p.name.startswith("."):
            continue
        if cutoff is not None and p.stat().st_mtime < cutoff:
            continue
        try:
            body = strip_frontmatter(p.read_text(encoding="utf-8")).strip()
            if body:
                items.append((p.name, body))
        except OSError:
            logger.warning("Could not read file %s", p)
    return items
