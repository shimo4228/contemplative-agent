"""Markdown text helpers shared by insight / stocktake / cli.

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
from collections.abc import Iterator
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

    Used by insight and the artifact writers to
    derive a stable filename from generated artifact bodies.
    """
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return None


def strip_frontmatter(text: str) -> str:
    """Strip a leading YAML frontmatter block (``---`` delimited).

    Returns *text* unchanged when there is no frontmatter. Used by
    stocktake (skill body
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

    Complements :func:`strip_frontmatter` for callers that need the
    frontmatter half — the description audit reads the declared
    ``name`` / ``description`` beside the body it judges.
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

    For legacy skills written before frontmatter was emitted. ``name`` is
    the title slug, ``description``
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


def set_frontmatter_field(text: str, key: str, value: str, *, synthesize: bool = False) -> str:
    """Return *text* with the top-level ``key: value`` scalar set in its frontmatter.

    The one set-or-insert. Two callers had grown their own — the adopt-time
    name canonicalization (``artifact_extraction``) and the ADR-0097 archive
    exit's supersede stamps (``cli/adopt``) — and ``_adopt_write_item`` called
    both on the same text ten lines apart (code review 2026-08-22). A pure
    text transform belongs here beside :func:`split_frontmatter` and
    :func:`synthesize_frontmatter`, which both copies already imported.

    Matching is anchored at column 0, deliberately: the frontmatter is read
    by regex, never parsed as YAML, so a ``key:`` indented inside a block
    scalar is prose and must survive (pinned by
    ``test_only_the_top_level_name_key_is_rewritten``). A key that is absent
    is appended before the closing ``---``, which keeps the emitted
    name/description/origin order intact when a lineage field joins them.

    *synthesize* decides what a body with no frontmatter gets. The default
    returns it unchanged — ``skill_theme`` already falls back to the filename
    stem, so canonicalizing a name into a block nobody wrote would invent
    identity rather than align it. Callers that need the field to be findable
    afterwards (an archived legacy skill whose ``superseded_by:`` is its only
    pointer home) pass ``True`` and get a block holding **only that field**.

    Deliberately not :func:`synthesize_frontmatter` for that case: it fills in
    ``name`` / ``description`` / ``origin``, and ``origin: auto-extracted`` is
    the harness's vocabulary for extraction-pipeline output. Stamping it on a
    hand-written skill fabricates provenance, and since restoring from the
    archive is a plain ``mv``, the false claim comes back into the store
    (silent-failure review 2026-08-22 MEDIUM). Add the field asked for and
    nothing else.
    """
    frontmatter, body = split_frontmatter(text)
    if not frontmatter:
        if not synthesize:
            return text
        frontmatter = "---\n---"
    lines = frontmatter.split("\n")
    prefix = f"{key}:"
    for i, line in enumerate(lines):
        if line.startswith(prefix):
            lines[i] = f"{key}: {value}"
            break
    else:
        # lines[0] and lines[-1] are the ``---`` fences.
        lines.insert(len(lines) - 1, f"{key}: {value}")
    return "\n".join(lines) + "\n\n" + body


_FM_NAME_RE = re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE)
_FM_DESCRIPTION_RE = re.compile(r'^description:\s*"?(.*?)"?\s*$', re.MULTILINE)


def skill_theme(text: str, fallback_name: str = "skill") -> tuple[str, str]:
    """Return ``(name, description)`` for a skill document.

    Reads the YAML frontmatter scalars when present; falls back to the
    first Markdown title (and the given name) for legacy bodies without
    frontmatter. The read-side inverse of :func:`synthesize_frontmatter`.
    Shared by the novelty gate's known-theme inventory, the staged-ledger
    writer, the skill selector's catalog and the stocktake description
    audit so every side agrees on a skill's identity.
    """
    frontmatter, body = split_frontmatter(text)
    name = None
    description = None
    if frontmatter:
        m = _FM_NAME_RE.search(frontmatter)
        name = m.group(1).strip() if m else None
        m = _FM_DESCRIPTION_RE.search(frontmatter)
        description = m.group(1).strip() if m else None
    title = extract_title(body or text)
    return (name or fallback_name, description or title or "")


def iter_markdown_documents(
    directory: Path | None, *, label: str = "Could not read file", since: str | None = None
) -> Iterator[tuple[Path, str]]:
    """Yield ``(path, raw text)`` for the ``*.md`` files of *directory*.

    The one owner of the traversal rules every skill/rule reader shares:
    sorted glob, ``*.md`` only, dotfiles skipped, unreadable files logged
    (under *label*) and skipped. The read catches ``ValueError`` as well as
    ``OSError`` — ``UnicodeDecodeError`` is NOT an ``OSError``, so a file with
    one bad byte used to raise out of every caller that only caught the
    latter. When *since* is an ISO timestamp, only files modified after it are
    yielded (an unparseable *since* logs a warning and reads all).

    Callers keep whatever is theirs (body filter, identity scrub, catalog
    shape); nothing here decides what a document means.
    """
    if directory is None or not directory.is_dir():
        return
    cutoff: float | None = None
    if since:
        try:
            cutoff = datetime.fromisoformat(since).timestamp()
        except ValueError:
            logger.warning("Invalid since timestamp %r, reading all files", since)
    for p in sorted(directory.glob("*.md")):
        if p.name.startswith("."):
            continue
        if cutoff is not None and p.stat().st_mtime < cutoff:
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except (OSError, ValueError):
            logger.warning("%s %s", label, p.name)
            continue
        yield p, raw


def read_markdown_documents(
    directory: Path, *, since: str | None = None
) -> list[tuple[str, str, str]]:
    """Return sorted ``(filename, raw text, frontmatter-stripped body)``.

    The stocktake reader: :func:`iter_markdown_documents` plus this pass's own
    rule that files whose body is empty after stripping are dropped. The raw
    text keeps its frontmatter.
    """
    docs: list[tuple[str, str, str]] = []
    for p, raw in iter_markdown_documents(directory, since=since):
        body = strip_frontmatter(raw).strip()
        if body:
            docs.append((p.name, raw, body))
    return docs
