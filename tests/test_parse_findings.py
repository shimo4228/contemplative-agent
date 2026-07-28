"""Tests for scripts/parse_findings.py — the findings → fix-plan seam.

The weekly diagnosis writes F1 findings as prose with a fixed heading and a
``**Code reference**`` block (the machine-readable contract stated in
.claude/skills/weekly-report-diagnosis/SKILL.md). The unattended fix stage
consumes them, so extraction and scope classification are structural
properties and belong to code (when-code-when-llm). The security-relevant
property is the *scope* call: a finding whose references reach outside
src/ / scripts/ / tests/ touches behavior-shaping artifacts and must be
routed to the full-text human gate, never the auto-fix path — so every
ambiguous case must classify as "prompt".
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import parse_findings as pf  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "parse_findings.py"

SAMPLE = """\
# Weekly Diagnosis — 2026-07-24

**Source report**: weekly-2026-07-24.md

## F1. Structural (code / schema / pipeline diff)

### F1.1. The reply prompt asserts an empty slot is complete

**Source quote (E P2)**: *"an empty field here"*

**Code reference**:
- `src/contemplative_agent/adapters/moltbook/reply_handler.py:401` — call site
- `…/llm_functions.py:282` — wrapper call on the empty string
- `config/prompts/reply.md` — the template's fixed header

**Structural change**: make the post slot conditional.

**Validity self-check**: not in `.notes/TASKS.md`.

### F1.2. Sweep state is committed before the LLM call

**Code reference**:
- `scripts/weekly-analysis.sh:208-209` — sweep runs in the collection phase
- `scripts/log_anomaly_sweep.py:214-215` — `write_state(...)` unconditional

**Structural change**: pass `--no-update`, promote after the report lands.

---

## F2. Identity-level open questions

### F2.1. Is silence the correct reading of the amended clause?

Body of the open question.

## F3. Pure observations

### F3.1. The upstream report fabricated its headline finding

### F3.2. The real repetition is intra-day
"""


def test_extracts_f1_sections_with_ids_and_titles():
    findings = pf.parse_findings(SAMPLE)
    assert [f.id for f in findings] == ["F1.1", "F1.2"]
    assert findings[0].title == "The reply prompt asserts an empty slot is complete"
    assert "Structural change" in findings[0].body
    # Body boundaries: the next section's text must not leak in.
    assert "Sweep state" not in findings[0].body
    assert "Identity-level" not in findings[1].body


def test_paths_extracted_only_from_code_reference_block():
    findings = pf.parse_findings(SAMPLE)
    # `.notes/TASKS.md` appears in the self-check prose but NOT in the Code
    # reference block, so it must not pollute the path set (it would drag
    # every finding to prompt scope).
    assert ".notes/TASKS.md" not in findings[0].paths


def test_line_numbers_stripped_and_ellipsis_resolved():
    findings = pf.parse_findings(SAMPLE)
    assert "src/contemplative_agent/adapters/moltbook/reply_handler.py" in findings[0].paths
    # `…/llm_functions.py` inherits the previous reference's directory.
    assert "src/contemplative_agent/adapters/moltbook/llm_functions.py" in findings[0].paths
    assert all(":" not in p for p in findings[0].paths)


def test_scope_classification():
    findings = pf.parse_findings(SAMPLE)
    # F1.1 touches config/prompts/ → behavior-shaping → prompt scope even
    # though it also references src/ files (conservative on mixed).
    assert findings[0].scope == "prompt"
    # F1.2 is closed over scripts/ → code scope.
    assert findings[1].scope == "code"


def test_no_code_reference_block_classifies_as_prompt():
    text = "## F1. X\n\n### F1.1. No references at all\n\nprose only\n"
    findings = pf.parse_findings(text)
    assert findings[0].paths == ()
    # Cannot verify code-closure → route to the human full-text gate.
    assert findings[0].scope == "prompt"


def test_f2_f3_counts():
    counts = pf.section_counts(SAMPLE)
    assert counts == {"f1": 2, "f2": 1, "f3": 2}


def test_garbage_input_yields_empty_not_crash():
    # Fault column: the diagnosis is LLM output; a malformed or empty file
    # must degrade to zero findings, never an exception (the orchestrator
    # turns the empty set into a NO_F1_FINDINGS reason code).
    assert pf.parse_findings("") == []
    assert pf.parse_findings("random\ntext\n### not a finding\n") == []
    assert pf.section_counts("") == {"f1": 0, "f2": 0, "f3": 0}


def test_cli_emits_json(tmp_path: Path):
    src = tmp_path / "weekly-2026-07-24-findings.md"
    src.write_text(SAMPLE, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(src)],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    assert data["counts"] == {"f1": 2, "f2": 1, "f3": 2}
    assert data["f1"][1]["scope"] == "code"
    assert data["f1"][1]["id"] == "F1.2"


def test_cli_missing_file_exits_nonzero(tmp_path: Path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "absent.md")],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert result.stdout == ""


def test_single_line_code_reference_extracts_path():
    # The SKILL.md template's canonical single-line form — used by ~half the
    # historical findings; missing it silently disabled auto-fix for them
    # (2026-07-29 review, HIGH).
    text = (
        "## F1. X\n\n### F1.1. Single-line reference\n\n"
        "**Code reference**: `scripts/weekly-analysis.sh:146-162` (具体ファイル + 行)\n\n"
        "**Structural change**: fix it.\n"
    )
    findings = pf.parse_findings(text)
    assert findings[0].paths == ("scripts/weekly-analysis.sh",)
    assert findings[0].scope == "code"


def test_traversal_path_rejected_and_routed_to_prompt():
    # `src/../../etc/x.py` startswith("src/") — a string check alone would
    # classify it as code scope (2026-07-29 review, CRITICAL).
    text = (
        "## F1. X\n\n### F1.1. Traversal\n\n"
        "**Code reference**:\n"
        "- `src/../../../etc/cron.d/evil.py:1` — nope\n\n"
        "**Structural change**: n/a.\n"
    )
    findings = pf.parse_findings(text)
    assert findings[0].paths == ()
    assert findings[0].scope == "prompt"


def test_cli_unreadable_bytes_exit_nonzero_no_traceback(tmp_path: Path):
    bad = tmp_path / "weekly-x-findings.md"
    bad.write_bytes(b"\xff\xfe\x00 invalid utf-8 \x80")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(bad)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "unreadable" in result.stderr
