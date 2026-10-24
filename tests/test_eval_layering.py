"""Machine-enforce the ADR-0089 layering contract.

Decision 2 held that only a wiring layer may import deepeval; the dependency
was dropped on 2026-10-24 (P1-04.12), so the invariant is now that **no** module
under evals/ imports it. import-linter cannot see evals/
(root_packages=["contemplative_agent"]) and a stray venv may still carry the
package, so an accidental import would pass every other gate — this AST check
is what makes the invariant real.
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


def test_no_evals_module_imports_deepeval():
    modules = sorted(EVALS_DIR.rglob("*.py"))
    assert modules, "evals/ has no modules — wrong path?"
    for path in modules:
        roots = _imported_roots(path)
        assert FORBIDDEN_ROOT not in roots, f"{path.relative_to(EVALS_DIR)} imports deepeval"
        assert not path.name.startswith("adapter_deepeval")


def test_eval_dependency_group_is_gone():
    import tomllib

    pyproject = EVALS_DIR.parent / "pyproject.toml"
    groups = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("dependency-groups", {})
    assert "eval" not in groups
    assert "deepeval" not in pyproject.read_text(encoding="utf-8").lower()


def test_deterministic_core_files_exist():
    # Guard the guard: a rename must update DETERMINISTIC_CORE, not silently
    # shrink the checked set.
    for name in DETERMINISTIC_CORE:
        assert (EVALS_DIR / name).is_file(), f"evals/{name} missing"
