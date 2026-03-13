"""Layer 1: EpisodeLog — append-only daily JSONL episode storage."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

SUMMARY_MAX_LENGTH = 200


def _truncate(text: str, max_length: int = SUMMARY_MAX_LENGTH) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def _write_restricted(path: Path, content: str) -> None:
    """Write content to a file with 0600 permissions from creation.

    Uses umask to ensure the file is never world-readable, even briefly.
    """
    old_umask = os.umask(0o177)
    try:
        path.write_text(content, encoding="utf-8")
    finally:
        os.umask(old_umask)


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

    def read_today(self) -> List[Dict[str, Any]]:
        """Read all records from today's log."""
        path = self._today_path()
        return self._read_file(path) if path is not None else []

    def read_range(self, days: int = 1) -> List[Dict[str, Any]]:
        """Read records from the last N days."""
        if self._log_dir is None:
            return []
        records: List[Dict[str, Any]] = []
        now = datetime.now(timezone.utc)
        for i in range(days):
            date_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            path = self._path_for_date(date_str)
            if path is not None:
                records.extend(self._read_file(path))
        return records

    def cleanup(self, retention_days: Optional[int] = None) -> int:
        """Delete log files older than retention_days. Returns count deleted."""
        retention = retention_days if retention_days is not None else 30
        if self._log_dir is None or not self._log_dir.exists():
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention)
        deleted = 0
        for path in self._log_dir.glob("*.jsonl"):
            match = re.match(r"(\d{4}-\d{2}-\d{2})\.jsonl", path.name)
            if not match:
                continue
            try:
                file_date = datetime.strptime(match.group(1), "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
                if file_date < cutoff:
                    path.unlink()
                    deleted += 1
                    logger.debug("Deleted old log: %s", path.name)
            except ValueError:
                continue
        return deleted

    @staticmethod
    def _read_file(path: Path) -> List[Dict[str, Any]]:
        """Read all JSON lines from a single file."""
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
