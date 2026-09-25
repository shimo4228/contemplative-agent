"""Absence guards around the Jev arm client (``evals/jev_arm.py``).

The client is an operator-run one-shot (RFC-0043 round 2, RFC-0045). Three
properties, all of them *absences* — the kind nothing else notices breaking,
because the tree still compiles and every other test still passes:

1. **The row logs stay out of the public tree.** The rows the client writes
   carry other agents' post bodies (untrusted content) and the decoded
   prompts, so they live under the gitignored ``.notes/`` tree — that is what
   ``assert_private_output`` enforces on the writer's side, and this file pins
   that ``.notes/`` is still gitignored. (Until 2026-09-25 a label scan over
   ``docs/`` and ``rfcs/`` also kept the arm's *numbers* out of the public tree,
   on the strength of TypeSafe MCA 2.3(f); that clause left the agreement on
   2026-09-19 — RFC-0040 records the check — and the scan was retired on the
   owner's decision. Numbers may be published; bodies still may not.)
2. **The hosted endpoint stays out of the shipped package and the schedules.**
   ``tests/test_cloud_egress_absence.py`` keeps ``claude -p`` out of ``src/``
   and ``scripts/``; this keeps ``api.typesafe.ai`` out of the same tree. A
   hosted judgment call reachable from the unattended loop would end
   security-by-absence just as surely as a cloud generation backend would.
3. **Nothing production-side imports the arm.** An import from ``src/`` or
   ``scripts/`` would make it reachable from the schedules even if no call site
   were visible.

Scanning source text rather than asserting on imports for (2) is deliberate,
and is the same reasoning ``test_cloud_egress_absence.py`` states: an
import-based check passes the moment a module is present but unreferenced.
"""

from __future__ import annotations

import ast
from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("repo root (pyproject.toml) not found above this file")


REPO_ROOT = _repo_root()

# The shipped package and the Python the schedules run — the same tree
# test_cloud_egress_absence.py guards, for the same reason.
SCANNED_DIRS = ("src", "scripts")

# The hosted destination. Spelled here, nowhere else in the tree.
TYPESAFE_HOST = "api.typesafe.ai"


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for name in SCANNED_DIRS:
        root = REPO_ROOT / name
        assert root.is_dir(), f"expected {root} to exist"
        files.extend(sorted(root.rglob("*.py")))
    assert files, "scan found no files — the globs are wrong, not the repo"
    return files


class TestJevRowsStayPrivate:
    def test_notes_is_gitignored(self):
        """The private rows live under .notes/; that is only private while it is untracked."""
        ignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        assert ".notes/" in [line.strip() for line in ignore]


class TestNoHostedEgressFromTheShippedTree:
    def test_the_typesafe_endpoint_is_absent_from_src_and_scripts(self):
        offenders = [
            f"{path.relative_to(REPO_ROOT)}:{i}"
            for path in _scanned_files()
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            if TYPESAFE_HOST in line
        ]
        assert not offenders, (
            f"{TYPESAFE_HOST} reached the shipped package or the scheduled Python — a hosted "
            "judgment call belongs in evals/, as an operator-run one-shot: " + ", ".join(offenders)
        )

    def test_nothing_in_src_or_scripts_imports_the_arm(self):
        offenders: list[str] = []
        for path in _scanned_files():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = {f"{node.module}.{alias.name}" for alias in node.names} | {node.module}
                else:
                    continue
                if any(name.endswith("jev_arm") for name in names):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{node.lineno}")
        assert not offenders, (
            "the Jev arm is reachable from the shipped package or the schedules: "
            + ", ".join(offenders)
        )
