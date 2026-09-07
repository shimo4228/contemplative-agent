"""Fault column for the weekly pipeline's Sample splice (RFC-0026).

The `## Sample` section is the one part of the weekly observation document the
writer cannot curate (ADR-0099 Decision 1). It used to get there by
transcription, and on 2026-08-28 a sentence went missing in the copy; the
pipeline now splices the collector's section in before promotion and the
existing verbatim check became this splice's assertion.

The stage is exercised through `scripts/weekly_sample_splice.py` directly — the
pipeline around it starts a `claude` session and promotes real files, and none
of that is what these cases are about. The collector's half of the seam (the
sidecar this reads) is pinned in tests/test_weekly_analysis_shell.py.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPLICE = REPO_ROOT / "scripts" / "weekly_sample_splice.py"

# The exact line set weekly-pipeline.sh's verbatim check demands, as its own
# regex writes it.
VERBATIM_RE = re.compile(
    r"^### Sample [0-9]+/"
    r"|^\*\*(Context \(counterparty, untrusted\)|Output \(agent\)):\*\*"
)

SAMPLE_SECTION = (
    "## Random Sample (deterministic control channel)\n"
    "\n"
    "Uniform sample of 2 of 40 entries, seed `weekly-sample-2026-09-04`.\n"
    "\n"
    "### Sample 1/2 — 24. [2026-09-01 09:41:43] COMMENT · with someone\n"
    "\n"
    "**Context (counterparty, untrusted):** first counterparty line.\n"
    "\n"
    "**Output (agent):** first agent line.\n"
    "\n"
    "### Sample 2/2 — 39. [2026-09-02 15:59:08] COMMENT · with another\n"
    "\n"
    "**Output (agent):** second agent line.\n"
)

REPORT_HEAD = "# Weekly Observation\n\n## Exceptions\n\nExceptions: 0.\n\n"
REPORT_TAIL = "## Discarded\n\nnothing.\n"


def _sample(tmp_path: Path, section: str = SAMPLE_SECTION) -> Path:
    """The sidecar weekly-analysis.sh writes beside the materials: the section
    alone, without the materials' `<untrusted_content_{nonce}>` frame."""
    path = tmp_path / "materials-sample.md"
    path.write_text(section, encoding="utf-8")
    return path


def _report(tmp_path: Path, sample_section: str = "## Sample\n\n") -> Path:
    path = tmp_path / "weekly-2026-09-04.md"
    path.write_text(REPORT_HEAD + sample_section + REPORT_TAIL, encoding="utf-8")
    return path


def _splice(sample: Path, report: Path):
    cmd = [sys.executable, str(SPLICE), "--sample", str(sample), "--report", str(report)]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def _verbatim_missing(sample: Path, report: Path) -> list[str]:
    """weekly-pipeline.sh's check, restated: every sample line the collector
    emitted must appear as a whole line in the promoted report."""
    report_lines = set(report.read_text(encoding="utf-8").split("\n"))
    return [
        line
        for line in sample.read_text(encoding="utf-8").split("\n")
        if VERBATIM_RE.search(line) and line not in report_lines
    ]


class TestSplice:
    def test_the_section_lands_under_the_heading_line_for_line(self, tmp_path):
        sample = _sample(tmp_path)
        report = _report(tmp_path)

        result = _splice(sample, report)

        assert result.returncode == 0, result.stderr
        text = report.read_text(encoding="utf-8")
        # Line for line, not "contains": a transfer that drops or reorders one
        # line is the failure this whole stage exists to remove.
        spliced = text[text.index("## Sample") + len("## Sample") : text.index("## Discarded")]
        assert spliced.strip("\n") == SAMPLE_SECTION.strip("\n")
        assert _verbatim_missing(sample, report) == []
        assert text.startswith(REPORT_HEAD)
        assert text.endswith(REPORT_TAIL)

    def test_sampler_failed_week_splices_the_single_line(self, tmp_path):
        unavailable = (
            "## Random Sample (deterministic control channel)\n"
            "\n"
            "Sample unavailable (reason=sampler-failed).\n"
        )
        sample = _sample(tmp_path, section=unavailable)
        report = _report(tmp_path)

        result = _splice(sample, report)

        assert result.returncode == 0, result.stderr
        text = report.read_text(encoding="utf-8")
        assert "Sample unavailable (reason=sampler-failed)" in text
        assert "### Sample" not in text
        assert _verbatim_missing(sample, report) == []

    def test_missing_heading_refuses_and_leaves_the_report_alone(self, tmp_path):
        sample = _sample(tmp_path)
        report = _report(tmp_path, sample_section="")
        before = report.read_bytes()

        result = _splice(sample, report)

        assert result.returncode == 3
        assert result.stdout.strip() == "SAMPLE_HEADING_MISSING"
        assert report.read_bytes() == before

    def test_duplicate_heading_refuses(self, tmp_path):
        sample = _sample(tmp_path)
        report = _report(tmp_path, sample_section="## Sample\n\n## Sample\n\n")
        before = report.read_bytes()

        result = _splice(sample, report)

        assert result.returncode == 3
        assert result.stdout.strip() == "SAMPLE_HEADING_DUPLICATE"
        assert report.read_bytes() == before

    def test_writer_body_is_refused_and_kept(self, tmp_path):
        """Not overwritten: what the writer wrote is the evidence of what went
        wrong that week, and the gate reads the document."""
        sample = _sample(tmp_path)
        report = _report(tmp_path, sample_section="## Sample\n\nI summarized the sample.\n\n")
        before = report.read_bytes()

        result = _splice(sample, report)

        assert result.returncode == 3
        assert result.stdout.strip() == "SAMPLE_WRITER_BODY"
        assert report.read_bytes() == before

    def test_second_splice_refuses_rather_than_doubling(self, tmp_path):
        sample = _sample(tmp_path)
        report = _report(tmp_path)

        assert _splice(sample, report).returncode == 0
        spliced = report.read_bytes()
        repeat = _splice(sample, report)

        assert repeat.returncode == 3
        assert repeat.stdout.strip() == "SAMPLE_ALREADY_SPLICED"
        assert report.read_bytes() == spliced

    def test_absent_sidecar_refuses_before_touching_the_report(self, tmp_path):
        report = _report(tmp_path)
        before = report.read_bytes()

        result = _splice(tmp_path / "nothing-here.md", report)

        assert result.returncode == 3
        assert result.stdout.strip() == "SAMPLE_SOURCE_MISSING"
        assert report.read_bytes() == before

    def test_empty_sidecar_refuses(self, tmp_path):
        """A zero-byte sidecar is a collector failure, not an empty sample —
        splicing it would leave a heading with nothing under it and no reason
        code saying why."""
        sample = _sample(tmp_path, section="\n\n")
        report = _report(tmp_path)
        before = report.read_bytes()

        result = _splice(sample, report)

        assert result.returncode == 3
        assert result.stdout.strip() == "SAMPLE_SOURCE_MISSING"
        assert report.read_bytes() == before

    def test_sample_as_the_last_section_still_gets_the_body(self, tmp_path):
        """No `## ` heading follows, so the region runs to EOF."""
        path = tmp_path / "weekly-tail.md"
        path.write_text(REPORT_HEAD + "## Sample\n", encoding="utf-8")

        result = _splice(_sample(tmp_path), path)

        assert result.returncode == 0, result.stderr
        text = path.read_text(encoding="utf-8")
        assert text.startswith(REPORT_HEAD + "## Sample\n")
        assert "**Output (agent):** second agent line." in text
