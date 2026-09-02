"""The wiki store and its four-verb operation vocabulary (RFC-0017 S1).

The Maintainer (S2) and the Proposer (S3) do not touch the filesystem. They
emit an *op* — one of the four frozen dataclasses below — and this module
decides whether it applies. Everything that could let a model widen its own
reach is held here, in code:

- **ids are allocated, never named.** ``Create`` carries a title and a body;
  the id comes from :func:`_next_page_id`. A model cannot invent ``p-9999``
  and have it exist, and cannot address a page by any spelling other than the
  one the index handed it.
- **anchors must be unique.** ``Replace`` / ``InsertAfter`` apply only when
  the anchor occurs exactly once. Zero and many are different refusals
  (``ANCHOR_NOT_FOUND`` / ``ANCHOR_AMBIGUOUS``) because they mean different
  things upstream: a hallucinated quote versus a real but under-specified one.
- **a refusal is a return value.** ADR-0075: the abstain carries a reason
  code and reaches ``logs/wiki-ops.jsonl``, so an offline replay can tell a
  Maintainer that emitted nothing from one whose every op was rejected.
  Raising would make the two look alike in the caller.
- **the path never leaves the store.** Ids are matched against
  :data:`_PAGE_ID_RE` and the resolved file is re-checked with
  ``_target_inside_data_root`` — the same predicate ``cli/store_paths`` uses,
  which moved into :mod:`._io` for this module (``core`` cannot import
  ``cli``; ADR-0001).

Pages are markdown with a hand-written YAML frontmatter block. Hand-written
because this project ships ``requests`` and ``numpy`` and nothing else, and
because the frontmatter here is a fixed five-key record rather than arbitrary
YAML: a parser that accepts less is the point, not a shortcut.

Wiki pages are a persistent memory an LLM wrote from untrusted episodes.
``rules/common/security.md`` says to read one back as untrusted data — this
module never interprets a page's body, only splices it.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

from ._io import (
    _target_inside_data_root,
    append_jsonl_restricted,
    now_iso,
    scrub_control,
    write_restricted,
)
from .text_utils import split_frontmatter

logger = logging.getLogger(__name__)


PATTERNS_DIRNAME = "patterns"
WIKI_OPS_LOG_NAME = "wiki-ops.jsonl"

# Four digits is a floor, not a cap: ``p-12345`` matches and sorts correctly
# because the allocator zero-pads to at least four and ids only grow.
_PAGE_ID_RE = re.compile(r"^p-\d{4,}$")

# Bounds on what reaches a rendered line. The body is not bounded — it is the
# page, and the page is the canonical copy — but the title goes into the
# index the Proposer reads as a single line, so it gets the same treatment as
# every other externally-authored identifier in this codebase.
_TITLE_MAX_CHARS = 120
_INDEX_SNIPPET_MAX_CHARS = 160
_SOURCE_MAX_CHARS = 64


OpName: TypeAlias = Literal["create", "append", "replace", "insert_after"]

RefusalReason: TypeAlias = Literal[
    "PAGE_NOT_FOUND",
    "PATH_ESCAPED",
    "ANCHOR_NOT_FOUND",
    "ANCHOR_AMBIGUOUS",
    "SOURCES_EMPTY",
    "TITLE_EMPTY",
    "TEXT_EMPTY",
    "PAGE_UNREADABLE",
]


@dataclass(frozen=True)
class Create:
    """A new pattern page. The id is allocated by the store, not supplied."""

    title: str
    body: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Append:
    """Add *text* to the end of an existing page's body."""

    page_id: str
    text: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class Replace:
    """Swap the single occurrence of *old* for *new*."""

    page_id: str
    old: str
    new: str
    sources: tuple[str, ...]


@dataclass(frozen=True)
class InsertAfter:
    """Put *text* on the line after the single occurrence of *anchor*."""

    page_id: str
    anchor: str
    text: str
    sources: tuple[str, ...]


WikiOp: TypeAlias = Create | Append | Replace | InsertAfter


@dataclass(frozen=True)
class WikiOpResult:
    """What the store did. ``applied`` and ``reason`` are never both set."""

    applied: bool
    op: OpName
    page_id: str | None
    reason: RefusalReason | None = None


@dataclass(frozen=True)
class WikiPage:
    """One page as read back. ``body`` is untrusted text; do not interpret it."""

    page_id: str
    title: str
    created: str
    updated: str
    revisions: int
    sources: tuple[str, ...]
    body: str


def _op_name(op: WikiOp) -> OpName:
    if isinstance(op, Create):
        return "create"
    if isinstance(op, Append):
        return "append"
    if isinstance(op, Replace):
        return "replace"
    return "insert_after"


def _op_text(op: WikiOp) -> str:
    """The op's payload — what the page gains. Hashed for the audit row.

    ``Replace`` hashes the replacement rather than the anchor: the anchor is
    already recoverable from the page's previous revision, the new text is
    not.
    """
    if isinstance(op, Create):
        return op.body
    if isinstance(op, Append):
        return op.text
    if isinstance(op, Replace):
        return op.new
    return op.text


def _clean_sources(sources: tuple[str, ...]) -> tuple[str, ...]:
    """Deduplicate, bound and single-line the episode ids, keeping order.

    The element form is an episode's ``ts`` — the ISO-8601 UTC timestamp the
    episode log keys on, which is what ``core/distill.py`` already stores as
    ``provenance.source_episode_ids``. RFC-0017 D4 asks the page to cite the
    raw layer; reusing that spelling rather than minting an id system means a
    page's citation and a pattern's provenance name the same thing.
    """
    out: list[str] = []
    for raw in sources:
        value = scrub_control(str(raw), _SOURCE_MAX_CHARS)
        if value and value not in out:
            out.append(value)
    return tuple(out)


def _render_frontmatter(page: WikiPage) -> str:
    lines = [
        "---",
        f"id: {page.page_id}",
        f"title: {page.title}",
        f"created: {page.created}",
        f"updated: {page.updated}",
        f"revisions: {page.revisions}",
        "sources:",
    ]
    lines.extend(f"  - {source}" for source in page.sources)
    lines.append("---")
    return "\n".join(lines)


def _render_page(page: WikiPage) -> str:
    return _render_frontmatter(page) + "\n" + page.body.rstrip("\n") + "\n"


def _parse_page(text: str) -> WikiPage | None:
    """Read back a page this module wrote, or ``None`` if it did not.

    Deliberately strict: an id that fails :data:`_PAGE_ID_RE`, a missing
    ``title``, or no frontmatter at all yields ``None`` rather than a
    half-filled record. A page in the store that this cannot read is a page
    something else wrote, and the index says so by leaving it out.
    """
    frontmatter, body = split_frontmatter(text)
    if not frontmatter:
        return None
    fields: dict[str, str] = {}
    sources: list[str] = []
    in_sources = False
    for line in frontmatter.split("\n")[1:-1]:
        if line.startswith("  - ") and in_sources:
            sources.append(line[4:].strip())
            continue
        in_sources = False
        key, _, value = line.partition(":")
        if not _:
            continue
        key = key.strip()
        if key == "sources":
            in_sources = True
            continue
        fields[key] = value.strip()

    page_id = fields.get("id", "")
    title = fields.get("title", "")
    if not _PAGE_ID_RE.match(page_id) or not title:
        return None
    try:
        revisions = int(fields.get("revisions", "1"))
    except ValueError:
        return None
    return WikiPage(
        page_id=page_id,
        title=title,
        created=fields.get("created", ""),
        updated=fields.get("updated", ""),
        revisions=revisions,
        sources=tuple(sources),
        body=body,
    )


@dataclass(frozen=True)
class WikiStore:
    """The pattern-page store rooted at *wiki_dir*, audited into *data_root*.

    Two paths rather than one because they answer different questions: pages
    live under ``wiki_dir`` (the containment root), the op log lives with
    every other audit log under ``data_root/logs``. ``core`` takes both as
    arguments and never reads ``adapters.moltbook.config`` (ADR-0001).
    """

    wiki_dir: Path
    data_root: Path

    # ---------------------------------------------------------------- read

    @property
    def patterns_dir(self) -> Path:
        return self.wiki_dir / PATTERNS_DIRNAME

    def _containment_root(self) -> Path:
        """``patterns_dir``, resolved, for the containment comparison.

        ``_target_inside_data_root`` resolves the *target* and compares it to
        the root as given, so a root reached through a symlink (``/tmp`` on
        macOS, and any operator whose ``MOLTBOOK_HOME`` is a link) would make
        every legitimate page look like an escape. Resolving the root closes
        that without weakening the target side, which is where the attack is.
        """
        try:
            return self.patterns_dir.resolve()
        except OSError:
            return self.patterns_dir

    def _page_path(self, page_id: str) -> Path | None:
        """The file for *page_id*, or ``None`` when the id is not one of ours."""
        if not _PAGE_ID_RE.match(page_id):
            return None
        return self.patterns_dir / f"{page_id}.md"

    def read_page(self, page_id: str) -> WikiPage | None:
        path = self._page_path(page_id)
        if path is None or not path.is_file():
            return None
        if not _target_inside_data_root(path, self._containment_root()):
            return None
        try:
            return _parse_page(path.read_text(encoding="utf-8"))
        except OSError:
            return None

    def _next_page_id(self) -> str:
        """One past the highest id on disk. Ids are never reused.

        Derived from the directory rather than kept in a counter file, so a
        crash between the write and a counter update cannot hand the next
        page an id that is already taken. Costs one listdir per create,
        which at a page a day is not a cost.
        """
        highest = 0
        if self.patterns_dir.is_dir():
            for path in self.patterns_dir.glob("p-*.md"):
                if _PAGE_ID_RE.match(path.stem):
                    highest = max(highest, int(path.stem[2:]))
        return f"p-{highest + 1:04d}"

    # --------------------------------------------------------------- write

    def apply(self, op: WikiOp) -> WikiOpResult:
        """Validate, apply, and audit one op. Never raises on a bad op.

        An ``OSError`` from the write itself DOES propagate: a disk that
        refused the page is not the model making a bad proposal, and folding
        it into a refusal reason would let a broken store read as a
        well-behaved abstain for as long as the disk stays full.
        """
        result = self._apply(op)
        self._audit(op, result)
        return result

    def _apply(self, op: WikiOp) -> WikiOpResult:
        name = _op_name(op)
        sources = _clean_sources(op.sources)
        if not sources:
            return WikiOpResult(False, name, getattr(op, "page_id", None), "SOURCES_EMPTY")

        if isinstance(op, Create):
            return self._create(op, sources)

        path = self._page_path(op.page_id)
        if path is None or not path.is_file():
            return WikiOpResult(False, name, None, "PAGE_NOT_FOUND")
        if not _target_inside_data_root(path, self._containment_root()):
            return WikiOpResult(False, name, op.page_id, "PATH_ESCAPED")
        page = self.read_page(op.page_id)
        if page is None:
            return WikiOpResult(False, name, op.page_id, "PAGE_UNREADABLE")

        body, refusal = _patched_body(page.body, op)
        if refusal is not None:
            return WikiOpResult(False, name, op.page_id, refusal)
        assert body is not None

        merged = page.sources + tuple(s for s in sources if s not in page.sources)
        self._write(
            path,
            WikiPage(
                page_id=page.page_id,
                title=page.title,
                created=page.created,
                updated=now_iso(),
                revisions=page.revisions + 1,
                sources=merged,
                body=body,
            ),
        )
        return WikiOpResult(True, name, page.page_id)

    def _create(self, op: Create, sources: tuple[str, ...]) -> WikiOpResult:
        title = scrub_control(op.title, _TITLE_MAX_CHARS)
        if not title:
            return WikiOpResult(False, "create", None, "TITLE_EMPTY")
        if not op.body.strip():
            return WikiOpResult(False, "create", None, "TEXT_EMPTY")
        page_id = self._next_page_id()
        path = self.patterns_dir / f"{page_id}.md"
        stamp = now_iso()
        self._write(
            path,
            WikiPage(
                page_id=page_id,
                title=title,
                created=stamp,
                updated=stamp,
                revisions=1,
                sources=sources,
                body=op.body,
            ),
        )
        return WikiOpResult(True, "create", page_id)

    def _write(self, path: Path, page: WikiPage) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_restricted(path, _render_page(page))

    def _audit(self, op: WikiOp, result: WikiOpResult) -> None:
        """Append one row per op — applied or refused (ADR-0075).

        The body is NOT stored: the page is the canonical copy and this log
        would otherwise become a second, drifting one. The digest is enough
        to prove which text an op carried.

        Best-effort, like every other audit writer in ``core``: a log that
        cannot be written must not turn an applied op into a reported
        refusal, which is a worse lie than a missing row. The warning is the
        record that the row is missing.
        """
        record = {
            "ts": now_iso(timespec="seconds"),
            "op": result.op,
            "page_id": result.page_id,
            "sources": list(_clean_sources(op.sources)),
            "text_sha256": hashlib.sha256(_op_text(op).encode("utf-8")).hexdigest(),
            "applied": result.applied,
            "reason": result.reason,
        }
        try:
            append_jsonl_restricted(self.data_root / "logs" / WIKI_OPS_LOG_NAME, record)
        except OSError:
            logger.warning("wiki: failed to append the op audit row (op=%s)", result.op)


def _patched_body(
    body: str, op: Append | Replace | InsertAfter
) -> tuple[str | None, RefusalReason | None]:
    """``(new body, None)`` or ``(None, reason)``. Exactly one side is set.

    A pair rather than a ``str | RefusalReason`` union, which is what this
    was written as first: ``RefusalReason`` is a ``Literal`` OF strings, so
    ``isinstance(result, str)`` accepted every refusal as a body and every
    anchor check silently passed (caught by the tests that assert a refusal
    is refused). A union whose arms are not distinguishable at runtime is
    not a union.

    One function for the three patch verbs because they share every
    precondition except which text they look for, and the caller's job —
    turn the reason into a logged refusal — is the same in all three.
    """
    if isinstance(op, Append):
        if not op.text.strip():
            return None, "TEXT_EMPTY"
        return body.rstrip("\n") + "\n" + op.text, None
    if isinstance(op, Replace):
        refusal = _anchor_refusal(body, op.old)
        if refusal is not None:
            return None, refusal
        return body.replace(op.old, op.new, 1), None
    refusal = _anchor_refusal(body, op.anchor, single_line=True)
    if refusal is not None:
        return None, refusal
    if not op.text.strip():
        return None, "TEXT_EMPTY"
    return _insert_after_line(body, op.anchor, op.text), None


def _anchor_refusal(body: str, anchor: str, *, single_line: bool = False) -> RefusalReason | None:
    """``None`` when *anchor* occurs exactly once in *body*.

    An empty anchor counts as absent rather than as matching everywhere: it
    is the shape a model emits when it has nothing to point at.

    ``single_line`` is the insert_after caller: that verb splices after the
    *line* holding the anchor, so an anchor spanning a newline is unique as a
    substring and present on no line. Refused here, because the alternative is
    a no-op the store would report as applied.
    """
    if not anchor:
        return "ANCHOR_NOT_FOUND"
    if single_line and "\n" in anchor:
        return "ANCHOR_NOT_FOUND"
    hits = body.count(anchor)
    if hits == 0:
        return "ANCHOR_NOT_FOUND"
    if hits > 1:
        return "ANCHOR_AMBIGUOUS"
    return None


def _insert_after_line(body: str, anchor: str, text: str) -> str:
    """Put *text* on its own line after the line holding *anchor*.

    Line-granular on purpose. The anchor is unique in the body by the time
    this runs, but a mid-line splice would produce a page whose markdown
    structure depends on where inside a line the model happened to quote.
    """
    lines = body.split("\n")
    for index, line in enumerate(lines):
        if anchor in line:
            return "\n".join(lines[: index + 1] + [text] + lines[index + 1 :])
    return body  # unreachable: the caller checked the anchor first


def render_index(wiki_dir: Path) -> str:
    """The page index the Maintainer and Proposer are given (RFC-0017 D4/D5).

    ``id | title | first body line`` in id order — the three things a caller
    needs to decide which page to open, and nothing that would let it decide
    without opening one. Pages this module cannot parse are left out and the
    heading counts what it listed, so an unreadable page reads as absent
    rather than as a blank row.

    Never empty: a store with no pages returns the heading, because an empty
    string in a prompt is indistinguishable from a template that failed to
    render.
    """
    patterns_dir = wiki_dir / PATTERNS_DIRNAME
    rows: list[str] = []
    if patterns_dir.is_dir():
        for path in sorted(patterns_dir.glob("p-*.md")):
            if not _PAGE_ID_RE.match(path.stem):
                continue
            try:
                page = _parse_page(path.read_text(encoding="utf-8"))
            except OSError:
                page = None
            if page is None:
                continue
            first_line = next(
                (line for line in page.body.splitlines() if line.strip()),
                "",
            )
            snippet = scrub_control(first_line, _INDEX_SNIPPET_MAX_CHARS)
            rows.append(f"{page.page_id} | {page.title} | {snippet}")
    header = f"# Wiki index ({len(rows)} pages)"
    return "\n".join([header, ""] + rows) + "\n"
