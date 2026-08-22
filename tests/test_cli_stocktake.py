"""skill-stocktake CLI tests (cli/stocktake_cmd.py) — the ADR-0097 reduced command.

What is pinned here:

- the handler reports, audits descriptions (advisory), and writes nothing to
  the store — no staging producer, no ``--stage`` flag, no merge / clean;
- the description audit reads each skill from disk and annotates findings
  with the usage count when a reading is attached;
- Tier 1.5 runtime routing (telemetry without the corpus) still holds;
- ``rules-stocktake`` is gone from the registry.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from contemplative_agent.cli import COMMANDS, main
from contemplative_agent.cli.stocktake_cmd import (
    _handle_skill_stocktake,
    _stocktake_description_phase,
)
from contemplative_agent.core.llm import GenerationOutput

SKILL = """\
---
name: a-skill
description: "Fires on narrow condition X"
origin: auto-extracted
---

# A Skill

**Context:** Testing context.

## Problem
Agents struggle with test scenarios and need a documented approach to them.

## Solution
Apply test-driven techniques consistently across every scenario encountered.

## When to Use
During test execution phases where coverage is insufficient or uneven.
"""


def _skills_dir(tmp_path: Path, names: tuple[str, ...] = ("a.md",)) -> Path:
    d = tmp_path / "skills"
    d.mkdir()
    for name in names:
        (d / name).write_text(SKILL, encoding="utf-8")
    return d


def _items(*names: str, raw: str = SKILL) -> list[tuple[str, str, str]]:
    """``StocktakeResult.items`` shape: (filename, raw, frontmatter-stripped body)."""
    from contemplative_agent.core.text_utils import strip_frontmatter

    return [(name, raw, strip_frontmatter(raw).strip()) for name in names]


class TestRegistry:
    def test_rules_stocktake_is_retired(self):
        names = {spec.name for spec in COMMANDS}
        assert "skill-stocktake" in names
        assert "rules-stocktake" not in names
        assert "rules-distill" not in names

    def test_skill_stocktake_has_no_stage_flag(self):
        spec = next(s for s in COMMANDS if s.name == "skill-stocktake")
        parser = argparse.ArgumentParser(prog=spec.name, add_help=False)
        spec.add_arguments(parser)
        options = {opt for action in parser._actions for opt in action.option_strings}
        assert "--stage" not in options


class TestHandler:
    def _run(self, tmp_path, *, desc_prompt="audit {name} {description} {skill}"):
        skills_dir = _skills_dir(tmp_path, ("a.md", "b.md"))
        staged_dir = tmp_path / ".staged"
        with (
            patch("contemplative_agent.adapters.moltbook.config.SKILLS_DIR", skills_dir),
            patch("contemplative_agent.adapters.moltbook.config.STAGED_DIR", staged_dir),
            patch("contemplative_agent.adapters.moltbook.config.MOLTBOOK_DATA_DIR", tmp_path),
            patch(
                "contemplative_agent.cli.stocktake_cmd._load_selection_reading", return_value=None
            ),
            patch("contemplative_agent.cli.memory_cmds._take_snapshot", return_value=tmp_path),
            patch(
                "contemplative_agent.core.prompts.STOCKTAKE_DESC_PROMPT",
                desc_prompt,
                create=True,
            ),
            patch(
                "contemplative_agent.core.stocktake.generate_full",
                # Distinct traces per call: _write_reasoning de-duplicates
                # identical traces, which would fold two skills into one section.
                side_effect=lambda *_a, **_k: GenerationOutput(
                    text="broader than the body", thinking=f"because-{len(gen.mock_calls)}"
                ),
            ) as gen,
        ):
            _handle_skill_stocktake(argparse.Namespace(), MagicMock())
        return skills_dir, staged_dir, gen

    def test_reports_and_audits_without_touching_the_store(self, tmp_path, capsys):
        skills_dir, staged_dir, gen = self._run(tmp_path)
        out = capsys.readouterr().out
        assert "Skill Stocktake Report" in out
        assert "Description audit: 2 mismatch(es), advisory only" in out
        # One LLM call per skill — the audit — and nothing else.
        assert gen.call_count == 2
        # Nothing written, nothing staged.
        assert (skills_dir / "a.md").read_text(encoding="utf-8") == SKILL
        assert not staged_dir.exists()

    def test_reasoning_md_carries_one_section_per_audited_skill(self, tmp_path):
        self._run(tmp_path)
        content = (tmp_path / "reasoning.md").read_text(encoding="utf-8")
        assert "## description a.md" in content
        assert "## description b.md" in content

    def test_empty_description_prompt_abstains_instead_of_fabricating(self, tmp_path, capsys):
        """A missing template loads as "" (domain.py required=False); an empty
        prompt must skip the audit, not report every skill as a mismatch."""
        _, _, gen = self._run(tmp_path, desc_prompt="")
        assert gen.call_count == 0
        assert "Description audit" not in capsys.readouterr().out


class TestDescriptionPhase:
    def test_annotates_findings_with_usage_count(self, capsys):
        with patch(
            "contemplative_agent.core.stocktake.generate_full",
            return_value=GenerationOutput(text="narrower than the body"),
        ):
            _stocktake_description_phase(
                _items("a.md"),
                desc_prompt="audit {name} {description} {skill}",
                usage_counts={"a-skill": 17},
            )
        out = capsys.readouterr().out
        assert "a.md [selected 17x in window] — narrower than the body" in out

    def test_missing_description_is_a_finding_without_an_llm_call(self, capsys):
        # Frontmatter present but no description, and no title to fall back on.
        bare = "---\nname: bare\n---\n\n## Problem\nx\n\n## Solution\ny\n"
        with patch("contemplative_agent.core.stocktake.generate_full") as gen:
            _stocktake_description_phase(
                _items("bare.md", raw=bare),
                desc_prompt="audit {name} {description} {skill}",
            )
        assert gen.call_count == 0
        assert "no description in frontmatter" in capsys.readouterr().out

    def test_reasoning_sections_name_the_skill_that_produced_each_trace(self):
        """The trace travels on the result, so a skill whose audit returned no
        trace cannot shift a later skill's trace onto the wrong label."""
        outputs = iter(
            [
                GenerationOutput(text="DESC_OK", thinking=None),  # a.md: no trace
                GenerationOutput(text="off-topic", thinking="trace-b"),  # b.md
            ]
        )
        with patch(
            "contemplative_agent.core.stocktake.generate_full",
            side_effect=lambda *_a, **_k: next(outputs),
        ):
            sections = _stocktake_description_phase(
                _items("a.md", "b.md"),
                desc_prompt="audit {name} {description} {skill}",
            )
        assert sections == [("description b.md", "trace-b")]


class TestStocktakeRuntimeRouting:
    """M1 (review 2026-06-27): stocktake routes through the Tier 1.5 runtime
    path that applies telemetry WITHOUT loading the skills/rules/axioms corpus
    (it passes its own system prompt)."""

    @patch("contemplative_agent.cli.stocktake_cmd._handle_skill_stocktake")
    @patch("contemplative_agent.cli.runtime.configure_llm")
    def test_skill_stocktake_applies_telemetry(self, mock_configure, mock_handler):
        with patch("sys.argv", ["contemplative-agent", "skill-stocktake"]):
            main()
        mock_handler.assert_called_once()
        kwargs_list = [c.kwargs for c in mock_configure.call_args_list]
        assert any("telemetry_dir" in kw for kw in kwargs_list)
        assert not any("skills_dir" in kw for kw in kwargs_list)
        assert not any("rules_dir" in kw for kw in kwargs_list)
        assert not any("axiom_prompt" in kw for kw in kwargs_list)
