"""Fault column for weekly-pipeline.sh stage 7c (confusion pairs + candidates, ADR-0105).

The stage writes three artifacts and must never write a fourth: the store is
read-only to the whole unattended chain, and the one thing an exit reading
could get catastrophically wrong is moving a skill file itself.

- C-1  a healthy week → per-week JSON + candidate file + a findings section,
       audited ok, and the skill store byte-identical afterwards
- C-2  the reading dies → CONFUSION_READING_FAILED and **neither** artifact
       left behind (a JSON without its candidate file reads at the gate as a
       complete reading with an empty half)
- C-3  stage 7b left no never-selected JSON → the reading still lands, its
       reasons name the missing half rather than reading as "nothing to list"
- C-4  the stage is not behind MOLTBOOK_PIPELINE_STAGES — a stage selection
       that silently skipped it would produce a week reading "no candidates"
       instead of "not read" (7b's reason, restated here)

macOS-only marker matches the sibling pipeline shell tests (BSD stat/date).
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin", reason="weekly-pipeline.sh uses BSD stat/date"
)

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "weekly-pipeline.sh"

LIVE_END_DATE = (datetime.now().astimezone() - timedelta(days=1)).strftime("%Y-%m-%d")

CLAUDE_STUB = "#!/bin/bash\nexit 0\n"

# Forward every `uv run ... python ...` to the real interpreter with the repo
# on PYTHONPATH, so stages 7b and 7c run their actual code; anything else the
# chain asks of uv is a no-op. `confusion_fail` makes 7c die the way a
# timeout or an import error would.
UV_STUB = """#!/bin/bash
if [[ "$*" == *confusion_pair_reading.py* && -f "$STUB_STATE/confusion_fail" ]]; then
  echo "boom" >&2
  exit 2
fi
if [[ "$*" == *never_selected_metrics* && -f "$STUB_STATE/neversel_fail" ]]; then
  echo "boom" >&2
  exit 2
fi
args=()
seen=0
for a in "$@"; do
  if [[ $seen == 1 ]]; then args+=("$a"); fi
  if [[ "$a" == python ]]; then seen=1; fi
done
if [[ $seen == 1 ]]; then
  exec "$REAL_PYTHON" "${args[@]}"
fi
exit 0
"""

COMPLETE_REPORT = "# Weekly Observation\n\n## Inventory\n\nbody\n"
COMPLETE_FINDINGS = (
    "# Weekly Diagnosis\n\n## F1. Structural\n\nnone\n\n## Diagnosis Metadata\n\n- read: x\n"
)

CATALOG = {
    "scope-boundary-mapping": "Map the scope of a boundary before arguing about it.",
    "internal-process-audit": "Audit the internal process that produced a claim.",
}


def _write_exec(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _record(selected: list[str], rejected: list[str]) -> str:
    return json.dumps(
        {
            "verdict": "judged",
            "catalog_names": list(CATALOG),
            "selected": selected,
            "rejected_names": rejected,
            "full_skill_tokens": 4000,
        }
    )


def _make_env(tmp_path: Path, *, stub_marker: str | None = None) -> dict:
    home = tmp_path / "moltbook"
    analysis = home / "reports" / "analysis"
    analysis.mkdir(parents=True)
    (home / "logs").mkdir(parents=True)
    (home / ".staged").mkdir(parents=True)
    skills = home / "skills"
    skills.mkdir(parents=True)
    for index, (name, description) in enumerate(CATALOG.items()):
        (skills / f"{name}-2026080{index + 1}.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\nbody\n", encoding="utf-8"
        )
    (home / "knowledge.json").write_text("[]", encoding="utf-8")

    (analysis / f"weekly-{LIVE_END_DATE}.md").write_text(COMPLETE_REPORT, encoding="utf-8")
    (analysis / f"weekly-{LIVE_END_DATE}-findings.md").write_text(
        COMPLETE_FINDINGS, encoding="utf-8"
    )

    # A log with enough judged exposures to clear the 600 floor, and one
    # entry the reader misnames more often than it chooses it.
    day = home / "logs" / f"skill-selection-{LIVE_END_DATE}.jsonl"
    lines = [_record(["internal-process-audit"], []) for _ in range(700)]
    lines += [_record([], ["scope-boundary-mappings"]) for _ in range(4)]
    day.write_text("\n".join(lines) + "\n", encoding="utf-8")

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
    env["REAL_PYTHON"] = sys.executable
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    # A stage name no stage answers to: everything behind `stage_enabled` is
    # skipped, so what runs is exactly the ungated 7b / 7c pair.
    env["MOLTBOOK_PIPELINE_STAGES"] = "none"
    return env


def _run(env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--skip-report", "--end-date", LIVE_END_DATE],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


def _home(env: dict) -> Path:
    return Path(env["MOLTBOOK_HOME"])


def _confusion_json(env: dict) -> Path:
    return _home(env) / "pipeline" / "confusion-pairs" / f"confusion-pairs-{LIVE_END_DATE}.json"


def _candidates(env: dict) -> Path:
    return _home(env) / "reports" / "analysis" / f"weekly-{LIVE_END_DATE}-archive-candidates.txt"


def _findings(env: dict) -> Path:
    return _home(env) / "reports" / "analysis" / f"weekly-{LIVE_END_DATE}-findings.md"


def _audit_events(env: dict) -> list[dict]:
    audit = _home(env) / "logs" / "weekly-pipeline-audit.jsonl"
    return [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]


def _stage_events(env: dict, stage: str) -> list[dict]:
    return [
        e
        for e in _audit_events(env)
        if e.get("event") == "stage_result" and e.get("stage") == stage
    ]


def _chain_reasons(env: dict) -> str:
    ends = [e for e in _audit_events(env) if e.get("event") == "chain_end"]
    assert ends, "chain_end event missing"
    return ends[-1].get("reasons", "")


def _store_digest(env: dict) -> str:
    """A hash of every skill file's name and bytes."""
    skills = sorted((_home(env) / "skills").glob("*.md"))
    digest = hashlib.sha256()
    for path in skills:
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_c1_a_healthy_week_writes_the_reading_and_leaves_the_store_alone(tmp_path: Path):
    env = _make_env(tmp_path)
    before = _store_digest(env)
    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert [e["result"] for e in _stage_events(env, "confusion")] == ["ok"]
    payload = json.loads(_confusion_json(env).read_text(encoding="utf-8"))
    assert payload["exposure_floor"] == 600
    assert [p["confused"]["name"] for p in payload["pairs"]] == ["scope-boundary-mapping"]
    assert payload["candidates"] == ["scope-boundary-mapping-20260801.md"]

    # The candidate file is exactly what `--archive-names` parses: one store
    # filename per line, nothing else.
    lines = _candidates(env).read_text(encoding="utf-8").splitlines()
    assert lines == ["scope-boundary-mapping-20260801.md"]

    assert "## Skill store exit candidates" in _findings(env).read_text(encoding="utf-8")
    assert _store_digest(env) == before
    assert not (_home(env) / "skills" / ".archive").exists()


def test_c2_a_failed_reading_is_a_reason_code_and_leaves_no_half_week(tmp_path: Path):
    env = _make_env(tmp_path, stub_marker="confusion_fail")
    before = _store_digest(env)
    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert [e["result"] for e in _stage_events(env, "confusion")] == ["fail"]
    assert "CONFUSION_READING_FAILED" in _chain_reasons(env)
    assert not _confusion_json(env).exists()
    assert not _candidates(env).exists()
    assert "## Skill store exit candidates" not in _findings(env).read_text(encoding="utf-8")
    assert _store_digest(env) == before


def test_c3_a_missing_never_selected_json_is_named_not_read_as_empty(tmp_path: Path):
    env = _make_env(tmp_path, stub_marker="neversel_fail")
    ns_json = _home(env) / "pipeline" / "never-selected" / f"never-selected-{LIVE_END_DATE}.json"
    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert not ns_json.exists()
    assert "NEVER_SELECTED_SCAN_FAIL" in _chain_reasons(env)
    payload = json.loads(_confusion_json(env).read_text(encoding="utf-8"))
    assert "CONFUSION_NEVER_SELECTED_MISSING" in payload["reasons"]
    assert payload["never_selected_strict"] == []
    # The confusion half still lands, and the candidate file carries only it.
    assert payload["candidates"] == ["scope-boundary-mapping-20260801.md"]
    # ...and the findings document says so, rather than rendering "0 name(s)"
    # like a week that had none. This is the surface a human archives from.
    findings = _findings(env).read_text(encoding="utf-8")
    assert "CONFUSION_NEVER_SELECTED_MISSING" in findings
    assert "WITHHELD, this half of the union is not in the file" in findings


def test_c4_the_stage_runs_even_when_no_stage_name_selects_it(tmp_path: Path):
    """MOLTBOOK_PIPELINE_STAGES=none is what every test here runs under; this
    one states the claim rather than relying on it."""
    env = _make_env(tmp_path)
    assert env["MOLTBOOK_PIPELINE_STAGES"] == "none"
    result = _run(env)

    assert result.returncode == 0, result.stderr
    assert _stage_events(env, "confusion"), "stage 7c did not run"
    # ...and the gated neighbours did not.
    assert [e["result"] for e in _stage_events(env, "deadcode")] == ["skipped"]
