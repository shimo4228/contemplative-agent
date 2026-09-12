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
  patterns with no embedding when Ollama is down; this backfills them.

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

from contemplative_agent.core.embeddings import embed_texts
from contemplative_agent.core.knowledge_store import KnowledgeStore

DEFAULT_BATCH_SIZE = 64


def backfill(knowledge_path: Path, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Embed every row lacking a vector; return how many were filled.

    Aborts via SystemExit without touching either file if any batch fails —
    a half-embedded store would pass the missing_embedding invariant on
    the filled half only and hide the failure. Every vector is obtained
    before anything is saved, so the abort is total.
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
    # get_raw_patterns() copies the list, not the dicts — assigning into a
    # row below is the same object the store will serialize.
    rows = store.get_raw_patterns()

    missing = [i for i, r in enumerate(rows) if not r.get("embedding")]
    if not missing:
        return 0

    vectors: list[list[float]] = []
    for start in range(0, len(missing), batch_size):
        chunk = missing[start : start + batch_size]
        embedded = embed_texts([rows[i].get("pattern", "") for i in chunk])
        if embedded is None or embedded.shape[0] != len(chunk):
            raise SystemExit(
                f"Error: embedder unavailable at rows {start}..{start + len(chunk)} "
                f"of {len(missing)} missing — nothing written. Is Ollama up with "
                "the embedding model pulled?"
            )
        vectors.extend(v.tolist() for v in embedded)

    for i, vec in zip(missing, vectors, strict=True):
        rows[i]["embedding"] = vec

    store.save()
    return len(missing)


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
