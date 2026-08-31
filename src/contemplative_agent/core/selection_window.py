"""Shared base for the selection-log instruments: day files, windows, tokens.

The read side of ``skill-selection-*.jsonl`` has two readings with
different scopes -- :mod:`.selection_metrics` (windowed) and
:mod:`.never_selected_metrics` (whole history *and* windowed) -- and they
must not disagree about where a window is or which files are in it. One
implementation of each, here, rather than a copy per reading.

Nothing in this module writes, calls an LLM, or reads the catalog. It is
imported by both instruments and by neither the selector nor the agent.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TypeGuard

logger = logging.getLogger(__name__)


_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


# Non-judged verdicts that still injected the whole corpus, named apart from
# the ``fail_open_*`` prefix family. ``shadow_observe_skill_selection``
# returns ``None`` for these and ``None`` means "keep the full prompt";
# ``empty_catalog`` is deliberately absent, because an empty catalog has
# nothing to inject.
_FULL_CORPUS_VERDICTS = frozenset({"no_template"})


def _tokens(text: str, *, min_chars: int = 1) -> set[str]:
    """The one tokenizer behind every vocabulary the split compares:
    lower-cased, split on anything outside ``[a-z0-9]``."""
    return {t for t in _TOKEN_SPLIT_RE.split(text.lower()) if len(t) >= min_chars}


def _is_prose(name: str) -> bool:
    """Rule 1: whitespace or a slash means a clause, not a slug."""
    return " " in name or "/" in name


def _is_int(value: object) -> TypeGuard[int]:
    """``bool`` excluded on purpose: ``isinstance(True, int)`` is True, so a
    JSON ``true`` would otherwise be read as the number 1.

    A ``TypeGuard`` rather than a plain ``bool`` so the narrowing survives
    into the caller. The readers used to take their records straight from
    ``json.loads`` (``Any``, which type-checks against anything); once the
    shared walk started handing back ``dict[str, Any]``, every
    ``rec.get(...)`` became ``Any | None`` and five call sites of this
    predicate stopped type-checking — the annotation, not the calls, was
    what was wrong.
    """
    return isinstance(value, int) and not isinstance(value, bool)


@dataclass(frozen=True)
class _SelectionDayFile:
    """One daily selection log as the two readings see it.

    ``readable=False`` means the file exists and was skipped — a state a
    reading must be able to *count*, not merely survive, which is why this
    is a value rather than a ``continue``.
    """

    date_part: str
    file_date: date
    records: tuple[dict[str, Any], ...]
    # Lines that were neither blank, valid-JSON-object rows: unparseable
    # text and valid JSON that is not an object.
    malformed_rows: int
    readable: bool


def _iter_selection_days(
    log_dir: Path, keep: Callable[[date], bool] | None = None
) -> Iterator[_SelectionDayFile]:
    """Yield one :class:`_SelectionDayFile` per daily selection log.

    The one place the log's *file* grammar lives — which files are logs,
    how their day is spelled, and what makes a line a record — shared by
    the windowed reading and the ADR-0097 exit reading. It was two copies
    that had already drifted, and the drift ran toward a crash: a line
    decoding to a JSON array reached ``rec.get`` in the windowed reader and
    raised ``AttributeError`` out of an instrument whose whole contract is
    degrade-never-abort. Non-object lines are now skipped by both readers,
    like unparseable ones, and **counted** by both.

    Decode faults are ``ValueError`` as well as ``OSError``: a log file
    with one bad byte raises ``UnicodeDecodeError``, which is not an
    ``OSError``, and the callers that broke on exactly that gap are named
    in ``scripts/value_layer_due_check.py`` and the retired
    ``scripts/build_decision_packet.py``. Here it would have taken out a
    whole reading with no reason code at all.

    ``keep`` is the caller's window predicate, applied to the filename date
    **before the file is opened** so a seven-day reading does not pay to
    decode a year of history; each caller still owns its predicate and its
    tallies. ``None`` reads every day — what the whole-history reading needs.

    Day is taken from the filename, not from each record's ``ts``: the
    writer derives both from the same UTC clock, and the filename is the
    field the window is cut on, so a record with a damaged timestamp still
    lands on the right day.
    """
    if not log_dir.is_dir():
        return
    for path in sorted(log_dir.glob("skill-selection-*.jsonl")):
        date_part = path.stem.removeprefix("skill-selection-")
        try:
            file_date = datetime.strptime(date_part, "%Y-%m-%d").date()
        except ValueError:
            continue
        if keep is not None and not keep(file_date):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, ValueError):
            logger.warning("skill selection reading: unreadable %s", path.name)
            yield _SelectionDayFile(date_part, file_date, (), 0, readable=False)
            continue
        records: list[dict[str, Any]] = []
        malformed = 0
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                malformed += 1
                continue
            if isinstance(rec, dict):
                records.append(rec)
            else:
                malformed += 1
        yield _SelectionDayFile(date_part, file_date, tuple(records), malformed, readable=True)


def resolve_selection_window(
    days: int | None, since: date | None, until: date | None
) -> tuple[date, date | None, int]:
    """Return ``(cutoff, upper, calendar_days)``; ``upper`` is ``None`` in
    ``days`` mode. The one place the window rules live — the CLI calls it
    to turn a bad flag combination into a usage error.

    ``days`` mode keeps its historical meaning — every file dated on or
    after ``today - days`` — which is ``days + 1`` calendar days including
    today; that is the trap the explicit window exists to avoid, and the
    two modes are exclusive so a caller cannot get both by accident.
    """
    if since is None:
        if until is not None:
            raise ValueError("until requires since")
        if days is None:
            raise ValueError("one of days or since is required")
        return datetime.now(timezone.utc).date() - timedelta(days=days), None, days
    if days is not None:
        raise ValueError("days and since/until are exclusive")
    upper = until if until is not None else datetime.now(timezone.utc).date()
    if since > upper:
        raise ValueError("since must not be after until")
    return since, upper, (upper - since).days + 1
