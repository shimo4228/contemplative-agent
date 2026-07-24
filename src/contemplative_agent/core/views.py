"""Views: seed-text driven semantic queries over knowledge.json (ADR-0019).

A view is a named seed text plus retrieval parameters. Queries embed the
seed and rank patterns by cosine similarity. This replaces the discrete
``subcategory`` field — the categorisation axis is no longer baked into
state, it lives as data in ``config/views/`` (templates) or
``~/.config/moltbook/views/`` (user-customised).

Seed file format (Markdown with optional YAML frontmatter):

    ---
    threshold: 0.65                    # optional, default 0.0 (no filter)
    top_k: 50                          # optional, default None
    seed_from: ${CONSTITUTION_DIR}/*.md # optional, inject seed from external files
    ---

    # Optional title (ignored)

    Seed text body (used when seed_from is absent or resolves to nothing).

When ``seed_from`` is present, the referenced files' contents replace the
body as the embedded seed. ``${VAR}`` placeholders are substituted from
``path_vars`` passed to ``ViewRegistry``. The value may contain glob
wildcards (``*``, ``?``). Relative paths resolve against the view file's
directory. If resolution yields zero readable files, the body is used as
fallback.

Role boundary — views vs prompts
--------------------------------

``config/views/`` and ``config/prompts/`` are both natural-language
config files, but they feed different machinery:

- **views** are *read-side*: the embedding model consumes the seed, and
  the result is a query-time ranking over patterns that already exist
  (ADR-0019 / ADR-0031, "classification as query").
- **prompts** are *write-side*: the generation LLM consumes them, and
  the result is new text.

Which pipelines consume views is deliberate, not an oversight. Retrieval
along a **predefined semantic axis** goes through a view
(``distill_identity`` → ``self_reflection``, ``amend_constitution`` →
``constitutional``). **Discovery of structure the operator has not
named** uses unsupervised clustering over the whole live pool instead
(``insight`` — see its module docstring). Do not add a view to insight
to "restore symmetry"; imposing a seed there would bias skill discovery
toward pre-named axes. The asymmetry is the design.

Register contract (ADR-0072)
----------------------------

Since 2026-07 the ``self_reflection`` view is not a neutral lens only:
it is the *read side* of a production→retrieval contract whose *write
side* is the register instruction in ``config/prompts/distill_episode.md``
(first-person, moment-indexed patterns). Editing either side alone can
silently break view supply — treat prompt and seed as a pair, and read
the view-supply instrument (``view_metrics``, surfaced at ``distill
--dry-run`` and the adopt gate) as the drift detector. The
``constitutional`` view has no such coupling: its seed is the live
constitution itself via ``seed_from``.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .embeddings import cosine, embed_one
from .knowledge_store import is_live

logger = logging.getLogger(__name__)

# Cache embedded seeds per ViewRegistry instance to avoid re-embedding on
# every query. Cleared when load_views() is called again.
_DEFAULT_THRESHOLD = 0.0
_DEFAULT_TOP_K: int | None = None


@dataclass(frozen=True)
class View:
    """A named semantic query over knowledge patterns."""

    name: str
    seed_text: str
    threshold: float = _DEFAULT_THRESHOLD
    top_k: int | None = _DEFAULT_TOP_K


_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
_VAR_RE = re.compile(r"\$\{(\w+)\}")


def _substitute_vars(value: str, path_vars: Mapping[str, Path]) -> str:
    """Replace ``${VAR}`` placeholders using path_vars. Unknown vars stay literal."""

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        replacement = path_vars.get(key)
        return str(replacement) if replacement is not None else m.group(0)

    return _VAR_RE.sub(repl, value)


def _resolve_seed_from(
    pattern: str,
    view_path: Path,
    path_vars: Mapping[str, Path],
) -> str | None:
    """Resolve a ``seed_from`` pattern to concatenated file contents.

    Returns ``None`` when no files match or all reads fail. Supports glob
    wildcards in the filename portion. Relative paths resolve against the
    view file's parent directory. ``${VAR}`` placeholders are substituted
    from ``path_vars``; unresolved placeholders cause fallback.
    """
    if "${" in pattern and _VAR_RE.search(pattern) is not None:
        substituted = _substitute_vars(pattern, path_vars)
        if "${" in substituted:
            logger.warning(
                "View %s: seed_from %r has unresolved placeholder — using body",
                view_path.name,
                pattern,
            )
            return None
    else:
        substituted = pattern

    p = Path(substituted)
    if not p.is_absolute():
        p = view_path.parent / p
    base = p.parent
    name = p.name
    try:
        matches = sorted(base.glob(name))
    except OSError as exc:
        logger.warning("View %s: seed_from glob failed: %s", view_path.name, exc)
        return None

    texts: list[str] = []
    for match in matches:
        try:
            body = match.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("View %s: seed_from read failed for %s: %s", view_path.name, match, exc)
            continue
        if body:
            texts.append(body)

    if not texts:
        logger.warning(
            "View %s: seed_from %r resolved to no readable content — using body",
            view_path.name,
            pattern,
        )
        return None
    return "\n\n".join(texts)


def _parse_frontmatter(front: str, view_name: str) -> tuple[float, int | None, str | None]:
    """Parse frontmatter lines; return (threshold, top_k, seed_from)."""
    threshold = _DEFAULT_THRESHOLD
    top_k: int | None = _DEFAULT_TOP_K
    seed_from: str | None = None
    for line in front.splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key == "threshold":
            try:
                threshold = float(value)
            except ValueError:
                logger.warning("View %s: invalid threshold %r", view_name, value)
        elif key == "top_k":
            try:
                top_k = int(value)
            except ValueError:
                logger.warning("View %s: invalid top_k %r", view_name, value)
        elif key == "seed_from":
            seed_from = value
    return threshold, top_k, seed_from


def _parse_seed_file(
    path: Path,
    path_vars: Mapping[str, Path] | None = None,
) -> View:
    """Parse a seed file into a View. Frontmatter is optional."""
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    threshold = _DEFAULT_THRESHOLD
    top_k: int | None = _DEFAULT_TOP_K
    seed_from: str | None = None
    if match:
        front, body = match.group(1), match.group(2)
        threshold, top_k, seed_from = _parse_frontmatter(front, path.name)
    else:
        body = raw

    seed_text = body.strip()
    if seed_from:
        injected = _resolve_seed_from(seed_from, path, path_vars or {})
        if injected is not None:
            seed_text = injected

    return View(
        name=path.stem,
        seed_text=seed_text,
        threshold=threshold,
        top_k=top_k,
    )


class ViewRegistry:
    """Loads view definitions from a directory and caches their embeddings."""

    def __init__(
        self,
        views_dir: Path | None = None,
        path_vars: Mapping[str, Path] | None = None,
    ) -> None:
        self._views_dir = views_dir
        self._path_vars: Mapping[str, Path] = path_vars or {}
        self._views: dict[str, View] = {}
        self._centroids: dict[str, np.ndarray] = {}
        self._loaded = False

    def load_views(self) -> dict[str, View]:
        """Read all *.md files in views_dir into View instances.

        Returns the loaded views dict. Embedding of seed texts is
        deferred to first query (lazy) to avoid hitting Ollama during
        cold imports. Seed content is validated against the same
        forbidden-pattern list as identity.md — views are user-editable
        after ``init`` copies them to ``$MOLTBOOK_HOME/views/``.
        """
        from .llm import validate_identity_content

        self._views = {}
        self._centroids = {}
        self._loaded = True
        if self._views_dir is None or not self._views_dir.exists():
            return {}
        for path in sorted(self._views_dir.glob("*.md")):
            try:
                view = _parse_seed_file(path, self._path_vars)
            except OSError as exc:
                logger.warning("Failed to read view %s: %s", path, exc)
                continue
            if view.seed_text and not validate_identity_content(view.seed_text):
                logger.warning(
                    "View %s failed pattern validation; skipping",
                    path.name,
                )
                continue
            self._views[view.name] = view
        return dict(self._views)

    def names(self) -> list[str]:
        if not self._loaded:
            self.load_views()
        return sorted(self._views.keys())

    def get(self, name: str) -> View | None:
        if not self._loaded:
            self.load_views()
        return self._views.get(name)

    def get_centroid(self, name: str) -> np.ndarray | None:
        """Return the embedding of the view's seed text, embedding on first call."""
        if not self._loaded:
            self.load_views()
        cached = self._centroids.get(name)
        if cached is not None:
            return cached
        view = self._views.get(name)
        if view is None:
            return None
        emb = embed_one(view.seed_text)
        if emb is None:
            logger.warning("Failed to embed seed text for view %s", name)
            return None
        self._centroids[name] = emb
        return emb

    def find_by_view(
        self,
        view_name: str,
        candidates: list[dict],
    ) -> list[dict]:
        """Return patterns from ``candidates`` ranked by cosine.

        ``candidates`` is a list of pattern dicts each containing an
        ``embedding`` field (List[float]). Patterns without embeddings
        are skipped silently. Applies the view's threshold and top_k.
        """
        view = self.get(view_name)
        if view is None:
            logger.warning("Unknown view: %s", view_name)
            return []
        seed_emb = self.get_centroid(view_name)
        if seed_emb is None:
            return []
        return self._rank(seed_emb, candidates, view.threshold, view.top_k)

    @staticmethod
    def _rank(
        seed_emb: np.ndarray,
        candidates: list[dict],
        threshold: float,
        top_k: int | None,
    ) -> list[dict]:
        """Rank candidates by raw cosine similarity.

        Pure read, pure semantics: a candidate makes the cut iff it is
        live (bitemporal), clears ``threshold``, and survives ``top_k``
        by cosine rank. ADR-0028 retired the Ebbinghaus ``strength``
        factor and the ``mark_access`` side-effect; ADR-0051 retired the
        ADR-0021 trust multiplier (origin is recorded in provenance,
        never weighted).
        """
        scored: list[tuple] = []
        for pat in candidates:
            emb = pat.get("embedding")
            if not emb:
                continue
            if not is_live(pat):
                continue
            vec = np.asarray(emb, dtype=np.float32)
            sim = cosine(seed_emb, vec)
            if sim < threshold:
                continue
            scored.append((sim, pat))
        scored.sort(key=lambda t: t[0], reverse=True)
        if top_k is not None:
            scored = scored[:top_k]
        return [pat for _, pat in scored]
