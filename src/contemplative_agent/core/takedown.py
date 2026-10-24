"""Takedown suppression list (RFC P3-05.19): withdraw published text by identifier.

A request to remove or correct third-party text we republished is carried out
by listing an *identifier* (never the text) in ``config/takedown-suppressions.txt``
or the private ``$MOLTBOOK_HOME/takedown-suppressions.txt``. The report writer
(``core.report``) renders a listed post's Context as ``[withdrawn]`` and the
counterparty's name as ``[withdrawn]``; ``scripts/export-patterns-jsonl.py``
keeps listed patterns out of the public ``knowledge.json`` / ``patterns.jsonl``;
the sync step applies ``file:`` entries to the public tree. An empty list
changes nothing.

Fail loud: a line that is not ``post:|name:|pattern:|file:`` followed by a value
raises :class:`TakedownListError` with its line number. A withdrawal that
silently fails to apply would republish exactly what was asked to be removed.

The matching rules are mirrored, stdlib-only, in ``scripts/export-patterns-jsonl.py``
(which runs without the package); ``tests/test_takedown.py`` pins both to the
same fixtures.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

LIST_NAME = "takedown-suppressions.txt"
WITHDRAWN = "[withdrawn]"
_KINDS = ("post", "name", "pattern", "file")
_MIN_POST_PREFIX = 8


class TakedownListError(ValueError):
    """A suppression-list line the parser refuses (stop, never skip)."""


@dataclass(frozen=True)
class Suppressions:
    posts: frozenset[str] = frozenset()
    names: frozenset[str] = frozenset()  # casefolded
    patterns: frozenset[str] = frozenset()
    files: frozenset[str] = frozenset()

    def __bool__(self) -> bool:
        return bool(self.posts or self.names or self.patterns or self.files)

    def post_withdrawn(self, post_id: str) -> bool:
        """True when ``post_id`` begins with a listed id (full id or 8+ char prefix)."""
        return bool(post_id) and any(post_id.startswith(p) for p in self.posts)

    def name_withdrawn(self, name: str) -> bool:
        return bool(name) and name.casefold() in self.names

    def text_names_withdrawn(self, text: str) -> bool:
        """True when ``text`` mentions a listed display name as a whole word."""
        folded = text.casefold()
        return any(re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", folded) for n in self.names)

    def pattern_withdrawn(self, pattern_id: str) -> bool:
        return pattern_id in self.patterns

    def file_withdrawn(self, rel_path: str) -> bool:
        return rel_path in self.files

    def merge(self, other: Suppressions) -> Suppressions:
        return Suppressions(
            self.posts | other.posts,
            self.names | other.names,
            self.patterns | other.patterns,
            self.files | other.files,
        )


def parse(text: str, *, source: str = "<text>") -> Suppressions:
    """Parse the list format; raise :class:`TakedownListError` on any bad line."""
    buckets: dict[str, set[str]] = {k: set() for k in _KINDS}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, sep, value = line.partition(":")
        value = value.strip()
        if not sep or kind not in _KINDS or not value:
            raise TakedownListError(f"{source}:{lineno}: expected 'post|name|pattern|file:<value>'")
        if kind == "post" and len(value) < _MIN_POST_PREFIX:
            raise TakedownListError(
                f"{source}:{lineno}: a post id needs at least {_MIN_POST_PREFIX} characters"
            )
        if kind == "name":
            value = value.casefold()
        buckets[kind].add(value)
    return Suppressions(
        frozenset(buckets["post"]),
        frozenset(buckets["name"]),
        frozenset(buckets["pattern"]),
        frozenset(buckets["file"]),
    )


def load_suppressions(config_dir: Path | None = None, home: Path | None = None) -> Suppressions:
    """The public list plus the optional private one; a missing file is an empty list."""
    from .domain import DEFAULT_CONFIG_DIR

    config_dir = config_dir if config_dir is not None else DEFAULT_CONFIG_DIR
    if home is None:
        env = os.environ.get("MOLTBOOK_HOME")
        home = Path(env) if env else Path.home() / ".config" / "moltbook"
    merged = Suppressions()
    for path in (config_dir / LIST_NAME, home / LIST_NAME):
        if path.is_file():
            merged = merged.merge(parse(path.read_text(encoding="utf-8"), source=str(path)))
    return merged


# The private request ledger ($MOLTBOOK_HOME/takedown-requests.jsonl, RFC
# P3-05.14): one JSON object per request. Identifiers only -- the requester's
# words and any third-party text stay out of the row.
LEDGER_FIELDS = ("received", "surface", "target", "decision", "actioned", "basis")
LEDGER_DECISIONS = frozenset({"pending", "withdrawn", "corrected", "declined"})


def validate_ledger_row(row: dict) -> None:
    """Raise :class:`TakedownListError` unless ``row`` has exactly the ledger shape."""
    if set(row) != set(LEDGER_FIELDS):
        raise TakedownListError(f"ledger row keys must be exactly {LEDGER_FIELDS}")
    if row["decision"] not in LEDGER_DECISIONS:
        raise TakedownListError(f"ledger decision must be one of {sorted(LEDGER_DECISIONS)}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row["received"])):
        raise TakedownListError("ledger 'received' must be YYYY-MM-DD")
    if row["actioned"] is not None and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(row["actioned"])):
        raise TakedownListError("ledger 'actioned' must be YYYY-MM-DD or null")


def ledger_count_line(rows: list[dict], as_of: str) -> str:
    """The public Maintenance line: counts only, no identifiers."""
    for row in rows:
        validate_ledger_row(row)
    actioned = sum(1 for r in rows if r["actioned"] is not None)
    return f"requests received {len(rows)} / actioned {actioned} as of {as_of}"
