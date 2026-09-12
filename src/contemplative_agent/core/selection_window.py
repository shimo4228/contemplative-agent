"""Shared base for the selection-log instruments: day files, windows, walks.

The read side of ``skill-selection-*.jsonl`` has two readings with
different scopes -- :mod:`.selection_metrics` (windowed) and
:mod:`.never_selected_metrics` (whole history *and* windowed) -- and they
must not disagree about where a window is or which files are in it. One
implementation of each, here, rather than a copy per reading.

The whole-history walk (:func:`_scan_selection_history`) lives here for the
same reason: two instruments read it — the ADR-0097 exit reading and the
ADR-0105 confusion reading — and it was the second one reaching across a
module boundary for the first one's private name.

Nothing in this module writes, calls an LLM, or reads the catalog. It is
imported by the instruments and by the selector (for the record-kind names
and the name cap), never the other way round.
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

from ._io import scrub_control

logger = logging.getLogger(__name__)


_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


# Length bound for a skill name, wherever one is read (security review
# 2026-07-10). Names are kebab-case ASCII by insight convention. It lives
# beside the log's grammar because the log is the untrusted side: a
# rejected name arrives from the model and is capped before it reaches any
# O(n*m) matcher. ``skill_selection`` applies the same cap to catalog
# fields, through this name rather than a second 80.
_NAME_MAX_CHARS = 80


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


# The selection log holds more than selections since RFC-0028: a ``publish``
# record links a selection to the comment it became. Records written before
# that RFC carry no ``kind`` at all, so absence *is* "selection" — which is
# what keeps the longitudinal readings (verdict mix, per-day record counts)
# one series across the change instead of gaining an "unknown" bucket on the
# day the publish records started.
SELECTION_RECORD_KIND = "selection"


# The publish record (RFC-0028): which comment a selection's generation became.
# Named here beside its sibling because this module is where the log's record
# grammar lives; the writer is ``skill_selection.record_publish_outcome``.
PUBLISH_RECORD_KIND = "publish"


def _iter_selection_days(
    log_dir: Path,
    keep: Callable[[date], bool] | None = None,
    *,
    kind: str | None = SELECTION_RECORD_KIND,
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

    ``kind`` filters the records by their ``kind`` field, defaulting to the
    selection records the two instruments read; ``kind=None`` yields every
    record (what the RFC-0028 join needs, since it reads both families).
    A record with no ``kind`` is a selection record — see
    :data:`SELECTION_RECORD_KIND`. Filtered-out rows are not malformed and
    are not counted as such.
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
        records, malformed = _parse_day_lines(lines, kind)
        yield _SelectionDayFile(date_part, file_date, records, malformed, readable=True)


def _parse_day_lines(lines: list[str], kind: str | None) -> tuple[tuple[dict[str, Any], ...], int]:
    """(records of the wanted kind, malformed-row count) for one day's lines."""
    records: list[dict[str, Any]] = []
    malformed = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            malformed += 1
            continue
        if not isinstance(rec, dict):
            malformed += 1
            continue
        if kind is not None and rec.get("kind", SELECTION_RECORD_KIND) != kind:
            continue
        records.append(rec)
    return tuple(records), malformed


@dataclass(frozen=True)
class SelectionWindow:
    """The resolved window, carrying the rules that follow from it.

    :func:`resolve_selection_window` settles where the window is; the two
    rules a reader then needs — whether a day is inside it, and how its
    bounds are spelled in a reading's ``window_since`` / ``window_until``
    fields — used to be rewritten at each reader, in three places and two
    phrasings that happened to agree. They agree here by construction.

    ``upper is None`` is ``days`` mode, and it is what both rules branch on:
    an open-ended window contains every day on or after ``cutoff``, and it
    publishes no bounds (the reading prints "the last N days" instead).
    """

    cutoff: date
    upper: date | None
    days: int

    def contains(self, day: date) -> bool:
        """Is ``day`` inside the window? The one containment rule, shared by
        the windowed reading and the whole-history walk's window scope."""
        return day >= self.cutoff and (self.upper is None or day <= self.upper)

    @property
    def since_text(self) -> str | None:
        """``window_since`` as the readings publish it: the lower bound in
        explicit-window mode, ``None`` in ``days`` mode."""
        return self.cutoff.isoformat() if self.upper is not None else None

    @property
    def until_text(self) -> str | None:
        """``window_until`` as the readings publish it; see
        :attr:`since_text`."""
        return self.upper.isoformat() if self.upper is not None else None


def resolve_selection_window(
    days: int | None, since: date | None, until: date | None
) -> SelectionWindow:
    """Return the resolved :class:`SelectionWindow`; ``upper`` is ``None`` in
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
        return SelectionWindow(datetime.now(timezone.utc).date() - timedelta(days=days), None, days)
    if days is not None:
        raise ValueError("days and since/until are exclusive")
    upper = until if until is not None else datetime.now(timezone.utc).date()
    if since > upper:
        raise ValueError("since must not be after until")
    return SelectionWindow(since, upper, (upper - since).days + 1)


@dataclass(frozen=True)
class _SelectionHistoryTally:
    """What one pass over the log knows before the catalog is resolved.

    Module-private and never crossing the process boundary: it is the raw
    material :class:`NeverSelectedReading` is computed from, carried in one
    value so the walk and the populations can be read apart. Its two scopes
    are the reading's own — ``history_*`` is whole-history, ``window_*`` is
    the trailing window — and the per-name maps carry both.
    """

    exposure_history: dict[str, int]
    exposure_window: dict[str, int]
    selected_history: dict[str, int]
    selected_window: dict[str, int]
    # Rejected-name emissions in the WINDOW only, per distinct name. Tallied
    # in this pass rather than in a second walk because the ADR-0105
    # confusion reading and this one are two readings of the same log and
    # the repo pays for one decode of it (~3.7k records over ~44 files at
    # the 2026-08 volume). Window-only on purpose: the confusion claim is
    # about how the reader behaves NOW, and a whole-history tally would
    # charge a skill for variants emitted against a catalog it no longer
    # shares. Untouched by this module's own populations.
    rejected_window: dict[str, int]
    last_selected: dict[str, str]
    days_read: list[str]
    history_files: int
    history_records: int
    history_judged: int
    history_fail_open: int
    unreadable_files: int
    malformed_rows: int
    window_records: int
    window_judged: int
    window_fail_open: int
    full_skill_tokens: int


def _injects_full_corpus(verdict: str) -> bool:
    """Non-judged verdicts that still put the whole corpus in the prompt —
    every ``fail_open_*`` and ``no_template``, the population the neutrality
    caveat counts. ``empty_catalog`` is out: there was no corpus to inject."""
    return verdict in _FULL_CORPUS_VERDICTS or verdict.startswith("fail_open")


def _tally_offered(
    rec: dict[str, Any],
    *,
    in_window: bool,
    exposure_history: dict[str, int],
    exposure_window: dict[str, int],
) -> None:
    """Count one judged record's ``catalog_names`` into both scopes."""
    names = rec.get("catalog_names")
    if not isinstance(names, list):
        return
    for name in names:
        if isinstance(name, str):
            exposure_history[name] = exposure_history.get(name, 0) + 1
            if in_window:
                exposure_window[name] = exposure_window.get(name, 0) + 1


def _tally_selected(
    rec: dict[str, Any],
    *,
    in_window: bool,
    date_part: str,
    selected_history: dict[str, int],
    selected_window: dict[str, int],
    last_selected: dict[str, str],
) -> None:
    """Count one judged record's ``selected`` into both scopes and advance
    the last-selected day.

    Filename day, like the window cut: the writer derives both from the same
    UTC clock, so a record with a damaged ``ts`` still lands on the right day.
    """
    selected = rec.get("selected")
    if not isinstance(selected, list):
        return
    for name in selected:
        if not isinstance(name, str):
            continue
        selected_history[name] = selected_history.get(name, 0) + 1
        if in_window:
            selected_window[name] = selected_window.get(name, 0) + 1
        if date_part > last_selected.get(name, ""):
            last_selected[name] = date_part


def _tally_rejected(
    rec: dict[str, Any],
    *,
    in_window: bool,
    rejected_window: dict[str, int],
) -> None:
    """Count one judged record's ``rejected_names`` by name, window only.

    The ``in_window`` guard lives here rather than at the call site so the
    walk keeps one statement per tally (the shape ruff's complexity gate
    measures, and the shape that makes the walk readable).

    Emissions, not records: a record naming two variants of one skill
    charges both, which is the count ``RejectedNameTally.count`` and
    ``scripts/skillsel_reading.py`` already publish.
    """
    names = rec.get("rejected_names")
    if not in_window or not isinstance(names, list):
        return
    for name in names:
        if not isinstance(name, str):
            continue
        # Same normalisation as the sibling reading's rejected-name tally
        # (``selection_metrics._tally_rejected_names``), not a courtesy: the
        # log is persisted untrusted data, and without the cap an unbounded
        # name reaches ``nearest_catalog_name``'s O(n*m) matcher once per
        # catalog entry. Two tallies that scrubbed differently would also make
        # the "one walk, one answer" claim false for exactly the rows where
        # it matters.
        scrubbed = scrub_control(name, _NAME_MAX_CHARS)
        if not scrubbed:
            continue
        rejected_window[scrubbed] = rejected_window.get(scrubbed, 0) + 1


def _scan_selection_history(log_dir: Path, window: SelectionWindow) -> _SelectionHistoryTally:
    """One pass over every ``skill-selection-*.jsonl``, tallying both scopes.

    Four fields per record and no per-name similarity scan (no ``difflib``,
    no mechanism split), so the weekly cost is a JSON decode of the log —
    ~3.7k records over ~44 files at the 2026-08 volume.
    """
    # Tallied for every catalogued name seen in the log, not just the ones
    # that turn out never-selected: which names those are is only known after
    # the whole history has been read, and the current catalog is resolved
    # later still.
    exposure_history: dict[str, int] = {}
    exposure_window: dict[str, int] = {}
    selected_history: dict[str, int] = {}
    selected_window: dict[str, int] = {}
    rejected_window: dict[str, int] = {}
    last_selected: dict[str, str] = {}
    history_files = 0
    history_records = 0
    history_judged = 0
    history_fail_open = 0
    unreadable_files = 0
    malformed_rows = 0
    window_records = 0
    window_judged = 0
    window_fail_open = 0
    full_skill_tokens = 0
    days_read: list[str] = []

    for day_file in _iter_selection_days(log_dir):
        date_part = day_file.date_part
        if not day_file.readable:
            # Counted, not merely survived. A day this reading could not open
            # is a day whose selections it cannot see, and the strict list is
            # a list of skills a human is about to remove — so the evidence
            # loss is named here and withholds that list below.
            unreadable_files += 1
            continue
        history_files += 1
        malformed_rows += day_file.malformed_rows
        days_read.append(date_part)
        in_window = window.contains(day_file.file_date)
        for rec in day_file.records:
            history_records += 1
            if in_window:
                window_records += 1
            verdict = str(rec.get("verdict", "unknown"))
            if verdict != "judged":
                if _injects_full_corpus(verdict):
                    # Two scopes, because the two skill populations have two
                    # scopes: the whole-history count is the one that belongs
                    # beside the strict list, and it is NOT recoverable by
                    # subtraction from the window's.
                    history_fail_open += 1
                    if in_window:
                        window_fail_open += 1
                continue
            # Judged-only below, for the reason the windowed reader's cut
            # records: every number here is a count over judged records,
            # and a name offered to a selector that never answered was
            # not refused.
            history_judged += 1
            if in_window:
                window_judged += 1
            _tally_offered(
                rec,
                in_window=in_window,
                exposure_history=exposure_history,
                exposure_window=exposure_window,
            )
            _tally_selected(
                rec,
                in_window=in_window,
                date_part=date_part,
                selected_history=selected_history,
                selected_window=selected_window,
                last_selected=last_selected,
            )
            _tally_rejected(rec, in_window=in_window, rejected_window=rejected_window)
            full = rec.get("full_skill_tokens")
            # ``_is_int``, not ``isinstance(full, int)``: ``True`` is an
            # int in Python, so a record carrying ``"full_skill_tokens":
            # true`` would read as a 1-token corpus and print "fits
            # within NUM_CTX" — the exact claim the abstain code exists
            # to withhold. The sibling reader takes the same field
            # through the same helper.
            if _is_int(full) and full > 0:
                # Last writer wins: files are walked in date order, so
                # this ends as the corpus the most recent judged action
                # saw. Recomputing it from today's catalog would answer a
                # different question than the caveat asks.
                full_skill_tokens = full

    return _SelectionHistoryTally(
        exposure_history=exposure_history,
        exposure_window=exposure_window,
        selected_history=selected_history,
        selected_window=selected_window,
        rejected_window=rejected_window,
        last_selected=last_selected,
        days_read=days_read,
        history_files=history_files,
        history_records=history_records,
        history_judged=history_judged,
        history_fail_open=history_fail_open,
        unreadable_files=unreadable_files,
        malformed_rows=malformed_rows,
        window_records=window_records,
        window_judged=window_judged,
        window_fail_open=window_fail_open,
        full_skill_tokens=full_skill_tokens,
    )


def log_health_reasons(
    tally: _SelectionHistoryTally, *, catalog_available: bool, prefix: str
) -> set[str]:
    """The five abstain codes that are about the LOG, not about the reading.

    Both exit readings (ADR-0097 D5, ADR-0105) derive the same five from the
    same walk and differ only in the prefix they spell them with — so the
    conditions live once, here, beside the walk that produces the evidence
    for them. Each reading keeps its own codes (``BELOW_FLOOR``,
    ``NO_PAIRS``, ``VALUE_LAYER_*``) and its own declared vocabulary, which
    is what :func:`resolve_reasons` filters against.

    ``LOG_PARTIAL`` and ``LOG_UNREADABLE`` are deliberately not exclusive: a
    lost DAY raises both, because it is degraded evidence *and* the sharper
    unbounded kind that withholds a population. A lost ROW raises only the
    first.
    """
    flagged: set[str] = set()
    if not catalog_available:
        # No ruler: nothing can be said of names that could not be
        # enumerated. Every population stays empty rather than reading as
        # "nothing to archive".
        flagged.add(f"{prefix}_NO_CATALOG")
    if not tally.history_judged:
        flagged.add(f"{prefix}_NO_HISTORY")
    if tally.unreadable_files or tally.malformed_rows:
        flagged.add(f"{prefix}_LOG_PARTIAL")
    if tally.unreadable_files:
        flagged.add(f"{prefix}_LOG_UNREADABLE")
    if not tally.window_records:
        # The window is empty while the history is not: every window-scoped
        # figure reads 0, including the fail-open count a reader would
        # otherwise take as "no fail-open ever happened". An agent that was
        # down for the requested fortnight produces exactly this.
        flagged.add(f"{prefix}_EMPTY_WINDOW")
    return flagged


def resolve_reasons(declared: tuple[str, ...], flagged: set[str]) -> tuple[str, ...]:
    """``flagged`` in ``declared`` order.

    Declared order, not emit order: the weekly packet renders these lists and
    a stable order is what makes week-over-week diffs readable. Filtering
    through the vocabulary also means an undeclared code cannot leave the
    reading that raised it.
    """
    return tuple(c for c in declared if c in flagged)
