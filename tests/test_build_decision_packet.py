"""Tests for scripts/build_decision_packet.py (+ pipeline_audit.py).

The Saturday decision packet is the single human gate of the unattended
weekly chain (ADR-0085), so its assembly is deliberately code, not LLM:
counts, tables and inclusion rules are structural properties, and the
human must be able to trust that "N patches" means N files on disk and
that prompt-scope diffs appear as full text (human-gate: summarising a
behavior-shaping diff can hide a gate-weakening change).

Fail-forward is the load-bearing fault column: the packet must be produced
— naming what died, with reason codes — for every partial failure of the
chain, because a missing packet is indistinguishable from a chain that
never ran (that ambiguity is what the watchdog checks, not the builder).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import build_decision_packet as bdp  # noqa: E402  # pyright: ignore[reportMissingImports]

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
AUDIT_SCRIPT = SCRIPTS / "pipeline_audit.py"

RUN_ID = "weekly-2026-07-24-0900"


def _audit_line(event: str, **fields) -> str:
    return json.dumps(
        {"ts": "2026-07-25T00:00:00+00:00", "run_id": RUN_ID, "event": event, **fields}
    )


def _write_inputs(tmp_path: Path) -> dict[str, Path]:
    audit = tmp_path / "weekly-pipeline-audit.jsonl"
    audit.write_text(
        "\n".join(
            [
                _audit_line("stage_result", stage="report", result="ok"),
                _audit_line("stage_result", stage="diagnosis", result="ok"),
                _audit_line(
                    "fix_result",
                    fix_id="F1.2",
                    scope="code",
                    result="patch_ready",
                    attempts="2",
                    patch="patches/weekly-2026-07-24/F1.2.patch",
                ),
                _audit_line(
                    "fix_result",
                    fix_id="F1.3",
                    scope="code",
                    result="failed",
                    attempts="2",
                    reason="VERIFY_FAIL_MAX_ATTEMPTS",
                ),
                _audit_line("review_result", fix_id="F1.2", verdict="APPROVE"),
                # Stale-finding gate: referenced paths got commits after the
                # findings file was written → deterministically skipped, and
                # a skip is not an attempt.
                _audit_line(
                    "fix_result",
                    fix_id="F1.4",
                    scope="code",
                    result="skipped",
                    attempts="0",
                    reason="FINDING_STALE",
                ),
                # A stray event from another run must be ignored.
                json.dumps(
                    {
                        "ts": "2026-07-18T00:00:00+00:00",
                        "run_id": "weekly-2026-07-17-0900",
                        "event": "fix_result",
                        "fix_id": "F1.9",
                        "result": "patch_ready",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    findings = tmp_path / "findings.json"
    findings.write_text(
        json.dumps(
            {
                "source": "weekly-2026-07-24-findings.md",
                "counts": {"f1": 3, "f2": 1, "f3": 2},
                "f1": [
                    {"id": "F1.1", "title": "Prompt slot", "scope": "prompt", "paths": []},
                    {"id": "F1.2", "title": "Sweep state", "scope": "code", "paths": []},
                    {"id": "F1.3", "title": "Other bug", "scope": "code", "paths": []},
                ],
            }
        ),
        encoding="utf-8",
    )

    patches = tmp_path / "patches"
    patches.mkdir()
    (patches / "F1.2.patch").write_text("--- a/x\n+++ b/x\n", encoding="utf-8")

    prompt_patches = tmp_path / "prompt-patches"
    prompt_patches.mkdir()
    (prompt_patches / "F1.1.patch").write_text(
        "--- a/config/prompts/reply.md\n+conditional block\n", encoding="utf-8"
    )

    insight = tmp_path / "insight-review.md"
    insight.write_text(
        "## 1. skill-a — RECOMMEND: adopt\n\nreason\n\n"
        "## 2. skill-b — RECOMMEND: reject\n\nreason\n",
        encoding="utf-8",
    )

    metrics = tmp_path / "pipeline-metrics.jsonl"
    return {
        "audit": audit,
        "findings": findings,
        "patches": patches,
        "prompt_patches": prompt_patches,
        "insight": insight,
        "metrics": metrics,
        "out": tmp_path / "packet.md",
    }


def _build(paths: dict[str, Path], **overrides) -> str:
    args = {
        "end_date": "2026-07-24",
        "run_id": RUN_ID,
        "audit": paths["audit"],
        "metrics": paths["metrics"],
        "findings": paths["findings"],
        "patches_dir": paths["patches"],
        "prompt_patches_dir": paths["prompt_patches"],
        "insight_review": paths["insight"],
        "improvement": None,
        "out": paths["out"],
    }
    args.update(overrides)
    bdp.build_packet(**args)
    return paths["out"].read_text(encoding="utf-8")


def test_packet_inventory_and_fix_table(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    # 1 作業 1 ゲート: the inventory enumerates counts and scope up front.
    assert "code patch: 1" in text
    assert "prompt diff: 1" in text
    assert "insight: 2" in text
    # Fix table carries the success, the bounded failure, and the stale skip.
    assert "F1.2" in text and "APPROVE" in text
    assert "F1.3" in text and "VERIFY_FAIL_MAX_ATTEMPTS" in text
    assert "F1.4" in text and "FINDING_STALE" in text
    # Cross-run events are excluded.
    assert "F1.9" not in text


def test_prompt_diff_inlined_full_text(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    # human-gate: behavior-shaping diffs appear as full text, never a summary.
    assert "+conditional block" in text


def test_insight_recommendations_counted_and_inlined(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "RECOMMEND: adopt" in text
    assert "RECOMMEND: reject" in text


def test_metrics_auto_record_appended(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _build(paths)
    records = [
        json.loads(line) for line in paths["metrics"].read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 1
    rec = records[0]
    assert rec["phase"] == "auto"
    assert rec["week_end"] == "2026-07-24"
    assert rec["f1_total"] == 3
    assert rec["f1_code"] == 2
    assert rec["f1_prompt"] == 1
    assert rec["fix_attempted"] == 2
    assert rec["fix_patch_ready"] == 1
    assert rec["verify_fail"] == 1
    assert rec["insight_items"] == 2
    assert rec["improvement_fired"] is False
    assert "VERIFY_FAIL_MAX_ATTEMPTS" in rec["reason_codes"]


def test_fail_forward_missing_findings(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths, findings=tmp_path / "absent.json")
    # The packet still exists and names the failure instead of hiding it.
    assert "DIAGNOSIS_UNAVAILABLE" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["f1_total"] == 0
    assert "DIAGNOSIS_UNAVAILABLE" in rec["reason_codes"]


def test_fail_forward_missing_insight_review(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths, insight_review=tmp_path / "absent.md")
    assert "INSIGHT_REVIEW_UNAVAILABLE" in text


def test_improvement_section_inlined_when_present(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    imp = tmp_path / "improvement.md"
    imp.write_text("--- a/.claude/skills/x\n+tighten step 3\n", encoding="utf-8")
    text = _build(paths, improvement=imp)
    assert "+tighten step 3" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["improvement_fired"] is True


def test_check_improvement_requires_recurrence(tmp_path: Path):
    metrics = tmp_path / "m.jsonl"
    auto = {"phase": "auto", "week_end": "x", "reason_codes": ["FIX_TIMEOUT"]}
    # One record only → not fired (a single bad week is noise, not a pattern).
    metrics.write_text(json.dumps(auto) + "\n", encoding="utf-8")
    assert bdp.check_improvement(metrics) == {"fired": False, "codes": []}
    # Two consecutive weeks sharing a code → fired (P4-shaped threshold).
    metrics.write_text(
        json.dumps(auto)
        + "\n"
        + json.dumps({"phase": "auto", "week_end": "y", "reason_codes": ["FIX_TIMEOUT", "X"]})
        + "\n",
        encoding="utf-8",
    )
    assert bdp.check_improvement(metrics) == {"fired": True, "codes": ["FIX_TIMEOUT"]}
    # Gate records in between must not break adjacency of auto records.
    metrics.write_text(
        json.dumps(auto)
        + "\n"
        + json.dumps({"phase": "gate", "week_end": "x"})
        + "\n"
        + json.dumps({"phase": "auto", "week_end": "y", "reason_codes": ["OTHER"]})
        + "\n",
        encoding="utf-8",
    )
    assert bdp.check_improvement(metrics) == {"fired": False, "codes": []}


def test_check_improvement_with_current_codes(tmp_path: Path):
    # The orchestrator calls this BEFORE build (this week's auto record is
    # not yet appended), passing the codes it has collected so far; the
    # comparison is then current-week vs the last recorded week.
    metrics = tmp_path / "m.jsonl"
    metrics.write_text(
        json.dumps({"phase": "auto", "week_end": "x", "reason_codes": ["FIX_TIMEOUT"]}) + "\n",
        encoding="utf-8",
    )
    assert bdp.check_improvement(metrics, current_codes=["FIX_TIMEOUT", "Y"]) == {
        "fired": True,
        "codes": ["FIX_TIMEOUT"],
    }
    assert bdp.check_improvement(metrics, current_codes=["OTHER"]) == {
        "fired": False,
        "codes": [],
    }
    # No history at all → nothing to recur against.
    empty = tmp_path / "empty.jsonl"
    assert bdp.check_improvement(empty, current_codes=["FIX_TIMEOUT"]) == {
        "fired": False,
        "codes": [],
    }


def test_gate_record_appended(tmp_path: Path):
    metrics = tmp_path / "m.jsonl"
    bdp.append_gate_record(
        metrics,
        end_date="2026-07-24",
        patches_adopted=1,
        patches_rejected=0,
        prompt_diffs_adopted=1,
        insight_adopted=1,
        insight_rejected=1,
        recommendation_matches=2,
        recommendation_total=2,
    )
    rec = json.loads(metrics.read_text(encoding="utf-8").splitlines()[0])
    assert rec["phase"] == "gate"
    assert rec["patches_adopted"] == 1
    assert rec["recommendation_matches"] == 2


def test_pipeline_audit_cli_appends_event(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    subprocess.run(
        [
            sys.executable,
            str(AUDIT_SCRIPT),
            "--log",
            str(log),
            "--run-id",
            RUN_ID,
            "--event",
            "fix_result",
            "--field",
            "fix_id=F1.2",
            "--field",
            "result=patch_ready",
        ],
        check=True,
        capture_output=True,
    )
    rec = json.loads(log.read_text(encoding="utf-8").splitlines()[0])
    assert rec["run_id"] == RUN_ID
    assert rec["event"] == "fix_result"
    assert rec["fix_id"] == "F1.2"
    assert "ts" in rec


def test_check_improvement_excludes_same_week_records(tmp_path: Path):
    # A same-week rerun must not compare the run against its own earlier
    # attempt (2026-07-29 review): the baseline is last week, not last record.
    metrics = tmp_path / "m.jsonl"
    metrics.write_text(
        json.dumps({"phase": "auto", "week_end": "2026-07-17", "reason_codes": ["A"]})
        + "\n"
        + json.dumps({"phase": "auto", "week_end": "2026-07-24", "reason_codes": ["B"]})
        + "\n",
        encoding="utf-8",
    )
    # Without exclusion this would fire on B (self-comparison).
    assert bdp.check_improvement(metrics, current_codes=["B"], end_date="2026-07-24") == {
        "fired": False,
        "codes": [],
    }
    # The true last-week record still participates.
    assert bdp.check_improvement(metrics, current_codes=["A"], end_date="2026-07-24") == {
        "fired": True,
        "codes": ["A"],
    }


def test_unreadable_inputs_degrade_to_reason_codes(tmp_path: Path):
    # Fail-forward survives non-UTF-8 bytes in every upstream artifact
    # (2026-07-29 review, CRITICAL: UnicodeDecodeError escaped every handler).
    paths = _write_inputs(tmp_path)
    paths["audit"].write_bytes(b"\xff\xfe garbage")
    bad_insight = tmp_path / "bad-insight.md"
    bad_insight.write_bytes(b"\x80\x81")
    bad_findings = tmp_path / "bad-findings.json"
    bad_findings.write_bytes(b"\xff{}")
    text = _build(paths, insight_review=bad_insight, findings=bad_findings)
    assert "AUDIT_UNREADABLE" in text
    assert "INSIGHT_REVIEW_UNREADABLE" in text
    assert "DIAGNOSIS_UNAVAILABLE" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "AUDIT_UNREADABLE" in rec["reason_codes"]


def test_recommend_count_is_heading_anchored(tmp_path: Path):
    # A stray "RECOMMEND:" in body prose must not inflate the inventory count.
    paths = _write_inputs(tmp_path)
    paths["insight"].write_text(
        "## 1. skill-a — RECOMMEND: adopt\n\n"
        "the phrase RECOMMEND: reject appears in prose here\n\n"
        "## 2. skill-b — RECOMMEND: reject\n\nreason\n",
        encoding="utf-8",
    )
    _build(paths)
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["insight_items"] == 2


def _write_review_loop_audit(paths: dict[str, Path]) -> None:
    """Audit shape produced by the review loop (T-PIPELINE-REVIEWLOOP):
    one review_result per round, in chronological order."""
    paths["audit"].write_text(
        "\n".join(
            [
                _audit_line(
                    "fix_result",
                    fix_id="F1.2",
                    scope="code",
                    result="patch_ready",
                    attempts="2",
                    patch="patches/weekly-2026-07-24/F1.2.patch",
                ),
                _audit_line("review_result", fix_id="F1.2", round="1", verdict="CONCERNS"),
                _audit_line("review_result", fix_id="F1.2", round="2", verdict="APPROVE"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def test_reviewer_column_shows_round_history(tmp_path: Path):
    # 2026-08-01 gate failure: a loop whose final verdict is APPROVE must not
    # erase the CONCERNS history — that reproduces the very information loss
    # the loop exists to fix.
    paths = _write_inputs(tmp_path)
    _write_review_loop_audit(paths)
    text = _build(paths)
    assert "CONCERNS→APPROVE" in text


def test_review_notes_inline_final_round_body(tmp_path: Path):
    # The human gate reads the reviewer's reasoning, not a 4-char verdict
    # (07-31 F1.1: three real defects hidden behind "CONCERNS").
    paths = _write_inputs(tmp_path)
    _write_review_loop_audit(paths)
    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()
    (run_logs / "fix-F1.2-review1.log").write_text(
        "VERDICT: CONCERNS\n- round-1 concern about the regression test\n", encoding="utf-8"
    )
    (run_logs / "fix-F1.2-review2.log").write_text(
        "VERDICT: APPROVE\n- round-2 concerns addressed\n", encoding="utf-8"
    )
    text = _build(paths, run_log_dir=run_logs)
    assert "Review notes" in text
    # Final round full text is inlined; earlier rounds stay on disk (their
    # verdicts appear in the history column).
    assert "round-2 concerns addressed" in text
    assert "round-1 concern about the regression test" not in text


def test_review_notes_absent_without_run_log_dir(tmp_path: Path):
    # Backward compatibility: an old-style invocation (no --run-log-dir)
    # renders the same packet as before the loop existed.
    paths = _write_inputs(tmp_path)
    _write_review_loop_audit(paths)
    text = _build(paths)
    assert "Review notes" not in text
    assert "REVIEW_LOG_UNREADABLE" not in text


def test_review_log_unreadable_degrades_to_reason_code(tmp_path: Path):
    # Fail-forward: a reviewed fix whose log vanished still enters the packet,
    # with the gap named instead of hidden.
    paths = _write_inputs(tmp_path)
    _write_review_loop_audit(paths)
    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()  # review2 log deliberately absent
    text = _build(paths, run_log_dir=run_logs)
    assert "REVIEW_LOG_UNREADABLE" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "REVIEW_LOG_UNREADABLE" in rec["reason_codes"]


def test_legacy_single_review_event_without_round(tmp_path: Path):
    # Pre-loop audit lines carry no round field; the reviewer column must
    # render them unchanged (the 07-24 packet is replayable).
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    rows = [line for line in text.splitlines() if line.startswith("| F1.2 ")]
    assert len(rows) == 1
    assert "APPROVE" in rows[0]
    assert "→" not in rows[0]


def test_review_body_with_backtick_fence_stays_contained(tmp_path: Path):
    # LLM review prose routinely quotes code in its own ``` fences; the
    # packet's fence must outrun the body's longest backtick run or the rest
    # of the review spills into raw packet Markdown (2026-08-01 review, HIGH).
    paths = _write_inputs(tmp_path)
    _write_review_loop_audit(paths)
    run_logs = tmp_path / "run-logs"
    run_logs.mkdir()
    (run_logs / "fix-F1.2-review1.log").write_text("VERDICT: CONCERNS\n", encoding="utf-8")
    (run_logs / "fix-F1.2-review2.log").write_text(
        "VERDICT: APPROVE\n- quoted repro:\n```python\nassert x\n```\ntail line\n",
        encoding="utf-8",
    )
    text = _build(paths, run_log_dir=run_logs)
    start = text.index("#### F1.2")
    section = text[start : text.index("## 3.")]
    # The body (including its inner fence) sits inside a longer outer fence.
    assert "````text" in section
    assert section.count("````") == 2
    assert "tail line" in section


def test_pipeline_audit_rejects_reserved_keys(tmp_path: Path):
    log = tmp_path / "audit.jsonl"
    result = subprocess.run(
        [
            sys.executable,
            str(AUDIT_SCRIPT),
            "--log",
            str(log),
            "--run-id",
            RUN_ID,
            "--event",
            "x",
            "--field",
            "run_id=spoofed",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert not log.exists()


# --- Dead-code intake (T-DEADCODE-INTAKE) --------------------------------
# Signal-first: the section and its inventory line exist only on weeks with
# candidates; a quiet week is silent in the packet but still countable in
# the metrics record (zero vs scan-failure stays distinguishable via reason
# codes). Deletion is never authored here — detection only.


def _dead_code_json(tmp_path: Path, candidates: list[dict]) -> Path:
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps(
            {
                "tool": "vulture",
                "report_prefixes": ["src/", "scripts/"],
                "count": len(candidates),
                "candidates": candidates,
                "unparsed_lines": 0,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_dead_code_section_rendered_when_candidates_exist(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    dc = _dead_code_json(
        tmp_path,
        [
            {
                "file": "src/contemplative_agent/core/foo.py",
                "line": 12,
                "message": "unused function 'orphan'",
                "confidence": 60,
            }
        ],
    )
    text = _build(paths, dead_code=dc)
    assert "dead code candidate: 1" in text
    assert "## 5. Dead code candidates" in text
    assert "unused function 'orphan'" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["dead_code_candidates"] == 1


def test_dead_code_zero_week_is_silent(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    dc = _dead_code_json(tmp_path, [])
    text = _build(paths, dead_code=dc)
    assert "Dead code candidates" not in text
    assert "dead code candidate:" not in text
    # The renumbered fixed headings hold on a quiet week (5 is a gap).
    assert "## 6. Pipeline metrics" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    # Scanned clean is 0 — distinguishable from the not-scanned None below.
    assert rec["dead_code_candidates"] == 0


def test_dead_code_absent_arg_keeps_packet_unchanged(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "Dead code candidates" not in text
    assert "DEADCODE_UNREADABLE" not in text
    assert "dead code —(not scanned)" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    # Not scanned must never read as "scanned clean" (2026-08-07 review).
    assert rec["dead_code_candidates"] is None


def test_dead_code_partial_scan_stderr_is_surfaced(tmp_path: Path):
    # F-DC-7 downstream: vulture skipped input files (stderr) — the gate
    # must see the coverage gap, not a clean-looking table.
    paths = _write_inputs(tmp_path)
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps(
            {
                "tool": "vulture",
                "count": 1,
                "candidates": [
                    {
                        "file": "src/contemplative_agent/core/foo.py",
                        "line": 12,
                        "message": "unused function 'orphan'",
                        "confidence": 60,
                    }
                ],
                "unparsed_lines": 0,
                "stderr_lines": 2,
            }
        ),
        encoding="utf-8",
    )
    text = _build(paths, dead_code=path)
    assert "DEADCODE_PARTIAL_SCAN" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "DEADCODE_PARTIAL_SCAN" in rec["reason_codes"]


def test_dead_code_non_dict_rows_are_dropped_not_fatal(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps({"tool": "vulture", "candidates": ["oops", 42]}),
        encoding="utf-8",
    )
    text = _build(paths, dead_code=path)
    assert "Dead code candidates" not in text  # nothing renderable survived
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["dead_code_candidates"] == 0


def test_dead_code_unreadable_degrades_to_reason_code(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    bad = tmp_path / "dead-code.json"
    bad.write_bytes(b"\xff not json")
    text = _build(paths, dead_code=bad)
    assert "DEADCODE_UNREADABLE" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "DEADCODE_UNREADABLE" in rec["reason_codes"]


def test_dead_code_partial_parse_is_surfaced_not_silent(tmp_path: Path):
    # A vulture format drift that breaks only some lines must degrade loudly:
    # reason code in the header + metrics, caveat in the section (codex P2).
    paths = _write_inputs(tmp_path)
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps(
            {
                "tool": "vulture",
                "count": 1,
                "candidates": [
                    {
                        "file": "src/contemplative_agent/core/foo.py",
                        "line": 12,
                        "message": "unused function 'orphan'",
                        "confidence": 60,
                    }
                ],
                "unparsed_lines": 3,
            }
        ),
        encoding="utf-8",
    )
    text = _build(paths, dead_code=path)
    assert "DEADCODE_PARTIAL_PARSE" in text
    assert "3 行が契約形式に一致せず未解釈" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "DEADCODE_PARTIAL_PARSE" in rec["reason_codes"]


def test_dead_code_count_is_code_owned_not_json_claimed(tmp_path: Path):
    # The human-facing count is computed from the candidate rows, never
    # trusted from the JSON's own "count" field.
    paths = _write_inputs(tmp_path)
    path = tmp_path / "dead-code.json"
    path.write_text(
        json.dumps(
            {
                "tool": "vulture",
                "count": 99,
                "candidates": [
                    {
                        "file": "scripts/old_tool.py",
                        "line": 3,
                        "message": "unused variable 'LEGACY_FLAG'",
                        "confidence": 100,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    text = _build(paths, dead_code=path)
    assert "dead code candidate: 1" in text
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert rec["dead_code_candidates"] == 1
