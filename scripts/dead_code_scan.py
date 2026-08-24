#!/usr/bin/env python3
"""Weekly dead-code intake — the fifth deterministic intake (T-DEADCODE-INTAKE).

Runs vulture over the repo and emits a JSON candidate list on stdout for the
Saturday gate. Detection and deletion are separated by construction: this
scan is read-only, its per-week JSON is read directly by /weekly-gate —
deliberately bypassing the unattended LLM session, so it can never author a
deletion — and deletion happens only as a human commit at the gate.

Scan-wide, report-narrow: vulture's scan paths (pyproject [tool.vulture])
include tests/ and evals/ so that code used only by tests resolves as used,
but candidates are reported for src/ and scripts/ only. Vulture's policy
(paths, whitelist) lives in pyproject so `uv run vulture` and this intake
agree by construction; false-positive exemptions live in
.vulture_whitelist.py and change only via the Saturday gate.

Faults abstain with a reason code on stderr and a nonzero exit — a format
drift or a missing binary must never read as "no dead code this week"
(ADR-0077; the pipeline turns the nonzero exit into DEADCODE_SCAN_FAIL).

Must run from the repo root (vulture resolves pyproject config and emits
paths relative to the cwd).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence

from _scan import ScanError

# vulture's stable pyflakes-shaped output line (verified against 2.16):
#   src/foo.py:12: unused function 'bar' (60% confidence)
_LINE_RE = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+): (?P<message>.+?) \((?P<confidence>\d+)% confidence\)$"
)

# 0 = nothing dead, 3 = dead code found (vulture 2.16, verified 2026-08-07).
_OK_RETURNCODES = (0, 3)

# Candidates are reported for production code only; tests/ and evals/ are
# scanned for reference resolution, not reported (test hygiene is a
# different instrument's job).
_REPORT_PREFIXES = ("src/", "scripts/")


# Internal bound so the standalone CLI cannot hang forever; the pipeline
# wraps the call in its own with_timeout as well.
_VULTURE_TIMEOUT_SECONDS = 240


def run_vulture(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    # Explicit utf-8: under launchd LANG is often unset and text=True would
    # decode with the (ASCII) locale encoding — a UnicodeDecodeError there
    # would escape the reason-code contract (2026-08-07 python review).
    return subprocess.run(
        list(cmd),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=_VULTURE_TIMEOUT_SECONDS,
    )


def _normalize_path(path: str) -> str:
    """Normalize a vulture-emitted path for the prefix filter.

    A `./src/...` or backslash-separated shape must not silently zero the
    report — the filter does 100% of the narrowing work, so its input shape
    is load-bearing (2026-08-07 reviews)."""
    normalized = path.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def parse_output(stdout: str) -> tuple[list[dict], int]:
    """Parse vulture stdout into candidate dicts + a count of alien lines."""
    candidates: list[dict] = []
    unparsed = 0
    for line in stdout.splitlines():
        if not line.strip():
            continue
        match = _LINE_RE.match(line)
        if match is None:
            unparsed += 1
            continue
        candidates.append(
            {
                "file": _normalize_path(match["path"]),
                "line": int(match["line"]),
                "message": match["message"],
                "confidence": int(match["confidence"]),
            }
        )
    return candidates, unparsed


def scan(
    runner: Callable[[Sequence[str]], subprocess.CompletedProcess] | None = None,
    cmd: Sequence[str] = ("vulture",),
) -> dict:
    # Module-level lookup at call time so tests can monkeypatch run_vulture.
    if runner is None:
        runner = run_vulture
    try:
        proc = runner(cmd)
    except FileNotFoundError as exc:
        raise ScanError("TOOL_MISSING", str(exc)) from exc
    except subprocess.TimeoutExpired as exc:
        raise ScanError("TOOL_TIMEOUT", str(exc)) from exc
    except OSError as exc:  # non-executable / directory / permission — same contract
        raise ScanError("TOOL_FAILED", str(exc)) from exc
    if proc.returncode not in _OK_RETURNCODES:
        raise ScanError(
            "TOOL_FAILED",
            f"exit={proc.returncode} stderr={proc.stderr.strip()[-500:]}",
        )
    parsed, unparsed = parse_output(proc.stdout)
    if unparsed and not parsed:
        raise ScanError("UNPARSEABLE_OUTPUT", f"{unparsed} unrecognized lines")
    # vulture reports an input file it could not parse (syntax error, bad
    # encoding) on stderr while still exiting 3 — a coverage gap, not a
    # candidate. Carried as a count so the packet can degrade loudly
    # (2026-08-07 python review HIGH: the third door into a silent zero).
    stderr_lines = len([ln for ln in proc.stderr.splitlines() if ln.strip()])
    reported = [c for c in parsed if any(c["file"].startswith(p) for p in _REPORT_PREFIXES)]
    return {
        "tool": "vulture",
        "report_prefixes": list(_REPORT_PREFIXES),
        "count": len(reported),
        "candidates": reported,
        "parsed_total": len(parsed),
        "unparsed_lines": unparsed,
        "stderr_lines": stderr_lines,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--vulture-bin",
        default="vulture",
        help="vulture executable (resolved from the active venv PATH)",
    )
    args = parser.parse_args(argv)
    try:
        result = scan(cmd=(args.vulture_bin,))
    except ScanError as exc:
        print(f"DEADCODE_SCAN_FAIL reason={exc.reason} {exc.detail}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
