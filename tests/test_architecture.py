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


# --- underscore-name crossings (P1-06.3) -------------------------------------
# scripts/ is outside import-linter's ``root_packages``, so a script that
# imports a private name of ``contemplative_agent`` is invisible to the layer
# contracts. This AST check closes that for scripts/ and evals/: an
# import of a ``_``-prefixed name from the package is a rename waiting to break
# it. ``core.llm`` is closed (P1-06.3, 2026-10-24): none may appear. The pins
# below are the crossings into OTHER modules that existed that day; they are
# neither drained nor extended — a new one is a failing test, and renaming a
# pinned name means removing its pin in the same change.
_UNDERSCORE_IMPORT_PINS: frozenset[tuple[str, str, str]] = frozenset(
    {
        (
            "scripts/injection_ablation_replay.py",
            "contemplative_agent.adapters.moltbook.llm_functions",
            "_selection_system",
        ),
        (
            "scripts/injection_ablation_replay.py",
            "contemplative_agent.core.embeddings",
            "_get_embedding_model",
        ),
        (
            "scripts/injection_ablation_replay.py",
            "contemplative_agent.core.skill_selection",
            "_catalog_key",
        ),
        (
            "scripts/novelty_replay_ab.py",
            "contemplative_agent.core.embeddings",
            "_get_embedding_model",
        ),
        (
            "scripts/novelty_replay_ab.py",
            "contemplative_agent.core.insight_novelty",
            "_NOVELTY_TEMPERATURE",
        ),
        ("scripts/novelty_replay_ab.py", "contemplative_agent.core.insight_novelty", "_known_doc"),
        (
            "scripts/novelty_replay_ab.py",
            "contemplative_agent.core.insight_novelty",
            "_parse_covered_ids",
        ),
        (
            "scripts/novelty_replay_ab.py",
            "contemplative_agent.core.insight_novelty",
            "_render_known_lines",
        ),
        (
            "scripts/novelty_retrieval_dry_run.py",
            "contemplative_agent.core.embeddings",
            "_get_embedding_model",
        ),
        (
            "scripts/retrieval_recall_measure.py",
            "contemplative_agent.core.embeddings",
            "_get_embedding_model",
        ),
        (
            "scripts/skillsel_arm_replay.py",
            "contemplative_agent.core.selection_window",
            "_NAME_MAX_CHARS",
        ),
        (
            "scripts/skillsel_arm_replay.py",
            "contemplative_agent.core.skill_selection",
            "_NONE_SENTINEL",
        ),
        (
            "scripts/skillsel_arm_replay.py",
            "contemplative_agent.core.skill_selection",
            "_SELECTION_NUM_PREDICT",
        ),
        (
            "scripts/skillsel_arm_replay.py",
            "contemplative_agent.core.skill_selection",
            "_render_catalog",
        ),
        (
            "scripts/submolt_scope_stability.py",
            "contemplative_agent.adapters.moltbook.submolt_scope",
            "_is_judged",
        ),
    }
)


def _underscore_imports_of_the_package() -> set[tuple[str, str, str]]:
    import ast

    found: set[tuple[str, str, str]] = set()
    for top in ("scripts", "evals"):
        for path in sorted((PROJECT_ROOT / top).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ImportFrom)
                    and node.level == 0
                    and node.module is not None
                    and (
                        node.module == "contemplative_agent"
                        or node.module.startswith("contemplative_agent.")
                    )
                ):
                    for alias in node.names:
                        if alias.name.startswith("_"):
                            rel = path.relative_to(PROJECT_ROOT).as_posix()
                            found.add((rel, node.module, alias.name))
    return found


@pytest.mark.unit
def test_scripts_and_evals_import_no_new_private_names_of_the_package() -> None:
    found = _underscore_imports_of_the_package()
    assert found == set(_UNDERSCORE_IMPORT_PINS)
    assert not [t for t in found if t[1].startswith("contemplative_agent.core.llm")]


@pytest.mark.unit
def test_llm_facade_declares_all_and_reexports_no_underscore_name() -> None:
    import contemplative_agent.core.llm as llm

    assert llm.__all__
    assert all(not name.startswith("_") for name in llm.__all__)
    assert all(hasattr(llm, name) for name in llm.__all__)
    facade = (PROJECT_ROOT / "src/contemplative_agent/core/llm/__init__.py").read_text(
        encoding="utf-8"
    )
    import re

    assert not re.search(r"^\s+(_\w+) as \1,?$", facade, re.M)
