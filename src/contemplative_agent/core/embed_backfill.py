"""Backfill missing pattern embeddings (P0-04.3).

When the embedder is down, ``distill`` degrades to "store the patterns with no
vector" (``_embed_patterns``). Such rows are invisible to dedup (``None`` is
always ADD), views and clustering until a vector is attached, and until now the
only repair was a manual script. This module is the shared body: ``distill``
calls it at the end of every non-dry run, and
``scripts/restore-embed-knowledge.py`` (post-restore rebuild) wraps it.

Two failure shapes, both explicit (ADR-0075, no silent fallback):

* nothing is written and ``BackfillError`` names a ``reason`` — an embedder that
  is down, or a batch that came back the wrong size. A half-embedded store would
  pass ``missing_embedding`` on the filled half only and hide the failure, so
  every vector is obtained before any row is touched;
* ``filled == 0`` with no error — nothing was missing.

The store is saved by the CALLER's choice (``save=True`` here for the script and
for distill's tail). Vectors land in the ADR-0108 sidecar through
``KnowledgeStore.save`` — one writer for the two-file layout.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import numpy as np

from .embeddings import embed_texts
from .knowledge_store import KnowledgeStore, is_live

logger = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 64

REASON_EMBED_UNAVAILABLE = "embed_unavailable"
REASON_SAVE_FAILED = "save_failed"
REASON_LOAD_FAILED = "load_failed"
REASON_DROPPED_ROWS = "dropped_rows"

Embedder = Callable[[list[str]], "np.ndarray | None"]


class BackfillError(Exception):
    """A backfill that wrote nothing; ``reason`` is the machine-greppable code."""

    def __init__(self, reason: str, detail: str) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


def count_missing(store: KnowledgeStore, *, live_only: bool = False) -> int:
    """Rows without a vector (the ``missing_embedding`` invariant's numerator)."""
    return len(_missing_rows(store.get_raw_patterns(), live_only))


def _missing_rows(rows: list[dict], live_only: bool) -> list[dict]:
    return [r for r in rows if not r.get("embedding") and (not live_only or is_live(r))]


def backfill_store(
    store: KnowledgeStore,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    live_only: bool = False,
    embed: Embedder | None = None,
) -> int:
    """Embed every row of an already-loaded *store* lacking a vector; save; return the count.

    Raises ``BackfillError`` (nothing written) when the store failed to load or
    holds non-pattern elements, a batch cannot be embedded, or the save fails. ``live_only`` limits the work to live rows — the scope of
    the ``missing_embedding`` invariant — which is what the scheduled distill
    tail wants; the manual restore script embeds every row.
    """
    # Saving would replace the file with only what the parser kept: a failed
    # load is an empty store, and dropped rows are elements it could not read.
    # Both refuse before anything is embedded or written.
    if store.load_failed:
        raise BackfillError(REASON_LOAD_FAILED, "knowledge store did not load")
    if store.dropped_rows:
        raise BackfillError(
            REASON_DROPPED_ROWS,
            f"{store.dropped_rows} element(s) are not pattern rows; saving would delete them",
        )
    embedder = embed if embed is not None else embed_texts
    # get_raw_patterns() copies the list, not the dicts — assigning into a row
    # below is the same object the store will serialize.
    missing = _missing_rows(store.get_raw_patterns(), live_only)
    if not missing:
        return 0

    vectors: list[list[float]] = []
    for start in range(0, len(missing), batch_size):
        chunk = missing[start : start + batch_size]
        embedded = embedder([r.get("pattern", "") for r in chunk])
        if embedded is None or embedded.shape[0] != len(chunk):
            raise BackfillError(
                REASON_EMBED_UNAVAILABLE,
                f"embedder unavailable at rows {start}..{start + len(chunk)} "
                f"of {len(missing)} missing",
            )
        vectors.extend(v.tolist() for v in embedded)

    for row, vec in zip(missing, vectors, strict=True):
        row["embedding"] = vec

    try:
        store.save()
    except Exception as exc:  # noqa: BLE001 — re-raised as a coded error
        raise BackfillError(REASON_SAVE_FAILED, f"{type(exc).__name__}: {exc}") from exc
    return len(missing)
