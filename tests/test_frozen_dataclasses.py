"""Immutability gate: every dataclass in src/ must be ``frozen=True``.

The project rule is "DTOs and domain objects are frozen, no exceptions" —
this gate turns that into a machine-readable form: the only exceptions are
the ones listed (with a reason) in ``ALLOWED_MUTABLE``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

# path (relative to repo root) :: class name -> reason the class may be mutable.
ALLOWED_MUTABLE = {
    # Private per-call accumulator internal to compute_metrics; never escapes
    # the function, documented as mutable in its docstring.
    "src/contemplative_agent/core/metrics.py::_Tally",
    # Same shape as _Tally: a private per-catalog_count accumulator internal
    # to read_skill_selection_log, frozen into CatalogRegime before it
    # leaves the function; never escapes mutable.
    "src/contemplative_agent/core/selection_metrics.py::_RegimeAccumulator",
    # Same shape again: the window-wide collections _scan_selection_day folds
    # each day into, internal to read_skill_selection_log and handed to the
    # frozen _WindowTally before they leave. They live in one object rather
    # than seven parameters — carrying them individually is what made the
    # scanner an eight-argument function (2026-08-31).
    "src/contemplative_agent/core/selection_metrics.py::_WindowCollections",
}


def _is_dataclass_decorator(node: ast.expr) -> bool:
    """Match ``@dataclass`` / ``@dataclasses.dataclass``, bare or called."""
    target = node.func if isinstance(node, ast.Call) else node
    if isinstance(target, ast.Name):
        return target.id == "dataclass"
    if isinstance(target, ast.Attribute):
        return target.attr == "dataclass"
    return False


def _has_frozen_true(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    return any(
        kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True
        for kw in node.keywords
    )


@pytest.mark.unit
def test_all_src_dataclasses_are_frozen() -> None:
    violations: list[str] = []
    for py in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        rel = py.relative_to(PROJECT_ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            decorators = [d for d in node.decorator_list if _is_dataclass_decorator(d)]
            if not decorators:
                continue
            if any(_has_frozen_true(d) for d in decorators):
                continue
            key = f"{rel}::{node.name}"
            if key in ALLOWED_MUTABLE:
                continue
            violations.append(f"{rel}:{node.lineno} {node.name}")
    assert not violations, (
        "Non-frozen dataclass in src/ — use @dataclass(frozen=True), or add "
        "the class to ALLOWED_MUTABLE with a reason if mutability is genuinely "
        "required:\n" + "\n".join(violations)
    )


@pytest.mark.unit
def test_allowlist_entries_still_exist() -> None:
    """A stale allowlist entry means the exception is gone — remove it."""
    stale: list[str] = []
    for entry in sorted(ALLOWED_MUTABLE):
        rel, class_name = entry.split("::")
        path = PROJECT_ROOT / rel
        if not path.exists():
            stale.append(f"{entry} (file missing)")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        if class_name not in names:
            stale.append(f"{entry} (class missing)")
    assert not stale, "Stale ALLOWED_MUTABLE entries:\n" + "\n".join(stale)
