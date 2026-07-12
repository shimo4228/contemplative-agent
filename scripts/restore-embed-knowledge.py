#!/usr/bin/env python3
"""Backfill missing pattern embeddings in $MOLTBOOK_HOME/knowledge.json.

Two callers:

* **Post-restore** — the backup mirror stores knowledge.json embedding-free
  (the 768-dim vectors are model-locked to nomic-embed-text, re-derivable
  from pattern text, and ~97% of the raw file's weight). After restoring
  the mirror into MOLTBOOK_HOME, run this once to rebuild the vectors;
  until then views / dedup ignore embedding-less rows.
* **Embed-outage repair** — distill's graceful-degradation branch ADDs
  patterns with no embedding when Ollama is down; this backfills them.

Requires the project venv (imports the package) and a running Ollama with
the embedding model pulled. Fails loudly without writing when the embedder
is unreachable. Idempotent: rows that already carry a vector are untouched;
a fully-embedded store is a no-op that rewrites nothing.

Usage:
    uv run python scripts/restore-embed-knowledge.py
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from contemplative_agent.core._io import write_text_atomic
from contemplative_agent.core.embeddings import embed_texts

DEFAULT_BATCH_SIZE = 64


def backfill(knowledge_path: Path, batch_size: int = DEFAULT_BATCH_SIZE) -> int:
    """Embed every row lacking a vector; return how many were filled.

    Aborts via SystemExit without touching the file if any batch fails —
    a half-embedded store would pass the missing_embedding invariant on
    the filled half only and hide the failure.
    """
    rows = json.loads(knowledge_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise SystemExit(f"Error: expected a JSON array in {knowledge_path}")

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

    for i, vec in zip(missing, vectors):
        rows[i]["embedding"] = vec

    # Same shape knowledge_store.save() writes (indent=2, trailing newline),
    # so the next store save produces a minimal diff.
    write_text_atomic(knowledge_path, json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
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
