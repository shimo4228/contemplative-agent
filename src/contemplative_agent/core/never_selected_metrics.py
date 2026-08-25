"""Instrument: the never-selected exposure reading for the store's exit (ADR-0097 D5).

Read-only, two scopes in one pass over the whole selection log: the strict
population (never selected in *any* recorded window) and the dormant one
(not selected inside a trailing window). Feeds the weekly packet's
retirement candidates; the floor is a listing criterion, never an automatic
retire.

Windowing is :mod:`.selection_window`'s, shared with
:mod:`.selection_metrics`, so the two readings of one log cannot disagree
about where the window is.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .llm import (
    NUM_CTX,
)
from .selection_window import (
    _FULL_CORPUS_VERDICTS,
    _is_int,
    _iter_selection_days,
    resolve_selection_window,
)
from .skill_selection import load_skill_catalog

logger = logging.getLogger(__name__)


# ADR-0097 D5. Judged exposures a skill must have accumulated over the WHOLE
# selection history before "never selected" is worth listing as an archive
# candidate. 600 is the smallest round number above the observed maximum
# first-selection latency: among skills that were eventually selected, the
# judged exposures before the first selection were p50 7 / p90 99 / p95 302 /
# max 569 (measured 2026-08-22 over `logs/skill-selection-*.jsonl`).
#
# It is NOT a retirement threshold and nothing downstream may treat it as one
# (`core/stocktake.py`: "never a numeric auto-retire threshold"). It selects
# what gets LISTED for a human to decide; the decision, the reason and the
# archive move stay at the Saturday gate. Its own expiry is pre-registered in
# ADR-0097 Review-when: a skill archived as strict never-selected being
# restored more than once means the floor is too low and must be re-read from
# the first-selection latency distribution.
NEVER_SELECTED_EXPOSURE_FLOOR = 600


# ADR-0097 D5's dormant cut: "zero selections in the trailing 14 days". A
# property of the decision, not of whatever window a caller happened to ask
# the surrounding report for — `report --days 7` would otherwise silently
# halve it and call a week's silence dormancy.
NEVER_SELECTED_DORMANT_WINDOW_DAYS = 14


@dataclass(frozen=True)
class NeverSelectedSkill:
    """One catalogued skill the selector did not choose, with the evidence a
    human needs to decide whether that means anything.

    Exposure — how often the name was actually *offered* — is the whole
    point. Without it a skill adopted yesterday is indistinguishable from one
    that has been offered two thousand times and refused, and the first is
    not evidence of anything (ADR-0097 D5).
    """

    name: str
    # Judged records over the WHOLE history that carried this name in
    # ``catalog_names``. The floor is applied to this number.
    judged_exposure: int
    # Same, restricted to the trailing window — the number that makes a
    # dormant row readable ("offered 606 times this fortnight, chosen 0").
    # Read only for dormant rows; carried on all three populations so one row
    # shape crosses the process boundary into the packet's JSON.
    window_exposure: int
    # Filename day of the last judged record that selected this name, or ""
    # when it never was. **`""` is not data**: it is `""` by construction for
    # every strict and every below-floor row (that is what those populations
    # mean), so only a dormant row's value carries information — there it is
    # the last-circulation date CREW library weeding treats as a filter the
    # librarian must still review. The field stays on all three for the same
    # uniform-shape reason as `window_exposure`.
    last_selected: str


@dataclass(frozen=True)
class NeverSelectedReading:
    """Whole-history exit reading over the selection log (ADR-0097 D5).

    Read-only. It lists; it never archives, ranks, gates or thresholds — the
    floor selects what gets listed and the Saturday gate decides
    (``read-only-instruments``: the instrument reports, the human decides).

    Two populations, kept apart because conflating them is the error this
    reading exists to avoid:

    - ``strict`` — zero selections across the whole selection history, at or
      above ``exposure_floor`` judged exposures. Only these are archive
      candidates: a skill never selected under two-pass injection was never
      injected, so removing it cannot change judged behaviour.
    - ``dormant`` — zero selections in the trailing window but selected at
      some point before. A reading only. Archiving one of these WOULD change
      judged behaviour, which is exactly why it is a separate field and not a
      longer version of the first list.

    ``below_floor`` is the third state and is not a population to act on:
    never selected, but not yet offered often enough for that to mean
    anything (ADR-0097 D8 — "a newly adopted skill becomes a never-selected
    candidate only after 600 judged exposures"). It is carried so a name
    missing from ``strict`` reads as "not yet measured" rather than "was
    selected".

    The neutrality caveat travels in the same object as the populations,
    because behaviour-neutrality holds for *judged* actions only: the
    fail-open path injects the full corpus. ``window_fail_open`` and
    ``history_full_skill_tokens`` against ``num_ctx`` are what let a reader check
    that instead of taking it on faith (the Codex challenge recorded in
    ADR-0097's Context).
    """

    strict: tuple[NeverSelectedSkill, ...]
    dormant: tuple[NeverSelectedSkill, ...]
    below_floor: tuple[NeverSelectedSkill, ...]
    exposure_floor: int
    # History span actually read, so "zero selections in the whole history"
    # can be weighed against how much history there was. ``history_files``
    # counts only the days this reading could open — the ones it could not
    # are ``unreadable_files`` below, and the difference is the whole point:
    # a reading that silently narrowed its own evidence is how a skill the
    # selector chose last month becomes an archive candidate.
    history_files: int
    history_records: int
    history_judged: int
    # Same population as ``window_fail_open`` over the whole history, kept
    # beside it because the two skill populations have two scopes and this
    # one belongs to ``strict``: a candidate never *judged*-selected may
    # still have been injected by every full-corpus action in the log's
    # life, and that count is not recoverable by subtraction from a
    # windowed one.
    history_fail_open: int
    history_first_day: str
    history_last_day: str
    # Evidence this reading could not see. A whole day that would not open
    # (``unreadable_files``) withholds the strict list outright; individual
    # lines that would not decode, or decoded to something other than an
    # object (``malformed_rows``), are bounded loss and are reported beside
    # the populations instead. Both raise ``NEVER_SELECTED_LOG_PARTIAL``.
    unreadable_files: int
    malformed_rows: int
    # Trailing window — the dormant cut and the neutrality caveat. Cut by
    # ``resolve_selection_window``, the same seam ``read_skill_selection_log``
    # uses, so the two readings of one log agree about where the window is;
    # ``window_since`` / ``window_until`` mirror that reading's fields and are
    # ``None`` in ``days`` mode.
    window_days: int
    window_since: str | None
    window_until: str | None
    window_records: int
    window_judged: int
    # Window records that injected the FULL corpus instead of a selection:
    # every ``fail_open_*`` **and** ``no_template``. The producer settles
    # what belongs here — ``shadow_observe_skill_selection`` returns ``None``
    # for both, and ``None`` means "keep the full prompt"
    # (``adapters/moltbook/llm_functions``). ``empty_catalog`` is the one
    # non-judged verdict left out, because there was no corpus to inject.
    #
    # This is the same population ``SkillSelectionDay.fell_back`` describes,
    # minus ``empty_catalog``; an earlier version of this field excluded
    # ``no_template`` too and so would have printed "fail-open: 0 of 700"
    # for a week in which a missing selection template sent the whole corpus
    # into all 700 actions — the exact claim this caveat exists to let a
    # reader check. Still not ``records - judged``, so the residual stays
    # visible rather than being absorbed silently.
    window_fail_open: int
    # Latest ``full_skill_tokens`` in the WHOLE history (baked in at record
    # time by the writer, so it is the corpus as the selector saw it), and
    # the context window it is compared against. 0 when no record carried a
    # usable value — see ``NEVER_SELECTED_FULL_TOKENS_UNKNOWN``.
    #
    # Whole-history on purpose, and named so: it is evidence for the
    # ``strict`` population, which is itself whole-history, and it is
    # rendered only beside that list. ``since``/``until`` move the dormant
    # cut and the window figures; they do not narrow the strict population,
    # so clamping this to the window would pair a whole-history list with
    # window-scoped evidence — the mismatch this rename exists to end.
    # ``dormant`` makes no neutrality claim and gets no corpus figure.
    history_full_skill_tokens: int
    num_ctx: int
    # Size of the catalog the populations were computed against — the
    # denominator a reader needs for "N of M skills". ``catalog_available``
    # is ``bool(catalog_size)`` and is carried anyway: it is the field the
    # renderers branch on, named as the sibling ``SkillSelectionReading``
    # names it, so the two readings of one log read alike. The third
    # encoding, ``NEVER_SELECTED_NO_CATALOG``, is the no-silent-fallback
    # contract and is what a consumer that cannot see this object gets.
    catalog_size: int
    catalog_available: bool
    # ADR-0075: anything not computable abstains with a code rather than
    # guessing. Closed vocabulary in ``NEVER_SELECTED_REASONS``.
    reasons: tuple[str, ...]


# Closed reason vocabulary for ``NeverSelectedReading.reasons``. The weekly
# packet re-renders these into its header, so they are named once here rather
# than spelled at each emit site.
#
# ``NEVER_SELECTED_BELOW_FLOOR`` is the one that means a guard WORKED: skills
# were never selected but none had been offered often enough to be worth
# listing, so nothing is proposed. It recurs by design in any week following
# an adoption, and the packet's recurrence trigger must treat it as designed.
NEVER_SELECTED_REASONS = (
    "NEVER_SELECTED_NO_CATALOG",
    "NEVER_SELECTED_NO_HISTORY",
    # The reading is degraded: something it should have read, it did not.
    # Raised for a lost day and for a lost row alike, so one code answers
    # "is this week's exit reading complete?".
    "NEVER_SELECTED_LOG_PARTIAL",
    # ...and the sharper one, raised only for a lost DAY. The two are kept
    # apart because the withholding decision turns on exactly this
    # difference: a dropped row is bounded evidence loss (one action out of
    # thousands), a dropped day is not — the single record that ever
    # selected a name may be the whole of it. Folding them would let two
    # corrupt lines in a 3,700-record log withhold the list every week,
    # which is how a safety guard becomes the reason the guard is removed.
    "NEVER_SELECTED_LOG_UNREADABLE",
    "NEVER_SELECTED_EMPTY_WINDOW",
    "NEVER_SELECTED_BELOW_FLOOR",
    "NEVER_SELECTED_FULL_TOKENS_UNKNOWN",
)


# Reasons under which a population is not a reading but the absence of one.
# A renderer must say "withheld" for these, never "none": the difference
# between "nothing to archive" and "this reading cannot tell you" is the
# entire safety margin of the exit.
NEVER_SELECTED_STRICT_WITHHELD = frozenset(
    {
        "NEVER_SELECTED_NO_CATALOG",
        "NEVER_SELECTED_NO_HISTORY",
        "NEVER_SELECTED_LOG_UNREADABLE",
    }
)


NEVER_SELECTED_DORMANT_WITHHELD = frozenset(
    {"NEVER_SELECTED_NO_CATALOG", "NEVER_SELECTED_EMPTY_WINDOW"}
)


def read_never_selected(
    log_dir: Path,
    *,
    days: int | None = None,
    since: date | None = None,
    until: date | None = None,
    skills_dir: Path | None,
    exposure_floor: int = NEVER_SELECTED_EXPOSURE_FLOOR,
) -> NeverSelectedReading:
    """Walk the whole selection history for the ADR-0097 D5 exit reading.

    **Two scopes in one pass, on purpose.** The strict population is defined
    over the *whole* selection history — a window cannot express it, because
    a skill selected once in March and never since is dormant rather than an
    archive candidate, and only a full walk tells those apart. The dormant
    population and the neutrality caveat are defined over a *trailing
    window*. Which scope each field is measured under is in its comment on
    :class:`NeverSelectedReading`: everything named ``history_*`` and the
    ``judged_exposure`` the floor tests are whole-history; everything named
    ``window_*``, plus ``dormant`` and ``NeverSelectedSkill.window_exposure``,
    are windowed.

    There is still only **one** windowing implementation in this module:
    ``days`` / ``since`` / ``until`` mean exactly what they mean on
    :func:`read_skill_selection_log` and are resolved by the same
    :func:`resolve_selection_window`, so the two readings of one log cannot
    disagree about where the window is. Passing ``since`` / ``until`` is also
    how a caller gets a reading that replays identically offline (ADR-0091's
    shape); ``days`` mode reads the UTC clock, as it does for the sibling.

    This is a separate function rather than another mode of
    :func:`read_skill_selection_log` because a single call would have to
    answer both scopes at once: ``dormant`` needs the windowed and the
    whole-history view of the same name simultaneously.

    One pass over every ``skill-selection-*.jsonl``, four fields per record
    and no per-name similarity scan (no ``difflib``, no mechanism split), so
    the weekly cost is a JSON decode of the log — ~3.7k records over ~44
    files at the 2026-08 volume.
    """
    cutoff, upper, window_days = resolve_selection_window(days, since, until)

    # Tallied for every catalogued name seen in the log, not just the ones
    # that turn out never-selected: which names those are is only known after
    # the whole history has been read, and the current catalog is resolved
    # later still.
    exposure_history: dict[str, int] = {}
    exposure_window: dict[str, int] = {}
    selected_history: dict[str, int] = {}
    selected_window: dict[str, int] = {}
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
        in_window = day_file.file_date >= cutoff and (upper is None or day_file.file_date <= upper)
        for rec in day_file.records:
            history_records += 1
            if in_window:
                window_records += 1
            verdict = str(rec.get("verdict", "unknown"))
            if verdict != "judged":
                if verdict in _FULL_CORPUS_VERDICTS or verdict.startswith("fail_open"):
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
            names = rec.get("catalog_names")
            if isinstance(names, list):
                for name in names:
                    if isinstance(name, str):
                        exposure_history[name] = exposure_history.get(name, 0) + 1
                        if in_window:
                            exposure_window[name] = exposure_window.get(name, 0) + 1
            selected = rec.get("selected")
            if isinstance(selected, list):
                for name in selected:
                    if not isinstance(name, str):
                        continue
                    selected_history[name] = selected_history.get(name, 0) + 1
                    if in_window:
                        selected_window[name] = selected_window.get(name, 0) + 1
                    # Filename day, like the window cut: the writer
                    # derives both from the same UTC clock, so a record
                    # with a damaged ``ts`` still lands on the right day.
                    if date_part > last_selected.get(name, ""):
                        last_selected[name] = date_part
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

    catalog_names = [e.name for e in load_skill_catalog(skills_dir)]
    flagged: set[str] = set()

    def _entry(name: str) -> NeverSelectedSkill:
        return NeverSelectedSkill(
            name=name,
            judged_exposure=exposure_history.get(name, 0),
            window_exposure=exposure_window.get(name, 0),
            last_selected=last_selected.get(name, ""),
        )

    strict: list[NeverSelectedSkill] = []
    below_floor: list[NeverSelectedSkill] = []
    dormant: list[NeverSelectedSkill] = []
    for name in catalog_names:
        if name in selected_history:
            # Selected at some point. Dormant only if the trailing window
            # also offered it and it went unchosen there — a name absent from
            # the window's catalog entirely was not refused, it was not on
            # the table (the 2026-07-12 breaker-open misreading, in the
            # windowed reader's own words).
            if name not in selected_window and exposure_window.get(name, 0) > 0:
                dormant.append(_entry(name))
            continue
        entry = _entry(name)
        if entry.judged_exposure >= exposure_floor:
            strict.append(entry)
        else:
            below_floor.append(entry)

    if not catalog_names:
        # No ruler: "never selected" cannot be said of names that could not be
        # enumerated. Every population stays empty rather than reading as
        # "nothing to archive".
        flagged.add("NEVER_SELECTED_NO_CATALOG")
    if not history_judged:
        flagged.add("NEVER_SELECTED_NO_HISTORY")
    if unreadable_files or malformed_rows:
        flagged.add("NEVER_SELECTED_LOG_PARTIAL")
    if unreadable_files:
        flagged.add("NEVER_SELECTED_LOG_UNREADABLE")
    if not window_records:
        # The window is empty while the history is not: every window-scoped
        # figure below reads 0, including the fail-open count a reader would
        # otherwise take as "no fail-open ever happened". An agent that was
        # down for the requested fortnight produces exactly this.
        flagged.add("NEVER_SELECTED_EMPTY_WINDOW")
    if below_floor and not strict:
        flagged.add("NEVER_SELECTED_BELOW_FLOOR")
    if not full_skill_tokens:
        # Without it the neutrality caveat is half a sentence: the reader
        # cannot check whether a fail-open would re-inject the corpus or
        # abstain for exceeding the context window.
        flagged.add("NEVER_SELECTED_FULL_TOKENS_UNKNOWN")

    # Declared order, not emit order: the weekly packet renders this list and
    # a stable order is what makes week-over-week diffs readable. Filtering
    # through the vocabulary also means an undeclared code cannot leave this
    # function.
    reasons = tuple(c for c in NEVER_SELECTED_REASONS if c in flagged)
    if NEVER_SELECTED_STRICT_WITHHELD & flagged:
        # A day that would not open is unbounded evidence loss: the one
        # record that ever selected this name may be in it. Withholding the
        # list is the only honest answer, and it is the same move
        # ``NEVER_SELECTED_NO_CATALOG`` already makes — the renderers say
        # "withheld", never "none" (``NEVER_SELECTED_STRICT_WITHHELD``).
        strict = []
    if NEVER_SELECTED_DORMANT_WITHHELD & flagged:
        dormant = []

    # Exposure descending: the most-offered, least-chosen skill is the one the
    # human has the most evidence about. A reading order, not a rank — nothing
    # downstream may treat position as priority (ADR-0071 invariant 1).
    # Each population is ordered by the exposure its own renderers print, so
    # the column a reader scans is monotonic; the packet preserves the order
    # it receives rather than re-sorting, so the two surfaces agree.
    def _by_exposure(entries: list[NeverSelectedSkill]) -> tuple[NeverSelectedSkill, ...]:
        return tuple(sorted(entries, key=lambda e: (-e.judged_exposure, e.name)))

    def _by_window_exposure(entries: list[NeverSelectedSkill]) -> tuple[NeverSelectedSkill, ...]:
        return tuple(sorted(entries, key=lambda e: (-e.window_exposure, e.name)))

    return NeverSelectedReading(
        strict=_by_exposure(strict),
        dormant=_by_window_exposure(dormant),
        below_floor=_by_exposure(below_floor),
        exposure_floor=exposure_floor,
        history_files=history_files,
        history_records=history_records,
        history_judged=history_judged,
        history_fail_open=history_fail_open,
        history_first_day=min(days_read) if days_read else "",
        history_last_day=max(days_read) if days_read else "",
        unreadable_files=unreadable_files,
        malformed_rows=malformed_rows,
        window_days=window_days,
        window_since=since.isoformat() if since is not None else None,
        window_until=upper.isoformat() if upper is not None else None,
        window_records=window_records,
        window_judged=window_judged,
        window_fail_open=window_fail_open,
        history_full_skill_tokens=full_skill_tokens,
        num_ctx=NUM_CTX,
        catalog_size=len(catalog_names),
        catalog_available=bool(catalog_names),
        reasons=reasons,
    )


def never_selected_reading_json(reading: NeverSelectedReading) -> dict[str, Any]:
    """Serialize the reading to the per-week JSON the Saturday gate reads (ADR-0098).

    Rows, not counts. The gate computes every number it reads from these rows
    and re-applies the floor itself — a count asserted in a field is a count
    nobody checked, and the strict list is the one list a human acts on.
    """

    def _rows(entries: tuple[NeverSelectedSkill, ...]) -> list[dict[str, Any]]:
        return [
            {
                "name": e.name,
                "judged_exposure": e.judged_exposure,
                "window_exposure": e.window_exposure,
                "last_selected": e.last_selected,
            }
            for e in entries
        ]

    return {
        "exposure_floor": reading.exposure_floor,
        "strict": _rows(reading.strict),
        "dormant": _rows(reading.dormant),
        "below_floor": _rows(reading.below_floor),
        "history": {
            "files": reading.history_files,
            "records": reading.history_records,
            "judged": reading.history_judged,
            "fail_open": reading.history_fail_open,
            "first_day": reading.history_first_day,
            "last_day": reading.history_last_day,
            "unreadable_files": reading.unreadable_files,
            "malformed_rows": reading.malformed_rows,
        },
        "window": {
            "days": reading.window_days,
            "since": reading.window_since,
            "until": reading.window_until,
            "records": reading.window_records,
            "judged": reading.window_judged,
            "fail_open": reading.window_fail_open,
        },
        "corpus": {
            # Named for its scope: the latest the WHOLE history carries, and
            # the packet renders it beside the whole-history strict list only.
            "history_full_skill_tokens": reading.history_full_skill_tokens,
            "num_ctx": reading.num_ctx,
        },
        "catalog": {
            "size": reading.catalog_size,
            "available": reading.catalog_available,
        },
        "reasons": list(reading.reasons),
    }


def _withholding(reading: NeverSelectedReading, codes: frozenset[str]) -> tuple[str, ...]:
    """The reasons, if any, under which a population must read as withheld
    rather than empty. Shared by both renderers of this reading so the
    packet — the surface a human archives from — cannot keep the weaker
    phrasing (the failure this helper exists to prevent was exactly that
    asymmetry)."""
    return tuple(c for c in reading.reasons if c in codes)


def format_never_selected_report(reading: NeverSelectedReading) -> str:
    """Render the exit reading for a terminal (`report --skill-selection`).

    The weekly packet renders the same reading from JSON; this one exists so
    the human at the gate can ask the question outside the weekly chain — and
    so the reading has a live consumer, which is the condition this repo puts
    on an instrument existing at all (signal-first).
    """
    lines = [
        "## Never-selected reading (ADR-0097 D5 exit — listing only)",
        "",
        f"History: {reading.history_files} daily logs "
        f"({reading.history_first_day or '—'} … {reading.history_last_day or '—'}), "
        f"{reading.history_judged} judged of {reading.history_records} records",
        f"Catalog: {reading.catalog_size} skills"
        + (
            ""
            if reading.catalog_available
            else " (unreadable OR empty — `load_skill_catalog` returns () for both; "
            "populations withheld either way)"
        ),
        f"Exposure floor: {reading.exposure_floor} judged exposures",
    ]
    if reading.unreadable_files or reading.malformed_rows:
        lines.append(
            f"Evidence lost: {reading.unreadable_files} unreadable day(s), "
            f"{reading.malformed_rows} unusable row(s)"
        )
    if reading.reasons:
        lines.append(f"Reasons: {', '.join(reading.reasons)}")
    span = (
        f"{reading.window_since} … {reading.window_until}"
        if reading.window_since
        else f"the last {reading.window_days} days"
    )
    lines.append("")
    lines.append(
        "Behaviour-neutrality holds for JUDGED actions only — the fail-open "
        "path injects the full corpus:"
    )
    # Whole-history, beside the whole-history population. A window figure
    # here would answer a question nobody asked of a strict candidate, and
    # would read as 0 for an agent that was down for the window.
    lines.append(
        f"- fail-open across the whole history: {reading.history_fail_open} "
        f"of {reading.history_records} records"
    )
    if reading.history_full_skill_tokens:
        relation = (
            "exceeds" if reading.history_full_skill_tokens >= reading.num_ctx else "fits within"
        )
        lines.append(
            f"- full corpus {reading.history_full_skill_tokens:,} tok {relation} "
            f"NUM_CTX {reading.num_ctx:,}"
        )
    else:
        lines.append(
            "- full corpus size unknown (NEVER_SELECTED_FULL_TOKENS_UNKNOWN) — "
            f"NUM_CTX is {reading.num_ctx:,}"
        )
    lines.append(
        "  One number, the latest the WHOLE history carries: the corpus as "
        "the most recent judged action saw it. Its distribution — median size "
        "per catalog size, and where the regime boundaries fall — is the "
        "`By catalog size` table of the windowed reading above; this line "
        "adds only the comparison against NUM_CTX, which that table does "
        "not make."
    )
    lines.append("")
    lines.append(
        f"Strict (0 selections in the whole history, >= {reading.exposure_floor} "
        "judged exposures) — archive candidates for the human gate:"
    )
    withheld = _withholding(reading, NEVER_SELECTED_STRICT_WITHHELD)
    if withheld:
        lines.append(f"- WITHHELD ({', '.join(withheld)}) — this reading cannot answer")
    elif reading.strict:
        for entry in reading.strict:
            lines.append(f"- {entry.name}: offered in {entry.judged_exposure} judged records")
    else:
        lines.append("- (none)")
    if reading.below_floor:
        highest = max(e.judged_exposure for e in reading.below_floor)
        lines.append("")
        lines.append(
            f"Below the floor: {len(reading.below_floor)} never-selected skills "
            f"under {reading.exposure_floor} exposures (highest {highest}) — "
            "not yet candidates, not listed"
        )
    lines.append("")
    lines.append(
        f"Dormant (0 selections in {span} but selected before) — "
        "reading only, NOT archive candidates:"
    )
    lines.append(
        f"  fail-open in {span}: {reading.window_fail_open} of {reading.window_records} records"
    )
    dormant_withheld = _withholding(reading, NEVER_SELECTED_DORMANT_WITHHELD)
    if dormant_withheld:
        lines.append(f"- WITHHELD ({', '.join(dormant_withheld)}) — this reading cannot answer")
    elif reading.dormant:
        for entry in reading.dormant:
            lines.append(
                f"- {entry.name}: offered in {entry.window_exposure} judged records "
                f"this window, last selected {entry.last_selected or '—'} "
                "(whole history — may post-date the window)"
            )
    else:
        lines.append("- (none)")
    return "\n".join(lines)
