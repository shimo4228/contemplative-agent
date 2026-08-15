"""Shared Markdown-neutralizer for scripts/ LLM-facing reports."""

from __future__ import annotations


def md_safe(s: str) -> str:
    """Neutralize Markdown table/code-span breakers before LLM-facing output.

    A backtick would close a code span early; a pipe would misparse a table
    cell. Shared by state_invariant_check and log_anomaly_sweep, whose reports
    are both fed to an LLM downstream.
    """
    return s.replace("|", "\\|").replace("`", "'")


def printable(text: str) -> str:
    """Neutralise control characters in text that reaches a terminal or a human.

    ``str.isprintable()`` rather than a hand-written character class: it
    rejects Cc, Cf, Cs, Co, Cn, Zl, Zp and non-space Zs, a strict superset of
    the C0/DEL/C1/bidi/zero-width class spelled out in ``tasks.py::_CONTROL_RE``
    and ``claims.py::safe``. One owner, because a second spelling of the class
    is a second thing to keep in sync — and the classes have already drifted
    once (an earlier copy passed U+202E while claiming parity).

    Separate from :func:`md_safe`: this one is about what can *act* on a
    terminal or reorder a line, that one is about what breaks Markdown
    structure. Fields that are both rendered into a table and printed raw want
    both.
    """
    return "".join(ch if ch.isprintable() else " " for ch in text)
