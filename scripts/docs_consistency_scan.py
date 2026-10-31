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
- notes_ref    — an ADR or an RFC (`rfcs/`) referencing `.notes/` (gitignored:
                 broken in every clone; the CLAUDE.md docs-placement rule
                 forbids it — write 「非公開ノート/…」 for a private source)
- review_when_missing — an English ADR in force (Status `accepted` or
                 `partially-superseded-by`) with no `## Review-when` section;
                 one line, or "No expiry (reason)", satisfies it. Withdrawn /
                 superseded / proposed ADRs are exempt. A check on the ADR
                 corpus itself, not a new instrument (P1-03.4)
- threshold_table — a Threshold Registry row in docs/CONFIGURATION.md whose
                 value no longer matches the code constant it names
                 (THRESHOLD_SOURCES; a missing row is a finding too)
- egress_docs  — the public egress statements (README en/ja "What it will
                 not do", the llms-full.txt data-leaves FAQ) against the shell
                 egress inventory EGRESS in tests/test_shell_egress_allowlist.py
                 (P1-10.14), read by AST: each verb there must be named by its
                 destination or command (EGRESS_VERB_NEEDLES), the "no cloud"
                 sentences in CLAUDE.md / .zenodo.json keep their agent-loop
                 scope, and the refuted unscoped phrases stay out (P2-02.4).
                 Findings carry a ``reason`` code. tests/ pins the real repo at
                 zero, so a new verb is red in CI before it is a weekly finding
- data_placeholder — with ``--data-repo DIR``: an unfilled ``<OWNER-...>`` or
                 ``<date>`` placeholder in a hand-kept governance file (the
                 takedown contact must not ship as a placeholder)
- data_stale_claim / data_graph_drift — with ``--data-repo DIR`` (a checkout
                 of the public data repo, RFC P3-05.1): the hand-kept
                 governance files (DATACARD.md, NOTICE, CITATION.cff,
                 .zenodo.json, llms.txt, README*.md, graph.jsonld) are
                 grepped for claims the data no longer supports (768-dim
                 embeddings, importance scores, "seven" views, Qwen,
                 rules-distill, ``n<1K``), for the licence-prose words
                 ``no restriction|一切の制限|unrestricted`` (P0-03.14) and for a
                 capitalised ``Shimo4228/`` Hugging Face id; a line that
                 says "retired" is a retirement note and passes. The
                 graph's ``RetrievalView`` node count must equal
                 ``len(views/*.md)``. Optional: absent flag = no check.
- rfc_reconcile — a triage 照合 section in rfcs/*.md, dated on/after the
                 cutover, without a `(by: judge|owner)` heading marker or a
                 `verdict:` line from the closed vocabulary (the form is fixed
                 in rfcs/README.md; the contract in docs/CYCLES.md)

Readings (never findings — ages carry no threshold; the gate reads them):
- freshness    — generated-date age and commits-behind of the block-form
                 FRESHNESS header in docs/CYCLES.md, and only that file: the
                 reading is scoped by path, not a sweep. docs/diagrams/README.md
                 carries the same header dialect and is deliberately out of
                 scope (its refresh rule is the 鮮度規約 human gate, not this
                 scan). File-level codemaps were retired by ADR-0102 —
                 structure is derived from code via LSP / grimp, not stored

Abstain is surfaced twice (P1-05.5): ``abstain_count`` in this JSON feeds the
``docs-consistency`` row of reports/PIPELINE-STATUS.md (``pipeline_watchdog.sh``),
and /weekly-gate Step 5b states "check X abstained" for any non-empty ``errors``
even when findings is 0. An ADR timestamp the bulk ``git log`` walk misses falls
back to one per-file ``git log -1`` before it counts as GIT_FAIL.

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
import ast
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
_SKIP_PREFIXES = ("http://", "https://", "mailto:", "#")

# Root-level docs scanned in addition to docs/**; AGENTS.md is a symlink to
# CLAUDE.md and symlinks are skipped wholesale. An explicit allowlist, not a
# glob: root scratch files must not enter the scan. CHANGELOG.md is excluded
# BY DECISION — release notes are a historical record of the release-time
# tree, and their links are not repair targets.
_ROOT_DOCS = ("CLAUDE.md", "README.md", "README.ja.md")

# Data-repo governance files kept by hand (everything else in that repo is an
# rsync --delete mirror and is judged by the data itself, not by prose).
_DATA_GOVERNANCE_FILES = (
    "DATACARD.md",
    "NOTICE",
    "CITATION.cff",
    ".zenodo.json",
    "llms.txt",
    "README.md",
    "README.ja.md",
    "graph.jsonld",
)
_DATA_STALE_RE = re.compile(
    r"768-dim|importance scores|\bseven\b|Qwen|rules-distill|n<1K"
    r"|no restriction|一切の制限|unrestricted|Shimo4228/"
)
# A line (or graph node) that says the thing is gone is a retirement note, not
# a stale claim: "retired", "withdrawn", or "dropped at export" for embeddings.
_RETIRED_LINE_RE = re.compile(
    r"retired|退役|withdrawn|drops?\b|dropped|embedding-free|without embeddings|除去|落と",
    re.IGNORECASE,
)


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


def _parse_name_only_walk(out: str) -> dict[str, int]:
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


def _single_last_commit(root: Path, rel: Path) -> int | None:
    out = _git(root, "log", "-1", "--format=%ct", "--", str(rel))
    try:
        return int(out) if out else None
    except ValueError:
        return None


def git_last_commit_ts(root: Path) -> Callable[[Path], int | None]:
    """Committer timestamp of each file's last commit (the enja_drift basis).

    One `git log --name-only` walk over docs/adr serves every pair — the
    per-file `git log -1` form costs ~190 subprocesses (~6s), which the shell
    test would pay on every pytest run. The walk is newest-first, so the
    first-seen timestamp per path is its last commit.

    A path the walk did not list (the 2026-09 to 2026-10 production runs: the
    walk succeeded yet missed ``0103-retire-the-wiki-mechanism.md`` four weeks
    running, cause not reproducible from a shallow clone) falls back to one
    ``git log -1`` for that file, itself cached — success or failure — so a
    degraded git still costs one subprocess per MISSING path, never a retry
    storm. A walk that failed outright gets no fallback (P1-05.5).
    """
    cache: dict[str, int] | None = None
    per_file: dict[str, int | None] = {}
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
        return _parse_name_only_walk(out)

    def _ts(rel: Path) -> int | None:
        nonlocal cache, loaded
        if not loaded:
            cache = _load()
            loaded = True
        if cache is None:
            return None
        hit = cache.get(str(rel))
        if hit is not None:
            return hit
        key = str(rel)
        if key not in per_file:
            per_file[key] = _single_last_commit(root, rel)
        return per_file[key]

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
    """Flag ADR / RFC text referencing the gitignored `.notes/` dir."""
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


_REVIEW_WHEN_RE = re.compile(r"^## Review-when\b", re.MULTILINE)
# Status leads that put an ADR out of force: nothing left to expire.
_REVIEW_WHEN_EXEMPT = ("superseded", "withdrawn", "proposed", "rejected")


def _status_lead(text: str) -> str | None:
    """First word of the ADR's Status block, lowercased; None when absent."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == "## Status":
            for nxt in lines[i + 1 :]:
                if nxt.strip():
                    stripped = nxt.strip().lstrip("*_ ").lower()
                    return re.split(r"[\s(—-]", stripped, maxsplit=1)[0] if stripped else None
            return None
    return None


def check_review_when(root: Path, rel_files: Iterable[Path]) -> tuple[list[dict], list[dict]]:
    """Flag in-force English ADRs that state no expiry condition."""
    findings: list[dict] = []
    errors: list[dict] = []
    for rel in rel_files:
        if rel.name.endswith(".ja.md") or not re.match(r"\d{4}-", rel.name):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(
                {
                    "check": "review_when_missing",
                    "reason": "FILE_UNREADABLE",
                    "detail": f"{rel}: {exc}",
                }
            )
            continue
        lead = _status_lead(text)
        if lead is None or lead.startswith(_REVIEW_WHEN_EXEMPT):
            continue
        if not _REVIEW_WHEN_RE.search(text):
            findings.append(
                {
                    "check": "review_when_missing",
                    "file": str(rel),
                    "line": None,
                    "detail": "in-force ADR has no `## Review-when` (one line, or 'No expiry (reason)')",
                }
            )
    return findings, errors


def parse_freshness(text: str) -> dict | None:
    """Extract the effective date / source-commit from a block-form FRESHNESS
    header (the CYCLES.md dialect). Returns None when the file carries none."""
    match = _FRESHNESS_RE.search(text)
    if match is None:
        return None
    fields: dict[str, str] = {}
    for line in match.group("body").splitlines():
        key, _, value = line.strip().partition(":")
        if value:
            fields[key.strip()] = value.strip()
    return {
        "generated": fields.get("generated"),
        "source_commit": fields.get("source-commit"),
    }


def freshness_readings(
    root: Path, behind: Callable[[str], int | None], today: date
) -> tuple[list[dict], list[dict]]:
    """Age reading for docs/CYCLES.md. A reading only, no threshold.

    Scope is one file by choice, not because it is the only stamped doc —
    docs/diagrams/README.md carries the same header dialect and is left to the
    鮮度規約 human gate. Hence straight-line rather than a loop over a
    one-element list: a loop whose body can only run once reads as a sweep, and
    the `continue`s that shaped it hid that the "nothing stale" answer and the
    "the file is gone" answer are the same empty list unless the absence is
    reported — which is why it is.
    """
    errors: list[dict] = []
    path = root / "docs" / "CYCLES.md"
    # Its absence must surface, not read as "nothing stale": a layout move
    # would otherwise leave the sole reading permanently empty (the deleted
    # mechanism reading guarded the same shape).
    if not path.is_file():
        rel = path.relative_to(root)
        return [], [
            {
                "check": "freshness",
                "reason": "FILE_MISSING",
                "detail": f"{rel}: sole FRESHNESS target absent",
            }
        ]
    rel = path.relative_to(root)
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], [{"check": "freshness", "reason": "FILE_UNREADABLE", "detail": f"{rel}: {exc}"}]

    parsed = parse_freshness(text)
    if parsed is None:
        return [], errors

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
                    "check": "freshness",
                    "reason": "GIT_FAIL",
                    "detail": f"rev-list failed for {rel} ({sha})",
                }
            )

    reading = {
        "file": str(rel),
        "generated": generated,
        "source_commit": sha,
        "commits_behind": commits_behind,
        "days_old": days_old,
    }
    return [reading], errors


# Threshold Registry rows (docs/CONFIGURATION.md) that the scan compares with the
# code: table name -> (source file, regex whose group 1 is the value). One check,
# no second registry — a row not listed here is documentation only (P1-04.8).
THRESHOLD_SOURCES: dict[str, tuple[str, str]] = {
    "SIM_DUPLICATE": (
        "src/contemplative_agent/core/thresholds.py",
        r"^SIM_DUPLICATE:\s*float\s*=\s*([\d.]+)",
    ),
    "SIM_UPDATE": (
        "src/contemplative_agent/core/thresholds.py",
        r"^SIM_UPDATE:\s*float\s*=\s*([\d.]+)",
    ),
    "DEDUP_IMPORTANCE_FLOOR": (
        "src/contemplative_agent/core/thresholds.py",
        r"^DEDUP_IMPORTANCE_FLOOR:\s*float\s*=\s*([\d.]+)",
    ),
    "CLUSTER_THRESHOLD_INSIGHT": (
        "src/contemplative_agent/core/thresholds.py",
        r"^CLUSTER_THRESHOLD_INSIGHT:\s*float\s*=\s*([\d.]+)",
    ),
    "MAX_BATCH": ("src/contemplative_agent/core/thresholds.py", r"^MAX_BATCH:\s*int\s*=\s*(\d+)"),
    "NEVER_SELECTED_EXPOSURE_FLOOR": (
        "src/contemplative_agent/core/never_selected_metrics.py",
        r"^NEVER_SELECTED_EXPOSURE_FLOOR\s*=\s*(\d+)",
    ),
    "NEVER_SELECTED_DORMANT_WINDOW_DAYS": (
        "src/contemplative_agent/core/never_selected_metrics.py",
        r"^NEVER_SELECTED_DORMANT_WINDOW_DAYS\s*=\s*(\d+)",
    ),
    "relevance_score4": ("config/domain.json", r'"relevance_score4":\s*([\d.]+)'),
    "identity-interval-days": (
        "scripts/value_layer_due_check.py",
        r'"--identity-interval-days",\s*type=int,\s*default=(\d+)',
    ),
    "amendment-interval-days": (
        "scripts/value_layer_due_check.py",
        r'"--amendment-interval-days",\s*type=int,\s*default=(\d+)',
    ),
    "Z_THRESHOLD": ("scripts/_census_series.py", r"^Z_THRESHOLD\s*=\s*([\d.]+)"),
    "_SOFT_INVALID_WARN_RATIO": (
        "scripts/state_invariant_check.py",
        r"^_SOFT_INVALID_WARN_RATIO\s*=\s*([\d.]+)",
    ),
    "MIN_REPORT_BYTES": ("scripts/pipeline_watchdog.sh", r"^MIN_REPORT_BYTES=(\d+)"),
}
_THRESHOLD_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*([\d.]+)\s*\|")


def check_threshold_table(root: Path) -> tuple[list[dict], list[dict]]:
    """Table value vs code value for every row THRESHOLD_SOURCES knows."""
    doc = root / "docs" / "CONFIGURATION.md"
    if not doc.is_file():
        return [], []  # not this repo (or the registry is gone): nothing to compare
    try:
        lines = doc.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [], [
            {
                "check": "threshold_table",
                "reason": "FILE_UNREADABLE",
                "detail": f"{doc.name}: {exc}",
            }
        ]
    rows = {m.group(1): m.group(2) for m in map(_THRESHOLD_ROW.match, lines) if m}
    findings: list[dict] = []
    errors: list[dict] = []
    for name, (rel, pattern) in THRESHOLD_SOURCES.items():
        if name not in rows:
            findings.append(
                {
                    "check": "threshold_table",
                    "file": "docs/CONFIGURATION.md",
                    "line": None,
                    "detail": f"{name}: no row in the Threshold Registry",
                }
            )
            continue
        try:
            code = re.search(pattern, (root / rel).read_text(encoding="utf-8"), re.MULTILINE)
        except OSError as exc:
            errors.append(
                {"check": "threshold_table", "reason": "FILE_UNREADABLE", "detail": f"{rel}: {exc}"}
            )
            continue
        if code is None:
            findings.append(
                {
                    "check": "threshold_table",
                    "file": rel,
                    "line": None,
                    "detail": f"{name}: value not found in {rel} (pattern drifted)",
                }
            )
        elif float(code.group(1)) != float(rows[name]):
            findings.append(
                {
                    "check": "threshold_table",
                    "file": "docs/CONFIGURATION.md",
                    "line": None,
                    "detail": f"{name}: table says {rows[name]}, {rel} says {code.group(1)}",
                }
            )
    return findings, errors


# --- egress_docs (P2-02.4) ---------------------------------------------------
# The shell egress inventory (P1-10.14) is read from the test that pins it,
# never copied here: each verb its EGRESS table lists must be named in every
# public egress statement, by the destination or command a reader has to see.
# A verb added to the inventory with no row below is itself a finding, and so
# is a row whose verb the inventory no longer has.
EGRESS_INVENTORY = "tests/test_shell_egress_allowlist.py"
# The inventory's name for the weekly session's verb, assembled so this line is
# not read as a CLI spawn by test_cloud_egress_absence.py's text-level guard
# (this module only compares strings; it starts no process).
_CLAUDE_PRINT_VERB = "claude " + "-p"
EGRESS_VERB_NEEDLES: dict[str, str] = {
    "git fetch": "GitHub",  # sync-research-data.sh: the lease check before the push
    "git push": "GitHub",  # sync-research-data.sh, backup-runtime.sh
    "gh repo view": "gh repo view",  # backup-runtime.sh: the visibility check
    "hf upload": "Hugging Face",  # sync-research-data.sh: the patterns projection
    "git clone": "restore-drill-check.sh",  # the restore drill, run by hand
    _CLAUDE_PRINT_VERB: "`claude`",  # weekly-pipeline.sh: the weekly report session
    "curl": "localhost",  # ollama-restart.plist: the keep-alive probe of local Ollama
}
# The agent loop's own row. Its Python side is pinned by test_cloud_egress_absence.py.
EGRESS_LOOP_NEEDLES = ("moltbook.com", "localhost")
# (file, the heading that opens the statement); a statement runs to the next
# `## ` heading or `---` rule.
EGRESS_STATEMENTS = (
    ("README.md", "## What it will not do"),
    ("README.ja.md", "## しないこと"),
    ("llms-full.txt", "## What data leaves my machine when running the agent?"),
)
# The one-sentence "no cloud" claims, each scoped to the agent loop.
EGRESS_SCOPE_PHRASES = (
    ("CLAUDE.md", "エージェント自身のループに cloud 推論は無い"),
    (".zenodo.json", "in the agent's own loop"),
)
# Unscoped claims the inventory refutes: sync-data pushes to GitHub and Hugging
# Face, and the weekly session reaches Anthropic. CHANGELOG.md is history and
# is not read.
_EGRESS_OVERCLAIM_RE = re.compile(
    r"anywhere in the pipeline|the only network call|only adapter-specific traffic"
    r"|no cloud sync|no data sent to Anthropic",
    re.IGNORECASE,
)
_EGRESS_OVERCLAIM_FILES = (
    "README.md",
    "README.ja.md",
    "CLAUDE.md",
    "llms.txt",
    "llms-full.txt",
    ".zenodo.json",
)


def read_egress_inventory(path: Path) -> dict[str, set[str]]:
    """The EGRESS literal of the allowlist test, by AST (the test is not imported)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "EGRESS" and node.value is not None:
            table = ast.literal_eval(node.value)
            if isinstance(table, dict) and all(isinstance(v, set) for v in table.values()):
                return table
            raise ValueError("EGRESS is not a {path: set} literal")
    raise ValueError("no EGRESS assignment")


def _section(lines: list[str], heading: str) -> tuple[int, str] | None:
    """(1-based heading line, text up to the next `## ` or `---`), or None."""
    for i, line in enumerate(lines):
        if line.strip() == heading:
            body = []
            for rest in lines[i + 1 :]:
                if rest.startswith("## ") or rest.strip() == "---":
                    break
                body.append(rest)
            return i + 1, "\n".join(body)
    return None


def _egress_finding(
    file: str, line: int | None, reason: str, detail: str, verb: str | None = None
) -> dict:
    finding = {
        "check": "egress_docs",
        "file": file,
        "line": line,
        "reason": reason,
        "detail": detail,
    }
    if verb is not None:
        finding["verb"] = verb
    return finding


def check_egress_docs(root: Path) -> tuple[list[dict], list[dict]]:  # noqa: C901
    """Public egress statements vs the shell egress inventory (P2-02.4).

    Reasons: VERB_UNMAPPED / NEEDLE_STALE (the needle table and the inventory
    disagree), SECTION_MISSING, NEEDLE_MISSING (a statement does not name a
    verb's destination or command), SCOPE_MISSING (a "no cloud" sentence lost
    its agent-loop scope), OVERCLAIM (a refuted unscoped phrase is back).
    """
    inventory_path = root / EGRESS_INVENTORY
    if not inventory_path.is_file():
        return [], []  # not this repo: nothing to compare
    try:
        inventory = read_egress_inventory(inventory_path)
    except (OSError, SyntaxError, ValueError) as exc:
        return [], [{"check": "egress_docs", "reason": "INVENTORY_UNREADABLE", "detail": f"{exc}"}]
    findings: list[dict] = []
    errors: list[dict] = []
    verbs: dict[str, str] = {}
    for path, path_verbs in sorted(inventory.items()):
        for verb in sorted(path_verbs):
            verbs.setdefault(verb, path)
    for verb, path in verbs.items():
        if verb not in EGRESS_VERB_NEEDLES:
            findings.append(
                _egress_finding(
                    EGRESS_INVENTORY,
                    None,
                    "VERB_UNMAPPED",
                    f"{verb} ({path}) has no row in EGRESS_VERB_NEEDLES",
                    verb=verb,
                )
            )
    for verb in EGRESS_VERB_NEEDLES:
        if verb not in verbs:
            findings.append(
                _egress_finding(
                    "scripts/docs_consistency_scan.py",
                    None,
                    "NEEDLE_STALE",
                    f"EGRESS_VERB_NEEDLES has {verb}, which the inventory no longer lists",
                    verb=verb,
                )
            )

    required = [(v, EGRESS_VERB_NEEDLES[v]) for v in verbs if v in EGRESS_VERB_NEEDLES]
    required += [("agent loop", needle) for needle in EGRESS_LOOP_NEEDLES]
    texts: dict[str, str] = {}
    wanted = {name for name, _ in EGRESS_STATEMENTS}
    wanted |= {name for name, _ in EGRESS_SCOPE_PHRASES}
    wanted |= set(_EGRESS_OVERCLAIM_FILES)
    for name in sorted(wanted):
        try:
            texts[name] = (root / name).read_text(encoding="utf-8")
        except FileNotFoundError:
            errors.append({"check": "egress_docs", "reason": "FILE_MISSING", "detail": name})
        except OSError as exc:
            errors.append(
                {"check": "egress_docs", "reason": "FILE_UNREADABLE", "detail": f"{name}: {exc}"}
            )

    for name, heading in EGRESS_STATEMENTS:
        if name not in texts:
            continue
        found = _section(texts[name].splitlines(), heading)
        if found is None:
            findings.append(
                _egress_finding(name, None, "SECTION_MISSING", f"no `{heading}` section")
            )
            continue
        line, body = found
        for verb, needle in required:
            if needle not in body:
                findings.append(
                    _egress_finding(
                        name,
                        line,
                        "NEEDLE_MISSING",
                        f"{verb}: the statement does not name {needle!r}",
                        verb=verb,
                    )
                )
    for name, phrase in EGRESS_SCOPE_PHRASES:
        if name in texts and phrase not in texts[name]:
            findings.append(
                _egress_finding(name, None, "SCOPE_MISSING", f"no {phrase!r} scope phrase")
            )
    for name in _EGRESS_OVERCLAIM_FILES:
        for lineno, text in enumerate(texts.get(name, "").splitlines(), 1):
            for m in _EGRESS_OVERCLAIM_RE.finditer(text):
                findings.append(
                    _egress_finding(name, lineno, "OVERCLAIM", f"unscoped claim {m.group(0)!r}")
                )
    return findings, errors


_DATA_PLACEHOLDER_RE = re.compile(r"<OWNER-[^>\n]*>|<date>")


def _grep_placeholders(label: str, text: str) -> list[dict]:
    """Unfilled owner placeholders (``<OWNER-...>``, ``<date>``) in a published file.

    The data repo's DATACARD / NOTICE are hand-kept (excluded from the sync), so a
    placeholder left in the drafts is committed by hand; the takedown contact is
    the one that matters. No retirement-note exemption applies here.
    """
    return [
        {
            "check": "data_placeholder",
            "file": label,
            "line": lineno,
            "detail": f"unfilled placeholder: {m.group(0)!r}",
        }
        for lineno, line in enumerate(text.splitlines(), start=1)
        for m in _DATA_PLACEHOLDER_RE.finditer(line)
    ]


def _grep_stale(label: str, text: str) -> list[dict]:
    """Findings for one text file, line by line; retirement notes pass."""
    out: list[dict] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _RETIRED_LINE_RE.search(line):
            continue
        for m in _DATA_STALE_RE.finditer(line):
            out.append(
                {
                    "check": "data_stale_claim",
                    "file": label,
                    "line": lineno,
                    "detail": f"stale or banned phrase: {m.group(0)!r}",
                }
            )
    return out


def _check_graph(data_repo: Path) -> tuple[list[dict], list[dict]]:
    """Per-node stale claims and the live RetrievalView count against views/."""
    graph = data_repo / "graph.jsonld"
    try:
        nodes = json.loads(graph.read_text(encoding="utf-8")).get("@graph", [])
    except FileNotFoundError:
        return [], [
            {"check": "data_stale_claim", "reason": "FILE_MISSING", "detail": "graph.jsonld"}
        ]
    except (OSError, ValueError) as exc:
        return [], [{"check": "data_graph_drift", "reason": "GRAPH_UNREADABLE", "detail": str(exc)}]
    findings: list[dict] = []
    live_views = 0
    for node in nodes:
        text = json.dumps(node, ensure_ascii=False)
        types = node.get("@type")
        if "RetrievalView" in (types if isinstance(types, list) else [types]) and not node.get(
            "retired"
        ):
            live_views += 1
        if node.get("retired") or _RETIRED_LINE_RE.search(text):
            continue
        for m in _DATA_STALE_RE.finditer(text):
            findings.append(
                {
                    "check": "data_stale_claim",
                    "file": "graph.jsonld",
                    "line": 0,
                    "detail": f"stale or banned phrase {m.group(0)!r} in node {node.get('@id')}",
                }
            )
    views = len(list((data_repo / "views").glob("*.md")))
    if live_views != views:
        findings.append(
            {
                "check": "data_graph_drift",
                "file": "graph.jsonld",
                "line": 0,
                "detail": f"{live_views} live RetrievalView nodes vs {views} views/*.md",
            }
        )
    return findings, []


def check_data_governance(data_repo: Path) -> tuple[list[dict], list[dict]]:
    """Stale-claim grep over the hand-kept data-repo files, plus the view count."""
    findings: list[dict] = []
    errors: list[dict] = []
    for name in _DATA_GOVERNANCE_FILES:
        if name == "graph.jsonld":
            continue  # judged per node: a line has no idea which node it is in
        try:
            text = (data_repo / name).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            errors.append({"check": "data_stale_claim", "reason": "FILE_MISSING", "detail": name})
            continue
        except OSError as exc:
            errors.append(
                {
                    "check": "data_stale_claim",
                    "reason": "FILE_UNREADABLE",
                    "detail": f"{name}: {exc}",
                }
            )
            continue
        findings.extend(_grep_stale(name, text))
        findings.extend(_grep_placeholders(name, text))
    graph_findings, graph_errors = _check_graph(data_repo)
    return findings + graph_findings, errors + graph_errors


# 照合 section form (rfcs/README.md). Sections dated before the cutover keep the
# old form and are not checked; the first triage tick after it is Wed 2026-11-04.
RECONCILE_FORM_FROM = "2026-11-01"
RECONCILE_VERDICTS = ("dead-band", "hold", "ready", "ask-owner", "stale")
_RECON_HEADING = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})\s+(.*)$")
_RECON_BY = re.compile(r"[(（]by:\s*(judge|owner)\s*[)）]")
_RECON_VERDICT = re.compile(r"^verdict:\s*(\S+)\s*$")


def _split_sections(lines: list[str]) -> list[tuple[int, str, list[str]]]:
    """(lineno, heading, body lines) for every `## ` section."""
    sections: list[tuple[int, str, list[str]]] = []
    for lineno, line in enumerate(lines, start=1):
        if line.startswith("## "):
            sections.append((lineno, line, []))
        elif sections:
            sections[-1][2].append(line)
    return sections


def _reconcile_problems(heading: str, body: list[str]) -> list[tuple[str, str]]:
    """(reason, detail) pairs for one section; empty when it is out of scope or clean."""
    m = _RECON_HEADING.match(heading)
    if not m or "照合" not in m.group(2) or m.group(1) < RECONCILE_FORM_FROM:
        return []
    problems: list[tuple[str, str]] = []
    if not _RECON_BY.search(m.group(2)):
        problems.append(("BY_MISSING", "heading lacks (by: judge|owner)"))
    verdicts = [v.group(1) for v in map(_RECON_VERDICT.match, body) if v]
    if not verdicts:
        problems.append(("VERDICT_MISSING", "section has no `verdict:` line"))
    elif verdicts[0] not in RECONCILE_VERDICTS:
        problems.append(
            (
                "VERDICT_UNKNOWN",
                f"verdict {verdicts[0]!r} not in {', '.join(RECONCILE_VERDICTS)}",
            )
        )
    return problems


def check_rfc_reconcile(root: Path) -> tuple[list[dict], list[dict]]:
    """Flag 照合 sections (dated on/after the cutover) that break the form."""
    findings: list[dict] = []
    errors: list[dict] = []
    rfcs = root / "rfcs"
    if not rfcs.is_dir():
        return findings, errors
    for path in sorted(rfcs.glob("[0-9]*.md")):
        rel = path.relative_to(root)
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            errors.append(
                {"check": "rfc_reconcile", "reason": "FILE_UNREADABLE", "detail": f"{rel}: {exc}"}
            )
            continue
        for lineno, heading, body in _split_sections(lines):
            for reason, detail in _reconcile_problems(heading, body):
                findings.append(
                    {
                        "check": "rfc_reconcile",
                        "file": str(rel),
                        "line": lineno,
                        "reason": reason,
                        "detail": detail,
                    }
                )
    return findings, errors


def scan(
    root: Path,
    ts: Callable[[Path], int | None] | None = None,
    behind: Callable[[str], int | None] | None = None,
    today: date | None = None,
    data_repo: Path | None = None,
) -> dict:
    if not root.is_dir() or not (root / "docs").is_dir():
        raise ScanError("REPO_UNREADABLE", str(root))
    ts = ts or git_last_commit_ts(root)
    behind = behind or git_commits_behind(root)
    today = today or date.today()

    md_files = find_md_files(root)
    adr_files = [f for f in md_files if f.parts[:2] == ("docs", "adr")]
    # RFCs are outside find_md_files (their links are not scanned), but their text
    # is public too, so the .notes/ rule covers them (P1-09.13).
    rfcs = root / "rfcs"
    rfc_files = [p.relative_to(root) for p in sorted(rfcs.glob("*.md"))] if rfcs.is_dir() else []

    findings: list[dict] = []
    errors: list[dict] = []
    for part_findings, part_errors in (
        check_links(root, md_files),
        check_pair_drift(adr_pairs(root), ts),
        check_notes_refs(root, [*adr_files, *rfc_files]),
        check_review_when(root, adr_files),
        check_threshold_table(root),
        check_egress_docs(root),
        check_rfc_reconcile(root),
    ):
        findings.extend(part_findings)
        errors.extend(part_errors)
    if data_repo is not None:
        part_findings, part_errors = check_data_governance(data_repo)
        findings.extend(part_findings)
        errors.extend(part_errors)
    freshness, part_errors = freshness_readings(root, behind, today)
    errors.extend(part_errors)

    return {
        "findings": findings,
        "count": len(findings),
        "readings": {"freshness": freshness},
        "errors": errors,
        # Counts for readers that do not parse the arrays (the watchdog is
        # pure bash, P1-05.5): a clean-looking findings list with
        # abstain_count > 0 is a scan that did not run a check.
        "readings_count": len(freshness),
        "abstain_count": len(errors),
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
    parser.add_argument(
        "--data-repo",
        type=Path,
        default=None,
        help="also check the hand-kept governance files of a public data-repo checkout",
    )
    args = parser.parse_args(argv)
    try:
        result = scan(args.repo, data_repo=args.data_repo)
    except ScanError as exc:
        print(f"DOCSCAN_FAIL reason={exc.reason} {exc.detail}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
