"""The AKC six-phase mapping has one canonical face: the Phase nodes of graph.jsonld (P1-13.7).

Before this, five faces restated the mapping and disagreed: the ADR index tagged
ADR-0020 ``Curate`` while the graph said ``Measure``, the graph's Curate phase
still named the retired ``rules-distill``, Measure pointed only at ADR-0020, and
Maintain pointed at five ADRs whose subject was retiring 2026-04 mechanisms.
Now the six ``Phase`` nodes (``realizedBy`` -> ADRs) are the source; the index
tags are generated from them (``scripts/adr_index.py``, gated by
``tests/test_adr_index_generated.py``), the glossary and ``llms-full.txt`` point
at them, and ``docs/CYCLES.md``'s AKC phase column is checked here.

What this module asserts:

1. Six Phase nodes, orders 1..6, with AKC's phase names.
2. Every phase names at least one ADR, and every named ADR exists and is in
   force: its Status does not lead with ``superseded-by`` / ``withdrawn``.
3. Every CLI command a phase description names (in backticks) is a command
   the CLI registers today, so a retired command cannot stay on a phase.
4. The CYCLES.md master table's ``AKC phase`` column uses only the graph's
   phase names, and between its rows names all six.

The AKC repository's own two faces (its CLAUDE.md phase line and the
``examples/constitution_amend`` table) live outside this repo and are not
checked here.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from contemplative_agent.cli import COMMANDS

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import adr_index  # noqa: E402  # pyright: ignore[reportMissingImports]

AKC_PHASES = ("Research", "Extract", "Curate", "Promote", "Measure", "Maintain")
_RETIRED_HEADS = ("superseded-by", "superseded by", "withdrawn")
# Phase descriptions backtick CLI command names and nothing else, so every
# backticked span is checked against the live command list (not against a shape).
_TICKED = re.compile(r"`([^`]+)`")
# Retired commands (ADR-0097, ADR-0103) may not come back even unticked.
_RETIRED_COMMANDS = ("rules-distill", "rules-stocktake", "wiki-maintain", "wiki-propose")

GRAPH = adr_index.load_graph()
PHASES = adr_index.phase_nodes(GRAPH)


def _status(adr: str) -> str:
    path = adr_index._adr_files(".md")[adr]
    return adr_index._status_block(path.read_text(encoding="utf-8")) or ""


@pytest.mark.unit
def test_six_phase_nodes_carry_the_akc_names_in_order() -> None:
    assert [int(n["order"]) for n in PHASES] == [1, 2, 3, 4, 5, 6]
    assert tuple(adr_index.phase_name(n) for n in PHASES) == AKC_PHASES


@pytest.mark.unit
@pytest.mark.parametrize("node", PHASES, ids=adr_index.phase_name)
def test_every_phase_is_realized_by_adrs_in_force(node: dict) -> None:
    urls = adr_index._as_list(node.get("realizedBy"))
    assert urls, f"{adr_index.phase_name(node)} names no ADR in realizedBy"
    files = adr_index._adr_files(".md")
    for url in urls:
        m = adr_index._ADR_URL_RE.search(url)
        assert m and m.group(1) in files, f"{url} is not an ADR file"
        assert url.endswith("/" + files[m.group(1)].name), f"{url} names a stale file name"
        status = _status(m.group(1)).lstrip("*").lower()
        assert not status.startswith(_RETIRED_HEADS), (
            f"{adr_index.phase_name(node)} points at ADR-{m.group(1)}, which is retired: {status!r}"
        )


@pytest.mark.unit
@pytest.mark.parametrize("node", PHASES, ids=adr_index.phase_name)
def test_phase_descriptions_name_only_current_cli_commands(node: dict) -> None:
    current = {spec.name for spec in COMMANDS}
    description = str(node.get("description", ""))
    named = set(_TICKED.findall(description))
    assert named <= current, (
        f"{adr_index.phase_name(node)} backticks name(s) that are not CLI commands: "
        f"{sorted(named - current)}"
    )
    retired = [c for c in _RETIRED_COMMANDS if re.search(rf"\b{re.escape(c)}\b", description)]
    assert not retired, f"{adr_index.phase_name(node)} names retired command(s): {retired}"


def _cycles_phase_cells() -> dict[str, str]:
    text = (REPO / "docs" / "CYCLES.md").read_text(encoding="utf-8")
    section = text.split("## Master table", 1)[1]
    cols: list[str] = []
    cells: dict[str, str] = {}
    for line in section.splitlines():
        if not line.startswith("|"):
            if cols:
                break
            continue
        row = [c.strip() for c in line.strip().strip("|").split("|")]
        if not cols:
            cols = row
        elif row[0].isdigit():
            cells[row[0]] = row[cols.index("AKC phase")]
    return cells


@pytest.mark.unit
def test_cycles_master_table_names_the_graph_phases() -> None:
    cells = _cycles_phase_cells()
    assert cells, "docs/CYCLES.md master table has no rows with an `AKC phase` column"
    seen: set[str] = set()
    for cycle, cell in cells.items():
        names = {n.strip() for n in cell.split("·")} - {"—"}
        assert names <= set(AKC_PHASES), f"cycle {cycle}: {sorted(names - set(AKC_PHASES))}"
        seen |= names
    assert seen == set(AKC_PHASES), f"CYCLES.md never names {sorted(set(AKC_PHASES) - seen)}"
