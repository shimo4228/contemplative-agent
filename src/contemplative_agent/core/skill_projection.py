"""The cheap projection of a skill, and the nearest-k store slice over it.

Two insight stages compare a cluster (RFC-0042 item 2, the naming call) and a
written candidate (item 4, the duplicate judge) against the skills already in
the store. Both show the SAME projection — name, description, and a clipped
head of what the skill does and when — because the 2026-09-19 replays that
justify the stages measured exactly that shape
(``docs/evidence/rfc-0041/``; the replay script itself was removed in
``bcc97e2`` once the stages shipped).

The novelty gate's inventory (``insight_novelty._load_known_themes``) is a
different, thinner projection: name + description only, packed by the token
budget of a multi-cluster chunk. It is not reused here — these stages judge one
item against five neighbours and can afford the body, and that affordance is
the whole reason the post-extraction order works where the pre-extraction one
does not (ADR-0084).

Retrieval is candidate generation only: nothing is dropped by cosine, the LLM
returns every verdict.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from .text_utils import iter_markdown_documents, skill_theme

logger = logging.getLogger(__name__)

# Characters kept from each body section. A measured condition of the RFC-0041
# replay, not a tuning knob: the gate's rejected candidates survive only in
# this projection, so the evidence for the stage is evidence for 230.
PROJECTION_CLIP = 230

# Store neighbours shown to a judging stage. Same k on both stages (RFC-0042).
NEAREST_K = 5

_SECTION_RE_CACHE: dict[str, re.Pattern[str]] = {}


@dataclass(frozen=True)
class SkillProjection:
    """One skill as the judging stages see it.

    ``does`` / ``when`` are the clipped ``## Solution`` and ``## When to Use``
    sections when the document has them, and the clipped head of the body when
    it does not. Both readings occur: skills adopted before RFC-0042 carry the
    fixed template, while a body written by the split call is free prose. The
    fallback exists so a free-form candidate projects into a shape the judge
    can compare at all — two empty fields ask it to compare nothing — but it is
    NOT the projection the RFC-0041 replay measured, which had the template on
    both sides. The wording and the 230-character clip are unchanged; what the
    replay cannot vouch for is the prose-head reading of ``does``.
    """

    name: str
    description: str
    does: str
    when: str

    def render(self) -> str:
        """The block a prompt carries. The replay's ``_render``, field for field."""
        return f"### {self.name}\n{self.description}\nDoes: {self.does}\nWhen: {self.when}"

    @property
    def retrieval_doc(self) -> str:
        """What cosine ranks: name + description, as in the replay's ``_embed``."""
        return f"{self.name}: {self.description}"


def _section(text: str, heading: str) -> str:
    """The clipped, whitespace-collapsed body of one ``## heading`` section."""
    pattern = _SECTION_RE_CACHE.get(heading)
    if pattern is None:
        pattern = re.compile(r"##\s*" + re.escape(heading) + r"\s*\n(.*?)(?=\n## |\Z)", re.S)
        _SECTION_RE_CACHE[heading] = pattern
    match = pattern.search(text)
    return " ".join(match.group(1).split())[:PROJECTION_CLIP] if match else ""


def _body_head(text: str) -> str:
    """Clipped prose after the frontmatter and the title, sections stripped.

    The fallback for a free-form body: the judge is asked what the agent would
    do, and an empty ``Does:`` answers nothing.
    """
    from .text_utils import split_frontmatter

    _frontmatter, body = split_frontmatter(text)
    lines = [line for line in body.splitlines() if not line.startswith("#")]
    return " ".join(" ".join(lines).split())[:PROJECTION_CLIP]


def project_skill(text: str, *, fallback_name: str = "skill") -> SkillProjection:
    """Project one skill document."""
    name, description = skill_theme(text, fallback_name=fallback_name)
    does = _section(text, "Solution")
    when = _section(text, "When to Use")
    if not does and not when:
        does = _body_head(text)
    return SkillProjection(name=name, description=description, does=does, when=when)


def load_store_projections(skills_dir: Path | None) -> tuple[SkillProjection, ...]:
    """Project every adopted skill file, in filename order."""
    return tuple(
        project_skill(text, fallback_name=path.stem)
        for path, text in iter_markdown_documents(
            skills_dir, label="insight stages: unreadable skill file"
        )
    )


@dataclass(frozen=True)
class StoreIndex:
    """The store's projections plus their embeddings, built once per run.

    Built once because a weekly run asks it ~30 times and re-embedding a
    50-skill store per question would cost more than the judging calls. A
    degenerate or failed embedding yields ``None`` from :meth:`build` rather
    than a silently arbitrary ranking — the caller then fails the stage open
    with a reason code (same policy as the novelty gate's
    ``retrieval_unavailable``).
    """

    projections: tuple[SkillProjection, ...]
    vectors: object  # np.ndarray, (N, D), L2-normalized

    @classmethod
    def build(cls, skills_dir: Path | None) -> StoreIndex | None:
        projections = load_store_projections(skills_dir)
        if not projections:
            return None
        vectors = _embed_normalized([p.retrieval_doc for p in projections])
        if vectors is None:
            logger.warning(
                "insight stages: store embedding unavailable for %d skill(s) "
                "(reason=retrieval_unavailable)",
                len(projections),
            )
            return None
        return cls(projections=projections, vectors=vectors)

    def nearest(self, query: str, k: int = NEAREST_K) -> tuple[SkillProjection, ...] | None:
        """The k nearest store projections to *query*, nearest first.

        ``None`` when the query could not be embedded. Ties break by name so
        the slice is deterministic at temperature 0.

        Nothing is excluded by name. The replay's leave-one-out arm skipped the
        candidate's own store row because there the candidate WAS that row; in
        production a candidate lives in the staging directory and is never in
        this index, so a name match can only be a different skill that
        re-slugified the same way — which is the strongest duplicate evidence
        there is, not a self-match to drop (code review 2026-09-19).
        """
        import numpy as np

        query_vectors = _embed_normalized([query])
        if query_vectors is None:
            return None
        scores = np.asarray(self.vectors) @ np.asarray(query_vectors)[0]
        ranked = sorted(
            ((float(scores[i]), self.projections[i]) for i in range(len(self.projections))),
            key=lambda item: (-item[0], item[1].name),
        )
        return tuple(projection for _score, projection in ranked[:k])


def _embed_normalized(texts: list[str]) -> object | None:
    """Embed and L2-normalize, or ``None`` on failure / degeneracy.

    A zero-norm row would score every document 0.0 and hand back the
    alphabetically first k names wearing a ranking's clothes — the same
    degeneracy ``insight_novelty._embed_in_batches`` refuses.
    """
    import numpy as np

    from .embeddings import embed_texts

    matrix = embed_texts(texts)
    if matrix is None or len(matrix) != len(texts):
        return None
    array = np.asarray(matrix, dtype=np.float64)
    if not np.isfinite(array).all():
        return None
    norms = np.linalg.norm(array, axis=1, keepdims=True)
    if float(norms.min()) == 0.0:
        return None
    return array / norms
