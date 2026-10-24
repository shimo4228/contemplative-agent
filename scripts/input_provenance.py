#!/usr/bin/env python3
"""Provenance of the instructions an unattended session reads (P2-02.7).

The weekly chain runs its headless claude session in the SAME checkout the owner's interactive
sessions edit, and the instruction files (weekly-report skill, CLAUDE.md, the
analysis prompt) change most weeks. This prints, as `key=value` lines or as
`--field key=value` arguments, what the session was handed:

  chain:  git_head, branch, dirty, instr_sha12, skills, drift
  gate:   git_head, gate_sha12            (weekly-gate's own SKILL.md)

`drift` is a comma list of why the checkout is not a clean `main`:
`branch` (not main), `dirty` (uncommitted changes under the instruction
paths), `untracked_skill` (a project skill directory git does not track —
including one the repo ignores). Empty = clean. The caller turns a non-empty
`drift` into the WARNING `PREFLIGHT_WORKTREE_DRIFT`; nothing here aborts —
a missing week costs more than a week written from an odd checkout.

Read-only; stdlib + git. Consumption plan (ADR-0101): (a) the Saturday gate's
Step 0 reader looks for the WARNING each week, and the longitudinal reading
(regime table) takes weeks where `instr_sha12` changes as split points;
(b) one WARNING marks "that week's document was written from a non-main /
uncommitted instruction set" and decides whether to re-run (runbook
docs/runbooks/weekly-chain-rerun.md); (c) retire the field when the headless
session stops (ADR-0080 amendment 2026-10-24, D-P2-02-1 = A); past rows stay.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

INSTRUCTION_FILES = (
    ".claude/skills/weekly-report/SKILL.md",
    ".claude/skills/weekly-report/references/diagnosis.md",
    "CLAUDE.md",
    "config/prompts/weekly-analysis.md",
)
DIRTY_PATHS = ("scripts/", ".claude/skills/weekly-report/", "config/prompts/", "CLAUDE.md")


def _git(root: Path, *args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout if out.returncode == 0 else None


def sha12(root: Path, files: tuple[str, ...]) -> str:
    h = hashlib.sha256()
    for rel in files:
        path = root / rel
        h.update(path.read_bytes() if path.is_file() else b"<absent>")
        h.update(b"\0")
    return h.hexdigest()[:12]


def git_head(root: Path) -> str:
    return (_git(root, "rev-parse", "--short", "HEAD") or "unknown").strip()


def chain_fields(root: Path) -> dict[str, str]:
    branch = (_git(root, "rev-parse", "--abbrev-ref", "HEAD") or "unknown").strip()
    status = _git(root, "status", "--porcelain", "--", *DIRTY_PATHS)
    dirty = len([ln for ln in (status or "").splitlines() if ln.strip()])
    tracked = set((_git(root, "ls-files", ".claude/skills") or "").splitlines())
    skills = []
    skills_dir = root / ".claude" / "skills"
    for d in sorted(p for p in skills_dir.iterdir() if p.is_dir()) if skills_dir.is_dir() else []:
        is_tracked = any(t.startswith(f".claude/skills/{d.name}/") for t in tracked)
        skills.append(f"{d.name}:{'tracked' if is_tracked else 'untracked'}")
    drift = []
    if branch != "main":
        drift.append("branch")
    if dirty > 0:
        drift.append("dirty")
    if any(s.endswith(":untracked") for s in skills):
        drift.append("untracked_skill")
    return {
        "git_head": git_head(root),
        "branch": branch,
        "dirty": str(dirty),
        "instr_sha12": sha12(root, INSTRUCTION_FILES),
        "skills": ",".join(skills) or "none",
        "drift": ",".join(drift),
    }


def gate_fields(root: Path) -> dict[str, str]:
    return {
        "git_head": git_head(root),
        "gate_sha12": sha12(root, (".claude/skills/weekly-gate/SKILL.md",)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("chain", "gate"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--as-fields", action="store_true", help="print `--field k=v` arguments on one line"
    )
    args = parser.parse_args()
    fields = (chain_fields if args.kind == "chain" else gate_fields)(args.root)
    if args.as_fields:
        print(" ".join(f"--field {k}={v}" for k, v in fields.items() if v != ""))
    else:
        for k, v in fields.items():
            print(f"{k}={v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
