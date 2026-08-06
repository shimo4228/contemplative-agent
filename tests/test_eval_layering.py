"""Machine-enforce the ADR-0089 layering contract.

Decision 2: only evals/adapter_deepeval.py and evals/run_eval.py may import
deepeval; the deterministic core must stay importable under the dev group.
import-linter cannot see evals/ (root_packages=["contemplative_agent"]) and
the shared venv usually HAS deepeval installed via the type gate, so an
accidental import would pass every other gate — this AST check is the only
thing that makes the invariant real.
"""

from __future__ import annotations

import ast
from pathlib import Path

EVALS_DIR = Path(__file__).resolve().parent.parent / "evals"
DETERMINISTIC_CORE = ("dataset.py", "judging.py", "generation.py", "compare.py")
FORBIDDEN_ROOT = "deepeval"


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_deterministic_core_never_imports_deepeval():
    for name in DETERMINISTIC_CORE:
        roots = _imported_roots(EVALS_DIR / name)
        assert FORBIDDEN_ROOT not in roots, f"evals/{name} imports deepeval"


def test_deterministic_core_files_exist():
    # Guard the guard: a rename must update DETERMINISTIC_CORE, not silently
    # shrink the checked set.
    for name in DETERMINISTIC_CORE:
        assert (EVALS_DIR / name).is_file(), f"evals/{name} missing"
