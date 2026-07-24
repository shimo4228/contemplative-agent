"""Local embedding interface via Ollama REST API.

Thin wrapper over Ollama's /api/embed endpoint plus the cosine
similarity primitive. Used by stocktake, distill (dedup), and the views
mechanism (ADR-0019) to resolve semantic similarity that
SequenceMatcher cannot detect (structural similarity hidden by
vocabulary variation).
"""

from __future__ import annotations

import logging
import os

import numpy as np
import requests

from .llm import _get_ollama_url

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_TIMEOUT_SECONDS = 60
EMBEDDING_DIM = 768  # nomic-embed-text dimension

# Calibration pin (ADR-0071 / ADR-0072). Every similarity threshold in this
# codebase (view floors 0.66/0.55, dedup 0.90/0.80, novelty θ=0.35, cluster
# 0.70/0.65) and the three-point calibration scale below were measured on
# THIS exact model. A same-dimension model swap passes every shape check
# (cosine dim guard, view_metrics row drop) while silently invalidating all
# of them — so the model identity itself is pinned here and compared at
# startup / report time. Re-measure the scale and update both constants
# whenever the geometry changes (model swap, seed rewrite, normalization).
CALIBRATED_EMBEDDING_MODEL = "nomic-embed-text"
# Three-point scale measured 2026-07-03 (ADR-0071 §readings, ADR-0072 §17-24):
# floor = cosine of deliberately unrelated texts vs corpus/seeds,
# corpus_mean = pairwise mean over the live pattern pool,
# top_band = consumed-view top matches.
CALIBRATION_ANCHORS = {
    "floor": (0.33, 0.46),
    "corpus_mean": 0.554,
    "top_band": (0.68, 0.77),
}


def _get_embedding_model() -> str:
    return os.environ.get("OLLAMA_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)


def calibration_drift_note() -> str | None:
    """Return a warning string when the active embedding model is not the
    calibration model, else None.

    Read-only instrument guard (ADR-0071 invariant 1): the note feeds the
    operator via logs / report output, never a gate. String comparison only —
    no I/O, safe to call on every command startup.
    """
    active = _get_embedding_model()
    if active == CALIBRATED_EMBEDDING_MODEL:
        return None
    return (
        f"embedding model {active!r} != calibration model "
        f"{CALIBRATED_EMBEDDING_MODEL!r}: all similarity thresholds and the "
        f"three-point scale (floor {CALIBRATION_ANCHORS['floor']}, corpus mean "
        f"{CALIBRATION_ANCHORS['corpus_mean']}, top band "
        f"{CALIBRATION_ANCHORS['top_band']}) were calibrated on the pinned "
        "model and are unreliable until re-measured (ADR-0071/0072)"
    )


def embed_texts(texts: list[str]) -> np.ndarray | None:
    """Embed a list of texts using Ollama. Returns (N, D) float array or None.

    On any failure (network, model missing, malformed response), returns
    None — caller is expected to handle gracefully (skip similarity-based
    work).
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    try:
        base_url = _get_ollama_url()
    except ValueError as exc:
        logger.error("Invalid Ollama URL for embedding: %s", exc)
        return None

    url = f"{base_url}/api/embed"
    payload = {
        "model": _get_embedding_model(),
        "input": texts,
    }
    try:
        response = requests.post(url, json=payload, timeout=EMBEDDING_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Embedding request failed: %s", exc)
        return None

    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        logger.warning("Embedding response missing 'embeddings' field")
        return None

    try:
        return np.asarray(embeddings, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        logger.warning("Could not parse embeddings array: %s", exc)
        return None


def embed_one(text: str) -> np.ndarray | None:
    """Embed a single text. Returns (D,) float vector or None."""
    result = embed_texts([text])
    if result is None or result.shape[0] == 0:
        return None
    return result[0]


def cosine(v1: np.ndarray, v2: np.ndarray) -> float:
    """Cosine similarity between two 1D vectors. Zero vectors → 0.0.

    A shape mismatch (e.g. an embedding-model swap without re-backfilling the
    stored vectors) also returns 0.0 rather than raising: the two vectors live
    in different spaces, so they are correctly treated as dissimilar, and the
    WARNING surfaces the misconfiguration instead of crashing every
    distill / insight / view command (ultracode sweep 2026-06-23).
    """
    if v1.shape != v2.shape:
        logger.warning(
            "cosine: embedding shape mismatch %s vs %s — treating as "
            "dissimilar (0.0); likely an embedding-model change without a "
            "re-backfill of stored vectors",
            v1.shape,
            v2.shape,
        )
        return 0.0
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


# find_similar / centroid / argmax_centroid / cosine_similarity_matrix
# were removed as dead code (no production callers; view assignment uses
# ViewRegistry._rank, dedup uses its own matrix path).
