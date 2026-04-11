"""Layer 2: KnowledgeStore — distilled learned patterns as JSON."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ._io import write_restricted
from .config import FORBIDDEN_SUBSTRING_PATTERNS

logger = logging.getLogger(__name__)


def effective_importance(p: dict) -> float:
    """Compute importance with time decay: importance * 0.95^days_elapsed."""
    base = p.get("importance", 0.5)
    distilled = p.get("distilled", "")
    if not distilled or distilled == "unknown":
        return base * 0.1  # Unknown timestamp → heavy penalty
    try:
        dt = datetime.fromisoformat(distilled)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
        days = max(0.0, days)
    except (ValueError, TypeError):
        return base * 0.1
    return max(0.0, min(1.0, base * (0.95 ** days)))


class KnowledgeStore:
    """Manages distilled learned patterns as a JSON file.

    Patterns are the only data stored here — all other data
    (agents, post topics, insights) lives in JSONL episode logs.
    """

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = path
        self._learned_patterns: List[dict] = []  # [{"pattern": str, "distilled": str}]

    def has_persisted_file(self) -> bool:
        """Check whether the backing JSON file exists on disk."""
        return self._path is not None and self._path.exists()

    def add_learned_pattern(
        self,
        pattern: str,
        distilled: Optional[str] = None,
        source: Optional[str] = None,
        importance: float = 0.5,
        category: str = "uncategorized",
        subcategory: Optional[str] = None,
    ) -> None:
        entry: dict = {
            "pattern": pattern,
            "distilled": distilled or datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "importance": importance,
            "category": category,
        }
        if source:
            entry["source"] = source
        if subcategory is not None:
            entry["subcategory"] = subcategory
        self._learned_patterns.append(entry)

    def get_raw_patterns(self, category: Optional[str] = None) -> List[dict]:
        """Return a copy of pattern dicts (for analysis/dedup).

        Args:
            category: If provided, only return patterns matching this category.
        """
        return list(self._filtered_pool(category))

    def get_learned_patterns(self, category: Optional[str] = None) -> List[str]:
        """Return a copy of the learned patterns (text only).

        Args:
            category: If provided, only return patterns matching this category.
                      Patterns without a category field are treated as "uncategorized".
        """
        return [p["pattern"] for p in self._filtered_pool(category)]

    def get_learned_patterns_by_subcategory(self, subcategory: str) -> List[dict]:
        """Return raw pattern dicts for a specific subcategory (uncategorized only)."""
        return [
            p for p in self._learned_patterns
            if p.get("category", "uncategorized") == "uncategorized"
            and p.get("subcategory") == subcategory
        ]

    def _filtered_pool(self, category: Optional[str]) -> List[dict]:
        """Return patterns filtered by category (None = all)."""
        if category is None:
            return self._learned_patterns
        return [p for p in self._learned_patterns if p.get("category", "uncategorized") == category]

    def _filter_since(self, since: str, pool: List[dict]) -> List[dict]:
        """Return dicts from pool distilled after since. Returns all on bad timestamp."""
        try:
            since_dt = datetime.fromisoformat(since)
        except (ValueError, TypeError):
            return list(pool)
        result = []
        for p in pool:
            distilled = p.get("distilled", "")
            if not distilled or distilled == "unknown":
                continue
            try:
                if datetime.fromisoformat(distilled) > since_dt:
                    result.append(p)
            except (ValueError, TypeError):
                continue
        return result

    def get_learned_patterns_since(self, since: str, category: Optional[str] = None) -> List[str]:
        """Return patterns distilled after the given ISO timestamp.

        Args:
            since: ISO timestamp cutoff.
            category: If provided, only return patterns matching this category.
        """
        return [p["pattern"] for p in self._filter_since(since, self._filtered_pool(category))]

    def get_raw_patterns_since(self, since: str, category: Optional[str] = None) -> List[dict]:
        """Return raw pattern dicts distilled after the given ISO timestamp.

        Like get_learned_patterns_since but returns full dicts (with subcategory).
        """
        return self._filter_since(since, self._filtered_pool(category))

    def _effective_importance(self, p: dict) -> float:
        return effective_importance(p)

    def get_context_string(
        self,
        limit: int = 50,
        category: Optional[str] = None,
        subcategory: Optional[str] = None,
    ) -> str:
        """Return learned patterns as a bullet list for LLM context injection.

        Returns top `limit` patterns sorted by effective importance
        (base importance with time decay). Default 50 balances signal
        quality with coverage for qwen3.5:9b's 32k context.

        Args:
            limit: Maximum number of patterns to return.
            category: If provided, only return patterns matching this category.
                      Patterns without a category field are treated as "uncategorized".
            subcategory: If provided, only return patterns matching this subcategory
                         (applied after category filter).
        """
        pool = self._filtered_pool(category)
        if subcategory is not None:
            pool = [p for p in pool if p.get("subcategory") == subcategory]
        if not pool:
            return ""
        scored = sorted(
            pool,
            key=self._effective_importance,
            reverse=True,
        )
        selected = scored[:limit]
        now = datetime.now(timezone.utc).isoformat(timespec="minutes")
        for p in selected:
            p["last_accessed"] = now
        return "\n".join(f"- {p['pattern']}" for p in selected)

    def load(self) -> None:
        """Load knowledge from JSON file.

        Validates content against forbidden patterns to detect
        tainted data that may have been injected via compromised
        external content during distillation.

        Also handles legacy Markdown format for migration.
        """
        if self._path is None or not self._path.exists():
            logger.debug("No knowledge file at %s", self._path)
            return
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read knowledge file: %s", exc)
            return

        # Validate against forbidden patterns
        text_lower = text.lower()
        for pat in FORBIDDEN_SUBSTRING_PATTERNS:
            if pat.lower() in text_lower:
                logger.warning(
                    "Knowledge file contains forbidden pattern: %s — "
                    "file may be tainted, skipping load",
                    pat,
                )
                return

        # Try JSON first, fall back to legacy Markdown
        text_stripped = text.strip()
        if text_stripped.startswith("["):
            self._parse_json(text_stripped)
        else:
            self._parse_legacy_markdown(text)

    def save(self) -> None:
        """Persist learned patterns to JSON file using atomic write."""
        if self._path is None:
            logger.debug("No knowledge path configured, skipping save")
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(self._learned_patterns, ensure_ascii=False, indent=2) + "\n"
        tmp_path = self._path.with_suffix(".json.tmp")
        try:
            write_restricted(tmp_path, content)
            os.replace(str(tmp_path), str(self._path))
        except OSError as exc:
            logger.error("Failed to save knowledge file: %s", exc)
            tmp_path.unlink(missing_ok=True)
            raise

    def _parse_json(self, text: str) -> None:
        """Parse JSON array of pattern objects."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse knowledge JSON: %s", exc)
            return
        if not isinstance(data, list):
            logger.warning("Knowledge JSON is not an array")
            return
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("pattern"), str):
                entry: dict = {
                    "pattern": item["pattern"],
                    "distilled": item.get("distilled", "unknown"),
                    "importance": item.get("importance", 0.5),
                }
                if item.get("source") is not None:
                    entry["source"] = item["source"]
                if item.get("last_accessed") is not None:
                    entry["last_accessed"] = item["last_accessed"]
                if item.get("category") is not None:
                    entry["category"] = item["category"]
                if item.get("subcategory") is not None:
                    entry["subcategory"] = item["subcategory"]
                self._learned_patterns.append(entry)
            elif isinstance(item, str):
                # Bare string — legacy format
                self._learned_patterns.append({
                    "pattern": item,
                    "distilled": "unknown",
                    "importance": 0.5,
                })

    def _parse_legacy_markdown(self, text: str) -> None:
        """Parse legacy Markdown format (only extracts Learned Patterns)."""
        in_patterns = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                in_patterns = stripped[3:].strip() == "Learned Patterns"
                continue
            if in_patterns and stripped.startswith("- "):
                item = stripped[2:].strip()
                if item:
                    self._learned_patterns.append({
                        "pattern": item,
                        "distilled": "unknown",
                        "importance": 0.5,
                    })
