"""Instrument: the per-window reading of ``skill-selection-*.jsonl`` (ADR-0071).

Read-only aggregate over the selection log the pass-1 selector writes
(:mod:`.skill_selection`): verdict mix, tokens saved, catalog-size regimes,
and the hallucinated-name tally with its three-mechanism split. Consumed by
``report --skill-selection`` and by the weekly chain; never by the agent.

Instrument, not gate: nothing here feeds a decision the runtime makes. The
one trust decision it does own is ``include_rejected_names`` -- see
:func:`format_skill_selection_report`.
"""

from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Literal, TypeAlias

import numpy as np

from ._io import (
    scrub_control,
)
from .selection_window import (
    _is_int,
    _is_prose,
    _iter_selection_days,
    _SelectionDayFile,
    _tokens,
    resolve_selection_window,
)
from .skill_selection import _NAME_MAX_CHARS, SkillCatalogEntry, load_skill_catalog
from .text_utils import read_markdown_documents

logger = logging.getLogger(__name__)


# Rows of the rejected-name tally the report renders before summarising the
# rest. Bounds the *output*, never the reading — see the renderer.
_REJECTED_NAME_RENDER_LIMIT = 50


# Hallucination-mechanism split (T-SKILLSEL-REPORT-WINDOW, 2026-08-22). The
# rule is stated once, here, so a reader can re-derive every row:
#   1. whitespace or ``/`` in the name → prose, not a slug → ``value_layer``
#   2. a token outside the catalog vocabulary (frontmatter name +
#      description — the two scalars the pass-1 prompt is built from) that
#      does occur in the value layer (constitution / identity) → ``value_layer``
#   3. surface similarity to the nearest catalog name ≥ the floor → ``wordform``
#   4. otherwise → ``semantic`` (a different real word swapped in)
# Rule 2 abstains (``unclassified`` / ``value_layer_unavailable``) when no
# value-layer text was readable, and every rule but 1 abstains
# (``catalog_unavailable``) when there is no catalog to measure against.
# The floor is the third reading's (2026-08-22 §4.2); it is a reporting
# boundary, never a gate.
WORDFORM_SIMILARITY_FLOOR = 0.90


# Value-layer tokens shorter than this are function words and would match
# almost any slug fragment; the reference classifier used the same cut.
_VALUE_LAYER_TOKEN_MIN_CHARS = 4


HallucinationMechanism: TypeAlias = Literal["wordform", "semantic", "value_layer", "unclassified"]


@dataclass(frozen=True)
class SkillSelectionDay:
    """One UTC day of the window, so a reader can see regime changes instead
    of their average.

    Window-wide aggregates hid a rollout and a corpus tripling from two
    consecutive readings: the 2026-07-24 one reported 83.6% fail-open that
    was a single incident, and the 2026-08-08 one reported 51.5% enforced
    across a window whose second half was 100% and a 2.2% hallucination rate
    spanning a catalog that went 19 → 45. Both had to be re-derived by hand.
    A window only gets longer as the corpus grows, so the day is the unit
    the log is actually informative at.
    """

    date: str
    records: int
    judged: int
    enforced: int
    judged_empty: int
    hallucination_records: int
    distinct_selected: int

    @property
    def fell_back(self) -> int:
        """Records that did not reach a judgment, so injection stayed
        full-corpus: every ``fail_open_*`` plus ``empty_catalog`` and
        ``no_template``. Derived rather than counted so ``records`` has no
        silent residual — a column that named only the fail-open family
        would read as calm on a day the whole catalog went missing. Which
        fallback verdicts fired is in the window's ``verdicts`` tally."""
        return self.records - self.judged


@dataclass(frozen=True)
class RejectedNameTally:
    """One hallucinated name, how often it was emitted, and how far it sits
    from the nearest name actually in the catalog.

    The rate alone (``hallucination_records``) cannot separate the three
    mechanisms the 2026-08-08 reading found behind it — wordform variance
    on a name that *is* in the catalog (``identify-`` for ``identifying-``),
    substitution of a different word (``translate-`` for ``trace-``), and
    text bled in from elsewhere in the prompt (constitution clauses
    arriving as skill names). Distance to the nearest catalog entry
    separates them at a glance: near-1.0 is wordform, mid-range is
    substitution, low is bleed.

    Classified since 2026-08-22 (``mechanism``), after two consecutive
    readings re-derived the same split by hand: the rule is fixed and
    stated once at ``WORDFORM_SIMILARITY_FLOOR``, so the assignment is a
    reproducible reading, not a judgment. It still feeds nothing — the
    instrument reports, the human decides (ADR-0071 /
    ``read-only-instruments``) — and whenever an input the rule needs is
    missing the row abstains with a reason code instead of guessing.

    ``similarity`` is surface (orthographic) distance from ``difflib``, not
    embedding cosine — on purpose. The embedding layer exists to resolve
    "structural similarity hidden by vocabulary variation"
    (``embeddings.py``); here vocabulary variation *is* the signal, and a
    semantic measure would collapse the wordform and substitution cases
    into each other.
    """

    name: str
    # Emissions, not records: one judged record that emitted the same
    # bogus name twice counts twice, so this does not sum to
    # ``hallucination_records``.
    count: int
    # Nearest catalog name, or ``""`` both when the catalog could not be
    # read (``skills_dir=None``) and when nothing in it resembles the name
    # at all. The renderer tells those two apart; neither fabricates a
    # match.
    nearest: str
    # 0.0 when ``nearest`` is empty. Only ``WORDFORM_SIMILARITY_FLOOR``
    # reads it as a boundary, and that is a reporting bucket, not a gate.
    similarity: float
    # One of ``HallucinationMechanism``; ``unclassified`` carries a reason
    # code in ``mechanism_reason`` (``catalog_unavailable`` /
    # ``value_layer_unavailable``). ``mechanism_note`` is the evidence for
    # a value-layer / semantic call (the foreign tokens) — it contains
    # fragments of the name, so it renders only where the name does.
    mechanism: HallucinationMechanism = "unclassified"
    mechanism_reason: str = ""
    mechanism_note: str = ""


@dataclass(frozen=True)
class MechanismTally:
    """Emissions and distinct names per hallucination mechanism."""

    mechanism: HallucinationMechanism
    emissions: int
    distinct: int


@dataclass(frozen=True)
class CatalogRegime:
    """Judged records conditioned on the catalog size they were offered.

    The catalog moves under adopt / stocktake inside one window, and the
    third reading (2026-08-22 §4.1) found the hallucination rate tracks
    the regime, not the window: 0.6% at 19 entries, 20% at 45. The corpus
    token axis sits beside the entry count because those two moved in
    opposite directions exactly once (45 → 48 entries, 35,992 → 33,745
    tokens) and the next window has to say whether that pair reproduces.
    """

    catalog_count: int
    judged: int
    hallucination_records: int
    # Median of ``full_skill_tokens`` over the judged records that carried
    # an integer value; ``None`` when none did (``tokens_missing`` says how
    # many were dropped). Never imputed.
    full_skill_tokens_median: float | None
    tokens_missing: int
    first_date: str
    last_date: str


@dataclass
class _RegimeAccumulator:
    """Mutable per-``catalog_count`` counters while the window is read;
    frozen into ``CatalogRegime`` once it has been. Same shape as the
    ``day_*`` counters that become ``SkillSelectionDay``."""

    first_date: str
    last_date: str
    judged: int = 0
    hallucination_records: int = 0
    tokens: list[int] = field(default_factory=list)
    tokens_missing: int = 0


@dataclass(frozen=True)
class SkillSelectionReading:
    """Read-only aggregate over the shadow log (ADR-0071 instrument).

    Feeds no gate, ranking, or retrieval — it informs the operator's
    enforcement decision and points ``skill-stocktake`` at never-selected
    skills. Percentiles are computed over ``judged`` records only.
    """

    days: int
    records: int
    verdicts: tuple[tuple[str, int], ...]
    per_skill: tuple[tuple[str, int], ...]
    never_selected: tuple[str, ...]
    # ADR-0081: judged records whose answer included at least one
    # hallucinated (non-catalog) name — one of ADR-0076's four
    # enforcement criteria, surfaced in the report as a rate over judged.
    hallucination_records: int
    selected_count_p50: float
    selected_count_p90: float
    token_reduction_p50: float
    token_reduction_p90: float
    # The denominator every rate below is taken over. Held explicitly rather
    # than re-derived from ``verdicts`` at each call site, so a numerator and
    # its denominator cannot drift apart.
    judged_records: int
    # Records whose selection actually fed back into injection. The verdict
    # counts say the selector succeeded; only this says the success was
    # used. Reading the rollout off the verdicts alone is what produced the
    # "38% enforced" misreading that outlived a whole ledger entry.
    enforced_records: int
    # Judged records that selected nothing. A judgment, not a failure
    # (ADR-0081 Decision 3) — but it injects no skill bodies at all, and
    # ADR-0081 closed its rollout partly on this being zero, so it needs to
    # be visible rather than inferable from a selected_count buried in the
    # log.
    judged_empty_records: int
    per_day: tuple[SkillSelectionDay, ...]
    # ``never_selected`` names paired with how many *judged* records carried
    # them in the catalog. Without it the report can only tell the operator
    # to "check the records count first" while holding the only copy of it —
    # and a skill adopted yesterday is indistinguishable from one that has
    # been offered a thousand times and refused. Counted over judged records
    # only: a name offered to a selector that never answered was not refused.
    #
    # Matched on exact name, so a skill renamed mid-window reports the
    # exposure of its new name — near zero, i.e. it reads as newly adopted.
    # Any bulk rename would do exactly that; read the first window after
    # one with that in mind. (The frontmatter-name backfill that used to be
    # named here as pending was dropped on 2026-08-08 — it moved every
    # renamed name *away* from what the selector emits.)
    never_selected_exposure: tuple[tuple[str, int], ...]
    # Hallucinated names themselves, not just how many records had one.
    # Added 2026-08-08 after a third ad-hoc script was needed to answer a
    # question the instrument already held the data for.
    rejected_name_tally: tuple[RejectedNameTally, ...]
    # Whether a catalog was readable at all. Without it the reading cannot
    # tell "measured, and nothing resembled it" from "there was no ruler":
    # both leave ``RejectedNameTally.similarity`` at 0.0, and the first
    # render of this tally claimed the former in both cases — so an
    # unreadable ``skills_dir`` would have read as the value-layer-bleed
    # signature, which is the single worst misreading this tally can
    # produce (cross-model review, 2026-08-08).
    catalog_available: bool
    # Explicit UTC calendar bounds when the caller windowed by
    # ``since`` / ``until``; both ``None`` in ``days`` mode. ``days`` is then
    # the calendar length of the bounded window.
    window_since: str | None = None
    window_until: str | None = None
    # Judged records bucketed by ``catalog_count``, ascending.
    catalog_regimes: tuple[CatalogRegime, ...] = ()
    # Judged records with no integer ``catalog_count`` — left out of the
    # regime table and reported, not folded into a bucket.
    catalog_count_missing: int = 0
    mechanism_tally: tuple[MechanismTally, ...] = ()
    # ``None`` when value-layer text was read; otherwise the reason code the
    # abstaining rows carry (``value_layer_not_configured`` when the caller
    # passed no paths, ``value_layer_unreadable`` when none could be read).
    value_layer_reason: str | None = "value_layer_not_configured"
    value_layer_files: int = 0
    # Configured value-layer paths that yielded no text (basenames only —
    # a home directory is not this instrument's to print). Non-empty with
    # ``value_layer_reason is None`` is the partial case: the split ran
    # against an incomplete vocabulary and says so.
    value_layer_missing: tuple[str, ...] = ()


def _read_value_layer_vocabulary(
    paths: tuple[Path, ...],
) -> tuple[frozenset[str] | None, int, tuple[str, ...]]:
    """Tokens (≥ ``_VALUE_LAYER_TOKEN_MIN_CHARS``) of every readable ``*.md``
    under ``paths`` — a directory through ``read_markdown_documents`` (the
    file rules of every other value-layer reader in core), a file as
    itself. Read-only.

    Returns ``(vocabulary, files read, paths that yielded nothing)``.
    ``vocabulary`` is ``None`` when no file could be read at all, so the
    caller can tell "configured but unreadable" from "nothing configured";
    the third element names the *partial* case — a root that yielded
    nothing, or a directory that yielded fewer documents than it holds
    ``*.md`` files. That case is the one that silently produces wrong
    readings: half a value layer still classifies, and a token living only
    in the missing half reads as ``semantic``.
    """
    tokens: set[str] = set()
    files = 0
    missing: list[str] = []
    for root in paths:
        before = files
        expected = 0
        try:
            if root.is_dir():
                texts = [raw for _, raw, _ in read_markdown_documents(root)]
                # ``read_markdown_documents`` skips unreadable files and
                # drops empty-bodied ones, so "some text came back" is not
                # "the directory was read": a clause file lost to
                # permissions leaves its vocabulary out while the count
                # still looks healthy.
                expected = len([f for f in root.glob("*.md") if not f.name.startswith(".")])
            elif root.is_file():
                # Decoding failures are a ValueError, not an OSError: an
                # identity file with one bad byte must abstain here, not
                # take the whole reading down through the caller's
                # degrade path.
                texts = [root.read_text(encoding="utf-8")]
            else:
                texts = []
        except (OSError, UnicodeDecodeError):
            logger.warning("skill selection reading: unreadable value-layer path %s", root.name)
            texts = []
        for text in texts:
            files += 1
            tokens |= _tokens(text, min_chars=_VALUE_LAYER_TOKEN_MIN_CHARS)
        if files == before:
            logger.warning("skill selection reading: value-layer path %s read nothing", root.name)
            missing.append(root.name)
        elif files - before < expected:
            logger.warning(
                "skill selection reading: value-layer path %s read %d of %d file(s)",
                root.name,
                files - before,
                expected,
            )
            missing.append(root.name)
    if not files:
        return None, 0, tuple(missing)
    return frozenset(tokens), files, tuple(missing)


def classify_hallucination(
    name: str,
    similarity: float,
    *,
    catalog_vocabulary: frozenset[str] | None,
    value_layer_vocabulary: frozenset[str] | None,
) -> tuple[HallucinationMechanism, str, str]:
    """Apply the four-rule split documented at ``WORDFORM_SIMILARITY_FLOOR``.

    Returns ``(mechanism, reason, note)``. ``catalog_vocabulary=None``
    means there was no catalog (no ruler) and ``value_layer_vocabulary=None``
    means no value-layer text was readable; each abstains exactly the rules
    that need it, nothing more.
    """
    if _is_prose(name):
        return "value_layer", "", "prose, not a slug"
    if catalog_vocabulary is None:
        return "unclassified", "catalog_unavailable", ""
    # Only tokens long enough to exist in the value-layer vocabulary are
    # tested against it — otherwise a 3-char foreign token would be reported
    # as "not in value layer" without ever having been looked up.
    foreign = sorted(
        t for t in _tokens(name) - catalog_vocabulary if len(t) >= _VALUE_LAYER_TOKEN_MIN_CHARS
    )
    if foreign:
        if value_layer_vocabulary is None:
            # Rule 3 needs no value layer, so check it before abstaining: a
            # misspelling *is* a token outside the catalog vocabulary, and
            # abstaining first made the weekly packet (which passes no
            # value-layer paths) call `unclassified` what the terminal
            # report called `wordform` — the same log line, two answers.
            # Only names far from every catalog entry, where the choice is
            # genuinely value_layer vs semantic, still abstain. On the
            # 2026-08-09..22 window no value-layer name sits at or above the
            # floor, so this costs no accuracy there; a name that did would
            # read as wordform without the value layer and value_layer with
            # it, which the reason code makes visible.
            if similarity >= WORDFORM_SIMILARITY_FLOOR:
                return "wordform", "", ""
            return "unclassified", "value_layer_unavailable", ""
        bled = [t for t in foreign if t in value_layer_vocabulary]
        if bled:
            return "value_layer", "", "foreign token(s) present in value layer: " + ",".join(bled)
    if similarity >= WORDFORM_SIMILARITY_FLOOR:
        return "wordform", "", ""
    note = ("foreign token(s) not in value layer: " + ",".join(foreign)) if foreign else ""
    return "semantic", "", note


@dataclass(frozen=True)
class _WindowTally:
    """What one pass over the window knows before the catalog is resolved.

    Module-private and never crossing the process boundary: it is the raw
    material :class:`SkillSelectionReading` is computed from, carried in one
    value so the walk and the classification can be read apart.
    """

    verdict_counts: dict[str, int]
    skill_counts: dict[str, int]
    selected_counts: list[int]
    reductions: list[int]
    exposure_counts: dict[str, int]
    rejected_counts: dict[str, int]
    days_seen: list[SkillSelectionDay]
    regimes: dict[int, _RegimeAccumulator]
    records: int
    judged_records: int
    hallucination_records: int
    enforced_records: int
    judged_empty_records: int
    catalog_count_missing: int


def _pct(values: list[int], q: float) -> float:
    """Percentile over a possibly empty sample; empty reads 0.0."""
    if not values:
        return 0.0
    return float(np.percentile(np.asarray(values, dtype=float), q))


def _tally_exposure(rec: dict[str, Any], exposure_counts: dict[str, int]) -> None:
    """Count one judged record's ``catalog_names`` as exposure."""
    names = rec.get("catalog_names")
    if isinstance(names, list):
        for name in names:
            if isinstance(name, str):
                exposure_counts[name] = exposure_counts.get(name, 0) + 1


def _tally_rejected_names(rec: dict[str, Any], rejected_counts: dict[str, int]) -> None:
    """Count one judged record's usable ``rejected_names``.

    Counted separately from the record tally at the call site: a record
    whose ``rejected_names`` is truthy but unusable (wrong type, non-string
    entries) still *is* a hallucination record. Folding the two would let a
    malformed field quietly lower the rate.
    """
    rejected = rec.get("rejected_names")
    if not isinstance(rejected, list):
        return
    for name in rejected:
        if not isinstance(name, str):
            continue
        clean = scrub_control(name, _NAME_MAX_CHARS)
        if not clean:
            continue
        rejected_counts[clean] = rejected_counts.get(clean, 0) + 1


def _tally_regime(
    rec: dict[str, Any],
    *,
    date_part: str,
    regimes: dict[int, _RegimeAccumulator],
) -> bool:
    """Fold one judged record into its ``catalog_count`` bucket.

    Returns whether the record carried an integer count — a ``False`` is the
    ``catalog_count_missing`` residual the table reports rather than folds.
    """
    count = rec.get("catalog_count")
    if not _is_int(count):
        return False
    regime = regimes.setdefault(count, _RegimeAccumulator(date_part, date_part))
    regime.judged += 1
    regime.hallucination_records += 1 if rec.get("rejected_names") else 0
    full = rec.get("full_skill_tokens")
    if _is_int(full):
        regime.tokens.append(full)
    else:
        regime.tokens_missing += 1
    regime.last_date = date_part
    return True


def _tally_selected(selected: list, skill_counts: dict[str, int], day_selected: set[str]) -> None:
    """Count one record's selected names into the window and the day."""
    for name in selected:
        skill_counts[name] = skill_counts.get(name, 0) + 1
        day_selected.add(name)


def _record_reduction(rec: dict) -> int | None:
    """The record's token reduction, or ``None`` when either side is unusable."""
    full = rec.get("full_skill_tokens")
    would_be = rec.get("would_be_skill_tokens")
    if _is_int(full) and _is_int(would_be):
        return full - would_be
    return None


@dataclass(frozen=True)
class _DayScan:
    """One day's contribution to the window tally, plus its per-day summary.

    The window-level collections (verdicts, skill counts, exposure, rejected
    names, regimes, reductions) are mutated in place by :func:`_scan_selection_day`
    because they are shared across days; only the scalars a day *adds* travel
    back here.
    """

    records: int
    judged: int
    enforced: int
    judged_empty: int
    hallucination_records: int
    catalog_count_missing: int
    summary: SkillSelectionDay


@dataclass
class _WindowCollections:
    """Mutable window-wide collections while the window is read; folded into
    ``_WindowTally`` once it has been. Same ROLE as :class:`_RegimeAccumulator`
    (a scratch accumulator, not a DTO, which is why neither is frozen) — not the
    same shape: that one is per-``catalog_count``, this one is window-wide.

    They live in one object rather than seven parameters because they are one
    thing: the state every day adds to. Passing them individually made
    :func:`_scan_selection_day` an eight-argument function whose signature said
    nothing a reader could use.
    """

    verdict_counts: dict[str, int] = field(default_factory=dict)
    skill_counts: dict[str, int] = field(default_factory=dict)
    selected_counts: list[int] = field(default_factory=list)
    reductions: list[int] = field(default_factory=list)
    # Exposure is counted for every catalogued name, not just the ones that
    # end up never-selected: which names those are is only known after the
    # whole window has been read, and the current catalog is resolved later
    # still.
    exposure_counts: dict[str, int] = field(default_factory=dict)
    # Names the selector emitted that matched nothing. Scrubbed at read time
    # as well as at the write seam: the writer sanitises what *it* appends,
    # but this reader parses a file on disk, and the global rule treats the
    # agent's own store as untrusted regardless of who wrote it.
    rejected_counts: dict[str, int] = field(default_factory=dict)
    regimes: dict[int, _RegimeAccumulator] = field(default_factory=dict)


def _scan_selection_day(day_file: _SelectionDayFile, acc: _WindowCollections) -> _DayScan:
    """Fold one day's records into the window collections and count the day."""
    date_part = day_file.date_part
    day_records = 0
    day_judged = 0
    day_enforced = 0
    day_judged_empty = 0
    day_hallucinations = 0
    day_catalog_missing = 0
    day_selected: set[str] = set()
    for rec in day_file.records:
        day_records += 1
        verdict = str(rec.get("verdict", "unknown"))
        acc.verdict_counts[verdict] = acc.verdict_counts.get(verdict, 0) + 1
        if verdict != "judged":
            continue
        # Everything below is judged-only, deliberately. Every rate
        # this instrument reports is a rate over judged records, so a
        # numerator counted on the other side of this line would be
        # measured against a population it is not drawn from — which
        # is exactly how "in catalog for 100 of 105 records" came to
        # describe a skill that had never once been judged.
        day_judged += 1
        if rec.get("enforced"):
            day_enforced += 1
        _tally_exposure(rec, acc.exposure_counts)
        selected = rec.get("selected") or []
        _tally_selected(selected, acc.skill_counts, day_selected)
        acc.selected_counts.append(len(selected))
        if not selected:
            day_judged_empty += 1
        if rec.get("rejected_names"):
            day_hallucinations += 1
        _tally_rejected_names(rec, acc.rejected_counts)
        reduction = _record_reduction(rec)
        if reduction is not None:
            acc.reductions.append(reduction)
        if not _tally_regime(rec, date_part=date_part, regimes=acc.regimes):
            day_catalog_missing += 1
    return _DayScan(
        records=day_records,
        judged=day_judged,
        enforced=day_enforced,
        judged_empty=day_judged_empty,
        hallucination_records=day_hallucinations,
        catalog_count_missing=day_catalog_missing,
        summary=SkillSelectionDay(
            date=date_part,
            records=day_records,
            judged=day_judged,
            enforced=day_enforced,
            judged_empty=day_judged_empty,
            hallucination_records=day_hallucinations,
            distinct_selected=len(day_selected),
        ),
    )


def _scan_selection_window(log_dir: Path, cutoff: date, upper: date | None) -> _WindowTally:
    """One pass over the window's ``skill-selection-*.jsonl`` files."""
    acc = _WindowCollections()
    records = 0
    judged_records = 0
    hallucination_records = 0
    enforced_records = 0
    judged_empty_records = 0
    days_seen: list[SkillSelectionDay] = []
    catalog_count_missing = 0
    for day_file in _iter_selection_days(
        log_dir, lambda d: d >= cutoff and (upper is None or d <= upper)
    ):
        if not day_file.readable:
            continue
        day = _scan_selection_day(day_file, acc)
        records += day.records
        judged_records += day.judged
        enforced_records += day.enforced
        judged_empty_records += day.judged_empty
        hallucination_records += day.hallucination_records
        catalog_count_missing += day.catalog_count_missing
        if day.records:
            days_seen.append(day.summary)
    return _WindowTally(
        verdict_counts=acc.verdict_counts,
        skill_counts=acc.skill_counts,
        selected_counts=acc.selected_counts,
        reductions=acc.reductions,
        exposure_counts=acc.exposure_counts,
        rejected_counts=acc.rejected_counts,
        days_seen=days_seen,
        regimes=acc.regimes,
        records=records,
        judged_records=judged_records,
        hallucination_records=hallucination_records,
        enforced_records=enforced_records,
        judged_empty_records=judged_empty_records,
        catalog_count_missing=catalog_count_missing,
    )


def _catalog_vocabulary(
    catalog: tuple[SkillCatalogEntry, ...], exposure_counts: dict[str, int]
) -> frozenset[str] | None:
    """What the pass-1 prompt actually shows (name + description), plus every
    name the window's records carried, so a name renamed away mid-window is
    still catalog-derived rather than foreign. Names only for the ruler in
    :func:`_rejected_name_tallies` — that stays the current catalog so the
    tally's nearest and the split's similarity agree. ``None`` when there was
    no catalog to read."""
    if not catalog:
        return None
    vocabulary: set[str] = set()
    for entry in catalog:
        vocabulary |= _tokens(f"{entry.name} {entry.description}")
    for name in exposure_counts:
        vocabulary |= _tokens(name)
    return frozenset(vocabulary)


def _rejected_name_tallies(
    rejected_counts: dict[str, int],
    catalog_names: list[str],
    *,
    catalog_vocabulary: frozenset[str] | None,
    value_layer_vocabulary: frozenset[str] | None,
) -> tuple[RejectedNameTally, ...]:
    """One row per distinct rejected name, emissions descending."""

    def _nearest(name: str) -> tuple[str, float]:
        """Closest catalog name by surface similarity, with its ratio.

        No cutoff: a name with no close match is exactly the interesting
        case (value-layer bleed), so its distance is worth reporting.

        Scored in one explicit pass rather than ``get_close_matches`` plus
        a second ``ratio()``. ``SequenceMatcher.ratio()`` is **not
        symmetric**, and the two calls take their operands in opposite
        orders — so on roughly 1% of realistic kebab-case names the
        printed similarity would not be the score that picked the winner,
        and a reader comparing rows would see an inconsistency with no
        way to explain it. That lands precisely on the wordform-versus-
        substitution boundary this tally exists to discriminate.

        Ties break toward the alphabetically first name; a name that
        matches nothing at all reports no nearest rather than the
        alphabetical accident ``get_close_matches`` would hand back.
        """
        if not catalog_names:
            return "", 0.0
        matcher = difflib.SequenceMatcher(autojunk=False)
        matcher.set_seq2(name)
        best_name, best_ratio = "", 0.0
        for candidate in sorted(catalog_names):
            matcher.set_seq1(candidate)
            ratio = matcher.ratio()
            if ratio > best_ratio:
                best_name, best_ratio = candidate, ratio
        return best_name, best_ratio

    def _tally(name: str, count: int) -> RejectedNameTally:
        nearest, similarity = _nearest(name)
        mechanism, reason, note = classify_hallucination(
            name,
            similarity,
            catalog_vocabulary=catalog_vocabulary,
            value_layer_vocabulary=value_layer_vocabulary,
        )
        return RejectedNameTally(
            name=name,
            count=count,
            nearest=nearest,
            similarity=similarity,
            mechanism=mechanism,
            mechanism_reason=reason,
            mechanism_note=note,
        )

    return tuple(
        _tally(name, count)
        for name, count in sorted(rejected_counts.items(), key=lambda kv: (-kv[1], kv[0]))
    )


def _mechanism_tallies(
    rejected_name_tally: tuple[RejectedNameTally, ...],
) -> tuple[MechanismTally, ...]:
    """Emissions and distinct names per mechanism, emissions descending."""
    mechanism_rows: dict[HallucinationMechanism, list[int]] = {}
    for entry in rejected_name_tally:
        mechanism_rows.setdefault(entry.mechanism, []).append(entry.count)
    return tuple(
        MechanismTally(mechanism=m, emissions=sum(counts), distinct=len(counts))
        for m, counts in sorted(mechanism_rows.items(), key=lambda kv: (-sum(kv[1]), kv[0]))
    )


def _catalog_regime_rows(regimes: dict[int, _RegimeAccumulator]) -> tuple[CatalogRegime, ...]:
    """Freeze the per-``catalog_count`` accumulators, ascending by size."""
    return tuple(
        CatalogRegime(
            catalog_count=count,
            judged=acc.judged,
            hallucination_records=acc.hallucination_records,
            full_skill_tokens_median=_pct(acc.tokens, 50) if acc.tokens else None,
            tokens_missing=acc.tokens_missing,
            first_date=acc.first_date,
            last_date=acc.last_date,
        )
        for count, acc in sorted(regimes.items())
    )


def read_skill_selection_log(
    log_dir: Path,
    *,
    days: int | None = None,
    since: date | None = None,
    until: date | None = None,
    skills_dir: Path | None,
    value_layer_paths: tuple[Path, ...] = (),
) -> SkillSelectionReading:
    """Aggregate ``skill-selection-*.jsonl`` files within the window.

    The window is either ``days`` (files dated on or after ``today - days``,
    unchanged since the instrument shipped) or an explicit, inclusive UTC
    calendar range ``since`` .. ``until`` (``until`` defaults to today); the
    two are exclusive. Files are selected by the date embedded in the
    filename (same daily rotation as LLM telemetry); broken lines are
    skipped, never fatal. ``never_selected`` is computed against the
    *current* catalog, so a skill adopted yesterday with no selections yet
    will appear — read it alongside ``records`` before drawing conclusions.
    ``value_layer_paths`` (constitution dir, identity file) are read, never
    written, and only feed the mechanism split of rejected names.
    """
    cutoff, upper, window_days = resolve_selection_window(days, since, until)
    tally = _scan_selection_window(log_dir, cutoff, upper)

    catalog = load_skill_catalog(skills_dir)
    catalog_names = [e.name for e in catalog]
    never_selected = tuple(name for name in catalog_names if name not in tally.skill_counts)
    never_selected_exposure = tuple(
        (name, tally.exposure_counts.get(name, 0)) for name in never_selected
    )
    catalog_vocabulary = _catalog_vocabulary(catalog, tally.exposure_counts)
    value_layer_vocabulary, value_layer_files, value_layer_missing = (
        _read_value_layer_vocabulary(value_layer_paths) if value_layer_paths else (None, 0, ())
    )
    value_layer_reason = (
        None
        if value_layer_vocabulary is not None
        else ("value_layer_unreadable" if value_layer_paths else "value_layer_not_configured")
    )
    rejected_name_tally = _rejected_name_tallies(
        tally.rejected_counts,
        catalog_names,
        catalog_vocabulary=catalog_vocabulary,
        value_layer_vocabulary=value_layer_vocabulary,
    )

    return SkillSelectionReading(
        days=window_days,
        records=tally.records,
        verdicts=tuple(sorted(tally.verdict_counts.items())),
        per_skill=tuple(sorted(tally.skill_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        never_selected=never_selected,
        hallucination_records=tally.hallucination_records,
        selected_count_p50=_pct(tally.selected_counts, 50),
        selected_count_p90=_pct(tally.selected_counts, 90),
        token_reduction_p50=_pct(tally.reductions, 50),
        token_reduction_p90=_pct(tally.reductions, 90),
        judged_records=tally.judged_records,
        enforced_records=tally.enforced_records,
        judged_empty_records=tally.judged_empty_records,
        per_day=tuple(sorted(tally.days_seen, key=lambda d: d.date)),
        never_selected_exposure=never_selected_exposure,
        rejected_name_tally=rejected_name_tally,
        catalog_available=bool(catalog_names),
        window_since=cutoff.isoformat() if upper is not None else None,
        window_until=upper.isoformat() if upper is not None else None,
        catalog_regimes=_catalog_regime_rows(tally.regimes),
        catalog_count_missing=tally.catalog_count_missing,
        mechanism_tally=_mechanism_tallies(rejected_name_tally),
        value_layer_reason=value_layer_reason,
        value_layer_files=value_layer_files,
        value_layer_missing=value_layer_missing,
    )


def _render_per_day(reading: SkillSelectionReading) -> list[str]:
    """The per-day table, empty when the window held no readable day."""
    if not reading.per_day:
        return []
    lines = [
        "",
        "Per day (a window-wide average hides the day a regime changed):",
        f"{'date':<12}{'records':>9}{'judged':>8}{'fell-back':>11}"
        f"{'enforced':>10}{'jd-empty':>10}{'halluc':>8}{'distinct':>10}",
    ]
    for day in reading.per_day:
        lines.append(
            f"{day.date:<12}{day.records:>9}{day.judged:>8}{day.fell_back:>11}"
            f"{day.enforced:>10}{day.judged_empty:>10}"
            f"{day.hallucination_records:>8}{day.distinct_selected:>10}"
        )
    lines.append(
        "  records = judged + fell-back; all other columns count judged "
        "records only. Which fallback verdicts fired is in `Verdicts` above."
    )
    return lines


def _render_catalog_regimes(reading: SkillSelectionReading) -> list[str]:
    """The by-catalog-size table, plus the residual it does not fold in."""
    if not (reading.catalog_regimes or reading.catalog_count_missing):
        return []
    lines = [
        "",
        "By catalog size (the rate tracks the regime, not the window):",
        f"{'catalog':>8}{'judged':>8}{'halluc':>8}{'rate':>9}{'tok p50':>10}  days",
    ]
    for regime in reading.catalog_regimes:
        rate = regime.hallucination_records / regime.judged if regime.judged else 0.0
        if regime.full_skill_tokens_median is None:
            tokens_text = "—"
        else:
            tokens_text = f"{regime.full_skill_tokens_median:,.0f}"
        span = (
            regime.first_date
            if regime.first_date == regime.last_date
            else f"{regime.first_date}..{regime.last_date}"
        )
        missing = (
            f" (full_skill_tokens_missing={regime.tokens_missing})" if regime.tokens_missing else ""
        )
        lines.append(
            f"{regime.catalog_count:>8}{regime.judged:>8}{regime.hallucination_records:>8}"
            f"{rate:>9.1%}{tokens_text:>10}  {span}{missing}"
        )
    if reading.catalog_count_missing:
        lines.append(
            f"  catalog_count_missing={reading.catalog_count_missing} judged records carried "
            "no integer catalog_count and are excluded from this table"
        )
    lines.append(
        "  halluc = judged records with ≥1 rejected name; tok p50 = median "
        "full_skill_tokens the record baked in (corpus size as offered)."
    )
    return lines


def _render_mechanism_tally(reading: SkillSelectionReading) -> list[str]:
    """The mechanism split, with the abstain notes that bound how it reads."""
    if not reading.mechanism_tally:
        return []
    lines = ["", "Hallucination by mechanism (emissions over distinct rejected names):"]
    total_emissions = sum(m.emissions for m in reading.mechanism_tally)
    for tally in reading.mechanism_tally:
        share = tally.emissions / total_emissions if total_emissions else 0.0
        lines.append(
            f"- {tally.mechanism}: {tally.emissions} emissions ({share:.1%}), "
            f"{tally.distinct} distinct"
        )
    if not reading.catalog_available:
        lines.append(
            "  no catalog to measure against: every non-prose name is "
            "`unclassified` (catalog_unavailable), not classified."
        )
    if reading.value_layer_reason is not None:
        lines.append(
            f"  value-layer rule abstained: {reading.value_layer_reason} — names with "
            "tokens outside the catalog vocabulary are `unclassified`, not `semantic`."
        )
    else:
        missing = (
            f"; read nothing from {', '.join(reading.value_layer_missing)}"
            if reading.value_layer_missing
            else ""
        )
        lines.append(
            f"  value layer read from {reading.value_layer_files} file(s) "
            f"(constitution / identity, read-only){missing}."
        )
    lines.append(
        "  Both rulers are the catalog and value layer as they stand *now*, not "
        "as each record saw them: a window spanning a rename, a rewritten "
        "description or a constitution amendment classifies older emissions "
        "against today's text. The audit records carry `catalog_names` (folded "
        "in above) but no description or value-layer snapshot, so this reading "
        "is not replayable across such a change — read a regime boundary in the "
        "table above as a boundary here too (cross-model review, 2026-08-22)."
    )
    return lines


def _render_rejected_names(
    reading: SkillSelectionReading, *, include_rejected_names: bool
) -> list[str]:
    """The rejected-name rows. ``include_rejected_names`` is the trust
    decision documented on :func:`format_skill_selection_report`."""
    if not reading.rejected_name_tally:
        return []
    lines = ["", "Rejected names (emitted, matched no catalog entry):"]
    if not include_rejected_names:
        lines.append(
            "  (names withheld — this renderer's default. They are model "
            "output shaped by untrusted input; `report --skill-selection` "
            "shows them. Shape below is catalog names and distances only.)"
        )
    shown = reading.rejected_name_tally[:_REJECTED_NAME_RENDER_LIMIT]
    for entry in shown:
        if entry.nearest:
            nearest_text = (
                f"nearest catalog name `{entry.nearest}` (similarity {entry.similarity:.2f})"
            )
        elif reading.catalog_available:
            # Measured against a real catalog and nothing came close:
            # the value-layer-bleed signature. Rendering this as
            # `nearest \`x\` (similarity 0.00)` read as a match claim.
            nearest_text = "no catalog name resembles it"
        else:
            # No ruler. Must not be reported as the line above — a
            # broken skills_dir would then read as bleed.
            nearest_text = "no catalog to compare against"
        # The name is the only untrusted half of the row; dropping it
        # still leaves the distance and which real skill it is near,
        # which is what "did wordform slips concentrate on three
        # skills, or is text bleeding in?" actually needs.
        head = f"{entry.name}: " if include_rejected_names else ""
        mechanism_text = entry.mechanism
        if entry.mechanism_reason:
            mechanism_text += f" ({entry.mechanism_reason})"
        # The note quotes tokens of the name: same trust boundary as
        # the name itself.
        if include_rejected_names and entry.mechanism_note:
            mechanism_text += f"; {entry.mechanism_note}"
        lines.append(f"- {head}{entry.count} emissions — {nearest_text} — {mechanism_text}")
    hidden = reading.rejected_name_tally[_REJECTED_NAME_RENDER_LIMIT:]
    if hidden:
        # Bounding the *rendering*, not the reading: the dataclass
        # still carries every row. Prose bleed — the degenerate mode
        # this tally exists to detect — is exactly the mode that emits
        # thousands of unique names, so an uncapped section would
        # explode the one artifact it is meant to inform. Silently
        # truncating would read as "that was all of it".
        lines.append(
            f"- … and {len(hidden)} more distinct names "
            f"({sum(e.count for e in hidden)} emissions), not shown"
        )
    lines.append(
        "  Counts are emissions, not records — one record can emit the same "
        "name twice, so these do not sum to the Hallucination line above. "
        "Similarity is surface (orthographic), not semantic: near 1.00 is a "
        "wordform slip on a name that IS in the catalog, mid-range is a "
        "different word, low means the text came from somewhere other than "
        "the catalog. The trailing bucket is the fixed four-rule split "
        f"(wordform floor {WORDFORM_SIMILARITY_FLOOR:.2f}); `unclassified` rows "
        "name the input the rule was missing."
    )
    return lines


def format_skill_selection_report(
    reading: SkillSelectionReading, *, include_rejected_names: bool = False
) -> str:
    """Render the reading. ``include_rejected_names`` is a trust decision.

    This renderer has two consumers with different trust requirements, and
    the difference is not phrasing — it is who reads the output:

    - ``report --skill-selection`` prints to a terminal for a human, who
      is the only reader that needs the hallucinated strings themselves
      (comparing their spelling against real names is the whole point of
      the tally). It passes ``include_rejected_names=True``.
    - ``scripts/weekly-analysis.sh`` pastes the same report into the
      weekly prompt, which an unattended chain reads before writing code
      patches (ADR-0085). It takes the default.

    A rejected name is, by definition, a string that matched nothing in
    the catalog: free text from a model whose prompt embeds untrusted post
    bodies. The 2026-08-08 reading measured this happening — 12% of
    rejected names were fragments bled from elsewhere in the prompt. Every
    other string this renderer emits comes from a closed, self-written
    vocabulary (catalog names via ``strip_to_printable``, fixed verdict
    tokens), so the tally would be the first arbitrary model output to
    reach that prompt. ADR-0083's precedent for the same tension — the
    cross-day duplicate scan — sends digests rather than content.

    The default is the restrictive one so a new caller is safe by
    omission, and the weekly script needs no knowledge of the boundary it
    is on the wrong side of.

    Withholding the names costs the weekly reader little: the *shape* of
    the tally — how many distinct names, how many emissions, and how far
    each sits from which real skill — is rendered either way, because the
    nearest name is a catalog name and the distance is a float.
    """
    if reading.window_since is not None:
        window_text = (
            f"{reading.window_since} .. {reading.window_until} UTC ({reading.days} calendar days)"
        )
    else:
        window_text = f"last {reading.days} days"
    lines = [
        "## Skill-selection reading (ADR-0076 instrument, ADR-0081 enforcement)",
        "",
        f"Window: {window_text} — {reading.records} records",
    ]
    if reading.verdicts:
        verdict_text = ", ".join(f"{v}: {n}" for v, n in reading.verdicts)
        lines.append(f"Verdicts: {verdict_text}")
    judged = reading.judged_records
    if judged:
        lines.append(
            f"Enforced: {reading.enforced_records}/{judged} judged "
            f"({reading.enforced_records / judged:.1%} fed back into injection)"
        )
        lines.append(
            f"Hallucination: {reading.hallucination_records}/{judged} judged "
            f"({reading.hallucination_records / judged:.1%} with rejected names)"
        )
        lines.append(
            f"Judged-empty: {reading.judged_empty_records}/{judged} judged "
            f"({reading.judged_empty_records / judged:.1%} injected no skill bodies)"
        )
    lines.append(
        "Selected per action: p50 "
        f"{reading.selected_count_p50:.1f} / p90 {reading.selected_count_p90:.1f}"
    )
    lines.append(
        "Would-be token reduction: p50 "
        f"≈{reading.token_reduction_p50:,.0f} tok / p90 "
        f"≈{reading.token_reduction_p90:,.0f} tok (audit C2 scale)"
    )
    lines.extend(_render_per_day(reading))
    lines.extend(_render_catalog_regimes(reading))
    if reading.per_skill:
        lines.append("")
        lines.append("Selection frequency:")
        for name, count in reading.per_skill:
            lines.append(f"- {name}: {count}")
    lines.extend(_render_mechanism_tally(reading))
    lines.extend(_render_rejected_names(reading, include_rejected_names=include_rejected_names))
    if reading.never_selected_exposure:
        lines.append("")
        # Deliberately not "candidates": this list is window-scoped, so most
        # of it is skills that were selected before the window opened
        # (dormant, ADR-0097 D5) and archiving one of those WOULD change
        # judged behaviour. Archive candidacy is decided by the whole-history
        # strict reading below, never by this line.
        lines.append("Never selected in window (window reading — not archive candidates):")
        for name, exposure in reading.never_selected_exposure:
            lines.append(f"- {name}: {format_never_selected_exposure(exposure, reading)}")
    return "\n".join(lines)


def format_never_selected_exposure(exposure: int, reading: SkillSelectionReading) -> str:
    """How often a never-selected skill was actually offered, in words.

    Shared by the two renderers of this reading (`report --skill-selection`
    and the stocktake usage section) so the surface where retirement is
    actually decided cannot keep the older, less informative phrasing.
    """
    if not reading.judged_records:
        return "no judged records in window — nothing was offered"
    if not exposure:
        return (
            f"never in catalog for any of {reading.judged_records} judged records "
            "(adopted after the window, or renamed since)"
        )
    return f"offered in {exposure} of {reading.judged_records} judged records, chosen 0"
