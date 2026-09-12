"""System-prompt assembly for the LLM seam: identity/axiom layering, learned
skills/rules corpus injection, identity validation, token estimation, and the
system-prompt budget instrument.

Sole owner of the prompt-side configuration: the five prompt inputs live in a
frozen :class:`PromptConfig`, of which ``_config`` is the process default, plus
the read caches (``_MD_CACHE``, ``_IDENTITY_CACHE``). The package facade
(``core.llm``) delegates here from ``configure()`` / ``reset_llm_config()`` and
re-exports functions only, never ``_config`` — a second copy of the state would
silently diverge. Every builder also accepts an explicit ``config``, so a caller
that wants a different composition (the budget instrument) passes one instead of
mutating the process default.
"""

from __future__ import annotations

import logging
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from ..config import FORBIDDEN_SUBSTRING_PATTERNS, FORBIDDEN_WORD_PATTERNS
from ..text_utils import strip_frontmatter
from .backend import NUM_CTX

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PromptConfig:
    """The five prompt inputs, as one immutable value.

    Set by ``configure()`` from the adapter (via the package facade's
    ``configure()``); ``_config`` below is the process default that every
    builder uses when no explicit config is passed.
    """

    identity_path: Path | None = None
    default_system_prompt: str | None = None
    axiom_prompt: str | None = None
    skills_dir: Path | None = None
    rules_dir: Path | None = None


_config = PromptConfig()

# Cache for _load_md_files results, keyed by directory path.
# Value is (mtime_key, concatenated_contents). Invalidated automatically
# when any *.md file is added, removed, or edited (mtime_key covers both).
_MD_CACHE: dict[Path, tuple[float, str]] = {}
# Same shape for the identity file, keyed by (path, mtime): the read +
# validate runs once per scored post, per internal note and per
# skill-selection call, so an unchanged identity.md is stat'd, not reread.
_IDENTITY_CACHE: tuple[Path, float, str] | None = None


def configure_prompting(
    *,
    identity_path: Path | None = None,
    default_system_prompt: str | None = None,
    axiom_prompt: str | None = None,
    skills_dir: Path | None = None,
    rules_dir: Path | None = None,
) -> None:
    """Set the prompt-side configuration. Called by ``core.llm.configure()``."""
    global _config
    updates = {
        "identity_path": identity_path,
        "default_system_prompt": default_system_prompt,
        "axiom_prompt": axiom_prompt,
        "skills_dir": skills_dir,
        "rules_dir": rules_dir,
    }
    _config = replace(_config, **{k: v for k, v in updates.items() if v is not None})


def reset_prompting() -> None:
    """Reset the prompt-side configuration and cache to defaults."""
    global _config, _IDENTITY_CACHE
    _config = PromptConfig()
    _MD_CACHE.clear()
    _IDENTITY_CACHE = None


def _get_default_system_prompt(config: PromptConfig) -> str:
    """Return the default system prompt, lazy-loading from domain module."""
    if config.default_system_prompt is not None:
        return config.default_system_prompt
    # Lazy import to avoid circular dependency at module load time
    from ..prompts import SYSTEM_PROMPT

    return SYSTEM_PROMPT


def get_distill_system_prompt() -> str:
    """Base system prompt for all distillation / extraction — axioms NOT injected.

    ADR-0058: value layers belong to action time, not distillation time. Every
    distillation stage (distill, insight, constitution amend,
    identity) reads material that is already value-shaped — self-generated
    records were produced under the full action prompt (identity + axioms +
    skills + rules), and downstream corpora (patterns → skills → rules) are
    further axiom-distilled. Re-injecting the axioms here double-counts them.
    The one slice of genuinely fresh material at distill time — external content
    the agent observed — should be extracted faithfully (Mindfulness), not
    re-interpreted through a value lens; the agent's value-laden *response* to it
    is already recorded separately. So distillation uses the base prompt (the
    credential-leak guard) only. Axioms remain at action time via
    ``_build_system_prompt`` (the full session prompt under which the agent
    acts) and ``get_identity_system_prompt`` (the identity lens for the
    mechanical Moltbook calls on fresh external content).
    """
    return _get_default_system_prompt(_config)


def get_identity_system_prompt() -> str:
    """System prompt with identity + axioms but no learned skills/rules.

    Used by mechanical calls (relevance scoring, submolt selection, topic
    summary, ADR-0081 pass-1 skill selection in ``core.skill_selection``) and
    the pre-action internal note: identity supplies the lens
    and the axioms the values, while the learned corpus stays out — it
    distracts a small model from single-token tasks and feeds its own
    vocabulary back into episodes (audit H5).
    """
    return _identity_axioms_base(_config)


def validate_identity_content(content: str) -> bool:
    """Return True if content passes all forbidden pattern checks."""
    content_lower = content.lower()
    for pattern in FORBIDDEN_SUBSTRING_PATTERNS:
        if pattern.lower() in content_lower:
            logger.warning(
                "Identity file contains forbidden pattern: %s, using default",
                pattern,
            )
            return False
    for pattern in FORBIDDEN_WORD_PATTERNS:
        if re.search(
            r"\b" + re.escape(pattern) + r"\b",
            content,
            re.IGNORECASE,
        ):
            logger.warning(
                "Identity file contains forbidden word: %s, using default",
                pattern,
            )
            return False
    return True


def _mtime_key(directory: Path, md_paths: list) -> float | None:
    """Composite mtime covering dir add/delete and per-file edits.

    Max of directory mtime (bumped on entry add/remove) and each
    file's mtime (bumped on content edit). Returns ``None`` if the
    directory stat fails so callers treat it as a cache miss rather
    than caching a stale sentinel.
    """
    try:
        stamps = [directory.stat().st_mtime]
    except OSError:
        return None
    for p in md_paths:
        try:
            stamps.append(p.stat().st_mtime)
        except OSError:
            continue
    return max(stamps)


def _load_md_files(directory: Path | None, label: str) -> str:
    """Load and concatenate .md files from a directory.

    Each file is validated against forbidden patterns; tainted files are skipped.
    Returns concatenated contents, or empty string if directory is missing/empty.

    Result is cached by ``(directory, composite mtime)`` so repeat
    calls inside a session (distill/insight loops invoke
    ``_build_system_prompt`` many times) skip the per-file
    read+validate when nothing has changed. Cache is invalidated
    automatically on any .md add, remove, or edit.
    """
    if directory is None or not directory.is_dir():
        return ""

    md_paths = sorted(directory.glob("*.md"))
    mtime = _mtime_key(directory, md_paths)

    cached = _MD_CACHE.get(directory)
    if mtime is not None and cached is not None and cached[0] == mtime:
        return cached[1]

    items = []
    for path in md_paths:
        try:
            # Strip the leading YAML frontmatter (name/description/origin +
            # telemetry counters) so only the behavioral body reaches the
            # system prompt — otherwise the model can echo it into output
            # (e.g. a skill's `name:` leaked into a published comment).
            content = strip_frontmatter(path.read_text(encoding="utf-8")).strip()
            if content and validate_identity_content(content):
                items.append(content)
            elif content:
                logger.warning("%s file %s contains forbidden patterns, skipping", label, path.name)
        except OSError as exc:
            logger.warning("Failed to read %s file %s: %s", label, path.name, exc)

    result = "\n\n".join(items)
    if mtime is not None:
        _MD_CACHE[directory] = (mtime, result)
    return result


def _identity_axioms_base(config: PromptConfig) -> str:
    """Identity (validated, or default prompt) plus CCAI axiom clauses.

    Shared base for ``get_identity_system_prompt`` and
    ``_build_system_prompt`` so both use the same identity-validation path.
    """
    global _IDENTITY_CACHE
    base_prompt = _get_default_system_prompt(config)
    identity = config.identity_path
    if identity is not None:
        try:
            mtime = identity.stat().st_mtime
        except OSError:
            mtime = None
        cached = _IDENTITY_CACHE
        if (
            mtime is not None
            and cached is not None
            and cached[0] == identity
            and cached[1] == mtime
        ):
            base_prompt = cached[2]
        elif mtime is not None:
            try:
                content = identity.read_text(encoding="utf-8").strip()
            except OSError as exc:
                logger.warning("failed to read identity file %s: %s", identity, exc)
                content = ""
            if content and validate_identity_content(content):
                base_prompt = content
                _IDENTITY_CACHE = (identity, mtime, base_prompt)

    # Append CCAI axiom clauses if configured
    if config.axiom_prompt:
        base_prompt = base_prompt + "\n\n---\n\n" + config.axiom_prompt
    return base_prompt


# Usage framing for the injected learned corpus (weekly diagnosis 2026-07-05
# F1.1). The auto-extracted skill bodies are imperative procedures with
# trigger tables; injected bare, the model performs them *visibly* — published
# comments opened with skill-activation scaffolding, once replacing the reply
# entirely (06-29 #2b826a1e). The framing states the process/product split
# (application is internal, published text is only the reply) without naming
# any phrase or format token. Wording drafted by the production model itself
# (gemma4:e4b, 2026-07-06). Externalized to config/prompts/ (ADR-0054); these
# hardcoded fallbacks re-assert the framing if a template is missing or empty.
_DEFAULT_LEARNED_SKILLS_FRAMING = (
    "These accumulated dispositions represent your internal knowledge base "
    "derived from past engagements; they inform how you interpret input and "
    "structure your responses. Remember that activating these skills is a "
    "purely internal process and must never be mentioned, labeled, or "
    "discussed in the final text you publish. Your published response should "
    "contain only the reply itself, addressed to the other party."
)
_DEFAULT_LEARNED_RULES_FRAMING = (
    "The rules listed act as silent behavioral constraints guiding your "
    "output; they are integral to your responses but must never be announced "
    "or narrated in any published text."
)


def _build_system_prompt(config: PromptConfig | None = None) -> str:
    """Build the full system prompt from identity, axioms, skills, and rules.

    Layers: default prompt (or identity.md if valid) + axioms + skills + rules.
    Identity content is validated against forbidden patterns. Each learned
    block is preceded by a usage-framing preamble (see the framing constants
    above) so the model treats the corpus as internal disposition rather than
    a procedure to narrate.
    """
    config = config if config is not None else _config
    return build_system_prompt_with_skills(_load_md_files(config.skills_dir, "Skill"), config)


def build_system_prompt_with_skills(skills: str, config: PromptConfig | None = None) -> str:
    """Compose the system prompt with a caller-supplied skills block.

    ADR-0081 pass-2 seam: under two-pass injection the caller passes the
    selection-filtered skill bodies (already frontmatter-stripped and
    forbidden-pattern-validated by ``skill_selection.selected_skills_block``);
    an empty string omits the ``<learned_skills>`` block entirely (a
    judged-empty selection injects nothing). Rules injection is unchanged.
    ``_build_system_prompt()`` delegates here with the full corpus, so the
    layer order and framing are single-sourced.
    """
    config = config if config is not None else _config
    base_prompt = _identity_axioms_base(config)

    # Append learned skills and rules if available (treated as untrusted —
    # distilled LLM output that passed forbidden-pattern checks but could
    # still contain behavioral manipulation). The framing imports stay inside
    # the corpus branches: pulling them eagerly would force the full prompt
    # registry to load even for a minimal runtime with an injected
    # default_system_prompt and no learned corpus (codex review 2026-07-06 P2).
    if skills:
        from ..prompts import LEARNED_SKILLS_FRAMING_PROMPT

        framing = LEARNED_SKILLS_FRAMING_PROMPT or _DEFAULT_LEARNED_SKILLS_FRAMING
        base_prompt = (
            base_prompt + "\n\n---\n\n" + framing + "\n\n"
            "<learned_skills>\n" + skills + "\n</learned_skills>"
        )

    rules = _load_md_files(config.rules_dir, "Rule")
    if rules:
        from ..prompts import LEARNED_RULES_FRAMING_PROMPT

        framing = LEARNED_RULES_FRAMING_PROMPT or _DEFAULT_LEARNED_RULES_FRAMING
        base_prompt = (
            base_prompt + "\n\n---\n\n" + framing + "\n\n"
            "<learned_rules>\n" + rules + "\n</learned_rules>"
        )

    return base_prompt


def _estimate_tokens(text: str) -> int:
    """Approximate token count without a tokenizer dependency (audit C2).

    Conservative upper bound in BOTH char classes, so the skip guard never
    under-counts: ASCII at ~3 chars/tok (dense markdown/code/URLs tokenize
    denser than prose's ~4 — ~0.33 tok/char ≥ real ~0.25); non-ASCII/CJK at
    2 tok/char (Qwen3.5 real is ~1.5-2, so 2 is the upper bound). Counting CJK
    at 1 tok/char would UNDER-estimate by 33-50% and let a CJK-heavy prompt
    slip past the guard into Ollama front-truncation — the exact failure the
    guard prevents. The project ships only
    requests+numpy, so no real tokenizer is available; over-estimating is the
    safe direction for a skip guard.
    """
    ascii_count = len(text.encode("ascii", "ignore"))
    return math.ceil(ascii_count / 3) + (len(text) - ascii_count) * 2


@dataclass(frozen=True)
class SystemBudgetReading:
    """Read-only projection of the system prompt's context-window cost.

    An ADR-0071-style instrument reading: it informs the operator at a
    value-layer approval gate ("adopting this batch takes the system prompt
    to N tok, Z% of the window") and feeds no gate, ranking, or retrieval.
    Token counts use :func:`_estimate_tokens`, which deliberately
    over-counts (audit C2 scale) — read the numbers as a conservative
    ceiling, not a measurement.
    """

    current_tokens: int
    projected_tokens: int
    window: int


def system_prompt_budget_reading(
    new_texts: Sequence[str],
    replaced_texts: Sequence[str] = (),
    *,
    identity_path: Path | None = None,
    axiom_prompt: str | None = None,
    skills_dir: Path | None = None,
    rules_dir: Path | None = None,
) -> SystemBudgetReading:
    """Project the system prompt token estimate after a value-layer change.

    ``new_texts`` are bodies about to be added (or written over existing
    files); ``replaced_texts`` are the current bodies they replace or delete.
    The projection is additive over file bodies — framing preambles and
    separators in :func:`_build_system_prompt` are per-corpus, not per-file,
    so a per-file delta approximates the real rebuild closely enough for an
    approval-gate reading. Motivated 2026-07-09: a 13-skill batch was
    approved with no budget visibility and pushed the system prompt past the
    C2 guard, silencing every self-post for 24+ hours.

    The keyword overrides let an unconfigured caller (e.g. the Tier-1
    ``adopt-staged`` command, which never runs the LLM setup) measure the
    session-time prompt composition. They compose a one-off
    :class:`PromptConfig` for this reading only — the process default is never
    touched, so an instrument leaves no module configuration behind.
    """
    overrides = {
        "identity_path": identity_path,
        "axiom_prompt": axiom_prompt,
        "skills_dir": skills_dir,
        "rules_dir": rules_dir,
    }
    config = replace(_config, **{k: v for k, v in overrides.items() if v is not None})
    current = _estimate_tokens(_build_system_prompt(config))
    delta = sum(_estimate_tokens(t) for t in new_texts) - sum(
        _estimate_tokens(t) for t in replaced_texts
    )
    return SystemBudgetReading(
        current_tokens=current,
        projected_tokens=max(0, current + delta),
        window=NUM_CTX,
    )
