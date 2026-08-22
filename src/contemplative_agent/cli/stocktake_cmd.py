"""skill-stocktake: structural quality report, usage reading, description audit.

ADR-0097 reduced this command to the three things that survived the
consolidator dissolution. It writes nothing to the store and stages nothing:
the structural check and the usage reading are code-owned readings, and the
ADR-0081 description audit is advisory. Retirement and consolidation happen at
the Saturday gate, not here — today through ``remove-skill``; the archive exit
(``adopt-staged --archive-names``) and the packet's never-selected and
co-selection readings are reserved for ADR-0097 slice 2 and do not exist yet.

``rules-stocktake`` was retired in the same decision; the rules layer keeps a
deterministic structural check (``core.stocktake.run_rules_quality_check``),
whose consumer — a rules section in the weekly packet — is reserved for
ADR-0097 slice 2.
"""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from pathlib import Path

from ..adapters.moltbook import config
from . import memory_cmds
from .registry import CommandSpec, Tier

logger = logging.getLogger(__name__)


def _stocktake_description_phase(
    items: Sequence[tuple[str, str, str]],
    *,
    desc_prompt: str,
    usage_counts: dict[str, int] | None = None,
) -> list[tuple[str, str | None]]:
    """Audit description fidelity for every skill (ADR-0081, advisory).

    Under two-pass injection the frontmatter description is the selector's
    only evidence, so a description broader or narrower than the body's
    triggers distorts every selection. This phase prints mismatch reasons
    for the operator — it writes nothing and gates nothing. ``usage_counts``
    (skill name → window selection count) annotates each finding so
    near-always-selected skills — the over-broad suspects — are visible next
    to the verdict.

    ``items`` is ``StocktakeResult.items``: the same ``(filename, raw, body)``
    the quality check read, so the audit judges those bytes rather than
    re-reading each file under a second read policy.

    Returns the ADR-0069 reasoning sections ``(label, trace)`` for
    ``reasoning.md``, one per skill whose audit produced a trace.
    """
    from ..core.stocktake import audit_skill_description
    from ..core.text_utils import skill_theme

    if not items:
        return []

    print(f"\n{'=' * 60}")
    print(f"Auditing descriptions for {len(items)} skill(s)...")

    sections: list[tuple[str, str | None]] = []
    findings = 0
    for name, raw, body in items:
        skill_name, description = skill_theme(raw, fallback_name=Path(name).stem)
        if not description:
            print(f"  {name} — no description in frontmatter (selector sees title only)")
            findings += 1
            continue

        reason, thinking = audit_skill_description((name, description, body), desc_prompt)
        if thinking:
            sections.append((f"description {name}", thinking))
        if reason is None:
            continue
        findings += 1
        suffix = ""
        if usage_counts is not None:
            suffix = f" [selected {usage_counts.get(skill_name, 0)}x in window]"
        print(f"  {name}{suffix} — {reason}")

    print(f"--- Description audit: {findings} mismatch(es), advisory only ---")
    return sections


# ADR-0081 usage window: matches the 2-week shadow-reading cadence the
# enforcement decision was made on (2026-07-24 first reading).
_USAGE_WINDOW_DAYS = 14


def _load_selection_reading():
    """Read the ADR-0081 usage dimension for the skill stocktake report.

    The instrument is optional (audit_dir unset disables it; the log dir may
    simply not exist), so any failure degrades to None — the stocktake runs
    exactly as before, just without the usage section. Never fatal.
    """
    from ..core.skill_selection import read_skill_selection_log

    try:
        reading = read_skill_selection_log(
            config.EPISODE_LOG_DIR,
            days=_USAGE_WINDOW_DAYS,
            skills_dir=config.SKILLS_DIR,
        )
    except Exception as exc:  # noqa: BLE001 — advisory reading, never fatal
        logger.warning("skill-selection usage reading unavailable: %s", exc)
        return None
    if reading.records == 0:
        # Fresh install or kill-switched instrument: an empty log window is
        # "no observation", not "every skill went unselected" — attaching it
        # would render a spurious all-never-selected section and annotate
        # findings as 0x (codex review 2026-07-24).
        return None
    return reading


def _handle_skill_stocktake(args: argparse.Namespace, _parser: argparse.ArgumentParser) -> None:
    """Report structural quality + usage, then audit descriptions (advisory)."""
    from ..core import prompts
    from ..core.stocktake import format_stocktake_report, run_skill_stocktake

    snapshot_path = memory_cmds._take_snapshot(args, "skill-stocktake", think=True)
    result = run_skill_stocktake(
        skills_dir=config.SKILLS_DIR,
        selection_reading=_load_selection_reading(),
    )
    print(format_stocktake_report(result, "Skill"))

    # Truthiness, not `is not None`: a missing template file loads as ""
    # (domain.py required=False), and an empty prompt would fabricate
    # mismatch findings for every skill instead of abstaining
    # (python-reviewer 2026-07-24 MEDIUM).
    sections: list[tuple[str, str | None]] = []
    if prompts.STOCKTAKE_DESC_PROMPT:
        usage_counts = (
            dict(result.selection_usage.per_skill) if result.selection_usage is not None else None
        )
        sections = _stocktake_description_phase(
            result.items,
            desc_prompt=prompts.STOCKTAKE_DESC_PROMPT,
            usage_counts=usage_counts,
        )

    # ADR-0069: persist the run's reasoning (one description-audit trace per
    # skill) to reasoning.md so the snapshot alone explains the findings.
    memory_cmds._write_reasoning(snapshot_path, sections)


# Tier 1.5: telemetry without the skills/rules/axioms corpus. Stocktake passes
# its own explicit system prompt, so loading the corpus would pollute its
# prompt environment (review 2026-06-27 M1) — but running with no telemetry at
# all, as the old no-LLM slot did, hid its generation behaviour entirely.
COMMANDS: tuple[CommandSpec, ...] = (
    CommandSpec(
        name="skill-stocktake",
        help="Report skill quality and usage; audit descriptions (advisory)",
        handler=_handle_skill_stocktake,
        tier=Tier.LLM_RUNTIME_ONLY,
    ),
)
