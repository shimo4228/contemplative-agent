"""The RFC-0027 fact table must keep rendering the runs already frozen.

The renderer gained two columns on 2026-09-17 (`target as written`, `flags`)
when the comparison harness started recording them. The 2026-09-12 result files
predate those fields, so the renderer has a second path for them — this pins
that both paths produce a well-formed table rather than a KeyError.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from scripts import rfc0027_render_fact_table as renderer

FROZEN = [
    "comparison-20260912.json",
    "comparison-20260912-rerun.json",
]


def _render(path: Path) -> list[str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        assert renderer.main([str(path)]) == 0
    return buffer.getvalue().splitlines()


@pytest.mark.parametrize("name", FROZEN)
def test_a_pre_2026_09_17_result_file_still_renders(name: str) -> None:
    path = renderer.HERE / name
    lines = _render(path)
    cases = json.loads(path.read_text(encoding="utf-8"))["arms"]["proposed"]["cases"]
    header = next(line for line in lines if line.startswith("| case | proposed:"))
    width = header.count("|")
    body = [
        line for line in lines if line.startswith("| `") and lines.index(line) > lines.index(header)
    ]
    assert len(body) == len(cases)
    assert all(line.count("|") == width for line in body)
    # no flag was recorded then, and the column says so rather than claiming none
    assert all("| n/a |" in line for line in body)
