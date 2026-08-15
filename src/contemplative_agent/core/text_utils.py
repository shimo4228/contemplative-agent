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

logger = logging.getLogger(__name__)

MAX_SLUG_LENGTH = 50

LOG_PREVIEW_LIMIT = 80

_WS_RUN_RE = re.compile(r"\s+")


def log_preview(text: str, limit: int = LOG_PREVIEW_LIMIT) -> str:
    """Collapse text to a single truncated line safe for operational logs.

    Generated bodies must not enter ``*.log`` verbatim: multi-line prose
    becomes prefix-less continuation lines that the log-anomaly sweep
    ingests as anomaly signatures, and full LLM output (downstream of
    untrusted feed content) does not belong in the channel classified as
    self-written (weekly 2026-07-11 F1.1). Full bodies live in the episode
    log and comment-reports; logs get this preview.
    """
    collapsed = _WS_RUN_RE.sub(" ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit].rstrip() + "…"


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


def extract_title(body: str) -> str | None:
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


def context_summary(body: str) -> str | None:
    """First sentence of the ``**Context:**`` line, or ``None`` when absent.

    The trigger-condition sentence of a skill body.
    """
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
    description = context_summary(body) or title
    # YAML double-quoted scalar: collapse whitespace and neutralise inner
    # double quotes so the synthesized line stays parseable.
    description = " ".join(description.split()).replace('"', "'")
    return f'---\nname: {name}\ndescription: "{description}"\norigin: {origin}\n---'


_FRONTMATTER_SCALAR_RE = {
    "name": re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE),
    "description": re.compile(r'^description:\s*"?(.*?)"?\s*$', re.MULTILINE),
}


def skill_theme(text: str, fallback_name: str = "skill") -> tuple[str, str]:
    """Return ``(name, description)`` for a skill document.

    Reads the YAML frontmatter scalars when present; falls back to the
    first Markdown title (and the given name) for legacy bodies without
    frontmatter. The read-side inverse of :func:`synthesize_frontmatter`.
    Shared by the novelty gate's known-theme inventory, the staged-ledger
    writer, the skill selector's catalog and the stocktake grouping
    evidence so every side agrees on a skill's identity.
    """
    frontmatter, body = split_frontmatter(text)
    name = None
    description = None
    if frontmatter:
        m = _FRONTMATTER_SCALAR_RE["name"].search(frontmatter)
        name = m.group(1).strip() if m else None
        m = _FRONTMATTER_SCALAR_RE["description"].search(frontmatter)
        description = m.group(1).strip() if m else None
    title = extract_title(body or text)
    return (name or fallback_name, description or title or "")


def read_markdown_documents(
    directory: Path, *, since: str | None = None
) -> list[tuple[str, str, str]]:
    """Return sorted ``(filename, raw text, frontmatter-stripped body)``.

    The one reader behind :func:`read_markdown_bodies` and the stocktake
    pass, so the file rules live in exactly one place: ``*.md`` only,
    dotfiles skipped, unreadable files logged and skipped, files whose body
    is empty after stripping dropped. When *since* is an ISO timestamp, only
    files modified after it are included (an unparseable *since* logs a
    warning and reads all). The raw text keeps its frontmatter.
    """
    if not directory.is_dir():
        return []
    cutoff: float | None = None
    if since:
        try:
            cutoff = datetime.fromisoformat(since).timestamp()
        except ValueError:
            logger.warning("Invalid since timestamp %r, reading all files", since)
    docs: list[tuple[str, str, str]] = []
    for p in sorted(directory.glob("*.md")):
        if p.name.startswith("."):
            continue
        if cutoff is not None and p.stat().st_mtime < cutoff:
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Could not read file %s", p)
            continue
        body = strip_frontmatter(raw).strip()
        if body:
            docs.append((p.name, raw, body))
    return docs


def read_markdown_bodies(directory: Path, *, since: str | None = None) -> list[tuple[str, str]]:
    """Return sorted ``(filename, frontmatter-stripped body)`` for ``*.md``.

    Projection of :func:`read_markdown_documents`. Shared by the
    rules-distill and stocktake readers.
    """
    return [(name, body) for name, _raw, body in read_markdown_documents(directory, since=since)]
