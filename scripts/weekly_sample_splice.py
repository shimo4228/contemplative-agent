#!/usr/bin/env python3
"""Splice the collector's Random Sample section into the weekly report.

The `## Sample` section is the one part of the weekly observation document
whose selection function is code rather than the writer (ADR-0099 Decision 1,
RFC-0010). The writer emits the `## Sample` heading and nothing under it; this
script copies the section into that slot before the report is promoted, so the
section is a deterministic transfer instead of a transcription the writer could
trim, reorder or annotate.

The body comes from the sidecar `weekly-analysis.sh` writes beside the
materials, not from the materials themselves: inside the materials the section
sits in an `<untrusted_content_{nonce}>` frame and the previous weeks' reports
embedded further down carry copies of their own, so recovering it there means a
frame-and-heading parser whose every defect lands in the promoted document.
The collector already holds the exact bytes.

Exit codes: 0 = spliced; 3 = refused, with a single reason code on stdout (the
report is left byte-identical); 2 = usage error.

    python3 scripts/weekly_sample_splice.py --sample S --report R

Reason codes:
    SAMPLE_SOURCE_MISSING    no sample sidecar, or it is empty
    SAMPLE_HEADING_MISSING   the report has no `## Sample` heading
    SAMPLE_HEADING_DUPLICATE the report has more than one
    SAMPLE_WRITER_BODY       the writer already wrote under the heading
    SAMPLE_ALREADY_SPLICED   a sample is in the slot already (not spliced twice)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

SOURCE_HEADING = "## Random Sample (deterministic control channel)"
TARGET_HEADING = "## Sample"
REFUSED = 3


def _is_section_heading(line: str) -> bool:
    return line.startswith("## ")


def splice(report: list[str], sample: list[str]) -> list[str] | str:
    """Insert ``sample`` under the report's `## Sample` heading, or return a
    reason code and leave the caller to write nothing."""
    slots = [i for i, line in enumerate(report) if line.rstrip() == TARGET_HEADING]
    if not slots:
        return "SAMPLE_HEADING_MISSING"
    if len(slots) > 1:
        return "SAMPLE_HEADING_DUPLICATE"
    head = slots[0]
    tail = len(report)
    for i in range(head + 1, len(report)):
        # A spliced body opens with SOURCE_HEADING, which is itself a `## `
        # heading: ending the region there would read an already-spliced
        # report as empty and splice a second copy in.
        if _is_section_heading(report[i]) and report[i].rstrip() != SOURCE_HEADING:
            tail = i
            break
    written = [line for line in report[head + 1 : tail] if line.strip()]
    if written:
        if written[0].rstrip() == SOURCE_HEADING:
            return "SAMPLE_ALREADY_SPLICED"
        return "SAMPLE_WRITER_BODY"
    return [*report[: head + 1], "", *sample, "", *report[tail:]]


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n")


def _write_lines(path: Path, lines: list[str]) -> None:
    """Write through a temp file in the same directory: a run killed mid-write
    must not leave a half-spliced report where the promote step reads one. The
    `.md` suffix is kept so the pipeline's pre-run cleanup glob sweeps a
    leftover away."""
    tmp = path.with_name(f"{path.stem}.splice.{os.getpid()}{path.suffix}")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Splice the Sample section.")
    parser.add_argument("--sample", required=True, help="collector's sample sidecar")
    parser.add_argument("--report", required=True, help="report to splice in place")
    args = parser.parse_args()

    sample_path = Path(args.sample)
    if not sample_path.is_file():
        print("SAMPLE_SOURCE_MISSING")
        return REFUSED
    sample = _read_lines(sample_path)
    while sample and not sample[-1].strip():
        sample.pop()
    if not sample:
        print("SAMPLE_SOURCE_MISSING")
        return REFUSED

    report_path = Path(args.report)
    result = splice(_read_lines(report_path), sample)
    if isinstance(result, str):
        print(result)
        return REFUSED
    _write_lines(report_path, result)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as exc:  # unreadable sidecar / unwritable report
        print(f"splice failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
