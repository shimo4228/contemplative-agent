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

Three assertions, all narrow enough to stay quiet on legitimate localization:

1. The **relation head** (the typed vocabulary term documented at
   ``docs/adr/README.md`` "Status line conventions") is identical on every face. The
   descriptive tail is free — ja localizes it, the index abbreviates it.
2. For **backward-supersede heads only**, the set of referenced ADR numbers
   agrees between body, index, and graph. This is the face that must stay
   machine-traversable (README.md: the phrases are mirrored as typed edges "so
   LLMs can traverse the supersede / withdrawal chain without parsing prose").

3. The graph's **typed edges** agree with that node's own Status prose — and a
   node whose Status claims no relation carries no supersede-family edge. That
   last clause is the one with teeth: ADR-0060 read a bare ``accepted`` while
   its node claimed to fully supersede ADR-0026 and ADR-0027, and nothing on
   any face contradicted it.

Both coverage gaps this module shipped with on 2026-08-15 are now closed
(T-ADR-STATUS-GATE), each having needed a corpus edit first:

- The **withdrawal chain** required normalizing ADR-0022's body Status, which
  buried the relation in a parenthetical ("withdrawn (by ADR-0034 …)" /
  「… により」) where ``_head`` could only see bare ``withdrawn`` while the index
  said ``withdrawn-by``. It now leads with the documented phrase.
- The **typed edges** disagreed with the prose in three places, all one root
  cause: a partial supersede has a backward vocabulary term
  (``partially-superseded-by``) but had no forward one, so ADR-0060 and
  ADR-0082 recorded scoped supersessions as full ``supersedes`` edges and
  ADR-0067's ``partially-supersedes`` Status produced no edge at all.
  ``partiallySupersedes`` now exists in the graph's ``@context`` and in the
  README's Status vocabulary, and ADR-0026 / ADR-0027 carry the backward half
  (author's call, 2026-08-15: follow the ADR-0021 / 0050 / 0065 precedent so a
  reader of the older ADR learns from its Status line that a section retired).

Cross-node reciprocity is deliberately *not* asserted: ADR-0034 leads with
``supersedes ADR-0022`` while ADR-0022 leads with ``withdrawn by ADR-0034``,
and each node matches its own prose. Whether a withdrawal is also a
supersession is a vocabulary judgment, not a defect a test should force.

Partial supersession is the one place where reciprocity IS asserted, because
there the two halves are the same claim in two directions rather than two
vocabulary choices. Six ``partiallySupersededBy`` edges had no forward half
until 2026-08-15, so an LLM traversing ``partiallySupersedes`` reached none of
ADR-0028 / 0029 / 0051 (from ADR-0021), ADR-0051 (from ADR-0050), ADR-0056
(from ADR-0053) or ADR-0070 (from ADR-0065). The last was a genuine
disagreement rather than an omission: ADR-0070's body said it "completes the
supersession of ADR-0065's MLX portions" while its Status named only ADR-0006
and ADR-0064, so the abbreviated faces and the full one disagreed and no
head-comparison could see it. All five ADRs now carry the forward half across
their five faces (T-ADR-PARTIAL-RECIPROCITY), and
``test_partial_supersede_edges_are_reciprocal`` keeps it that way — adding one
half of a partial supersede without the other is now a failure, not a slow
drift back to prose-only traversal.

What that test does NOT check is that the two halves agree on *scope*, which
is a semantic agreement between prose faces and out of reach here. It is a
convention instead, documented under "Status line conventions": the forward
half names only what it retired, and the surviving scope lives on the backward
half, the one face that stays correct as later partial supersessions land.
The 2026-08-15 review caught all four new forward halves stating it wrongly —
three had replicated ADR-0021's residue *after all three* supersessions onto
ADRs whose own bodies still used the trust surface — so the convention is
newer than the reciprocity gate and is not enforced by it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ADR_DIR = REPO / "docs" / "adr"

# Order matters: a head that is a prefix of another must come first —
# "withdrawn-by" ahead of "withdrawn", or every withdrawal-by-ADR collapses
# into the bare form and drops out of the target comparison below.
_HEADS = (
    "partially-superseded-by",
    "superseded-by",
    "withdrawn-by",
    "withdrawn",
    "accepted",
    "proposed",
    "rejected",
)
# Heads whose ADR references are a backward chain and must be traversable.
# Forward phrases ("accepted — supersedes 0024") are excluded: they are
# authored on the newer ADR and carry different semantics.
_BACKWARD = {"partially-superseded-by", "superseded-by", "withdrawn-by"}

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


def _graph_nodes() -> dict[str, dict]:
    graph = json.loads((REPO / "graph.jsonld").read_text(encoding="utf-8"))
    nodes = graph.get("@graph", graph)
    return {
        str(node["identifier"])[4:]: node
        for node in nodes
        if str(node.get("identifier", "")).startswith("ADR-")
    }


GRAPH_NODES = _graph_nodes()


def _graph_status() -> dict[str, str]:
    return {num: str(node["status"]) for num, node in GRAPH_NODES.items() if "status" in node}


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


# Status relation phrase -> the graph edge that mirrors it.
_EDGE_FOR_PHRASE = {
    "partially-superseded-by": "partiallySupersededBy",
    "superseded-by": "supersededBy",
    "withdrawn-by": "withdrawnBy",
    "partially-supersedes": "partiallySupersedes",
    "supersedes": "supersedes",
}
_SUPERSEDE_EDGES = frozenset(_EDGE_FOR_PHRASE.values())
# Longest phrase first, or "partially-superseded-by" is read as "superseded-by"
# and "partially-supersedes" as "supersedes" — collapsing a scoped supersede
# into a full one, which is the very defect this module exists to catch. Each
# hyphen also matches a space: the corpus writes both ("withdrawn by ADR-0034").
_PHRASE_RE = re.compile(
    "|".join(p.replace("-", "[- ]") for p in sorted(_EDGE_FOR_PHRASE, key=len, reverse=True))
)
# ADR numbers immediately following a relation phrase, as a run: "ADR-0006,
# ADR-0064" / "0067 and 0070". Anchored rather than scanning the whole clause
# so scope prose that cites an ADR as a *reason* ("… see ADR-0031") is not
# mistaken for a supersede target.
_REF_RUN_RE = re.compile(r"[\s,/]*(?:and\s+)?(?:adr-)?(0\d{3})")


def _expected_edges(status: str, adr: str) -> dict[str, set[str]]:
    """The typed edges a Status string obliges its graph node to carry.

    Multi-relation statuses are real — ADR-0060 fully supersedes ADR-0027 while
    only partially superseding ADR-0026 — so each phrase binds the ADR numbers
    that follow *it*, never every number in the string.
    """
    text = re.sub(r"\s+", " ", status).lower()
    found = list(_PHRASE_RE.finditer(text))
    edges: dict[str, set[str]] = {}
    for i, match in enumerate(found):
        stop = found[i + 1].start() if i + 1 < len(found) else len(text)
        clause = text[match.end() : stop]
        edge = _EDGE_FOR_PHRASE[match.group(0).replace(" ", "-")]
        # "supersedes X in part" is the same claim as "partially-supersedes X"
        # (ADR-0082's body writes it that way); honour the scope, not the verb.
        if edge == "supersedes" and "in part" in clause:
            edge = "partiallySupersedes"
        refs, pos = set(), 0
        while ref := _REF_RUN_RE.match(clause, pos):
            refs.add(ref.group(1))
            pos = ref.end()
        refs -= {adr}
        if refs:
            edges.setdefault(edge, set()).update(refs)
    return edges


def _edge_refs(node: dict, key: str) -> set[str]:
    """ADR numbers a typed edge points at, read off the target filenames."""
    value = node.get(key, [])
    targets = [value] if isinstance(value, str) else value
    return {m.group(1) for t in targets if (m := re.search(r"/(\d{4})-[^/]*\.md$", str(t)))}


@pytest.mark.unit
@pytest.mark.parametrize("adr", sorted(GRAPH_NODES))
def test_graph_edges_match_their_own_status_prose(adr: str) -> None:
    """A node's typed edges must say what its own Status says — no more.

    Read alone, ``status`` and the edges are each plausible; only together do
    they contradict. ADR-0060 read a bare ``accepted`` while carrying a full
    ``supersedes`` edge onto two ADRs that also read ``accepted``, so an LLM
    traversing the graph saw a retirement no prose face confirmed.

    Asserted per node, never across nodes: whether ADR-0034's ``supersedes``
    obliges ADR-0022 to answer with ``supersededBy`` rather than the
    ``withdrawnBy`` it carries is a vocabulary judgment (see module docstring).
    """
    node = GRAPH_NODES[adr]
    status = str(node.get("status", ""))
    assert status, f"ADR-{adr} graph node has no status field"

    expected = _expected_edges(status, adr)
    actual = {key: _edge_refs(node, key) for key in _SUPERSEDE_EDGES if key in node}
    assert actual == expected, (
        f"ADR-{adr} graph edges disagree with its own Status {status!r}: "
        f"expected {expected or 'no supersede-family edge'}, found "
        f"{actual or 'none'} (see docs/adr/README.md '### Status line conventions')"
    )


@pytest.mark.unit
def test_partial_supersede_edges_are_reciprocal() -> None:
    """Every ``partiallySupersededBy`` must have its forward half, and vice versa.

    Unlike the supersedes/withdrawnBy pairing, the two halves of a partial
    supersede are not a vocabulary choice — they are one claim stated from
    each end. Recording only the backward half is what left ``0021 → 0028 /
    0029 / 0051``, ``0050 → 0051``, ``0053 → 0056`` and ``0065 → 0070``
    unreachable by forward traversal, so the README's promise that an LLM can
    follow the lineage without parsing prose held only for full supersessions
    (T-ADR-PARTIAL-RECIPROCITY, closed 2026-08-15).

    Asserted over the edges rather than the prose because the prose faces are
    already pinned to the edges per node: a missing half fails here, and a
    half added to the graph without its Status sentence fails above.
    """
    backward: set[tuple[str, str]] = set()
    forward: set[tuple[str, str]] = set()
    for adr, node in GRAPH_NODES.items():
        for target in _edge_refs(node, "partiallySupersededBy"):
            backward.add((target, adr))  # (superseder, superseded)
        for target in _edge_refs(node, "partiallySupersedes"):
            forward.add((adr, target))

    missing_forward = sorted(backward - forward)
    missing_backward = sorted(forward - backward)
    assert not missing_forward, (
        "partiallySupersededBy with no forward half — forward traversal cannot "
        f"reach these: {[f'{a} partially-supersedes {b}' for a, b in missing_forward]}"
    )
    assert not missing_backward, (
        "partiallySupersedes with no backward half — the superseded ADR's own "
        "Status does not say a section retired: "
        f"{[f'{b} partially-superseded-by {a}' for a, b in missing_backward]}"
    )


# --- P1-03.2: an Amendment in the body must show in every Status face --------

# The three amendment notations the corpus actually uses: ``## Amendment (date)``
# (also ``Amendment 2 (date)`` / ``Amendment record (date)``) and the bold
# ``**D3 amendment (date, RFC-…)**`` that ADR-0106 carries in place of a heading.
_AMENDMENT_RE = re.compile(
    r"^(?:## Amendment\b[^()\n]*|\*\*[A-Za-z0-9 ]*amendment )\((\d{4}-\d\d-\d\d)", re.M
)
# The word a Status face must carry once the body has been amended. ja bodies
# may say 追補 instead; the index and graph always use ``amended``.
_AMENDED_WORD = re.compile(r"amended|追補", re.I)
# ADRs whose Status says ``amended`` without a dated Amendment block: ADR-0075
# folded its 2026-08-29 narrowing into the body text itself (no separate
# section), so the tail is the only record that the body changed after accept.
_AMENDED_WITHOUT_BLOCK = frozenset({"0075"})


def _amendment_dates(adr: str) -> list[str]:
    path = next(p for p in ADR_DIR.glob(f"{adr}-*.md") if not p.name.endswith(".ja.md"))
    seen: list[str] = []
    for d in _AMENDMENT_RE.findall(path.read_text(encoding="utf-8")):
        if d not in seen:
            seen.append(d)
    return seen


@pytest.mark.unit
@pytest.mark.parametrize("adr", ADR_NUMBERS)
def test_amendment_blocks_and_status_tail_agree(adr: str) -> None:
    """A dated Amendment in the body obliges ``amended`` on all five faces.

    Before this, 5 ADRs said ``amended`` in the body, 2 in the index and 16
    carried an Amendment block, so a reader of the index could not tell which
    decisions had moved after acceptance. Dates are not compared, only the
    presence of the tail (the Amendment blocks are the dated record).
    The reverse direction holds too: a Status that claims ``amended`` needs a
    block to point at, except the named exception above.
    """
    dates = _amendment_dates(adr)
    for label, statuses in FACES:
        if adr not in statuses:
            continue
        has_tail = bool(_AMENDED_WORD.search(statuses[adr]))
        if dates:
            assert has_tail, (
                f"ADR-{adr} {label}: body has Amendment block(s) {dates} but the "
                f"Status {statuses[adr]!r} carries no `(amended …)` tail"
            )
        elif adr not in _AMENDED_WITHOUT_BLOCK:
            assert not re.search(r"\(amended", statuses[adr]), (
                f"ADR-{adr} {label}: Status claims `amended` but the body has no "
                f"dated Amendment block"
            )


# --- P1-03.6: the index Date is the body Date --------------------------------

_DATE_HEADINGS = ("## Date", "## 日付")


def _body_date(path: Path) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip() in _DATE_HEADINGS:
            for nxt in lines[i + 1 : i + 6]:
                m = re.search(r"\d{4}-\d\d-\d\d", nxt)
                if m:
                    return m.group(0)
            return None
    return None


def _index_dates(readme: Path) -> dict[str, str]:
    """The Date cell of each index row (the column headed ``Date``)."""
    out: dict[str, str] = {}
    cols: list[str] = []
    for line in readme.read_text(encoding="utf-8").splitlines():
        if line.startswith("| ADR |"):
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
        elif cols and (m := re.match(r"^\|\s*\[(\d{4})\]", line)):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out[m.group(1)] = cells[cols.index("Date")]
    return out


@pytest.mark.unit
@pytest.mark.parametrize("adr", ADR_NUMBERS)
def test_index_date_equals_body_date(adr: str) -> None:
    """The index Date column and each body's ``## Date`` must be the same day.

    ADR-0032 had no ``## Date`` section at all while the index listed one, so
    the column could not be regenerated from the bodies (P1-03.5).
    """
    for suffix, readme in ((".md", "README.md"), (".ja.md", "README.ja.md")):
        path = next(
            p
            for p in ADR_DIR.glob(f"{adr}-*.md")
            if p.name.endswith(suffix) and (suffix == ".ja.md") == p.name.endswith(".ja.md")
        )
        body = _body_date(path)
        assert body is not None, f"{path.name}: no `## Date` section with a date"
        assert _index_dates(ADR_DIR / readme).get(adr) == body, (
            f"{path.name}: body Date {body} != {readme} index Date"
        )


# --- P1-03.3: a Note that revises another ADR needs a typed edge -------------

# ``**Note (2026-10-09, revised by ADR-0113)**`` declares that a later ADR changed
# what the paragraph says. ``**Note (2026-08-29, per ADR-0101 T4)**`` only
# records that a procedure was applied and must not demand an edge to ADR-0101.
# The edge vocabulary a revision may use is left open on purpose: the
# ``revised-by`` term itself is an owner decision (D-P1-03-2); until then the
# existing partial/full supersede edges satisfy the rule.
_REVISED_NOTE_RE = re.compile(
    r"\bNote\b[^()\n]*\(\d{4}-\d\d-\d\d[^)\n]*?\brevised by \[?ADR-(\d{4})"
)
_REVISION_EDGES = ("partiallySupersededBy", "supersededBy", "withdrawnBy", "revisedBy")


def _revised_by_targets(text: str) -> set[str]:
    return set(_REVISED_NOTE_RE.findall(text))


@pytest.mark.unit
def test_revised_by_note_matcher_ignores_procedural_notes() -> None:
    """The negative case: a ``per ADR-0101 T4`` Note is not a revision."""
    assert _revised_by_targets("> **Note (2026-10-17, revised by ADR-0113)**: x") == {"0113"}
    assert _revised_by_targets("> **Note (2026-10-17, per ADR-0101 T4)**: x") == set()
    assert (
        _revised_by_targets(
            "> **Note (2026-08-29, ADR-0101 T4 first stocktake)**: open question put"
        )
        == set()
    )
    assert _revised_by_targets("Note (2026-09-20, revised by [ADR-0081](./x.md)): y") == {"0081"}


@pytest.mark.unit
def test_dated_notes_have_typed_edges() -> None:
    """``Note (date, revised by ADR-X)`` in an ADR body => the node has an edge to X."""
    problems = []
    for adr in ADR_NUMBERS:
        path = next(p for p in ADR_DIR.glob(f"{adr}-*.md") if not p.name.endswith(".ja.md"))
        targets = _revised_by_targets(path.read_text(encoding="utf-8"))
        node = GRAPH_NODES.get(adr, {})
        have: set[str] = set()
        for key in _REVISION_EDGES:
            have |= _edge_refs(node, key)
        for target in sorted(targets - have):
            problems.append(
                f"ADR-{adr}: Note says 'revised by ADR-{target}' but the graph node has no edge to it"
            )
    assert not problems, "\n".join(problems)


# --- P1-03.7: new ADRs say who decided and which layer they live in ----------

_LAYERS = frozenset({"mechanism", "instrument", "governance", "research", "worldview"})
# The 113 ADRs written before this rule are not backfilled (author's call,
# 2026-10: AKC ADR-0026 does the same); the rule starts at the next number.
_DECIDED_BY_FROM = 114


def _section(text: str, heading: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == heading:
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                if nxt.startswith("## "):
                    break
                body.append(nxt)
            return "\n".join(body).strip()
    return None


def _layer_problem(text: str) -> str | None:
    decided = _section(text, "## Decided by")
    if not decided:
        return "no `## Decided by` section"
    for key in ("proposed-by:", "decided-by:", "date:"):
        if key not in decided:
            return f"`## Decided by` lacks `{key}`"
    layer = _section(text, "## Layer")
    if layer is None:
        return "no `## Layer` section"
    if layer.strip().lower() not in _LAYERS:
        return f"`## Layer` is {layer!r}, expected one of {sorted(_LAYERS)}"
    return None


@pytest.mark.unit
def test_decided_by_and_layer_checker_on_synthetic_adrs() -> None:
    good = (
        "# ADR-0200: x\n\n## Decided by\nproposed-by: session\ndecided-by: owner\n"
        "date: 2026-11-01\n\n## Layer\nmechanism\n\n## Context\nc\n"
    )
    assert _layer_problem(good) is None
    assert "Decided by" in (_layer_problem("## Layer\nmechanism\n") or "")
    assert "Layer" in (_layer_problem(good.replace("mechanism", "vibes")) or "")
    assert "decided-by" in (_layer_problem(good.replace("decided-by:", "who:")) or "")


@pytest.mark.unit
def test_adrs_from_0114_declare_decided_by_and_layer() -> None:
    """Every en ADR numbered >= 0114 has ``## Decided by`` and a one-value ``## Layer``."""
    problems = []
    for adr in ADR_NUMBERS:
        if int(adr) < _DECIDED_BY_FROM:
            continue
        path = next(p for p in ADR_DIR.glob(f"{adr}-*.md") if not p.name.endswith(".ja.md"))
        if problem := _layer_problem(path.read_text(encoding="utf-8")):
            problems.append(f"ADR-{adr}: {problem}")
    assert not problems, "\n".join(problems)


@pytest.mark.unit
def test_llms_files_reach_the_newest_adr() -> None:
    """llms.txt lists, and llms-full.txt counts, every ADR up to the newest on disk (P1-09.7).

    Both files went four ADRs stale once because the "when adding an ADR" rule
    named only graph.jsonld.
    """
    newest = max(int(n) for n in _adrs_on_disk())
    llms = (REPO / "llms.txt").read_text(encoding="utf-8")
    listed = {int(m) for m in re.findall(r"\[ADR-(\d{4})\b", llms)}
    assert max(listed) == newest, f"llms.txt newest ADR row is {max(listed):04d}, docs/adr has {newest:04d}"
    full = (REPO / "llms-full.txt").read_text(encoding="utf-8")
    m = re.search(r"\*\*ADRs\*\*: (\d+) total.*?ADR-0001 through ADR-(\d{4})", full)
    assert m, "llms-full.txt Facts lost its ADR count line"
    assert int(m.group(1)) == len(_adrs_on_disk()) and int(m.group(2)) == newest
