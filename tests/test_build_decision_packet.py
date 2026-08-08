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
import re
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


# --- scope escalation (2026-07-29 security review C4) -----------------------
#
# The shell moves a code-scope patch that touched a path outside
# ^(src|scripts|tests)/ into the full-text gate. That guard worked on the
# 2026-08-07 run, but the packet said nothing about it: the escalated patches
# appeared under §3 with no reason, because the builder harvested reason codes
# only from `fix_result.reason` and the escalation is its own event type. A
# guard whose effect is visible but whose cause is not invites the next reader
# to "fix" the scope classifier (the escalation counterpart of ADR-0075's
# no-silent-fallback rule).


def _escalate(paths: dict[str, Path], fix_id: str = "F1.2", files: object = "docs/x.md") -> None:
    """Record an escalation for ``fix_id`` and move its patch to the prompt dir.

    Mirrors the exporter: escalation redirects the output dir, so the patch
    exists in the prompt dir and NOT in the code dir.
    """
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id=fix_id, files=files) + "\n")
    name = f"{fix_id.replace('/', '_')}.patch"
    (paths["patches"] / name).unlink(missing_ok=True)
    (paths["prompt_patches"] / name).write_text(
        "--- a/src/x.py\n+++ b/src/x.py\n", encoding="utf-8"
    )


def test_scope_escalation_reaches_the_header_reason_codes(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _escalate(paths)
    text = _build(paths)
    # Recomputed from the event type, not read from the shell's REASONS var:
    # the builder stays an independent replay of the audit log.
    assert "SCOPE_ESCALATED" in text.split("## 1.")[0]
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "SCOPE_ESCALATED" in rec["reason_codes"]


def test_scope_escalation_marks_the_fix_table_row(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2")
    text = _build(paths)
    row = next(ln for ln in text.splitlines() if ln.startswith("| F1.2 "))
    # The declared scope stays visible (it is what the classifier said); the
    # marker says the export overrode it.
    assert "code" in row and "SCOPE_ESCALATED" in row
    # An unescalated row keeps its plain scope cell.
    assert "SCOPE_ESCALATED" not in next(ln for ln in text.splitlines() if ln.startswith("| F1.3 "))


def test_escalated_prompt_patch_names_its_cause(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2", files="docs/CODEMAPS/architecture.md")
    text = _build(paths)
    section = text.split("## 3.")[1].split("## 4.")[0]
    body = section.split("### F1.2.patch")[1]
    # Why this code-scope patch is in the full-text section, and which path
    # put it there — answerable from the packet alone.
    assert "SCOPE_ESCALATED" in body
    assert "触れたパス: `docs/CODEMAPS/architecture.md`" in body
    # The un-escalated prompt diff carries no such note.
    assert "SCOPE_ESCALATED" not in section.split("### F1.1.patch")[1].split("###")[0]


def test_inventory_counts_escalated_diffs(tmp_path: Path):
    paths = _write_inputs(tmp_path)
    _escalate(paths)
    text = _build(paths)
    inventory = text.split("## 1.")[1].split("## 2.")[0]
    assert "prompt diff: 2" in inventory
    assert "うち 1 件" in inventory


def test_escalated_patch_leaves_the_code_patch_count(tmp_path: Path):
    # The gate approves code patches in Step 2 WITHOUT reading their diffs;
    # an escalated patch is not in patches_dir and must not be counted as an
    # apply target, or the escalation's whole point is lost one step earlier.
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2")  # the only patch_ready code fix
    inventory = _build(paths).split("## 1.")[1].split("## 2.")[0]
    assert "code patch: 0 件" in inventory
    assert "+1 件は §3 の全文ゲートへ昇格" in inventory


def test_escalation_inferred_from_patch_location_when_event_is_lost(tmp_path: Path):
    # The shell's audit append is best-effort. Losing that one line must not
    # erase the escalation from all three surfaces — a code-scope fix whose
    # patch landed in the prompt dir is an escalation by definition.
    paths = _write_inputs(tmp_path)
    audit_lines = (
        paths["audit"]
        .read_text(encoding="utf-8")
        .replace(
            "patches/weekly-2026-07-24/F1.2.patch",
            str(paths["prompt_patches"] / "F1.2.patch"),
        )
    )
    paths["audit"].write_text(audit_lines, encoding="utf-8")
    text = _build(paths)
    # Named as inferred, so the audit-log gap is itself visible.
    assert "SCOPE_ESCALATED_INFERRED" in text.split("## 1.")[0]
    assert "SCOPE_ESCALATED" in next(ln for ln in text.splitlines() if ln.startswith("| F1.2 "))
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "SCOPE_ESCALATED_INFERRED" in rec["reason_codes"]


def test_recorded_escalation_does_not_also_report_as_inferred(tmp_path: Path):
    # Both signals firing for the same fix is the normal case, not a gap.
    paths = _write_inputs(tmp_path)
    audit_lines = (
        paths["audit"]
        .read_text(encoding="utf-8")
        .replace(
            "patches/weekly-2026-07-24/F1.2.patch",
            str(paths["prompt_patches"] / "F1.2.patch"),
        )
    )
    paths["audit"].write_text(audit_lines, encoding="utf-8")
    _escalate(paths, fix_id="F1.2", files="docs/x.md")
    text = _build(paths)
    assert "SCOPE_ESCALATED_INFERRED" not in text
    assert "SCOPE_ESCALATED" in text


def test_no_escalation_leaves_the_packet_unchanged(tmp_path: Path):
    # Signal-first: a quiet week adds no reason code, no marker, no note.
    paths = _write_inputs(tmp_path)
    text = _build(paths)
    assert "SCOPE_ESCALATED" not in text
    assert "うち" not in text.split("## 1.")[1].split("## 2.")[0]


# --- fault column ----------------------------------------------------------


def test_escalation_without_files_field_still_surfaces(tmp_path: Path):
    # A truncated/older event shape must not hide the escalation itself —
    # the reason code and the marker are what the human acts on.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1.2") + "\n")
    (paths["prompt_patches"] / "F1.2.patch").write_text("--- a/src/x.py\n", encoding="utf-8")
    text = _build(paths)
    assert "SCOPE_ESCALATED" in text
    assert "（パス不明）" in text


def test_escalated_paths_cannot_forge_packet_structure(tmp_path: Path):
    # The path list is chosen by the fix session (an LLM with write access in
    # the worktree); a crafted filename must not be able to forge a section
    # heading. The shell collapses newlines, but the builder must not depend
    # on that — and splitlines() is the alphabet every consumer splits on.
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2", files="docs/a.md ## 5. Dead code candidates")
    text = _build(paths)
    assert not any(ln.startswith("## 5.") for ln in text.splitlines())


def test_escalated_paths_cannot_write_prose_or_html(tmp_path: Path):
    # git passes every printable ASCII byte in a filename through unquoted, so
    # a raw render would let the fix session write reassurance in the builder's
    # own voice, or open an HTML <details> that folds away the rest of the
    # packet in a browser preview. Only the path allowlist survives.
    paths = _write_inputs(tmp_path)
    _escalate(
        paths,
        fix_id="F1.2",
        files="docs/x.md).　確認済み・対応不要。(was: y.md <details> *bold*",
    )
    line = next(ln for ln in _build(paths).splitlines() if ln.startswith("触れたパス:"))
    assert "確認済み" not in line and "<details>" not in line
    assert "`docs/x.md" in line  # the real path is still legible to the human


def test_escalated_path_list_is_bounded(tmp_path: Path):
    # An unbounded list is a cheap way to push the surrounding explanation out
    # of the reader's view in the packet's most decision-relevant sentence.
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2", files=" ".join(f"docs/f{i}.md" for i in range(50)))
    line = next(ln for ln in _build(paths).splitlines() if ln.startswith("触れたパス:"))
    # "断片", not "件": git does not quote spaces, so one filename can split
    # into many tokens — calling them files would be a misleading count.
    assert "ほか 30 断片" in line
    assert "docs/f49.md" not in line


def test_unresolvable_patch_path_does_not_kill_the_packet(tmp_path: Path):
    # The inferred-escalation check is the builder's only filesystem I/O on an
    # audit-derived string. resolve() raises ValueError (not OSError) on an
    # embedded NUL — fail-forward means losing that signal, not the packet.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "fix_result",
                fix_id="F1.6",
                scope="code",
                result="patch_ready",
                attempts="1",
                patch="pat\x00ches/F1.6.patch",
            )
            + "\n"
        )
    assert "F1.6" in _build(paths)


def test_review_round_cannot_forge_a_section_through_the_log_path(tmp_path: Path):
    # `round` is audit-derived and becomes part of a filename; the resulting
    # REVIEW_LOG_UNREADABLE note interpolates that path. A newline there forges
    # the §5 heading the gate attaches a deletion procedure to.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "review_result",
                fix_id="F1.3",
                round="1\n\n## 5. Dead code candidates\n\n| `src/x.py` | 1 | unused | 90% |",
                verdict="APPROVE",
            )
            + "\n"
        )
    run_logs = tmp_path / "runlog"
    run_logs.mkdir()
    text = _build(paths, run_log_dir=run_logs)
    assert "REVIEW_LOG_UNREADABLE" in text
    assert not any(ln.startswith("## 5.") for ln in text.splitlines())


def test_escalation_inferred_from_declared_scope_without_any_audit_event(tmp_path: Path):
    # A sustained audit-write outage takes out both event-based signals at
    # once. findings.json + the exported filename still reconstruct it.
    paths = _write_inputs(tmp_path)
    paths["audit"].write_text("", encoding="utf-8")
    (paths["prompt_patches"] / "F1.2.patch").write_text(  # F1.2 is declared code
        "--- a/src/x.py\n", encoding="utf-8"
    )
    text = _build(paths)
    assert "SCOPE_ESCALATED_INFERRED" in text
    body = text.split("### F1.2.patch")[1]
    assert "SCOPE_ESCALATED" in body


def test_declared_prompt_scope_patch_is_not_inferred_as_escalated(tmp_path: Path):
    # F1.1 is declared prompt scope — an ordinary prompt diff, not an override.
    paths = _write_inputs(tmp_path)
    paths["audit"].write_text("", encoding="utf-8")
    assert "SCOPE_ESCALATED" not in _build(paths)


def test_inferred_escalation_does_not_assert_paths_it_never_saw(tmp_path: Path):
    # The inferred branch observed only the patch's output dir. Repeating the
    # observed branch's sentence would assert a cause the builder never saw —
    # the unearned certainty this whole change exists to remove.
    paths = _write_inputs(tmp_path)
    paths["audit"].write_text("", encoding="utf-8")
    (paths["prompt_patches"] / "F1.2.patch").write_text("--- a/src/x.py\n", encoding="utf-8")
    body = _build(paths).split("### F1.2.patch")[1].split("```")[0]
    assert "SCOPE_ESCALATED_INFERRED" in body
    assert "の外に触れた" not in body  # no fabricated cause
    assert "触れたパス:" not in body  # no path slot reused for a non-path


def test_reviewer_verdict_is_constrained_to_its_contract(tmp_path: Path):
    # `verdict` is the one free-text LLM-authored value in the packet: the
    # shell greps a line out of the review session's own output. Left on _cell
    # alone it could carry <details> into the §2 table AND the #### heading,
    # folding away every later section in a browser preview.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "review_result",
                fix_id="F1.3",
                verdict="APPROVE <details><summary>ok</summary>",
            )
            + "\n"
        )
    text = _build(paths)
    assert "<details>" not in text
    assert "UNRECOGNIZED(" in text
    # Breaking the reviewer contract is itself reportable, not silently shown.
    assert "REVIEW_VERDICT_UNRECOGNIZED" in text.split("## 1.")[0]
    # A contract-conforming verdict is untouched.
    assert "| F1.2 " in text and "APPROVE |" in text


def test_designed_escalation_does_not_fire_the_improvement_trigger(tmp_path: Path):
    # A docs-touching fix two weeks running is routine. P4 exists to catch
    # faults; spending an unattended session "improving" a guard that worked
    # as designed is the wrong trigger. An audit-log gap still counts.
    metrics = tmp_path / "metrics.jsonl"
    metrics.write_text(
        json.dumps({"phase": "auto", "week_end": "2026-07-17", "reason_codes": ["SCOPE_ESCALATED"]})
        + "\n",
        encoding="utf-8",
    )
    assert bdp.check_improvement(metrics, current_codes=["SCOPE_ESCALATED"])["fired"] is False
    assert (
        bdp.check_improvement(
            metrics, current_codes=["SCOPE_ESCALATED", "SCOPE_ESCALATED_INFERRED"]
        )["fired"]
        is False
    )  # INFERRED not in the baseline yet
    metrics.write_text(
        json.dumps(
            {
                "phase": "auto",
                "week_end": "2026-07-17",
                "reason_codes": ["SCOPE_ESCALATED", "SCOPE_ESCALATED_INFERRED"],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    fired = bdp.check_improvement(metrics, current_codes=["SCOPE_ESCALATED_INFERRED"])
    assert fired["fired"] is True and fired["codes"] == ["SCOPE_ESCALATED_INFERRED"]


def test_null_reason_does_not_become_a_none_reason_code(tmp_path: Path):
    # _cell stringifies, so testing truthiness after it would let a JSON null
    # enter as the literal code "None" — and, recurring, fire P4.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("fix_result", fix_id="F1.5", result="failed", reason=None) + "\n")
    _build(paths)
    rec = json.loads(paths["metrics"].read_text(encoding="utf-8").splitlines()[0])
    assert "None" not in rec["reason_codes"]


def test_truncated_escalation_path_is_marked_as_elided(tmp_path: Path):
    # A truncated path that reads as complete defeats the note's purpose.
    paths = _write_inputs(tmp_path)
    _escalate(paths, fix_id="F1.2", files="docs/" + "a" * 200 + ".md")
    line = next(ln for ln in _build(paths).splitlines() if ln.startswith("触れたパス:"))
    assert "…`" in line


def test_table_cells_escape_pipes(tmp_path: Path):
    # The §2 table's own values are audit-derived too: an unescaped `|` in any
    # of them silently shifts every later column. Pinned on `patch`, the one
    # cell carrying a filesystem path.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "fix_result",
                fix_id="F1.7",
                scope="code",
                result="patch_ready",
                attempts="1",
                patch="patches/a|b.patch",
            )
            + "\n"
        )
    row = next(ln for ln in _build(paths).splitlines() if ln.startswith("| F1.7 "))
    assert "a\\|b.patch" in row
    # No unescaped `|` outside the six column delimiters.
    assert re.sub(r"\\\|", "", row).count("|") == 7


def test_escalation_without_exported_patch_still_surfaces(tmp_path: Path):
    # Escalation moves the output dir; the export can still fail (EMPTY_DIFF).
    # No §3 body exists to annotate, so the header + table must carry it —
    # and the inventory must not claim a full-text diff that is not there.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1.3", files="docs/x.md") + "\n")
    text = _build(paths)
    assert "SCOPE_ESCALATED" in text
    assert "SCOPE_ESCALATED" in next(ln for ln in text.splitlines() if ln.startswith("| F1.3 "))
    assert "うち" not in text.split("## 1.")[1].split("## 2.")[0]


def test_escalation_of_another_run_is_not_harvested(tmp_path: Path):
    # Run-id filtering is the property the independent-replay design rests on:
    # last week's escalation must not raise this week's reason code.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            json.dumps(
                {
                    "ts": "2026-07-18T00:00:00+00:00",
                    "run_id": "weekly-2026-07-17-0900",
                    "event": "scope_escalation",
                    "fix_id": "F1.2",
                    "files": "docs/old.md",
                }
            )
            + "\n"
        )
    text = _build(paths)
    assert "SCOPE_ESCALATED" not in text
    assert "docs/old.md" not in text


def test_escalated_fix_id_with_slash_matches_its_patch(tmp_path: Path):
    # The exporter names patches `<fix_id with / → _>.patch`; the builder must
    # use the same contract or the §3 note lands on no patch at all.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1/9", files="docs/y.md") + "\n")
    (paths["prompt_patches"] / "F1_9.patch").write_text("--- a/src/y.py\n", encoding="utf-8")
    body = _build(paths).split("### F1_9.patch")[1]
    assert "SCOPE_ESCALATED" in body and "docs/y.md" in body


def test_escalation_files_null_or_list_degrade_readably(tmp_path: Path):
    # A JSON null must not print "None" as if it were a path, and a list must
    # not leak a Python repr — the builder does not depend on the shell's
    # space-joined string formatting.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1.2", files=None) + "\n")
    (paths["prompt_patches"] / "F1.2.patch").write_text("--- a/src/x.py\n", encoding="utf-8")
    text = _build(paths)
    assert "（パス不明）" in text and "触れたパス: None" not in text

    (tmp_path / "second").mkdir()
    paths2 = _write_inputs(tmp_path / "second")
    with paths2["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", fix_id="F1.2", files=["docs/a.md"]) + "\n")
    (paths2["prompt_patches"] / "F1.2.patch").write_text("--- a/src/x.py\n", encoding="utf-8")
    assert "触れたパス: `docs/a.md`" in _build(paths2)


def test_escalation_without_fix_id_marks_no_row(tmp_path: Path):
    # A "?" key would stamp the marker onto every other row that also lost its
    # fix_id. The escalation itself still reaches the header.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(_audit_line("scope_escalation", files="docs/x.md") + "\n")
        fh.write(_audit_line("fix_result", scope="code", result="patch_ready", attempts="1") + "\n")
    text = _build(paths)
    assert "SCOPE_ESCALATED" in text.split("## 1.")[0]
    assert "SCOPE_ESCALATED" not in next(ln for ln in text.splitlines() if ln.startswith("| ? "))


def test_reason_code_cannot_forge_a_heading_from_the_header(tmp_path: Path):
    # Reason codes are literal constants in today's emitter, but the builder
    # does not trust the shell: the header renders them into a line of prose.
    paths = _write_inputs(tmp_path)
    with paths["audit"].open("a", encoding="utf-8") as fh:
        fh.write(
            _audit_line(
                "fix_result",
                fix_id="F1.8",
                scope="code",
                result="failed",
                attempts="1",
                reason="VERIFY_FAIL\n## 5. Dead code candidates",
            )
            + "\n"
        )
    text = _build(paths)
    assert not any(ln.startswith("## 5.") for ln in text.splitlines())
