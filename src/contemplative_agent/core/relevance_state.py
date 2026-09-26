"""The relevance judgment as a 4-level Score: its state and its question (RFC-0046).

One owner for the two things the RFC-0045 replay measured (arm
``C/logits/score4``: AUC 0.944 against Jev's on-topic label on the 150-row
dev set) and the production shadow now asks, so the shadow cannot drift from
the arm whose number justified it:

* the **state** — ``{"domain": <domain text>, "post": <untrusted frame>}``
  rendered as indented JSON, the exact prompt prefix arm C sent;
* the **question** — instructions plus four ordered levels, read from
  ``config/prompts/relevance_score4.md`` (ADR-0054: LLM-read text lives in
  ``config/prompts/``).

``scripts/relevance_arm_replay.py`` imports this module for both, and
``adapters/moltbook/relevance_shadow.py`` asks the question in production.
Nothing here calls a model or writes anything.

**Whose domain** (RFC-0046, owner decision 2026-09-26): "my domain" is
identity + axioms — :func:`production_domain_text`, the body of the system
prompt production's mechanical calls run under. The RFC-0045 arm C (and J)
read identity.md alone; that definition stays reproducible under the name
:data:`DOMAIN_SOURCE_IDENTITY` (the replay's ``read_domain``). The ladder's
Cx arm is this definition read the arm C way.
"""

from __future__ import annotations

import json

from .llm import ScoreQuestion, get_identity_system_prompt, wrap_untrusted_content

# The id the question carries in a DecisionResult. It never reaches the
# prompt (the backend renders instructions and levels only).
QUESTION_ID = "relevance"
LEVEL_COUNT = 4
# The level whose probability is the would-be gate's score: "directly
# on-topic". Level order is lowest first, so it is the last.
TOP_LEVEL = LEVEL_COUNT - 1
# arm C's frame: the logged feed preview is 500 characters, and production's
# live relevance prompt wraps the same text at max_input=1000.
POST_MAX_INPUT = 1000

_LEVEL_MARK = "- "

# What a state's ``domain`` holds. Written into every shadow row
# (``domain_source``) and every label-set manifest, so a reading never pools
# the two; a row without the field predates the switch and is identity.
DOMAIN_SOURCE_PRODUCTION = "identity+axioms"
DOMAIN_SOURCE_IDENTITY = "identity"
DOMAIN_SOURCES: tuple[str, ...] = (DOMAIN_SOURCE_PRODUCTION, DOMAIN_SOURCE_IDENTITY)


def production_domain_text() -> str:
    """The domain as production defines it: identity + ``"\\n\\n---\\n\\n"`` + axioms.

    The same function the mechanical calls' system prompt comes from
    (``prompting._identity_axioms_base``), so the two cannot disagree: the
    identity validation and its default fallback are production's, and with no
    axioms configured the domain is identity alone, exactly as the prompt is.
    """
    return get_identity_system_prompt()


def parse_score4_prompt(text: str) -> tuple[str, tuple[str, ...]]:
    """``(instructions, levels)`` from the prompt file's text.

    Lines starting ``- `` are the levels, lowest first; every other non-blank
    line is the instructions, joined by a space. Raises ValueError unless there
    are instructions and exactly :data:`LEVEL_COUNT` levels — a rubric with a
    different number of levels would shift which probability is "on-topic".
    """
    levels: list[str] = []
    prose: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(_LEVEL_MARK):
            levels.append(line[len(_LEVEL_MARK) :].strip())
        else:
            prose.append(line)
    if not prose:
        raise ValueError("relevance_score4 prompt has no instructions")
    if len(levels) != LEVEL_COUNT:
        raise ValueError(
            f"relevance_score4 prompt has {len(levels)} level(s), expected {LEVEL_COUNT}"
        )
    return " ".join(prose), tuple(levels)


def score4_question(text: str | None = None) -> ScoreQuestion:
    """The 4-level question. *text* defaults to the loaded prompt template.

    The default goes through ``core.prompts`` so a ``$MOLTBOOK_HOME/prompts/``
    override applies the same way it does to every other prompt.
    """
    if text is None:
        from . import prompts

        text = prompts.RELEVANCE_SCORE4_PROMPT
    instructions, levels = parse_score4_prompt(text)
    return ScoreQuestion(id=QUESTION_ID, instructions=instructions, levels=levels)


def packaged_score4_prompt() -> str:
    """The packaged ``relevance_score4.md``, bypassing any home override.

    For the offline replay, whose numbers must not depend on which
    ``$MOLTBOOK_HOME`` the operator happened to point at.
    """
    from .domain import DEFAULT_PROMPTS_DIR

    return (DEFAULT_PROMPTS_DIR / "relevance_score4.md").read_text(encoding="utf-8")


def build_state(domain: str, post_text: str) -> dict[str, str]:
    """``{domain, post}`` — the post inside production's untrusted frame."""
    return {"domain": domain, "post": wrap_untrusted_content(post_text, max_input=POST_MAX_INPUT)}


def state_text(state: dict[str, str]) -> str:
    """The state as the prompt prefix a decision backend receives."""
    return json.dumps(state, ensure_ascii=False, indent=2)
