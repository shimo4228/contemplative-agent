"""ADR Status must agree across every face that publishes it.

An ADR's Status is stated in four places: the ADR body (en and ja), the index
row in ``docs/adr/README.md`` / ``README.ja.md``, and the ``status`` field of
the ADR's node in ``graph.jsonld``. Nothing kept them in step, and they drifted
silently for months: on 2026-08-15 a manual read found ADR-0053 stale in the
index and the graph (the body and the graph *description* already recorded the
ADR-0056 retirement), ADR-0050's index row missing ADR-0082 that the graph
already carried, and three ja index rows still reading ``proposed`` for ADRs
long since superseded or accepted.

Neither existing gate could see it. ``test_graph_integrity`` checks the
node-to-file bijection and ``@id`` resolvability, never the Status value;
``scripts/docs_consistency_scan.py`` compares *commit timestamps*, so a pair
edited in one commit reads clean no matter what it says.

Two assertions, both narrow enough to stay quiet on legitimate localization:

1. The **relation head** (the typed vocabulary term documented at
   ``docs/adr/README.md`` "Status line conventions") is identical on every face. The
   descriptive tail is free — ja localizes it, the index abbreviates it.
2. For **backward-supersede heads only**, the set of referenced ADR numbers
   agrees between body, index, and graph. This is the face that must stay
   machine-traversable (README.md: the phrases are mirrored as typed edges "so
   LLMs can traverse the supersede / withdrawal chain without parsing prose").

Known coverage gaps, deliberately not closed here so the gate does not read as
broader than it is (T-ADR-STATUS-GATE in the task ledger):

- **The withdrawal chain is unchecked.** ``withdrawn-by`` is absent from
  ``_HEADS``, so it collapses into bare ``withdrawn`` and never reaches the
  target comparison. Adding it requires normalizing ADR-0022's body Status,
  which spells the relation as prose ("withdrawn (by ADR-0034 …)" / 「… により」)
  rather than the documented ``withdrawn-by ADR-NNNN`` form.
- **The typed graph edges are not read** — only the graph's ``status`` string
  is. ``supersedes`` / ``supersededBy`` / ``partiallySupersededBy`` /
  ``withdrawnBy`` already disagree with the prose in at least four places
  (ADR-0060's node claims ``supersedes`` ADR-0026 and ADR-0027, both of which
  read ``accepted`` on all five faces), and reconciling them needs a human
  decision about which side is right, not a test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ADR_DIR = REPO / "docs" / "adr"

# Order matters: a head that is a prefix of another must come after it.
# Nothing here is a prefix of anything else today, but adding "withdrawn-by"
# (see the coverage note in the module docstring) would have to precede
# "withdrawn".
_HEADS = (
    "partially-superseded-by",
    "superseded-by",
    "withdrawn",
    "accepted",
    "proposed",
    "rejected",
)
# Heads whose ADR references are a backward supersede chain and must be
# traversable. Forward phrases ("accepted — supersedes 0024") are excluded:
# they are authored on the newer ADR and carry different semantics.
_BACKWARD = {"partially-superseded-by", "superseded-by"}

_ADR_FILE = re.compile(r"^(\d{4})-.+\.md$")
_INDEX_ROW = re.compile(r"^\|\s*\[(\d{4})\]\([^)]+\)\s*\|(?:[^|]*)\|([^|]*)\|")


def _head(status: str) -> str | None:
    """The typed vocabulary term a Status string leads with.

    Tolerates the formatting variety the corpus actually carries: leading
    markdown emphasis (ADR-0032 ``**withdrawn (…)**``) and the unhyphenated
    ``superseded by`` (ADR-0023). Only the term is normalized — the tail is
    free text and is never compared.
    """
    text = re.sub(r"^[*_\s]+", "", status).strip().lower()
    text = re.sub(r"\s+", " ", text)
    for head in _HEADS:
        if text.startswith(head) or text.startswith(head.replace("-", " ")):
            return head
    return None


def _refs(status: str) -> set[str]:
    """ADR numbers named in a Status string, ``ADR-`` prefix optional.

    Restricted to the ``0NNN`` shape so the dates woven through the scope
    parentheticals ("retired 2026-06-17") are not read as ADR references.
    """
    return set(re.findall(r"(?:ADR-)?\b(0\d{3})\b", status))


def _body_status(path: Path) -> str | None:
    """Text of the ADR's Status section, joined to one line."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        # The ja twins are inconsistent: most keep "## Status", ADR-0028 uses
        # the translated heading.
        if line.strip() in ("## Status", "## ステータス"):
            block: list[str] = []
            for nxt in lines[i + 1 :]:
                if nxt.startswith("## "):
                    break
                if nxt.strip():
                    block.append(nxt.strip())
                elif block:
                    break
            return " ".join(block) or None
    return None


def _index_cells(readme: Path) -> dict[str, str]:
    cells = {}
    for line in readme.read_text(encoding="utf-8").splitlines():
        m = _INDEX_ROW.match(line)
        if m:
            cells[m.group(1)] = m.group(2).strip()
    return cells


def _graph_status() -> dict[str, str]:
    graph = json.loads((REPO / "graph.jsonld").read_text(encoding="utf-8"))
    nodes = graph.get("@graph", graph)
    out = {}
    for node in nodes:
        ident = str(node.get("identifier", ""))
        if ident.startswith("ADR-") and "status" in node:
            out[ident[4:]] = str(node["status"])
    return out


def _faces() -> list[tuple[str, dict[str, str]]]:
    """(label, {adr number: status text}) for every face that states a Status."""
    bodies_en, bodies_ja = {}, {}
    for path in sorted(ADR_DIR.glob("*.md")):
        m = _ADR_FILE.match(path.name)
        if not m:
            continue
        status = _body_status(path)
        if status is None:
            continue
        (bodies_ja if path.name.endswith(".ja.md") else bodies_en)[m.group(1)] = status
    return [
        ("body en", bodies_en),
        ("body ja", bodies_ja),
        ("index en", _index_cells(ADR_DIR / "README.md")),
        ("index ja", _index_cells(ADR_DIR / "README.ja.md")),
        ("graph.jsonld", _graph_status()),
    ]


FACES = _faces()
BODY_EN = dict(FACES)["body en"]
ADR_NUMBERS = sorted(BODY_EN)


def _adrs_on_disk() -> set[str]:
    return {
        m.group(1)
        for p in ADR_DIR.glob("*.md")
        if (m := _ADR_FILE.match(p.name)) and not p.name.endswith(".ja.md")
    }


@pytest.mark.unit
@pytest.mark.parametrize("label", [label for label, _ in FACES])
def test_every_face_states_a_status_for_every_adr(label: str) -> None:
    """No ADR may drop off a face without saying so.

    This is the canary, and it is the point of the whole module. Both
    assertions below iterate the ADRs a face actually yielded, so anything that
    fails to parse — a `## Status` heading that grew a parenthetical, an index
    row whose markdown changed shape, a graph node that lost its `status` key —
    would leave that ADR unchecked while the suite stayed green. Comparing each
    face against the files on disk converts silent de-enrollment into a named
    failure.
    """
    statuses = dict(FACES)[label]
    missing = sorted(_adrs_on_disk() - set(statuses))
    assert not missing, (
        f"{label} states no Status for ADR(s) {missing} — either the entry is "
        f"genuinely absent or this module stopped parsing it, and both mean "
        f"those ADRs are no longer covered by the checks below"
    )


@pytest.mark.unit
@pytest.mark.parametrize("adr", ADR_NUMBERS)
def test_status_head_agrees_across_faces(adr: str) -> None:
    """The typed vocabulary term must be identical wherever the Status appears."""
    seen: dict[str, str] = {}
    for label, statuses in FACES:
        if adr not in statuses:
            continue  # ja twin or graph node may legitimately not exist
        head = _head(statuses[adr])
        assert head is not None, (
            f"ADR-{adr} {label}: {statuses[adr]!r} starts with no documented "
            f"Status term (see docs/adr/README.md '### Status line conventions')"
        )
        seen[label] = head
    distinct = set(seen.values())
    assert len(distinct) == 1, f"ADR-{adr} Status heads disagree across faces: {seen}"


@pytest.mark.unit
@pytest.mark.parametrize("adr", ADR_NUMBERS)
def test_supersede_targets_agree_across_faces(adr: str) -> None:
    """A backward supersede chain must name the same ADRs on every short face.

    The index cells and the graph ``status`` are the abbreviated faces, and
    they must agree exactly — that pairing is what ADR-0050 broke (the graph
    carried ADR-0082, the index did not).

    The ADR bodies carry per-target scope prose that legitimately cites other
    ADRs (ADR-0050's scope note mentions ADR-0060 without being superseded by
    it), so a body is held to the weaker rule that it must at least name every
    target the short faces claim.
    """
    if _head(BODY_EN[adr]) not in _BACKWARD:
        pytest.skip("not a backward supersede status")

    short = {
        label: _refs(statuses[adr]) - {adr}
        for label, statuses in FACES
        if adr in statuses and not label.startswith("body")
    }
    distinct = {frozenset(v) for v in short.values()}
    assert len(distinct) == 1, (
        f"ADR-{adr} names different supersede targets per face: "
        + ", ".join(f"{k}={sorted(v)}" for k, v in short.items())
    )

    claimed = set(next(iter(distinct)))
    for label, statuses in FACES:
        if adr in statuses and label.startswith("body"):
            missing = claimed - _refs(statuses[adr])
            assert not missing, (
                f"ADR-{adr} {label} does not name supersede target(s) "
                f"{sorted(missing)} that the index and graph claim"
            )
