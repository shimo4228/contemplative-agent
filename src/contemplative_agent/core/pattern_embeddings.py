"""ADR-0108: SQLite sidecar for pattern embeddings, keyed by pattern id.

``knowledge.json`` keeps what the value layer is observed for — pattern text,
provenance, bitemporal validity — and the 768-dim vectors live here instead.
The split is worth 97% of that file's bytes and, with them, the 8-second taint
scan and the 1.6 GB parse peak measured on 2026-09-12.

The key is ``knowledge_store.pattern_id`` (ADR-0050's content hash of
``distilled|pattern``), so nothing new is persisted to identify a row.

Deliberately not shared with :mod:`.episode_embeddings`, which is the same
idea one table over: that store carries a ``ts`` column and an index on it to
serve a time-range read the pattern store has no use for, and its live writer
(``novelty.PostEmbeddingCache``) sits on the publish path. Generalizing the two
would put a shared base class under a hot adapter path to save a schema string.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

PATTERN_EMBEDDINGS_FILENAME = "pattern-embeddings.sqlite"

# Python's sqlite3 default is 5 s. Before ADR-0108 the store's whole save was
# one atomic JSON rename with last-writer-wins semantics and no contention to
# lose to; the sidecar reintroduces a lock, and the weekly chain, a scheduled
# session and an operator script can all reach this file. 30 s is longer than
# any single write here takes (0.134 s for the full 8.5k-row rewrite) so it
# absorbs overlap without turning a real deadlock into a hang.
_BUSY_TIMEOUT_S = 30.0


def _is_busy(exc: sqlite3.Error) -> bool:
    """True when *exc* is lock contention rather than a damaged file.

    The distinction is load-bearing: a corrupt sidecar should degrade to "no
    vectors, all rows are re-derivation candidates" (ADR-0108 D3), but a
    momentary lock degrading the same way would silently run a whole distill
    with zero vectors — dedup and views skip embedding-less rows, so the run
    would re-add duplicates and return nothing, with a WARNING for evidence.
    Contention is loud; damage is named.
    """
    return isinstance(exc, sqlite3.OperationalError) and (
        "locked" in str(exc).lower() or "busy" in str(exc).lower()
    )


def sidecar_path_for(knowledge_path: Path) -> Path:
    """The sidecar that belongs to *knowledge_path* — its sibling."""
    return knowledge_path.parent / PATTERN_EMBEDDINGS_FILENAME


@dataclass(frozen=True)
class SidecarConsistency:
    """What the two halves of the store looked like at the last ``load()``.

    The store is two files (ADR-0108 D3) and a restore can produce half of it,
    so every half-state gets a reason code instead of an absent vector nobody
    can account for. ``missing_ids`` is the re-derivation worklist.
    """

    total_rows: int = 0
    hydrated: int = 0
    inline_legacy: int = 0
    sidecar_absent: bool = False
    sidecar_unreadable: bool = False
    row_missing: int = 0
    dim_mismatch: int = 0
    orphan_vectors: int = 0
    missing_ids: tuple[str, ...] = field(default_factory=tuple)

    @property
    def clean(self) -> bool:
        """True when neither half is missing anything the other claims."""
        return not self.reason_codes()

    def reason_codes(self) -> list[str]:
        """Every code that fired, in the order ADR-0108 D3 lists them."""
        codes = []
        if self.inline_legacy:
            codes.append("inline_legacy")
        if self.sidecar_absent:
            codes.append("sidecar_absent")
        if self.sidecar_unreadable:
            codes.append("sidecar_unreadable")
        if self.row_missing:
            codes.append("row_missing")
        if self.dim_mismatch:
            codes.append("dim_mismatch")
        if self.orphan_vectors:
            codes.append("orphan_vectors")
        return codes

    def describe(self) -> str:
        """One line naming the counts behind the codes, for the WARNING."""
        return (
            f"rows={self.total_rows} hydrated={self.hydrated} "
            f"inline_legacy={self.inline_legacy} sidecar_absent={self.sidecar_absent} "
            f"sidecar_unreadable={self.sidecar_unreadable} "
            f"row_missing={self.row_missing} dim_mismatch={self.dim_mismatch} "
            f"orphan_vectors={self.orphan_vectors}"
        )


def _row_to_vector(row: tuple[str, int, bytes]) -> tuple[str, np.ndarray | None]:
    """Decode one stored row, checking the blob against its recorded ``dim``.

    This is what the ``dim`` column is for. Reconstructing the width from the
    blob length alone would make a truncated write look like a legitimately
    narrower vector, which the loader would then either use or blame on an
    embedding-model change — both wrong answers to "these bytes are damaged".
    """
    pid, dim, blob = row
    vec = np.frombuffer(blob, dtype=np.float32)
    if int(dim) != int(vec.shape[0]):
        logger.warning(
            "Pattern embedding %s is %d wide but records dim=%d — blob truncated or "
            "written by another writer; treated as absent",
            pid,
            vec.shape[0],
            dim,
        )
        return pid, None
    return pid, vec


class PatternEmbeddingStore:
    """SQLite store mapping pattern_id → float32 vector.

    ``dim`` is stored beside the blob rather than inferred from its length so
    a width change (an embedding-model swap without a re-backfill) is a value
    the loader can compare, not a division it has to trust.

    A ``None`` path makes every method inert, which is what an in-memory
    ``KnowledgeStore`` (tests, ``--dry-run`` paths) needs.
    """

    _SCHEMA = """
        CREATE TABLE IF NOT EXISTS pattern_embeddings (
            pattern_id TEXT PRIMARY KEY,
            dim INTEGER NOT NULL,
            vector BLOB NOT NULL
        );
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path
        self._initialized = False

    @property
    def path(self) -> Path | None:
        return self._db_path

    def exists(self) -> bool:
        return self._db_path is not None and self._db_path.exists()

    def _ensure_initialized(self) -> None:
        if self._initialized or self._db_path is None:
            self._initialized = True
            return
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        # Same 0600 posture as the episode sidecar: this file is derived from
        # pattern text that the store itself keeps unreadable to other users.
        old_umask = os.umask(0o177)
        try:
            with self._connect() as conn:
                conn.executescript(self._SCHEMA)
        finally:
            os.umask(old_umask)
        self._initialized = True

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._db_path is None:
            raise RuntimeError("PatternEmbeddingStore has no db_path configured")
        conn = sqlite3.connect(str(self._db_path), timeout=_BUSY_TIMEOUT_S)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def upsert_many(self, items: Iterable[tuple[str, np.ndarray]]) -> int:
        """Bulk insert/replace. Returns the number of rows written."""
        if self._db_path is None:
            return 0
        rows = [
            (pid, int(vec.shape[0]), np.ascontiguousarray(vec, dtype=np.float32).tobytes())
            for pid, vec in items
        ]
        if not rows:
            return 0
        self._ensure_initialized()
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR REPLACE INTO pattern_embeddings (pattern_id, dim, vector) "
                "VALUES (?, ?, ?)",
                rows,
            )
        return len(rows)

    def get_all(self) -> dict[str, np.ndarray] | None:
        """Every stored vector by id, or ``None`` when the file is unreadable.

        The load path wants the whole table — 8.5k rows read in 18 ms — so
        there is no id-staging query here of the kind the episode store needs
        for its per-batch lookups.

        ``None`` is the third answer a two-file store needs, distinct from the
        empty dict: an interrupted restore can leave a truncated or non-SQLite
        file here, and ADR-0108 D3 promises every half-state a reason code
        rather than an exception out of ``load()``. The caller degrades to
        "no vectors, all rows are re-derivation candidates", which
        ``scripts/restore-embed-knowledge.py`` then repairs.
        """
        if not self.exists():
            return {}
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT pattern_id, dim, vector FROM pattern_embeddings"
                ).fetchall()
            return {pid: vec for pid, vec in (_row_to_vector(r) for r in rows) if vec is not None}
        except (sqlite3.Error, ValueError, TypeError) as exc:
            if isinstance(exc, sqlite3.Error) and _is_busy(exc):
                raise
            logger.warning(
                "Pattern embedding sidecar at %s is unreadable (%s) — every row becomes a "
                "re-derivation candidate; run scripts/restore-embed-knowledge.py",
                self._db_path,
                exc,
            )
            return None

    def count(self) -> int:
        if not self.exists():
            return 0
        try:
            # Inside the guard: initialization itself opens the file, so a
            # damaged one raises here rather than at the query.
            self._ensure_initialized()
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM pattern_embeddings").fetchone()
        except sqlite3.Error as exc:
            if _is_busy(exc):
                raise
            logger.warning("Cannot count the pattern embedding sidecar (%s)", exc)
            return 0
        return int(row[0]) if row else 0

    def prune(self, keep_ids: set[str]) -> int:
        """Delete vectors no pattern claims. Returns how many were removed.

        Not called from ``save()``: a vector whose row was soft-invalidated
        today may be claimed again by a revision tomorrow, and an orphan costs
        3 KB. Pruning is an operator action (the migration script offers it).
        """
        if not self.exists():
            return 0
        # A file that exists but has no table (an interrupted first save, or a
        # zero-byte file left by rsync) must not raise here: prune runs in the
        # migration script *after* the store has already been rewritten, so a
        # traceback lands at the point the runbook says the migration worked.
        try:
            self._ensure_initialized()
            with self._connect() as conn:
                stored = {
                    pid for (pid,) in conn.execute("SELECT pattern_id FROM pattern_embeddings")
                }
                doomed = stored - keep_ids
                if not doomed:
                    return 0
                conn.executemany(
                    "DELETE FROM pattern_embeddings WHERE pattern_id = ?", ((p,) for p in doomed)
                )
        except sqlite3.Error as exc:
            if _is_busy(exc):
                raise
            logger.warning("Cannot prune the pattern embedding sidecar (%s)", exc)
            return 0
        return len(doomed)
