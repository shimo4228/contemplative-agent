#!/usr/bin/env python3
"""Self-regulation reading: eight weeks of load and metabolism side by side (P2-01.5).

stdlib only (run with bare ``python3``; ADR-0109). Read-only over the
self-written logs under ``$MOLTBOOK_HOME`` (never ``logs/episodes/`` or any
``*.log``), ``rfcs/`` and ``git log`` of the checkout; writes nothing, holds no
state. Roadmap: P2-01.2 / .3 / .5 / .7 / .8 / .13.

What one row (an ISO week, Monday-Sunday, eight of them) carries -- columns are
**side by side and never composed** into one number (ADR-0080 amendment 2026-08-26,
"no single scalar"):

``rulings``      (i)  gate_record: adopted + rejected + deleted + whitelisted + archived.
                      ``*_held`` is a deferral, not a ruling.
``gate_min``     P2-01.2  minutes from the week's first ``gate_start`` to its last
                      ``gate_record``, minus the roadmap part (compare with the
                      127-minute timetable of weekly-gate Step 0). ``-`` when either
                      end is missing.
``drafts``       (ii) new ``origin: gate`` RFC files (first commit date in the week).
``outside``      (iii) distinct files other than ``rfcs/README.md`` touched by the
                      week's Saturday commits that carry no ``Roadmap:`` trailer.
``repairs``      ``fix`` commits of the week (any day) -- the repair-PR count.
``rm_dec`` / ``rm_min`` / ``rm_files``   P2-01.13 the roadmap's own execution,
                      separated: ``category=roadmap`` gate_item rows, the
                      ``roadmap_start``..``roadmap_end`` minutes, and the files of
                      commits carrying a ``Roadmap:`` trailer. They are not in
                      ``rulings`` / ``gate_min`` / ``outside``, so they cannot move
                      the candidate declaration.
``staged/adopted/archived``  (vi) insight staged (``insight-staged.jsonl`` rows),
                      adopted and archived (``audit.jsonl``, same rules as the census
                      gate section). Reconcile against ``pipeline/value-layer/changes.json``
                      once P2-05.7 lands; until then this is the script's own count.
``empty_sel``    P2-01.7 judged-empty / judged in ``skill-selection-*.jsonl`` with the
                      Wilson interval (``_stats``); ``rejected_names``-only rows are a
                      separate count. Under ten judged rows only the counts print.
``freeze``       P2-01.5 "stops" column: ``nonfix`` and ``quiet_weeks`` copied from
                      ``scripts/freeze_reading.py``'s one line for that week. This script
                      runs no git analysis of the frozen set itself.

Not per-week, printed once below the table: (iv) open RFC ledger count and (v)
the latest ``exceptions N`` of the weekly Inventory line (a snapshot, so it cannot
be recomputed for a past week).

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


def _gate_columns(table: list[Week], pm: list[dict]) -> None:
    """Rulings, gate minutes and the roadmap's own part, from ``pipeline-metrics.jsonl``."""
    by = {w.label: w for w in table}
    marks: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    for r in pm:
        w = by.get(week_of(_day(r)))
        dt, ev = _ts(r.get("ts")), r.get("event")
        if w is None or dt is None or not isinstance(ev, str):
            continue
        marks[(w.label, ev)].append(dt)
        if ev == "gate_record":
            w.gate = True
            w.rulings += sum(_num(r.get(f)) for f in GATE_DECISION_FIELDS)
        elif ev == "gate_item" and r.get("category") == "roadmap" and r.get("decision") != "closed":
            w.rm_dec += 1

    def minutes(label: str, a: str, b: str) -> int | None:
        if (label, a) not in marks or (label, b) not in marks:
            return None
        return max(0, round((max(marks[(label, b)]) - min(marks[(label, a)])).total_seconds() / 60))

    for w in table:
        w.rm_min = minutes(w.label, "roadmap_start", "roadmap_end")
        total = minutes(w.label, "gate_start", "gate_record")
        w.gate_min = None if total is None else max(0, total - (w.rm_min or 0))


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


def build(home: Path, repo: Path | None, end: date, weeks: int) -> tuple[list[Week], dict]:
    logs = home / "logs"
    if not logs.is_dir():
        raise ScanError("SELFREG_NO_LOG_DIR", str(logs))
    table = [Week(*s) for s in week_span(end, weeks)]
    _gate_columns(table, read_jsonl(logs / "pipeline-metrics.jsonl"))
    # The weekly chain runs Saturday 09:00 with --end Friday; the gate (and its
    # gate_record) comes later, so a gate-less last week is pending, not absent.
    last = table[-1]
    last.pending = not last.gate and last.monday + timedelta(days=5) >= end
    _intake_columns(table, logs)
    footer: dict = {
        "open_ledger": None,
        "notes": [],
        "audit_readable": (logs / "audit.jsonl").is_file(),
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


def render(table: list[Week], footer: dict, n: int) -> str:
    head = (
        "week",
        "rulings",
        "gate_min",
        "drafts",
        "outside",
        "repairs",
        "rm_dec",
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
                gm,
                str(w.drafts),
                _cell(w.outside),
                _cell(w.repairs),
                str(w.rm_dec),
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
        "and are outside rulings / gate_min / outside. `-` = source unavailable.",
        "",
        "| " + " | ".join(head) + " |",
        "|" + "---|" * len(head),
    ]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
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
    args = ap.parse_args(argv)
    try:
        end = date.fromisoformat(args.end)
        if args.weeks < 1:
            raise ValueError("--weeks must be >= 1")
        table, footer = build(args.home, args.repo, end, args.weeks)
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
