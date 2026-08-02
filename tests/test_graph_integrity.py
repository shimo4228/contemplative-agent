"""Referential integrity between graph.jsonld and repo artifacts.

graph.jsonld is the concept-level companion of CODEMAPS (CLAUDE.md: new
ADRs / Concepts / Axioms update both faces). Entity nodes that mirror repo
artifacts must stay in one-to-one correspondence with those artifacts; a
node whose artifact is gone is the graph-side form of the orphan problem
ADR-0073 diagnosed. Numeric or textual claims *inside* node descriptions
are historical records of past decisions and deliberately not checked.
"""

import json
from pathlib import Path


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("repo root (pyproject.toml) not found above this file")


REPO_ROOT = _repo_root()
BLOB_PREFIX = "https://github.com/shimo4228/contemplative-agent/blob/main/"

# Frozen by design: the four axioms are the project's core (Laukkonen et al.
# 2025); the three memory layers are the architecture's spine.
AXIOM_IDS = {
    "https://shimo4228.github.io/shimo4228/vocab#axiom/emptiness",
    "https://shimo4228.github.io/shimo4228/vocab#axiom/non-duality",
    "https://shimo4228.github.io/shimo4228/vocab#axiom/mindfulness",
    "https://shimo4228.github.io/shimo4228/vocab#axiom/boundless-care",
}
MEMORY_LAYER_IDS = {
    "https://shimo4228.github.io/shimo4228/vocab#memory-layer/episode-log",
    "https://shimo4228.github.io/shimo4228/vocab#memory-layer/knowledge",
    "https://shimo4228.github.io/shimo4228/vocab#memory-layer/identity",
}


def _nodes() -> list[dict]:
    graph = json.loads((REPO_ROOT / "graph.jsonld").read_text(encoding="utf-8"))
    return graph["@graph"]


def _nodes_of(kind: str) -> list[dict]:
    result = []
    for node in _nodes():
        types = node.get("@type", [])
        types = [types] if isinstance(types, str) else types
        if kind in types:
            result.append(node)
    return result


class TestGraphIntegrity:
    def test_url_relationships_are_coerced_to_iri_edges(self):
        graph = json.loads((REPO_ROOT / "graph.jsonld").read_text(encoding="utf-8"))
        context = graph["@context"]

        for relationship in ("citation", "subjectOf"):
            assert context[relationship] == {
                "@id": f"https://schema.org/{relationship}",
                "@type": "@id",
            }

    def test_adr_nodes_match_adr_files_bidirectionally(self):
        node_paths = {n["@id"].removeprefix(BLOB_PREFIX) for n in _nodes_of("ADR")}
        file_paths = {
            f"docs/adr/{p.name}"
            for p in (REPO_ROOT / "docs" / "adr").glob("[0-9]*.md")
            if not p.name.endswith(".ja.md")
        }
        stale_nodes = node_paths - file_paths
        unregistered = file_paths - node_paths
        assert node_paths == file_paths, (
            f"graph.jsonld ADR nodes ↔ docs/adr/ files diverged. "
            f"Nodes without a file (stale): {sorted(stale_nodes)}. "
            f"Files without a node (register in graph.jsonld per CLAUDE.md "
            f"両面更新 rule): {sorted(unregistered)}."
        )

    def test_axiom_nodes_are_exactly_the_four_axioms(self):
        assert {n["@id"] for n in _nodes_of("Axiom")} == AXIOM_IDS

    def test_memory_layer_nodes_are_exactly_the_three_layers(self):
        assert {n["@id"] for n in _nodes_of("MemoryLayer")} == MEMORY_LAYER_IDS

    def test_every_repo_file_id_resolves_to_an_existing_file(self):
        broken = []
        for node in _nodes():
            node_id = node.get("@id", "")
            if node_id.startswith(BLOB_PREFIX):
                rel = node_id.removeprefix(BLOB_PREFIX).split("#", 1)[0]
                if not (REPO_ROOT / rel).is_file():
                    broken.append(node_id)
        assert not broken, f"graph.jsonld @ids pointing at nonexistent repo files: {broken}"

    def test_node_ids_are_unique(self):
        ids = [n["@id"] for n in _nodes() if "@id" in n]
        dupes = {i for i in ids if ids.count(i) > 1}
        assert not dupes, f"duplicate @ids in graph.jsonld: {sorted(dupes)}"
