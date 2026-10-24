"""Provenance and exit-state records of the weekly session (P2-02.3 / .6 / .7 / .8 / .9).

Drives the real weekly-pipeline.sh (report stage only) with a stubbed `claude`
that answers `--version`, the preflight tool-set probe and the session itself,
and reads back what the audit log recorded:

- P2-02.3  chain_start `model=` / `claude_version=`; the session gets `--model`
           only when PIPELINE_WEEKLY_MODEL is set; the document's `writer:`
           stamp is repeated in a `writer_stamp` stage row.

macOS-only marker matches the other weekly-pipeline shell suites (BSD date).
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="weekly-pipeline.sh uses BSD stat/date"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "weekly-pipeline.sh"
END_DATE = "2026-07-24"

REPORT_MD = (
    "## Inventory\n\nformat: instrument-v1 (RFC-0010); writer: stub-writer-1\n\n"
    "## Ledger\n\n## Deviations\n\n## Exceptions\n\n## Sample\n\n## Discarded\n"
)
FINDINGS_MD = "# Weekly findings\n\n## Diagnosis Metadata\n\n- stub\n"

# One stub for every mode the chain uses: `--version`, the tool-set probe
# (stream-json init event), and the session. argv of the SESSION call is kept
# NUL-delimited in $STUB_STATE/session_args.
CLAUDE_STUB = r"""#!/bin/bash
if [[ "$1" == "--version" ]]; then echo "9.9.9 (Stub Code)"; exit 0; fi
if [[ " $* " == *" stream-json "* ]]; then
  if [[ -f "$STUB_STATE/probe_tools" ]]; then
    python3 - "$STUB_STATE/probe_tools" <<'PY'
import json, sys
tools = open(sys.argv[1]).read().split()
print(json.dumps({"type": "system", "subtype": "init", "tools": tools}))
PY
  fi
  exit 0
fi
printf '%s\0' "$@" > "$STUB_STATE/session_args"
env > "$STUB_STATE/session_env"
if [[ -f "$STUB_STATE/envelope" ]]; then cat "$STUB_STATE/envelope"; fi
cp "$STUB_STATE/report_body.md" "$STUB_REPORT"
cp "$STUB_STATE/findings_body.md" "$STUB_FINDINGS"
exit 0
"""


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def make_env(tmp_path: Path, *, report_md: str = REPORT_MD, probe_tools: str | None = "Read Glob Grep Edit Write Skill") -> dict:
    home = tmp_path / "moltbook"
    (home / "reports" / "analysis").mkdir(parents=True)
    (home / "reports" / "comment-reports").mkdir(parents=True)
    (home / "logs").mkdir(parents=True)
    (home / ".staged").mkdir(parents=True)
    (home / "reports" / "comment-reports" / f"comment-report-{END_DATE}.md").write_text(
        "# Comment report\n\n## Entry 1\n\nOutput: hello.\n", encoding="utf-8"
    )
    state = tmp_path / "stub-state"
    state.mkdir()
    (state / "report_body.md").write_text(report_md, encoding="utf-8")
    (state / "findings_body.md").write_text(FINDINGS_MD, encoding="utf-8")
    if probe_tools is not None:
        (state / "probe_tools").write_text(probe_tools + "\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "claude", CLAUDE_STUB)
    tasks = tmp_path / "tasks"
    tasks.mkdir()
    fakehome = tmp_path / "fakehome"
    fakehome.mkdir()
    private = home / "reports" / ".private"
    private.mkdir(parents=True, exist_ok=True)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("PIPELINE_") and not k.startswith("MOLTBOOK_")
    }
    env.update(
        MOLTBOOK_HOME=str(home),
        HOME=str(fakehome),
        STUB_STATE=str(state),
        STUB_REPORT=str(private / f"weekly-{END_DATE}.md"),
        STUB_FINDINGS=str(private / f"weekly-{END_DATE}-findings.md"),
        PATH=f"{bin_dir}:{env['PATH']}",
        MOLTBOOK_PIPELINE_STAGES="report",
        PIPELINE_TASKS_DIR=str(tasks),
        PIPELINE_CLAIMS_PY=os.devnull,
        PIPELINE_CLAUDE_ENV_PASSTHROUGH="STUB_STATE STUB_REPORT STUB_FINDINGS",
    )
    return env


def run_chain(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--end-date", END_DATE],
        env=env, capture_output=True, text=True, timeout=300,
    )


def audit_events(env: dict) -> list[dict]:
    audit = Path(env["MOLTBOOK_HOME"]) / "logs" / "weekly-pipeline-audit.jsonl"
    return [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]


def chain_start(env: dict) -> dict:
    return [e for e in audit_events(env) if e["event"] == "chain_start"][-1]


def stage_rows(env: dict, stage: str) -> list[dict]:
    return [e for e in audit_events(env) if e.get("event") == "stage_result" and e.get("stage") == stage]


def session_argv(env: dict) -> list[str]:
    raw = (Path(env["STUB_STATE"]) / "session_args").read_text(encoding="utf-8")
    return [a for a in raw.split("\0") if a != ""]


# --- P2-02.3 ------------------------------------------------------------------


def test_p3_chain_start_records_cli_version_and_default_model(tmp_path: Path):
    env = make_env(tmp_path)
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    start = chain_start(env)
    assert start["claude_version"] == "9.9.9 (Stub Code)"
    assert start["model"] == "default"
    assert "--model" not in session_argv(env)


def test_p3_a_pinned_model_reaches_the_session_and_the_audit(tmp_path: Path):
    env = make_env(tmp_path)
    env["PIPELINE_WEEKLY_MODEL"] = "stub-model-x[1m]"
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    assert chain_start(env)["model"] == "stub-model-x[1m]"
    argv = session_argv(env)
    assert argv[argv.index("--model") + 1] == "stub-model-x[1m]"


def test_p3_a_model_with_shell_metacharacters_is_refused_before_any_work(tmp_path: Path):
    env = make_env(tmp_path)
    env["PIPELINE_WEEKLY_MODEL"] = "x; rm -rf /"
    proc = run_chain(env)
    assert proc.returncode == 1
    assert "PIPELINE_WEEKLY_MODEL" in proc.stderr
    assert not (Path(env["MOLTBOOK_HOME"]) / "logs" / "weekly-pipeline-audit.jsonl").exists()


def test_p3_the_documents_writer_stamp_is_repeated_in_the_audit(tmp_path: Path):
    env = make_env(tmp_path)
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    rows = stage_rows(env, "writer_stamp")
    assert [(r["result"], r.get("writer")) for r in rows] == [("ok", "stub-writer-1")]


def test_p3_a_report_without_the_stamp_is_a_reason_not_an_abort(tmp_path: Path):
    env = make_env(tmp_path, report_md=REPORT_MD.replace("; writer: stub-writer-1", ""))
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    rows = stage_rows(env, "writer_stamp")
    assert [(r["result"], r.get("reason")) for r in rows] == [("fail", "REPORT_WRITER_STAMP_MISSING")]
    ends = [e for e in audit_events(env) if e["event"] == "chain_end"]
    assert "REPORT_WRITER_STAMP_MISSING" in ends[-1]["reasons"]


# --- P2-02.6 ------------------------------------------------------------------


def test_p6_a_tool_set_the_cli_resolves_as_declared_runs(tmp_path: Path):
    env = make_env(tmp_path)
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    ends = [e for e in audit_events(env) if e["event"] == "chain_end"]
    assert "PREFLIGHT_TOOLSET" not in ends[-1]["reasons"]


def test_p6_a_dropped_tool_name_aborts_with_the_drift_reason(tmp_path: Path):
    env = make_env(tmp_path, probe_tools="Read Glob Grep Edit Write")  # Skill silently dropped
    proc = run_chain(env)
    assert proc.returncode == 1
    rows = [e for e in audit_events(env) if e.get("stage") == "preflight"]
    assert [(r["result"], r["reason"]) for r in rows] == [("fail", "PREFLIGHT_TOOLSET_DRIFT")]
    assert "missing=Skill" in rows[0]["diff"]
    assert not (Path(env["STUB_STATE"]) / "session_args").exists()  # no session was spent


def test_p6_a_gained_tool_name_also_aborts(tmp_path: Path):
    env = make_env(tmp_path, probe_tools="Read Glob Grep Edit Write Skill Bash")
    proc = run_chain(env)
    assert proc.returncode == 1
    assert "gained=Bash" in [e for e in audit_events(env) if e.get("stage") == "preflight"][0]["diff"]


def test_p6_a_probe_with_no_answer_is_a_reason_not_an_abort(tmp_path: Path):
    env = make_env(tmp_path, probe_tools=None)
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    ends = [e for e in audit_events(env) if e["event"] == "chain_end"]
    assert "PREFLIGHT_TOOLSET_PROBE_FAIL" in ends[-1]["reasons"]


# --- P2-02.7 ------------------------------------------------------------------


def _synthetic_checkout(tmp_path: Path) -> Path:
    """A copy of the chain's scripts in a throwaway git checkout, off main,
    with an uncommitted instruction edit and an untracked skill directory."""
    import shutil

    root = tmp_path / "checkout"
    shutil.copytree(REPO_ROOT / "scripts", root / "scripts")
    for rel in (".claude/skills/weekly-report", "config/prompts"):
        shutil.copytree(REPO_ROOT / rel, root / rel)
    shutil.copy(REPO_ROOT / "CLAUDE.md", root / "CLAUDE.md")

    def git(*a: str) -> None:
        subprocess.run(
            ["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t", *a],
            check=True, capture_output=True,
        )

    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    git("checkout", "-q", "-b", "feature")
    skill = root / ".claude/skills/weekly-report/SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + "\nuncommitted\n", encoding="utf-8")
    (root / ".claude/skills/stray").mkdir()
    (root / ".claude/skills/stray/SKILL.md").write_text("x\n", encoding="utf-8")
    return root


def test_p7_chain_start_carries_the_five_provenance_fields_and_the_drift_warning(tmp_path: Path):
    env = make_env(tmp_path)
    root = _synthetic_checkout(tmp_path)
    proc = subprocess.run(
        ["bash", str(root / "scripts" / "weekly-pipeline.sh"), "--end-date", END_DATE],
        env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stderr
    start = chain_start(env)
    assert start["branch"] == "feature" and int(start["dirty"]) >= 1
    assert len(start["instr_sha12"]) == 12 and start["git_head"] not in ("", "unknown")
    assert "stray:untracked" in start["skills"] and "weekly-report:tracked" in start["skills"]
    assert start["worktree_drift"] == "branch,dirty,untracked_skill"
    assert "PREFLIGHT_WORKTREE_DRIFT" in proc.stderr
    ends = [e for e in audit_events(env) if e["event"] == "chain_end"]
    assert "PREFLIGHT_WORKTREE_DRIFT" in ends[-1]["reasons"]


# --- P2-02.8 ------------------------------------------------------------------

ENVELOPE_OK = {
    "type": "result", "subtype": "success", "is_error": False, "duration_ms": 61000,
    "duration_api_ms": 50000, "num_turns": 14, "result": "SECRET REPORT TEXT",
    "total_cost_usd": 0.5, "permission_denials": [],
    "modelUsage": {"stub-writer-1": {"inputTokens": 1}},
    "usage": {"input_tokens": 10, "output_tokens": 20},
}


def _with_envelope(env: dict, envelope: dict) -> dict:
    (Path(env["STUB_STATE"]) / "envelope").write_text(json.dumps(envelope), encoding="utf-8")
    return env


def _report_row(env: dict) -> dict:
    return stage_rows(env, "report")[-1]


def test_p8_a_normal_envelope_records_the_numbers_and_no_reason(tmp_path: Path):
    env = _with_envelope(make_env(tmp_path), ENVELOPE_OK)
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    row = _report_row(env)
    assert row["result"] == "ok" and "reason" not in row
    assert (row["is_error"], row["denials"], row["num_turns"], row["duration_ms"]) == ("false", "0", "14", "61000")
    assert row["models"] == "stub-writer-1"
    assert "--output-format" in session_argv(env)
    assert session_argv(env)[session_argv(env).index("--output-format") + 1] == "json"
    # The envelope's result text is not kept anywhere in the run's logs.
    run_dir = next((Path(env["MOLTBOOK_HOME"]) / "logs" / "weekly-pipeline").iterdir())
    assert not [p for p in run_dir.rglob("*") if p.is_file() and "SECRET REPORT TEXT" in p.read_text(errors="ignore")]
    assert not list((Path(env["MOLTBOOK_HOME"]) / "reports" / ".private").glob(".session-envelope-*"))


def test_p8_is_error_is_a_failed_report_row_with_its_own_reason(tmp_path: Path):
    env = _with_envelope(make_env(tmp_path), {**ENVELOPE_OK, "is_error": True})
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr  # the stub still wrote a complete report
    row = _report_row(env)
    assert (row["result"], row["reason"]) == ("fail", "REPORT_SESSION_ERROR")


def test_p8_denials_are_a_reason_that_does_not_abort(tmp_path: Path):
    env = _with_envelope(make_env(tmp_path), {**ENVELOPE_OK, "permission_denials": [{"tool_name": "Read"}] * 3})
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    row = _report_row(env)
    assert (row["result"], row["reason"], row["denials"]) == ("ok", "REPORT_SESSION_DENIED", "3")
    ends = [e for e in audit_events(env) if e["event"] == "chain_end"]
    assert "REPORT_SESSION_DENIED" in ends[-1]["reasons"]


def test_p8_a_missing_denials_key_reads_unknown_never_zero(tmp_path: Path):
    envelope = {k: v for k, v in ENVELOPE_OK.items() if k != "permission_denials"}
    env = _with_envelope(make_env(tmp_path), envelope)
    run_chain(env)
    assert _report_row(env)["denials"] == "unknown"


def test_p8_an_unreadable_envelope_is_named(tmp_path: Path):
    env = make_env(tmp_path)
    (Path(env["STUB_STATE"]) / "envelope").write_text("not json at all", encoding="utf-8")
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    ends = [e for e in audit_events(env) if e["event"] == "chain_end"]
    assert "REPORT_SESSION_ENVELOPE_UNREADABLE" in ends[-1]["reasons"]


# --- P2-02.9 ------------------------------------------------------------------


def test_p9_the_session_sees_only_the_allowlisted_environment(tmp_path: Path):
    env = make_env(tmp_path)
    env["ANTHROPIC_API_KEY"] = "leak-1"
    env["CLAUDE_CODE_EFFORT"] = "leak-2"
    env["PIPELINE_WEEKLY_TIMEOUT"] = "600"
    proc = run_chain(env)
    assert proc.returncode == 0, proc.stderr
    seen = dict(
        line.split("=", 1)
        for line in (Path(env["STUB_STATE"]) / "session_env").read_text(encoding="utf-8").splitlines()
        if "=" in line
    )
    assert "ANTHROPIC_API_KEY" not in seen and "CLAUDE_CODE_EFFORT" not in seen
    assert "PIPELINE_WEEKLY_TIMEOUT" not in seen
    assert seen["DISABLE_AUTOUPDATER"] == "1"
    assert seen["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] == "1"
    assert seen["MOLTBOOK_HOME"] == env["MOLTBOOK_HOME"]
    assert seen["HOME"] == env["HOME"] and "PATH" in seen
