#!/usr/bin/env python3
"""Self-regulation reading: eight weeks of load and metabolism side by side (P2-01.5).

stdlib only (run with bare ``python3``; ADR-0109). Read-only over the
self-written logs under ``$MOLTBOOK_HOME`` (never ``logs/episodes/`` or any
``*.log``), the weekly reports under ``reports/analysis/`` (line counts only),
``rfcs/`` and ``git log`` of the checkout; writes nothing, holds no state.
Roadmap: P2-01.2 / .3 / .5 / .7 / .8 / .13, P2-06.1.

What one row (an ISO week, Monday-Sunday, eight of them) carries -- columns are
**side by side and never composed** into one number (ADR-0080 amendment 2026-08-26,
"no single scalar"). The roman numerals are P2-01.5's column numbers; P2-01.3
numbers the three *load series* differently -- (i) rulings, (ii) reading volume
(the second table below), (iii) ``outside``:

``rulings``      (i)  gate_record: adopted + rejected + deleted + whitelisted + archived.
                      ``*_held`` is a deferral, not a ruling.
``agree``        P2-01.5  ``gate_item`` rows whose ``decision`` equals the briefing's
                      ``recommendation``, over the week's ruled rows other than
                      ``category=roadmap`` (``rm_agree`` holds those). Same population as
                      the census Gate record, which splits it per category: a row missing
                      either side or a bundle closure (``closed``) is not counted. A row
                      is placed by its ``ts`` (the gate that wrote it), not by a
                      retroactive ``decided_at``. ``k/n`` with the Wilson interval from
                      ten rows (``_stats``, P2-01.9's rule).
``gate_min``     P2-01.2  minutes from the week's first ``gate_start`` to its last
                      ``gate_record``, minus the roadmap part (compare with the
                      127-minute timetable of weekly-gate Step 0). ``-`` when either
                      end is missing.
``drafts``       (ii) new ``origin: gate`` RFC files (first commit date in the week).
``outside``      (iii) distinct files other than ``rfcs/README.md`` touched by the
                      week's Saturday commits that carry no ``Roadmap:`` trailer.
``repairs``      ``fix`` commits of the week (any day) -- the repair-PR count.
``rm_dec`` / ``rm_agree`` / ``rm_min`` / ``rm_files``   P2-01.13 the roadmap's own
                      execution, separated: ``category=roadmap`` gate_item rows, their
                      agreement (as ``agree``), the ``roadmap_start``..``roadmap_end``
                      minutes, and the files of commits carrying a ``Roadmap:`` trailer.
                      They are not in ``rulings`` / ``gate_min`` / ``outside``, so they
                      cannot move the candidate declaration.
``staged/adopted/archived``  (vi) insight staged (``insight-staged.jsonl`` rows),
                      adopted and archived (``audit.jsonl``, same rules as the census
                      gate section). ``--changes pipeline/value-layer/changes.json``
                      (P2-05.7, the data repo) adds one line naming each week where
                      adopted / archived / identity approvals differ from the change
                      series' skills files added / removed and identity changes; the
                      counts themselves stay the script's own.
``empty_sel``    P2-01.7 judged-empty / judged in ``skill-selection-*.jsonl`` with the
                      Wilson interval (``_stats``); ``rejected_names``-only rows are a
                      separate count. Under ten judged rows only the counts print.
``freeze``       P2-01.5 "stops" column: ``nonfix`` and ``quiet_weeks`` copied from
                      ``scripts/freeze_reading.py``'s one line for that week. This script
                      runs no git analysis of the frozen set itself.

Reading volume, load series (ii) (P2-01.3 / P2-06.1), is a second table with the
same week rows (series (ii) is its own series; it is never summed with (i) or
(iii)). A week's report is the ``reports/analysis/weekly-{stamp}.md`` with the
latest stamp from the previous Saturday to the week's Friday -- the one the
week's Saturday gate reads, since the chain passes Friday as ``--end``; a
Saturday or Sunday re-run falls in the next week's window and is superseded by
that week's Friday report. Its cells are counts only (the Sample section quotes
counterparties; no report text is printed):

``inventory``    the five numbers of the Inventory line
                      (decisions-pending / exceptions / new-observations /
                      continuing / discarded).
``Inventory`` .. ``Discarded``  lines per section, from its ``## `` header to the
                      next ``## `` header (the same count as ``wc -l`` over the span).
``carried``      ``(since W)`` marks / ``Carried:`` lines in Exceptions: the
                      carried fold (P2-06.1) leaves one line holding every item.
``doc`` / ``findings``  total lines of the report and of ``weekly-{stamp}-findings.md``.

``(report pending)`` marks a week whose report is not written yet: the weekly
materials are built before the session that writes that week's report. Below the
table one line gives the Exceptions lines of the last three reports and whether
they fell twice running -- the reading P2-06.1's done-criterion names; the gate
judges it (first two production weeks after the fold: the 2026-11-14 gate).

Not per-week, printed once below the table: (iv) open RFC ledger count and (v)
the latest ``exceptions N`` of the weekly Inventory line (a snapshot, so it cannot
be recomputed for a past week); how many ruled ``gate_item`` rows name their
``recommender`` (D-P2-01-2 = A: the 2026-12-12 audit's key; the values are model ids
and are not printed); and the (vi) reconciliation line.

Candidate declaration: ``self-regulating candidate`` when ``rulings + drafts +
outside == 0`` for ``--n`` consecutive weeks (default 8; the roadmap leaves N to
the 11-28 gate). A week with no ``gate_record`` is *not* a zero week -- an absent
gate is not a self-regulating one, and the line says how many weeks were absent.
Sufficiency stays the owner's: ``gate_record self_regulation_verdict=``.

Metabolism floor (D-P2-01-3 = B, owner 2026-10-24): when adopted = 0, archived = 0
and identity updates (``audit.jsonl`` ``distill-identity`` approved) = 0 for 8
consecutive weeks the script prints ``metabolism floor reached`` -- the trigger for
filing the end-of-run consideration event (P4-01), never a declaration of steady
state. D-P2-01-1 = B (owner 2026-10-24): the load columns above are the three
series plus drafts / repairs / minutes; ``--intake-line`` prints the PIPELINE-STATUS
intake line.

Abstains with ``reason=CODE detail`` on stderr and exit 2 (``scripts/_scan.py``
shape) when ``--home`` is unusable; a column whose source is missing prints ``-``
with the reason in the footnotes rather than a zero.

### Consumption plan (ADR-0101)
(a) The Saturday gate reads this table in the weekly materials
(``## Self-Regulation Reading``) at Step 1, every week; the headless report copies it.
(b) Reads at the 2026-11-28 gate decide D-P2-01-1 / -3 (which columns stay) and, from
then on, every "load to zero" proposal is judged against the eight rows; the owner's
sufficiency verdict goes in ``gate_record``.
(c) Retire the weekly table after the verdict is recorded and N weeks of candidate have
passed; the quarterly T4 (ADR-0101) reads it afterwards.
Reading-volume table (P2-06.1): (a) the same gate reads it at Step 1; (b) the
2026-11-14 gate reads the Exceptions line once for P2-06.1's done-criterion (two
production weeks after the carried fold), and the 2026-11-28 gate (D-P2-01-1 = B)
reads the eight rows once to keep or drop series (ii) as these columns; (c) it retires
with the weekly table, or at 11-28 if that gate drops series (ii).
``agree`` / ``rm_agree`` and the recommender line (P2-01.5): (a) the same gate reads
them at Step 1; (b) the 2026-12-12 gate reads the eight rows once to fix the
D-P2-01-2 audit's n and to check that ``recommender`` covers its population; after
that ADR-0099's Review-when (~100% sustained) is read from them at the quarterly T4;
(c) they retire with the weekly table.
(vi) reconciliation line (P2-01.5, P2-05.7): (a) the same gate reads it at Step 1;
(b) a week it names is checked once at that gate against ``audit.jsonl`` and the
snapshots, and the explanation goes in that gate's ``gate_record``; (c) it retires
with the weekly table. The three plans are also in ``docs/evidence/adr-0080/README.md``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scan import ScanError  # noqa: E402
from _stats import MIN_DENOMINATOR, format_rate  # noqa: E402

WEEKS = 8
CANDIDATE_N = 8
FLOOR_WEEKS = 8
TIMETABLE_MIN = 127  # weekly-gate Step 0 timetable: 12:00-14:07
# Same fields as scripts/_census_series.GATE_DECISION_FIELDS (pinned by a test).
GATE_DECISION_FIELDS = (
    "insight_adopted",
    "insight_rejected",
    "deadcode_deleted",
    "deadcode_whitelisted",
    "skills_archived",
)
TERMINAL_STATES = {
    "done",
    "withdrawn",
    "obsoleted",
    "resolved",
    "rejected",
    "accepted",
    "superseded",
}


def _ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def week_of(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def week_span(end: date, weeks: int) -> list[tuple[str, date, date]]:
    """``(label, monday, sunday)`` for the ``weeks`` ISO weeks ending with ``end``'s."""
    monday = end - timedelta(days=end.weekday())
    out = []
    for i in range(weeks - 1, -1, -1):
        m = monday - timedelta(days=7 * i)
        out.append((week_of(m), m, m + timedelta(days=6)))
    return out


def read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return rows
    for line in text.splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and _ts(rec.get("ts")):
            rows.append(rec)
    return rows


def read_glob(logs: Path, pattern: str) -> list[dict]:
    rows: list[dict] = []
    for p in sorted(logs.glob(pattern)):
        rows += read_jsonl(p)
    return rows


def _day(rec: dict) -> date:
    dt = _ts(rec.get("ts"))
    assert dt is not None
    return dt.date()


def _num(value: object) -> int:
    try:
        return int(float(str(value)))
    except (ValueError, OverflowError):
        return 0


@dataclass
class Week:
    label: str
    monday: date
    sunday: date
    gate: bool = False
    pending: bool = False  # Saturday gate not yet run when read (end <= that Saturday)
    rulings: int = 0
    gate_min: int | None = None
    drafts: int = 0
    outside: int | None = None
    repairs: int | None = None
    rm_dec: int = 0
    agree: int = 0  # gate_item recommendation == decision, categories other than roadmap
    agree_n: int = 0
    rm_agree: int = 0  # the same, category=roadmap
    rm_agree_n: int = 0
    rm_min: int | None = None
    rm_files: int | None = None
    staged: int = 0
    adopted: int = 0
    archived: int = 0
    identity: int = 0
    judged: int = 0
    empty: int = 0
    rejected_only: int = 0
    freeze: str = "-"
    read: ReadVolume | None = None
    read_pending: bool = False  # the week's report is written after these materials
    notes: list[str] = field(default_factory=list)


def _git(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScanError("GIT_UNUSABLE", type(exc).__name__) from exc
    if proc.returncode != 0:
        raise ScanError("GIT_UNUSABLE", proc.stderr.strip()[:120])
    return proc.stdout


@dataclass(frozen=True)
class Commit:
    sha: str
    day: date
    subject: str
    roadmap: bool


def read_commits(repo: Path, since: date, until: date) -> list[Commit]:
    out = _git(
        repo,
        "log",
        f"--since={since - timedelta(days=1)}",
        f"--until={until + timedelta(days=2)}",
        "--format=%H%x02%cI%x02%s%x02%(trailers:key=Roadmap,valueonly,separator=%x3b)%x03",
    )
    commits = []
    for rec in out.split("\x03"):
        parts = rec.strip("\n").split("\x02")
        if len(parts) != 4:
            continue
        sha, iso, subject, trailer = parts
        try:
            day = date.fromisoformat(iso[:10])
        except ValueError:
            continue
        if since <= day <= until:
            commits.append(Commit(sha, day, subject, bool(trailer.strip())))
    return commits


def _files(repo: Path, sha: str) -> set[str]:
    return {f for f in _git(repo, "show", "--name-only", "--format=", sha).splitlines() if f}


def new_gate_drafts(repo: Path, since: date, until: date) -> list[date]:
    """First-commit day of every ``rfcs/*.md`` whose frontmatter says ``origin: gate``."""
    days: list[date] = []
    for p in sorted((repo / "rfcs").glob("*.md")):
        if p.name == "README.md":
            continue
        head = p.read_text(encoding="utf-8", errors="replace").split("\n---", 2)[0][:2000]
        if not re.search(r"^origin:\s*gate\s*$", head, re.M):
            continue
        first = _git(repo, "log", "--diff-filter=A", "--format=%cI", "--", f"rfcs/{p.name}")
        added = first.strip().splitlines()
        if added and since <= (d := date.fromisoformat(added[-1][:10])) <= until:
            days.append(d)
    return days


def open_ledger(repo: Path) -> int:
    n = 0
    for p in (repo / "rfcs").glob("[0-9]*.md"):
        m = re.search(r"^state:\s*(\S+)", p.read_text(encoding="utf-8", errors="replace"), re.M)
        if m and m.group(1).lower() not in TERMINAL_STATES:
            n += 1
    return n


def latest_exceptions(home: Path, end: date) -> tuple[int | None, str]:
    best: tuple[str, int] | None = None
    for p in (home / "reports" / "analysis").glob("weekly-????-??-??.md"):
        stamp = p.stem.removeprefix("weekly-")
        if stamp > end.isoformat():
            continue
        m = re.search(r"exceptions\s+(\d+)", p.read_text(encoding="utf-8", errors="replace")[:3000])
        if m and (best is None or stamp > best[0]):
            best = (stamp, int(m.group(1)))
    return (best[1], best[0]) if best else (None, "")


# --- Reading volume: load series (ii) (P2-01.3 / P2-06.1) ----------------------

READ_SECTIONS = ("Inventory", "Ledger", "Deviations", "Exceptions", "Discarded")
INVENTORY_KEYS = ("decisions-pending", "exceptions", "new-observations", "continuing", "discarded")
_INVENTORY_RE = re.compile(r"\s*·\s*".join(rf"{k}\s+(\d+)" for k in INVENTORY_KEYS))
_CARRIED_RE = re.compile(r"^\s*(?:[-*]\s+)?Carried:")


@dataclass(frozen=True)
class ReadVolume:
    """What the week's gate reads: one weekly report and its findings file, in lines."""

    stamp: str  # end-date of weekly-{stamp}.md
    inventory: tuple[int, ...] | None  # INVENTORY_KEYS, in order; None = line not found
    sections: tuple[int | None, ...]  # lines per READ_SECTIONS (header to next ``## ``)
    carried_items: int  # ``(since W)`` marks on the Exceptions ``Carried:`` line(s)
    carried_lines: int  # ``Carried:`` lines in Exceptions (the fold makes it 0 or 1)
    doc_lines: int
    findings_lines: int | None  # None = no weekly-{stamp}-findings.md


def _line_count(path: Path) -> int | None:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except OSError:
        return None


def _section_spans(lines: list[str]) -> dict[str, tuple[int, int]]:
    """``{first word of a "## " header: (start, stop)}``, header line included."""
    heads = [
        (i, ln[3:].split()[0])
        for i, ln in enumerate(lines)
        if ln.startswith("## ") and ln[3:].split()
    ]
    spans: dict[str, tuple[int, int]] = {}
    for k, (i, name) in enumerate(heads):
        stop = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        spans.setdefault(name, (i, stop))
    return spans


def _carried(lines: list[str]) -> tuple[int, int]:
    """``(items, lines)`` of the Exceptions section's ``Carried:`` list item(s).

    An item runs from its ``Carried:`` line through the indented continuation
    lines the report hard-wraps it into; ``(since W)`` is mandatory on every
    carried item (``config/prompts/weekly-analysis.md``), so its count is the
    item count.
    """
    items = n_lines = 0
    i = 0
    while i < len(lines):
        if not _CARRIED_RE.match(lines[i]):
            i += 1
            continue
        n_lines += 1
        block = [lines[i]]
        i += 1
        while i < len(lines) and lines[i].startswith((" ", "\t")) and lines[i].strip():
            block.append(lines[i])
            i += 1
        items += " ".join(block).count("(since ")
    return items, n_lines


def read_volume(path: Path) -> ReadVolume | None:
    """Counts only: no body text leaves this function (a Sample entry quotes a counterparty)."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    stamp = path.stem.removeprefix("weekly-")
    spans = _section_spans(lines)
    m = _INVENTORY_RE.search("\n".join(lines)[:3000])
    exc = spans.get("Exceptions")
    items, n_carried = _carried(lines[exc[0] : exc[1]]) if exc else (0, 0)
    return ReadVolume(
        stamp=stamp,
        inventory=tuple(int(g) for g in m.groups()) if m else None,
        sections=tuple((spans[s][1] - spans[s][0]) if s in spans else None for s in READ_SECTIONS),
        carried_items=items,
        carried_lines=n_carried,
        doc_lines=len(lines),
        findings_lines=_line_count(path.with_name(f"weekly-{stamp}-findings.md")),
    )


def _read_columns(table: list[Week], home: Path, end: date) -> None:
    """The report each week's Saturday gate reads: latest end-date in (previous Friday, Friday].

    The chain passes Friday as ``--end``, so a week's own report is
    ``weekly-{Friday}.md``; a Saturday or Sunday re-run belongs to the next
    week's window and is superseded by that week's Friday report.
    """
    stamps = sorted(
        p.stem.removeprefix("weekly-")
        for p in (home / "reports" / "analysis").glob("weekly-????-??-??.md")
        if p.stem.removeprefix("weekly-") <= end.isoformat()
    )
    for w in table:
        lo, hi = (
            (w.monday - timedelta(days=2)).isoformat(),
            (w.monday + timedelta(days=4)).isoformat(),
        )
        inside = [s for s in stamps if lo <= s <= hi]
        if inside:
            w.read = read_volume(home / "reports" / "analysis" / f"weekly-{inside[-1]}.md")
        else:
            w.read_pending = w.monday + timedelta(days=4) >= end


def exceptions_trend(table: list[Week]) -> str:
    """P2-06.1's done-criterion reading: Exceptions lines over the last three reports."""
    pts = [
        (w.read.stamp, w.read.sections[READ_SECTIONS.index("Exceptions")])
        for w in table
        if w.read is not None and w.read.sections[READ_SECTIONS.index("Exceptions")] is not None
    ][-3:]
    if len(pts) < 3:
        return f"Exceptions lines (P2-06.1): {len(pts)} report(s) in the window; three are needed."
    vals = [v for _, v in pts]
    fell = vals[0] > vals[1] > vals[2]  # type: ignore[operator]
    trail = " → ".join(f"{v} (weekly-{s})" for s, v in pts)
    return (
        f"Exceptions lines (P2-06.1): {trail}; fell in both of the last two reports: "
        f"{'yes' if fell else 'no'}."
    )


def freeze_cells(repo: Path, weeks: list[Week], end: date) -> None:
    script = Path(__file__).resolve().parent / "freeze_reading.py"
    for w in weeks:
        try:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--repo",
                    str(repo),
                    "--end",
                    min(w.sunday, end).isoformat(),
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            w.freeze = "n/a"
            w.notes.append(f"freeze: {type(exc).__name__}")
            continue
        m_n = re.search(r"nonfix=(\d+)", proc.stdout)
        m_q = re.search(r"quiet_weeks=(\d+)", proc.stdout)
        if proc.returncode == 0 and m_n and m_q:
            w.freeze = f"nonfix {m_n.group(1)} / quiet {m_q.group(1)}"
        else:
            w.freeze = "n/a"
            w.notes.append(
                "freeze: " + (proc.stderr.strip().splitlines() or ["no output"])[-1][:80]
            )


def _agreement_pair(r: dict) -> tuple[str, str] | None:
    """``(recommendation, decision)`` of a ruled ``gate_item``; None when it is not one.

    Same population as the census Gate record (``_census_series.gate_agreement``):
    a row missing either side, or a bundle closure (``closed`` on either side),
    is neither agreement nor disagreement.
    """
    rec, dec = r.get("recommendation"), r.get("decision")
    if rec is None or dec is None or "closed" in (str(rec), str(dec)):
        return None
    return str(rec), str(dec)


def _tally_item(w: Week, r: dict, recommender: dict[str, list[int]]) -> None:
    """One ``gate_item`` row into the week's roadmap count and agreement cells."""
    roadmap = r.get("category") == "roadmap"
    if roadmap and r.get("decision") != "closed":
        w.rm_dec += 1
    if (pair := _agreement_pair(r)) is None:
        return
    same = pair[0] == pair[1]
    if roadmap:
        w.rm_agree, w.rm_agree_n = w.rm_agree + same, w.rm_agree_n + 1
    else:
        w.agree, w.agree_n = w.agree + same, w.agree_n + 1
    tally = recommender["roadmap" if roadmap else "gate"]
    tally[0] += bool(r.get("recommender"))
    tally[1] += 1


def _gate_columns(table: list[Week], pm: list[dict]) -> dict[str, list[int]]:
    """Rulings, agreement, gate minutes and the roadmap's own part, from ``pipeline-metrics.jsonl``.

    Returns ``{"gate" | "roadmap": [rows with a recommender, ruled rows]}`` over the
    window (D-P2-01-2 = A: ``recommender`` is the audit's key; its values are model
    ids and are not printed).
    """
    by = {w.label: w for w in table}
    marks: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    recommender = {"gate": [0, 0], "roadmap": [0, 0]}
    for r in pm:
        w = by.get(week_of(_day(r)))
        dt, ev = _ts(r.get("ts")), r.get("event")
        if w is None or dt is None or not isinstance(ev, str):
            continue
        marks[(w.label, ev)].append(dt)
        if ev == "gate_record":
            w.gate = True
            w.rulings += sum(_num(r.get(f)) for f in GATE_DECISION_FIELDS)
        elif ev == "gate_item":
            _tally_item(w, r, recommender)

    def minutes(label: str, a: str, b: str) -> int | None:
        if (label, a) not in marks or (label, b) not in marks:
            return None
        return max(0, round((max(marks[(label, b)]) - min(marks[(label, a)])).total_seconds() / 60))

    for w in table:
        w.rm_min = minutes(w.label, "roadmap_start", "roadmap_end")
        total = minutes(w.label, "gate_start", "gate_record")
        w.gate_min = None if total is None else max(0, total - (w.rm_min or 0))
    return recommender


def _intake_columns(table: list[Week], logs: Path) -> None:
    by = {w.label: w for w in table}
    for r in read_jsonl(logs / "insight-staged.jsonl"):
        if (w := by.get(week_of(_day(r)))) is not None:
            w.staged += 1
    for r in read_jsonl(logs / "audit.jsonl"):
        if (w := by.get(week_of(_day(r)))) is None:
            continue
        w.adopted += _is_adopted(r)
        w.archived += _is_archived(r)
        w.identity += r.get("command") == "distill-identity" and r.get("decision") == "approved"
    for r in read_glob(logs, "skill-selection-*.jsonl"):
        w = by.get(week_of(_day(r)))
        if w is None or r.get("kind", "selection") != "selection" or r.get("verdict") != "judged":
            continue
        w.judged += 1
        if not r.get("selected"):
            if r.get("rejected_names"):
                w.rejected_only += 1
            else:
                w.empty += 1


def _is_adopted(r: dict) -> bool:
    return r.get("command") == "insight" and r.get("decision") == "approved"


def _is_archived(r: dict) -> bool:
    src = str(r.get("source") or "")
    return src == "stage-archived-names" or src.startswith("direct-archive")


def _git_columns(table: list[Week], repo: Path, end: date) -> int:
    """Drafts, repairs, outside / roadmap files and the freeze cell; returns open ledger."""
    by = {w.label: w for w in table}
    first, last = table[0].monday, table[-1].sunday
    for d in new_gate_drafts(repo, first, last):
        if (w := by.get(week_of(d))) is not None:
            w.drafts += 1
    outside: dict[str, set[str]] = defaultdict(set)
    rm_files: dict[str, set[str]] = defaultdict(set)
    for w in table:
        w.outside, w.rm_files, w.repairs = 0, 0, 0
    for c in read_commits(repo, first, last):
        w = by.get(week_of(c.day))
        if w is None:
            continue
        if re.match(r"fix(\(|:|!)", c.subject):
            w.repairs = (w.repairs or 0) + 1
        if c.roadmap:
            rm_files[w.label] |= _files(repo, c.sha)
        elif c.day.weekday() == 5:  # Saturday = the gate's day
            outside[w.label] |= _files(repo, c.sha) - {"rfcs/README.md"}
    for w in table:
        w.outside, w.rm_files = len(outside[w.label]), len(rm_files[w.label])
    freeze_cells(repo, table, end)
    return open_ledger(repo)


def reconcile_changes(table: list[Week], path: Path) -> str:
    """(vi) against the value-layer change series (P2-05.7), differences named, not reconciled.

    Per week: the script's ``adopted`` against the number of names in the skills
    rows' ``files_added``, ``archived`` against ``files_removed``, identity
    approvals against identity change rows, each change placed in the week of its
    ``ts_to`` (the first snapshot that shows it). A week after the series' last
    snapshot is not covered. A revision changes a digest without adding or
    removing a file, and a retired writer (rules-distill, merge) adds and removes
    files no gate row names, so a mismatch is a pointer for the reader, never a
    correction of either count.
    """

    def names(value: object) -> int:
        return len(value) if isinstance(value, list) else _num(value)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        changes = data["changes"]
        last = _ts(data["coverage"]["last_ts"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f"(vi) not reconciled: {path.name} unreadable ({type(exc).__name__})."
    by = {w.label: w for w in table}
    seen: dict[str, list[int]] = {w.label: [0, 0, 0] for w in table}
    for c in changes if isinstance(changes, list) else []:
        dt = _ts(c.get("ts_to")) if isinstance(c, dict) else None
        if dt is None or (w := by.get(week_of(dt.date()))) is None:
            continue
        if c.get("kind") == "skills":
            seen[w.label][0] += names(c.get("files_added"))
            seen[w.label][1] += names(c.get("files_removed"))
        elif c.get("kind") == "identity":
            seen[w.label][2] += 1
    covered = [w for w in table if last is not None and w.monday <= last.date()]
    diffs = []
    for w in covered:
        added, removed, ident = seen[w.label]
        parts = [
            f"{name} {mine} vs {theirs}"
            for name, mine, theirs in (
                ("adopted/skills added", w.adopted, added),
                ("archived/skills removed", w.archived, removed),
                ("identity approved/changed", w.identity, ident),
            )
            if mine != theirs
        ]
        if parts:
            diffs.append(f"{w.label}: " + ", ".join(parts))
    head = (
        f"(vi) against {path.name} (P2-05.7, last snapshot {last.date() if last else '-'}): "
        f"{len(covered) - len(diffs)} of {len(covered)} covered week(s) agree"
    )
    return head + ("; " + "; ".join(diffs) + "." if diffs else ".")


def build(
    home: Path, repo: Path | None, end: date, weeks: int, changes: Path | None = None
) -> tuple[list[Week], dict]:
    logs = home / "logs"
    if not logs.is_dir():
        raise ScanError("SELFREG_NO_LOG_DIR", str(logs))
    table = [Week(*s) for s in week_span(end, weeks)]
    recommender = _gate_columns(table, read_jsonl(logs / "pipeline-metrics.jsonl"))
    # The weekly chain runs Saturday 09:00 with --end Friday; the gate (and its
    # gate_record) comes later, so a gate-less last week is pending, not absent.
    last = table[-1]
    last.pending = not last.gate and last.monday + timedelta(days=5) >= end
    _intake_columns(table, logs)
    _read_columns(table, home, end)
    footer: dict = {
        "open_ledger": None,
        "notes": [],
        "audit_readable": (logs / "audit.jsonl").is_file(),
        "recommender": recommender,
    }
    if repo is None:
        footer["notes"].append("no --repo: drafts / outside / repairs / rm_files / freeze not read")
    else:
        try:
            footer["open_ledger"] = _git_columns(table, repo, end)
        except ScanError as exc:
            footer["notes"].append(f"git/rfcs columns unavailable: {exc}")
    footer["exceptions"] = latest_exceptions(home, end)
    footer["intake"] = intake_counts(home, end)
    if changes is not None:
        footer["reconcile"] = reconcile_changes(table, changes)
    return table, footer


def intake_counts(home: Path, end: date) -> dict:
    """(vi) over the last 28 days: staged / adopted / archived, and ``.staged`` pending."""
    since = end - timedelta(days=27)
    logs = home / "logs"
    staged = sum(1 for r in read_jsonl(logs / "insight-staged.jsonl") if since <= _day(r) <= end)
    adopted = archived = 0
    for r in read_jsonl(logs / "audit.jsonl"):
        if not since <= _day(r) <= end:
            continue
        adopted += _is_adopted(r)
        archived += _is_archived(r)
    pending = len(list((home / ".staged").glob("*.meta.json")))
    return {
        "staged": staged,
        "pending": pending,
        "adopted": int(adopted),
        "archived": int(archived),
    }


def intake_line(counts: dict) -> str:
    """The PIPELINE-STATUS line: names and counts only, no judgement."""
    return (
        f"- ➖ intake — staged 4w: {counts['staged']}, pending: {counts['pending']}, "
        f"adopted 4w: {counts['adopted']}"
    )


def _cell(v: int | None) -> str:
    return "-" if v is None else str(v)


def candidate(table: list[Week], n: int) -> str:
    run = 0
    table = [w for w in table if not w.pending]
    absent = sum(1 for w in table if not w.gate)
    for w in reversed(table):
        if w.gate and w.rulings + w.drafts + (w.outside or 0) == 0:
            run += 1
        else:
            break
    verdict = "self-regulating candidate" if run >= n else f"not a candidate ({run} < {n})"
    return (
        f"zero-load run: {run} week(s) of rulings + drafts + outside = 0 (N = {n}); {verdict}"
        f"; weeks with no gate_record: {absent}. Sufficiency is the owner's "
        "(`gate_record self_regulation_verdict=`)."
    )


def floor(table: list[Week], readable: bool = True) -> str:
    if not readable:
        return "metabolism floor not readable (audit.jsonl missing); no verdict."
    table = [w for w in table if not w.pending]
    run = 0
    for w in reversed(table):
        if w.adopted == 0 and w.archived == 0 and w.identity == 0:
            run += 1
        else:
            break
    state = "metabolism floor reached" if run >= FLOOR_WEEKS else "metabolism floor not reached"
    return (
        f"adopted = 0 and archived = 0 and identity updates = 0 for {run} consecutive week(s) "
        f"(threshold {FLOOR_WEEKS}): {state} (D-P2-01-3 = B: reached files the end-of-run "
        "consideration event under P4-01; it does not declare steady state)."
    )


READ_HEAD = (
    "week",
    "report",
    "inventory (pending/exc/new/cont/disc)",
    *READ_SECTIONS,
    "carried (items/lines)",
    "doc",
    "findings",
)


def render_read_volume(table: list[Week]) -> list[str]:
    """Load series (ii) as its own table: the same eight rows, line counts side by side."""
    lines = [
        "### Reading volume (load series (ii), P2-01.3 / P2-06.1)",
        "",
        "Lines of the weekly report the week's gate reads (`reports/analysis/weekly-{report}.md`, "
        "each section from its `## ` header to the next) and of its findings file. "
        "Read beside the table above, never summed.",
        "",
        "| " + " | ".join(READ_HEAD) + " |",
        "|" + "---|" * len(READ_HEAD),
    ]
    for w in table:
        rv = w.read
        if rv is None:
            gap = "(report pending)" if w.read_pending else "-"
            cells = [w.label, gap, *(["-"] * (len(READ_HEAD) - 2))]
        else:
            cells = [
                w.label,
                rv.stamp,
                "/".join(map(str, rv.inventory)) if rv.inventory else "-",
                *(_cell(v) for v in rv.sections),
                f"{rv.carried_items}/{rv.carried_lines}",
                str(rv.doc_lines),
                _cell(rv.findings_lines),
            ]
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", exceptions_trend(table)]
    return lines


def recommender_line(tally: dict[str, list[int]] | None) -> str:
    """How much of the agreement population names its recommender (D-P2-01-2 = A)."""
    if not tally:
        return "recommender: not read."
    g, rm = tally["gate"], tally["roadmap"]
    return (
        f"recommender recorded on ruled gate_item rows in the window: gate {g[0]}/{g[1]}, "
        f"roadmap {rm[0]}/{rm[1]} (the audit's key, D-P2-01-2 = A; values are not printed)."
    )


def render(table: list[Week], footer: dict, n: int) -> str:
    head = (
        "week",
        "rulings",
        "agree (rec = dec)",
        "gate_min",
        "drafts",
        "outside",
        "repairs",
        "rm_dec",
        "rm_agree",
        "rm_min",
        "rm_files",
        "staged",
        "adopted",
        "archived",
        "empty_sel (judged-empty/judged)",
        "freeze",
    )
    rows = []
    for w in table:
        if w.judged >= MIN_DENOMINATOR:
            sel = f"{format_rate(w.empty, w.judged)}" + (
                f" +{w.rejected_only} rejected-only" if w.rejected_only else ""
            )
        else:
            sel = f"{w.empty}/{w.judged}" + (
                f" +{w.rejected_only} rejected-only" if w.rejected_only else ""
            )
        gm = _cell(w.gate_min)
        if w.gate_min is not None and w.gate_min > TIMETABLE_MIN:
            gm += f" (>{TIMETABLE_MIN})"
        rows.append(
            (
                w.label + ("" if w.gate else " (gate pending)" if w.pending else " (no gate)"),
                str(w.rulings),
                format_rate(w.agree, w.agree_n),
                gm,
                str(w.drafts),
                _cell(w.outside),
                _cell(w.repairs),
                str(w.rm_dec),
                format_rate(w.rm_agree, w.rm_agree_n),
                _cell(w.rm_min),
                _cell(w.rm_files),
                str(w.staged),
                str(w.adopted),
                str(w.archived),
                sel,
                w.freeze,
            )
        )
    lines = [
        "## Self-Regulation Reading",
        "",
        "Columns are read side by side, never summed. `rm_*` are the roadmap's own execution "
        "and are outside rulings / gate_min / outside. `agree` / `rm_agree` = gate_item rows "
        "whose decision equals the briefing's recommendation (k/n, with the Wilson interval "
        "from ten rows; P2-01.9). `-` = source unavailable.",
        "",
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
    ]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    lines += ["", *render_read_volume(table)]
    exc, exc_week = footer["exceptions"]
    lines += [
        "",
        candidate(table, n),
        "",
        floor(table, footer.get("audit_readable", True)),
        "",
        f"(iv) open RFC ledger: {_cell(footer['open_ledger'])} · (v) exceptions: "
        + (f"{exc} (weekly-{exc_week})" if exc is not None else "-"),
        "",
        intake_line(footer["intake"]).removeprefix("- ➖ "),
        "",
        recommender_line(footer.get("recommender")),
        "",
        footer.get("reconcile", "(vi) not reconciled: no --changes given."),
    ]
    notes = footer["notes"] + [x for w in table for x in w.notes]
    if notes:
        lines += ["", "Notes: " + "; ".join(dict.fromkeys(notes))]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--home", type=Path, required=True, help="MOLTBOOK_HOME")
    ap.add_argument("--repo", type=Path, default=None, help="checkout for git / rfcs columns")
    ap.add_argument("--end", default=date.today().isoformat(), help="YYYY-MM-DD")
    ap.add_argument("--weeks", type=int, default=WEEKS)
    ap.add_argument("--n", type=int, default=CANDIDATE_N, help="zero-load weeks for the candidate")
    ap.add_argument("--intake-line", action="store_true", help="print only the intake line")
    ap.add_argument(
        "--changes",
        type=Path,
        default=None,
        help="pipeline/value-layer/changes.json (P2-05.7) to reconcile (vi) against",
    )
    args = ap.parse_args(argv)
    try:
        end = date.fromisoformat(args.end)
        if args.weeks < 1:
            raise ValueError("--weeks must be >= 1")
        table, footer = build(args.home, args.repo, end, args.weeks, args.changes)
    except ValueError as exc:
        print(f"reason=BAD_ARGUMENT {exc}", file=sys.stderr)
        return 2
    except ScanError as exc:
        print(f"reason={exc.reason} {exc.detail}".rstrip(), file=sys.stderr)
        return 2
    print(intake_line(footer["intake"]) if args.intake_line else render(table, footer, args.n))
    return 0


if __name__ == "__main__":
    sys.exit(main())
