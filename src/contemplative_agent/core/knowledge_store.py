"""Layer 2: KnowledgeStore — distilled learned patterns as JSON."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from ._io import now_iso, write_restricted
from .config import FORBIDDEN_SUBSTRING_PATTERNS

logger = logging.getLogger(__name__)

def effective_importance(p: dict) -> float:
    """Extraction weight: pure time decay ``0.95^days_elapsed``.

    The distill-time LLM importance rating was retired by ADR-0056 — an
    ablation showed it added almost nothing beyond decay (Kendall tau 0.84
    vs a decay-only variant, identical top-5 batch order). The Ebbinghaus
    ``strength`` factor was retired by ADR-0028 and the trust factor by
    ADR-0051 (origin is recorded, never weighted). Extraction weight is
    therefore time alone.
    """
    distilled = p.get("distilled", "")
    if not distilled or distilled == "unknown":
        return 0.1  # Unknown timestamp → heavy penalty
    try:
        dt = datetime.fromisoformat(distilled)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        days = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    except (ValueError, TypeError):
        return 0.1
    return min(1.0, 0.95 ** days)


def is_live(pattern: Dict) -> bool:
    """True if the pattern is currently retrievable (ADR-0051).

    Bitemporal gate only: a pattern is live iff ``valid_until is None``
    (current truth). The former trust floor (ADR-0021 IV-7) could never
    fire — no assigned base trust was below it — and was retired together
    with the rest of the trust weighting by ADR-0051.
    """
    return pattern.get("valid_until") is None


def pattern_id(p: dict) -> str:
    """Computed content-hash identity for a pattern row (ADR-0050).

    No persisted id field — ``distilled`` alone cannot serve (minute
    precision collides within a batch), so the hash binds timestamp and
    text. Bitemporal revision (ADR-0021 soft-invalidate + revised ADD)
    yields a different text and therefore a distinct id, which is
    lineage-correct: the revision is a different claim.
    """
    raw = f"{p.get('distilled', '')}|{p.get('pattern', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


# ADR-0050 read-time derivation: epistemic kind is a pure function of
# source_type, never persisted. {observed, generated} only — "asserted"
# was rejected (needs semantic judgment, not derivable from record type).
_EPISTEMIC_KIND_BY_SOURCE: Dict[str, str] = {
    "self_reflection": "generated",
    "mixed": "generated",  # any self contribution taints the batch
    "external_reply": "observed",
}


def epistemic_kind_for(p: dict) -> Optional[str]:
    """Derive the epistemic kind of a pattern row (ADR-0050).

    Returns ``"generated"`` for self-narrative provenance,
    ``"observed"`` for externally received content, ``None`` when the
    source is unknown or unrecorded (legacy rows included).
    """
    provenance = p.get("provenance") or {}
    source_type = provenance.get("source_type", "")
    return _EPISTEMIC_KIND_BY_SOURCE.get(source_type)


def epistemic_counts_for(patterns: List[dict]) -> Dict[str, int]:
    """Tally epistemic kinds over pattern rows (ADR-0050).

    All three keys are always present so audit.jsonl records keep a
    stable shape for offline analysis; ``None`` kinds count as
    ``"unknown"``.
    """
    counts = {"observed": 0, "generated": 0, "unknown": 0}
    for p in patterns:
        kind = epistemic_kind_for(p)
        counts[kind or "unknown"] += 1
    return counts


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
        embedding: Optional[List[float]] = None,
        gated: Optional[bool] = None,
        provenance: Optional[Dict] = None,
        valid_from: Optional[str] = None,
        valid_until: Optional[str] = None,
    ) -> None:
        """Append a new learned pattern dict.

        ADR-0021 fields (provenance / valid_from / valid_until) are all
        optional. When omitted, sensible defaults are written so the
        pattern is immediately usable: ``provenance.source_type =
        "unknown"``, ``valid_from = distilled``, ``valid_until = None``
        (current truth).

        ADR-0026: ``category`` / ``subcategory`` are no longer written.
        Routing is query-time via ``ViewRegistry``; the ``gated`` flag
        preserves the legacy noise gate.

        ADR-0028: pattern-layer forgetting (``last_accessed_at`` /
        ``access_count``) and feedback (``success_count`` /
        ``failure_count``) fields have been retired.

        ADR-0051: ``trust_score`` / ``trust_updated_at`` are no longer
        written. Origin lives in ``provenance.source_type`` (recorded,
        never weighted).

        ADR-0056: ``importance`` is no longer written. The distill-time
        LLM rating was retired; extraction weight is pure time decay
        (``effective_importance``).
        """
        distilled_value = distilled or now_iso()
        entry: dict = {
            "pattern": pattern,
            "distilled": distilled_value,
        }
        if source:
            entry["source"] = source
        if embedding is not None:
            entry["embedding"] = embedding
        if gated is not None:
            entry["gated"] = gated

        # ADR-0021: provenance (origin record; ADR-0050 derives the
        # epistemic kind from it at read time)
        entry["provenance"] = provenance or {"source_type": "unknown"}

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

    def get_live_patterns(self) -> List[dict]:
        """Return patterns that pass ``is_live`` (bitemporal gate)."""
        return [p for p in self._learned_patterns if is_live(p)]

    def get_live_patterns_since(self, since: str) -> List[dict]:
        """Return live patterns distilled after the given ISO timestamp."""
        return [
            p for p in self._filter_since(since, self._learned_patterns)
            if is_live(p)
        ]

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
                self._learned_patterns.append(_entry_from_dict(item))
            elif isinstance(item, str):
                # Bare string — legacy format
                self._learned_patterns.append({
                    "pattern": item,
                    "distilled": "unknown",
                })


def _entry_from_dict(item: dict) -> dict:
    """Restore one persisted pattern object, preserving optional fields.

    ADR-0056: the legacy ``importance`` field is no longer restored;
    a tainted/legacy file's value is silently dropped on the next save
    (extraction weight is pure time decay, no LLM rating).
    """
    entry: dict = {
        "pattern": item["pattern"],
        "distilled": item.get("distilled", "unknown"),
    }
    if item.get("source") is not None:
        entry["source"] = item["source"]
    # ADR-0028: ``last_accessed`` (pattern-layer forgetting) is no longer
    # restored on read. It was never read after restore once forgetting was
    # retired; legacy files load cleanly and the field is silently dropped on
    # the next save (same shed pattern as ADR-0051/0056, zero information loss).
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
    # are net-reductive on the next write-back. ADR-0051:
    # ``trust_score`` / ``trust_updated_at`` are no longer
    # restored on read — legacy files load cleanly and the
    # fields are silently dropped on the next save (every
    # historical value is a pure function of
    # ``provenance.source_type``).
    if isinstance(item.get("provenance"), dict):
        prov = dict(item["provenance"])
        prov.pop("sanitized", None)
        entry["provenance"] = prov
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
    return entry

