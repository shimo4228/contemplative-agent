"""Layer 2: KnowledgeStore — distilled learned patterns as JSON."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from ._io import age_days, now_iso, parse_aware_utc, write_text_atomic
from .config import first_forbidden_substring
from .pattern_embeddings import PatternEmbeddingStore, SidecarConsistency, sidecar_path_for

logger = logging.getLogger(__name__)


def _parse_distilled(p: dict) -> datetime | None:
    """Parse a pattern's ``distilled`` ISO timestamp to a tz-aware datetime.

    Returns ``None`` for missing / ``"unknown"`` / malformed timestamps;
    naive inputs are coerced to UTC (matching ``effective_importance`` and
    ``_filter_since``).
    """
    distilled = p.get("distilled", "")
    if not distilled or distilled == "unknown":
        return None
    try:
        return parse_aware_utc(distilled)
    except (ValueError, TypeError):
        return None


def effective_importance(p: dict) -> float:
    """Extraction weight: pure time decay ``0.95^days_elapsed``.

    The distill-time LLM importance rating was retired by ADR-0056 — an
    ablation showed it added almost nothing beyond decay (Kendall tau 0.84
    vs a decay-only variant, identical top-5 batch order). The Ebbinghaus
    ``strength`` factor was retired by ADR-0028 and the trust factor by
    ADR-0051 (origin is recorded, never weighted). Extraction weight is
    therefore time alone.
    """
    dt = _parse_distilled(p)
    if dt is None:
        return 0.1  # Missing / unknown / malformed timestamp → heavy penalty
    return min(1.0, 0.95 ** age_days(dt))


def is_live(pattern: dict) -> bool:
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
# source_type, never persisted. "asserted" was rejected (needs semantic
# judgment, not derivable from record type). The ``observed`` kind and its
# ``external_reply`` arm were retired in ADR-0082 — unreachable since
# ADR-0060, so the key only invited misreading as an external-grounding
# metric. An ``external_reply`` row now falls through to ``unknown``.
_EPISTEMIC_KIND_BY_SOURCE: dict[str, str] = {
    "self_reflection": "generated",
    "mixed": "generated",  # any self contribution taints the batch
}


def epistemic_kind_for(p: dict) -> str | None:
    """Derive the epistemic kind of a pattern row (ADR-0050, ADR-0082).

    Returns ``"generated"`` for self-narrative provenance, ``None`` when the
    source is unknown or unrecorded (legacy rows included).
    """
    provenance = p.get("provenance") or {}
    source_type = provenance.get("source_type", "")
    return _EPISTEMIC_KIND_BY_SOURCE.get(source_type)


def epistemic_counts_for(patterns: list[dict]) -> dict[str, int]:
    """Tally epistemic kinds over pattern rows (ADR-0050, ADR-0082).

    Both keys are always present so audit.jsonl records keep a stable shape
    for offline analysis; ``None`` kinds count as ``"unknown"``.

    Read this as a *provenance-kind* tally (self-narrative vs unrecorded
    source), NOT as an external-grounding presence metric. The external world
    (the post engaged with, the other agent's comment) enters distillation as
    grounding *text inside* the rich render, and was never counted here.

    Records written before ADR-0082 also carry an ``observed`` key that is
    structurally zero; offline readers should use ``.get(...)`` rather than
    assume a fixed key set.
    """
    counts = {"generated": 0, "unknown": 0}
    for p in patterns:
        kind = epistemic_kind_for(p)
        counts[kind or "unknown"] += 1
    return counts


class KnowledgeStore:
    """Manages distilled learned patterns as a JSON file.

    Patterns are the only data stored here — all other data
    (agents, post topics, insights) lives in JSONL episode logs.
    """

    def __init__(self, path: Path | None = None, embeddings_path: Path | None = None) -> None:
        self._path = path
        self._learned_patterns: list[dict] = []  # [{"pattern": str, "distilled": str}]
        # ADR-0108: the 768-dim vectors live beside the JSON, not inside it.
        # ``embeddings_path`` exists so a caller can point the two halves
        # somewhere other than the default sibling (tests, a second home).
        if embeddings_path is None and path is not None:
            embeddings_path = sidecar_path_for(path)
        self._embeddings = PatternEmbeddingStore(embeddings_path)
        self._consistency = SidecarConsistency()
        # Array elements the parser could not read as pattern rows. Zero for
        # every well-formed store; non-zero means a save would delete them.
        self._dropped_rows = 0
        # True when load() found an existing file it could not read/parse.
        # In that state save() must NOT overwrite the on-disk file with the
        # empty in-memory list — that would destroy the persisted patterns
        # (see HIGH-4, ultracode sweep 2026-06-23). A fresh store with no
        # backing file leaves this False so the first save() can create it.
        self._load_failed = False

    @property
    def dropped_rows(self) -> int:
        """Elements the last ``load()`` refused to read as pattern rows.

        Public because a writer that rewrites the whole array — which every
        ``save()`` now does — deletes them. The operator scripts check this
        and refuse rather than silently shedding data from a production store
        as a side effect of embedding something else.
        """
        return self._dropped_rows

    @property
    def load_failed(self) -> bool:
        """True when the last ``load()`` hit an existing file it could not use.

        Public because an operator tool (``scripts/restore-embed-knowledge.py``)
        must not embed and re-save an empty in-memory store over a populated
        file; ``save()``'s own refusal is silent by design, and a backfill that
        reports "0 filled" would read as success.
        """
        return self._load_failed

    def prune_orphan_vectors(self) -> int:
        """Delete sidecar vectors no loaded pattern claims. Returns the count.

        Not called from ``save()``: a soft-invalidated row's vector may be
        claimed again by a revision, and an orphan costs 3 KB. This is the
        operator's broom (``scripts/migrate-knowledge-sidecar.py --prune``).
        """
        return self._embeddings.prune({pattern_id(p) for p in self._learned_patterns})

    def sidecar_consistency(self) -> SidecarConsistency:
        """What the two halves looked like at the last ``load()`` (ADR-0108 D3)."""
        return self._consistency

    def has_persisted_file(self) -> bool:
        """Check whether the backing JSON file exists on disk."""
        return self._path is not None and self._path.exists()

    def add_learned_pattern(
        self,
        pattern: str,
        distilled: str | None = None,
        source: str | None = None,
        embedding: list[float] | None = None,
        gated: bool | None = None,
        provenance: dict | None = None,
        valid_from: str | None = None,
        valid_until: str | None = None,
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

    def get_raw_patterns(self) -> list[dict]:
        """Return a copy of pattern dicts (for analysis/dedup).

        ADR-0026: the ``category`` filter has been retired. Use a
        ``ViewRegistry`` + ``find_by_view`` for semantic routing.
        """
        return list(self._learned_patterns)

    def _filter_since(self, since: str, pool: list[dict]) -> list[dict]:
        """Return dicts from pool distilled at/after since. Returns all on bad timestamp.

        Both sides are coerced to tz-aware (naive → UTC), matching
        ``effective_importance``. Without this, comparing a tz-naive
        ``distilled`` against a tz-aware ``since`` (or vice versa) raised
        TypeError and silently dropped the pattern from the result — a latent
        data-loss path for "since" queries (ultracode sweep 2026-06-23).

        Inclusive (``>=``) since bug-audit 2026-07-06 M12: both ``distilled``
        and the run markers carry minute precision, so with strict ``>`` a
        pattern distilled in the same minute as the marker was excluded this
        run AND every later run (markers only move forward) — a permanent
        silent loss, not a delay. The cost of ``>=`` is one same-minute
        re-processing, which downstream approval gates absorb.
        """
        try:
            since_dt = parse_aware_utc(since)
        except (ValueError, TypeError):
            return list(pool)
        result = []
        for p in pool:
            dt = _parse_distilled(p)
            if dt is not None and dt >= since_dt:
                result.append(p)
        return result

    def get_live_patterns(self) -> list[dict]:
        """Return patterns that pass ``is_live`` (bitemporal gate)."""
        return [p for p in self._learned_patterns if is_live(p)]

    def get_live_patterns_since(self, since: str) -> list[dict]:
        """Return live patterns distilled at or after the given ISO timestamp."""
        return [p for p in self._filter_since(since, self._learned_patterns) if is_live(p)]

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
        self._load_failed = False
        self._dropped_rows = 0
        if self._path is None or not self._path.exists():
            logger.debug("No knowledge file at %s", self._path)
            return
        try:
            text = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read knowledge file: %s", exc)
            self._load_failed = True
            return

        # Validate against forbidden patterns
        found = first_forbidden_substring(text)
        if found is not None:
            logger.warning(
                "Knowledge file contains forbidden pattern: %s — "
                "file may be tainted, skipping load",
                found,
            )
            self._load_failed = True
            return

        # Knowledge files are JSON since v2.0 (ADR-0019). Non-JSON shapes
        # are no longer accepted; restore from a backup if you need to read
        # a legacy Markdown file.
        text_stripped = text.strip()
        if text_stripped.startswith("["):
            self._parse_json(text_stripped)
            self._hydrate_embeddings()
        else:
            logger.warning(
                "Knowledge file is not a JSON array; legacy Markdown is no "
                "longer supported. Restore from a `.bak` file if needed."
            )
            self._load_failed = True

    def _hydrate_embeddings(self) -> None:
        """Attach each row's vector from the sidecar, naming every half-state.

        ADR-0108 D2: the vector lands back in ``entry["embedding"]`` as a
        ``list[float]``, the exact shape the inline file used to carry, so no
        consumer of the field changes. D3: a row that ends up without one is
        counted under a reason code rather than silently absent — the store is
        two files now, and half of it can be missing.
        """
        rows = self._learned_patterns
        inline = sum(1 for p in rows if isinstance(p.get("embedding"), list))
        sidecar_absent = not self._embeddings.exists()
        stored = self._embeddings.get_all()
        sidecar_unreadable = stored is None
        if stored is None:
            stored = {}

        # The dominant width is the store's own answer to "which model wrote
        # these", rather than a constant this module would have to keep in
        # step with core.embeddings.
        widths: dict[int, int] = {}
        for vec in stored.values():
            widths[int(vec.shape[0])] = widths.get(int(vec.shape[0]), 0) + 1
        for p in rows:
            emb = p.get("embedding")
            if isinstance(emb, list):
                widths[len(emb)] = widths.get(len(emb), 0) + 1
        dominant = max(widths, key=lambda w: widths[w]) if widths else 0

        hydrated = 0
        row_missing = 0
        dim_mismatch = 0
        missing_ids: list[str] = []
        claimed: set[str] = set()
        for p in rows:
            pid = pattern_id(p)
            claimed.add(pid)
            if isinstance(p.get("embedding"), list):
                continue  # legacy inline row — used as-is, migrated on save()
            vec = stored.get(pid)
            if vec is None:
                row_missing += 1
                missing_ids.append(pid)
                continue
            if int(vec.shape[0]) != dominant:
                dim_mismatch += 1
                missing_ids.append(pid)
                continue
            p["embedding"] = vec.tolist()
            hydrated += 1

        self._consistency = SidecarConsistency(
            total_rows=len(rows),
            hydrated=hydrated,
            inline_legacy=inline,
            sidecar_absent=sidecar_absent and bool(rows),
            sidecar_unreadable=sidecar_unreadable,
            row_missing=row_missing,
            dim_mismatch=dim_mismatch,
            orphan_vectors=len(set(stored) - claimed),
            missing_ids=tuple(missing_ids),
        )
        if not self._consistency.clean:
            logger.warning(
                "Knowledge sidecar consistency: %s (%s)",
                ",".join(self._consistency.reason_codes()),
                self._consistency.describe(),
            )

    def save(self) -> None:
        """Persist learned patterns to JSON file using atomic write.

        Refuses to write when the most recent ``load()`` failed on an
        existing file (HIGH-4, ultracode sweep 2026-06-23): a failed load
        leaves ``_learned_patterns`` empty, so an unconditional save would
        atomically replace a populated file with ``[]`` and no ``.bak``.
        Persisting an empty list over unreadable-but-present data is treated
        as data loss; the operator must restore from a backup or fix the file.
        """
        if self._path is None:
            logger.debug("No knowledge path configured, skipping save")
            return
        if self._load_failed:
            logger.error(
                "Refusing to save knowledge file: the last load() failed on an "
                "existing file at %s, so the in-memory store may be empty. "
                "Restore from a `.bak` or fix the file before saving.",
                self._path,
            )
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # ADR-0108 D3: sidecar first. A sidecar fault leaves the JSON at its
        # previous state; the reverse order could leave a JSON with no vectors
        # anywhere, which is the one ordering that loses data. A JSON fault
        # after a successful sidecar write leaves orphan vectors, which the
        # next load() counts and nothing reads.
        self._embeddings.upsert_many(_vectors_to_persist(self._learned_patterns))

        content = (
            json.dumps(_without_embeddings(self._learned_patterns), ensure_ascii=False, indent=2)
            + "\n"
        )
        try:
            write_text_atomic(self._path, content)
        except OSError as exc:
            logger.error("Failed to save knowledge file: %s", exc)
            raise

    def _parse_json(self, text: str) -> None:
        """Parse JSON array of pattern objects."""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse knowledge JSON: %s", exc)
            self._load_failed = True
            return
        if not isinstance(data, list):
            logger.warning("Knowledge JSON is not an array")
            self._load_failed = True
            return
        dropped = 0
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("pattern"), str):
                self._learned_patterns.append(_entry_from_dict(item))
            elif isinstance(item, str):
                # Bare string — legacy format
                self._learned_patterns.append(
                    {
                        "pattern": item,
                        "distilled": "unknown",
                    }
                )
            else:
                dropped += 1
        self._dropped_rows = dropped
        if dropped:
            # Silent until 2026-09-12. It did not matter while every writer of
            # this file was a verbatim JSON round-trip; it matters now that
            # ``save()`` rewrites the whole array, because a row the parser
            # refuses is a row the next save deletes. The operator scripts
            # refuse to write when this is non-zero.
            logger.warning(
                "Knowledge file has %d/%d element(s) that are not pattern rows — they are "
                "NOT loaded, and a save would drop them. Fix or remove them before writing.",
                dropped,
                len(data),
            )


def _vectors_to_persist(patterns: list[dict]) -> list[tuple[str, np.ndarray]]:
    """``(pattern_id, float32 vector)`` for every row that has a usable one.

    A row whose ``embedding`` is not numeric is skipped with a WARNING rather
    than raising. Before ADR-0108 such a row serialized straight back into the
    JSON; letting it raise here would make one corrupt legacy row block every
    save of the whole store, which is a worse failure than the one it reports.
    Downstream, ``_live_embedded`` and the view metrics already skip it.
    """
    out: list[tuple[str, np.ndarray]] = []
    for p in patterns:
        emb = p.get("embedding")
        if not isinstance(emb, list) or not emb:
            continue
        try:
            vec = np.asarray(emb, dtype=np.float32)
        except (TypeError, ValueError):
            logger.warning(
                "Skipping non-numeric embedding on pattern %.60r — not written to the "
                "sidecar; the row persists as text and reads back unembedded",
                p.get("pattern", ""),
            )
            continue
        if vec.ndim != 1:
            logger.warning(
                "Skipping embedding of shape %s on pattern %.60r — expected a flat vector",
                vec.shape,
                p.get("pattern", ""),
            )
            continue
        # ``np.asarray([None, None], dtype=float32)`` yields NaN rather than
        # raising, and a NaN vector poisons every cosine it reaches. Caught at
        # the storage boundary rather than at each of the seven read sites.
        if not bool(np.isfinite(vec).all()):
            logger.warning(
                "Skipping non-finite embedding on pattern %.60r — NaN/inf would make "
                "every cosine against it meaningless",
                p.get("pattern", ""),
            )
            continue
        out.append((pattern_id(p), vec))
    return out


def _without_embeddings(patterns: list[dict]) -> list[dict]:
    """Serialization view of the rows: everything but the vectors (ADR-0108).

    A shallow copy per row rather than a mutation — the in-memory dicts are
    what every consumer holds during and after a save, and ``distill`` reads
    them again for its instruments on the same objects.
    """
    return [{k: v for k, v in p.items() if k != "embedding"} for p in patterns]


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
