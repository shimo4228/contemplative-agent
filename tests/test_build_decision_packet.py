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
