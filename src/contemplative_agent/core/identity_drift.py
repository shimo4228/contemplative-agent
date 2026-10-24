"""Identity version-distance instrument: read-only, record-only (P3-04.8).

At each ``distill-identity --stage`` one row is appended to
``logs/identity-drift.jsonl`` comparing the live ``identity.md`` with the staged
candidate: embedding cosine, sentence retention, and the count of sentences that
carry dissolution vocabulary. Nothing here steers: no gate, threshold or
generation step reads the row (ADR-0071 read-only composition, ADR-0101
consumption plan in ADR-0091's amendment).

Why counts and not rates. An identity is 694-954 B, about 8-12 sentences. A rate
over that denominator reads as more resolution than it has, so the row stores
counts (``k`` of ``n``) and the reader attaches a Wilson interval
(``scripts/_stats.wilson_ci``; counts only when ``n < 10``). The writer does not
import ``scripts/``, which is not a package.

Series. The row is written for every staged candidate ("all staged"). The
"adopted only" series is a join at read time: ``candidate_sha256[:16]`` equals
the ``content_hash`` of the matching ``staged`` and ``approved`` rows in
``audit.jsonl``. That holds because the caller passes the candidate exactly as
staged (``staging.ensure_trailing_newline`` already applied): the one
normalisation rule stays in ``cli/staging.py`` rather than being spelled twice. Keeping the two series
separable is the point — rejection alone can make a stream of adopted versions
look stable.

Degraded readings are ``None`` with a reason code, never ``0.0``: cosine 0.0
would read as maximal drift (same rule as ``constitution_shadow``).
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from ._io import append_jsonl_restricted, b64_audit_fields, now_iso
from .embeddings import _get_embedding_model, cosine, embed_texts

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Identity texts are agent-written and short; the cap only bounds a runaway row.
_MAX_TEXT_AUDIT_BYTES = 16384

# Dissolution vocabulary (the register the 2026-08 and 2026-09 identities moved
# through: "fluid texture" -> "structural tension"). Lexical and deliberately
# small; the reading is the series, not any one word. A change to this table is
# a change to the series, so it needs a dated note in the ADR.
DISSOLUTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "fluid": re.compile(r"\bfluid\w*", re.IGNORECASE),
    "dissolve": re.compile(r"\bdissol\w*", re.IGNORECASE),
    "texture": re.compile(r"\btextur\w*", re.IGNORECASE),
    "tension": re.compile(r"\btension\w*", re.IGNORECASE),
}

# A sentence that tells the agent it may stay silent / not reply. Shared with
# the weekly materials column (P3-06.9 (d)): one definition, imported there.
# Lexical, so it reads a flag, not a stance. The template identities carry one
# ("it's okay not to respond to everything"); the production identity may not.
SILENCE_PERMISSION = re.compile(
    r"(?:okay|ok|fine|free|allowed|permitted|enough)\s+(?:for\s+me\s+)?(?:to\s+)?"
    r"(?:not\s+(?:to\s+)?(?:respond|reply|comment|speak|answer)|stay\s+silent|remain\s+silent)"
    r"|(?:do\s+not|don't|need\s+not|needn't)\s+(?:have\s+to\s+|need\s+to\s+)?"
    r"(?:respond|reply|comment|answer)\s+to\s+everything",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_NORMALIZE_WS = re.compile(r"\s+")


def split_sentences(text: str) -> list[str]:
    """Split on sentence-final punctuation and newlines; drop blanks and bullets' markers."""
    parts = (p.strip().lstrip("-*#> ").strip() for p in _SENTENCE_SPLIT.split(text))
    return [p for p in parts if p]


def _norm(sentence: str) -> str:
    return _NORMALIZE_WS.sub(" ", sentence).strip().lower().strip(".!?;: ")


def sentence_retention(current: Sequence[str], candidate: Sequence[str]) -> dict[str, int]:
    """Counts of the current sentences kept verbatim (normalised) in the candidate."""
    cand = {_norm(s) for s in candidate}
    cur_norm = [_norm(s) for s in current]
    cur = set(cur_norm)
    return {
        "current_sentences": len(current),
        "retained_sentences": sum(1 for s in cur_norm if s in cand),
        "candidate_sentences": len(candidate),
        "novel_sentences": sum(1 for s in candidate if _norm(s) not in cur),
    }


def vocabulary_counts(sentences: Sequence[str]) -> dict[str, int]:
    """Sentence counts per dissolution word, over ``n`` sentences."""
    counts = {"sentences": len(sentences)}
    for name, pattern in DISSOLUTION_PATTERNS.items():
        counts[name] = sum(1 for s in sentences if pattern.search(s))
    counts["any"] = sum(
        1 for s in sentences if any(p.search(s) for p in DISSOLUTION_PATTERNS.values())
    )
    return counts


def has_silence_permission(text: str) -> bool:
    return bool(SILENCE_PERMISSION.search(_NORMALIZE_WS.sub(" ", text)))


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _cosine_reading(
    current: str,
    candidate: str,
    embed: Callable[[list[str]], np.ndarray | None],
) -> tuple[float | None, str]:
    vecs = embed([current, candidate])
    if vecs is None:
        return None, "embed_unavailable"
    if vecs.ndim != 2 or vecs.shape[0] != 2:
        return None, "embed_malformed"
    if not (np.any(vecs[0]) and np.any(vecs[1])):
        return None, "degenerate_vector"
    return round(float(cosine(vecs[0], vecs[1])), 4), "ok"


def measure_identity_drift(
    current: str | None,
    candidate: str,
    *,
    embed: Callable[[list[str]], np.ndarray | None] = embed_texts,
) -> dict[str, Any]:
    """Build one drift row. Pure apart from the injected embedder."""
    cand_sents = split_sentences(candidate)
    row: dict[str, Any] = {
        "ts": now_iso(timespec="seconds"),
        "event": "identity_drift",
        "schema_version": SCHEMA_VERSION,
        "candidate_sha256": _sha256(candidate),
        "embedding_model": _get_embedding_model(),
        "candidate_vocabulary": vocabulary_counts(cand_sents),
        "candidate_silence_permission": has_silence_permission(candidate),
    }
    if current is None or not current.strip():
        row.update(
            verdict="no_current",
            current_sha256=None,
            cosine=None,
            cosine_reason="no_current",
        )
    else:
        cur_sents = split_sentences(current)
        value, reason = _cosine_reading(current, candidate, embed)
        row.update(
            verdict="ok" if value is not None else reason,
            current_sha256=_sha256(current),
            cosine=value,
            cosine_reason=reason,
            current_vocabulary=vocabulary_counts(cur_sents),
            current_silence_permission=has_silence_permission(current),
            retention=sentence_retention(cur_sents, cand_sents),
        )
    row.update(b64_audit_fields("candidate", candidate, max_bytes=_MAX_TEXT_AUDIT_BYTES))
    row.update(b64_audit_fields("current", current, max_bytes=_MAX_TEXT_AUDIT_BYTES))
    return row


def record_identity_drift(
    candidate: str,
    *,
    identity_path: Path,
    log_path: Path,
    embed: Callable[[list[str]], np.ndarray | None] = embed_texts,
) -> dict[str, Any] | None:
    """Append one drift row; never raises (an instrument must not abort its host).

    Returns the row, or ``None`` when it could not be built or written (logged).
    """
    try:
        try:
            current: str | None = identity_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            current = None
        row = measure_identity_drift(current, candidate, embed=embed)
        append_jsonl_restricted(log_path, row)
        return row
    except Exception as exc:  # noqa: BLE001 — degrade-never-abort (ADR-0075)
        logger.warning("identity-drift record failed (%s): %s", log_path, exc)
        return None
