"""Constitution amendment: feed constitutional experience back into ethical principles.

ADR-0026 (Phase 2): constitutional pattern selection moved from the
pattern-level ``category`` field to query-time view routing. The caller
supplies a ``ViewRegistry`` and we retrieve patterns via
``find_by_view("constitutional", ...)``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional, Tuple, Union

from .knowledge_store import epistemic_counts_for, pattern_id
from .llm import generate_full, get_distill_system_prompt, validate_identity_content
from .memory import KnowledgeStore
from .prompts import CONSTITUTION_AMEND_PROMPT
from .views import ViewRegistry

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3


@dataclass(frozen=True)
class AmendmentResult:
    """Result of a successful constitution amendment generation.

    ADR-0050: ``pattern_ids`` carries the content-hash ids of the
    view-matched input patterns; ``epistemic_counts`` their
    observed/generated tally.
    """

    text: str
    target_path: Path
    marker_dir: Path
    pattern_ids: Tuple[str, ...] = ()
    epistemic_counts: Dict[str, int] = field(default_factory=dict)
    # ADR-0069: reasoning trace behind the amendment (amend-constitution runs
    # think-ON — the constitution sits at the top of the behavior-change chain,
    # so the owner sees *why* this amendment was proposed at the approval gate).
    thinking: Optional[str] = None


def amend_constitution(
    knowledge_store: Optional[KnowledgeStore] = None,
    constitution_dir: Optional[Path] = None,
    view_registry: Optional[ViewRegistry] = None,
) -> Union[str, AmendmentResult]:
    """Generate a constitution amendment from accumulated constitutional patterns.

    Reads the current constitution and constitutional patterns from the knowledge store,
    then asks the LLM to propose an updated constitution that incorporates learned
    ethical insights while preserving the original structure.

    File writing is the caller's responsibility (ADR-0012 approval gate).

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        constitution_dir: Directory containing constitution .md files.
        view_registry: ViewRegistry used to retrieve constitutional
            patterns via embedding cosine (ADR-0026). Required since
            Phase 2 — the legacy ``category="constitutional"`` row
            filter has been retired.

    Returns:
        AmendmentResult on success, or error message string.
    """
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if view_registry is None:
        msg = (
            "amend_constitution requires a ViewRegistry since ADR-0026. "
            "Pass a ViewRegistry instance so constitutional patterns can be "
            "retrieved via view cosine."
        )
        logger.warning(msg)
        return msg

    # ADR-0026 Phase 2: constitutional patterns are retrieved via the
    # "constitutional" view's embedding cosine rather than a persisted
    # category label. Patterns lacking embeddings are silently skipped.
    matched = view_registry.find_by_view("constitutional", knowledge.get_live_patterns())
    if len(matched) < MIN_PATTERNS_REQUIRED:
        msg = (
            f"Insufficient constitutional patterns ({len(matched)}/{MIN_PATTERNS_REQUIRED}). "
            f"More ethical experience needed before amendment."
        )
        logger.info(msg)
        return msg

    constitutional_text = "\n".join(f"- {p['pattern']}" for p in matched)

    if not CONSTITUTION_AMEND_PROMPT:
        msg = "constitution_amend.md prompt template not found."
        logger.warning(msg)
        return msg

    if constitution_dir is None:
        msg = "No constitution directory configured."
        logger.warning(msg)
        return msg

    axiom_files = sorted(constitution_dir.glob("*.md"))
    if not axiom_files:
        msg = f"No constitution files found in {constitution_dir}"
        logger.warning(msg)
        return msg

    # Use the first (or only) .md file as the constitution source
    axioms_path = axiom_files[0]
    current_constitution = axioms_path.read_text(encoding="utf-8").strip()
    if not current_constitution:
        msg = "Constitution file is empty."
        logger.warning(msg)
        return msg

    prompt = CONSTITUTION_AMEND_PROMPT.format(
        current_constitution=current_constitution,
        constitutional_patterns=constitutional_text,
    )

    out = generate_full(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        caller="constitution.amend",
        think=True,
    )
    if out is None or out.text is None:
        msg = "LLM failed to generate constitution amendment."
        logger.warning(msg)
        return msg

    amended_text = out.text.strip()

    if not validate_identity_content(amended_text):
        logger.warning("Generated constitution failed validation")
        return amended_text

    return AmendmentResult(
        text=amended_text,
        target_path=axioms_path,
        marker_dir=constitution_dir,
        pattern_ids=tuple(pattern_id(p) for p in matched),
        epistemic_counts=epistemic_counts_for(matched),
        thinking=out.thinking,
    )
