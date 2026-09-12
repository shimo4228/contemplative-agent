"""ADR-0109 D1: the wheel's runtime dependency floor is ``requests`` + ``numpy``.

This is the machine gate for a rule that otherwise lives only in prose. Adding a
runtime dependency is allowed, but only through an ADR (new or amending 0109) —
that ADR changes ``RUNTIME_FLOOR`` here in the same commit. Dev / eval groups and
``scripts/`` are outside this gate by design (ADR-0109 D2).
"""

from __future__ import annotations

from pathlib import Path

import tomllib

RUNTIME_FLOOR = frozenset({"requests", "numpy"})

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _distribution_name(requirement: str) -> str:
    # "numpy>=1.24.0" / "requests[socks]>=2" / "pkg ; python_version<'3.12'" → bare name.
    head = requirement.split(";", 1)[0]
    for sep in ("[", ">", "<", "=", "!", "~", " "):
        head = head.split(sep, 1)[0]
    return head.strip().lower()


def test_runtime_dependencies_are_exactly_the_adr_0109_floor() -> None:
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]
    names = {_distribution_name(r) for r in project["dependencies"]}
    assert names == RUNTIME_FLOOR, (
        f"[project].dependencies = {sorted(names)} != ADR-0109 floor {sorted(RUNTIME_FLOOR)}. "
        "A runtime dependency needs an ADR; update RUNTIME_FLOOR in the same commit."
    )


def test_no_optional_dependency_extras() -> None:
    # An extra is runtime code a user installs — inside D1, not a way around it.
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]
    assert "optional-dependencies" not in project, (
        "[project.optional-dependencies] would add runtime code outside the ADR-0109 "
        "floor; an extra needs an ADR like any runtime dependency."
    )
