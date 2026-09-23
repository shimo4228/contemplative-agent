"""Absence guards for the RFC-0043 Jev arm.

The arm's client (``evals/jev_arm.py``) and the harness it fed were removed
once RFC-0043's consumption plan expired; ``docs/evidence/rfc-0043/README.md``
names the commit to restore them from. What outlives the client is what the
client was never the point of: the private rows it wrote still sit in the
gitignored ``.notes/`` tree, and the public tree must still not carry them.

Three properties, all of them *absences* — the kind nothing else notices
breaking, because the tree still compiles and every other test still passes:

1. **No Jev number reaches the public tree.** The TypeSafe Master Customer
   Agreement (2026-08-27, read 2026-09-20) lists "publish benchmarks or
   performance information about the Services" among customer restrictions,
   2.3(f). The arm labels are the handle the numbers travel under, so their
   absence from ``docs/`` AND ``rfcs/`` is what is checked, together with the
   ``.notes/`` tree the rows were written to staying gitignored. Prose
   about the run is fine and is meant to be written — "we ran it, the agreement
   keeps the numbers private" carries no label and no number.
2. **The hosted endpoint stays out of the shipped package and the schedules.**
   ``tests/test_cloud_egress_absence.py`` keeps ``claude -p`` out of ``src/``
   and ``scripts/``; this keeps ``api.typesafe.ai`` out of the same tree. A
   hosted judgment call reachable from the unattended loop would end
   security-by-absence just as surely as a cloud generation backend would.
3. **Nothing production-side imports the arm.** It was an operator-run
   one-shot; if it is ever restored, an import from ``src/`` or ``scripts/``
   would make it reachable from the schedules even if no call site were visible.

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

# The handles the private numbers travel under in the row log. A public file
# carrying one of these is either a number or a pointer to where they live.
PRIVATE_ARM_MARKERS = ("J1/jev", "J2/jev", "jev/noul", "jev/choice")

# Every tracked tree a reader outside this machine can see. `rfcs/` is here
# because it is the public task ledger and is exactly where the round-2 write-up
# lands — the guard scanning only `docs/` would have watched the wrong door.
PUBLIC_DIRS = ("docs", "rfcs")
PUBLIC_SUFFIXES = ("*.json", "*.md")


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for name in SCANNED_DIRS:
        root = REPO_ROOT / name
        assert root.is_dir(), f"expected {root} to exist"
        files.extend(sorted(root.rglob("*.py")))
    assert files, "scan found no files — the globs are wrong, not the repo"
    return files


def _public_files() -> list[Path]:
    files: list[Path] = []
    for name in PUBLIC_DIRS:
        root = REPO_ROOT / name
        assert root.is_dir(), f"{root} is a public tree this guard is about"
        files.extend(path for suffix in PUBLIC_SUFFIXES for path in sorted(root.rglob(suffix)))
    assert files, "scan found no public files — the globs are wrong, not the repo"
    return files


class TestJevNumbersStayPrivate:
    def test_no_public_file_carries_a_jev_arm_label(self):
        """MCA 2.3(f). Saying a run happened is fine; carrying its numbers is not."""
        offenders = [
            f"{path.relative_to(REPO_ROOT)}:{i} ({marker})"
            for path in _public_files()
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
            for marker in PRIVATE_ARM_MARKERS
            if marker in line
        ]
        assert not offenders, (
            "a Jev arm label reached the public tree (TypeSafe MCA 2.3(f) keeps the "
            "numbers private): " + ", ".join(offenders)
        )

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
