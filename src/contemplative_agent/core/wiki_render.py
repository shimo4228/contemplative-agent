"""The two derived pages the Proposer reads, drawn by code (RFC-0017 S1).

WikiSkill has the Maintainer write ``logs.md`` and ``skill-impact.md``. CA
does not: both are projections over logs the loop already writes, and a
projection an LLM composes is a second copy that can disagree with the first.
So they are rendered here, deterministically, and nobody has to ask whether
the page is current.

- :func:`render_evolution_log` — one line per insight candidate ever staged,
  with the decision it finally got and, if it has since been retired, what
  superseded it. Sources: ``logs/insight-staged.jsonl`` (the ADR-0074 theme
  ledger), ``logs/audit.jsonl`` (the ADR-0012 approval ledger), and the
  ``superseded_by:`` frontmatter of ``skills/.archive/`` (ADR-0097 D5).
- :func:`render_skill_impact` — per skill, how often it was selected, when
  last, and how often it was merely *offered*. The paper's column here is a
  verification score; CA has no ground truth, so selection is the only
  evidence of use there is (RFC-0017 D5), and the two columns are kept apart
  so a never-selected skill that has been offered a thousand times cannot be
  read as one adopted yesterday.

Both degrade rather than abort. A malformed line is counted and skipped —
the ``observed_injection_outcomes`` posture — and the count is printed, so a
reading taken over a half-corrupt log says so instead of looking calm. Both
return a heading on empty input: an empty string in a prompt is
indistinguishable from a template that failed to render.

Everything these read is untrusted: candidate names come from an LLM that
read untrusted episodes. Names are passed through ``scrub_control`` before
they reach a rendered line, because a newline in a name forges an extra row
(the ``skill-selection`` rejected-name tally, 2026-08-08). The
``prompt_b64`` / ``output_b64`` payloads in the selection log are never
touched: this module needs names and counts, and reading the bodies would
put untrusted prose into a page the Proposer is prompted with.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from ._io import scrub_control
from .selection_window import _iter_selection_days
from .text_utils import split_frontmatter

logger = logging.getLogger(__name__)

_NAME_MAX_CHARS = 64
_ABSENT = "-"


def _read_jsonl_objects(path: Path) -> tuple[list[dict[str, Any]], int]:
    """Every JSON object in *path*, plus how many lines were not one.

    A missing file is not a fault (zero rows, zero skipped): the loop writes
    these ledgers lazily and a fresh ``MOLTBOOK_HOME`` has neither. An
    unreadable one is — it is counted as a single skipped line so the
    heading cannot claim a clean read.

    ``ValueError`` alongside ``OSError`` because one bad byte raises
    ``UnicodeDecodeError``, which is not an ``OSError`` — the gap that has
    taken out readings in this codebase before (``_iter_selection_days``).
    """
    if not path.is_file():
        return [], 0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        logger.warning("wiki render: unreadable %s", path.name)
        return [], 1
    rows: list[dict[str, Any]] = []
    skipped = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            skipped += 1
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
        else:
            skipped += 1
    return rows, skipped


def _clean(value: object, fallback: str = _ABSENT) -> str:
    """A log field as one bounded, single-line, control-free cell."""
    text = scrub_control(str(value), _NAME_MAX_CHARS)
    return text or fallback


def _final_decisions(audit_rows: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    """``basename -> (ts, decision)`` for the LATEST row naming each file.

    Latest, not first: a candidate is staged, then held, then approved, and
    only the last of those is its fate. Keyed on the basename because the
    ledger records the staged path and the approval records the adopted one,
    and the filename is the only field both carry.
    """
    latest: dict[str, tuple[str, str]] = {}
    for row in audit_rows:
        path = row.get("path")
        decision = row.get("decision")
        if not isinstance(path, str) or not isinstance(decision, str):
            continue
        name = Path(path).name
        ts = str(row.get("ts", ""))
        if name not in latest or ts >= latest[name][0]:
            latest[name] = (ts, decision)
    return latest


def _superseded_by(data_root: Path) -> dict[str, str]:
    """``archived filename -> the successor named in its frontmatter``.

    ``cli/skill_archive`` keeps the source's own filename on the way into
    ``.archive/``, so the key here is the same one the staging ledger holds.
    A missing archive directory is the normal state of a store where nothing
    has been superseded yet.
    """
    archive = data_root / "skills" / ".archive"
    if not archive.is_dir():
        return {}
    out: dict[str, str] = {}
    for path in sorted(archive.glob("*.md")):
        try:
            frontmatter, _ = split_frontmatter(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for line in frontmatter.split("\n"):
            key, sep, value = line.partition(":")
            if sep and key.strip() == "superseded_by":
                successor = _clean(value.strip(), "")
                if successor:
                    out[path.name] = successor
                break
    return out


def render_evolution_log(data_root: Path, *, until: date | None = None) -> str:
    """The candidate history the Proposer reads before proposing (RFC-0017 D5).

    One row per staged candidate, oldest first, so "this theme has been
    tried and rejected twice" is visible without the model having to hold
    the history itself. Rows the ledger cannot key (no ``ts``, no
    ``filename``) are counted as skipped rather than rendered blank — a row
    with no identity teaches the reader nothing and costs it a line of
    budget.

    ``until`` (inclusive) hides candidates staged after that date. Default
    ``None`` = everything, which is what a live run wants; the offline
    replay (RFC-0017 S4) passes the day being replayed so a 2026-07-13
    iteration cannot read a decision made in August. Rows dropped this way
    are NOT counted as skipped: they are outside the window, not unusable,
    and conflating the two would make the heading report a corrupt ledger.

    Only the staging date is windowed. A candidate's ``final decision`` and
    its ``superseded by`` successor still come from the whole ledger, so a
    replayed row can show an outcome that had not happened yet on the day.
    That is a named deviation rather than an oversight: reconstructing the
    approval state of every past day would mean replaying the human gate,
    which is the one thing the replay cannot do.
    """
    staged_rows, skipped = _read_jsonl_objects(data_root / "logs" / "insight-staged.jsonl")
    audit_rows, audit_skipped = _read_jsonl_objects(data_root / "logs" / "audit.jsonl")
    skipped += audit_skipped

    decisions = _final_decisions(audit_rows)
    superseded = _superseded_by(data_root)

    entries: list[tuple[str, str]] = []
    cutoff = until.isoformat() if until is not None else None
    for row in staged_rows:
        ts = row.get("ts")
        filename = row.get("filename")
        if not isinstance(ts, str) or not isinstance(filename, str) or not ts or not filename:
            skipped += 1
            continue
        if cutoff is not None and ts[:10] > cutoff:
            continue
        name = _clean(row.get("name", Path(filename).stem))
        decision = decisions.get(Path(filename).name, ("", _ABSENT))[1]
        entries.append(
            (ts, f"{ts[:10]} | {name} | {_clean(decision)} | {superseded.get(filename, _ABSENT)}")
        )

    entries.sort(key=lambda item: item[0])
    header = f"# Evolution log ({len(entries)} candidates, {skipped} unusable lines skipped)"
    columns = "date | candidate | final decision | superseded by"
    return "\n".join([header, "", columns] + [line for _, line in entries]) + "\n"


def _string_names(value: object) -> list[str]:
    """The string entries of a log list field, or nothing.

    ``selected`` and ``catalog_names`` are written from LLM output, so a
    nested object or a number in either is a shape the reading has to
    survive rather than an impossibility. Dropping it silently is right
    here: this is a projection, and the record-level fault tally lives with
    the parse in ``_iter_selection_days``.
    """
    if not isinstance(value, list):
        return []
    return [entry for entry in value if isinstance(entry, str)]


def _window_predicate(since: date | None, until: date | None) -> Callable[[date], bool] | None:
    """The day filter for a two-sided window, or ``None`` when it is open.

    ``None`` rather than a tautological ``lambda`` so the unbounded case stays
    the same object identity ``_iter_selection_days`` already special-cases.
    """
    if since is None and until is None:
        return None

    def keep(file_date: date) -> bool:
        return (since is None or file_date >= since) and (until is None or file_date <= until)

    return keep


@dataclass(frozen=True)
class _ImpactTally:
    """The three per-skill columns plus the two denominators, in one pass."""

    selections: dict[str, int]
    last_selected: dict[str, str]
    offered: dict[str, int]
    records: int
    skipped: int


def _tally_selection_window(log_dir: Path, keep: Callable[[date], bool] | None) -> _ImpactTally:
    """One pass over the window's selection logs.

    Only ``judged`` records contribute: a name offered to a selector that
    never answered was not refused, and counting it would let a week of
    fail-open records read as a week of rejection. Non-string entries in
    either list are skipped — the fields are written from LLM output, and a
    reading that crashes on one is not a reading.
    """
    selections: dict[str, int] = {}
    last_selected: dict[str, str] = {}
    offered: dict[str, int] = {}
    records = 0
    skipped = 0

    for day in _iter_selection_days(log_dir, keep):
        skipped += day.malformed_rows
        if not day.readable:
            skipped += 1
            continue
        for record in day.records:
            records += 1
            if record.get("verdict") != "judged":
                continue
            for name in _string_names(record.get("catalog_names")):
                offered[name] = offered.get(name, 0) + 1
            for name in _string_names(record.get("selected")):
                selections[name] = selections.get(name, 0) + 1
                last_selected[name] = day.date_part

    return _ImpactTally(selections, last_selected, offered, records, skipped)


def render_skill_impact(data_root: Path, *, since: date | None, until: date | None = None) -> str:
    """Per-skill selection evidence — the paper's ``skill-impact.md`` (D5).

    Three columns, and deliberately not one score. ``selections`` is how
    often the pass-1 selector chose the skill; ``last selected`` dates that
    evidence, so a skill that was useful in July and untouched since reads
    differently from one selected yesterday; ``offered`` is how many judged
    records carried it in the catalog at all, which is the denominator
    without which a zero cannot be told from an absence.

    ``since`` and ``until`` (both inclusive, UTC calendar) bound the window;
    ``None`` on either end leaves it open. ``until`` exists for the offline
    replay (RFC-0017 S4), where a July iteration must not see August's
    selections; a live run leaves it unset and reads up to today. The file grammar — which files are logs, how their
    day is spelled, what makes a line a record, and how a malformed one is
    counted — is reused from :func:`.selection_window._iter_selection_days`
    rather than restated. The per-skill tally is this module's own: the
    ADR-0071 reading next door carries neither a per-skill last-selected
    date nor exposure for skills that *were* selected, and widening an
    instrument for a page it does not consume would tie two readings
    together for no gain.
    """
    log_dir = data_root / "logs"
    keep = _window_predicate(since, until)

    tally = _tally_selection_window(log_dir, keep)
    selections, last_selected, offered = tally.selections, tally.last_selected, tally.offered
    records, skipped = tally.records, tally.skipped

    names = sorted(set(selections) | set(offered), key=lambda n: (-selections.get(n, 0), n))
    rows = [
        f"{_clean(name)} | {selections.get(name, 0)} | "
        f"{last_selected.get(name, _ABSENT)} | {offered.get(name, 0)}"
        for name in names
    ]
    header = (
        f"# Skill impact ({len(names)} skills over {records} records, "
        f"{skipped} unusable lines skipped)"
    )
    columns = "skill | selections | last selected | offered"
    return "\n".join([header, "", columns] + rows) + "\n"
