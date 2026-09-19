"""The two judging stages around insight extraction, and their audit log.

RFC-0042 items 2 and 4. Both stages are enum-constrained, temperature 0, and
fail open with a reason code:

* **naming** — before the body is written, one call per surviving cluster says
  whether the observations ``reconfirm`` an existing skill, are
  ``insufficient``, ask to ``revise`` a named one, or are ``new``. Only ``new``
  proceeds to the body call. ``revise`` is recorded and stops (RFC-0042 option
  A: the goal is the volume reaching the Saturday gate, and a replacement path
  works against it; the recorded proposals are the material for deciding
  whether to add one).
* **duplicate** — after the body, description and name exist, one call per
  candidate compares it with the same nearest-5 store slice and answers
  ``duplicate`` / ``distinct``. Only ``distinct`` reaches staging.

The order is the point (ADR-0084): a judge placed before the artifact has no
artifact to compare, which is why the pre-extraction novelty gate moves counts
without separating populations while the post-extraction one separates them
(``docs/evidence/rfc-0041/`` reading 3 — at t=0, 33/68 gate-rejected,
12/53 leave-one-out adopted, 0/7 control).

Both calls run ``think=False``. The replays that justify them ran that way
(the post-extraction judge replay — removed in ``bcc97e2``, results frozen in
``docs/evidence/rfc-0041/`` — and the novelty gate), so think-ON
here would be an unmeasured condition; ADR-0069's think-ON stays where the
generation is (the body call).

Neither stage is a weekly instrument (ADR-0101): the reason codes live in this
log and the Saturday gate reads a single count line. Nothing here computes a
rate, a trend, or a metric column.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import llm
from ._io import strip_code_fence
from .skill_projection import SkillProjection

logger = logging.getLogger(__name__)

# Sampling temperature of both judging calls (RFC-0042). At 0 the RFC-0041
# replay is bit-identical across repetitions; at the previous default of 1.0
# individual verdicts reproduced at barely chance level (kappa 0.04-0.24).
STAGE_TEMPERATURE = 0.0

# Observation text shown per cluster member in the naming prompt. The naming
# call sees the whole cluster (up to ``thresholds.MAX_BATCH`` = 10 members)
# plus five rendered store projections; clipping each member keeps the worst
# case far inside the 32k window that ``llm``'s pre-flight guards.
NAMING_OBSERVATION_CHARS = 400

NAMING_RECORD_KIND = "insight_naming"
DUPLICATE_RECORD_KIND = "insight_duplicate"

# Per-field cap on the base64-stored prompt / output, same shape and size as
# the novelty log's. One record per cluster and per candidate, so a weekly run
# at the ~30-cluster scale writes well under a megabyte.
_MAX_STAGE_AUDIT_BYTES = 131072

# Why a stage produced no verdict and failed open. ``no_store`` and
# ``retrieval_unavailable`` mean the comparison slice could not be built at
# all; the rest are the call's own failures.
StageFailReason = Literal[
    "llm_none",
    "unparseable",
    "off_enum",
    "no_store",
    "retrieval_unavailable",
]

NamingKind = Literal["reconfirm", "insufficient", "revise", "new"]
_NAMING_KINDS: tuple[NamingKind, ...] = ("reconfirm", "insufficient", "revise", "new")

DuplicateVerdictValue = Literal["duplicate", "distinct"]


@dataclass(frozen=True)
class NamingVerdict:
    """What the naming call said about one cluster."""

    kind: NamingKind
    target_skill: str | None
    change_reason: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateVerdict:
    """What the duplicate judge said about one written candidate."""

    verdict: DuplicateVerdictValue
    nearest: str | None


def append_stage_record(audit_path: Path | None, record: dict, *, what: str) -> None:
    """Append one stage record, best-effort — an instrument never breaks insight."""
    if audit_path is None:
        return
    try:
        from ._io import append_jsonl_restricted

        append_jsonl_restricted(audit_path, record)
    except Exception as exc:  # instrumentation must never break insight
        logger.warning("insight %s audit record failed: %s", what, exc)


def _audit(
    audit_path: Path | None,
    *,
    kind: str,
    what: str,
    prompt: str | None,
    raw_output: str | None,
    fields: dict,
) -> None:
    """Build and append one replay record (ADR-0075).

    The prompt and the raw output are the untrusted-bearing halves (cluster
    observations and store bodies go in, model prose comes out), so they are
    stored base64 + sha256 and bounded; verdicts, reason codes, temperature and
    the store names shown stay in plain text where a reading can group on them.
    """
    if audit_path is None:
        return
    try:
        from ._io import b64_audit_fields, now_iso

        record: dict = {
            "kind": kind,
            "ts": now_iso("seconds"),
            "temperature": STAGE_TEMPERATURE,
            **fields,
            **b64_audit_fields("prompt", prompt, max_bytes=_MAX_STAGE_AUDIT_BYTES),
            **b64_audit_fields("output", raw_output, max_bytes=_MAX_STAGE_AUDIT_BYTES),
        }
    except Exception as exc:  # instrumentation must never break insight
        logger.warning("insight %s audit record failed: %s", what, exc)
        return
    append_stage_record(audit_path, record, what=what)


def _parse_object(raw: str) -> dict | None:
    """Parse the one JSON object a constrained call returns, else ``None``.

    Tolerates a code fence and surrounding prose the same way the novelty
    gate's parser does: ``format=`` makes both unlikely, and an injected
    backend that ignores the schema is exactly when tolerance is worth having.
    """
    text = strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# Stage 1: the naming call
# ---------------------------------------------------------------------------


def _render_observations(observations: list[str], ids: tuple[str, ...]) -> str:
    return "\n".join(
        f"- [{oid}] {text[:NAMING_OBSERVATION_CHARS]}"
        for oid, text in zip(ids, observations, strict=False)
    )


def _naming_schema(store_names: list[str], evidence_ids: list[str]) -> dict:
    """Enum-constrain every field the RFC-0027 runs got wrong as free strings.

    The format violations that motivated this (target names losing their date
    suffix 5/5, evidence ids swapped 2/12) were both in fields typed as an
    unconstrained ``string``; 512 enum-constrained calls in the RFC-0041 replay
    produced zero off-enum and zero parse failures.
    """
    return {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": list(_NAMING_KINDS)},
            "target_skill": {"enum": [*store_names, None]},
            "change_reason": {"type": "string"},
            "evidence_ids": {
                "type": "array",
                "items": {"type": "string", "enum": evidence_ids},
            },
        },
        "required": ["kind", "target_skill", "change_reason", "evidence_ids"],
    }


def judge_naming(
    topic: str,
    observations: list[str],
    evidence_ids: tuple[str, ...],
    nearest: tuple[SkillProjection, ...] | None,
    *,
    audit_path: Path | None = None,
) -> NamingVerdict | None:
    """Name what this cluster is relative to the store, or ``None`` to fail open.

    ``nearest`` is ``None`` when the store slice could not be built; the stage
    then has nothing to compare against and the cluster passes to the body call
    unjudged, recorded with ``reason=no_store``.
    """
    from .prompts import INSIGHT_NAMING_PROMPT, INSIGHT_NAMING_SYSTEM_PROMPT

    common = {"topic": topic, "store_shown": [p.name for p in nearest or ()]}
    if not nearest:
        logger.warning(
            "insight naming: no store slice for cluster [%s] — passing it through "
            "unjudged (reason=no_store)",
            topic,
        )
        _audit(
            audit_path,
            kind=NAMING_RECORD_KIND,
            what="naming",
            prompt=None,
            raw_output=None,
            fields={**common, "verdict": None, "reason": "no_store"},
        )
        return None

    store_names = [p.name for p in nearest]
    prompt = INSIGHT_NAMING_PROMPT.format(
        observations=_render_observations(observations, evidence_ids),
        existing_skills="\n\n".join(p.render() for p in nearest),
    )
    out = llm.generate_full(
        prompt,
        system=INSIGHT_NAMING_SYSTEM_PROMPT,
        num_predict=600,
        format=_naming_schema(store_names, list(evidence_ids)),
        temperature=STAGE_TEMPERATURE,
        caller="insight.naming",
        drop_truncated=True,
    )

    def _fail(reason: StageFailReason, raw: str | None) -> None:
        logger.warning(
            "insight naming: cluster [%s] unjudged, passing it through (reason=%s)",
            topic,
            reason,
        )
        _audit(
            audit_path,
            kind=NAMING_RECORD_KIND,
            what="naming",
            prompt=prompt,
            raw_output=raw,
            fields={**common, "verdict": None, "reason": reason},
        )

    if out is None or out.text is None:
        _fail("llm_none", None)
        return None
    parsed = _parse_object(out.text)
    if parsed is None:
        _fail("unparseable", out.text)
        return None
    kind = parsed.get("kind")
    if kind not in _NAMING_KINDS:
        _fail("off_enum", out.text)
        return None

    target = parsed.get("target_skill")
    # A target the call was not shown is dropped rather than trusted — the same
    # rule the novelty gate applies to hallucinated cluster ids. ``revise``
    # without a real target has nothing to revise, so it degrades to a
    # judgment with no target and is recorded as such.
    if not isinstance(target, str) or target not in store_names:
        target = None
    ids = parsed.get("evidence_ids")
    evidence = (
        tuple(i for i in ids if isinstance(i, str) and i in evidence_ids)
        if (isinstance(ids, list))
        else ()
    )
    reason_text = parsed.get("change_reason")
    verdict = NamingVerdict(
        kind=kind,
        target_skill=target,
        change_reason=reason_text if isinstance(reason_text, str) else "",
        evidence_ids=evidence,
    )
    _audit(
        audit_path,
        kind=NAMING_RECORD_KIND,
        what="naming",
        prompt=prompt,
        raw_output=out.text,
        fields={
            **common,
            "verdict": verdict.kind,
            "reason": None,
            "target_skill": verdict.target_skill,
            "change_reason": verdict.change_reason,
            "evidence_ids": list(verdict.evidence_ids),
        },
    )
    return verdict


# ---------------------------------------------------------------------------
# Stage 2: the post-extraction duplicate judge
# ---------------------------------------------------------------------------


def _duplicate_schema(store_names: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["duplicate", "distinct"]},
            "nearest": {"type": "string", "enum": store_names},
        },
        "required": ["verdict", "nearest"],
    }


def judge_duplicate(
    candidate: SkillProjection,
    nearest: tuple[SkillProjection, ...] | None,
    *,
    audit_path: Path | None = None,
) -> DuplicateVerdict | None:
    """Judge a written candidate against the store, or ``None`` to fail open."""
    from .prompts import INSIGHT_DUPLICATE_PROMPT, INSIGHT_DUPLICATE_SYSTEM_PROMPT

    common = {"candidate": candidate.name, "store_shown": [p.name for p in nearest or ()]}
    if not nearest:
        logger.warning(
            "insight duplicate judge: no store slice for candidate %r — staging it "
            "unjudged (reason=no_store)",
            candidate.name,
        )
        _audit(
            audit_path,
            kind=DUPLICATE_RECORD_KIND,
            what="duplicate",
            prompt=None,
            raw_output=None,
            fields={**common, "verdict": None, "reason": "no_store"},
        )
        return None

    store_names = [p.name for p in nearest]
    prompt = INSIGHT_DUPLICATE_PROMPT.format(
        candidate=candidate.render(),
        store="\n\n".join(p.render() for p in nearest),
    )
    out = llm.generate_full(
        prompt,
        system=INSIGHT_DUPLICATE_SYSTEM_PROMPT,
        num_predict=200,
        format=_duplicate_schema(store_names),
        temperature=STAGE_TEMPERATURE,
        caller="insight.duplicate",
        drop_truncated=True,
    )

    def _fail(reason: StageFailReason, raw: str | None) -> None:
        logger.warning(
            "insight duplicate judge: candidate %r unjudged, staging it (reason=%s)",
            candidate.name,
            reason,
        )
        _audit(
            audit_path,
            kind=DUPLICATE_RECORD_KIND,
            what="duplicate",
            prompt=prompt,
            raw_output=raw,
            fields={**common, "verdict": None, "reason": reason},
        )

    if out is None or out.text is None:
        _fail("llm_none", None)
        return None
    parsed = _parse_object(out.text)
    if parsed is None:
        _fail("unparseable", out.text)
        return None
    value = parsed.get("verdict")
    if value not in ("duplicate", "distinct"):
        _fail("off_enum", out.text)
        return None
    nearest_name = parsed.get("nearest")
    if not isinstance(nearest_name, str) or nearest_name not in store_names:
        nearest_name = None
    verdict = DuplicateVerdict(verdict=value, nearest=nearest_name)
    _audit(
        audit_path,
        kind=DUPLICATE_RECORD_KIND,
        what="duplicate",
        prompt=prompt,
        raw_output=out.text,
        fields={**common, "verdict": verdict.verdict, "reason": None, "nearest": verdict.nearest},
    )
    return verdict
