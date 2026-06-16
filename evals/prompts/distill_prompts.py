"""promptfoo prompt functions for the distill pipeline.

Renders prompts through the SAME production code paths as
``contemplative_agent.core.distill``:

- templates load via ``core.prompts`` (lazy loader over ``config/prompts/``)
- episode lines format via ``distill.summarize_record`` + the
  ``[ts[:16]] type: summary`` line layout (distill.py)
- the system prompt assembles via ``core.llm.get_distill_system_prompt()``
  after ``configure(axiom_prompt=...)`` — identical to what cli.py does

So there is no template duplication and no drift: a change to
``config/prompts/*.md`` or to the system-prompt assembly is exercised here
automatically. The ``str.format()`` rendering also happens in Python, which
sidesteps the nunjucks ``{{ }}`` conflict (the templates contain literal
``{{...}}`` JSON examples that promptfoo must never re-render).

Run with ``MOLTBOOK_HOME`` unset so runtime prompt overrides cannot leak in
(see evals/README.md).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from contemplative_agent.core.distill import summarize_record  # noqa: E402
from contemplative_agent.core.domain import load_constitution  # noqa: E402
from contemplative_agent.core.llm import (  # noqa: E402
    configure,
    get_distill_system_prompt,
    reset_llm_config,
)
from contemplative_agent.core.prompts import (  # noqa: E402
    DISTILL_PROMPT,
    DISTILL_REFINE_PROMPT,
)

_AXIOMS_DIR = REPO / "config" / "templates" / "contemplative" / "constitution"
_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _system(with_axioms: bool) -> str:
    """Production system prompt: system.md (+ axioms when enabled)."""
    reset_llm_config()
    if with_axioms:
        clauses = load_constitution(_AXIOMS_DIR)
        if clauses:
            configure(axiom_prompt=clauses)
    return get_distill_system_prompt()


def _episode_lines(fixture_name: str) -> str:
    """Same episode-line layout as distill.py builds for {episodes}."""
    lines = []
    for raw in (_FIXTURES / fixture_name).read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        record = json.loads(raw)
        record_type = record.get("type", "unknown")
        summary = summarize_record(record_type, record.get("data", {}))
        if summary:
            lines.append(f"[{record.get('ts', '')[:16]}] {record_type}: {summary}")
    return "\n".join(lines)


def _chat(system: str, user: str) -> str:
    return json.dumps(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )


def distill_step1(context: dict) -> str:
    """Step 1 (extract): free-form observation prose, axioms as lens."""
    episodes = _episode_lines(context["vars"]["episode_file"])
    return _chat(_system(True), DISTILL_PROMPT.format(episodes=episodes))


def distill_step1_no_axioms(context: dict) -> str:
    """Step 1 without axioms — the §C1 ablation arm."""
    episodes = _episode_lines(context["vars"]["episode_file"])
    return _chat(_system(False), DISTILL_PROMPT.format(episodes=episodes))


def distill_refine(context: dict) -> str:
    """Step 2 (refine): step-1 prose -> {"patterns": [...]} JSON."""
    raw_output = (
        (_FIXTURES / context["vars"]["raw_output_file"])
        .read_text(encoding="utf-8")
        .strip()
    )
    return _chat(_system(True), DISTILL_REFINE_PROMPT.format(raw_output=raw_output))
