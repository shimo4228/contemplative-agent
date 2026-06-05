"""Local embedding interface via Ollama REST API.

Thin wrapper over Ollama's /api/embed endpoint plus the cosine
similarity primitive. Used by stocktake, distill (dedup), and the views
mechanism (ADR-0009) to resolve semantic similarity that
SequenceMatcher cannot detect (structural similarity hidden by
vocabulary variation).
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

import numpy as np
import requests

from .llm import _get_ollama_url

logger = logging.getLogger(__name__)

_DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_TIMEOUT_SECONDS = 60
EMBEDDING_DIM = 768  # nomic-embed-text dimension


def _get_embedding_model() -> str:
    return os.environ.get("OLLAMA_EMBEDDING_MODEL", _DEFAULT_EMBEDDING_MODEL)


def embed_texts(texts: List[str]) -> Optional[np.ndarray]:
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


def embed_one(text: str) -> Optional[np.ndarray]:
    """Embed a single text. Returns (D,) float vector or None."""
    result = embed_texts([text])
    if result is None or result.shape[0] == 0:
        return None
    return result[0]


def cosine(v1: np.ndarray, v2: np.ndarray) -> float:
    """Cosine similarity between two 1D vectors. Zero vectors → 0.0."""
    n1 = float(np.linalg.norm(v1))
    n2 = float(np.linalg.norm(v2))
    if n1 == 0.0 or n2 == 0.0:
        return 0.0
    return float(np.dot(v1, v2) / (n1 * n2))


# find_similar / centroid / argmax_centroid / cosine_similarity_matrix
# were removed as dead code (no production callers; view assignment uses
# ViewRegistry._rank, dedup uses its own matrix path).
