#!/usr/bin/env python3
"""Freeze reading: one line saying how much the mechanism layer still moves (P1-01.1).

stdlib only (run with bare ``python3``; ADR-0109) -- no dependency, no network.
Read-only over ``git log`` of the checkout; writes nothing, holds no state.

Roadmap: P1-01.1 / .4 / .7 / .8 (docs/plans/roadmap-2026-10/ROADMAP.md).

What it reads (the four series of P1-01.1, plus the P1-01.7 / .8 extras)
------------------------------------------------------------------------
(i)   commits touching the **frozen set** (``FROZEN_SET`` below, the one place
      the path set lives; ``--table`` prints it as the table the ADR carries),
      per ISO week and conventional-commit type. ``fix`` is the only type that
      does not count as "moved"; ``feat`` / ``refactor`` / ``perf`` / ``docs`` /
      ``chore`` / no prefix all do. A commit that touches a name in
      ``REGIME_PATTERN`` (OLLAMA_MODEL / OLLAMA_EMBEDDING_MODEL / _DEFAULT_*_MODEL)
      is reported as kind ``regime``, apart from fix and from violations.
      Instrument rows are counted in their own column and a **deletion** of an
      instrument file never counts (retiring an instrument is the intended
      direction of travel).
(ii)  new ADRs this calendar month, by ``## Layer`` value when the ADR carries
      one (P1-03.7), otherwise ``unlayered``.
(iii) amendment headings added to ADRs this month (a heading-level proxy for
      "changes Decision / Mechanism"; consumption plans, Review-when and
      Decided-by lines are counted as ``docs_motion`` and reported only), and
      how many of those commits also touch the frozen set.
(iv)  net added lines under ``tests/`` for the week, two series: ``tests/*_shell.py``
      (checks the frozen .sh files) and everything else. Reading only.
(.7)  ``tests/`` files modified or deleted in the window that no item's
      「書き換える既存テスト:」 line names (new files, ``*_shell.py`` and
      ``tests/test_surface_snapshot.py`` are exempt).
(P1-08.10) ``caplog_text``, printed beside (iv): occurrences of the fixed string
      ``caplog.text`` in ``tests/*.py`` (top level, as the shell glob reads it)
      at the last commit on or before ``--end``. Text assertions are what the
      test convention moves to reason codes when a test is touched (CLAUDE.md
      開発原則); the count shows whether that migration happens. Reading only,
      no threshold; its reader and removal are (iv)'s.

Also: ``reproduces_missing`` = frozen-set commits without a ``Reproduces:`` trailer,
and ``quiet_weeks`` = consecutive ISO weeks ending at the reading week with no
non-``fix`` frozen-set commit (a week with no commits is quiet).

Decisions applied (owner, 2026-10-24): D-P1-01-1 = A -- a week is quiet when
the frozen set saw only ``fix`` commits AND no mechanism-layer ADR was added
AND no mechanism-layer amendment heading was added (ADRs without a ``## Layer``
count as mechanism: the stricter reading), and 8 consecutive quiet ISO weeks
(``WINDOW_WEEKS``) make the script say ``freeze candidate``, with the base rate
of quiet weeks in the horizon printed beside it. Additional stage B: instrument
rows are reported in their own column and never enter the quiet-week reading.
D-P1-01-2 = A: a commit touching a model name is kind ``regime`` and does not
reset the run (a forced swap is read, not hidden). The verdict is a human
``gate_record`` entry (``freeze_verdict=``), never this script.

Abstains with ``reason=CODE detail`` on stderr and exit 2 (``scripts/_scan.py``
shape) when git is unusable, rather than printing zeros. A missing
enumeration file degrades only the ``unlisted_tests`` field, with its reason
code in the line.

Consumption plan (ADR-0101): (a) the Saturday gate reads the single line in the
weekly materials (``## Freeze Reading``) every week; the headless report copies
it. (b) one reading answers one question: has ``quiet_weeks`` reached the window
D-P1-01-1 = A fixed (8). (c) removal: after the freeze verdict is recorded, the weekly
stage is dropped and the quarterly T4 reads it instead.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _scan import ScanError  # noqa: E402

# D-P1-01-1 = A (owner, 2026-10-24): 8 consecutive quiet ISO weeks.
WINDOW_WEEKS = 8

DEFAULT_ENUMERATION = "docs/plans/roadmap-2026-10/ROADMAP.md"
ENUMERATION_PHRASE = "書き換える既存テスト"
SNAPSHOT_TEST = "tests/test_surface_snapshot.py"

# P1-01.8: a commit whose diff adds or removes one of these names is a regime
# change (model swap = device boundary), whatever its type.
REGIME_PATTERN = r"OLLAMA_MODEL|OLLAMA_EMBEDDING_MODEL|_DEFAULT_[A-Z_]*MODEL"

MECHANISM = "mechanism"
INSTRUMENT = "instrument"


@dataclass(frozen=True)
class Row:
    """One row of the frozen-set table (P1-01.4).

    ``path`` ending in ``/`` is a directory prefix, otherwise an exact file.
    ``pending`` names a decision that can still drop or retype the row.
    """

    path: str
    kind: str
    note: str = ""
    pending: str = ""


# The table. Instrument rows are listed so they are counted in their own
# column and never enter the quiet-week reading (D-P1-01-1 additional stage B).
FROZEN_SET: tuple[Row, ...] = (
    Row("src/", MECHANISM),
    Row("config/launchd/", MECHANISM),
    Row("config/prompts/", MECHANISM),
    Row("config/domain.json", MECHANISM),
    Row("scripts/weekly-pipeline.sh", MECHANISM, "weekly chain entry"),
    Row("scripts/pipeline_watchdog.sh", MECHANISM),
    Row("scripts/rotate-log.sh", MECHANISM),
    Row("scripts/backup-runtime.sh", MECHANISM),
    Row("scripts/state_invariant_check.py", MECHANISM, "production-path script"),
    Row("scripts/restore-embed-knowledge.py", MECHANISM, "called by backup-runtime.sh"),
    Row(
        ".claude/skills/weekly-report/",
        MECHANISM,
        "SKILL.md + references/diagnosis.md; instruction text of the only LLM stage",
        pending="D-P2-02-1",  # decided A (provisional): kept as mechanism; B would drop it
    ),
    # Instrument scripts the weekly chain calls (deletions never count).
    Row("scripts/instrument_census.py", INSTRUMENT),
    Row("scripts/_census_registry.py", INSTRUMENT),
    Row("scripts/_census_series.py", INSTRUMENT),
    Row("scripts/api_drift_scan.py", INSTRUMENT),
    Row("scripts/cross_day_duplicate_scan.py", INSTRUMENT),
    Row("scripts/log_anomaly_sweep.py", INSTRUMENT),
    Row("scripts/observation_ledger.py", INSTRUMENT),
    Row("scripts/value_layer_approval_join.py", INSTRUMENT),
    Row("scripts/weekly_random_sample.py", INSTRUMENT),
    Row("scripts/confusion_pair_reading.py", INSTRUMENT),
    Row("scripts/dead_code_scan.py", INSTRUMENT),
    Row("scripts/weekly-analysis.sh", INSTRUMENT, "materials collector"),
)


def active_rows(exclude_pending: Iterable[str] = ()) -> tuple[Row, ...]:
    gone = set(exclude_pending)
    return tuple(r for r in FROZEN_SET if r.pending not in gone)


def path_kind(path: str, rows: tuple[Row, ...] = FROZEN_SET) -> str | None:
    """Kind of a path under the frozen-set table, or None when outside it."""
    for r in rows:
        if r.path.endswith("/"):
            if path.startswith(r.path):
                return r.kind
        elif path == r.path:
            return r.kind
    return None


def table_markdown(rows: tuple[Row, ...] = FROZEN_SET) -> str:
    out = ["| path | kind | pending decision | note |", "|---|---|---|---|"]
    for r in rows:
        out.append(f"| `{r.path}` | {r.kind} | {r.pending or '-'} | {r.note or '-'} |")
    return "\n".join(out)


_TYPE_RE = re.compile(r"^([A-Za-z]+)(\([^)]*\))?!?:")


def commit_type(subject: str) -> str:
    m = _TYPE_RE.match(subject)
    return m.group(1).lower() if m else "none"


@dataclass(frozen=True)
class Commit:
    sha: str
    day: date
    subject: str
    has_reproduces: bool
    files: tuple[tuple[str, str], ...]  # (status letter, path)


def iso_week(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def _git(repo: Path, *args: str) -> str:
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), "--no-pager", *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ScanError("GIT_UNAVAILABLE", str(exc)) from exc
    if res.returncode != 0:
        raise ScanError("GIT_FAILED", (res.stderr.strip().splitlines() or ["?"])[-1][:200])
    return res.stdout


_RS, _US = "\x1e", "\x1f"


def read_commits(repo: Path, since: date, until: date) -> list[Commit]:
    fmt = f"{_RS}%H{_US}%cI{_US}%s{_US}%(trailers:key=Reproduces,valueonly,separator=%x2C)"
    raw = _git(
        repo,
        "log",
        "--no-renames",
        "--name-status",
        f"--format={fmt}",
        f"--since={since.isoformat()}T00:00:00",
        f"--until={until.isoformat()}T23:59:59",
    )
    commits: list[Commit] = []
    for rec in raw.split(_RS):
        if not rec.strip():
            continue
        head, _, tail = rec.partition("\n")
        parts = head.split(_US)
        if len(parts) < 4:
            continue
        sha, iso, subject, repro = parts[0], parts[1], parts[2], parts[3]
        files = []
        for line in tail.splitlines():
            if "\t" in line:
                st, p = line.split("\t", 1)
                files.append((st.strip()[:1], p.strip()))
        commits.append(
            Commit(sha, date.fromisoformat(iso[:10]), subject, bool(repro.strip()), tuple(files))
        )
    return commits


def regime_shas(repo: Path, since: date, until: date, rows: tuple[Row, ...]) -> set[str]:
    """Commits whose diff adds/removes a model-name token inside a frozen path."""
    pathspecs = [r.path for r in rows if r.kind == MECHANISM]
    raw = _git(
        repo,
        "log",
        "--format=%H",
        "-G" + REGIME_PATTERN,
        f"--since={since.isoformat()}T00:00:00",
        f"--until={until.isoformat()}T23:59:59",
        "--",
        *pathspecs,
    )
    return {s for s in raw.split() if s}


@dataclass(frozen=True)
class Touch:
    mechanism: bool
    instrument: bool  # a non-deletion touch of an instrument row


def touch_of(c: Commit, rows: tuple[Row, ...]) -> Touch:
    mech = inst = False
    for st, p in c.files:
        k = path_kind(p, rows)
        if k == MECHANISM:
            mech = True  # a deleted mechanism file is a move too
        elif k == INSTRUMENT and st != "D":
            inst = True
    return Touch(mech, inst)


def week_summary(
    commits: list[Commit], rows: tuple[Row, ...], regimes: set[str]
) -> dict[str, Counter]:
    """ISO week -> Counter of mechanism kinds / instrument commits."""
    weeks: dict[str, Counter] = defaultdict(Counter)
    for c in commits:
        t = touch_of(c, rows)
        wk = iso_week(c.day)
        if t.mechanism:
            kind = "regime" if c.sha in regimes else commit_type(c.subject)
            weeks[wk]["mechanism"] += 1
            weeks[wk]["fix" if kind == "fix" else ("regime" if kind == "regime" else "nonfix")] += 1
            if not c.has_reproduces:
                weeks[wk]["reproduces_missing"] += 1
        if t.instrument:
            weeks[wk]["instrument"] += 1
    return weeks


def read_enumeration(path: Path) -> set[str]:
    """tests/ files named on any 「書き換える既存テスト:」 line."""
    named: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        i = line.find(ENUMERATION_PHRASE)
        if i < 0:
            continue
        named.update(re.findall(r"tests/[\w./-]+\.py", line[i:]))
    return named


def unlisted_tests(commits: list[Commit], named: set[str]) -> list[str]:
    """tests/ files modified/deleted (not added) outside the enumeration."""
    out: set[str] = set()
    for c in commits:
        for st, p in c.files:
            if not p.startswith("tests/") or not p.endswith(".py"):
                continue
            if st == "A" or p.endswith("_shell.py") or p == SNAPSHOT_TEST or p in named:
                continue
            out.add(p)
    return sorted(out)


def tests_net_lines(repo: Path, since: date, until: date) -> tuple[int, int]:
    """(src series, scripts series) net added lines under tests/ in the window."""
    raw = _git(
        repo,
        "log",
        "--numstat",
        "--format=",
        f"--since={since.isoformat()}T00:00:00",
        f"--until={until.isoformat()}T23:59:59",
        "--",
        "tests/",
    )
    src = shell = 0
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        net = int(parts[0]) - int(parts[1])
        if parts[2].endswith("_shell.py"):
            shell += net
        else:
            src += net
    return src, shell


_TOP_LEVEL_TEST = re.compile(r"^tests/[^/]+\.py$")


def caplog_text_count(repo: Path, end: date) -> int | None:
    """``grep -o caplog.text tests/*.py | wc -l`` over the tree of the last commit on or before ``end``.

    Read from that commit rather than the working tree so a past ``--end`` reads
    its own week. ``None`` when no commit precedes ``end``. A git failure raises
    ``ScanError``; the caller degrades only this field.
    """
    sha = _git(repo, "rev-list", "-1", f"--before={end.isoformat()}T23:59:59", "HEAD").strip()
    if not sha:
        return None
    try:
        res = subprocess.run(
            ["git", "-C", str(repo), "--no-pager", "grep", "-o", "-F", "caplog.text", sha, "--"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise ScanError("GIT_UNAVAILABLE", str(exc)) from exc
    if res.returncode == 1:  # git grep: no match
        return 0
    if res.returncode != 0:
        raise ScanError("GIT_FAILED", (res.stderr.strip().splitlines() or ["?"])[-1][:200])
    # Each match prints as "<sha>:<path>:caplog.text"; keep tests/*.py (top level).
    paths = [out_line.split(":", 2)[1:2] for out_line in res.stdout.splitlines()]
    return sum(1 for path in paths if path and _TOP_LEVEL_TEST.match(path[0]))


_ADR_FILE = re.compile(r"^docs/adr/(\d{4})-[^/]*\.md$")
_AMEND_HEADING = re.compile(r"^#{2,3} .*(Amendment|amendment|追補)")
_AMEND_LAYER = re.compile(r"(?:Amendment|追補)[^()（]*[(（]\d{4}-\d\d-\d\d, (\w+)[)）]")
_DOCS_MOTION = re.compile(r"^#{2,3} .*(Consumption plan|Review-when|Decided by)")

# D-P1-01-1 = A: a week is only quiet when no new mechanism ADR and no
# mechanism amendment landed. ADRs that carry no layer yet count as
# mechanism: the stricter reading never declares a candidate by mistake.
_MECHANISM_LAYERS = ("mechanism", "unlayered")


def _adr_layer(repo: Path, path: str) -> str:
    try:
        lines = (repo / path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return "unlayered"
    for i, ln in enumerate(lines):
        if ln.strip() == "## Layer":
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    return nxt.strip().strip("*`").split()[0].lower()
    return "unlayered"


@dataclass(frozen=True)
class AdrEvent:
    day: date
    kind: str  # "new" | "amend" | "docs_motion"
    layer: str
    with_frozen: bool = False


def _added_adrs(repo: Path, since: date, until: date) -> list[AdrEvent]:
    raw = _git(
        repo,
        "log",
        "--no-renames",
        "--diff-filter=A",
        "--name-only",
        f"--format={_RS}%cI",
        f"--since={since.isoformat()}T00:00:00",
        f"--until={until.isoformat()}T23:59:59",
        "--",
        "docs/adr/",
    )
    out = []
    for rec in raw.split(_RS):
        if not rec.strip():
            continue
        iso, _, names = rec.partition("\n")
        for p in names.split():
            if _ADR_FILE.match(p) and not p.endswith(".ja.md"):
                out.append(
                    AdrEvent(date.fromisoformat(iso.strip()[:10]), "new", _adr_layer(repo, p))
                )
    return out


def _patch_events(repo: Path, since: date, until: date, frozen: dict[str, bool]) -> list[AdrEvent]:
    patch = _git(
        repo,
        "log",
        "--no-renames",
        "-p",
        "-U0",
        f"--format={_RS}%H{_US}%cI",
        f"--since={since.isoformat()}T00:00:00",
        f"--until={until.isoformat()}T23:59:59",
        "--",
        "docs/adr/",
    )
    out: list[AdrEvent] = []
    for rec in patch.split(_RS):
        if not rec.strip():
            continue
        head, _, body = rec.partition("\n")
        sha, _, iso = head.partition(_US)
        day = date.fromisoformat(iso.strip()[:10])
        cur = ""
        for line in body.splitlines():
            if line.startswith("+++ b/"):
                cur = line[6:]
            elif (
                line.startswith("+")
                and not line.startswith("+++")
                and _ADR_FILE.match(cur)
                and not cur.endswith(".ja.md")
            ):
                text = line[1:]
                if _AMEND_HEADING.match(text):
                    m = _AMEND_LAYER.search(text)
                    layer = m.group(1).lower() if m else _adr_layer(repo, cur)
                    out.append(AdrEvent(day, "amend", layer, frozen.get(sha, False)))
                elif _DOCS_MOTION.match(text):
                    out.append(AdrEvent(day, "docs_motion", ""))
    return out


def adr_events(repo: Path, since: date, until: date, rows: tuple[Row, ...]) -> list[AdrEvent]:
    frozen = {c.sha: touch_of(c, rows).mechanism for c in read_commits(repo, since, until)}
    return _added_adrs(repo, since, until) + _patch_events(repo, since, until, frozen)


def adr_quiet_weeks(events: list[AdrEvent]) -> set[str]:
    """ISO weeks holding a mechanism-layer new ADR or amendment (not quiet)."""
    return {
        iso_week(e.day)
        for e in events
        if e.kind in ("new", "amend") and e.layer in _MECHANISM_LAYERS
    }


def quiet_run(
    weeks: dict[str, Counter], adr_noisy: set[str], end: date, horizon: int
) -> tuple[int, int]:
    """(consecutive quiet weeks ending at ``end``, quiet weeks in the horizon).

    Quiet = fix-only frozen-set commits AND no mechanism ADR / amendment
    (D-P1-01-1 = A). Regime commits and instrument rows do not break a week.
    """

    def quiet(d: date) -> bool:
        wk = iso_week(d)
        return weeks.get(wk, Counter())["nonfix"] == 0 and wk not in adr_noisy

    run = 0
    for k in range(horizon):
        if not quiet(end - timedelta(days=7 * k)):
            break
        run += 1
    total = sum(quiet(end - timedelta(days=7 * k)) for k in range(horizon))
    return run, total


def _fmt_counter(c: Counter) -> str:
    return ",".join(f"{k}={v}" for k, v in sorted(c.items())) or "0"


def build_line(
    repo: Path,
    end: date,
    weeks_back: int,
    window: int | None,
    enumeration: Path,
    exclude_pending: Iterable[str] = (),
) -> str:
    rows = active_rows(exclude_pending)
    window = WINDOW_WEEKS if window is None else window
    monday = end - timedelta(days=end.weekday())
    horizon_start = min(monday - timedelta(days=7 * (weeks_back - 1)), end.replace(day=1))
    commits = read_commits(repo, horizon_start, end)
    regimes = regime_shas(repo, horizon_start, end, rows)
    weeks = week_summary(commits, rows, regimes)
    this = weeks.get(iso_week(end), Counter())
    week_commits = [c for c in commits if monday <= c.day <= end]
    events = adr_events(repo, horizon_start, end, rows)
    run, quiet_total = quiet_run(weeks, adr_quiet_weeks(events), end, weeks_back)
    src_net, shell_net = tests_net_lines(repo, monday, end)
    month = [e for e in events if (e.day.year, e.day.month) == (end.year, end.month)]
    new_c = Counter(e.layer for e in month if e.kind == "new")
    amend_c = Counter(e.layer for e in month if e.kind == "amend")
    amend_frozen = sum(1 for e in month if e.kind == "amend" and e.with_frozen)
    docs_motion = sum(1 for e in month if e.kind == "docs_motion")

    try:
        named = read_enumeration(enumeration)
        unl = unlisted_tests(week_commits, named)
        unl_txt = f"{len(unl)}" + (f"({','.join(unl[:5])})" if unl else "")
    except OSError as exc:
        unl_txt = f"n/a(reason=ENUMERATION_UNREADABLE {type(exc).__name__})"

    try:
        caplog = caplog_text_count(repo, end)
        caplog_txt = "n/a(reason=NO_COMMIT)" if caplog is None else str(caplog)
    except ScanError as exc:
        caplog_txt = f"n/a(reason={exc.reason})"

    cand = "freeze candidate" if run >= window else f"no(quiet_weeks {run} < window {window})"
    ym = end.strftime("%Y-%m")
    return (
        f"freeze_reading week={iso_week(end)} "
        f"mechanism_commits={this['mechanism']} fix={this['fix']} nonfix={this['nonfix']} "
        f"regime={this['regime']} reproduces_missing={this['reproduces_missing']} "
        f"instrument_commits={this['instrument']} quiet_weeks={run} "
        f"base_rate_quiet={quiet_total}/{weeks_back} "
        f"adr_new[{ym}]={_fmt_counter(new_c)} adr_amend[{ym}]={_fmt_counter(amend_c)} "
        f"amend_with_frozen={amend_frozen} docs_motion={docs_motion} "
        f"tests_net_lines(src={src_net:+d},scripts={shell_net:+d}) caplog_text={caplog_txt} "
        f"unlisted_tests={unl_txt} candidate={cand}"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent))
    ap.add_argument(
        "--end", default=date.today().isoformat(), help="YYYY-MM-DD, end of the reading week"
    )
    ap.add_argument("--weeks", type=int, default=12, help="history horizon in ISO weeks")
    ap.add_argument(
        "--window",
        type=int,
        default=None,
        help=f"quiet-week window (default {WINDOW_WEEKS}, D-P1-01-1 = A)",
    )
    ap.add_argument(
        "--enumeration",
        default=None,
        help=f"file holding the \u300c{ENUMERATION_PHRASE}:\u300d lines (default <repo>/{DEFAULT_ENUMERATION})",
    )
    ap.add_argument(
        "--exclude-pending",
        action="append",
        default=[],
        help="drop rows pending this decision id (e.g. D-P2-02-1)",
    )
    ap.add_argument("--table", action="store_true", help="print the frozen-set table and exit")
    args = ap.parse_args(argv)

    if args.table:
        print(table_markdown(active_rows(args.exclude_pending)))
        return 0
    repo = Path(args.repo)
    enum = Path(args.enumeration) if args.enumeration else repo / DEFAULT_ENUMERATION
    try:
        end = date.fromisoformat(args.end)
        print(build_line(repo, end, args.weeks, args.window, enum, args.exclude_pending))
    except ValueError as exc:
        print(f"reason=BAD_ARGUMENT {exc}", file=sys.stderr)
        return 2
    except ScanError as exc:
        print(f"reason={exc.reason} {exc.detail}".rstrip(), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
