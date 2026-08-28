#!/usr/bin/env python3
"""Co-selection family instrument (ADR-0097 Decisions 5 and 7) — read-only.

Reads the selector's own audit log (``logs/skill-selection-*.jsonl``, written
by ``core/skill_selection.py``) and prints the family structure the selector
reveals — with no LLM and no embeddings:

- **sibling pairs** — both conditional probabilities >= ``--sibling-min``
  (default 0.6): the selector does not distinguish the two skills.
- **sub-case pairs** — ``P(general|specific) >= --subcase-high`` (0.7) while
  ``P(specific|general) <= --subcase-low`` (0.4): the selector treats the
  first as a special case of the second.
- **family any-of rate** — for an operator-named set of skills, the share of
  judged actions in which at least one member was selected. This is the
  quantity ADR-0097 Decision 7 promotes a rule on (>= 0.75 over at least two
  *disjoint* windows of >= 500 judged records), so windows are explicit and
  repeatable and the disjointness is derived rather than asserted.

**Instrument, never intervention** (ADR-0071, skill ``read-only-instruments``).
Nothing here feeds a gate, a ranking, the injector or ``adopt-staged``; the
reading informs the human at the Saturday gate, who decides. ADR-0097
Decision 7 keeps every member skill in the store — a family reading is not an
archive list.

Deterministic and replayable: every window is passed in as ``--window
START:END`` (inclusive, filename dates, the same daily rotation the selector
writes), so there is no wall-clock read and the same log always produces the
same reading. Faults abstain with a reason code on stderr and a nonzero exit
— an unreadable log must never print as "no family structure" (ADR-0075).

Counting rules, all of which are printed beside the rates:

- **Judged records only.** ``verdict != "judged"`` means the selector never
  answered, so the action neither selected nor refused anything; the same cut
  ``core/skill_selection.py`` makes. A judged record whose ``catalog_names``
  or ``selected`` is unusable is excluded from every statistic and counted
  separately, so ``judged`` and ``judged_analyzed`` are both reported.
- **Window coverage.** ``days_in_window`` and ``days_with_a_log_file`` are
  both printed and a shortfall raises ``MISSING_LOG_DAYS``. A quiet day
  legitimately writes no file, so this is coverage rather than a fault — but
  a 3/7-covered window otherwise renders with exactly the authority of a
  7/7 one, and Decision 7 compares windows against each other.
- **Judged floor.** ``--min-judged`` (default 500, Decision 7's bar) marks
  each window ``decision_input: false`` and raises ``BELOW_JUDGED_FLOOR``
  when it is not met, so the headline rate of a mistyped one-day window does
  not read like the headline rate of a week.
- **Minimum support** (``support_rule`` in the output). A pair is reported
  only when

  1. it was *jointly offered* in at least ``--min-co-exposure`` judged records
     (default 100). The store grew 24 -> 57 skills over the weeks this reading
     was designed for, so a low co-exposure almost always means one member was
     adopted mid-window and the pair describes a corner of the window rather
     than the selector's behaviour. 100 judged records is just over one day of
     production (ADR-0097 Decision 8: ~80-95 judged records/day), i.e. the
     floor says "at least a day of joint exposure"; and
  2. each member was selected in at least ``--min-selections`` of those
     records (default 20) — that count is the denominator of one conditional.
     At 20 the 95% Wilson interval around a 0.65 estimate is [0.43, 0.82]: it
     still straddles the 0.6 sibling threshold but no longer reaches the
     <= 0.4 sub-case band, so the two classifications stay distinguishable.
     At 13 it reaches 0.385 and they do not.

  The two clauses are reported apart (``pairs_below_co_exposure`` /
  ``pairs_below_selections``) so the operator knows which floor to
  reconsider, and the floor is a floor rather than a guarantee — every
  conditional is printed with its own denominator and its 95% Wilson
  interval, so a thin pair reads as thin even when it clears the rule.
- **Conditioning** (``--condition``, default ``co-exposed``). Numerator and
  both denominators are restricted to judged records where *both* names were
  in the catalog, so a skill adopted mid-window is not penalised for the part
  of the window it did not exist in. ``--condition window`` reproduces the
  plain ``count(a and b) / count(a)`` reading quoted in ADR-0097's Context;
  the unconditioned denominators are printed either way, so the two readings
  can be compared without a second run.

Misreading guards this instrument cannot resolve for you: a high any-of rate
means the family is broadly applicable **or** that the selector does not
discriminate within it — undecidable from co-selection alone (ADR-0071
invariant 2). A pair that clears the sibling test says the selector treats
the two as interchangeable, not that their procedures are the same; ADR-0097
records the opposite for the constraint family.

Usage::

    python3 scripts/coselection_families.py \\
        --log-dir "$MOLTBOOK_HOME/logs" \\
        --window 2026-08-16:2026-08-22 \\
        --family constraint=skill-a,skill-b,skill-c
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any

from _scan import ScanError
from _stats import wilson_ci

# The same filename grammar `adapters/moltbook/submolt_scope.py` already names
# as a constant. Re-declared rather than imported for the bare-`python3`
# reason given at `load_window`.
_LOG_PREFIX = "skill-selection-"
_LOG_GLOB = f"{_LOG_PREFIX}*.jsonl"

DEFAULT_SIBLING_MIN = 0.6
DEFAULT_SUBCASE_HIGH = 0.7
DEFAULT_SUBCASE_LOW = 0.4
DEFAULT_MIN_CO_EXPOSURE = 100
DEFAULT_MIN_SELECTIONS = 20
DEFAULT_TOP = 50

# ADR-0097 Decision 7's promotion criterion, echoed into the reading so the
# numbers and the bar they are read against travel together.
FAMILY_RATE_MIN = 0.75
FAMILY_MIN_JUDGED = 500
FAMILY_MIN_WINDOWS = 2

# Cost bound (read-only-instruments invariant 4): co-exposure is quadratic in
# the catalog. Grouping by catalog signature keeps the real cost at
# ``#signatures * |catalog|^2`` (a few thousand operations at 57 skills), but
# a store 17x today's would still be minutes of silent work — abstain instead.
_MAX_CATALOG_NAMES = 1000

# Every parse fault this reading can record, enumerated exactly once. The set
# used to be spelled out three times (dataclass fields, the sum, the rendered
# block); an eighth fault meant three edits, and a line forgotten in the sum
# made that fault silent — the one thing the docstring above says must not
# happen.
FAULT_KEYS = (
    "unreadable_files",
    "malformed_lines",
    "non_dict_records",
    "judged_without_catalog",
    "judged_without_usable_selection",
    "selected_outside_catalog",
    "dropped_selected_entries",
)


@dataclass(frozen=True)
class JudgedRecord:
    """One judged selection: which catalog was offered, and what was picked."""

    signature_id: int
    selected: frozenset[str]


@dataclass(frozen=True)
class WindowData:
    """Everything one window contributes, with its parse faults named."""

    start: str
    end: str
    days_in_window: int
    days_with_a_log_file: int
    records: int
    judged: int
    # Counted over ``judged``, not over ``judged_analyzed``: enforcement is a
    # property of the record the selector wrote, decided before this reading
    # could tell whether the catalog was usable. The output names it
    # ``enforced_of_judged`` so it is not summed against the analysed set.
    enforced: int
    judged_records: tuple[JudgedRecord, ...]
    signatures: tuple[tuple[str, ...], ...]
    signature_counts: tuple[int, ...]
    parse_faults: tuple[tuple[str, int], ...]

    @property
    def judged_analyzed(self) -> int:
        return len(self.judged_records)

    @property
    def missing_days(self) -> int:
        return self.days_in_window - self.days_with_a_log_file

    @property
    def faults(self) -> int:
        return sum(count for _, count in self.parse_faults)


def parse_window(spec: str) -> tuple[date, date]:
    """``START:END`` (inclusive) into a date pair."""
    start_text, sep, end_text = spec.partition(":")
    if not sep:
        raise ScanError("BAD_WINDOW", f"expected START:END, got {spec!r}")
    try:
        start = date.fromisoformat(start_text.strip())
        end = date.fromisoformat(end_text.strip())
    except ValueError as exc:
        raise ScanError("BAD_WINDOW", f"{spec!r}: {exc}") from exc
    if end < start:
        raise ScanError("BAD_WINDOW", f"{spec!r}: end is before start")
    return start, end


def parse_family(spec: str) -> tuple[str, tuple[str, ...]]:
    """``NAME=member,member,...`` into a family definition."""
    name, sep, members_text = spec.partition("=")
    name = name.strip()
    if not sep or not name:
        raise ScanError("BAD_FAMILY_SPEC", f"expected NAME=a,b,c, got {spec!r}")
    members: list[str] = []
    for raw in members_text.split(","):
        member = raw.strip()
        if member and member not in members:
            members.append(member)
    if not members:
        raise ScanError("BAD_FAMILY_SPEC", f"{name!r} has no members")
    return name, tuple(members)


def _process_log_line(
    line: str,
    path_name: str,
    faults: dict[str, int],
    signature_ids: dict[tuple[str, ...], int],
    signature_counts: list[int],
    judged_records: list[JudgedRecord],
) -> tuple[bool, bool, bool]:
    """Parse and account for one JSONL line from a selection log.

    Split out of :func:`load_window` (behaviour-preserving) — the per-line
    accounting that used to run inline in the nested file/line loop. Mutates
    ``faults`` / ``signature_ids`` / ``signature_counts`` / ``judged_records``
    in place (all mutable containers owned by the caller for the whole
    window) and returns ``(is_record, is_judged, is_enforced)`` so the caller
    can fold those into its own running totals.
    """
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        faults["malformed_lines"] += 1
        return False, False, False
    if not isinstance(record, dict):
        faults["non_dict_records"] += 1
        return False, False, False
    if str(record.get("verdict", "")) != "judged":
        return True, False, False
    enforced = bool(record.get("enforced"))
    raw_catalog = record.get("catalog_names")
    if not isinstance(raw_catalog, list):
        faults["judged_without_catalog"] += 1
        return True, True, enforced
    catalog = {name for name in raw_catalog if isinstance(name, str) and name}
    if not catalog:
        faults["judged_without_catalog"] += 1
        return True, True, enforced
    if len(catalog) > _MAX_CATALOG_NAMES:
        raise ScanError(
            "CATALOG_TOO_LARGE",
            f"{path_name}: {len(catalog)} names exceeds the {_MAX_CATALOG_NAMES} bound",
        )
    # ``selected`` gets the same type check ``catalog_names`` gets, and
    # gets it BEFORE the catalog signature is recorded so an excluded
    # record cannot still inflate the exposure denominators. A non-list
    # (``5``, ``true``) used to reach ``for name in ...`` as an uncaught
    # TypeError — a nonzero exit with no reason code, and exit 1 where
    # every other fault exits 2. A bare string was worse: it iterated
    # per character, so ``"a-one"`` booked five phantom out-of-catalog
    # faults and left a silently empty selection that lowered every
    # family rate.
    raw_selected = record.get("selected")
    if not isinstance(raw_selected, list):
        faults["judged_without_usable_selection"] += 1
        return True, True, enforced
    signature = tuple(sorted(catalog))
    signature_id = signature_ids.get(signature)
    if signature_id is None:
        signature_id = len(signature_counts)
        signature_ids[signature] = signature_id
        signature_counts.append(0)
    signature_counts[signature_id] += 1

    selected: set[str] = set()
    for name in raw_selected:
        if not isinstance(name, str) or not name:
            faults["dropped_selected_entries"] += 1
            continue
        if name not in catalog:
            # The writer validates picks against the catalog, so this
            # is log corruption rather than selector behaviour; a name
            # with no exposure would otherwise produce a conditional
            # with an empty denominator.
            faults["selected_outside_catalog"] += 1
            continue
        selected.add(name)
    judged_records.append(JudgedRecord(signature_id, frozenset(selected)))
    return True, True, enforced


def _process_log_file(
    path: Path,
    faults: dict[str, int],
    signature_ids: dict[tuple[str, ...], int],
    signature_counts: list[int],
    judged_records: list[JudgedRecord],
) -> tuple[int, int, int]:
    """Read one dated log file and account every line in it.

    Split out of :func:`load_window` (behaviour-preserving). Returns this
    file's ``(records, judged, enforced)`` deltas for the caller to fold into
    the window totals.
    """
    try:
        text = path.read_text(encoding="utf-8")
    # UnicodeDecodeError is a ValueError, not an OSError — the gap that
    # took the (since retired) packet builder down once (2026-07-29 review).
    except (OSError, UnicodeDecodeError):
        faults["unreadable_files"] += 1
        return 0, 0, 0

    records = judged = enforced = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        is_record, is_judged, is_enforced = _process_log_line(
            line, path.name, faults, signature_ids, signature_counts, judged_records
        )
        if is_record:
            records += 1
        if is_judged:
            judged += 1
            if is_enforced:
                enforced += 1
    return records, judged, enforced


def load_window(log_dir: Path, start: date, end: date) -> WindowData:
    """Read every ``skill-selection-YYYY-MM-DD.jsonl`` dated within the window.

    The day comes from the filename rather than each record's ``ts`` for the
    same reason ``core/skill_selection.py`` does it: the writer derives both
    from one UTC clock, so a record with a damaged timestamp still lands on
    the right day. Broken lines are counted, never fatal.

    **This is the third walk of this log in the repo.** The others are
    ``core/skill_selection.py::read_skill_selection_log`` (which owns the
    grammar, being the writer) and ``adapters/moltbook/submolt_scope.py``'s
    window reader. They are not imported here because this script's documented
    workflow is a bare ``python3`` invocation with no installed package,
    matching the other ``scripts/`` intakes. The three have already drifted:
    submolt_scope guards ``isinstance(rec, dict)``, skill_selection drops
    malformed lines uncounted, and this one counts seven buckets — so the
    consolidation worth doing is a shared ``iter_daily_records`` in
    ``core/skill_selection.py``, not an import edge from here.

    Line splitting is likewise not ``_audit.parse_records``, which the
    retrieval instrument does use: that helper merges undecodable lines and
    non-object records into one counter, and this reading reports them apart.
    Widening its arity would touch the two weekly-packet consumers its own
    docstring says must not diverge.
    """
    faults = dict.fromkeys(FAULT_KEYS, 0)
    signature_ids: dict[tuple[str, ...], int] = {}
    signature_counts: list[int] = []
    judged_records: list[JudgedRecord] = []
    days_with_a_log_file = 0
    records = 0
    judged = 0
    enforced = 0

    for path in sorted(log_dir.glob(_LOG_GLOB)):
        date_part = path.stem.removeprefix(_LOG_PREFIX)
        try:
            file_date = date.fromisoformat(date_part)
        except ValueError:
            continue
        if file_date < start or file_date > end:
            continue
        days_with_a_log_file += 1
        file_records, file_judged, file_enforced = _process_log_file(
            path, faults, signature_ids, signature_counts, judged_records
        )
        records += file_records
        judged += file_judged
        enforced += file_enforced

    ordered = sorted(signature_ids.items(), key=lambda item: item[1])
    return WindowData(
        start=start.isoformat(),
        end=end.isoformat(),
        days_in_window=(end - start).days + 1,
        days_with_a_log_file=days_with_a_log_file,
        records=records,
        judged=judged,
        enforced=enforced,
        judged_records=tuple(judged_records),
        signatures=tuple(signature for signature, _ in ordered),
        signature_counts=tuple(signature_counts),
        parse_faults=tuple((key, faults[key]) for key in FAULT_KEYS),
    )


@dataclass(frozen=True)
class Tallies:
    """Per-window counts every rate below is derived from."""

    selected_total: dict[str, int]
    both_selected: dict[tuple[str, str], int]
    co_exposure: dict[tuple[str, str], int]
    # (a, b) -> judged records where a was selected AND b was in the catalog.
    selected_with_exposed: dict[tuple[str, str], int]


def tally(window: WindowData) -> Tallies:
    selected_total: dict[str, int] = {}
    both_selected: dict[tuple[str, str], int] = {}
    co_exposure: dict[tuple[str, str], int] = {}
    selected_with_exposed: dict[tuple[str, str], int] = {}
    # (signature_id, name) -> judged records with that catalog where name was
    # picked.
    selected_by_signature: dict[tuple[int, str], int] = {}

    for record in window.judged_records:
        for name in record.selected:
            selected_total[name] = selected_total.get(name, 0) + 1
            key = (record.signature_id, name)
            selected_by_signature[key] = selected_by_signature.get(key, 0) + 1
        for pair in combinations(sorted(record.selected), 2):
            both_selected[pair] = both_selected.get(pair, 0) + 1

    # Both loops below fan out over signatures rather than over records: the
    # catalog changes a handful of times a week, not per action, so the
    # exposure arithmetic costs ``#signatures * |catalog|^2`` instead of
    # ``#records * |catalog|^2``.
    for signature_id, signature in enumerate(window.signatures):
        count = window.signature_counts[signature_id]
        for pair in combinations(signature, 2):
            co_exposure[pair] = co_exposure.get(pair, 0) + count
    for (signature_id, name), count in selected_by_signature.items():
        for other in window.signatures[signature_id]:
            if other == name:
                continue
            ordered_key = (name, other)
            selected_with_exposed[ordered_key] = selected_with_exposed.get(ordered_key, 0) + count

    return Tallies(selected_total, both_selected, co_exposure, selected_with_exposed)


@dataclass(frozen=True)
class Thresholds:
    sibling_min: float
    subcase_high: float
    subcase_low: float

    def validate(self) -> None:
        for label, value in (
            ("sibling-min", self.sibling_min),
            ("subcase-high", self.subcase_high),
            ("subcase-low", self.subcase_low),
        ):
            if not 0.0 <= value <= 1.0:
                raise ScanError("BAD_THRESHOLDS", f"--{label}={value} outside [0, 1]")
        if not self.subcase_low < self.sibling_min <= self.subcase_high:
            # Overlapping bands would let one pair be classified as both a
            # sibling and a sub-case, and the reader could not tell which
            # reading the script meant.
            raise ScanError(
                "BAD_THRESHOLDS",
                f"need subcase-low < sibling-min <= subcase-high, got "
                f"{self.subcase_low} / {self.sibling_min} / {self.subcase_high}",
            )


@dataclass(frozen=True)
class PairRows:
    """Classified pairs plus the two support clauses that withheld the rest."""

    siblings: list[dict[str, Any]]
    subcases: list[dict[str, Any]]
    considered: int
    below_co_exposure: int
    below_selections: int


def _pair_rows(
    window: WindowData,
    tallies: Tallies,
    *,
    thresholds: Thresholds,
    min_co_exposure: int,
    min_selections: int,
    condition: str,
) -> PairRows:
    siblings: list[dict[str, Any]] = []
    subcases: list[dict[str, Any]] = []
    considered = 0
    below_co_exposure = 0
    below_selections = 0

    for (first, second), exposure in tallies.co_exposure.items():
        considered += 1
        both = tallies.both_selected.get((first, second), 0)
        if condition == "window":
            den_first = tallies.selected_total.get(first, 0)
            den_second = tallies.selected_total.get(second, 0)
        else:
            den_first = tallies.selected_with_exposed.get((first, second), 0)
            den_second = tallies.selected_with_exposed.get((second, first), 0)
        # The two clauses are reported apart because their justifications
        # differ: the first says the pair was barely offered together, the
        # second says one member was barely picked. A merged count cannot tell
        # the operator which floor to reconsider.
        if exposure < min_co_exposure:
            below_co_exposure += 1
            continue
        if min(den_first, den_second) < min_selections:
            below_selections += 1
            continue
        p_second_given_first = both / den_first
        p_first_given_second = both / den_second
        base = {
            "co_exposure": exposure,
            "both_selected": both,
            "selected_window": {
                first: tallies.selected_total.get(first, 0),
                second: tallies.selected_total.get(second, 0),
            },
            "judged_analyzed": window.judged_analyzed,
        }
        if (
            p_second_given_first >= thresholds.sibling_min
            and p_first_given_second >= thresholds.sibling_min
        ):
            siblings.append(
                {
                    "a": first,
                    "b": second,
                    "a_selected": den_first,
                    "b_selected": den_second,
                    "p_b_given_a": round(p_second_given_first, 4),
                    "p_b_given_a_ci95": wilson_ci(both, den_first),
                    "p_a_given_b": round(p_first_given_second, 4),
                    "p_a_given_b_ci95": wilson_ci(both, den_second),
                    **base,
                }
            )
            continue
        for specific, general, p_general, p_specific, den_specific, den_general in (
            (first, second, p_second_given_first, p_first_given_second, den_first, den_second),
            (second, first, p_first_given_second, p_second_given_first, den_second, den_first),
        ):
            if p_general >= thresholds.subcase_high and p_specific <= thresholds.subcase_low:
                subcases.append(
                    {
                        "specific": specific,
                        "general": general,
                        "specific_selected": den_specific,
                        "general_selected": den_general,
                        "p_general_given_specific": round(p_general, 4),
                        "p_general_given_specific_ci95": wilson_ci(both, den_specific),
                        "p_specific_given_general": round(p_specific, 4),
                        "p_specific_given_general_ci95": wilson_ci(both, den_general),
                        **base,
                    }
                )
                break

    siblings.sort(
        key=lambda row: (-min(row["p_b_given_a"], row["p_a_given_b"]), row["a"], row["b"])
    )
    subcases.sort(
        key=lambda row: (
            -row["p_general_given_specific"],
            row["p_specific_given_general"],
            row["specific"],
        )
    )
    return PairRows(siblings, subcases, considered, below_co_exposure, below_selections)


def _family_rows(
    window: WindowData,
    tallies: Tallies,
    families: tuple[tuple[str, tuple[str, ...]], ...],
) -> list[dict[str, Any]]:
    exposed: set[str] = set()
    for signature in window.signatures:
        exposed.update(signature)
    rows: list[dict[str, Any]] = []
    for name, members in families:
        member_set = frozenset(members)
        hits = sum(1 for record in window.judged_records if record.selected & member_set)
        denominator = window.judged_analyzed
        member_exposed = sum(
            window.signature_counts[signature_id]
            for signature_id, signature in enumerate(window.signatures)
            if member_set & set(signature)
        )
        rows.append(
            {
                "name": name,
                "members": list(members),
                # A member the catalog never offered in this window reads as
                # never selected and silently lowers the rate — so it is named
                # rather than left to be inferred from a low per-member count.
                "members_absent_from_catalog": [m for m in members if m not in exposed],
                "judged_analyzed": denominator,
                "any_of_selected": hits,
                # ADR-0097 Decision 7 states its bar over judged records, so
                # that stays the headline denominator. But a member adopted
                # mid-window is offered for only part of it, and the records
                # before its adoption dilute the rate downward with nothing in
                # the output to show for it — `members_absent_from_catalog`
                # catches only TOTAL absence. So the exposure is printed
                # alongside, with the rate over it, and a shortfall raises
                # PARTIAL_FAMILY_EXPOSURE. The bias is one-directional
                # (dilution -> false negative against the 0.75 bar, never a
                # false positive), which is why the criterion is left alone
                # and the reader is given both numbers instead.
                "judged_with_a_member_exposed": member_exposed,
                "any_of_rate": round(hits / denominator, 4) if denominator else None,
                "any_of_rate_ci95": wilson_ci(hits, denominator),
                "any_of_rate_over_exposed": (
                    round(hits / member_exposed, 4) if member_exposed else None
                ),
                "per_member_selected": {m: tallies.selected_total.get(m, 0) for m in members},
            }
        )
    return rows


def build_window_reading(
    window: WindowData,
    *,
    thresholds: Thresholds,
    min_co_exposure: int,
    min_selections: int,
    min_judged: int,
    condition: str,
    families: tuple[tuple[str, tuple[str, ...]], ...],
    top: int,
) -> dict[str, Any]:
    """One window's block of the reading (pure; unit-testable)."""
    tallies = tally(window)
    pairs = _pair_rows(
        window,
        tallies,
        thresholds=thresholds,
        min_co_exposure=min_co_exposure,
        min_selections=min_selections,
        condition=condition,
    )
    family_rows = _family_rows(window, tallies, families)
    catalog_sizes = [len(signature) for signature in window.signatures]
    decision_input = window.judged_analyzed >= min_judged
    reasons: list[str] = []
    if window.faults:
        reasons.append("LOG_PARTIAL_PARSE")
    if window.missing_days:
        reasons.append("MISSING_LOG_DAYS")
    if window.judged_analyzed == 0:
        reasons.append("WINDOW_EMPTY")
    elif not decision_input:
        reasons.append("BELOW_JUDGED_FLOOR")
    if any(row["members_absent_from_catalog"] for row in family_rows):
        reasons.append("FAMILY_MEMBER_ABSENT")
    if any(row["judged_with_a_member_exposed"] < window.judged_analyzed for row in family_rows):
        reasons.append("PARTIAL_FAMILY_EXPOSURE")
    return {
        "start": window.start,
        "end": window.end,
        "days_in_window": window.days_in_window,
        "days_with_a_log_file": window.days_with_a_log_file,
        "records": window.records,
        "judged": window.judged,
        "judged_analyzed": window.judged_analyzed,
        "decision_input": decision_input,
        "min_judged": min_judged,
        "enforced_of_judged": window.enforced,
        "catalog_signatures": len(window.signatures),
        "catalog_size_min": min(catalog_sizes) if catalog_sizes else 0,
        "catalog_size_max": max(catalog_sizes) if catalog_sizes else 0,
        "pairs_considered": pairs.considered,
        "pairs_below_support": pairs.below_co_exposure + pairs.below_selections,
        "pairs_below_co_exposure": pairs.below_co_exposure,
        "pairs_below_selections": pairs.below_selections,
        "sibling_pairs_total": len(pairs.siblings),
        "sibling_pairs": pairs.siblings[:top] if top > 0 else pairs.siblings,
        "subcase_pairs_total": len(pairs.subcases),
        "subcase_pairs": pairs.subcases[:top] if top > 0 else pairs.subcases,
        "families": family_rows,
        "parse_faults": dict(window.parse_faults),
        "reasons": reasons,
    }


def windows_overlap(windows: tuple[WindowData, ...]) -> bool:
    """True when any two windows share a day (Decision 7 wants disjoint ones).

    Derived from the windows themselves rather than accepted as an argument:
    it feeds ``family_criterion.satisfied``, which is Decision 7's promotion
    arithmetic, so a caller passing the wrong value would silently flip it.

    One boolean over ALL pairs, deliberately: a third overlapping window
    disqualifies the criterion even when two others were disjoint and
    qualifying. That is the conservative direction against a promotion bar,
    and ``WINDOWS_OVERLAP`` names it, so the operator's repair is to re-run
    with the disjoint pair rather than to have the instrument guess which
    windows they meant.
    """
    spans = [(date.fromisoformat(w.start), date.fromisoformat(w.end)) for w in windows]
    for (start_a, end_a), (start_b, end_b) in combinations(spans, 2):
        if start_a <= end_b and start_b <= end_a:
            return True
    return False


def build_reading(
    windows: tuple[WindowData, ...],
    *,
    thresholds: Thresholds,
    min_co_exposure: int,
    min_selections: int,
    condition: str,
    families: tuple[tuple[str, tuple[str, ...]], ...],
    top: int,
    min_judged: int = FAMILY_MIN_JUDGED,
) -> dict[str, Any]:
    """Assemble the whole reading from already-loaded windows (pure)."""
    thresholds.validate()
    if condition not in ("co-exposed", "window"):
        raise ScanError("BAD_CONDITION", condition)
    if min_co_exposure < 1 or min_selections < 1:
        raise ScanError("BAD_SUPPORT", f"{min_co_exposure}/{min_selections}")
    if min_judged < 1:
        raise ScanError("BAD_MIN_JUDGED", str(min_judged))
    if top < 0:
        # A negative cap would silently mean "print everything", which is what
        # 0 already says explicitly — two spellings of one behaviour is how a
        # reader ends up unsure whether a short list was truncated.
        raise ScanError("BAD_TOP", str(top))
    if not windows:
        raise ScanError("NO_WINDOWS", "at least one --window is required")
    names = [name for name, _ in families]
    if len(names) != len(set(names)):
        raise ScanError("BAD_FAMILY_SPEC", f"duplicate family name in {names}")

    overlapping = windows_overlap(windows)
    window_readings = [
        build_window_reading(
            window,
            thresholds=thresholds,
            min_co_exposure=min_co_exposure,
            min_selections=min_selections,
            min_judged=min_judged,
            condition=condition,
            families=families,
            top=top,
        )
        for window in windows
    ]
    if all(reading["judged_analyzed"] == 0 for reading in window_readings):
        total = sum(reading["records"] for reading in window_readings)
        raise ScanError(
            "NO_JUDGED_RECORDS",
            f"{total} records read, none judged with a usable catalog and selection",
        )

    evaluable = not overlapping and len(window_readings) >= FAMILY_MIN_WINDOWS
    criterion_families: dict[str, Any] = {}
    for index, (name, _members) in enumerate(families):
        qualifying = 0
        for reading in window_readings:
            # Positional rather than a name scan: _family_rows emits in
            # `families` order, and reading back one's own serialized output
            # by name is a join that can silently miss.
            row = reading["families"][index]
            rate = row["any_of_rate"]
            if (
                rate is not None
                and rate >= FAMILY_RATE_MIN
                and row["judged_analyzed"] >= FAMILY_MIN_JUDGED
            ):
                qualifying += 1
        criterion_families[name] = {
            "windows_evaluated": len(window_readings),
            "qualifying_windows": qualifying,
            # None, not False, when the criterion cannot be evaluated at all:
            # one window or overlapping windows is "you did not give me the
            # evidence", and an operator reading `.satisfied` alone must not
            # see that as "this family failed the 0.75 bar". Same discipline
            # as `any_of_rate: null` on a zero denominator.
            "satisfied": (qualifying >= FAMILY_MIN_WINDOWS) if evaluable else None,
        }

    reasons = ["WINDOWS_OVERLAP"] if overlapping else []
    for reading in window_readings:
        reasons.extend(reading["reasons"])

    return {
        "condition": condition,
        "thresholds": {
            "sibling_min": thresholds.sibling_min,
            "subcase_high": thresholds.subcase_high,
            "subcase_low": thresholds.subcase_low,
        },
        "support_rule": {
            "min_co_exposure": min_co_exposure,
            "min_selections": min_selections,
            "min_judged": min_judged,
            "counted_over": (
                "judged records with a usable catalog and selection; under "
                f"condition={condition!r} the min_selections floor is counted over "
                + ("the co-exposed subset of them" if condition == "co-exposed" else "all of them")
            ),
        },
        "top": top,
        "windows": window_readings,
        "family_criterion": {
            "any_of_rate_min": FAMILY_RATE_MIN,
            "min_judged_per_window": FAMILY_MIN_JUDGED,
            "min_windows": FAMILY_MIN_WINDOWS,
            "windows_disjoint": not overlapping,
            "evaluable": evaluable,
            "families": criterion_families,
        },
        "ambiguity_note": (
            "A high any-of rate means the family is broadly applicable OR that "
            "the selector does not discriminate within it; co-selection cannot "
            "tell those apart. A sibling pair says the selector treats two "
            "skills as interchangeable, not that their procedures are."
        ),
        "reasons": list(dict.fromkeys(reasons)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only co-selection family reading over the skill-selection log."
    )
    parser.add_argument(
        "--log-dir", type=Path, required=True, help="dir holding skill-selection-*.jsonl"
    )
    parser.add_argument(
        "--window",
        action="append",
        required=True,
        metavar="START:END",
        help="inclusive date window (repeatable; Decision 7 wants >= 2 disjoint ones)",
    )
    parser.add_argument(
        "--family",
        action="append",
        default=[],
        metavar="NAME=a,b,c",
        help="named skill set for the any-of rate (repeatable)",
    )
    parser.add_argument("--sibling-min", type=float, default=DEFAULT_SIBLING_MIN)
    parser.add_argument("--subcase-high", type=float, default=DEFAULT_SUBCASE_HIGH)
    parser.add_argument("--subcase-low", type=float, default=DEFAULT_SUBCASE_LOW)
    parser.add_argument("--min-co-exposure", type=int, default=DEFAULT_MIN_CO_EXPOSURE)
    parser.add_argument("--min-selections", type=int, default=DEFAULT_MIN_SELECTIONS)
    parser.add_argument(
        "--min-judged",
        type=int,
        default=FAMILY_MIN_JUDGED,
        help="per-window judged floor below which the window is not a decision input",
    )
    parser.add_argument("--condition", choices=("co-exposed", "window"), default="co-exposed")
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP, help="max pairs printed per list (0 = all)"
    )
    args = parser.parse_args(argv)

    try:
        if not args.log_dir.is_dir():
            raise ScanError("LOG_DIR_MISSING", str(args.log_dir))
        if not any(args.log_dir.glob(_LOG_GLOB)):
            raise ScanError("NO_LOG_FILES", f"no {_LOG_GLOB} under {args.log_dir}")
        specs = tuple(parse_window(spec) for spec in args.window)
        families = tuple(parse_family(spec) for spec in args.family)
        windows = tuple(load_window(args.log_dir, start, end) for start, end in specs)
        reading = build_reading(
            windows,
            thresholds=Thresholds(args.sibling_min, args.subcase_high, args.subcase_low),
            min_co_exposure=args.min_co_exposure,
            min_selections=args.min_selections,
            min_judged=args.min_judged,
            condition=args.condition,
            families=families,
            top=args.top,
        )
    except ScanError as exc:
        # `reason=` token per the scripts/_scan.py contract (the weekly chain
        # greps it out of a stage's .err file); exit 2 matches every other
        # instrument's "the reading is unavailable".
        print(f"coselection_families: reason={exc.reason} {exc.detail}", file=sys.stderr)
        return 2

    thin = [w for w in reading["windows"] if not w["decision_input"]]
    if thin:
        spans = ", ".join(f"{w['start']}..{w['end']} ({w['judged_analyzed']} judged)" for w in thin)
        print(
            f"coselection_families: reason=BELOW_JUDGED_FLOOR {spans} under "
            f"{args.min_judged} judged — read as context, not as a decision input",
            file=sys.stderr,
        )
    print(json.dumps(reading, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
