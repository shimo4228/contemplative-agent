"""Tests for scripts/dead_code_scan.py — the weekly dead-code intake.

The fifth deterministic intake (T-DEADCODE-INTAKE) runs vulture over the repo
and emits a JSON candidate list for the Saturday decision packet. Detection
and deletion are separated by construction: this scan is read-only, its
output bypasses the diagnosis→fix LLM stages entirely, and deletion happens
only as a human commit at the Saturday gate.

Scan-wide, report-narrow: vulture parses src/scripts/tests/evals so that
code used only by tests resolves as used, but candidates are reported for
src/ and scripts/ only (test hygiene is out of scope for this instrument).

Fault column (chaos-TDD, ADR-0077 — the desired guard behavior is asserted
first; the seam is the injectable vulture runner):

- F-DC-1  vulture binary missing → abstain with reason=TOOL_MISSING
- F-DC-2  unexpected exit code (config error) → abstain with reason=TOOL_FAILED
- F-DC-3  output entirely unparseable (format drift) → abstain with
          reason=UNPARSEABLE_OUTPUT, never a silent zero-candidate success
- F-DC-4  mixed parseable/garbage lines → succeed, but the unparsed count is
          carried in the JSON (surfaced, not swallowed)
- F-DC-5  vulture hangs → reason=TOOL_TIMEOUT (internal subprocess timeout;
          the shell's with_timeout degrades to no-op without coreutils)
- F-DC-6  non-executable / permission fault → reason=TOOL_FAILED, not a
          traceback
- F-DC-7  vulture reports an unreadable input file on stderr while still
          exiting 3 → stderr_lines carried in the JSON (a coverage gap must
          not read as a clean scan)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# scripts/ is not a package; import the module by path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dead_code_scan as dcs  # noqa: E402  # pyright: ignore[reportMissingImports]

VULTURE_OUT = """\
src/contemplative_agent/core/foo.py:12: unused function 'orphan' (60% confidence)
scripts/old_tool.py:3: unused variable 'LEGACY_FLAG' (100% confidence)
tests/test_foo.py:9: unused function 'helper_never_called' (60% confidence)
evals/probe.py:5: unused method 'a_measure' (60% confidence)
"""


def _proc(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(
        args=["vulture"], returncode=returncode, stdout=stdout, stderr=stderr
    )


class TestParseOutput:
    def test_parses_file_line_message_confidence(self):
        candidates, unparsed = dcs.parse_output(VULTURE_OUT)
        assert unparsed == 0
        assert candidates[0] == {
            "file": "src/contemplative_agent/core/foo.py",
            "line": 12,
            "message": "unused function 'orphan'",
            "confidence": 60,
        }
        assert len(candidates) == 4

    def test_blank_lines_are_not_unparsed(self):
        candidates, unparsed = dcs.parse_output("\n\n")
        assert candidates == [] and unparsed == 0

    def test_garbage_lines_counted_as_unparsed(self):
        candidates, unparsed = dcs.parse_output("some warning without the contract shape\n")
        assert candidates == [] and unparsed == 1


class TestScan:
    def test_candidates_filtered_to_report_prefixes(self):
        result = dcs.scan(runner=lambda cmd: _proc(3, VULTURE_OUT))
        files = [c["file"] for c in result["candidates"]]
        # tests/ and evals/ resolve references but are never reported.
        assert files == [
            "src/contemplative_agent/core/foo.py",
            "scripts/old_tool.py",
        ]
        assert result["count"] == 2
        assert result["unparsed_lines"] == 0

    def test_clean_scan_is_zero_candidates(self):
        # vulture exits 0 with empty output when nothing is dead.
        result = dcs.scan(runner=lambda cmd: _proc(0, ""))
        assert result["count"] == 0
        assert result["candidates"] == []

    def test_f_dc_1_missing_binary_abstains_tool_missing(self):
        def runner(cmd):
            raise FileNotFoundError("vulture")

        with pytest.raises(dcs.ScanError) as exc:
            dcs.scan(runner=runner)
        assert exc.value.reason == "TOOL_MISSING"

    def test_f_dc_2_unexpected_exit_code_abstains_tool_failed(self):
        # 0 = clean and 3 = dead code found are vulture's success codes
        # (verified against vulture 2.16); anything else is a tool fault.
        with pytest.raises(dcs.ScanError) as exc:
            dcs.scan(runner=lambda cmd: _proc(2, "", "config error: bad option"))
        assert exc.value.reason == "TOOL_FAILED"
        assert "config error" in exc.value.detail

    def test_f_dc_3_unparseable_output_abstains_not_silent_zero(self):
        # A format drift must never read as "no dead code this week".
        with pytest.raises(dcs.ScanError) as exc:
            dcs.scan(runner=lambda cmd: _proc(3, "totally new output format\nanother line\n"))
        assert exc.value.reason == "UNPARSEABLE_OUTPUT"

    def test_f_dc_4_mixed_garbage_is_surfaced_in_count(self):
        mixed = VULTURE_OUT + "stray non-contract line\n"
        result = dcs.scan(runner=lambda cmd: _proc(3, mixed))
        assert result["count"] == 2
        assert result["unparsed_lines"] == 1

    def test_f_dc_5_hung_vulture_abstains_tool_timeout(self):
        def runner(cmd):
            raise subprocess.TimeoutExpired(cmd=list(cmd), timeout=240)

        with pytest.raises(dcs.ScanError) as exc:
            dcs.scan(runner=runner)
        assert exc.value.reason == "TOOL_TIMEOUT"

    def test_f_dc_6_permission_fault_abstains_tool_failed(self):
        def runner(cmd):
            raise PermissionError("not executable")

        with pytest.raises(dcs.ScanError) as exc:
            dcs.scan(runner=runner)
        assert exc.value.reason == "TOOL_FAILED"

    def test_f_dc_7_stderr_coverage_gap_is_carried(self):
        # vulture prints "invalid syntax at ..." on stderr and still exits 3;
        # the skipped file is a coverage gap the packet must degrade on.
        result = dcs.scan(
            runner=lambda cmd: _proc(3, VULTURE_OUT, 'src/b.py:1: invalid syntax at "def (:"\n')
        )
        assert result["count"] == 2
        assert result["stderr_lines"] == 1

    def test_path_shapes_are_normalized_before_the_prefix_filter(self):
        # ./src/… or backslash separators must not silently zero the report.
        out = (
            "./src/contemplative_agent/core/foo.py:12: unused function 'orphan' (60% confidence)\n"
            "scripts\\old_tool.py:3: unused variable 'LEGACY_FLAG' (100% confidence)\n"
        )
        result = dcs.scan(runner=lambda cmd: _proc(3, out))
        assert [c["file"] for c in result["candidates"]] == [
            "src/contemplative_agent/core/foo.py",
            "scripts/old_tool.py",
        ]


class TestMain:
    def test_main_writes_json_and_exits_zero(self, capsys, monkeypatch):
        monkeypatch.setattr(dcs, "run_vulture", lambda cmd: _proc(3, VULTURE_OUT))
        rc = dcs.main([])
        assert rc == 0
        # json.loads, not a substring: the actual contract with
        # weekly-pipeline.sh is that stdout is valid JSON.
        data = json.loads(capsys.readouterr().out)
        assert data["count"] == 2
        assert data["parsed_total"] == 4

    def test_main_fault_exits_nonzero_with_reason_on_stderr(self, capsys, monkeypatch):
        monkeypatch.setattr(dcs, "run_vulture", lambda cmd: _proc(2, "", "boom"))
        rc = dcs.main([])
        assert rc == 1
        err = capsys.readouterr().err
        assert "TOOL_FAILED" in err
