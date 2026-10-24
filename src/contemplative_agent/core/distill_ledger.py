"""Processed-episode ledger for ``distill`` (P0-04.1, ADR-0060 amendment).

``distill`` used to read a calendar window (``read_range(days)``: today's UTC
file for ``--days 1``) and keep no memory of what it had processed. Two
consequences, both structural:

* Episodes appended after the daily run (the 21Z / 06:00 JST session) land in
  a file whose date the NEXT run no longer reads, so they were never distilled.
* An episode that abstained on a backend fault (``llm_none`` ...) was lost
  with the day's window.

The ledger replaces "which calendar day" with "which episodes". The window is
the last ``LEDGER_MIN_WINDOW_DAYS`` or more UTC day-files, minus the episodes
already processed. Recorded: episodes **distilled successfully** and episodes
the model **judged** to hold nothing durable (a verdict; judging it again would
give the durability gate a second draw). A **fault** abstain (``llm_none``,
``empty_render``, ``shape_violation``) is not recorded, so the next run retries
it while it is still inside the window.

Append-only JSONL (ADR-0075), one row per episode:
``{"episode_id": <the record's ts>, "processed_at": <iso>}`` plus the
``run_id`` / ``session_id`` that ``append_jsonl_restricted`` stamps. The
``episode_id`` is the same value distill already stores as
``provenance.source_episode_ids``, so the ledger holds no episode text.

Pure functions over a ``Path``; the caller (the CLI composition root) decides
where the file lives, and ``None`` means "no ledger" (the legacy calendar
window), which keeps library callers and tests that do not care unchanged.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from pathlib import Path

from ._io import append_jsonl_restricted, now_iso

logger = logging.getLogger(__name__)

# The window must be at least two UTC day-files: a run that starts at 18:30Z
# must still see the previous day's late (21Z+) episodes, and a late start that
# crosses 00:00Z must still see the day it was scheduled for.
LEDGER_MIN_WINDOW_DAYS = 2

# Reason code for a ledger write that did not reach disk (ADR-0075: no silent
# fallback). The run itself has already saved its patterns by then.
LEDGER_WRITE_FAILED = "ledger_write_failed"


def read_processed_ids(path: Path | None) -> set[str]:
    """Episode ids recorded in the ledger; empty when absent or unreadable.

    Malformed lines are skipped (an append interrupted mid-line must not
    disable the whole ledger); an unreadable file is reported and treated as
    empty — the cost of that is one redundant, dedup-absorbed re-run.
    """
    ids: set[str] = set()
    if path is None:
        return ids
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed distill ledger line in %s", path.name)
                    continue
                eid = row.get("episode_id") if isinstance(row, dict) else None
                if isinstance(eid, str) and eid:
                    ids.add(eid)
    except FileNotFoundError:
        return ids
    except OSError as exc:
        logger.warning("Failed to read distill ledger %s: %s", path.name, exc)
    return ids


def stored_episode_ids(patterns: Iterable[dict]) -> set[str]:
    """Episode ids already carried by stored patterns' provenance.

    Read-only seed for the first ledger run: everything the store already
    distilled counts as processed, so introducing the ledger does not re-run a
    whole window that the old calendar-day run had finished.
    """
    ids: set[str] = set()
    for p in patterns:
        prov = p.get("provenance")
        if not isinstance(prov, dict):
            continue
        for eid in prov.get("source_episode_ids") or ():
            if isinstance(eid, str) and eid:
                ids.add(eid)
    return ids


def record_processed(path: Path, episode_ids: Iterable[str]) -> int:
    """Append one row per id; return how many reached disk.

    A failed append is logged with ``reason=ledger_write_failed`` and stops the
    batch: the ids not written are simply retried by the next run, and dedup
    absorbs the repeat.
    """
    written = 0
    stamp = now_iso(timespec="seconds")
    for eid in episode_ids:
        try:
            append_jsonl_restricted(path, {"episode_id": eid, "processed_at": stamp})
        except OSError as exc:
            logger.warning(
                "Distill ledger append failed: reason=%s path=%s err=%s",
                LEDGER_WRITE_FAILED,
                path.name,
                exc,
            )
            break
        written += 1
    return written
