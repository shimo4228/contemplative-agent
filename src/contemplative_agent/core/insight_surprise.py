"""Surprise readings for insight candidates (ADR-0096) — read-only.

**Surprise** is how far a candidate cluster sits from the patterns the agent
distilled most recently: ``1 - cos`` against the last ``k`` rows, reported
both against the nearest one (``s_nn``) and against the distribution
(``s_mean``). It is computed in code from embeddings that already exist, with
no LLM call, and it is **listed for the reviewer, never applied**.

Why listed and not applied — the 2026-08-17 calibration over the 78 labelled
candidates of the 2026-07-25 batch (owner's own adopt/reject decisions as
ground truth):

- Surprise is not uninformative: ``s_mean`` scored AUC 0.76–0.79 with a
  permutation p ≈ 0.02, and the five adopted candidates had a rank median of
  19/78 against a random expectation of 39.5.
- It does not reproduce the decision. Positives are n=5, and at every ``k``
  the single most surprising candidate was one the owner **rejected**
  (``operationalizing-systematic-absence``) — from exactly the family the
  owner pruned because its register was already saturated. Rare is not the
  same as useful, which is why D-MEM (arXiv:2603.14597) gives its Utility
  judge a veto over its Critic Router rather than ranking on novelty alone.

So the reading rides along with the candidate for a human to weigh; nothing is
dropped, deferred or reordered by it (``read-only-instruments`` invariant 1:
observability, never intervention). Coverage against what the agent already
carries is a different question and belongs to ADR-0074's novelty gate.

**No z-normalization, deliberately.** The same calibration measured a raw
max-cosine spread of 0.108–0.129 with p50 at 0.806 — at or above the nearest-
neighbour ceiling this store has historically topped out at, i.e. all 78
candidates piled on top of each other. Z-scoring turned that into a ~5–6 sd
spread and manufactured a separation the data does not contain. Values here
therefore stay on the cosine scale, and every reading carries the raw
reference distribution it came from (``ref_cos_p50`` / ``ref_cos_spread``) so
a reader can see how much discriminability was available at all — the
ambiguity note of ``read-only-instruments`` invariant 2.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime

import numpy as np

from .knowledge_store import _parse_distilled, pattern_id

logger = logging.getLogger(__name__)

# Reference window: how many of the most recently distilled patterns a
# candidate is measured against. Not a threshold — nothing passes or fails at
# any value of it. Chosen from the calibration's three-point sweep (100 / 300 /
# 1000): ``s_mean`` moved little across the three, and the widest window is the
# least sensitive to a single quiet or busy day.
SURPRISE_REF_K = 1000


@dataclass(frozen=True)
class SurpriseReading:
    """One candidate's distance from the recent distillation window.

    ``rank`` is 1-based over ``s_mean`` within this batch (1 = furthest from
    the recent distribution); ``of`` is the batch size. A rank is a position,
    not a verdict — the batch is not truncated at any rank.
    """

    s_mean: float
    s_nn: float
    rank: int
    of: int
    ref_k: int
    ref_cos_p50: float
    ref_cos_spread: float

    def as_dict(self) -> dict[str, float | int]:
        """Plain dict for the staging sidecar / audit record."""
        return asdict(self)


def _unit(mat: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalize, zero rows left as-is.

    Same zero-norm convention as ``clustering._cosine_matrix`` and
    ``view_metrics.diversity_stats`` — a degenerate row must read the same way
    everywhere embeddings are compared.
    """
    norms = np.linalg.norm(mat, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


def _centroid(vectors: Sequence[Sequence[float]]) -> np.ndarray | None:
    """Mean of the unit-normalized member embeddings, re-normalized.

    Rows of the wrong width are skipped with a warning rather than raising —
    an instrument must never crash its host command
    (``read-only-instruments`` invariant 3).
    """
    rows = [np.asarray(v, dtype=np.float32) for v in vectors if v is not None and len(v)]
    if not rows:
        return None
    width = len(rows[0])
    kept = [r for r in rows if r.shape == (width,)]
    if len(kept) != len(rows):
        logger.warning(
            "insight surprise: skipped %d member embedding(s) of mismatched width",
            len(rows) - len(kept),
        )
    if not kept:
        return None
    return _unit(np.mean(_unit(np.stack(kept)), axis=0))


def _reference_window(patterns: Sequence[dict], ref_k: int) -> tuple[list[str], np.ndarray] | None:
    """The ``ref_k`` most recently distilled embedded patterns, newest first.

    Rows with no embedding or an unparseable ``distilled`` timestamp are out of
    scope: the reading is "distance from what was learned lately", and a row
    with no date cannot be placed on that axis.
    """
    dated: list[tuple[datetime, dict]] = []
    for p in patterns:
        if not p.get("embedding"):
            continue
        when = _parse_distilled(p)
        if when is None:
            continue
        dated.append((when, p))
    if not dated:
        return None
    # Sort on the parsed instant, not the raw string: a row written with a
    # non-UTC offset sorts by its text and lands in the wrong half of "most
    # recent" (the bug class ``knowledge_store._filter_since`` documents).
    dated.sort(key=lambda row: row[0], reverse=True)
    window = [p for _, p in dated[:ref_k]]
    widths = {len(p["embedding"]) for p in window}
    if len(widths) != 1:
        width = max(widths, key=lambda w: sum(1 for p in window if len(p["embedding"]) == w))
        logger.warning(
            "insight surprise: reference window has mixed embedding widths %s — keeping %d",
            sorted(widths),
            width,
        )
        window = [p for p in window if len(p["embedding"]) == width]
        if not window:
            return None
    # Hash only the survivors: ``pattern_id`` is a sha256 per row, and the
    # store is several times ``ref_k``.
    ids = [pattern_id(p) for p in window]
    matrix = _unit(np.asarray([p["embedding"] for p in window], dtype=np.float32))
    return ids, matrix


def compute_surprise(
    candidates: Mapping[str, Sequence[Sequence[float]]],
    patterns: Sequence[dict],
    ref_k: int = SURPRISE_REF_K,
    exclude: Mapping[str, set[str]] | None = None,
) -> dict[str, SurpriseReading]:
    """Read each candidate's distance from the recent distillation window.

    Args:
        candidates: topic → the member embeddings of that cluster.
        patterns: the pattern rows to draw the reference window from.
        ref_k: window size (see ``SURPRISE_REF_K``).
        exclude: topic → pattern ids to mask out of the window for that
            candidate. Its own material must be masked: with the cluster's own
            rows in scope the nearest-neighbour cosine pins to 1.0 and every
            candidate reads the same (calibration, 2026-08-17).

    Returns:
        topic → reading. Candidates with no usable embedding are absent from
        the mapping rather than carrying a placeholder value — a missing
        reading is honest, an invented one is not.
    """
    window = _reference_window(patterns, ref_k)
    if window is None:
        logger.warning("insight surprise: no dated, embedded reference patterns — no reading")
        return {}
    ref_ids, ref_matrix = window
    exclude = exclude or {}
    # Position index so masking a candidate's own members costs O(|own|)
    # instead of an O(ref_k) membership scan per candidate.
    position = {pid: i for i, pid in enumerate(ref_ids)}

    rows: list[tuple[str, SurpriseReading]] = []
    for topic, member_vectors in candidates.items():
        centroid = _centroid(member_vectors)
        if centroid is None or centroid.shape[0] != ref_matrix.shape[1]:
            if centroid is not None:
                logger.warning(
                    "insight surprise: %s centroid width %d != reference width %d — skipped",
                    topic,
                    centroid.shape[0],
                    ref_matrix.shape[1],
                )
            continue
        # Mask the cosine vector, not the reference matrix: fancy-indexing the
        # matrix would copy ref_k x dim floats per candidate to drop a handful
        # of rows.
        cos = ref_matrix @ centroid
        own = [position[pid] for pid in (exclude.get(topic) or ()) if pid in position]
        keep = np.ones(len(ref_ids), dtype=bool)
        keep[own] = False
        if keep.any():
            cos = cos[keep]
        else:
            logger.warning(
                "insight surprise: %s owns the whole reference window — reading unmasked", topic
            )
        rows.append(
            (
                topic,
                SurpriseReading(
                    s_mean=float(1.0 - cos.mean()),
                    s_nn=float(1.0 - cos.max()),
                    rank=0,  # positions are assigned below, once the batch is known
                    of=0,
                    ref_k=len(ref_ids),
                    ref_cos_p50=float(np.median(cos)),
                    ref_cos_spread=float(cos.max() - cos.min()),
                ),
            )
        )

    # Rank on ``s_mean``: the calibration found it steadier than ``s_nn`` and
    # far less sensitive to ``k`` — the nearest neighbour is pinned to the
    # store's ceiling, the distribution centre is not. Ties break on the topic
    # name so the listing is reproducible.
    order = sorted(rows, key=lambda row: (-row[1].s_mean, row[0]))
    total = len(order)
    return {
        topic: replace(reading, rank=idx, of=total)
        for idx, (topic, reading) in enumerate(order, start=1)
    }


def log_surprise(readings: Mapping[str, SurpriseReading]) -> None:
    """Print the batch listing. Enumeration only — nothing acts on it."""
    if not readings:
        return
    ordered = sorted(readings.items(), key=lambda kv: kv[1].rank)
    first = ordered[0][1]
    s_means = [r.s_mean for r in readings.values()]
    logger.info(
        "insight surprise (read-only listing; no candidate is dropped, deferred or "
        "reordered by it): n=%d ref_k=%d batch s_mean spread=%.4f — that spread is "
        "this batch's discriminability budget; near 0.1 it means the ranking "
        "separates very little (calibration 2026-08-17). The per-row ref cos "
        "figures below describe each candidate's own neighbourhood and are a "
        "different distribution.",
        first.of,
        first.ref_k,
        max(s_means) - min(s_means),
    )
    for topic, r in ordered:
        logger.info(
            "  #%d %s s_mean=%.4f s_nn=%.4f (ref cos p50=%.3f spread=%.3f)",
            r.rank,
            topic,
            r.s_mean,
            r.s_nn,
            r.ref_cos_p50,
            r.ref_cos_spread,
        )
