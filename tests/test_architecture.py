"""Architecture gate: enforce ADR-0001 import direction via import-linter.

Runs the ``lint-imports`` CLI (contracts defined in ``pyproject.toml``,
``[tool.importlinter]``) so that every pytest run also verifies the
one-way dependency rule cli -> adapters -> core.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _lint_imports_executable() -> Path:
    # import-linter has no ``python -m`` entry point; resolve the console
    # script from the same environment as the running interpreter.
    return Path(sys.executable).parent / "lint-imports"


@pytest.mark.unit
def test_import_direction_contract() -> None:
    executable = _lint_imports_executable()
    if not executable.exists():
        pytest.fail(f"lint-imports not found at {executable}; install dev dependencies (uv sync)")

    result = subprocess.run(
        [str(executable)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "import-linter contract broken (see pyproject.toml "
        "[tool.importlinter] for the fix policy):\n"
        f"{result.stdout}\n{result.stderr}"
    )
