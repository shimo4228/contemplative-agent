"""input_provenance.py (P2-02.7): what the unattended session's instructions are made of."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "input_provenance",
    Path(__file__).resolve().parent.parent / "scripts" / "input_provenance.py",
)
assert _SPEC is not None and _SPEC.loader is not None
ip = importlib.util.module_from_spec(_SPEC)
sys.modules["input_provenance"] = ip
_SPEC.loader.exec_module(ip)


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), "-c", "user.email=t@example.invalid", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


def _checkout(root: Path) -> None:
    for rel, body in {
        ".claude/skills/weekly-report/SKILL.md": "skill\n",
        ".claude/skills/weekly-report/references/diagnosis.md": "diag\n",
        ".claude/skills/weekly-gate/SKILL.md": "gate\n",
        "CLAUDE.md": "claude\n",
        "config/prompts/weekly-analysis.md": "prompt\n",
        "scripts/x.sh": "echo\n",
    }.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")


def test_a_clean_main_checkout_has_no_drift(tmp_path: Path):
    _checkout(tmp_path)
    f = ip.chain_fields(tmp_path)
    assert f["drift"] == "" and f["dirty"] == "0" and f["branch"] == "main"
    assert len(f["instr_sha12"]) == 12 and f["git_head"] != "unknown"
    assert f["skills"] == "weekly-gate:tracked,weekly-report:tracked"


def test_feature_branch_uncommitted_instruction_and_untracked_skill_each_show(tmp_path: Path):
    _checkout(tmp_path)
    clean = ip.chain_fields(tmp_path)["instr_sha12"]
    _git(tmp_path, "checkout", "-q", "-b", "feature")
    (tmp_path / ".claude/skills/weekly-report/SKILL.md").write_text("edited\n", encoding="utf-8")
    (tmp_path / ".claude/skills/private-skill").mkdir()
    (tmp_path / ".claude/skills/private-skill/SKILL.md").write_text("x\n", encoding="utf-8")
    f = ip.chain_fields(tmp_path)
    assert f["drift"] == "branch,dirty,untracked_skill"
    assert f["dirty"] == "1"
    assert "private-skill:untracked" in f["skills"]
    assert f["instr_sha12"] != clean  # the digest moves with the instruction text


def test_an_ignored_skill_directory_still_counts_as_untracked(tmp_path: Path):
    _checkout(tmp_path)
    (tmp_path / ".gitignore").write_text(".claude/skills/hidden/\n", encoding="utf-8")
    (tmp_path / ".claude/skills/hidden").mkdir()
    (tmp_path / ".claude/skills/hidden/SKILL.md").write_text("x\n", encoding="utf-8")
    assert "untracked_skill" in ip.chain_fields(tmp_path)["drift"]


def test_gate_fields_carry_the_gate_skill_digest(tmp_path: Path):
    _checkout(tmp_path)
    before = ip.gate_fields(tmp_path)
    (tmp_path / ".claude/skills/weekly-gate/SKILL.md").write_text("changed\n", encoding="utf-8")
    after = ip.gate_fields(tmp_path)
    assert before["git_head"] == after["git_head"] and before["gate_sha12"] != after["gate_sha12"]
