"""Fault column for the weekly-pipeline.sh value-layer stage (stage 5b).

The stage is a deterministic due check (`value_layer_due_check.py`) plus a
conditional identity staging behind three guards: live-run (no backfill
firing), insight-completed-today (`.last_insight` marker — the 08:00 insight
job writes to staging INSIDE the chain's window, so staging identity into
the momentarily-empty dir would make the ADR-0074 pending guard discard the
arriving insight batch), and staging-empty.  These tests drive the real
script with stubbed `claude` / `uv` binaries, per scenario:

- V-1  due + marker fresh + staging empty → distill staged (md + sidecar),
       audited ok, packet carries the inventory line and the §8 section
- V-2  due + staging busy → deferred with IDENTITY_STAGING_BUSY, manual
       gate path named in packet, distill never invoked
- V-3  approval audit log missing → due check abstains, VALUE_LAYER_CHECK_FAIL,
       no identity run, packet still builds (fail-forward)
- V-4  nothing due → no identity attempt, quiet packet
- V-5  distill runs but stages nothing (LLM failure) → IDENTITY_STAGE_FAIL
       from the on-disk ground truth, packet visible
- V-6  insight marker stale/missing → IDENTITY_INSIGHT_PENDING, distill
       never invoked (the reverse-race guard, adr review 2026-08-10)
- V-7  --end-date backfill → IDENTITY_BACKFILL_SKIP, distill never invoked
       (code review 2026-08-10 HIGH)
- V-8  distill writes the .md but not the sidecar (timeout kill window) →
       IDENTITY_STAGE_FAIL — adopt-staged pairs on the sidecar
- V-9  CLI staging refusal (concurrent producer won the flock) →
       IDENTITY_STAGING_RACE, a designed outcome distinct from LLM failure

macOS-only marker matches test_weekly_analysis_shell.py (BSD stat/date).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="weekly-pipeline.sh uses BSD stat/date"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "weekly-pipeline.sh"

# Live END_DATE: the backfill guard compares against `date -v-1d`, so the
# fixtures must use the real yesterday (in local time, matching the script).
LIVE_END_DATE = (datetime.now().astimezone() - timedelta(days=1)).strftime("%Y-%m-%d")

CLAUDE_STUB = """#!/bin/bash
exit 0
"""

UV_STUB = """#!/bin/bash
# Stub uv: the only call this stage makes is `uv run ... contemplative-agent
# distill-identity --stage`; behavior per scenario marker file:
#   identity_fail    — exit 0, stage nothing (LLM failure shape)
#   identity_partial — write the .md but not the sidecar (timeout kill window)
#   identity_refuse  — print the CLI's ADR-0074 refusal line, stage nothing
#   (default)        — stage the complete md + sidecar pair
if [[ "$*" == *distill-identity* ]]; then
  echo "distill-identity invoked" >> "$STUB_STATE/identity_calls"
  if [[ -f "$STUB_STATE/identity_fail" ]]; then
    exit 0
  fi
  if [[ -f "$STUB_STATE/identity_refuse" ]]; then
    echo "Another staging producer holds the staging lock — refusing this batch (ADR-0074). Retry when it finishes."
    exit 0
  fi
  mkdir -p "$MOLTBOOK_HOME/.staged"
  echo "distilled identity body" > "$MOLTBOOK_HOME/.staged/identity.md"
  if [[ ! -f "$STUB_STATE/identity_partial" ]]; then
    echo '{"target": "identity.md"}' > "$MOLTBOOK_HOME/.staged/identity.md.meta.json"
  fi
fi
exit 0
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _make_env(
    tmp_path: Path,
    *,
    approval_audit_lines: list[str] | None,
    staged_metas: int = 0,
    stub_marker: str | None = None,
    insight_marker: str = "fresh",
    end_date: str = LIVE_END_DATE,
) -> tuple[dict, str]:
    home = tmp_path / "moltbook"
    analysis = home / "reports" / "analysis"
    analysis.mkdir(parents=True)
    (home / "logs").mkdir(parents=True)
    (home / ".staged").mkdir(parents=True)
    (home / "skills").mkdir(parents=True)

    (analysis / f"weekly-{end_date}.md").write_text("# report\n\nbody\n", encoding="utf-8")

    if approval_audit_lines is not None:
        (home / "logs" / "audit.jsonl").write_text(
            "\n".join(approval_audit_lines) + "\n", encoding="utf-8"
        )
    (home / "knowledge.json").write_text("[]", encoding="utf-8")
    for i in range(staged_metas):
        (home / ".staged" / f"insight-{i}.md").write_text("body\n", encoding="utf-8")
        (home / ".staged" / f"insight-{i}.md.meta.json").write_text("{}\n", encoding="utf-8")

    now = datetime.now(timezone.utc)
    if insight_marker == "fresh":
        (home / "skills" / ".last_insight").write_text(now.isoformat() + "\n", encoding="utf-8")
    elif insight_marker == "stale":
        (home / "skills" / ".last_insight").write_text(
            (now - timedelta(days=2)).isoformat() + "\n", encoding="utf-8"
        )
    # insight_marker == "missing": write nothing

    state = tmp_path / "stub-state"
    state.mkdir()
    if stub_marker is not None:
        (state / stub_marker).write_text("1\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "claude", CLAUDE_STUB)
    _write_exec(bin_dir / "uv", UV_STUB)

    env = os.environ.copy()
    env["MOLTBOOK_HOME"] = str(home)
    env["STUB_STATE"] = str(state)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["MOLTBOOK_PIPELINE_STAGES"] = "valuelayer,packet"
    return env, end_date


def _run(env: dict, end_date: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--skip-report", "--end-date", end_date],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _audit_events(env: dict) -> list[dict]:
    audit = Path(env["MOLTBOOK_HOME"]) / "logs" / "weekly-pipeline-audit.jsonl"
    return [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]


def _stage_events(env: dict, stage: str) -> list[dict]:
    return [
        e
        for e in _audit_events(env)
        if e.get("event") == "stage_result" and e.get("stage") == stage
    ]


def _packet_text(env: dict, end_date: str) -> str:
    packet = Path(env["MOLTBOOK_HOME"]) / "reports" / "analysis" / f"weekly-{end_date}-packet.md"
    return packet.read_text(encoding="utf-8")


def _identity_line(days_ago: int) -> str:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return json.dumps(
        {
            "ts": ts.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "command": "distill-identity",
            "decision": "approved",
        }
    )


def test_v1_identity_due_and_staging_empty_stages_candidate(tmp_path: Path):
    env, end_date = _make_env(tmp_path, approval_audit_lines=[_identity_line(40)])
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    assert [e["result"] for e in _stage_events(env, "valuelayer")] == ["ok"]
    assert [e["result"] for e in _stage_events(env, "identity")] == ["ok"]
    staged_dir = Path(env["MOLTBOOK_HOME"]) / ".staged"
    assert (staged_dir / "identity.md").is_file()
    assert (staged_dir / "identity.md.meta.json").is_file()

    packet = _packet_text(env, end_date)
    assert "identity candidate: 1" in packet
    assert "## 8. Value layer cadence" in packet
    # The instrument reading is persisted for the longitudinal read.
    vl_json = (
        Path(env["MOLTBOOK_HOME"]) / "pipeline" / "value-layer" / f"value-layer-{end_date}.json"
    )
    assert json.loads(vl_json.read_text(encoding="utf-8"))["identity"]["due"] is True


def test_v2_identity_due_but_staging_busy_defers(tmp_path: Path):
    env, end_date = _make_env(tmp_path, approval_audit_lines=[_identity_line(40)], staged_metas=1)
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    events = _stage_events(env, "identity")
    assert [(e["result"], e.get("reason")) for e in events] == [
        ("skipped", "IDENTITY_STAGING_BUSY")
    ]
    # The distill must never have been attempted against a busy staging dir.
    assert not (Path(env["STUB_STATE"]) / "identity_calls").exists()
    packet = _packet_text(env, end_date)
    assert "IDENTITY_STAGING_BUSY" in packet
    assert "distill-identity" in packet.split("## 8.")[1]


def test_v3_missing_approval_audit_abstains_and_packet_survives(tmp_path: Path):
    env, end_date = _make_env(tmp_path, approval_audit_lines=None)
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    events = _stage_events(env, "valuelayer")
    assert [(e["result"], e.get("reason")) for e in events] == [("fail", "VALUE_LAYER_CHECK_FAIL")]
    assert _stage_events(env, "identity") == []
    assert not (Path(env["STUB_STATE"]) / "identity_calls").exists()
    packet = _packet_text(env, end_date)
    assert "VALUE_LAYER_CHECK_FAIL" in packet
    assert "Value layer cadence" not in packet


def test_v4_nothing_due_is_quiet(tmp_path: Path):
    env, end_date = _make_env(tmp_path, approval_audit_lines=[_identity_line(3)])
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    assert [e["result"] for e in _stage_events(env, "valuelayer")] == ["ok"]
    assert _stage_events(env, "identity") == []
    assert "Value layer cadence" not in _packet_text(env, end_date)


def test_v5_distill_stages_nothing_reads_as_fail(tmp_path: Path):
    env, end_date = _make_env(
        tmp_path, approval_audit_lines=[_identity_line(40)], stub_marker="identity_fail"
    )
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    events = _stage_events(env, "identity")
    assert [(e["result"], e.get("reason")) for e in events] == [("fail", "IDENTITY_STAGE_FAIL")]
    assert "IDENTITY_STAGE_FAIL" in _packet_text(env, end_date)


@pytest.mark.parametrize("marker_state", ["stale", "missing"])
def test_v6_insight_marker_not_fresh_defers(tmp_path: Path, marker_state: str):
    """The reverse-race guard: identity fires only after the same-day insight
    job has COMPLETED (marker fresh) — otherwise staging identity into the
    momentarily-empty dir would make ADR-0074 discard the arriving insight
    batch (adr review 2026-08-10 CRITICAL)."""
    env, end_date = _make_env(
        tmp_path, approval_audit_lines=[_identity_line(40)], insight_marker=marker_state
    )
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    events = _stage_events(env, "identity")
    assert [(e["result"], e.get("reason")) for e in events] == [
        ("skipped", "IDENTITY_INSIGHT_PENDING")
    ]
    assert not (Path(env["STUB_STATE"]) / "identity_calls").exists()
    assert "IDENTITY_INSIGHT_PENDING" in _packet_text(env, end_date)


def test_v7_backfill_never_fires_a_run(tmp_path: Path):
    """A --end-date backfill must not fire a real LLM run off a stale-dated
    reading and reset the genuine cadence clock (code review 2026-08-10)."""
    backfill = (datetime.now().astimezone() - timedelta(days=10)).strftime("%Y-%m-%d")
    env, end_date = _make_env(
        tmp_path, approval_audit_lines=[_identity_line(60)], end_date=backfill
    )
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    events = _stage_events(env, "identity")
    assert [(e["result"], e.get("reason")) for e in events] == [
        ("skipped", "IDENTITY_BACKFILL_SKIP")
    ]
    assert not (Path(env["STUB_STATE"]) / "identity_calls").exists()


def test_v8_missing_sidecar_reads_as_fail(tmp_path: Path):
    """adopt-staged pairs on the .meta.json sidecar — an .md alone is an
    orphan, not a candidate (codex review 2026-08-10 P2)."""
    env, end_date = _make_env(
        tmp_path, approval_audit_lines=[_identity_line(40)], stub_marker="identity_partial"
    )
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    events = _stage_events(env, "identity")
    assert [(e["result"], e.get("reason")) for e in events] == [("fail", "IDENTITY_STAGE_FAIL")]
    assert "identity candidate: 1" not in _packet_text(env, end_date)


def test_v9_cli_refusal_is_a_designed_outcome_not_a_fault(tmp_path: Path):
    """Losing the flock to a concurrent producer is ADR-0074 working as
    designed — it must not read as an LLM failure in the P4 detector."""
    env, end_date = _make_env(
        tmp_path, approval_audit_lines=[_identity_line(40)], stub_marker="identity_refuse"
    )
    proc = _run(env, end_date)
    assert proc.returncode == 0, proc.stderr

    events = _stage_events(env, "identity")
    assert [(e["result"], e.get("reason")) for e in events] == [
        ("skipped", "IDENTITY_STAGING_RACE")
    ]
    assert "IDENTITY_STAGE_FAIL" not in _packet_text(env, end_date)
