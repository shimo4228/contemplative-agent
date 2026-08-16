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
import time
from typing import Any

import numpy as np
import requests

from ._io import now_iso
from .llm import _classify_request_error, _get_ollama_url, emit_llm_telemetry

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

    Every call past the empty-input shortcut is recorded on the shared
    per-call telemetry channel as ``caller="embed"`` (see :func:`_embed_impl`).
    The shortcut itself returns before the record is built: it does no work to
    attribute, and a row reporting a duration for it would be a fiction. A
    call rejected by the URL guard IS recorded — it was a call, it just failed
    before the socket.
    """
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    tel: dict[str, Any] = {
        "ts": now_iso(timespec="seconds"),
        # Separates embedding cost from generation cost in one log — the
        # reading this instrument exists for (a distill run's wall clock split
        # between the two). Same key the generate rows use, so one grouping
        # answers both questions.
        "caller": "embed",
        # The model that actually served THIS row. Embedding runs on its own
        # model (OLLAMA_EMBEDDING_MODEL), independent of the generation model,
        # and the ADR-0071/0072 calibration is pinned to that identity — a row
        # whose model is unrecorded cannot be read against a calibration.
        "model": _get_embedding_model(),
        "batch_size": len(texts),
        # Size of the input, never the input. len() of untrusted text is not
        # untrusted text (ADR-0065 metadata-only).
        "input_chars": sum(len(t) for t in texts),
        # Rows actually returned. Stays None on every failure path, and a
        # short response (M < N) leaves it below batch_size — the one
        # degradation that parses cleanly and is otherwise only visible in the
        # caller's own guard (distill.py compares shape[0]).
        "rows": None,
        "duration_ms": None,
        # Default covers unexpected exceptions, matching _generate_full: any
        # path that does not explicitly claim success records as an error.
        "outcome": "error",
    }
    started = time.monotonic()
    try:
        return _embed_impl(texts, tel)
    finally:
        tel["duration_ms"] = int((time.monotonic() - started) * 1000)
        emit_llm_telemetry(tel)


def _classify_embed_error(exc: requests.RequestException | ValueError) -> str:
    """Fault class for a failed embed POST, in the generate path's vocabulary.

    The unparsable-body case must be tested FIRST. ``response.json()`` raises
    ``requests.exceptions.JSONDecodeError``, which is *itself* a
    ``RequestException`` (MRO: JSONDecodeError -> InvalidJSONError ->
    RequestException), so asking "transport error?" first swallows it and
    reports a generic ``request_error`` — the ``bad_json`` code would be
    unreachable and the two row kinds would name one fault two ways, which is
    the exact failure sharing the vocabulary is meant to prevent.
    ``_post_ollama`` is not exposed to this because it splits the POST and the
    ``.json()`` into separate ``try`` blocks; this path catches both together,
    so the ordering has to do that work instead.
    """
    if isinstance(exc, (requests.exceptions.InvalidJSONError, ValueError)):
        return "bad_json"
    return _classify_request_error(exc)


def _embed_impl(texts: list[str], tel: dict[str, Any]) -> np.ndarray | None:
    """Body of :func:`embed_texts`; mutates *tel* with outcome metadata.

    Each failure already logs a distinct human-readable line; what is stamped
    here is the machine-readable counterpart. ``error_kind`` is sparse (failure
    rows only) and reuses the generation path's vocabulary wherever the fault
    exists on both — ``bad_url`` and ``bad_json`` are literally the tokens
    ``_post_ollama`` writes — so one ``llm-calls`` file reads under one set of
    words. ``missing_embeddings`` and ``bad_array`` extend it: they are faults
    only an embedding response can have, and folding them into a shared code
    would trade a precise diagnosis for a false sense of a closed enum.

    The circuit breaker is deliberately untouched, as it always has been on
    this path: embedding failures degrade their callers (dedup, views,
    novelty) rather than gate them, and wiring a breaker here would be a
    behavior change smuggled in with an instrument.
    """
    try:
        base_url = _get_ollama_url()
    except ValueError as exc:
        logger.error("Invalid Ollama URL for embedding: %s", exc)
        tel["error_kind"] = "bad_url"
        return None

    url = f"{base_url}/api/embed"
    payload = {
        # Read from the record, not from the environment a second time: the
        # model this row REPORTS and the model the request ASKS FOR are then
        # one value, not two reads of a mutable env that happen to agree.
        "model": tel["model"],
        "input": texts,
    }
    try:
        response = requests.post(url, json=payload, timeout=EMBEDDING_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Embedding request failed: %s", exc)
        tel["error_kind"] = _classify_embed_error(exc)
        return None

    embeddings = data.get("embeddings")
    if not isinstance(embeddings, list) or not embeddings:
        logger.warning("Embedding response missing 'embeddings' field")
        tel["error_kind"] = "missing_embeddings"
        return None

    try:
        array = np.asarray(embeddings, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        logger.warning("Could not parse embeddings array: %s", exc)
        tel["error_kind"] = "bad_array"
        return None

    tel["outcome"] = "ok"
    tel["rows"] = array.shape[0]
    return array


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
