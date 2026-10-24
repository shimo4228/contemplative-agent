"""Constitution amendment: feed constitutional experience back into ethical principles.

ADR-0026 (Phase 2): constitutional pattern selection moved from the
pattern-level ``category`` field to query-time view routing. The caller
supplies a ``ViewRegistry`` and we retrieve patterns via
``find_by_view("constitutional", ...)``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .knowledge_store import epistemic_counts_for, pattern_id
from .llm import generate_full, get_distill_system_prompt, validate_identity_content
from .memory import KnowledgeStore
from .views import ViewRegistry

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3

# Reason-coded refusal for a generation that fails forbidden-pattern validation
# (P0-04.5). The rejected body is NOT echoed: the CLI prints any ``str`` result,
# so returning the text would surface a tainted amendment as if it were output.
# Mirrors ``distill_identity``; the CLI matches this string to append a
# ``validation_failed`` row to ``audit.jsonl``.
AMEND_VALIDATION_FAILED = "Generated constitution failed forbidden-pattern validation; discarded."


_COLON_HEADING_RE = re.compile(r"^\s*(?:\*\*)?[^\s\-*>#\"][^\n]*:(?:\*\*)?\s*$")
_MD_HEADING_RE = re.compile(r"^#{1,6}\s+\S")
_CLAUSE_RE = re.compile(r"^\s*[-*]\s+(.*\S)")


def shape_reading(text: str) -> dict[str, Any]:
    """Count sections, clauses and the quoted-clause rate of a constitution-shaped text.

    P0-07.7: a purely structural reading (no embeddings, no LLM) so the amend
    record and the ADR-0092 shadow instrument can share one definition. A
    section is a line ending in ``:`` (optionally bold) when the text has any,
    else a markdown heading; a clause is a bullet line; ``quoted_rate`` is the
    share of clauses that start with a double quote (``None`` with no clauses).
    """
    lines = text.splitlines()
    colon = sum(1 for ln in lines if _COLON_HEADING_RE.match(ln) and not _CLAUSE_RE.match(ln))
    sections = colon or sum(1 for ln in lines if _MD_HEADING_RE.match(ln))
    clauses = [m.group(1) for ln in lines if (m := _CLAUSE_RE.match(ln))]
    quoted = sum(1 for c in clauses if c.startswith('"'))
    return {
        "sections": sections,
        "clauses": len(clauses),
        "quoted_rate": round(quoted / len(clauses), 4) if clauses else None,
    }


def provenance_path(target: Path) -> Path:
    """Sidecar holding a constitution file's machine-written provenance.

    A sibling ``<stem>.provenance.json``, never frontmatter: ``read_constitution``
    concatenates the raw ``*.md`` files into the system prompt, so anything
    inside them is injected, while this file (not ``*.md``) never is.
    """
    return target.with_name(f"{target.stem}.provenance.json")


def _view_numbers(view_registry: ViewRegistry, name: str) -> tuple[int | None, float | None]:
    """``(top_k, threshold)`` of a view, ``None`` where the view or a field is absent."""
    view = view_registry.get(name)
    top_k = getattr(view, "top_k", None)
    threshold = getattr(view, "threshold", None)
    return (
        top_k if isinstance(top_k, int) and not isinstance(top_k, bool) else None,
        float(threshold) if isinstance(threshold, (int, float)) else None,
    )


def render_constitutional_patterns(matched: list[dict]) -> str:
    """Render view-matched patterns as prompt bullets, chat-control tokens stripped.

    Patterns are distilled from episodes that embed untrusted external content,
    so a pattern can carry template-breakout tokens (security review 2026-08-11).
    Shared by both constitution arms — ``amend_constitution`` and the ADR-0092
    shadow synthesis, where the patterns are the prompt's *sole* content — so
    the two prompts stay comparable and the strip cannot drift apart.
    """
    from .llm import strip_injection_tokens

    lines = []
    for p in matched:
        # Shared with the wrapper's strip since 2026-08-16. The local copy was
        # a single ``replace`` pass, which is the shape that lets a nested
        # payload reconstruct the token it just deleted. No attack path was
        # verified *here* — this prompt carries no frame, so a reconstructed
        # closing tag would have nothing to close — so this is a consolidation,
        # not a security fix. It exists so the two strips cannot drift again.
        lines.append(f"- {strip_injection_tokens(str(p['pattern'])).text}")
    return "\n".join(lines)


@dataclass(frozen=True)
class AmendmentResult:
    """Result of a successful constitution amendment generation.

    ADR-0050: ``pattern_ids`` carries the content-hash ids of the
    view-matched input patterns; ``epistemic_counts`` their
    generated/unknown tally (ADR-0082).
    """

    text: str
    target_path: Path
    marker_dir: Path
    pattern_ids: tuple[str, ...] = ()
    epistemic_counts: dict[str, int] = field(default_factory=dict)
    # ADR-0069: reasoning trace behind the amendment (amend-constitution runs
    # think-ON — the constitution sits at the top of the behavior-change chain,
    # so the owner sees *why* this amendment was proposed at the approval gate).
    thinking: str | None = None
    # P0-07.7: how much of the store the amendment saw (matched_count of
    # live_count patterns, under the view's top_k / threshold) and the
    # structural shape of the current and amended texts. Recorded, never gated
    # on (bold integration is by design). Written into the snapshot manifest
    # by the amend handler.
    input_selection: dict[str, Any] = field(default_factory=dict)


def amend_constitution(
    knowledge_store: KnowledgeStore | None = None,
    constitution_dir: Path | None = None,
    view_registry: ViewRegistry | None = None,
) -> str | AmendmentResult:
    """Generate a constitution amendment from accumulated constitutional patterns.

    Reads the current constitution and constitutional patterns from the knowledge store,
    then asks the LLM to propose an updated constitution that incorporates learned
    ethical insights while preserving the original structure.

    File writing is the caller's responsibility (ADR-0012 approval gate).

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        constitution_dir: Directory containing constitution .md files.
        view_registry: ViewRegistry used to retrieve constitutional
            patterns via embedding cosine (ADR-0026). Required since
            Phase 2 — the legacy ``category="constitutional"`` row
            filter has been retired.

    Returns:
        AmendmentResult on success, or error message string.
    """
    from .prompts import CONSTITUTION_AMEND_PROMPT

    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if view_registry is None:
        msg = (
            "amend_constitution requires a ViewRegistry since ADR-0026. "
            "Pass a ViewRegistry instance so constitutional patterns can be "
            "retrieved via view cosine."
        )
        logger.warning(msg)
        return msg

    # ADR-0026 Phase 2: constitutional patterns are retrieved via the
    # "constitutional" view's embedding cosine rather than a persisted
    # category label. Patterns lacking embeddings are silently skipped.
    live_patterns = knowledge.get_live_patterns()
    matched = view_registry.find_by_view("constitutional", live_patterns)
    if len(matched) < MIN_PATTERNS_REQUIRED:
        msg = (
            f"Insufficient constitutional patterns ({len(matched)}/{MIN_PATTERNS_REQUIRED}). "
            f"More ethical experience needed before amendment."
        )
        logger.info(msg)
        return msg

    constitutional_text = render_constitutional_patterns(matched)

    if not CONSTITUTION_AMEND_PROMPT:
        msg = "constitution_amend.md prompt template not found."
        logger.warning(msg)
        return msg

    if constitution_dir is None:
        msg = "No constitution directory configured."
        logger.warning(msg)
        return msg

    axiom_files = sorted(constitution_dir.glob("*.md"))
    if not axiom_files:
        msg = f"No constitution files found in {constitution_dir}"
        logger.warning(msg)
        return msg

    # P0-04.7: the loader (``core/domain.py``) concatenates EVERY ``*.md`` in
    # the directory, but an amendment can only replace one file. With two or
    # more, the write would leave the old text injected beside the new
    # (the ``-2.md`` incident, ADR-0090). Refuse and say why; the operator
    # merges them into one file first.
    if len(axiom_files) > 1:
        names = ", ".join(f.name for f in axiom_files)
        msg = (
            f"Refusing to amend: {len(axiom_files)} constitution files in "
            f"{constitution_dir} ({names}). The loader concatenates all of them "
            f"but an amendment replaces one; merge them into a single file first."
        )
        logger.warning(msg)
        return msg

    axioms_path = axiom_files[0]
    current_constitution = axioms_path.read_text(encoding="utf-8").strip()
    if not current_constitution:
        msg = "Constitution file is empty."
        logger.warning(msg)
        return msg

    top_k, threshold = _view_numbers(view_registry, "constitutional")
    prompt = CONSTITUTION_AMEND_PROMPT.format(
        current_constitution=current_constitution,
        constitutional_patterns=constitutional_text,
    )

    out = generate_full(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        caller="constitution.amend",
        think=True,
        drop_truncated=True,
    )
    if out is None or out.text is None:
        msg = "LLM failed to generate constitution amendment."
        logger.warning(msg)
        return msg

    amended_text = out.text.strip()

    if not validate_identity_content(amended_text):
        logger.warning("Generated constitution failed validation; discarding")
        return AMEND_VALIDATION_FAILED

    return AmendmentResult(
        text=amended_text,
        target_path=axioms_path,
        marker_dir=constitution_dir,
        pattern_ids=tuple(pattern_id(p) for p in matched),
        epistemic_counts=epistemic_counts_for(matched),
        thinking=out.thinking,
        input_selection={
            "matched_count": len(matched),
            "live_count": len(live_patterns),
            "top_k": top_k,
            "threshold": threshold,
            "shape_current": shape_reading(current_constitution),
            "shape_amended": shape_reading(amended_text),
        },
    )
