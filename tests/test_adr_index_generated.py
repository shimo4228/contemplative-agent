"""The ADR index tables and the graph's ADR face are generated from the ADR bodies (P1-03.5).

The index in ``docs/adr/README.md`` / ``README.ja.md`` and the ADR nodes of
``graph.jsonld`` were hand-written: 113 rows x 2 faces plus 113 nodes that drifted
from the bodies. ``scripts/adr_index.py`` now derives the tables and the nodes'
body facts (name, status, dates, supersede-family edges, phase) from them, plus an
``RFC`` node for each rfcs/ file an edge points at, and this module is the single
gate: the committed files must be byte-for-byte what the script generates. Fixing
a stale row or node therefore means fixing the ADR body (or running the script),
never editing the row. A node's ``description`` and its other edges stay hand-written.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import adr_index  # noqa: E402  # pyright: ignore[reportMissingImports]


@pytest.mark.unit
@pytest.mark.parametrize("readme,ja", [("README.md", False), ("README.ja.md", True)])
def test_committed_index_equals_generated(readme: str, ja: bool) -> None:
    path = REPO / "docs" / "adr" / readme
    assert path.read_text(encoding="utf-8") == adr_index.generated(path, ja), (
        f"docs/adr/{readme} differs from what scripts/adr_index.py generates — "
        f"run `python3 scripts/adr_index.py` and commit the result"
    )


@pytest.mark.unit
def test_check_mode_exits_zero_when_current_and_revised_since_prints_a_count() -> None:
    assert adr_index.main(["--check"]) == 0
    out = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "adr_index.py"), "--revised-since", "30"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert out.returncode == 0
    assert "ADR(s) revised in the last 30 days" in out.stdout


@pytest.mark.unit
def test_revised_since_counts_by_the_latest_dated_event() -> None:
    today = date(2026, 10, 24)
    inside = adr_index.revised_since(30, today)
    # ADR-0113's last Amendment is 2026-10-17; ADR-0001 was never revised.
    assert "0113" in inside
    assert "0001" not in inside
    assert adr_index.revised_since(3650, today) == sorted(adr_index._adr_files(".md"))


@pytest.mark.unit
def test_every_adr_has_a_row_with_the_same_date_as_its_body() -> None:
    rows = adr_index._rows(False)
    assert [r["adr"] for r in rows] == sorted(adr_index._adr_files(".md"))
    assert all(r["date"] and r["revised"] >= r["date"] for r in rows)


def _body(status: str, extra: str = "", date_line: str = "2026-01-01") -> str:
    return f"# ADR-0200: Title (withdrawn 2026-02-02)\n\n## Status\n\n{status}\n\n## Date\n\n{date_line}\n\n{extra}"


@pytest.mark.unit
@pytest.mark.parametrize(
    "status,extra,expected",
    [
        ("accepted", "", "accepted"),
        ("accepted (note) — narrow", "", "accepted (note)"),
        ("**withdrawn (2026-04-27)** — same day", "", "withdrawn (2026-04-27)"),
        (
            "accepted — supersedes ADR-0064 (MLX) and ADR-0006 (Docker); partially-supersedes [ADR-0065](./x.md) (a), partially-supersedes ADR-0067 (b)",
            "",
            "accepted — supersedes 0006, 0064; partially-supersedes 0065, 0067",
        ),
        (
            "partially-superseded-by ADR-0104 (x)",
            "## Amendment (2026-07-18): a\n\n## Amendment 2 (2026-09-19): b\n",
            "partially-superseded-by 0104 (amended 2026-07-18, 2026-09-19)",
        ),
        (
            "partially-superseded-by ADR-0067 (a); partially-superseded-by ADR-0070 (b)",
            "",
            "partially-superseded-by 0067, 0070",
        ),
        ("accepted (amended 2026-08-29)", "", "accepted (amended 2026-08-29)"),
        (
            "accepted — extends [ADR-0066](./0066.md)",
            "**D3 amendment (2026-09-12, RFC-0029)** x\n",
            "accepted (amended 2026-09-12) — extends 0066",
        ),
    ],
)
def test_status_cell_is_the_spine_of_the_body_status(
    status: str, extra: str, expected: str
) -> None:
    assert adr_index.status_cell("0200", _body(status, extra)) == expected


@pytest.mark.unit
def test_last_revised_takes_the_latest_of_date_amendment_and_note() -> None:
    body = _body(
        "accepted",
        "> **Note (2026-03-05, ADR-0101 T4)**: x\n## Amendment (2026-02-01): y\n> **Note added 2026-04-09 (ADR-0111)**: z\n",
    )
    assert adr_index.last_revised(body) == "2026-04-09"
    assert adr_index.last_revised(_body("accepted")) == "2026-01-01"


@pytest.mark.unit
def test_title_drops_the_prefix_and_a_trailing_withdrawal_note() -> None:
    assert adr_index._title(_body("accepted")) == "Title"


@pytest.mark.unit
def test_akc_tags_come_from_the_graph_phase_nodes() -> None:
    by_adr = {r["adr"]: r["title"] for r in adr_index._rows(False)}
    tags = adr_index.akc_tags(adr_index.load_graph())
    assert tags, "no Phase node names an ADR in realizedBy"
    for adr, tag in tags.items():
        assert by_adr[adr].endswith(f"`[AKC: {tag}]`")
    for adr in set(by_adr) - set(tags):
        assert "[AKC" not in by_adr[adr], f"ADR-{adr} has a tag no Phase node gives it"


@pytest.mark.unit
def test_akc_tags_join_several_phases_in_phase_order() -> None:
    def phase(order: int, name: str, *adrs: str) -> dict:
        return {
            "@id": f"{adr_index.PHASE_PREFIX}{name.lower()}",
            "order": order,
            "alternateName": [{"@value": name, "@language": "en"}],
            "realizedBy": [f"https://x/docs/adr/{a}-t.md" for a in adrs],
        }

    graph = {"@graph": [phase(5, "Measure", "0097"), phase(3, "Curate", "0097", "0104")]}
    assert adr_index.akc_tags(graph) == {"0097": "Curate/Measure", "0104": "Curate"}


# --- the graph's ADR face and RFC nodes (PR-B) --------------------------------


@pytest.mark.unit
def test_committed_graph_equals_generated() -> None:
    assert (REPO / "graph.jsonld").read_text(encoding="utf-8") == adr_index.generated_graph(), (
        "graph.jsonld's ADR face or RFC nodes differ from what scripts/adr_index.py "
        "generates — fix the ADR body / RFC frontmatter, run `python3 scripts/adr_index.py` "
        "and commit the result"
    )


@pytest.mark.unit
def test_graph_face_is_idempotent() -> None:
    once = adr_index.graph_face(adr_index.load_graph())
    assert adr_index.graph_face(once) == once


@pytest.mark.unit
def test_every_adr_node_has_a_description() -> None:
    """The generator creates a node for a new ADR file without one; the writer adds it."""
    missing = [
        n["identifier"]
        for n in adr_index.load_graph()["@graph"]
        if adr_index._is_type(n, "ADR") and not str(n.get("description", "")).strip()
    ]
    assert not missing, f"ADR nodes without a description: {missing}"


@pytest.mark.unit
def test_adr_to_rfc_edges_are_typed_rfc_nodes() -> None:
    nodes = adr_index.load_graph()["@graph"]
    rfc_ids = {n["@id"] for n in nodes if adr_index._is_type(n, "RFC")}
    edges = [
        (n["identifier"], url)
        for n in nodes
        if adr_index._is_type(n, "ADR")
        for url in adr_index._as_list(n.get("isBasedOn"))
        if "/rfcs/" in url
    ]
    assert len(edges) >= 8, edges
    assert {url for _, url in edges} <= rfc_ids
    for node in nodes:
        if adr_index._is_type(node, "RFC"):
            assert node["name"].startswith(node["identifier"]) and node["status"], node


@pytest.mark.unit
def test_a_new_adr_file_gets_a_generated_node_without_a_description() -> None:
    graph = adr_index.load_graph()
    victim = next(n for n in graph["@graph"] if n.get("identifier") == "ADR-0087")
    graph["@graph"].remove(victim)
    rebuilt = next(
        n for n in adr_index.graph_face(graph)["@graph"] if n.get("identifier") == "ADR-0087"
    )
    assert "description" not in rebuilt
    for key in ("@id", "name", "status", "datePublished", "dateModified", "extends"):
        assert rebuilt[key] == victim[key], key


@pytest.mark.unit
def test_cell_relations_bind_each_phrase_to_its_own_numbers() -> None:
    cell = (
        "accepted (amended 2026-08-01) — partially-supersedes ADR-0065; "
        "partially-superseded-by ADR-0070, ADR-0071"
    )
    assert adr_index.cell_relations(cell) == {
        "partially-supersedes": ["0065"],
        "partially-superseded-by": ["0070", "0071"],
    }
    assert adr_index.cell_relations("withdrawn-by ADR-0034") == {"withdrawn-by": ["0034"]}
