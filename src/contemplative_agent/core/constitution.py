"""Constitution amendment: feed constitutional experience back into ethical principles."""

from __future__ import annotations

import logging
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .llm import generate, get_distill_system_prompt, validate_identity_content
from .memory import KnowledgeStore
from .prompts import CONSTITUTION_AMEND_PROMPT

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3


def amend_constitution(
    knowledge_store: Optional[KnowledgeStore] = None,
    constitution_dir: Optional[Path] = None,
    dry_run: bool = False,
) -> str:
    """Propose amendments to the constitution based on accumulated constitutional patterns.

    Reads the current constitution and constitutional patterns from the knowledge store,
    then asks the LLM to propose an updated constitution that incorporates learned
    ethical insights while preserving the original structure.

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        constitution_dir: Directory containing contemplative-axioms.md.
        dry_run: If True, return proposed amendments without writing.

    Returns:
        The proposed (or written) amended constitution text.
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

    axioms_path = constitution_dir / "contemplative-axioms.md"
    if not axioms_path.exists():
        msg = f"No constitution file found at {axioms_path}"
        logger.warning(msg)
        return msg

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
        logger.warning("Generated constitution failed validation — not writing")
        return amended_text

    if dry_run:
        logger.info("Dry run — not writing constitution amendment")
        return amended_text

    axioms_path.write_text(amended_text + "\n", encoding="utf-8")
    os.chmod(axioms_path, stat.S_IRUSR | stat.S_IWUSR)
    logger.info("Constitution amended: %s", axioms_path)

    marker = constitution_dir / ".last_constitution_amend"
    marker.write_text(
        datetime.now(timezone.utc).isoformat(timespec="minutes") + "\n",
        encoding="utf-8",
    )

    return amended_text
