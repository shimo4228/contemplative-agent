"""Shadow constitution instrument: patterns-only synthesis, observe-only (ADR-0092).

Runs the amendment's retrieval path but synthesizes a constitution WITHOUT
injecting the current one — the divergence between the shadow text and the
live constitution is the reading. The live constitution is read only to
compute that reading (sha256 + embedding cosine), never fed to the LLM.
Nothing here writes to the constitution; the only writes are the append-only
JSONL record and the caller-facing return value.

Reading ambiguity (read-only-instruments discipline): the reading is partially
circular through THREE channels — the input patterns were produced under the
full action prompt, which includes the live constitution (ADR-0058 keeps
axioms at action time); the ``constitutional`` view that *selects* the
patterns is itself seeded from the live constitution files
(``${CONSTITUTION_DIR}`` seed, ADR-0019); and both arms' prompts impose the
same per-section shape constraints, so a whole-doc cosine is inflated by
shared genre regardless of content. Convergence therefore measures
"experience-supported" only jointly with that shaping — the divergent
clauses and the free section inventory, not convergent wording, are the
primary signal (ADR-0092 Decision 5 reserves a floor anchor for this).
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from ._io import append_jsonl_restricted, b64_audit_fields, now_iso
from .constitution import MIN_PATTERNS_REQUIRED, render_constitutional_patterns
from .embeddings import _get_embedding_model, calibration_drift_note, cosine, embed_texts
from .knowledge_store import epistemic_counts_for, pattern_id
from .llm import generate_full, get_distill_system_prompt, validate_identity_content
from .memory import KnowledgeStore
from .prompts import CONSTITUTION_SYNTHESIZE_PROMPT
from .views import ViewRegistry

logger = logging.getLogger(__name__)

# Same budget as the skill-selection shadow log (ADR-0076): generous enough
# for a full constitution + prompt, bounded so one record cannot balloon.
_MAX_SHADOW_AUDIT_BYTES = 65536


@dataclass(frozen=True)
class ShadowConstitutionResult:
    """Result of one shadow synthesis run.

    ``cosine_vs_current`` is baked at generation time against the constitution
    text whose digest is ``current_sha256`` — the live text will change across
    amendments, so the pair travels together (replayable-audit-logs: metrics
    against mutable state are recorded, never recomputed).
    """

    text: str
    validation_passed: bool
    cosine_vs_current: float | None
    cosine_reason: str
    current_sha256: str
    pattern_ids: tuple[str, ...] = ()
    epistemic_counts: dict[str, int] = field(default_factory=dict)
    thinking: str | None = None


def _append_record(log_path: Path | None, record: dict[str, Any]) -> None:
    """Best-effort append: the instrument must never crash its host command."""
    if log_path is None:
        return
    try:
        append_jsonl_restricted(log_path, record)
    except Exception as exc:  # noqa: BLE001 — degrade-never-abort (ADR-0075)
        logger.warning("Failed to append shadow-constitution record to %s: %s", log_path, exc)


def _base_record(verdict: str) -> dict[str, Any]:
    return {
        "ts": now_iso(timespec="seconds"),
        "event": "shadow_constitution",
        "verdict": verdict,
    }


def _abstain(
    log_path: Path | None,
    verdict: str,
    msg: str,
    *,
    prompt: str | None = None,
    level: int = logging.WARNING,
    extra: dict[str, Any] | None = None,
) -> str:
    logger.log(level, msg)
    record = _base_record(verdict)
    record["message"] = msg
    if extra:
        record.update(extra)
    record.update(b64_audit_fields("prompt", prompt, max_bytes=_MAX_SHADOW_AUDIT_BYTES))
    record.update(b64_audit_fields("output", None, max_bytes=_MAX_SHADOW_AUDIT_BYTES))
    _append_record(log_path, record)
    return msg


def _divergence_reading(shadow_text: str, current_constitution: str) -> tuple[float | None, str]:
    """One embed round-trip for both texts (same model instance, same regime).

    A degraded reading is ``None`` + reason — never 0.0: for this instrument
    0.0 is the strongest possible divergence signal, so letting an embedding
    failure masquerade as it would be exactly the silent fallback ADR-0075
    forbids (code review 2026-08-11).
    """
    vecs = embed_texts([shadow_text, current_constitution])
    if vecs is None:
        return None, "embed_unavailable"
    if vecs.ndim != 2 or vecs.shape[0] != 2:
        return None, "embed_malformed"
    shadow_vec, current_vec = vecs[0], vecs[1]
    if not (np.any(shadow_vec) and np.any(current_vec)):
        return None, "degenerate_vector"
    return cosine(shadow_vec, current_vec), "ok"


def synthesize_shadow_constitution(
    knowledge_store: KnowledgeStore | None = None,
    constitution_dir: Path | None = None,
    view_registry: ViewRegistry | None = None,
    *,
    log_path: Path | None,
) -> ShadowConstitutionResult | str:
    """Synthesize a constitution from constitutional patterns alone.

    Mirrors ``amend_constitution``'s retrieval and guard structure (same view,
    same ``MIN_PATTERNS_REQUIRED``) so the two arms stay comparable, but the
    prompt receives only the patterns. Returns the result on success or an
    error message string; either way the outcome lands in ``log_path`` with a
    reason code. ``log_path`` is keyword-only and has no default so disabling
    the record (``None`` — kill switch by absence) is a conscious choice,
    never an omission (observability-by-default, ADR-0075).

    The divergence baseline is the concatenation of ALL ``*.md`` files in
    ``constitution_dir`` — the same text ``load_constitution`` feeds the
    runtime — deliberately unlike ``amend_constitution``, which targets only
    the first file because that is the file it rewrites (security review
    2026-08-11: a first-file-only baseline would silently misdescribe
    multi-file installs).
    """
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if view_registry is None:
        return _abstain(
            log_path,
            "no_view_registry",
            "synthesize_shadow_constitution requires a ViewRegistry (ADR-0026): "
            "constitutional patterns are retrieved via view cosine.",
        )

    matched = view_registry.find_by_view("constitutional", knowledge.get_live_patterns())
    if len(matched) < MIN_PATTERNS_REQUIRED:
        return _abstain(
            log_path,
            "insufficient_patterns",
            f"Insufficient constitutional patterns ({len(matched)}/{MIN_PATTERNS_REQUIRED}). "
            f"More ethical experience needed before a shadow synthesis is meaningful.",
            # Routine early-life state, not a fault (parity with constitution.py).
            level=logging.INFO,
            extra={"pattern_count": len(matched)},
        )

    if not CONSTITUTION_SYNTHESIZE_PROMPT:
        return _abstain(
            log_path, "prompt_missing", "constitution_synthesize.md prompt template not found."
        )

    if constitution_dir is None:
        return _abstain(
            log_path,
            "no_constitution_dir",
            "No constitution directory configured (needed for the divergence reading).",
        )

    axiom_files = sorted(constitution_dir.glob("*.md"))
    if not axiom_files:
        return _abstain(
            log_path, "no_constitution_files", f"No constitution files found in {constitution_dir}"
        )

    try:
        contents = [f.read_text(encoding="utf-8").strip() for f in axiom_files]
    except OSError as exc:
        return _abstain(
            log_path,
            "constitution_read_error",
            f"Failed to read constitution files in {constitution_dir}: {exc}",
        )
    current_constitution = "\n\n".join(c for c in contents if c)
    if not current_constitution:
        return _abstain(log_path, "empty_constitution", "Constitution files are empty.")
    current_sha256 = hashlib.sha256(current_constitution.encode("utf-8")).hexdigest()
    constitution_files = [f.name for f in axiom_files]

    constitutional_text = render_constitutional_patterns(matched)
    # The instrument's core invariant: the prompt is patterns-only. The
    # current constitution never enters it (and ADR-0058 keeps it out of the
    # distill system prompt) — the whole reading rests on this absence.
    prompt = CONSTITUTION_SYNTHESIZE_PROMPT.format(constitutional_patterns=constitutional_text)

    lineage: dict[str, Any] = {
        "pattern_count": len(matched),
        "pattern_ids": [pattern_id(p) for p in matched],
        "epistemic_counts": epistemic_counts_for(matched),
        "current_sha256": current_sha256,
        "constitution_files": constitution_files,
    }

    out = generate_full(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        caller="constitution.shadow",
        think=True,
        drop_truncated=True,
    )
    if out is None or out.text is None:
        return _abstain(
            log_path,
            # Covers both backend outage and drop_truncated: generate_full
            # returns None for either, so they are not separable at this seam.
            # The per-call telemetry log keeps done_reason for the split.
            "llm_failure",
            "LLM failed to generate shadow constitution (outage or truncation drop).",
            prompt=prompt,
            extra=lineage,
        )

    shadow_text = out.text.strip()
    validation_passed = validate_identity_content(shadow_text)
    cosine_vs_current, cosine_reason = _divergence_reading(shadow_text, current_constitution)
    if cosine_reason != "ok":
        logger.warning("Shadow divergence reading degraded: %s", cosine_reason)

    result = ShadowConstitutionResult(
        text=shadow_text,
        validation_passed=validation_passed,
        cosine_vs_current=cosine_vs_current,
        cosine_reason=cosine_reason,
        current_sha256=current_sha256,
        pattern_ids=tuple(lineage["pattern_ids"]),
        epistemic_counts=dict(lineage["epistemic_counts"]),
        thinking=out.thinking,
    )

    record = _base_record("ok" if validation_passed else "validation_failed")
    record.update(lineage)
    record.update(
        {
            "cosine_vs_current": cosine_vs_current,
            "cosine_reason": cosine_reason,
            # Longitudinal comparability (ADR-0071 calibration discipline):
            # a model swap silently changes the cosine scale, so the model
            # identity and any drift note travel with every reading.
            "embedding_model": _get_embedding_model(),
            "calibration_drift": calibration_drift_note(),
            # Length regimes: the embedder truncates long inputs server-side,
            # so record both sizes for the reader to spot asymmetric regimes.
            "shadow_chars": len(shadow_text),
            "current_chars": len(current_constitution),
        }
    )
    record.update(b64_audit_fields("prompt", prompt, max_bytes=_MAX_SHADOW_AUDIT_BYTES))
    record.update(b64_audit_fields("output", shadow_text, max_bytes=_MAX_SHADOW_AUDIT_BYTES))
    record.update(b64_audit_fields("thinking", out.thinking, max_bytes=_MAX_SHADOW_AUDIT_BYTES))
    _append_record(log_path, record)

    return result
