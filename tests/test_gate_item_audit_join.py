"""scripts/gate_item_audit_join.py: a week's gate_item rows resolve to audit rows (P1-12.1 PR-B)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "gate_item_audit_join.py"


def _write(path: Path, rows: list[dict]) -> Path:
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


def _run(tmp_path: Path, metrics: list[dict], audit: list[dict], run_id="gate-2026-10-31"):
    m = _write(tmp_path / "pipeline-metrics.jsonl", metrics)
    a = _write(tmp_path / "audit.jsonl", audit)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--metrics", str(m), "--audit", str(a), "--run-id", run_id],
        capture_output=True,
        text=True,
    )


def _item(name="a.md", **kw):
    row = {
        "ts": "2026-10-31T05:00:00+00:00",
        "run_id": "gate-2026-10-31",
        "event": "gate_item",
        "item": name,
        "category": "insight",
        "recommendation": "adopt",
        "decision": "adopt",
        "content_hash": "0123456789abcdef",
        "approver": "Test Human",
    }
    row.update(kw)
    return row


def _audit_row(**kw):
    row = {
        "ts": "2026-10-31T04:59:00+00:00",
        "command": "insight",
        "decision": "approved",
        "source": "stage-adopted-names",
        "content_hash": "0123456789abcdef",
        "approver": "Test Human",
    }
    row.update(kw)
    return row


def test_every_item_resolving_exits_zero(tmp_path):
    out = _run(tmp_path, [_item()], [_audit_row()])
    assert out.returncode == 0, out.stdout
    assert "0 unresolved" in out.stdout


def test_a_missing_content_hash_is_unresolved(tmp_path):
    item = _item()
    del item["content_hash"]
    out = _run(tmp_path, [item], [_audit_row()])
    assert out.returncode == 1
    assert "no content_hash" in out.stdout


def test_a_hash_with_no_audit_row_is_unresolved(tmp_path):
    out = _run(tmp_path, [_item()], [_audit_row(content_hash="ffffffffffffffff")])
    assert out.returncode == 1
    assert "no approved/rejected audit row" in out.stdout


def test_a_staged_row_does_not_satisfy_the_join(tmp_path):
    out = _run(tmp_path, [_item()], [_audit_row(decision="staged", source="stage")])
    assert out.returncode == 1


def test_a_verdict_that_disagrees_is_unresolved(tmp_path):
    out = _run(tmp_path, [_item(decision="reject")], [_audit_row()])
    assert out.returncode == 1
    assert "gate_item says reject, audit row says approved" in out.stdout


def test_hold_and_non_audit_categories_need_no_row(tmp_path):
    items = [
        _item("h.md", decision="hold", content_hash=""),
        _item("O-001", category="deadcode"),
        _item("RFC", category="roadmap", content_hash=""),
    ]
    out = _run(tmp_path, items, [])
    assert out.returncode == 0, out.stdout


def test_an_approver_that_differs_is_noted(tmp_path):
    out = _run(tmp_path, [_item(approver="Someone Else")], [_audit_row()])
    assert out.returncode == 0
    assert "approver differs" in out.stdout


def test_other_runs_are_ignored_and_an_empty_run_is_unavailable(tmp_path):
    out = _run(tmp_path, [_item(run_id="gate-2026-10-24")], [_audit_row()])
    assert out.returncode == 2
    assert "no-gate-items" in out.stdout


def test_an_unreadable_log_is_not_all_resolved(tmp_path):
    out = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--metrics",
            str(tmp_path / "nope.jsonl"),
            "--audit",
            str(tmp_path / "nope2.jsonl"),
            "--run-id",
            "gate-x",
        ],
        capture_output=True,
        text=True,
    )
    assert out.returncode == 2
