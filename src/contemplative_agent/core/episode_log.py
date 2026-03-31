"""Layer 1: EpisodeLog — append-only daily JSONL episode storage."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EpisodeLog:
    """Append-only episode log stored as daily JSONL files.

    Each line: {"ts": "ISO8601", "type": "interaction|post|activity|insight", "data": {...}}
    """

    def __init__(self, log_dir: Optional[Path] = None) -> None:
        self._log_dir = log_dir

    def _today_path(self) -> Optional[Path]:
        if self._log_dir is None:
            return None
        return self._log_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"

    def _path_for_date(self, date_str: str) -> Optional[Path]:
        if self._log_dir is None:
            return None
        return self._log_dir / f"{date_str}.jsonl"

    def append(self, record_type: str, data: Dict[str, Any]) -> None:
        """Append a record immediately to today's log file."""
        if self._log_dir is None:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": record_type,
            "data": data,
        }
        path = self._today_path()
        if path is None:
            return
        try:
            old_umask = os.umask(0o177)
            try:
                with path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
            finally:
                os.umask(old_umask)
        except OSError as exc:
            logger.warning("Failed to write episode log: %s", exc)

    def read_range(
        self, days: int = 1, record_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Read records from the last N days.

        Args:
            days: Number of days to look back.
            record_type: If given, filter to records with this type
                         (e.g. "post", "insight", "interaction").
        """
        if self._log_dir is None:
            return []
        records: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            path = self._path_for_date(date_str)
            if path is not None:
                records.extend(self.read_file(path))
        if record_type is not None:
            records = [r for r in records if r.get("type") == record_type]
        return records

    @staticmethod
    def read_file(path: Path) -> List[Dict[str, Any]]:
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
