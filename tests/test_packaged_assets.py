"""Orphan guards for packaged data assets (ADR-0073).

Dead-code tools only analyze code: a data file loaded by glob or registry has
no static import edge, so when its last consumer is retired in Python the file
dies without changing a byte — the five orphaned view seeds sat
loaded-but-unqueried for two months this way. These tests close the silent
direction (file without consumer). The opposite direction (registry field
without packaged file) is covered by
``test_every_registry_field_has_a_packaged_default`` — at runtime a missing
file raises only for the required fields; optional fields degrade to ``""``.
"""

import dataclasses
import re
from pathlib import Path

from contemplative_agent.core.domain import PromptTemplates
from contemplative_agent.core.view_metrics import CONSUMED_VIEWS


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("repo root (pyproject.toml) not found above this file")


REPO_ROOT = _repo_root()

# Prompt documents consumed by scripts/weekly-analysis.sh rather than the
# PromptTemplates registry. A stem listed here must name its consumer.
SCRIPT_READ_PROMPTS = {"principles", "weekly-analysis", "weekly-analysis-ja"}


def _prompt_stems() -> set[str]:
    prompts_dir = REPO_ROOT / "config" / "prompts"
    assert prompts_dir.is_dir(), f"expected packaged prompts at {prompts_dir}"
    return {p.stem for p in prompts_dir.glob("*.md")}


class TestPackagedPrompts:
    def test_every_prompt_file_is_consumed(self):
        fields = {f.name for f in dataclasses.fields(PromptTemplates)}
        orphans = _prompt_stems() - fields - SCRIPT_READ_PROMPTS
        assert not orphans, (
            f"Prompt files without a consumer: {sorted(orphans)}. "
            "Either wire a PromptTemplates field, add the stem to "
            "SCRIPT_READ_PROMPTS naming its consumer, or delete the file."
        )

    def test_every_registry_field_has_a_packaged_default(self):
        fields = {f.name for f in dataclasses.fields(PromptTemplates)}
        missing = fields - _prompt_stems()
        assert not missing, (
            f"PromptTemplates fields without a packaged default: "
            f"{sorted(missing)}"
        )


class TestDocClaims:
    def test_configuration_canonical_counts_match_reality(self):
        """docs/CONFIGURATION.md#pipeline-prompts--view-seeds is the single
        place that states prompt counts (README / llms.txt / CODEMAPS point
        here instead of repeating numbers); this pins that one claim."""
        text = (REPO_ROOT / "docs" / "CONFIGURATION.md").read_text(
            encoding="utf-8"
        )
        match = re.search(
            r"(\d+)\s+loaded\s+prompt\s+templates\s+plus\s+(\d+)\s+"
            r"script-read\s+prompt\s+documents",
            text,
        )
        assert match, (
            "canonical inventory sentence not found in docs/CONFIGURATION.md"
        )
        assert int(match.group(1)) == len(dataclasses.fields(PromptTemplates))
        assert int(match.group(2)) == len(SCRIPT_READ_PROMPTS)


class TestPackagedViewSeeds:
    def test_shipped_views_are_exactly_the_consumed_set(self):
        views_dir = REPO_ROOT / "config" / "views"
        assert views_dir.is_dir(), f"expected packaged views at {views_dir}"
        shipped = {p.stem for p in views_dir.glob("*.md")}
        consumed = set(CONSUMED_VIEWS)
        assert shipped == consumed, (
            "config/views/ must ship exactly the consumed views "
            "(ADR-0073: a view lands together with its consumer wiring). "
            f"Unexpected: {sorted(shipped - consumed)}, "
            f"missing: {sorted(consumed - shipped)}. "
            "New views update view_metrics.CONSUMED_VIEWS in the same change."
        )
