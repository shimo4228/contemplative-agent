"""Instrument: the reader's confusion-pair reading for the store's exit (ADR-0105).

Read-only. The second signal of the ADR-0105 AND, beside
:mod:`.never_selected_metrics`: a skill the selector keeps *misnaming its way
into* while choosing it no more often than it mistypes it. "Low demand AND
duplicated" is the SkillOps-shaped conjunction the ADR settles on; neither
half retires anything by itself, and nothing here writes to the store.

Three rules that are deliberately NOT re-implemented here:

- the four-rule mechanism split of a rejected name is
  :func:`.selection_metrics.classify_hallucination` (floor
  ``WORDFORM_SIMILARITY_FLOOR``), and the nearest-catalog-name ruler is
  :func:`.selection_metrics.nearest_catalog_name`. A third copy of the split
  is the drift this module exists downstream of;
  ``tests/test_skill_confusion.py`` pins both against
  ``scripts/skillsel_reading.py::classify``, the manual instrument that froze
  the rule in RFC-0015's 4th reading.
- the exposure floor is ``NEVER_SELECTED_EXPOSURE_FLOOR`` (600 judged
  exposures over the whole history), imported rather than restated. ADR-0105
  shares the floor on purpose: two exit signals with two floors would let a
  skill be "enough evidence" for one reading and not the other in the same
  week.
- the log walk is :func:`.selection_window._scan_selection_history`,
  the same function that produces the never-selected reading, so the two
  readings cannot disagree about which records are judged, where the window
  is, what a malformed row costs, or how a rejected name is normalised. They
  are separate *calls* — the weekly chain runs 7b and 7c as two processes and
  the log is decoded twice; sharing the function buys agreement, not speed.

**Two scopes, like the sibling reading.** ``confused_as`` and
``selected_window`` are counted over the trailing window (the reader's
current behaviour is the claim); ``judged_exposure`` and the floor applied
to it are whole-history (how much evidence there is about the name). Field
names carry the scope.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .never_selected_metrics import (
    NEVER_SELECTED_DORMANT_WINDOW_DAYS,
    NEVER_SELECTED_EXPOSURE_FLOOR,
)
from .selection_metrics import (
    _catalog_vocabulary,
    _read_value_layer_vocabulary,
    classify_hallucination,
    nearest_catalog_name,
)
from .selection_window import (
    _scan_selection_history,
    log_health_reasons,
    resolve_reasons,
    resolve_selection_window,
)
from .skill_selection import load_skill_catalog, skill_theme
from .text_utils import iter_markdown_documents

logger = logging.getLogger(__name__)


# Shared with the never-selected reading, not re-derived. See the module
# docstring: one floor for the store's whole exit.
CONFUSION_EXPOSURE_FLOOR = NEVER_SELECTED_EXPOSURE_FLOOR

# Shared with the never-selected reading's dormant cut for the same reason,
# and because 14 days is what carries the >= 600 judged records the ADR-0105
# consumption plan reads the hallucination band over. Measured on the live
# log: 1,030 judged records over 2026-08-23..09-05 (RFC-0015's 4th reading),
# ~74/day, so a 7-day window carries ~500 — below the plan's own denominator.
CONFUSION_WINDOW_DAYS = NEVER_SELECTED_DORMANT_WINDOW_DAYS

# Which mechanisms count as the reader confusing one store entry for
# another. ``value_layer`` is text bled in from the constitution / identity —
# it maps to a nearest catalog name too, but the reader was not reaching for
# that skill, so counting it would charge a skill for a leak somewhere else.
# ``unclassified`` abstained and cannot be charged to anything.
CONFUSION_MECHANISMS = frozenset({"wordform", "semantic"})


CONFUSION_REASONS = (
    "CONFUSION_NO_CATALOG",
    "CONFUSION_NO_HISTORY",
    # Degraded: something this reading should have read, it did not.
    "CONFUSION_LOG_PARTIAL",
    # ...and the sharper one, raised only for a lost DAY — the same
    # bounded/unbounded distinction the sibling reading draws, with the same
    # consequence: a lost day withholds the pairs outright.
    "CONFUSION_LOG_UNREADABLE",
    "CONFUSION_EMPTY_WINDOW",
    # No rejected name in the window mapped onto a catalog entry. The guard
    # working, not a failure: it is the reading for a week in which the
    # reader did not confuse anything.
    "CONFUSION_NO_PAIRS",
    "CONFUSION_VALUE_LAYER_UNAVAILABLE",
    # ...and the sharper one: SOME value-layer text was read and some was not.
    # A half-read constitution does not abstain, it misclassifies — a token
    # living only in the missing half reads as ``semantic``, and ``semantic``
    # is charged to a skill here while ``value_layer`` is not. So a partial
    # read inflates ``confused_as`` in the direction of listing a candidate,
    # which is why it is named separately from the total failure.
    "CONFUSION_VALUE_LAYER_PARTIAL",
    # A retire pick has no unique file in the store, so it cannot be written
    # into an ``--archive-names`` file. Named rather than silently dropped.
    "CONFUSION_FILE_UNRESOLVED",
    # Raised by the pipeline stage, not by this module: stage 7b's per-week
    # JSON — the never-selected half of the union — was absent or unusable,
    # so the candidate file carries the confusion half only. Declared here so
    # the vocabulary stays closed over what actually reaches the JSON.
    "CONFUSION_NEVER_SELECTED_MISSING",
    "CONFUSION_NEVER_SELECTED_UNREADABLE",
)


# Reasons under which the pairs are not a reading but the absence of one. A
# renderer must say "withheld", never "no pairs": "the reader confused
# nothing" and "this reading cannot tell you" are opposite claims, and only
# one of them is a reason to archive.
CONFUSION_PAIRS_WITHHELD = frozenset(
    {
        "CONFUSION_NO_CATALOG",
        "CONFUSION_NO_HISTORY",
        "CONFUSION_LOG_UNREADABLE",
        "CONFUSION_EMPTY_WINDOW",
    }
)

# Same fail-unsafe guard as the sibling reading's, and a raise for the same
# reason: a withheld code absent from the declared tuple is filtered out
# before the withholding decision reads it, so it stops withholding silently.
if CONFUSION_PAIRS_WITHHELD - set(CONFUSION_REASONS):
    raise RuntimeError("withheld codes missing from CONFUSION_REASONS")


@dataclass(frozen=True)
class ConfusedSkill:
    """One store entry with the three counts the pair rule reads.

    ``confused_as`` is emissions, not records: one judged record that emitted
    two variants of the same name charges the name twice, exactly as
    ``RejectedNameTally.count`` does.
    """

    name: str
    # Window: rejected-name emissions whose nearest catalog entry was this
    # name, under a mechanism in ``CONFUSION_MECHANISMS``.
    confused_as: int
    # Window: judged records that actually selected this name.
    selected_window: int
    # WHOLE HISTORY: judged records that carried this name in
    # ``catalog_names``. The floor is applied to this number, not to a
    # window one — a fortnight cannot say how much evidence there is.
    judged_exposure: int
    # Surface similarity of the charged emissions to this name, lowest and
    # highest. **This reading applies no similarity floor to the charge** —
    # ``classify_hallucination`` calls any slug-shaped name with no
    # value-layer token ``semantic`` at any distance, so an emission scoring
    # 0.31 is charged to whichever entry is orthographically nearest by
    # noise. There is no derived number to floor it with (the 0.90 wordform
    # floor is a reporting boundary for a different question), so the
    # evidence is reported instead of thresholded: a pair whose band sits in
    # the 0.3s is a pair a reader can discount. 0.0 when nothing was charged.
    similarity_min: float
    similarity_max: float


@dataclass(frozen=True)
class ConfusionPair:
    """One candidate and the store entry its confusions ran between.

    ``partner`` is the entry the confused name's *own* variants resemble
    second-best: for every rejected name that mapped onto ``confused``, the
    runner-up catalog entry is scored, and the heaviest runner-up is the
    partner. ``None`` only when the confusions had nowhere else to land — a
    one-entry catalog, or every variant's runner-up scoring exactly 0. Two
    kebab-case slugs almost always share some substring, so on a real
    catalog **there is essentially always a partner**, and its similarity is
    what says whether the pairing means anything: read
    ``partner_similarity_max`` beside it. No floor is applied here either,
    for the reason on ``ConfusedSkill.similarity_min``.

    A consequence worth stating: ``retire`` may name the **partner**, which
    was never itself tested against the candidate condition. It has to clear
    the exposure floor and have a store file, and nothing more. That is the
    rule ADR-0105 settles on (the quieter side of the pair is the one whose
    absence costs least), not an oversight — but it means the partner's
    similarity is load-bearing evidence, not decoration.

    ``retire`` is the side of the pair with fewer window selections, and it
    is empty when neither side may be listed. ``retire_blocked`` says why:
    ``below_floor`` (the side with fewer selections has not been offered
    ``exposure_floor`` times, so retiring it would be the Library Drift A4
    collapse — retiring on evidence that does not exist), ``no_file`` (no
    unique store file carries that name).
    """

    confused: ConfusedSkill
    partner: ConfusedSkill | None
    # Summed emissions of the rejected names whose runner-up was
    # ``partner``. 0 when there is no partner. Evidence for the pairing, not
    # a rank.
    partner_weight: int
    # Highest surface similarity any charged emission had to ``partner``.
    # 0.0 with no partner.
    partner_similarity_max: float
    retire: str
    retire_blocked: str


@dataclass(frozen=True)
class ConfusionReading:
    """The ADR-0105 confusion-pair reading over one selection log.

    Read-only and listing-only: it names pairs and a side, the Saturday gate
    decides and moves the file. ``pairs`` is ordered by ``confused_as``
    descending — a reading order, not a rank (ADR-0071 invariant 1).
    """

    pairs: tuple[ConfusionPair, ...]
    exposure_floor: int
    # Every rejected-name emission the window carried, by mechanism
    # (emissions, not distinct names — a name emitted 40 times counts 40).
    # The denominator for "how much of the confusion this reading charged to
    # a skill", so a reader can see what the ``CONFUSION_MECHANISMS`` filter
    # dropped instead of taking the pair list as the whole of it.
    mechanism_emissions: tuple[tuple[str, int], ...]
    # Emissions charged to a catalog entry (the numerator of the above).
    charged_emissions: int
    window_days: int
    window_since: str | None
    window_until: str | None
    window_records: int
    window_judged: int
    history_files: int
    history_records: int
    history_judged: int
    unreadable_files: int
    malformed_rows: int
    catalog_size: int
    catalog_available: bool
    # ``skill name -> store filename``, for the names this reading lists
    # only. ``--archive-names`` addresses FILES, not names, so the mapping
    # is part of the reading rather than something the pipeline re-derives.
    retire_files: tuple[tuple[str, str], ...]
    # The whole store map this reading resolved names against, carried so the
    # candidate file is built from the SAME traversal that decided
    # ``retire_blocked="no_file"``. Two globs of a live store can disagree.
    store_files: tuple[tuple[str, str], ...]
    # ADR-0075: anything not computable abstains with a code rather than
    # guessing. Closed vocabulary in ``CONFUSION_REASONS``.
    reasons: tuple[str, ...]
    # The subset of ``reasons`` under which ``pairs`` reads as withheld
    # rather than empty. Carried explicitly because the consumer that acts on
    # the distinction (the Saturday gate) reads the JSON, not this module's
    # constants — asking a human to re-apply ``CONFUSION_PAIRS_WITHHELD``
    # from memory is how "withheld" quietly becomes "none".
    withheld: tuple[str, ...]


def skill_files_by_name(skills_dir: Path | None) -> dict[str, str]:
    """``skill name -> filename`` for the live store, ambiguities dropped.

    The catalog loader keeps no filename (``SkillCatalogEntry`` is what the
    prompt needs), but the store's exit addresses files: ``adopt-staged
    --archive-names`` takes ``old-skill-20260601.md``, not the frontmatter
    name. Same traversal and same name normalisation as
    :func:`.skill_selection.load_skill_catalog`, so a name that reaches this
    map is spelled the way the selection log spells it.

    Two files claiming one name are dropped rather than resolved: writing
    either into an archive file would retire a skill nobody named.
    """
    mapping: dict[str, str] = {}
    ambiguous: set[str] = set()
    for path, text in iter_markdown_documents(
        skills_dir, label="confusion reading: unreadable skill file"
    ):
        name, _description = skill_theme(text, fallback_name=path.stem)
        if name in mapping and mapping[name] != path.name:
            ambiguous.add(name)
            continue
        mapping[name] = path.name
    for name in ambiguous:
        logger.warning("confusion reading: skill name %r has more than one file", name)
        mapping.pop(name, None)
    return mapping


@dataclass(frozen=True)
class _Charge:
    """What one pass over the window's rejected names knows.

    Module-private: the raw material :class:`ConfusionReading` is computed
    from, in one value so the charging and the pair rule can be read apart.
    """

    # Emissions whose nearest entry is the key, under a counted mechanism.
    confused_as: dict[str, int]
    # ``[target][other]`` — of those emissions, how many had ``other`` as
    # their second-nearest entry, and (below) the best similarity any of
    # them had to it. The pairing evidence.
    runner_up_weight: dict[str, dict[str, int]]
    runner_up_similarity: dict[str, dict[str, float]]
    # ``[target] -> (lowest, highest)`` similarity among the charged
    # emissions.
    similarity_band: dict[str, tuple[float, float]]
    # Every emission, counted or not, by mechanism.
    mechanism_emissions: dict[str, int]


def _charge_rejected_names(
    rejected_window: dict[str, int],
    catalog_names: Sequence[str],
    *,
    catalog_vocabulary: frozenset[str] | None,
    value_layer_vocabulary: frozenset[str] | None,
) -> _Charge:
    """Charge each window rejected name to the catalog entry it resembles.

    No similarity floor is applied — see ``ConfusedSkill.similarity_min`` for
    why, and for what is reported in its place.
    """
    confused_as: dict[str, int] = {}
    runner_up_weight: dict[str, dict[str, int]] = {}
    runner_up_similarity: dict[str, dict[str, float]] = {}
    similarity_band: dict[str, tuple[float, float]] = {}
    mechanism_emissions: dict[str, int] = {}
    ordered = list(catalog_names)
    for name, count in rejected_window.items():
        nearest, similarity = nearest_catalog_name(name, ordered)
        mechanism, _reason, _note = classify_hallucination(
            name,
            similarity,
            catalog_vocabulary=catalog_vocabulary,
            value_layer_vocabulary=value_layer_vocabulary,
        )
        mechanism_emissions[mechanism] = mechanism_emissions.get(mechanism, 0) + count
        if not nearest or mechanism not in CONFUSION_MECHANISMS:
            continue
        confused_as[nearest] = confused_as.get(nearest, 0) + count
        low, high = similarity_band.get(nearest, (similarity, similarity))
        similarity_band[nearest] = (min(low, similarity), max(high, similarity))
        runner_up, runner_similarity = nearest_catalog_name(
            name, [c for c in ordered if c != nearest]
        )
        if runner_up and runner_similarity > 0.0:
            weights = runner_up_weight.setdefault(nearest, {})
            weights[runner_up] = weights.get(runner_up, 0) + count
            sims = runner_up_similarity.setdefault(nearest, {})
            sims[runner_up] = max(sims.get(runner_up, 0.0), runner_similarity)
    return _Charge(
        confused_as=confused_as,
        runner_up_weight=runner_up_weight,
        runner_up_similarity=runner_up_similarity,
        similarity_band=similarity_band,
        mechanism_emissions=mechanism_emissions,
    )


def _pick_partner(weights: dict[str, int]) -> tuple[str, int]:
    """The heaviest runner-up, ties broken by name so the pair is stable."""
    if not weights:
        return "", 0
    name = min(weights, key=lambda other: (-weights[other], other))
    return name, weights[name]


def _build_pairs(
    charge: _Charge,
    *,
    selected_window: dict[str, int],
    exposure_history: dict[str, int],
    exposure_floor: int,
    skill_files: dict[str, str],
) -> tuple[list[ConfusionPair], list[str]]:
    """Apply the ADR-0105 pair rule; return the pairs and the reason codes."""

    confused_as = charge.confused_as

    def _entry(name: str) -> ConfusedSkill:
        low, high = charge.similarity_band.get(name, (0.0, 0.0))
        return ConfusedSkill(
            name=name,
            confused_as=confused_as.get(name, 0),
            selected_window=selected_window.get(name, 0),
            judged_exposure=exposure_history.get(name, 0),
            similarity_min=low,
            similarity_max=high,
        )

    pairs: list[ConfusionPair] = []
    reasons: list[str] = []
    for name in sorted(confused_as):
        confused = _entry(name)
        # The candidate condition, verbatim from ADR-0105: the reader named
        # its way INTO this entry at least as often as it chose it, and the
        # entry has been offered often enough for that to mean anything.
        # ``confused_as > 0`` is unreachable while the loop ranges over
        # ``confused_as`` (every key was inserted with a positive count);
        # kept so the condition stays correct if the loop is ever ranged over
        # the whole catalog, where a never-confused entry would satisfy
        # ``0 >= 0``.
        if confused.confused_as <= 0:
            continue
        if confused.confused_as < confused.selected_window:
            continue
        if confused.judged_exposure < exposure_floor:
            continue
        partner_name, partner_weight = _pick_partner(charge.runner_up_weight.get(name, {}))
        partner = _entry(partner_name) if partner_name else None
        partner_similarity = charge.runner_up_similarity.get(name, {}).get(partner_name, 0.0)
        # The side of the pair the reader reaches for LESS is the one whose
        # absence costs least. With no partner the candidate is alone and is
        # its own pick.
        sides = [confused] if partner is None else [confused, partner]
        pick = min(sides, key=lambda s: (s.selected_window, s.judged_exposure, s.name))
        blocked = ""
        if pick.judged_exposure < exposure_floor:
            # Library Drift A4: retiring on evidence that does not exist
            # collapsed a store to two entries. The pair is still listed —
            # the reading is the point — but it proposes nothing.
            blocked = "below_floor"
        elif pick.name not in skill_files:
            blocked = "no_file"
            reasons.append("CONFUSION_FILE_UNRESOLVED")
        pairs.append(
            ConfusionPair(
                confused=confused,
                partner=partner,
                partner_weight=partner_weight,
                partner_similarity_max=partner_similarity,
                retire="" if blocked else pick.name,
                retire_blocked=blocked,
            )
        )
    pairs.sort(key=lambda p: (-p.confused.confused_as, p.confused.name))
    return pairs, reasons


def read_confusion_pairs(
    log_dir: Path,
    *,
    days: int | None = None,
    since: date | None = None,
    until: date | None = None,
    skills_dir: Path | None,
    value_layer_paths: tuple[Path, ...] = (),
) -> ConfusionReading:
    """Read the confusion pairs over ``skill-selection-*.jsonl`` (ADR-0105).

    One pass over the log per call, through the sibling reading's own walk, so
    the two exit readings agree about every boundary they share. (The weekly
    chain still decodes the log twice: 7b and 7c are separate processes.)
    ``days`` / ``since`` / ``until`` mean what they mean on
    :func:`.never_selected_metrics.read_never_selected`, resolved by the same
    :func:`.selection_window.resolve_selection_window`.

    ``value_layer_paths`` (constitution dir, identity file) are read, never
    written, and only feed the mechanism split — a rejected name that is
    constitution text bled into the answer is not a skill the reader
    confused, and without them that rule abstains rather than guessing.
    """
    window = resolve_selection_window(days, since, until)
    tally = _scan_selection_history(log_dir, window)

    catalog = load_skill_catalog(skills_dir)
    catalog_names = [e.name for e in catalog]
    catalog_vocabulary = _catalog_vocabulary(catalog, tally.exposure_history)
    value_layer_vocabulary, _files, value_layer_missing = (
        _read_value_layer_vocabulary(value_layer_paths) if value_layer_paths else (None, 0, ())
    )
    charge = _charge_rejected_names(
        tally.rejected_window,
        catalog_names,
        catalog_vocabulary=catalog_vocabulary,
        value_layer_vocabulary=value_layer_vocabulary,
    )
    confused_as = charge.confused_as
    skill_files = skill_files_by_name(skills_dir)
    pairs, pair_reasons = _build_pairs(
        charge,
        selected_window=tally.selected_window,
        exposure_history=tally.exposure_history,
        exposure_floor=CONFUSION_EXPOSURE_FLOOR,
        skill_files=skill_files,
    )

    flagged = set(pair_reasons) | log_health_reasons(
        tally, catalog_available=bool(catalog_names), prefix="CONFUSION"
    )
    if value_layer_vocabulary is None:
        # Rule 2 of the split could not run. Named because it moves names
        # between ``value_layer`` and ``semantic``, and only the second is
        # charged to a skill here.
        flagged.add("CONFUSION_VALUE_LAYER_UNAVAILABLE")
    elif value_layer_missing:
        flagged.add("CONFUSION_VALUE_LAYER_PARTIAL")
    if not confused_as:
        flagged.add("CONFUSION_NO_PAIRS")
    reasons = resolve_reasons(CONFUSION_REASONS, flagged)

    if CONFUSION_PAIRS_WITHHELD & set(reasons):
        pairs = []

    withheld = tuple(c for c in reasons if c in CONFUSION_PAIRS_WITHHELD)
    retire_files = tuple(
        sorted(
            {
                (p.retire, skill_files[p.retire])
                for p in pairs
                if p.retire and p.retire in skill_files
            }
        )
    )
    return ConfusionReading(
        pairs=tuple(pairs),
        exposure_floor=CONFUSION_EXPOSURE_FLOOR,
        mechanism_emissions=tuple(sorted(charge.mechanism_emissions.items())),
        charged_emissions=sum(confused_as.values()),
        window_days=window.days,
        window_since=window.since_text,
        window_until=window.until_text,
        window_records=tally.window_records,
        window_judged=tally.window_judged,
        history_files=tally.history_files,
        history_records=tally.history_records,
        history_judged=tally.history_judged,
        unreadable_files=tally.unreadable_files,
        malformed_rows=tally.malformed_rows,
        catalog_size=len(catalog_names),
        catalog_available=bool(catalog_names),
        retire_files=retire_files,
        store_files=tuple(sorted(skill_files.items())),
        reasons=reasons,
        withheld=withheld,
    )


def confusion_reading_json(reading: ConfusionReading) -> dict[str, Any]:
    """Serialize for the per-week JSON the Saturday gate reads.

    Rows, not counts — the same contract as
    :func:`.never_selected_metrics.never_selected_reading_json`: the gate
    re-applies the rule from the rows rather than trusting an asserted
    verdict.
    """

    def _skill(entry: ConfusedSkill | None) -> dict[str, Any] | None:
        if entry is None:
            return None
        return {
            "name": entry.name,
            "confused_as": entry.confused_as,
            "selected_window": entry.selected_window,
            "judged_exposure": entry.judged_exposure,
            "similarity_min": entry.similarity_min,
            "similarity_max": entry.similarity_max,
        }

    return {
        "exposure_floor": reading.exposure_floor,
        "pairs": [
            {
                "confused": _skill(p.confused),
                "partner": _skill(p.partner),
                "partner_weight": p.partner_weight,
                "partner_similarity_max": p.partner_similarity_max,
                "retire": p.retire,
                "retire_blocked": p.retire_blocked,
            }
            for p in reading.pairs
        ],
        "retire_files": [{"name": n, "file": f} for n, f in reading.retire_files],
        "mechanisms": {
            "emissions": dict(reading.mechanism_emissions),
            "charged_to_a_skill": reading.charged_emissions,
            "counted": sorted(CONFUSION_MECHANISMS),
        },
        "window": {
            "days": reading.window_days,
            "since": reading.window_since,
            "until": reading.window_until,
            "records": reading.window_records,
            "judged": reading.window_judged,
        },
        "history": {
            "files": reading.history_files,
            "records": reading.history_records,
            "judged": reading.history_judged,
            "unreadable_files": reading.unreadable_files,
            "malformed_rows": reading.malformed_rows,
        },
        "catalog": {
            "size": reading.catalog_size,
            "available": reading.catalog_available,
        },
        "reasons": list(reading.reasons),
        # The withholding subset, spelled out rather than left for the reader
        # to re-derive from a constant it cannot see.
        "withheld": list(reading.withheld),
    }


def archive_candidate_files(
    reading: ConfusionReading,
    never_selected_strict: Sequence[str],
    skill_files: dict[str, str] | None = None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """``(filenames, unresolved names)`` for the week's candidate file.

    The union ADR-0105 writes: the never-selected strict population and each
    pair's retire side, deduplicated and sorted, as **store filenames** —
    what ``adopt-staged --archive-names`` addresses. A name with no unique
    file is returned separately rather than dropped, so the findings can say
    a candidate exists that the file cannot carry.

    ``skill_files`` defaults to the reading's own ``store_files``, which is
    the point: the traversal that decided ``retire_blocked="no_file"`` and
    the one that writes the file must be the same snapshot of a live store.
    """
    if skill_files is None:
        skill_files = dict(reading.store_files)
    files: set[str] = set()
    unresolved: set[str] = set()
    for name in list(never_selected_strict) + [p.retire for p in reading.pairs if p.retire]:
        if not name:
            continue
        filename = skill_files.get(name)
        if filename is None:
            unresolved.add(name)
            continue
        files.add(filename)
    return tuple(sorted(files)), tuple(sorted(unresolved))


def format_confusion_findings(
    reading: ConfusionReading,
    never_selected_strict: Sequence[str],
    candidate_files: Sequence[str],
    candidates_path: str,
    extra_reasons: Sequence[str] = (),
) -> str:
    """The findings section (ADR-0105 stage 7c).

    Facts and pointers only — no evaluative or recommending vocabulary
    (ADR-0099's binding prohibition). Every number here is recomputable from
    the per-week JSON beside it.

    ``extra_reasons`` carries codes the *stage* raised rather than this
    reading — chiefly ``CONFUSION_NEVER_SELECTED_MISSING``. Without them a
    week whose never-selected half was lost renders "0 name(s)" with nothing
    to distinguish it from a week that had none, and this document is the
    surface a human archives from.
    """
    span = (
        f"{reading.window_since} … {reading.window_until}"
        if reading.window_since
        else f"the last {reading.window_days} days"
    )
    lines = [
        "## Skill store exit candidates (ADR-0105 — listing only)",
        "",
        f"Window: {span}, {reading.window_judged} judged of {reading.window_records} records. "
        f"History: {reading.history_judged} judged of {reading.history_records} records "
        f"over {reading.history_files} daily logs.",
        f"Catalog: {reading.catalog_size} skills. "
        f"Exposure floor: {reading.exposure_floor} judged exposures (whole history).",
    ]
    mechanisms = ", ".join(f"{m} {n}" for m, n in reading.mechanism_emissions) or "none"
    lines.append(
        f"Rejected-name emissions by mechanism: {mechanisms}. "
        f"Charged to a catalog entry ({', '.join(sorted(CONFUSION_MECHANISMS))}): "
        f"{reading.charged_emissions}."
    )
    all_reasons = tuple(reading.reasons) + tuple(extra_reasons)
    if all_reasons:
        lines.append(f"Reasons: {', '.join(all_reasons)}")
    lines.append("")
    lines.append("Confusion pairs (confused_as >= selected in the window, exposure >= floor):")
    # The reading carries this explicitly so the renderer does not re-apply
    # CONFUSION_PAIRS_WITHHELD from memory (field comment at its declaration).
    if reading.withheld:
        lines.append(f"- WITHHELD ({', '.join(reading.withheld)}) — this reading cannot answer")
    elif not reading.pairs:
        lines.append("- (none)")
    else:
        for pair in reading.pairs:
            confused = pair.confused
            head = (
                f"- {confused.name}: named-into {confused.confused_as} "
                f"(similarity {confused.similarity_min:.2f}..{confused.similarity_max:.2f}), "
                f"selected {confused.selected_window} in the window, "
                f"offered {confused.judged_exposure} times in the whole history"
            )
            if pair.partner is None:
                head += "; no second entry the variants resemble"
            else:
                head += (
                    f"; runs against {pair.partner.name} "
                    f"(selected {pair.partner.selected_window}, "
                    f"offered {pair.partner.judged_exposure}, "
                    f"weight {pair.partner_weight}, "
                    f"similarity {pair.partner_similarity_max:.2f})"
                )
            if pair.retire:
                head += f"; fewer selections: {pair.retire}"
            else:
                head += f"; no side listed ({pair.retire_blocked})"
            lines.append(head)
    lines.append("")
    strict_note = (
        " — WITHHELD, this half of the union is not in the file"
        if any(r.startswith("CONFUSION_NEVER_SELECTED_") for r in extra_reasons)
        else ""
    )
    lines.append(
        f"Never-selected strict (ADR-0097 D5, from the same week's "
        f"never-selected JSON): {len(never_selected_strict)} name(s){strict_note}"
    )
    lines.append("")
    lines.append(
        f"Candidate file: `{candidates_path}` — {len(candidate_files)} store filename(s), "
        "the union of the two populations. The store is unchanged; "
        "`adopt-staged --archive-names` is the Saturday gate's."
    )
    if not candidate_files:
        lines.append(
            "The file is empty this week; `--archive-names` rejects an empty file (exit 2), "
            "so it is not passed."
        )
    return "\n".join(lines)


__all__ = [
    "CONFUSION_EXPOSURE_FLOOR",
    "CONFUSION_MECHANISMS",
    "CONFUSION_PAIRS_WITHHELD",
    "CONFUSION_REASONS",
    "CONFUSION_WINDOW_DAYS",
    "ConfusedSkill",
    "ConfusionPair",
    "ConfusionReading",
    "archive_candidate_files",
    "confusion_reading_json",
    "format_confusion_findings",
    "read_confusion_pairs",
    "skill_files_by_name",
]
