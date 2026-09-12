"""Layer 1: EpisodeLog — append-only daily JSONL episode storage."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ._io import append_jsonl_restricted

logger = logging.getLogger(__name__)

# Daily files held by the per-instance read memo. The hot path is the 7-day
# window the feed gate re-reads once per candidate post; the one-shot 30-day
# rebuild (memory_repos._build_cache) then merely misses, which costs exactly
# what an uncached read costs today.
_FILE_MEMO_MAX = 8


class EpisodeLog:
    """Append-only episode log stored as daily JSONL files.

    Each line: {"ts": "ISO8601", "type": "interaction|post|activity|session|dialogue",
    "data": {...}}. Those five are the whole written vocabulary; readers that
    branch on type must tolerate the historical type="insight" records still
    sitting in old daily files (retired by ADR-0052 — nothing appends or loads
    them, and episode_render treats one reaching it as a bug).
    """

    def __init__(self, log_dir: Path | None = None) -> None:
        self._log_dir = log_dir
        self._memo: dict[Path, tuple[tuple[int, int], list[dict[str, Any]]]] = {}

    def _today_path(self) -> Path | None:
        return self._path_for_date(datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    def _path_for_date(self, date_str: str) -> Path | None:
        if self._log_dir is None:
            return None
        return self._log_dir / f"{date_str}.jsonl"

    def append(self, record_type: str, data: dict[str, Any]) -> None:
        """Append a record immediately to today's log file."""
        path = self._today_path()
        if path is None:
            return
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": record_type,
            "data": data,
        }
        try:
            append_jsonl_restricted(path, record)
        except OSError as exc:
            logger.warning("Failed to write episode log: %s", exc)

    def read_range(self, days: int = 1, record_type: str | None = None) -> list[dict[str, Any]]:
        """Read records from the last N days.

        Args:
            days: Number of days to look back.
            record_type: If given, filter to records with this type
                         (e.g. "post", "insight", "interaction").
        """
        if self._log_dir is None:
            return []
        records: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            path = self._path_for_date(date_str)
            if path is not None:
                records.extend(self._read_file_memoized(path))
        if record_type is not None:
            records = [r for r in records if r.get("type") == record_type]
        return records

    def _read_file_memoized(self, path: Path) -> list[dict[str, Any]]:
        """:meth:`read_file`, memoized per instance on ``(mtime_ns, size)``.

        Past days are append-only and never change, yet ``read_range`` is called
        once per candidate post by the feed gate
        (``memory_repos.prior_comment_targets``), re-parsing the same week each
        time. Today's file does change — the stat key invalidates on every
        append, so a stale read is not reachable.

        A fresh list is returned each call, but the record dicts are shared:
        ``read_range`` consumers read records, they never mutate them.
        """
        try:
            st = path.stat()
        except OSError:
            # Missing (or unreadable) — read_file owns that branch, including
            # its warning, and nothing is worth memoizing.
            return self.read_file(path)
        key = (st.st_mtime_ns, st.st_size)
        cached = self._memo.get(path)
        if cached is not None and cached[0] == key:
            return list(cached[1])
        records = self.read_file(path)
        if len(self._memo) >= _FILE_MEMO_MAX and path not in self._memo:
            self._memo.pop(next(iter(self._memo)))
        self._memo[path] = (key, records)
        return list(records)

    @staticmethod
    def read_file(path: Path) -> list[dict[str, Any]]:
        """Read all JSON lines from a single JSONL file."""
        if not path.exists():
            return []
        records = []
        try:
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed log line in %s", path.name)
        except OSError as exc:
            logger.warning("Failed to read log file %s: %s", path.name, exc)
        return records
