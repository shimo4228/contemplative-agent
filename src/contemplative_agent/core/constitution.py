"""Constitution amendment: feed constitutional experience back into ethical principles."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from .llm import generate, get_distill_system_prompt, validate_identity_content
from .memory import KnowledgeStore
from .prompts import CONSTITUTION_AMEND_PROMPT

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3


@dataclass(frozen=True)
class AmendmentResult:
    """Result of a successful constitution amendment generation."""

    text: str
    target_path: Path
    marker_dir: Path


def amend_constitution(
    knowledge_store: Optional[KnowledgeStore] = None,
    constitution_dir: Optional[Path] = None,
) -> Union[str, AmendmentResult]:
    """Generate a constitution amendment from accumulated constitutional patterns.

    Reads the current constitution and constitutional patterns from the knowledge store,
    then asks the LLM to propose an updated constitution that incorporates learned
    ethical insights while preserving the original structure.

    File writing is the caller's responsibility (ADR-0012 approval gate).

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        constitution_dir: Directory containing constitution .md files.

    Returns:
        AmendmentResult on success, or error message string.
    """
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    constitutional_patterns = knowledge.get_learned_patterns(category="constitutional")
    if len(constitutional_patterns) < MIN_PATTERNS_REQUIRED:
        msg = (
            f"Insufficient constitutional patterns ({len(constitutional_patterns)}/{MIN_PATTERNS_REQUIRED}). "
            f"More ethical experience needed before amendment."
        )
        logger.info(msg)
        return msg

    constitutional_text = knowledge.get_context_string(category="constitutional")

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

    result = generate(prompt, system=get_distill_system_prompt(), max_length=4000)
    if result is None:
        msg = "LLM failed to generate constitution amendment."
        logger.warning(msg)
        return msg

    amended_text = result.strip()

    if not validate_identity_content(amended_text):
        logger.warning("Generated constitution failed validation")
        return amended_text

    return AmendmentResult(
        text=amended_text,
        target_path=axioms_path,
        marker_dir=constitution_dir,
    )
