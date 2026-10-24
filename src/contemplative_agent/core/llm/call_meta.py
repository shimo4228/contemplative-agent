"""Identity columns of an ``llm-calls`` row: ``kind``, ``schema``, ``template``.

Added by P1-07.13 so a row says what family it is, which generation of the row
shape wrote it, and which prompt template (by file stem) the call was built
from. The digest of that template is in the session-start episode's
``prompt_digests`` (``core.provenance``), joined on ``session_id``.

Additive only: a row written before this carries none of the three, and a row
with no ``kind`` reads as ``generation`` exactly as before.
"""

from __future__ import annotations

from typing import Any

# Bump when the row's shape changes in a way a reader must branch on.
LLM_CALLS_SCHEMA = 2

KIND_GENERATION = "generation"
KIND_EMBEDDING = "embedding"
KIND_DECISION = "decision"

# caller tag -> the ``config/prompts/<stem>.md`` it is built from. Only callers
# with one template are listed; a caller absent here simply writes no
# ``template`` (sparse, never a guess). The relevance gate's callers all ask
# ``relevance_score4.md`` (ADR-0113). A test pins that every stem is a file.
CALLER_TEMPLATE: dict[str, str] = {
    "moltbook.comment": "comment",
    "moltbook.reply": "reply",
    "moltbook.cooperation_post": "cooperation_post",
    "moltbook.post_title": "post_title",
    "moltbook.internal_note": "internal_note",
    "moltbook.topic_summary": "topic_summary",
    "moltbook.select_submolt": "submolt_selection",
    "moltbook.verify_solve": "verification_solve_extract_system",
    "moltbook.relevance_shadow": "relevance_score4",
    "moltbook.relevance_seed": "relevance_score4",
    "moltbook.submolt_scope_score4": "relevance_score4",
    "core.skill_selection": "skill_selection",
    "distill.episode": "distill_episode",
    "distill.postgate": "distill_postgate",
    "distill.identity": "identity_distill",
    "constitution.amend": "constitution_amend",
    "insight.novelty": "insight_novelty",
    "insight.naming": "insight_naming",
    "insight.duplicate": "insight_duplicate",
    "insight.description": "insight_description",
    "insight.skill_extract": "insight_extraction",
    "stocktake.description_audit": "stocktake_description",
    "dialogue.peer": "dialogue",
}


def call_meta(kind: str, caller: str) -> dict[str, Any]:
    """The three identity columns for one row (``template`` only when known)."""
    meta: dict[str, Any] = {"kind": kind, "schema": LLM_CALLS_SCHEMA}
    template = CALLER_TEMPLATE.get(caller)
    if template is not None:
        meta["template"] = template
    return meta
