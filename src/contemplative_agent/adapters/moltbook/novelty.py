"""Continuous novelty gate for self-posts (ADR-0039).

Replaces the boolean Jaccard gate in ``dedup.is_duplicate_title`` that
drifted into silent failure in May 2026. Computes a continuous novelty
score from embedding cosine similarity with temporal decay, plus a
rate-deficit Lagrangian term that loosens the admit threshold when the
agent has been silent.

Design:
  - ``compute_novelty`` is a pure function over (draft_vec, [(prior_vec,
    age_days), ...], tau) — Ollama-free, golden-tested.
  - ``PostEmbeddingCache`` wraps the existing ``EpisodeEmbeddingStore``
    (ADR-0019) using ``PostRecord.post_id`` as the storage key. No new
    schema; reuses the embedding sidecar already on disk.
  - ``NoveltyGate.evaluate`` orchestrates: fetch / fill cache for
    history, embed the draft, compute novelty + deficit, log the
    decision tuple, and fall back to Jaccard if embedding fails.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional, Sequence, Tuple

import numpy as np

from contemplative_agent.core.config import VALID_ID_PATTERN
from contemplative_agent.core.embeddings import (
    cosine,
    embed_one,
    embed_texts,
)
from contemplative_agent.core.episode_embeddings import EpisodeEmbeddingStore
from contemplative_agent.core.memory import MemoryStore, PostRecord

from .dedup import is_duplicate_title

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Decision record
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GateDecision:
    """Outcome of a single gate evaluation. Logged in full on every call."""

    admit: bool
    novelty: float
    deficit: float
    threshold: float
    nearest_title: Optional[str]
    nearest_sim: float
    reason: str  # "admit" | "reject:low_novelty" | "embed_failed_fallback"


# ---------------------------------------------------------------------------
# Pure formula
# ---------------------------------------------------------------------------


def compute_novelty(
    draft_vec: np.ndarray,
    history: Sequence[Tuple[np.ndarray, float]],
    *,
    tau_days: float,
) -> float:
    """``1.0 - max_{p ∈ H} cos_sim(draft, p) · exp(-Δt_days(p) / τ)``.

    Empty history → 1.0 (maximum novelty). Recency decay halves the
    influence of two-week-old posts at the default τ=14, so an identical
    repost from 30 days ago contributes ``exp(-30/14) ≈ 0.117`` rather
    than the full 1.0 a fresh repost would.
    """
    if not history:
        return 1.0
    max_decayed = 0.0
    for prior_vec, age_days in history:
        sim = cosine(draft_vec, prior_vec)
        decayed = sim * math.exp(-age_days / tau_days)
        if decayed > max_decayed:
            max_decayed = decayed
    return 1.0 - max_decayed


# ---------------------------------------------------------------------------
# Cache adapter over the existing sidecar
# ---------------------------------------------------------------------------


def embedding_text(title: str, topic_summary: str) -> str:
    """Canonical text fed to the embedding model for a self-post.

    Title plus topic_summary is the same semantic unit the Jaccard gate
    operated on; body is intentionally excluded (it is large and not the
    locus of dedup intent). Exposed (not underscore-prefixed) so call
    sites that persist a published post — see ``post_pipeline.py`` —
    can use the exact same text shape the gate scored against. Drift
    between draft-side and history-side text would silently degrade
    novelty scores.
    """
    return f"{title}\n{topic_summary}"


class PostEmbeddingCache:
    """Reads / fills ``EpisodeEmbeddingStore`` keyed by ``PostRecord.post_id``.

    We reuse the sidecar table rather than provisioning a new one: ADR-0019
    already defines the schema, and ``post_id`` is server-issued (Moltbook
    API), stable, and unique enough to serve as a primary key. Records with
    empty ``post_id`` are skipped — they cannot be stored without a key.
    """

    def __init__(self, store: EpisodeEmbeddingStore) -> None:
        self._store = store

    def get_or_embed_many(
        self, records: Sequence[PostRecord]
    ) -> dict[str, np.ndarray]:
        """Return ``{post_id: vector}`` for as many records as can be embedded.

        Strategy: one ``get_many`` against the sidecar, then a single
        ``embed_texts`` call for the misses, then a single ``upsert_many``.
        Records with empty ``post_id`` are silently dropped. If the batch
        embedding call returns None (Ollama outage), the miss records are
        omitted from the result and the caller decides how to proceed.
        """
        ids = [r.post_id for r in records if r.post_id]
        if not ids:
            return {}
        cached = self._store.get_many(ids)
        misses = [r for r in records if r.post_id and r.post_id not in cached]
        if not misses:
            return cached
        miss_texts = [
            embedding_text(r.title, r.topic_summary) for r in misses
        ]
        miss_vecs = embed_texts(miss_texts)
        if miss_vecs is None or miss_vecs.shape[0] != len(misses):
            return cached
        rows: List[Tuple[str, str, np.ndarray]] = []
        for record, vec in zip(misses, miss_vecs):
            cached[record.post_id] = vec
            rows.append((record.post_id, record.timestamp, vec))
        if rows:
            self._store.upsert_many(rows)
        return cached

    def upsert(self, post_id: str, timestamp: str, vector: np.ndarray) -> None:
        if not post_id:
            return
        self._store.upsert(post_id, timestamp, vector)


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------


class NoveltyGate:
    """Self-post gate combining continuous novelty with rate-deficit slack.

    ``admit if novelty + μ · max(0, target_rate - actual_7d_rate) ≥ θ``.

    The Jaccard gate (``dedup.is_duplicate_title``) is retained as the
    fallback path for when embedding is unavailable — when Ollama is down
    or the model returns nothing, we degrade to the older gate rather
    than open the floodgates.
    """

    def __init__(
        self,
        embed_store: EpisodeEmbeddingStore,
        memory: MemoryStore,
        *,
        theta: float = 0.35,
        tau_days: float = 14.0,
        mu: float = 0.20,
        target_rate: float = 3.0,
        fallback_jaccard_threshold: float = 0.45,
    ) -> None:
        self._cache = PostEmbeddingCache(embed_store)
        self._memory = memory
        self._theta = theta
        self._tau_days = tau_days
        self._mu = mu
        self._target_rate = target_rate
        self._fallback_threshold = fallback_jaccard_threshold

    def evaluate(
        self,
        draft_title: str,
        draft_topic_summary: str,
        draft_body: str,  # noqa: ARG002 — body kept in signature for future use
        recent_records: Sequence[PostRecord],
    ) -> GateDecision:
        """Decide whether a draft self-post should be admitted."""
        draft_text = embedding_text(draft_title, draft_topic_summary)
        draft_vec = embed_one(draft_text)
        if draft_vec is None:
            return self._fallback(
                draft_title, draft_topic_summary, recent_records
            )

        cached = self._cache.get_or_embed_many(list(recent_records))
        history = _build_history(recent_records, cached)
        novelty = compute_novelty(
            draft_vec, history, tau_days=self._tau_days
        )
        deficit = max(0.0, self._target_rate - self._memory.get_post_rate_7d())
        score = novelty + self._mu * deficit
        nearest_title, nearest_sim = _find_nearest(
            draft_vec, recent_records, cached
        )

        admit = score >= self._theta
        reason = "admit" if admit else "reject:low_novelty"
        decision = GateDecision(
            admit=admit,
            novelty=novelty,
            deficit=deficit,
            threshold=self._theta,
            nearest_title=nearest_title,
            nearest_sim=nearest_sim,
            reason=reason,
        )
        logger.info(
            "NoveltyGate %s: novelty=%.3f deficit=%.2f score=%.3f "
            "theta=%.2f nearest=%.3f (%r)",
            "admit" if admit else "reject",
            novelty,
            deficit,
            score,
            self._theta,
            nearest_sim,
            nearest_title,
        )
        return decision

    def record(self, post_id: str, timestamp: str, text: str) -> None:
        """Embed and persist a just-published post for future gate calls.

        ``post_id`` must match ``VALID_ID_PATTERN``; the Moltbook server
        issues ids of this shape, and rejecting anything else mirrors the
        guard already in place for ``submolt`` in ``post_pipeline.py``.
        Defense-in-depth: parameterised SQLite queries already prevent
        injection, but a malformed id should never reach the sidecar.
        """
        if not post_id or not VALID_ID_PATTERN.match(post_id):
            if post_id:
                logger.warning(
                    "NoveltyGate.record: rejected malformed post_id=%r",
                    post_id,
                )
            return
        vec = embed_one(text)
        if vec is None:
            logger.warning(
                "NoveltyGate.record: embed failed for post_id=%s; "
                "history will backfill lazily on next evaluate()",
                post_id,
            )
            return
        self._cache.upsert(post_id, timestamp, vec)

    def _fallback(
        self,
        draft_title: str,
        draft_topic_summary: str,
        recent_records: Sequence[PostRecord],
    ) -> GateDecision:
        """Degrade to the Jaccard gate when embedding is unavailable.

        The fallback threshold (0.45) is deliberately looser than the
        retired 0.25 because the failure mode here is "Ollama is recovering"
        rather than steady-state operation — false negatives matter more
        than false positives during recovery.
        """
        is_dup, sim, prior_title = is_duplicate_title(
            draft_title,
            draft_topic_summary,
            recent_records,
            threshold=self._fallback_threshold,
        )
        decision = GateDecision(
            admit=not is_dup,
            novelty=1.0 - sim,
            deficit=0.0,
            threshold=self._fallback_threshold,
            nearest_title=prior_title,
            nearest_sim=sim,
            reason="embed_failed_fallback",
        )
        logger.warning(
            "NoveltyGate fallback (embedding unavailable): jaccard=%.2f "
            "threshold=%.2f admit=%s nearest=%r",
            sim,
            self._fallback_threshold,
            not is_dup,
            prior_title,
        )
        return decision


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_history(
    records: Sequence[PostRecord], cached: dict[str, np.ndarray]
) -> List[Tuple[np.ndarray, float]]:
    """Pair each cached embedding with its age in days (UTC, current time)."""
    now = datetime.now(timezone.utc)
    out: List[Tuple[np.ndarray, float]] = []
    for record in records:
        vec = cached.get(record.post_id)
        if vec is None:
            continue
        try:
            ts = datetime.fromisoformat(record.timestamp)
        except ValueError:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
        out.append((vec, age_days))
    return out


def _find_nearest(
    draft_vec: np.ndarray,
    records: Sequence[PostRecord],
    cached: dict[str, np.ndarray],
) -> Tuple[Optional[str], float]:
    """Report the nearest (highest-similarity) prior post, for logging only.

    Recency decay is *not* applied here — the log value is the raw similarity
    to the closest historical post, which is what an operator would want to
    see to judge whether the gate is behaving reasonably.
    """
    best_title: Optional[str] = None
    best_sim = 0.0
    for record in records:
        vec = cached.get(record.post_id)
        if vec is None:
            continue
        sim = cosine(draft_vec, vec)
        if sim > best_sim:
            best_sim = sim
            best_title = record.title
    return best_title, best_sim
