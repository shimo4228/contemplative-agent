"""Interpret meditation results and save to config/meditation/."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ...core._io import write_restricted
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


def _save_result(result: MeditationResult, results_path: Path) -> None:
    """Append meditation result to results.json."""
    results_path.parent.mkdir(parents=True, exist_ok=True)

    existing: List[dict] = []
    if results_path.exists():
        try:
            existing = json.loads(results_path.read_text(encoding="utf-8"))
            if not isinstance(existing, list):
                existing = []
        except (json.JSONDecodeError, OSError):
            existing = []

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **asdict(result),
    }
    existing.append(entry)

    content = json.dumps(existing, ensure_ascii=False, indent=2) + "\n"
    tmp_path = results_path.with_suffix(".json.tmp")
    try:
        write_restricted(tmp_path, content)
        os.replace(str(tmp_path), str(results_path))
    except OSError as exc:
        logger.error("Failed to save meditation results: %s", exc)
        tmp_path.unlink(missing_ok=True)
        raise


def interpret_and_save(
    result: MeditationResult,
    results_path: Path,
    dry_run: bool = False,
    prompt_template: Optional[str] = None,
) -> str:
    """Interpret meditation results via LLM and save raw data to results.json.

    LLM interpretation is for human-readable output only.
    Only the raw MeditationResult is persisted (no LLM text).

    Returns:
        Human-readable output string.
    """
    summary = format_meditation_summary(result)

    if result.cycles_run == 0:
        return f"{summary}\n\nNo meditation cycles run — nothing to interpret."

    # Save raw result (not LLM interpretation)
    if not dry_run:
        _save_result(result, results_path)
        logger.info("Meditation result saved to %s", results_path)

    # Load prompt template for human-readable interpretation
    if prompt_template is None:
        try:
            from ...core import prompts
            prompt_template = prompts.MEDITATION_INTERPRET_PROMPT
        except (AttributeError, Exception):
            prompt_template = None

    if not prompt_template:
        save_msg = f"(Result saved to {results_path})" if not dry_run else "(dry run)"
        return f"{summary}\n\n{save_msg}"

    prompt = prompt_template.replace("{meditation_summary}", summary)
    llm_output = generate(prompt, max_length=1000)

    if not llm_output:
        save_msg = f"(Result saved to {results_path})" if not dry_run else "(dry run)"
        return f"{summary}\n\n(LLM returned no output for interpretation.)\n{save_msg}"

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
    else:
        output_lines.append("(No actionable patterns extracted)")

    if not dry_run:
        output_lines.append(f"\n(Result saved to {results_path})")
    else:
        output_lines.append("\n(dry run — result not saved)")

    return "\n".join(output_lines)
