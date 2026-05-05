"""Layer 2: KnowledgeStore — distilled learned patterns as JSON."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ._io import now_iso, write_restricted
from .config import FORBIDDEN_SUBSTRING_PATTERNS

logger = logging.getLogger(__name__)

# ADR-0021 source_type values. "unknown" is the migration default for
# legacy patterns without recorded provenance. ADR-0029 retired
# ``user_input`` (no producer; conflicted with ADR-0007 untrusted-input
# boundary) and ``external_post`` (no producer; primary external-content
# defense is quarantine at the summarize boundary, not trust-weighting).
SOURCE_TYPES = (
    "self_reflection",
    "external_reply",
    "mixed",
    "unknown",
)

# ADR-0021 base trust by source. Applied at distill time; later adjusted
# by approval-gate hooks. (Pattern-layer feedback nudges were retired by
# ADR-0028; ``user_input`` / ``external_post`` rows were retired by
# ADR-0029.)
TRUST_BASE_BY_SOURCE: Dict[str, float] = {
    "self_reflection": 0.9,
    "unknown": 0.6,
    "external_reply": 0.55,
    "mixed": 0.5,  # overridden to min(inputs) when mixed sources are known
}

DEFAULT_TRUST = TRUST_BASE_BY_SOURCE["unknown"]


def effective_importance(p: dict) -> float:
    """Compute retrieval weight: importance × time decay × trust.

    ``importance × 0.95^days_elapsed`` is the coarse aging signal; ADR-0021
    augments it with trust (provenance quality). The Ebbinghaus ``strength``
    factor was retired by ADR-0028. Patterns missing trust degrade to
    legacy-only scoring.
    """
    base = p.get("importance", 0.5)
    distilled = p.get("distilled", "")
    if not distilled or distilled == "unknown":
        legacy = base * 0.1  # Unknown timestamp → heavy penalty
    else:
        try:
            dt = datetime.fromisoformat(distilled)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
            days = max(0.0, days)
            legacy = base * (0.95 ** days)
        except (ValueError, TypeError):
            legacy = base * 0.1

    trust = float(p.get("trust_score", 1.0))
    return max(0.0, min(1.0, legacy * trust))


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
        embedding: Optional[List[float]] = None,
        gated: Optional[bool] = None,
        provenance: Optional[Dict] = None,
        trust_score: Optional[float] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> None:
        """Append a new learned pattern dict.

        ADR-0021 fields (provenance / trust_score / valid_from / valid_until)
        are all optional. When omitted, sensible defaults are written so the
        pattern is immediately usable: ``provenance.source_type = "unknown"``,
        ``trust_score = DEFAULT_TRUST``, ``valid_from = distilled``,
        ``valid_until = None`` (current truth).

        ADR-0026: ``category`` / ``subcategory`` are no longer written.
        Routing is query-time via ``ViewRegistry``; the ``gated`` flag
        preserves the legacy noise gate.

        ADR-0028: pattern-layer forgetting (``last_accessed_at`` /
        ``access_count``) and feedback (``success_count`` /
        ``failure_count``) fields have been retired.
        """
        ts = now_iso()
        distilled_value = distilled or ts
        entry: dict = {
            "pattern": pattern,
            "distilled": distilled_value,
            "importance": importance,
        }
        if source:
            entry["source"] = source
        if embedding is not None:
            entry["embedding"] = embedding
        if gated is not None:
            entry["gated"] = gated

        # ADR-0021: provenance + trust
        entry["provenance"] = provenance or {"source_type": "unknown"}
        entry["trust_score"] = (
            float(trust_score) if trust_score is not None else DEFAULT_TRUST
        )
        entry["trust_updated_at"] = ts

        # ADR-0021: bitemporal
        entry["valid_from"] = valid_from or distilled_value
        entry["valid_until"] = valid_until  # None = current truth

        self._learned_patterns.append(entry)

    def get_raw_patterns(self) -> List[dict]:
        """Return a copy of pattern dicts (for analysis/dedup).

        ADR-0026: the ``category`` filter has been retired. Use a
        ``ViewRegistry`` + ``find_by_view`` for semantic routing.
        """
        return list(self._learned_patterns)

    def replace_pattern(self, old_ref: dict, new_pattern: dict) -> bool:
        """Replace a pattern by identity (``is``). Returns True if replaced.

        Used by callers that construct a new dict representing a state
        transition (e.g. bitemporal invalidation) and need to swap it in
        without mutating the existing DTO.
        """
        for i, p in enumerate(self._learned_patterns):
            if p is old_ref:
                self._learned_patterns[i] = new_pattern
                return True
        return False

    def get_learned_patterns(self) -> List[str]:
        """Return a copy of the learned patterns (text only).

        ADR-0026: the ``category`` filter has been retired.
        """
        return [p["pattern"] for p in self._learned_patterns]

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

    def get_raw_patterns_since(self, since: str) -> List[dict]:
        """Return raw pattern dicts distilled after the given ISO timestamp."""
        return self._filter_since(since, self._learned_patterns)

    def get_live_patterns(self) -> List[dict]:
        """Return patterns that pass ``is_live`` (bitemporal + trust)."""
        from .forgetting import is_live

        return [p for p in self._learned_patterns if is_live(p)]

    def get_live_patterns_since(self, since: str) -> List[dict]:
        """Return live patterns distilled after the given ISO timestamp."""
        from .forgetting import is_live

        return [
            p for p in self._filter_since(since, self._learned_patterns)
            if is_live(p)
        ]

    def _effective_importance(self, p: dict) -> float:
        return effective_importance(p)

    def load(self) -> None:
        """Load knowledge from JSON file.

        Idempotent: resets ``_learned_patterns`` before parsing so
        repeat calls on the same instance cannot duplicate entries.
        Several commands (e.g. ``insight``) load at both the CLI
        handler and the core function layer; without this reset a
        subsequent ``save()`` would persist the doubled list.

        Validates content against forbidden patterns to detect
        tainted data that may have been injected via compromised
        external content during distillation.

        Also handles legacy Markdown format for migration.
        """
        self._learned_patterns = []
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

        # Knowledge files are JSON since v2.0 (ADR-0019). Non-JSON shapes
        # are no longer accepted; restore from a backup if you need to read
        # a legacy Markdown file.
        text_stripped = text.strip()
        if text_stripped.startswith("["):
            self._parse_json(text_stripped)
        else:
            logger.warning(
                "Knowledge file is not a JSON array; legacy Markdown is no "
                "longer supported. Restore from a `.bak` file if needed."
            )

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
                # ADR-0026: ``category`` / ``subcategory`` are no longer
                # restored on read. If a legacy file is loaded, the
                # field is silently dropped on the next save (ADR-0035
                # retired the ``migrate-categories`` rewrite command).
                if isinstance(item.get("embedding"), list):
                    entry["embedding"] = list(item["embedding"])
                if isinstance(item.get("gated"), bool):
                    entry["gated"] = item["gated"]

                # ADR-0021 optional fields. Preserve only if present; the
                # load path does not auto-fill, so legacy files keep
                # whatever shape they have on disk (ADR-0035 retired the
                # ``migrate-patterns`` rewrite command). ADR-0029: strip
                # the retired ``sanitized`` flag at load time so saves
                # are net-reductive on the next write-back.
                if isinstance(item.get("provenance"), dict):
                    prov = dict(item["provenance"])
                    prov.pop("sanitized", None)
                    entry["provenance"] = prov
                if isinstance(item.get("trust_score"), (int, float)):
                    entry["trust_score"] = float(item["trust_score"])
                if isinstance(item.get("trust_updated_at"), str):
                    entry["trust_updated_at"] = item["trust_updated_at"]
                if isinstance(item.get("valid_from"), str):
                    entry["valid_from"] = item["valid_from"]
                if "valid_until" in item:
                    vu = item["valid_until"]
                    if vu is None or isinstance(vu, str):
                        entry["valid_until"] = vu
                # ADR-0028: last_accessed_at / access_count /
                # success_count / failure_count are no longer restored on
                # read. Legacy files with these fields load cleanly and
                # the fields are silently dropped on next save.
                self._learned_patterns.append(entry)
            elif isinstance(item, str):
                # Bare string — legacy format
                self._learned_patterns.append({
                    "pattern": item,
                    "distilled": "unknown",
                    "importance": 0.5,
                })

