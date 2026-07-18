"""Warning-only drift check: INDEX.md Statistics vs live measurements.

Recomputes the machine-checkable rows of ``docs/CODEMAPS/INDEX.md#statistics``
the same way the doc's "Measured by" line prescribes, and emits a
``UserWarning`` per drifted row. The test itself always passes: detection is
code, the update decision stays human (AKC Maintain). Refresh the table (and
its "As of" date) when a warning fires.

Rows with an ambiguous counting convention (e.g. "Core modules ... incl.
``llm/`` package as one row") are deliberately not checked.
"""

from __future__ import annotations

import re
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_MD = PROJECT_ROOT / "docs" / "CODEMAPS" / "INDEX.md"
LOC_DRIFT_THRESHOLD = 0.10  # LOC is documented as approximate ("~")


def _documented(pattern: str, text: str) -> int | None:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else None


def _count_py(root: Path, *, exclude_init: bool = False) -> int:
    files = [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]
    if exclude_init:
        files = [p for p in files if p.name != "__init__.py"]
    return len(files)


def _collected_test_count() -> int | None:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=300,
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    return int(match.group(1)) if match else None


@pytest.mark.unit
def test_index_statistics_match_reality_warning_only() -> None:
    text = INDEX_MD.read_text(encoding="utf-8")
    src = PROJECT_ROOT / "src"
    adapters = src / "contemplative_agent" / "adapters"
    drift: list[str] = []

    def check(label: str, documented: int | None, measured: int | None) -> None:
        if documented is None:
            drift.append(f"{label}: could not parse documented value from INDEX.md")
        elif measured is None:
            drift.append(f"{label}: could not measure live value")
        elif documented != measured:
            drift.append(f"{label}: documented {documented}, measured {measured}")

    check(
        "Total .py files",
        _documented(r"\| Total `\.py` files \| (\d+)", text),
        _count_py(src),
    )
    check(
        "Test files",
        _documented(r"\| Test files \| (\d+)", text),
        len(list((PROJECT_ROOT / "tests").glob("test_*.py"))),
    )
    check(
        "Tests collected",
        _documented(r"\((\d+) tests collected\)", text),
        _collected_test_count(),
    )
    for label, pkg, pattern in (
        (
            "Moltbook adapter modules",
            adapters / "moltbook",
            r"\| Moltbook adapter modules \| (\d+)",
        ),
        (
            "Meditation adapter modules",
            adapters / "meditation",
            r"\| Meditation adapter modules \| (\d+)",
        ),
        (
            "Dialogue adapter modules",
            adapters / "dialogue",
            r"\| Dialogue adapter modules \| (\d+)",
        ),
        (
            "CLI package modules",
            src / "contemplative_agent" / "cli",
            r"\| CLI package modules \| (\d+)",
        ),
    ):
        check(label, _documented(pattern, text), _count_py(pkg, exclude_init=True))
    check(
        "Config templates",
        _documented(r"\| Config templates \| (\d+)", text),
        # One template = one persona directory under config/templates/.
        len([p for p in (PROJECT_ROOT / "config" / "templates").iterdir() if p.is_dir()]),
    )

    documented_loc = _documented(r"\| LOC \| ~(\d+)", text)
    measured_loc = sum(
        len(p.read_text(encoding="utf-8").splitlines())
        for p in src.rglob("*.py")
        if "__pycache__" not in p.parts
    )
    if documented_loc is None:
        drift.append("LOC: could not parse documented value from INDEX.md")
    elif abs(measured_loc - documented_loc) / documented_loc > LOC_DRIFT_THRESHOLD:
        drift.append(f"LOC: documented ~{documented_loc}, measured {measured_loc} (>10% drift)")

    if drift:
        warnings.warn(
            "INDEX.md#statistics has drifted from live measurements — refresh "
            "the table (and its 'As of' date):\n" + "\n".join(drift),
            UserWarning,
            stacklevel=1,
        )
