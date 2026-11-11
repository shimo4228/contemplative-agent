#!/usr/bin/env python3
"""Source-pattern age of the skills the selector picked (RFC-0071 P3-01.3, read-only).

stdlib only (run with bare ``python3``; ADR-0109). Manual run only — not wired
into CI, the weekly chain or the verify gate (the roadmap's consumption plan
(c)). Reads, under ``--home`` (default ``$MOLTBOOK_HOME`` or
``~/.config/moltbook``), never ``logs/episodes/`` nor any ``*.log``:

- ``logs/skill-selection-*.jsonl`` — ``ts``, ``verdict``, ``enforced``,
  ``selected`` and ``catalog_names`` only. The b64 prompt / output fields are
  never decoded.
- ``logs/audit.jsonl`` — ``command``, ``decision``, ``ts``, the basename of
  ``path`` and ``source_ids`` only. ``reason`` and every other body-like field
  is never read into a row.
- ``knowledge.json`` — ``distilled`` (the pattern's creation time) and the
  pattern id, computed as ``core/knowledge_store.py::pattern_id`` does
  (``sha256(f"{distilled}|{pattern}")[:12]``); the text is hashed, never kept.
- the ``name:`` frontmatter line of ``skills/*.md``, ``skills/.archive/*.md``
  and ``snapshots/*/skills/*.md``.

The question (roadmap P3-01.3): do the skills that get selected lean toward
young source patterns? This script prints the reading; it judges nothing. The
verdict is written by the owner after two readings (two quarters).

Tracing rule, selection -> source patterns (each step's failure is a reason
code, counted and printed; nothing is dropped silently):

1. A selection is one name in ``selected`` of a ``verdict: judged`` record
   (records without ``kind`` predate the field; ``kind: publish`` rows are not
   selections). A name repeated inside one record counts once. ``fail_open_*``
   records select nothing and are counted separately.
2. Name -> file. ``selected`` holds the frontmatter ``name:`` the selector read
   (``core/skill_selection.py::load_skill_catalog`` via ``skill_theme``), not
   the file slug — names and slugs differ for every live skill. The map is
   built from every ``name:`` line in the live dir, ``.archive/`` and the
   approval snapshots, so a skill renamed by a clean rewrite or retired since
   still resolves. A name in no file -> ``name_unmapped``.
3. File -> adoption row. The audit rows whose ``path`` basename is that file
   (``<slug>.md``) and whose ``command`` is ``insight`` with ``decision:
   approved`` (the adopt-time row; ``cli/staging.py`` carries ``source_ids``
   from the staged ``.meta.json`` into it, ADR-0050). Of those, the latest at
   or before the selection time is used. A name several slugs carried (a
   retired ``foo-20260801`` and its re-adopted ``foo-20261001`` both read
   ``name: foo``, because adopt canonicalises ``name:`` to the undated slug —
   ``core/artifact_extraction.py::slug_from_stem``) resolves to the slug whose
   such row is the newest; two slugs tied on that row's time ->
   ``name_ambiguous``, and so is no candidate having such a row while the
   candidates' reasons below differ. None at all, but an approved row of
   another command (a stocktake merge) -> ``adopted_without_insight_row``;
   no approved row of any command -> ``no_adoption_row``; insight rows only
   after the selection -> ``adoption_after_selection``; the row carries no
   ``source_ids`` (adoptions before the lineage field) ->
   ``adoption_row_without_source_ids``.
4. ``source_ids`` -> patterns in ``knowledge.json``. None found ->
   ``source_pattern_missing``; some found -> traced on the found ones, and the
   missing ids are tallied on their own line.
5. Age = selection time - the skill's source time, in weeks. A skill's source
   time is the **median** ``distilled`` of its found source patterns. Median
   rather than min / max because one adoption bundles 3-9 patterns from a
   cluster: the median is defined for every bundle size, one stray old or young
   member does not move it, and it is a time of the skill itself (fixed at
   adoption), so the age of one skill grows by exactly the elapsed time between
   two selections. The within-skill spread (max - min, weeks) is printed per
   skill so the choice can be checked. A source time after the selection ->
   ``pattern_after_selection``.

Baseline (not weighted by being selected): for the same judged records, every
name in the record's ``catalog_names`` — the skills live at that call — is
traced the same way and aged at that call's time. If the selector picked
uniformly from its catalog, the selected distribution would equal this one;
the gap between the two is the reading.

Corpus line (the comparison ADR-0124's Q2 row names — "older material than
the corpus as a whole"): every ``knowledge.json`` pattern created on or before
the window's last judged record, aged at that record's time. It is today's
``knowledge.json``, so for a past window it lacks rows removed since and keeps
soft-invalidated ones.

Window: ``--start`` / ``--end`` (``YYYY-MM-DD``, inclusive, the UTC date of
the record's ``ts``); either omitted means open on that side. Rates print with
the Wilson interval from ten rows and as counts below that (P2-01.9's rule,
``_stats``).

Output boundary (ADR-0083): counts, rates, ISO weeks, age in weeks and skill
names (printable ``[A-Za-z0-9._-]`` only; any other character prints as
``?``). Never ``reason``, pattern text, prompt / output text or a pattern id.

Consumption plan (ADR-0101, roadmap P3-01.3): (a) the owner, once a quarter;
the first reading is frozen under ``docs/evidence/rfc-0071/`` and cited from the
research-question ADR's Q2 section. (b) Two readings decide one sentence —
whether selected skills lean toward young source patterns. (c) If two readings
leave Q2 undecided the axis is dropped (the script stays as evidence); values
are frozen at P4-02's final sync and the script is not re-run after that.

Usage:
    python3 scripts/source_pattern_age.py [--home DIR] [--start YYYY-MM-DD] [--end YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _stats import MIN_DENOMINATOR, wilson_ci  # noqa: E402  (sibling import, see _stats docstring)
from skills_index import frontmatter  # noqa: E402  (sibling import)

WEEK_SECONDS = 7 * 24 * 3600
_SELECTION_FILE_RE = re.compile(r"^skill-selection-\d{4}-\d{2}-\d{2}\.jsonl$")
_NAME_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]")
_NAME_MAX = 80
_FRONTMATTER_READ_BYTES = 4096

# Reason codes, in the order a trace fails. Closed vocabulary — the render
# prints only these.
NAME_UNMAPPED = "name_unmapped"
NAME_AMBIGUOUS = "name_ambiguous"
NO_ADOPTION_ROW = "no_adoption_row"
ADOPTED_WITHOUT_INSIGHT_ROW = "adopted_without_insight_row"
ADOPTION_AFTER_SELECTION = "adoption_after_selection"
ADOPTION_ROW_WITHOUT_SOURCE_IDS = "adoption_row_without_source_ids"
SOURCE_PATTERN_MISSING = "source_pattern_missing"
PATTERN_AFTER_SELECTION = "pattern_after_selection"
REASONS = (
    NAME_UNMAPPED,
    NAME_AMBIGUOUS,
    NO_ADOPTION_ROW,
    ADOPTED_WITHOUT_INSIGHT_ROW,
    ADOPTION_AFTER_SELECTION,
    ADOPTION_ROW_WITHOUT_SOURCE_IDS,
    SOURCE_PATTERN_MISSING,
    PATTERN_AFTER_SELECTION,
)


@dataclass(frozen=True)
class Adoption:
    """One approved ``insight`` audit row for a skill file: when, and its lineage ids."""

    ts: datetime
    source_ids: tuple[str, ...]


@dataclass(frozen=True)
class Call:
    """One judged selection record reduced to time and names."""

    ts: datetime
    enforced: bool | None
    selected: tuple[str, ...]
    catalog: tuple[str, ...]


@dataclass(frozen=True)
class Trace:
    """Outcome of tracing one (name, time): an age in weeks, or a reason code."""

    age_weeks: float | None
    reason: str | None
    source_week: str | None = None
    spread_weeks: float | None = None
    missing_ids: int = 0


@dataclass(frozen=True)
class Inputs:
    calls: tuple[Call, ...]
    fail_open: tuple[datetime, ...]
    selection_files: int
    selection_lines: int
    name_to_slugs: dict[str, frozenset[str]]
    insight_rows: dict[str, tuple[Adoption, ...]]
    other_adopted: frozenset[str]
    pattern_time: dict[str, datetime]
    audit_lines: int
    skill_files: int


# --- parsing -------------------------------------------------------------


def parse_ts(value: object) -> datetime | None:
    """Aware UTC datetime from an ISO string; naive input is read as UTC."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def pattern_id(p: dict) -> str:
    """Mirror of ``core/knowledge_store.py::pattern_id`` (ADR-0050)."""
    raw = f"{p.get('distilled', '')}|{p.get('pattern', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def safe_name(name: str) -> str:
    return _NAME_UNSAFE_RE.sub("?", name)[:_NAME_MAX]


def load_calls(logs: Path) -> tuple[list[Call], list[datetime], int, int]:
    """(judged calls, fail-open record times, files read, lines read)."""
    calls: list[Call] = []
    fail_open: list[datetime] = []
    files = lines = 0
    for path in sorted(logs.glob("skill-selection-*.jsonl")):
        if not _SELECTION_FILE_RE.match(path.name):
            continue
        files += 1
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                lines += 1
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict) or rec.get("kind", "selection") != "selection":
                    continue
                verdict = rec.get("verdict")
                ts = parse_ts(rec.get("ts"))
                if ts is not None and isinstance(verdict, str) and verdict.startswith("fail_open"):
                    fail_open.append(ts)
                    continue
                if verdict != "judged" or ts is None:
                    continue
                selected = [n for n in rec.get("selected") or [] if isinstance(n, str)]
                catalog = [n for n in rec.get("catalog_names") or [] if isinstance(n, str)]
                enforced = rec.get("enforced")
                calls.append(
                    Call(
                        ts=ts,
                        enforced=enforced if isinstance(enforced, bool) else None,
                        selected=tuple(dict.fromkeys(selected)),
                        catalog=tuple(dict.fromkeys(catalog)),
                    )
                )
    return calls, fail_open, files, lines


def load_name_map(home: Path) -> tuple[dict[str, frozenset[str]], int]:
    """``name:`` -> the file slugs that carried it, over live, archive and snapshots."""
    dirs = [home / "skills", home / "skills" / ".archive"]
    dirs += sorted(p for p in (home / "snapshots").glob("*/skills") if p.is_dir())
    acc: dict[str, set[str]] = {}
    files = 0
    for d in dirs:
        for path in sorted(d.glob("*.md")):
            if path.name.startswith(".") or path.name == "INDEX.md" or path.is_symlink():
                continue
            try:
                with path.open(encoding="utf-8", errors="replace") as fh:
                    head = fh.read(_FRONTMATTER_READ_BYTES)
            except OSError:
                continue
            files += 1
            # skill_theme's fallback: a file without ``name:`` is named by its stem.
            name = frontmatter(head).get("name") or path.stem
            acc.setdefault(name, set()).add(path.stem)
    return {k: frozenset(v) for k, v in acc.items()}, files


def load_audit(path: Path) -> tuple[dict[str, tuple[Adoption, ...]], frozenset[str], int]:
    """(slug -> approved insight rows, slugs with an approved non-insight row, lines)."""
    insight: dict[str, list[Adoption]] = {}
    other: set[str] = set()
    lines = 0
    if not path.is_file():
        return {}, frozenset(), 0
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            lines += 1
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if not isinstance(rec, dict) or rec.get("decision") != "approved":
                continue
            p = rec.get("path")
            ts = parse_ts(rec.get("ts"))
            if not isinstance(p, str) or ts is None:
                continue
            base = p.replace("\\", "/").rsplit("/", 1)[-1]
            if not base.endswith(".md"):
                continue
            slug = base[: -len(".md")]
            if rec.get("command") == "insight":
                ids = tuple(i for i in rec.get("source_ids") or [] if isinstance(i, str))
                insight.setdefault(slug, []).append(Adoption(ts=ts, source_ids=ids))
            else:
                other.add(slug)
    return (
        {k: tuple(sorted(v, key=lambda a: a.ts)) for k, v in insight.items()},
        frozenset(other),
        lines,
    )


def load_patterns(path: Path) -> dict[str, datetime]:
    """pattern id -> creation time (``distilled``)."""
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("learned_patterns", []) if isinstance(data, dict) else data
    out: dict[str, datetime] = {}
    for p in rows if isinstance(rows, list) else []:
        if not isinstance(p, dict):
            continue
        ts = parse_ts(p.get("distilled"))
        if ts is not None:
            out[pattern_id(p)] = ts
    return out


def load_inputs(home: Path) -> Inputs:
    logs = home / "logs"
    calls, fail_open, sel_files, sel_lines = load_calls(logs)
    name_map, skill_files = load_name_map(home)
    insight, other, audit_lines = load_audit(logs / "audit.jsonl")
    return Inputs(
        calls=tuple(calls),
        fail_open=tuple(fail_open),
        selection_files=sel_files,
        selection_lines=sel_lines,
        name_to_slugs=name_map,
        insight_rows=insight,
        other_adopted=other,
        pattern_time=load_patterns(home / "knowledge.json"),
        audit_lines=audit_lines,
        skill_files=skill_files,
    )


# --- tracing -------------------------------------------------------------


def median_time(times: list[datetime]) -> datetime:
    ordered = sorted(times)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return ordered[mid - 1] + (ordered[mid] - ordered[mid - 1]) / 2


def iso_week(dt: datetime) -> str:
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


def _adoption_for(slug: str, at: datetime, inp: Inputs) -> Adoption | str:
    """The latest approved insight row of *slug* at or before *at*, else a reason code."""
    rows = inp.insight_rows.get(slug)
    if not rows:
        return ADOPTED_WITHOUT_INSIGHT_ROW if slug in inp.other_adopted else NO_ADOPTION_ROW
    prior = [r for r in rows if r.ts <= at]
    return prior[-1] if prior else ADOPTION_AFTER_SELECTION


def trace(name: str, at: datetime, inp: Inputs) -> Trace:
    slugs = inp.name_to_slugs.get(name)
    if not slugs:
        return Trace(None, NAME_UNMAPPED)
    picks = {slug: _adoption_for(slug, at, inp) for slug in sorted(slugs)}
    rows = [r for r in picks.values() if isinstance(r, Adoption)]
    if not rows:
        reasons = {r for r in picks.values() if isinstance(r, str)}
        return Trace(None, reasons.pop() if len(reasons) == 1 else NAME_AMBIGUOUS)
    # A retired skill and its re-adopted successor share a name (adopt
    # canonicalises ``name:`` to the undated slug); the slug adopted most
    # recently at or before the selection is the one the selector read.
    newest = max(r.ts for r in rows)
    if sum(1 for r in rows if r.ts == newest) > 1:
        return Trace(None, NAME_AMBIGUOUS)
    row = next(r for r in rows if r.ts == newest)
    if not row.source_ids:
        return Trace(None, ADOPTION_ROW_WITHOUT_SOURCE_IDS)
    found = [inp.pattern_time[i] for i in row.source_ids if i in inp.pattern_time]
    missing = len(row.source_ids) - len(found)
    if not found:
        return Trace(None, SOURCE_PATTERN_MISSING, missing_ids=missing)
    source = median_time(found)
    age = (at - source).total_seconds() / WEEK_SECONDS
    if age < 0:
        return Trace(None, PATTERN_AFTER_SELECTION, missing_ids=missing)
    spread = (max(found) - min(found)).total_seconds() / WEEK_SECONDS
    return Trace(age, None, iso_week(source), spread, missing)


@dataclass(frozen=True)
class Distribution:
    total: int
    ages: tuple[float, ...]
    reasons: dict[str, int]
    missing_ids: int


def distribution(pairs: list[tuple[str, datetime]], inp: Inputs) -> Distribution:
    ages: list[float] = []
    reasons: Counter[str] = Counter()
    missing = 0
    for name, at in pairs:
        t = trace(name, at, inp)
        missing += t.missing_ids
        if t.age_weeks is None:
            reasons[t.reason or "unknown"] += 1
        else:
            ages.append(t.age_weeks)
    return Distribution(len(pairs), tuple(ages), dict(reasons), missing)


# --- rendering -----------------------------------------------------------


def rate(k: int, n: int) -> str:
    """``k/n = x% [lo-hi%]``; counts only under ten rows (P2-01.9's rule)."""
    ci = wilson_ci(k, n) if n >= MIN_DENOMINATOR else None
    if ci is None:
        return f"{k}/{n}"
    return f"{k}/{n} = {100 * k / n:.1f}% [{100 * ci[0]:.1f}-{100 * ci[1]:.1f}%]"


def quartiles(ages: tuple[float, ...]) -> str:
    if not ages:
        return "- (no traced rows)"
    if len(ages) == 1:
        return f"median {ages[0]:.1f}"
    q1, q2, q3 = statistics.quantiles(ages, n=4, method="inclusive")
    return (
        f"min {min(ages):.1f} / Q1 {q1:.1f} / median {q2:.1f} / Q3 {q3:.1f} / max {max(ages):.1f}"
    )


def corpus_ages(inp: Inputs, at: datetime | None) -> tuple[float, ...]:
    """Age in weeks, at *at*, of every pattern created on or before it."""
    if at is None:
        return ()
    return tuple(
        (at - t).total_seconds() / WEEK_SECONDS for t in inp.pattern_time.values() if t <= at
    )


def in_window(dt: datetime, start: date | None, end: date | None) -> bool:
    d = dt.date()
    return (start is None or d >= start) and (end is None or d <= end)


def render(inp: Inputs, start: date | None, end: date | None) -> str:
    calls = [c for c in inp.calls if in_window(c.ts, start, end)]
    sel_pairs = [(n, c.ts) for c in calls for n in c.selected]
    cat_pairs = [(n, c.ts) for c in calls for n in c.catalog]
    sel = distribution(sel_pairs, inp)
    cat = distribution(cat_pairs, inp)
    enforced = Counter(
        "true" if c.enforced is True else "false" if c.enforced is False else "absent"
        for c in calls
    )
    first = min((c.ts for c in calls), default=None)
    last = max((c.ts for c in calls), default=None)

    out: list[str] = []
    w = f"{start or 'open'} .. {end or 'open'}"
    out.append(f"# Source-pattern age of selected skills ({w})")
    out.append("")
    out.append("## Inputs")
    out.append("")
    out.append(
        f"- skill-selection log: {inp.selection_files} files, {inp.selection_lines} lines; "
        f"judged records in window: {len(calls)} "
        f"(enforced true {enforced['true']} / false {enforced['false']} / "
        f"absent {enforced['absent']}); fail-open records in window (select nothing): "
        f"{sum(1 for t in inp.fail_open if in_window(t, start, end))}"
    )
    if first and last:
        out.append(f"- judged records span {first.date()} .. {last.date()} (UTC)")
    out.append(
        f"- audit.jsonl: {inp.audit_lines} lines; skill files with an approved insight row: "
        f"{len(inp.insight_rows)}"
    )
    out.append(
        f"- knowledge.json: {len(inp.pattern_time)} patterns; "
        f"skill files read for `name:`: {inp.skill_files} "
        f"({len(inp.name_to_slugs)} distinct names)"
    )
    out.append("")
    out.append("## Traced")
    out.append("")
    out.append("| population | rows | traced | untraced |")
    out.append("|---|---|---|---|")
    for label, d in (("selected", sel), ("catalog (baseline)", cat)):
        out.append(
            f"| {label} | {d.total} | {rate(len(d.ages), d.total)} | {d.total - len(d.ages)} |"
        )
    out.append("")
    out.append("Untraced by reason code:")
    out.append("")
    out.append("| reason | selected | catalog (baseline) |")
    out.append("|---|---|---|")
    for r in REASONS:
        out.append(f"| {r} | {sel.reasons.get(r, 0)} | {cat.reasons.get(r, 0)} |")
    out.append("")
    out.append(
        f"Source ids absent from knowledge.json on traced or untraced rows "
        f"(summed per row): selected {sel.missing_ids} / catalog {cat.missing_ids}"
    )
    out.append("")
    out.append("## Age in weeks (selection time - median creation of the source patterns)")
    out.append("")
    corpus = corpus_ages(inp, last)
    out.append(f"- selected: {quartiles(sel.ages)}")
    out.append(f"- catalog (baseline): {quartiles(cat.ages)}")
    ref = f"at {last.isoformat(timespec='minutes')}" if last else "(no judged record)"
    out.append(f"- corpus {ref}, {len(corpus)} patterns: {quartiles(corpus)}")
    out.append("")
    out.append("| age (weeks, floor) | selected | catalog (baseline) | corpus |")
    out.append("|---|---|---|---|")
    sel_bins = Counter(int(a) for a in sel.ages)
    cat_bins = Counter(int(a) for a in cat.ages)
    cor_bins = Counter(int(a) for a in corpus)
    top = max([*sel_bins, *cat_bins, *cor_bins], default=-1)
    for b in range(top + 1):
        out.append(f"| {b} | {sel_bins.get(b, 0)} | {cat_bins.get(b, 0)} | {cor_bins.get(b, 0)} |")
    out.append("")
    out.append("## Per skill (selected in window)")
    out.append("")
    out.append(
        "| skill name | selections | catalog rows | source week (median) | "
        "within-skill spread (weeks) | median age at selection | untraced reason |"
    )
    out.append("|---|---|---|---|---|---|---|")
    per_sel: Counter[str] = Counter(n for n, _ in sel_pairs)
    per_cat: Counter[str] = Counter(n for n, _ in cat_pairs)
    sel_times: dict[str, list[datetime]] = {}
    for n, at in sel_pairs:
        sel_times.setdefault(n, []).append(at)
    for name, count in sorted(per_sel.items(), key=lambda kv: (-kv[1], kv[0])):
        traces = [trace(name, at, inp) for at in sel_times[name]]
        ages = [t.age_weeks for t in traces if t.age_weeks is not None]
        reasons = Counter(t.reason for t in traces if t.reason)
        shown = next((t for t in traces if t.age_weeks is not None), None)
        out.append(
            f"| {safe_name(name)} | {count} | {per_cat.get(name, 0)} | "
            f"{shown.source_week if shown else '-'} | "
            f"{f'{shown.spread_weeks:.1f}' if shown and shown.spread_weeks is not None else '-'} | "
            f"{f'{statistics.median(ages):.1f}' if ages else '-'} | "
            f"{', '.join(f'{r} {k}' for r, k in sorted(reasons.items())) or '-'} |"
        )
    out.append("")
    return "\n".join(out)


def _date(value: str) -> date:
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    default_home = os.environ.get("MOLTBOOK_HOME") or str(Path.home() / ".config" / "moltbook")
    parser.add_argument("--home", type=Path, default=Path(default_home))
    parser.add_argument("--start", type=_date, default=None, help="YYYY-MM-DD, inclusive (UTC)")
    parser.add_argument("--end", type=_date, default=None, help="YYYY-MM-DD, inclusive (UTC)")
    args = parser.parse_args(argv)
    if not (args.home / "logs").is_dir():
        print(f"ERROR: no logs/ under {args.home}", file=sys.stderr)
        return 2
    print(render(load_inputs(args.home), args.start, args.end))
    return 0


if __name__ == "__main__":
    sys.exit(main())
