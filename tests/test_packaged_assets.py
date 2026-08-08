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

from contemplative_agent.core.domain import PromptTemplates, load_prompt_templates
from contemplative_agent.core.view_metrics import CONSUMED_VIEWS


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("repo root (pyproject.toml) not found above this file")


REPO_ROOT = _repo_root()

# Prompt documents consumed by scripts rather than the PromptTemplates
# registry. A stem listed here must name its consumer:
# - principles / weekly-analysis / weekly-analysis-ja → scripts/weekly-analysis.sh
# - fix-implementation / fix-review / insight-recommendation /
#   pipeline-improvement → scripts/weekly-pipeline.sh (ADR-0085)
SCRIPT_READ_PROMPTS = {
    "principles",
    "weekly-analysis",
    "weekly-analysis-ja",
    "fix-implementation",
    "fix-review",
    "insight-recommendation",
    "pipeline-improvement",
}


def _prompt_stems() -> set[str]:
    prompts_dir = REPO_ROOT / "config" / "prompts"
    assert prompts_dir.is_dir(), f"expected packaged prompts at {prompts_dir}"
    return {p.stem for p in prompts_dir.glob("*.md")}


class TestPackagedPrompts:
    def test_each_field_loads_the_file_named_after_it(self):
        """``load_prompt_templates`` maps fields to files with 38 hand-written
        ``read("<name>.md")`` calls; nothing asserted the argument matched the
        field name until now.

        ``evals/run_eval.hashed_prompt_paths`` decides what the eval hashes
        from the field names alone, so it inherits this assumption. Break it —
        ``comment=read("comment-v2.md")`` while ``comment.md`` still exists —
        and the digest hashes a file the loader ignores while missing the one
        it reads. That is the *wrong-file* direction, strictly worse than the
        detection-miss that function's docstring documents, and no guard
        caught it (python review, 2026-08-08).
        """
        import tempfile

        fields = [f.name for f in dataclasses.fields(PromptTemplates)]
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            for name in fields:
                (d / f"{name}.md").write_text(f"MARK-{name}", encoding="utf-8")
            loaded = load_prompt_templates(d)
        mismatched = {
            name: getattr(loaded, name)
            for name in fields
            if getattr(loaded, name) != f"MARK-{name}"
        }
        assert not mismatched, (
            f"fields not loading <field>.md: {sorted(mismatched)}. "
            "evals/run_eval.hashed_prompt_paths derives the eval's hash input "
            "from field names and would hash the wrong file."
        )

    def test_every_script_read_prompt_has_a_real_script_consumer(self):
        """``SCRIPT_READ_PROMPTS`` says a stem "must name its consumer", which
        was prose. Adding a stem is a one-line way to silence the orphan guard
        below — and since 2026-08-08 that guard is what the eval's allowlist
        leans on to be safe, so the set became load-bearing without gaining a
        check (python review, 2026-08-08)."""
        scripts = "\n".join(
            p.read_text(encoding="utf-8") for p in sorted((REPO_ROOT / "scripts").glob("*.sh"))
        )
        unreferenced = sorted(s for s in SCRIPT_READ_PROMPTS if f"{s}.md" not in scripts)
        assert not unreferenced, (
            f"stems claim a script consumer but no scripts/*.sh names them: {unreferenced}. "
            "Either wire a PromptTemplates field or delete the file — do not park "
            "generation-path templates here; the eval digest excludes this set."
        )

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
        assert not missing, f"PromptTemplates fields without a packaged default: {sorted(missing)}"


class TestDocClaims:
    def test_configuration_canonical_counts_match_reality(self):
        """docs/CONFIGURATION.md#pipeline-prompts--view-seeds is the single
        place that states prompt counts (README / llms.txt / CODEMAPS point
        here instead of repeating numbers); this pins that one claim."""
        text = (REPO_ROOT / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8")
        match = re.search(
            r"(\d+)\s+loaded\s+prompt\s+templates\s+plus\s+(\d+)\s+"
            r"script-read\s+prompt\s+documents",
            text,
        )
        assert match, "canonical inventory sentence not found in docs/CONFIGURATION.md"
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
