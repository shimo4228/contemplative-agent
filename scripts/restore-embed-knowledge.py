#!/usr/bin/env python3
"""Backfill missing pattern embeddings in $MOLTBOOK_HOME/knowledge.json.

Two callers:

* **Post-restore** — neither the backup mirror nor the research sync carries
  the vectors (they are model-locked to nomic-embed-text, re-derivable from
  pattern text, and were ~97% of the raw file's weight before ADR-0108 moved
  them to ``pattern-embeddings.sqlite``). After restoring the mirror into
  MOLTBOOK_HOME, run this once to rebuild the sidecar; until then views /
  dedup ignore embedding-less rows and ``state_invariant_check.py`` reports
  them under ``missing_embedding``.
* **Embed-outage repair** — distill's graceful-degradation branch ADDs
  patterns with no embedding when Ollama is down; this backfills them. Since
  P0-04.3 distill's own tail does the same automatically (live rows), so this
  script is for the post-restore rebuild and for a store distill has not
  touched.

Writes through ``KnowledgeStore`` rather than editing the JSON in place, so
the vectors land in the ADR-0108 sidecar and the JSON stays text-only — one
writer for the two-file layout, not two.

Requires the project venv (imports the package) and a running Ollama with
the embedding model pulled. Fails loudly without writing when the embedder
is unreachable. Idempotent in effect: rows that already carry a vector keep
it, and a fully-embedded store is a no-op that rewrites nothing. It is not a
verbatim round-trip, though — a run that does fill something rewrites the
whole array through the store's own parser, which sheds fields retired by
ADR-0028 / 0051 / 0056. It refuses outright if the file holds elements the
parser cannot read as pattern rows, since saving would delete them.

Usage:
    uv run python scripts/restore-embed-knowledge.py
"""

from __future__ import annotations

import os
from pathlib import Path

from contemplative_agent.core.embed_backfill import (
    DEFAULT_BATCH_SIZE,
    BackfillError,
    backfill_store,
)
from contemplative_agent.core.embeddings import embed_texts
from contemplative_agent.core.knowledge_store import KnowledgeStore


def backfill(knowledge_path: Path, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Embed every row lacking a vector; return how many were filled.

    The body lives in ``core/embed_backfill.py`` (P0-04.3: distill's tail runs
    the same code). Aborts via SystemExit without touching either file if any
    batch fails — a half-embedded store would pass the missing_embedding
    invariant on the filled half only and hide the failure. Every vector is
    obtained before anything is saved, so the abort is total.
    """
    store = KnowledgeStore(path=knowledge_path)
    store.load()
    if store.load_failed:
        raise SystemExit(
            f"Error: {knowledge_path} could not be loaded (unreadable, tainted or "
            "not a JSON array) — nothing written."
        )
    if store.dropped_rows:
        raise SystemExit(
            f"Error: {knowledge_path} has {store.dropped_rows} element(s) that are not "
            "pattern rows. Saving would delete them, so nothing was written. Fix or "
            "remove them first."
        )
    try:
        return backfill_store(store, batch_size=batch_size, embed=embed_texts)
    except BackfillError as exc:
        raise SystemExit(
            f"Error: {exc.detail} — nothing written (reason={exc.reason}). "
            "Is Ollama up with the embedding model pulled?"
        ) from exc


def main() -> None:
    home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    knowledge_path = home / "knowledge.json"
    if not knowledge_path.is_file():
        raise SystemExit(f"Error: {knowledge_path} not found")

    filled = backfill(knowledge_path)
    if filled == 0:
        print("All rows already embedded — nothing to do.")
    else:
        print(f"Backfilled {filled} embeddings in {knowledge_path}")


if __name__ == "__main__":
    main()
