"""Embedding-cosine dedup for distilled patterns (ADR-0019/0021/0056).

Pure decision functions: compare new patterns against the live pool and the
current batch, and classify each as add / update / skip / skip-new. Extracted
verbatim from core/distill.py (ADR-0079 Phase 3b). Must not import from
.distill (the distill pipeline imports this module).
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from ._io import now_iso
from .embeddings import cosine
from .knowledge_store import is_live
from .thresholds import SIM_DUPLICATE, SIM_UPDATE

logger = logging.getLogger(__name__)

def _dedup_patterns(
    new_patterns: Sequence[str],
    new_embeddings: Sequence[Optional[np.ndarray]],
    existing_patterns: Sequence[dict],
    *,
    mutate_existing: bool = True,
) -> Tuple[
    List[str],
    List[Optional[np.ndarray]],
    List[int],
    int,
    int,
]:
    """Remove duplicates by comparing new patterns against existing ones.

    Returns ``(add_patterns, add_embeddings, add_indices, skip_count,
    update_count)``.
    - SKIP: cosine >= SIM_DUPLICATE (near-exact duplicate)
    - UPDATE: cosine >= SIM_UPDATE against existing → soft-invalidate the old
      pattern (``valid_until = now``) and ADD the new pattern. The old row is
      kept for audit / replay (ADR-0021 bitemporal) rather than mutated in
      place. ADR-0056: no importance boost — the LLM rating was retired and
      extraction weight is pure time decay, so the re-observed pattern simply
      re-enters with a fresh timestamp.
    - ADD: cosine <  SIM_UPDATE against everything

    Patterns whose embedding is None (Ollama failure) are always ADD'd
    so distillation degrades gracefully when the embed model is down.
    Existing patterns without embeddings are ignored as dedup candidates.
    """
    add_patterns: List[str] = []
    add_embeddings: List[Optional[np.ndarray]] = []
    add_indices: List[int] = []
    skip_count = 0
    update_count = 0

    ts = now_iso()

    existing_with_emb = _live_embedded(existing_patterns)

    for input_idx, (new_text, new_emb) in enumerate(zip(new_patterns, new_embeddings)):
        if new_emb is None:
            add_patterns.append(new_text)
            add_embeddings.append(None)
            add_indices.append(input_idx)
            continue

        best_existing_sim, best_existing_pat = _best_existing_sim(new_emb, existing_with_emb)
        best_new_sim, best_new_idx = _best_accepted_sim(new_emb, add_embeddings)

        action = _dedup_action(best_existing_sim, best_existing_pat, best_new_sim, best_new_idx)
        if action == "skip":
            skip_count += 1
            logger.info("SKIP (%.2f): %s", max(best_existing_sim, best_new_sim), new_text[:60])
        elif action == "update":
            # ADR-0021: soft-invalidate old, keep row for audit, and ADD the
            # re-observed pattern with a fresh timestamp (no importance boost,
            # ADR-0056).
            assert best_existing_pat is not None  # guaranteed by _dedup_action
            if mutate_existing:
                best_existing_pat["valid_until"] = ts
            add_patterns.append(new_text)
            add_embeddings.append(new_emb)
            add_indices.append(input_idx)
            update_count += 1
            logger.debug("UPDATE (%.2f): invalidate + re-add: %s", best_existing_sim, new_text[:60])
        elif action == "skip_new":
            skip_count += 1
            logger.debug("SKIP-NEW (%.2f): %s", best_new_sim, new_text[:60])
        else:
            add_patterns.append(new_text)
            add_embeddings.append(new_emb)
            add_indices.append(input_idx)

    return (
        add_patterns,
        add_embeddings,
        add_indices,
        skip_count,
        update_count,
    )


def _live_embedded(existing_patterns: Sequence[dict]) -> List[Tuple[Dict, np.ndarray]]:
    """Pre-compute existing embeddings (live patterns with embeddings only)."""
    existing_with_emb: List[Tuple[Dict, np.ndarray]] = []
    for p in existing_patterns:
        if not is_live(p):
            continue  # bitemporally invalidated — ignore
        emb = p.get("embedding")
        if isinstance(emb, list):
            existing_with_emb.append((p, np.asarray(emb, dtype=np.float32)))
    return existing_with_emb


def _best_existing_sim(
    new_emb: np.ndarray, existing_with_emb: Sequence[Tuple[Dict, np.ndarray]]
) -> Tuple[float, Optional[Dict]]:
    """Best cosine similarity vs existing patterns."""
    best_sim = -1.0
    best_pat: Optional[Dict] = None
    for pat_dict, pat_emb in existing_with_emb:
        sim = cosine(new_emb, pat_emb)
        if sim > best_sim:
            best_sim = sim
            best_pat = pat_dict
    return best_sim, best_pat


def _best_accepted_sim(
    new_emb: np.ndarray, add_embeddings: Sequence[Optional[np.ndarray]]
) -> Tuple[float, int]:
    """Best cosine similarity vs already-accepted new patterns (cross-batch)."""
    best_sim = -1.0
    best_idx = -1
    for idx, accepted_emb in enumerate(add_embeddings):
        if accepted_emb is None:
            continue
        sim = cosine(new_emb, accepted_emb)
        if sim > best_sim:
            best_sim = sim
            best_idx = idx
    return best_sim, best_idx


def _dedup_action(
    best_existing_sim: float,
    best_existing_pat: Optional[Dict],
    best_new_sim: float,
    best_new_idx: int,
) -> str:
    """Decide: ``skip`` / ``update`` existing / ``skip_new`` (boost in batch) / ``add``."""
    if best_existing_sim >= SIM_DUPLICATE or best_new_sim >= SIM_DUPLICATE:
        return "skip"
    if (
        best_existing_sim >= SIM_UPDATE
        and best_existing_pat is not None
        and best_existing_sim >= best_new_sim
    ):
        return "update"
    if best_new_sim >= SIM_UPDATE and best_new_idx >= 0:
        return "skip_new"
    return "add"
