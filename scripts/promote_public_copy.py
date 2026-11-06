#!/usr/bin/env python3
"""Build the public copy of one weekly document for ``--promote`` (P2-05.1).

stdlib only; run as ``python3 -I scripts/promote_public_copy.py`` by
``scripts/sync-research-data.sh --promote <name> --sha256 <hex>``. It writes the
public copy to ``--out``, a file outside the data repo; the sync script puts it
into the data repo only after every check has passed (ADR-0010 amendment
2026-10-31).

Read once. The document is opened with ``O_NOFOLLOW`` and checked as a regular
file on the same descriptor it is read from, and the sha256 of exactly those
bytes must equal ``--sha256``, the hash recorded when the owner approved the
document at weekly-gate Step 6d. Nothing reads the path again, so a file
swapped after the check cannot be what is published.

The public copy (owner's decision, S47 bounce 1):

- **Sample dropped.** The weekly report's Sample section quotes other agents'
  posts (``scripts/weekly_random_sample.py``); Moltbook's terms grant no right to
  republish them (ADR-0010 amendment 2026-10-31, D-P3-05-7 = A). Every H2
  section headed ``## Sample`` (or the collector's ``## Random Sample ...``) is
  dropped from its heading to the next H2 heading or the end of the file, and
  one line, ``SAMPLE_OMITTED``, stands in its place. A document without such a
  heading is published byte for byte.
- **Context labels refuse.** After the drop, any line still carrying a
  counterparty Context label, in any letter case (``Context (counterparty``,
  ``Context (untrusted``, a bold ``**Context:**`` / ``__Context__`` label, ...),
  refuses the promote: other agents' text sits somewhere code did not put it.
- **Takedown entries refuse.** ``name:`` and ``post:`` entries of the public and
  the private takedown list (ADR-0127) are matched against the public copy with
  the rules of ``contemplative_agent.core.takedown`` (a name as a whole word,
  case-folded; a post id by prefix agreement over at least 8 characters, applied
  to every id-shaped token). A hit refuses the promote. The rules are mirrored
  here, stdlib-only, and ``tests/test_sync_research_data_shell.py`` pins them to
  the core module. The dropped Sample is not matched: it is not published.

The home-path and secret-shape checks of the public copy are the sync script's
(the same ``grep`` patterns its daily gates use).

Exit status: 0 = the public copy is written and its sha256 is printed on
stdout; 1 = refused, with one ``REFUSED <REASON>: ...`` line on stderr that
names line numbers, never the document's text or a listed name; 2 = usage.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import stat
import sys
from dataclasses import dataclass
from pathlib import Path

SAMPLE_OMITTED = (
    "_Sample omitted from the public copy: it quotes other agents' posts "
    "(ADR-0010 amendment 2026-10-31)._"
)
_H2 = re.compile(r"^##[ \t]")
_SAMPLE_H2 = re.compile(r"^##[ \t]+(?:random[ \t]+)?sample\b", re.IGNORECASE)
_CONTEXT_LABELS = (
    # `Context (counterparty, untrusted)`, `context (Untrusted`, `Context (counterparty)`
    re.compile(r"context\s*\([^)\n]*\b(?:counterparty|untrusted)\b", re.IGNORECASE),
    # a bold label: `**Context:**`, `**Context**:`, `__Context:__`, `**Context (…):**`
    re.compile(r"(?:\*\*|__)\s*context\s*(?:\([^)\n]*\))?\s*:?\s*(?:\*\*|__)", re.IGNORECASE),
)
_MIN_POST_PREFIX = 8  # as core.takedown
_ID_TOKEN = re.compile(r"[0-9A-Za-z]+(?:-[0-9A-Za-z]+)*")


class Refused(Exception):
    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def read_once(path: Path, expected_sha256: str) -> bytes:
    """The bytes of *path*, refused unless it is a regular file holding *expected_sha256*."""
    # O_NONBLOCK: a FIFO swapped in after the shell's -f check opens at once and is
    # refused below, instead of blocking the open forever. No effect on a regular file.
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise Refused(
            "NOT_READABLE", f"cannot open the document ({exc.strerror}; a symlink is refused)"
        ) from None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise Refused("NOT_REGULAR", "the document is not a regular file")
        chunks = []
        while chunk := os.read(fd, 1 << 16):
            chunks.append(chunk)
    finally:
        os.close(fd)
    data = b"".join(chunks)
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected_sha256.lower():
        raise Refused(
            "SHA256_MISMATCH",
            f"the document has sha256 {actual}, not the {expected_sha256.lower()} the owner approved",
        )
    return data


def drop_sample(text: str) -> str | None:
    """*text* with every Sample H2 section replaced by ``SAMPLE_OMITTED``; None if it has none."""
    out: list[str] = []
    dropping = dropped = False
    for line in text.splitlines(keepends=True):
        body = line.rstrip("\r\n")
        eol = line[len(body) :] or "\n"
        if _H2.match(body):
            if _SAMPLE_H2.match(body):
                if not dropping:
                    out.append(SAMPLE_OMITTED + eol)
                dropping = dropped = True
                continue
            if dropping:
                out.append(eol)  # the blank line before the next section
                dropping = False
        if not dropping:
            out.append(line)
    return "".join(out) if dropped else None


def context_label_lines(text: str) -> list[int]:
    return [
        n
        for n, line in enumerate(text.splitlines(), start=1)
        if any(rx.search(line) for rx in _CONTEXT_LABELS)
    ]


@dataclass(frozen=True)
class Suppressions:
    names: frozenset[str]  # casefolded
    posts: frozenset[str]


def parse_suppressions(text: str, source: str = "<text>") -> Suppressions:
    """The ``name:`` / ``post:`` entries; a malformed line refuses, as in core.takedown."""
    names: set[str] = set()
    posts: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        kind, sep, value = line.partition(":")
        value = value.strip()
        if not sep or kind not in ("post", "name", "pattern", "file") or not value:
            raise Refused(
                "TAKEDOWN_LIST", f"{source}:{lineno}: expected 'post|name|pattern|file:<value>'"
            )
        if kind == "post" and len(value) < _MIN_POST_PREFIX:
            raise Refused(
                "TAKEDOWN_LIST", f"{source}:{lineno}: a post id needs at least 8 characters"
            )
        if kind == "name":
            names.add(value.casefold())
        elif kind == "post":
            posts.add(value)
    return Suppressions(frozenset(names), frozenset(posts))


def id_tokens(text: str) -> list[str]:
    """The id-shaped tokens of *text* (letters and digits, hyphen-joined)."""
    return _ID_TOKEN.findall(text)


def _name_hit(text: str, sup: Suppressions) -> bool:
    folded = text.casefold()
    return any(re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", folded) for n in sup.names)


def _post_hit(text: str, sup: Suppressions) -> bool:
    return any(
        len(tok) >= _MIN_POST_PREFIX
        and any(tok.startswith(p) or p.startswith(tok) for p in sup.posts)
        for tok in id_tokens(text)
    )


def takedown_hits(text: str, sup: Suppressions) -> bool:
    return _name_hit(text, sup) or _post_hit(text, sup)


def public_copy(data: bytes, sup: Suppressions) -> bytes:
    """The bytes to publish, or :class:`Refused`."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("NOT_UTF8", "the document is not UTF-8 text") from None
    dropped = drop_sample(text)
    if dropped is not None:
        text, data = dropped, dropped.encode("utf-8")
    lines = context_label_lines(text)
    if lines:
        raise Refused(
            "CONTEXT_LABEL",
            f"a counterparty Context label outside the Sample section, line(s) {lines[:20]} "
            "of the public copy",
        )
    for kind, hit in (("TAKEDOWN_NAME", _name_hit), ("TAKEDOWN_POST", _post_hit)):
        if hit(text, sup):
            where = [n for n, line in enumerate(text.splitlines(), start=1) if hit(line, sup)]
            raise Refused(
                kind,
                f"an entry of the takedown list appears in the public copy, line(s) {where[:20] or '?'}",
            )
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--suppressions",
        type=Path,
        action="append",
        default=[],
        help="a takedown list (ADR-0127); repeatable, a missing file is an empty list",
    )
    args = parser.parse_args(argv)
    try:
        sup = Suppressions(frozenset(), frozenset())
        for path in args.suppressions:
            if path.is_file():
                more = parse_suppressions(path.read_text(encoding="utf-8"), str(path))
                sup = Suppressions(sup.names | more.names, sup.posts | more.posts)
        out = public_copy(read_once(args.source, args.sha256), sup)
    except Refused as exc:
        print(f"REFUSED {exc.reason}: {exc.detail}", file=sys.stderr)
        return 1
    args.out.write_bytes(out)
    print(hashlib.sha256(out).hexdigest())
    return 0


if __name__ == "__main__":
    sys.exit(main())
