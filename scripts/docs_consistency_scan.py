#!/usr/bin/env python3
"""Weekly docs-consistency intake — the sixth deterministic intake (ADR-0093).

Scans the repo checkout's own documentation corpus (docs/ + CLAUDE.md +
READMEs — all self-authored, so nothing here is untrusted text) and emits a
JSON findings list on stdout for the Saturday gate. Detection and repair are
separated by construction: the scan is read-only, its per-week JSON is read
directly by /weekly-gate — bypassing the unattended LLM session — and any doc
edit stays a human commit at the gate.

Why this exists: the two observed instances of this defect class (ADR-0081's
refuted-but-unmarked safety argument; a ledger citation of a rules clause
that no longer exists) were both caught *incidentally* by a reviewer doing
other work. This intake makes the deterministic 80% of that class a weekly
reading instead of an accident.

Checks (findings):
- enja_drift   — an ADR's English canonical was committed after its .ja.md
                 twin (the docs-language policy expects same-PR updates)
- broken_link  — a relative Markdown link whose target does not exist in the
                 checkout (fenced blocks and inline code spans are skipped)
- notes_ref    — an ADR referencing `.notes/` (gitignored: broken in every
                 clone; the CLAUDE.md docs-placement rule forbids it)

Readings (never findings — ages carry no threshold; the gate reads them):
- codemaps_freshness — generated-date age and commits-behind of each
                 FRESHNESS header under docs/CODEMAPS/ + docs/CYCLES.md
- mechanism_freshness — commits touching src/ or scripts/ since
                 architecture.md's last commit (proxy for the CLAUDE.md
                 same-PR Data Flow covenant; whether they were
                 mechanism-layer is the reader's judgment)

Faults degrade, they never lie: a git failure or unreadable file lands in
``errors`` with a reason code while the remaining checks still run; only an
unusable repo root abstains nonzero (DOCSCAN_FAIL on stderr) — a broken scan
must never read as "docs all clean this week" (ADR-0077).

Semantic staleness (a *claim* refuted by later evidence) is out of scope by
design — that judgment needs an LLM and belongs to a human-triggered session,
not the unattended chain (ADR-0093).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Iterable
from datetime import date, datetime
from pathlib import Path

from _scan import ScanError

# Bounded subprocess calls: the pipeline wraps the whole scan in with_timeout,
# but each git call is also bounded so one hung invocation cannot eat the
# stage budget alone.
_GIT_TIMEOUT = 30

_LINK_RE = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
_CODE_SPAN_RE = re.compile(r"`[^`]*`")
_FRESHNESS_RE = re.compile(r"<!--\s*\nFRESHNESS\n(?P<body>.*?)-->", re.DOTALL)
# codemap-writer's one-line stamp: `<!-- Generated: DATE | Updated: DATE (note) … -->`
_ONELINE_FRESHNESS_RE = re.compile(
    r"<!--\s*Generated:\s*(?P<generated>\d{4}-\d{2}-\d{2})"
    r"(?:.*?Updated:\s*(?P<updated>\d{4}-\d{2}-\d{2}))?"
)
_SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")

# Root-level docs scanned in addition to docs/**; AGENTS.md is a symlink to
# CLAUDE.md and symlinks are skipped wholesale. An explicit allowlist, not a
# glob: root scratch files must not enter the scan. CHANGELOG.md is excluded
# BY DECISION — release notes are a historical record of the release-time
# tree, and their links are not repair targets.
_ROOT_DOCS = ("CLAUDE.md", "README.md", "README.ja.md")


def _git(root: Path, *args: str) -> str | None:
    """Run a git query; None on any failure (callers surface GIT_FAIL).

    Explicit utf-8/replace, not text=True: under launchd's unset LANG the
    default decode is ASCII and a non-ASCII path would raise (the
    dead_code_scan lesson).
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=_GIT_TIMEOUT,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def git_last_commit_ts(root: Path) -> Callable[[Path], int | None]:
    """Committer timestamp of each file's last commit (the enja_drift basis).

    One `git log --name-only` walk over docs/adr serves every pair — the
    per-file `git log -1` form costs ~190 subprocesses (~6s), which the shell
    test would pay on every pytest run. The walk is newest-first, so the
    first-seen timestamp per path is its last commit.
    """
    cache: dict[str, int] | None = None
    loaded = False  # a FAILED walk is cached too — one degraded git costs one
    # subprocess, not one per pair (2026-08-14 codex review P2: the retry
    # storm would eat the stage timeout and turn GIT_FAIL into DOCSCAN_FAIL)

    def _load() -> dict[str, int] | None:
        # quotepath=false: a non-ASCII ADR name would otherwise be emitted
        # octal-escaped and never match its dict key (all names are ASCII
        # today — cheap hardening, 2026-08-14 code review).
        out = _git(
            root,
            "-c",
            "core.quotepath=false",
            "log",
            "--format=COMMIT:%ct",
            "--name-only",
            "--",
            "docs/adr",
        )
        if out is None:
            return None
        seen: dict[str, int] = {}
        current: int | None = None
        for line in out.splitlines():
            if line.startswith("COMMIT:"):
                try:
                    current = int(line[len("COMMIT:") :])
                except ValueError:
                    current = None
            elif line and current is not None:
                seen.setdefault(line, current)
        return seen

    def _ts(rel: Path) -> int | None:
        nonlocal cache, loaded
        if not loaded:
            cache = _load()
            loaded = True
        return cache.get(str(rel)) if cache is not None else None

    return _ts


def git_commits_behind(root: Path) -> Callable[[str], int | None]:
    """Commit count from a FRESHNESS source-commit to HEAD."""

    def _behind(sha: str) -> int | None:
        if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
            return None
        out = _git(root, "rev-list", "--count", f"{sha}..HEAD")
        try:
            return int(out) if out else None
        except ValueError:
            return None

    return _behind


def extract_links(text: str) -> list[tuple[int, str]]:
    """Relative link targets with line numbers; external/anchor links skipped.

    Fenced code blocks and inline code spans are excluded — docs quote example
    links, and a quoted example must not read as a broken reference.
    """
    links: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for match in _LINK_RE.finditer(_CODE_SPAN_RE.sub("", line)):
            target = match.group(1).strip()
            # `](path "title")` — the title is display metadata, not the path.
            if ' "' in target:
                target = target.split(' "', 1)[0]
            if not target or target.startswith(_SKIP_PREFIXES) or "://" in target:
                continue
            target = target.split("#", 1)[0]
            if target:
                links.append((lineno, target))
    return links


def find_md_files(root: Path) -> list[Path]:
    """Repo-relative Markdown files in scope (docs/** + root docs), no symlinks."""
    files = [Path(name) for name in _ROOT_DOCS if (root / name).is_file()]
    docs = root / "docs"
    if docs.is_dir():
        files.extend(p.relative_to(root) for p in sorted(docs.rglob("*.md")))
    return [f for f in files if not (root / f).is_symlink()]


def check_links(root: Path, rel_files: Iterable[Path]) -> tuple[list[dict], list[dict]]:
    findings: list[dict] = []
    errors: list[dict] = []
    root_resolved = root.resolve()
    for rel in rel_files:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(
                {"check": "broken_link", "reason": "FILE_UNREADABLE", "detail": f"{rel}: {exc}"}
            )
            continue
        for lineno, target in extract_links(text):
            resolved = ((root / rel).parent / target).resolve()
            # An ../-escape that happens to exist on the host is still broken
            # in every clone — existence only counts inside the checkout
            # (2026-08-14 codex review P2).
            if not resolved.is_relative_to(root_resolved):
                detail = f"target resolves outside the repository: {target}"
            elif not resolved.exists():
                detail = f"target does not exist: {target}"
            else:
                continue
            findings.append(
                {"check": "broken_link", "file": str(rel), "line": lineno, "detail": detail}
            )
    return findings, errors


def adr_pairs(root: Path) -> list[tuple[Path, Path]]:
    """(en, ja) repo-relative pairs for every ADR that has a .ja.md twin."""
    adr_dir = root / "docs" / "adr"
    if not adr_dir.is_dir():
        return []
    pairs: list[tuple[Path, Path]] = []
    for en in sorted(adr_dir.glob("*.md")):
        if en.name.endswith(".ja.md"):
            continue
        ja = en.with_name(en.name[: -len(".md")] + ".ja.md")
        if ja.is_file():
            pairs.append((en.relative_to(root), ja.relative_to(root)))
    return pairs


def check_pair_drift(
    pairs: Iterable[tuple[Path, Path]], ts: Callable[[Path], int | None]
) -> tuple[list[dict], list[dict]]:
    """Flag ADRs whose English canonical outran the Japanese twin."""
    findings: list[dict] = []
    errors: list[dict] = []
    for en, ja in pairs:
        en_ts, ja_ts = ts(en), ts(ja)
        if en_ts is None or ja_ts is None:
            errors.append(
                {"check": "enja_drift", "reason": "GIT_FAIL", "detail": f"no timestamp: {en}"}
            )
            continue
        if en_ts > ja_ts:
            findings.append(
                {
                    "check": "enja_drift",
                    "file": str(en),
                    "line": None,
                    "detail": f"en committed after ja ({en_ts - ja_ts}s gap): {ja}",
                }
            )
    return findings, errors


def check_notes_refs(root: Path, rel_files: Iterable[Path]) -> tuple[list[dict], list[dict]]:
    """Flag ADR text referencing the gitignored `.notes/` ledger dir."""
    findings: list[dict] = []
    errors: list[dict] = []
    for rel in rel_files:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(
                {"check": "notes_ref", "reason": "FILE_UNREADABLE", "detail": f"{rel}: {exc}"}
            )
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ".notes/" in line:
                findings.append(
                    {
                        "check": "notes_ref",
                        "file": str(rel),
                        "line": lineno,
                        "detail": ".notes/ is gitignored — broken in every clone",
                    }
                )
    return findings, errors


def parse_freshness(text: str) -> dict | None:
    """Extract the effective date / source-commit from a freshness header.

    Two stamp dialects exist: the block-form FRESHNESS comment (CYCLES.md)
    and codemap-writer's one-line `Generated: … | Updated: …` comment, where
    Updated (when present) is the effective date and no commit is recorded.
    """
    match = _FRESHNESS_RE.search(text)
    if match is None:
        oneline = _ONELINE_FRESHNESS_RE.search(text)
        if oneline is None:
            return None
        return {
            "generated": oneline.group("updated") or oneline.group("generated"),
            "source_commit": None,
        }
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, _, value = line.strip().partition(":")
        if value:
            fields[key.strip()] = value.strip()
    return {
        "generated": fields.get("generated"),
        "source_commit": fields.get("source-commit"),
    }


def codemaps_freshness(
    root: Path, behind: Callable[[str], int | None], today: date
) -> tuple[list[dict], list[dict]]:
    """Age readings for FRESHNESS-stamped docs. Readings only, no threshold."""
    readings: list[dict] = []
    errors: list[dict] = []
    targets = (
        sorted((root / "docs" / "CODEMAPS").glob("*.md"))
        if (root / "docs" / "CODEMAPS").is_dir()
        else []
    )
    cycles = root / "docs" / "CYCLES.md"
    if cycles.is_file():
        targets.append(cycles)
    for path in targets:
        rel = path.relative_to(root)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(
                {
                    "check": "codemaps_freshness",
                    "reason": "FILE_UNREADABLE",
                    "detail": f"{rel}: {exc}",
                }
            )
            continue
        parsed = parse_freshness(text)
        if parsed is None:
            continue
        days_old: int | None = None
        generated = parsed["generated"]
        if generated:
            try:
                days_old = (today - datetime.strptime(generated, "%Y-%m-%d").date()).days
            except ValueError:
                days_old = None
        commits_behind: int | None = None
        sha = parsed["source_commit"]
        if sha:
            commits_behind = behind(sha)
            if commits_behind is None:
                errors.append(
                    {
                        "check": "codemaps_freshness",
                        "reason": "GIT_FAIL",
                        "detail": f"rev-list failed for {rel} ({sha})",
                    }
                )
        readings.append(
            {
                "file": str(rel),
                "generated": generated,
                "source_commit": sha,
                "commits_behind": commits_behind,
                "days_old": days_old,
            }
        )
    return readings, errors


# What the Data Flow section documents stage-by-stage lives in BOTH trees:
# src/ (core pipeline) and scripts/ (weekly stages). Measured over three
# historical windows, src/ alone misses ~40% of covenant-relevant commits
# (2026-08-25 code review) — this very reading's own commit touched only
# scripts/ + tests/.
_MECHANISM_PATHSPECS = ("src/", "scripts/")


def mechanism_freshness(
    root: Path, run: Callable[..., str | None]
) -> tuple[dict | None, list[dict]]:
    """Reading only: commits touching the mechanism trees since architecture.md
    was last committed.

    The deterministic proxy for the CLAUDE.md freshness covenant (mechanism
    changes update architecture.md's Data Flow in the same PR). Whether any of
    those commits *were* mechanism-layer is a semantic judgment — that stays
    with the weekly session and the gate; no threshold here.

    Known false-negative direction: the anchor is architecture.md's last
    commit of ANY kind, so an unrelated edit to the file (a link fix at the
    gate) resets the count and can erase a still-undocumented mechanism
    change. The reading is a weekly nudge, not an audit trail — the week the
    violation happens it IS visible, and that is the read-and-judge moment.

    A repo without docs/CODEMAPS/architecture.md has no covenant to proxy:
    reading None with no error (the scan runs on clones and test repos).
    Every degraded arm past that point surfaces GIT_FAIL with the arm named —
    none may read as a confident 0 ("covenant clean").
    """
    rel = Path("docs") / "CODEMAPS" / "architecture.md"
    if not (root / rel).is_file():
        return None, []

    def _fail(arm: str) -> tuple[None, list[dict]]:
        return None, [
            {"check": "mechanism_freshness", "reason": "GIT_FAIL", "detail": arm}
        ]

    pathspecs = [p for p in _MECHANISM_PATHSPECS if (root / p).is_dir()]
    if not pathspecs:
        # rev-list over a matching-nothing pathspec exits 0 printing 0 — a
        # layout move would otherwise read as permanently clean.
        return _fail(
            f"no mechanism tree ({', '.join(_MECHANISM_PATHSPECS)}) exists — "
            "a layout move must update _MECHANISM_PATHSPECS"
        )
    sha = run(root, "log", "-1", "--format=%H", "--", str(rel))
    if not sha:
        # `git log -1 -- <untracked>` exits 0 with empty stdout: no base
        # commit, nothing to count from.
        return _fail(f"{rel} has no commit (untracked?)")
    if not re.fullmatch(r"[0-9a-f]{7,40}", sha):
        return _fail(f"log emitted a non-SHA for {rel}")
    raw = run(root, "rev-list", "--count", f"{sha}..HEAD", "--", *pathspecs)
    if raw is None:
        return _fail(f"rev-list failed for {sha[:7]}..HEAD")
    try:
        count = int(raw)
    except ValueError:
        return _fail(f"rev-list emitted a non-count for {sha[:7]}..HEAD")
    return {
        "file": str(rel),
        "last_commit": sha[:7],
        "mechanism_commits_since": count,
        "pathspecs": pathspecs,
    }, []


def scan(
    root: Path,
    ts: Callable[[Path], int | None] | None = None,
    behind: Callable[[str], int | None] | None = None,
    today: date | None = None,
    run: Callable[..., str | None] | None = None,
) -> dict:
    if not root.is_dir() or not (root / "docs").is_dir():
        raise ScanError("REPO_UNREADABLE", str(root))
    ts = ts or git_last_commit_ts(root)
    behind = behind or git_commits_behind(root)
    today = today or date.today()
    run = run or _git

    md_files = find_md_files(root)
    adr_files = [f for f in md_files if f.parts[:2] == ("docs", "adr")]

    findings: list[dict] = []
    errors: list[dict] = []
    for part_findings, part_errors in (
        check_links(root, md_files),
        check_pair_drift(adr_pairs(root), ts),
        check_notes_refs(root, adr_files),
    ):
        findings.extend(part_findings)
        errors.extend(part_errors)
    codemaps, part_errors = codemaps_freshness(root, behind, today)
    errors.extend(part_errors)
    mechanism, part_errors = mechanism_freshness(root, run)
    errors.extend(part_errors)

    return {
        "findings": findings,
        "count": len(findings),
        "readings": {"codemaps": codemaps, "mechanism": mechanism},
        "errors": errors,
        "scanned_files": len(md_files),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repo root to scan (default: this script's repo)",
    )
    args = parser.parse_args(argv)
    try:
        result = scan(args.repo)
    except ScanError as exc:
        print(f"DOCSCAN_FAIL reason={exc.reason} {exc.detail}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
