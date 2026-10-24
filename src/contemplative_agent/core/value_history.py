"""Version history for the two replaced value-layer files (P3-04.2, D-P3-04-1 = C).

``identity.md`` and the constitution are overwritten in place on adoption, so
the only record of an earlier version was a pivot snapshot, and since ADR-0020's
2026-10-24 amendment those survive but sit inside run-start copies. This module
writes one verbatim copy of each adopted version under ``$MOLTBOOK_HOME`` so the
public tree (a ``sync-data`` rsync of that home) carries a time-ordered history
without GitHub archaeology:

- identity     -> ``history/identity/<UTC ts>-<sha12>.md``
- constitution -> ``constitution/history/<UTC date>-<sha12>.md``, plus an entry
  for it in ``constitution/history/lineage.json`` (``constitution_lineage``)

The file is the adopted bytes, nothing added, so ``sha256(file)[:12]`` equals the
name's suffix and equals the live file's hash at that moment. Provenance (who
adopted, by which route) stays in the private ``audit.jsonl``; the history files
carry none, and ``constitution/CHANGELOG.md`` is the readable ledger.

It lives under the data home on purpose. The sync is ``rsync --delete`` from that
home, so a file placed only in the data repo would be deleted at the next run;
a file the home owns is carried through. The constitution loader and the pivot
snapshot both read ``constitution/*.md`` flat (no recursion), so the subfolder
changes neither the injected text nor the snapshot contents.

Best-effort: the adoption has already been written and audited when this runs;
a failure here is logged and never undoes or blocks it. It never overwrites an
existing history file (same name means same date and same bytes).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path

from ._io import write_restricted
from .constitution_lineage import upsert_lineage

logger = logging.getLogger(__name__)

IDENTITY_HISTORY_DIR = Path("history") / "identity"
CONSTITUTION_HISTORY_DIR = Path("constitution") / "history"


def history_path(command: str, text: str, data_root: Path, now: datetime) -> Path | None:
    """Where the adopted ``text`` of ``command`` belongs, or None for other commands."""
    sha12 = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    if command == "distill-identity":
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        return data_root / IDENTITY_HISTORY_DIR / f"{stamp}-{sha12}.md"
    if command == "amend-constitution":
        return data_root / CONSTITUTION_HISTORY_DIR / f"{now.strftime('%Y-%m-%d')}-{sha12}.md"
    return None


def record_value_history(
    command: str,
    text: str,
    data_root: Path,
    *,
    now: datetime | None = None,
) -> Path | None:
    """Write the adopted ``text`` to its history file; return the path or None.

    ``text`` must be the exact bytes written to the live file (trailing newline
    included), so the name's sha12 matches the live file's hash.
    """
    stamp = now or datetime.now(timezone.utc)
    try:
        path = history_path(command, text, data_root, stamp)
        if path is None:
            return None
        if path.exists():
            return path
        path.parent.mkdir(parents=True, exist_ok=True)
        write_restricted(path, text)
        if command == "amend-constitution":
            # P3-04.12: the section -> technique map rides with the version.
            upsert_lineage(path.parent / "lineage.json", path.name, text)
        return path
    except (OSError, ValueError) as exc:
        logger.warning("value-history write failed for %s: %s", command, exc)
        return None
