"""Interpret meditation results and store as learned patterns."""

from __future__ import annotations

import logging
from typing import Optional

from ...core.knowledge_store import KnowledgeStore
from ...core.llm import generate
from .config import ACTION_STATES, CONTEXT_STATES
from .meditate import MeditationResult

logger = logging.getLogger(__name__)


def format_meditation_summary(result: MeditationResult) -> str:
    """Format meditation result as structured text for LLM interpretation."""
    lines = [
        "## Meditation Session Summary",
        "",
        f"Cycles run: {result.cycles_run}",
        f"Convergence delta: {result.convergence_delta:.6f}",
        f"Total policies pruned: {result.pruned_policies}",
        "",
        "### Entropy",
        f"Initial: {result.entropy_initial:.4f}",
        f"Final: {result.entropy_final:.4f}",
        f"Change: {result.entropy_final - result.entropy_initial:+.4f}",
        "",
        "### Belief Distribution (context states)",
    ]

    for i, name in enumerate(CONTEXT_STATES):
        initial = result.initial_beliefs[i] if i < len(result.initial_beliefs) else 0
        final = result.final_beliefs[i] if i < len(result.final_beliefs) else 0
        change = final - initial
        lines.append(f"  {name}: {initial:.3f} → {final:.3f} ({change:+.3f})")

    lines.extend([
        "",
        "### Action Space",
        f"Actions: {', '.join(ACTION_STATES)}",
    ])

    return "\n".join(lines)


def interpret_and_store(
    result: MeditationResult,
    knowledge_store: KnowledgeStore,
    dry_run: bool = False,
    prompt_template: Optional[str] = None,
) -> str:
    """Use LLM to interpret belief changes, store as learned patterns.

    1. Format the MeditationResult into a structured summary
    2. Send to LLM with meditation_interpret prompt
    3. Parse LLM output as bullet-point patterns
    4. Write patterns to KnowledgeStore with source="meditation"

    Returns:
        Human-readable output string.
    """
    summary = format_meditation_summary(result)

    if result.cycles_run == 0:
        return f"{summary}\n\nNo meditation cycles run — nothing to interpret."

    # Load prompt template
    if prompt_template is None:
        try:
            from ...core import prompts
            prompt_template = prompts.MEDITATION_INTERPRET_PROMPT
        except (AttributeError, Exception):
            prompt_template = None

    if not prompt_template:
        # Fallback: return summary without LLM interpretation
        return f"{summary}\n\n(No meditation_interpret prompt template found — showing raw results.)"

    prompt = prompt_template.replace("{meditation_summary}", summary)
    llm_output = generate(prompt, max_length=1000)

    if not llm_output:
        return f"{summary}\n\n(LLM returned no output for interpretation.)"

    # Parse bullet points from LLM output
    patterns = []
    for line in llm_output.strip().splitlines():
        line = line.strip()
        if line.startswith("- "):
            patterns.append(line[2:].strip())

    output_lines = [summary, "", "### Meditation Insights"]

    if patterns:
        for p in patterns:
            output_lines.append(f"- {p}")

        if not dry_run:
            for p in patterns:
                knowledge_store.add_learned_pattern(
                    pattern=p, source="meditation",
                )
            knowledge_store.save()
            output_lines.append(f"\n({len(patterns)} patterns saved to knowledge store)")
        else:
            output_lines.append(f"\n(dry run — {len(patterns)} patterns not saved)")
    else:
        output_lines.append("(No actionable patterns extracted)")

    return "\n".join(output_lines)
