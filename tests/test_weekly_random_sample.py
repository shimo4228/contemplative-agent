"""Fault column for ``scripts/weekly_random_sample.py`` (RFC-0010 / ADR-0099).

The sampler is the instrument document's control channel: a uniform,
seed-replayable draw the LLM writer copies verbatim and cannot curate. Its
input is the comment-report Markdown that ``core/report.py`` emits — an
LLM-authored grammar — so the parsing boundaries are the fault surface:
the field vocabulary (Thinking must never leak into an excerpt) and the
entry separator (``---`` must never bleed into an Output excerpt).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "weekly_random_sample.py"

DAY = "2026-01-01"

ENTRY_FULL = """# Moltbook Activity Report — 2026-01-01

**Configuration**: domain=test

## Comments (2 total)

### 1. [2026-01-01 00:00:00] COMMENT · with alice · post aaa111 · relevance 1.00

**Context:**
counterparty context body

**Thinking:**
private reasoning trace that must never be sampled

**Output:**
agent output body

---

### 2. [2026-01-01 00:05:00] REPLY · with bob · post bbb222 · relevance —

**Context:**
second context

**Internal note:**
agent internal note

**Output:**
second output

---
"""


def _make_reports(tmp_path: Path, text: str = ENTRY_FULL) -> Path:
    report_dir = tmp_path / "comment-reports"
    report_dir.mkdir()
    (report_dir / f"comment-report-{DAY}.md").write_text(text, encoding="utf-8")
    return report_dir


def _run(report_dir: Path, k: str = "2") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--report-dir",
            str(report_dir),
            "--start",
            DAY,
            "--end",
            DAY,
            "--k",
            k,
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


class TestFieldBoundaries:
    def test_thinking_never_reaches_the_sample(self, tmp_path):
        """The reasoning trace is neither of the two rendered fields and must
        not bleed into a neighboring capture either."""
        out = _run(_make_reports(tmp_path)).stdout
        assert "private reasoning trace" not in out
        assert "counterparty context body" in out
        assert "agent output body" in out

    def test_entry_separator_does_not_bleed_into_the_output_excerpt(self, tmp_path):
        out = _run(_make_reports(tmp_path)).stdout
        for line in out.splitlines():
            if line.startswith("**Output (agent):**"):
                assert "---" not in line, line

    def test_internal_note_is_parsed_but_not_rendered(self, tmp_path):
        out = _run(_make_reports(tmp_path)).stdout
        assert "agent internal note" not in out
        assert "second context" in out


class TestDeterminism:
    def test_same_seed_reproduces_the_same_bytes(self, tmp_path):
        report_dir = _make_reports(tmp_path)
        first = _run(report_dir, k="1").stdout
        second = _run(report_dir, k="1").stdout
        assert first == second
        assert f"seed `weekly-sample-{DAY}`" in first

    def test_k_larger_than_corpus_degrades_to_the_corpus(self, tmp_path):
        out = _run(_make_reports(tmp_path), k="50").stdout
        assert "Uniform sample of 2 of 2 entries" in out


class TestDegradation:
    def test_empty_window_states_unavailability_instead_of_failing(self, tmp_path):
        report_dir = tmp_path / "comment-reports"
        report_dir.mkdir()
        result = _run(report_dir)
        assert result.returncode == 0, result.stderr
        assert "Sample unavailable" in result.stdout

    def test_excerpts_are_cut_at_the_fixed_caps(self, tmp_path):
        long_body = "word " * 400
        text = ENTRY_FULL.replace("agent output body", long_body.strip())
        out = _run(_make_reports(tmp_path, text)).stdout
        assert "[…truncated at 500 chars]" in out
