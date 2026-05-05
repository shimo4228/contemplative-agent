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
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from .text_utils import extract_title, slugify

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResolvedArtifactPath:
    """A title-derived filename plus its safe target path."""

    filename: str
    target_path: Path


def resolve_artifact_path(
    body: str,
    target_dir: Optional[Path],
    *,
    label: str,
) -> Optional[ResolvedArtifactPath]:
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
        return ResolvedArtifactPath(filename=filename, target_path=Path(filename))
    path = target_dir / filename
    if not path.resolve().is_relative_to(target_dir.resolve()):
        logger.error("%s path escape attempt: %s", label, path)
        return None
    return ResolvedArtifactPath(filename=filename, target_path=path)
