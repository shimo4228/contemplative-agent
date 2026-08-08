"""Shared step for resolving an LLM artifact body to a safe file path.

Both ``insight`` and ``rules-distill`` produce Markdown bodies that need
the same chain: ``extract_title → slugify → path-escape guard``. This
module hosts that chain so a fix (for example, tightening the path
guard) only needs to land in one place.

ADR-0035 PR3a explicitly rejects a base-class framing for the broader
"extract → validate → stage" loop. The LLM call, the marker semantics
(``_NO_RULES_MARKER``), the multi-output split, and the frontmatter
merge differ enough across the callers that pulling them into a parent
re-creates the ADR-0024/0025 overgeneralization that ADR-0030 had to
withdraw. The helper here is scoped tightly to the genuinely shared
step.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .text_utils import extract_title, slugify, split_frontmatter

logger = logging.getLogger(__name__)

_FRONTMATTER_NAME_RE = re.compile(r"^name:.*$", re.MULTILINE)

# Inverse of the ``<slug>-YYYYMMDD.md`` naming that resolve_artifact_path
# composes, plus the optional ``-N`` counter that the adopt-time collision
# guard (cli.approval._collision_free_path) may append after the date.
_DATED_STEM_RE = re.compile(r"^(?P<slug>.+)-\d{8}(?P<counter>-\d+)?$")


@dataclass(frozen=True)
class ResolvedArtifactPath:
    """A title-derived filename plus its safe target path.

    ``slug`` is the date-free stem of ``filename`` — the single token the
    caller can write back into the body's frontmatter so filename and
    declared identity cannot diverge.
    """

    filename: str
    target_path: Path
    slug: str


def resolve_artifact_path(
    body: str,
    target_dir: Path | None,
    *,
    label: str,
) -> ResolvedArtifactPath | None:
    """Derive ``<slug>-YYYYMMDD.md`` from *body* and check it against escape.

    Returns ``None`` when:

    - ``body`` has no ``# `` heading, or the heading slugifies to empty.
    - The resolved path escapes ``target_dir``.

    The caller increments its own ``dropped_count``; this helper only
    logs the rejection reason. ``label`` shows up in the log line so a
    grep over real runs can attribute the drop to a specific batch
    (e.g. ``"Batch 3/7 [reasoning]"``).
    """
    title = extract_title(body) or ""
    slug = slugify(title)
    if not slug:
        logger.warning("%s: empty slug, dropping", label)
        return None
    today = date.today().strftime("%Y%m%d")
    filename = f"{slug}-{today}.md"
    if target_dir is None:
        return ResolvedArtifactPath(filename=filename, target_path=Path(filename), slug=slug)
    path = target_dir / filename
    if not path.resolve().is_relative_to(target_dir.resolve()):
        logger.error("%s path escape attempt: %s", label, path)
        return None
    return ResolvedArtifactPath(filename=filename, target_path=path, slug=slug)


def slug_from_stem(stem: str) -> str:
    """Return the date-free identity token for a final target filename stem.

    Inverts :func:`resolve_artifact_path`'s ``<slug>-YYYYMMDD`` naming while
    preserving a trailing ``-N`` collision counter: a collision-renamed file
    (``foo-20260801-2.md``) must carry a declared name distinct from the file
    it collided with (``foo`` vs ``foo-2``), or the two would re-collide in
    every consumer that keys on the declared name (``skill_theme`` selector
    key, novelty dedup, stocktake clustering). Stems without a date suffix
    (identity/constitution targets, legacy names) are returned unchanged.
    """
    m = _DATED_STEM_RE.match(stem)
    if not m:
        return stem
    return m.group("slug") + (m.group("counter") or "")


def canonicalize_frontmatter_name(text: str, slug: str) -> str:
    """Return *text* with its frontmatter ``name:`` scalar set to *slug*.

    The extraction prompt emits two free-form identity strings: the
    frontmatter ``name:`` and the ``# `` heading. Only the heading decides
    the filename (:func:`resolve_artifact_path`), while ``skill_theme``
    reads the frontmatter name — so a candidate could be filed, selected
    and ledgered under three different tokens. Rewriting the scalar with
    the resolved slug at stage time makes filename, declared name and
    ledger identity the same token by construction; the heading stays as
    the human-readable title (it is what pass-2 injection carries).

    Bodies without frontmatter are returned unchanged — ``skill_theme``
    already falls back to the filename stem for those.
    """
    frontmatter, body = split_frontmatter(text)
    if not frontmatter:
        return text
    rewritten, count = _FRONTMATTER_NAME_RE.subn(f"name: {slug}", frontmatter, count=1)
    if count == 0:
        lines = frontmatter.split("\n")
        lines.insert(1, f"name: {slug}")
        rewritten = "\n".join(lines)
    return f"{rewritten}\n\n{body}"
