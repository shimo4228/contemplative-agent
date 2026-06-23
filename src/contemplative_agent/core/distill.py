"""Sleep-time memory distillation: extract patterns from episode logs.

ADR-0019: dedup is embedding-cosine based; subcategorisation has been
removed (replaced by views, which materialise grouping at query time).

ADR-0060: each substantive engagement episode (comment / reply / post) is
rendered richly and distilled by one grounded LLM call; the resulting
patterns flow through the unchanged embed → cosine dedup → store tail.
The ADR-0026 ingest-time noise gate and the fixed-size batch extract/refine
pipeline were removed — recurrence is captured downstream when ``insight``
clusters patterns into skills, not by pre-clustering episodes here.
"""

from __future__ import annotations

import json as json_mod
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from ._io import now_iso, strip_code_fence, truncate_boundary
from .embeddings import cosine, embed_texts
from .config import MAX_COMMENT_LENGTH, MAX_POST_LENGTH
from .knowledge_store import (
    effective_importance,
    epistemic_counts_for,
    is_live,
    pattern_id,
)
from .llm import (
    generate,
    get_distill_system_prompt,
    validate_identity_content,
    wrap_untrusted_content,
)
from .memory import EpisodeLog, KnowledgeStore
from .prompts import (
    DISTILL_EPISODE_PROMPT,
    IDENTITY_DISTILL_PROMPT,
)
from .views import ViewRegistry

logger = logging.getLogger(__name__)

# Input scope (ADR-0060): distill learns only from substantive engagement
# episodes — comment / reply / post activity records, which carry real
# world-grounding (original_post / their_comment / the agent's own output +
# the pre-action internal_note). The redundant short 'interaction' / 'post'
# records (each engagement writes both a rich activity record and a short
# paired one) and the template sparse actions (upvote / follow / unfollow,
# which carry no engagement content) are excluded.
RICH_ACTIONS = frozenset({"comment", "reply", "post"})

# Per-field excerpt caps for the rich episode render (ADR-0060). Set to the
# platform field limits so realistic content is never cut: one episode per
# LLM call fits inside NUM_CTX with margin even at platform max — the
# worst-case reply (post 40000 + comment 10000 + own reply 10000 + note)
# estimates ≈21.6k input tokens for ASCII (llm._estimate_tokens, /3), well
# under the 32768 budget after num_predict. truncate_boundary stays as a
# structural guard for out-of-spec data; a pathological all-CJK max render
# would be skipped by the NUM_CTX guard in generate() (logged, not corrupt).
# internal_note is in-register first-person and never capped. Measured
# production field lengths (p90 ≈ original_post 4700 / content 4700 /
# their_comment 1500, max ≈ 7400) are well within these, so nothing real is
# truncated — see docs/evidence/adr-0060/.
EXCERPT_CAPS = {
    "original_post": MAX_POST_LENGTH,
    "their_comment": MAX_COMMENT_LENGTH,
    "content": MAX_POST_LENGTH,
}

# Structured-output schema for the per-episode distill call. Constrains the
# model to emit ``{"patterns": [...]}`` at the token level (Ollama format=),
# removing the malformed-JSON risk the 2-step bullet fallback used to absorb.
_PATTERNS_SCHEMA = {
    "type": "object",
    "properties": {"patterns": {"type": "array", "items": {"type": "string"}}},
    "required": ["patterns"],
}

# Embedding-based dedup thresholds live in ``core/thresholds.py`` since
# ADR-0035 PR2; re-exported under the historical names here so existing call
# sites keep working without ad-hoc late imports.
from .thresholds import (  # noqa: E402 — module-level by design
    DEDUP_IMPORTANCE_FLOOR,
    SIM_DUPLICATE,
    SIM_UPDATE,
)


def distill(
    days: int = 1,
    dry_run: bool = False,
    episode_log: Optional[EpisodeLog] = None,
    knowledge_store: Optional[KnowledgeStore] = None,
    log_files: Optional[List[Path]] = None,
) -> str:
    """Distill recent engagement episodes into learned patterns.

    ADR-0060: each substantive engagement episode (comment / reply / post)
    is rendered richly — the post engaged with, the other agent's comment,
    the agent's own output, and the pre-action internal note — and distilled
    individually by one LLM call. The resulting patterns are embedded and
    deduplicated by cosine similarity against the live pool (the unchanged
    tail). The former noise gate (ADR-0026 Step 0) and fixed-size batching
    are gone: recurrence is captured downstream when ``insight`` clusters
    patterns into skills, not by pre-clustering episodes.

    Args:
        days: Number of days of episodes to process.
        dry_run: If True, return results without writing.
        episode_log: EpisodeLog instance (uses default if None).
        knowledge_store: KnowledgeStore instance (uses default if None).
        log_files: Explicit JSONL file paths to process (overrides days).

    Returns:
        The distilled patterns as a string.
    """
    episodes = episode_log or EpisodeLog()
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if log_files:
        records: List[Dict] = []
        for path in log_files:
            records.extend(EpisodeLog.read_file(path))
    else:
        records = episodes.read_range(days=days)
    # ADR-0052 (audit M4): insight records are LLM session summaries, not
    # observations. Re-distilling them creates summary-of-summary patterns
    # two hops from any observable fact. Generation was retired, but
    # historical insight records remain in the log permanently (episodes
    # are research data) — so the read path must exclude them explicitly.
    pre_insight_filter = len(records)
    records = [r for r in records if r.get("type") != "insight"]
    if pre_insight_filter > len(records):
        logger.info(
            "Excluded %d insight records from distillation (ADR-0052)",
            pre_insight_filter - len(records),
        )
    if not records:
        msg = "No episodes found for distillation."
        logger.info(msg)
        return msg

    # ADR-0060: distill only substantive engagement episodes. The redundant
    # short paired records and the template sparse actions are filtered out;
    # there is no noise gate (its job — keeping noise out of retrieval — is
    # already done at query time by view centroids, ADR-0031).
    rich = [r for r in records if _is_rich_episode(r)]
    if not rich:
        msg = "No engagement episodes (comment/reply/post) for distillation."
        logger.info(msg)
        return msg
    logger.info(
        "Distilling %d engagement episodes (filtered from %d records)",
        len(rich), len(records),
    )

    # Determine source date range from the in-scope episodes. read_range
    # returns newest-day-first, so the oldest timestamp is last — render the
    # range oldest~newest for readable provenance.
    timestamps = sorted(r.get("ts", "")[:10] for r in rich if r.get("ts"))
    source_date = timestamps[0] if timestamps else None
    if timestamps and timestamps[0] != timestamps[-1]:
        source_date = f"{timestamps[0]}~{timestamps[-1]}"

    result = _distill_episodes(rich, knowledge, source_date, dry_run)

    # ``results`` is empty only when every episode's LLM call returned None
    # (an episode that yields zero patterns still records its raw output) —
    # surface that as a message rather than a silent blank line.
    if not result.results:
        msg = f"Distillation extracted no patterns: all {len(rich)} episode calls failed."
        logger.warning(msg)
        return msg

    if not dry_run and (result.added or result.updated):
        knowledge.save()
        logger.info(
            "Distill complete: %d added, %d updated", result.added, result.updated,
        )

    return "\n\n".join(result.results)


def _is_rich_episode(record: Dict) -> bool:
    """True iff this episode carries substantive world-grounding (ADR-0060).

    Only ``activity`` records for ``comment`` / ``reply`` / ``post`` actions
    carry the post engaged with, the agent's own output, and (for replies)
    the other agent's comment. Interaction records are redundant short pairs;
    sparse actions (upvote / follow / unfollow) carry no engagement content.
    """
    if record.get("type") != "activity":
        return False
    return (record.get("data") or {}).get("action") in RICH_ACTIONS


def enrich(
    knowledge_store: KnowledgeStore,
    dry_run: bool = False,
) -> int:
    """No-op since ADR-0019: subcategorisation is now query-time via views.

    Kept as a stable entry point so the ``enrich`` CLI subcommand is
    callable; it now reports zero work.
    """
    _ = (knowledge_store, dry_run)
    logger.info("enrich is a no-op since ADR-0019.")
    return 0


@dataclass(frozen=True)
class IdentityResult:
    """Result of a successful identity distillation.

    ADR-0050: ``pattern_ids`` carries the content-hash ids of the
    view-matched input patterns; ``epistemic_counts`` their
    observed/generated tally — the headline metric for how much of the
    identity input is self-generated narrative.
    """

    text: str
    target_path: Path
    pattern_ids: Tuple[str, ...] = ()
    epistemic_counts: Dict[str, int] = field(default_factory=dict)


def distill_identity(
    knowledge_store: Optional[KnowledgeStore] = None,
    identity_path: Optional[Path] = None,
    view_registry: Optional[ViewRegistry] = None,
) -> Union[str, IdentityResult]:
    """Distill an updated identity description from self-reflection patterns.

    Asks the LLM to write a brief self-description from the agent's accumulated
    self-reflection patterns. Since ADR-0057 the prior identity is NOT seeded
    into the prompt; since ADR-0058 the distillation system prompt is axiom-free
    (``get_distill_system_prompt`` is base-only). The persona emerges from the
    self-reflection corpus alone, which already carries the axiom register, so
    the two former inputs only over-determined the output.

    File writing is the caller's responsibility (ADR-0012 approval gate).

    Args:
        knowledge_store: KnowledgeStore instance (uses default if None).
        identity_path: Write target for the distilled identity (the caller
            performs the approval-gated write); no longer read as a prompt
            seed since ADR-0057.
        view_registry: ViewRegistry used to retrieve self-reflection
            patterns via embedding cosine. Required for ADR-0019 routing;
            patterns lacking embeddings are skipped.

    Returns:
        IdentityResult on success, or error message string.
    """
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if view_registry is None:
        msg = (
            "distill_identity requires a ViewRegistry since ADR-0019. "
            "Pass a ViewRegistry instance."
        )
        logger.warning(msg)
        return msg

    # Identity is distilled from self-reflection patterns only. Routing is
    # done via the "self_reflection" view's embedding cosine (ADR-0019,
    # ADR-0026). Rationale: self-reflection captures internal states;
    # mixing behavioral norms into identity dilutes persona specificity
    # via the Emptiness axiom.
    matched = view_registry.find_by_view("self_reflection", knowledge.get_raw_patterns())
    if not matched:
        msg = "No self-reflection patterns available for identity distillation."
        logger.info(msg)
        return msg
    knowledge_text = "\n".join(f"- {p['pattern']}" for p in matched)

    if not IDENTITY_DISTILL_PROMPT:
        msg = "identity_distill.md prompt template not found."
        logger.warning(msg)
        return msg

    # The prior identity is intentionally NOT seeded into the prompt. Seeding
    # it made the LLM edit the previous text (regression-to-prior hysteresis),
    # so upstream routing/staging changes had little leverage on the output.
    # Distilling fresh from the self-reflection corpus alone lets the identity
    # actually move, and matches the persona's own claim of holding no fixed,
    # defended shape (Emptiness / non-self).
    prompt = IDENTITY_DISTILL_PROMPT.format(
        knowledge=knowledge_text,
    )

    result = generate(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        caller="distill.identity",
    )
    if result is None:
        msg = "LLM failed to generate identity revision."
        logger.warning(msg)
        return msg

    # Clean up: strip empty lines and preamble
    lines = [line.strip() for line in result.strip().splitlines() if line.strip()]
    new_identity = "\n".join(lines)

    # Validate against forbidden patterns before returning
    if not validate_identity_content(new_identity):
        logger.warning("Generated identity failed validation")
        return new_identity

    if not identity_path:
        return new_identity

    return IdentityResult(
        text=new_identity,
        target_path=identity_path,
        pattern_ids=tuple(pattern_id(p) for p in matched),
        epistemic_counts=epistemic_counts_for(matched),
    )



def _episode_source_kind(record: Dict) -> str:
    """Classify one episode as 'self' / 'external' / 'unknown' (ADR-0021)."""
    record_type = record.get("type", "")
    data = record.get("data", {}) or {}
    if record_type == "interaction":
        return "external" if data.get("direction") == "received" else "self"
    if record_type in ("post", "activity"):
        return "self"
    return "unknown"


def _derive_source_type(records: List[Dict]) -> str:
    """Map a batch of episodes to an ADR-0021 provenance.source_type value.

    Pure origin record (ADR-0051 retired the trust weighting that used to
    hang off it; ADR-0050's ``epistemic_kind_for`` derives from it):

    - All self-generated → self_reflection.
    - All externally-sourced → external_reply.
    - Mixed self + external → mixed.
    - Only unknown types → unknown.
    """
    kinds = {_episode_source_kind(r) for r in records}
    kinds.discard("unknown")
    if not kinds:
        return "unknown"
    if kinds == {"self"}:
        return "self_reflection"
    if kinds == {"external"}:
        return "external_reply"
    return "mixed"


@dataclass(frozen=True)
class _CategoryResult:
    """Result of distilling a single category."""
    results: Tuple[str, ...]
    added: int
    updated: int


@dataclass(frozen=True)
class _BatchOutput:
    """Patterns distilled from one episode (ADR-0060).

    ``refined`` is the raw LLM output (kept for the returned summary string);
    ``source_type`` and ``episode_ids`` carry the single episode's ADR-0021
    provenance.
    """
    refined: str
    patterns: Tuple[str, ...]
    source_type: str
    episode_ids: Tuple[str, ...]


def render_episode(record_type: str, data: dict) -> str:
    """Render one episode as a rich, world-grounded block (ADR-0060).

    A ``comment`` / ``reply`` / ``post`` activity record carries the post
    the agent engaged with (``original_post``), the other agent's comment
    (``their_comment``, replies only), the agent's own output (``content``),
    and the pre-action ``internal_note``. Each external field is excerpted
    with :func:`truncate_boundary` at its ADR-0060 cap; the in-register note
    is included in full. A sparse record with none of those fields falls
    back to the one-line :func:`summarize_record` so the caller never gets
    an empty render.
    """
    if record_type != "activity":
        return summarize_record(record_type, data)

    parts: List[str] = []
    # ADR-0060 added external (peer-authored) fields to the distill render.
    # ``original_post`` / ``their_comment`` are stored RAW in the episode log
    # (action-time wrapping in llm_functions.py does not reach the persisted
    # record), so they must be wrapped here before reaching the distill LLM —
    # otherwise a malicious peer post could steer pattern extraction into
    # skills/rules/identity/constitution. The agent's own ``title`` /
    # ``content`` / ``internal_note`` are self-authored and stay un-wrapped so
    # extraction remains faithful to the agent's own register.
    op = data.get("original_post")
    if op:
        parts.append(
            "Post I engaged with:\n"
            + wrap_untrusted_content(op, max_input=EXCERPT_CAPS["original_post"])
        )
    tc = data.get("their_comment")
    if tc:
        parts.append(
            "Their comment:\n"
            + wrap_untrusted_content(tc, max_input=EXCERPT_CAPS["their_comment"])
        )
    title = data.get("title")
    if title:
        parts.append("Title I gave it:\n" + title)
    out = data.get("content")
    action = data.get("action", "?")
    if out:
        parts.append(
            f"My {action}:\n" + truncate_boundary(out, EXCERPT_CAPS["content"])
        )
    note = data.get("internal_note")
    if note:
        parts.append("What I noticed:\n" + note)  # in-register, never capped

    if not parts:
        return summarize_record(record_type, data)

    target = data.get("target_agent", "")
    header = f"[{action} {target}]" if target else f"[{action}]"
    return header + "\n" + "\n\n".join(parts)


def _parse_refined_patterns(refined: str) -> List[str]:
    """Parse step-2 output into raw pattern strings (JSON, bullet fallback)."""
    raw_patterns: List[str] = []
    json_text = strip_code_fence(refined)
    try:
        parsed = json_mod.loads(json_text)
        for item in parsed.get("patterns", []):
            text = str(item).strip() if item else ""
            if text:
                raw_patterns.append(text)
    except (json_mod.JSONDecodeError, TypeError):
        # Fallback: bullet-point parsing
        for line in refined.splitlines():
            line = line.strip()
            if line.startswith("- "):
                pattern = line[2:].strip()
                if pattern:
                    raw_patterns.append(pattern)
    return raw_patterns


def _distill_one(record: Dict) -> Optional[_BatchOutput]:
    """Distill one engagement episode into its pattern(s); None on failure.

    ADR-0060: a single LLM call over the rich, world-grounded render of one
    episode. Structured output (``format=``) constrains the model to the
    ``{"patterns": [...]}`` shape, so the malformed-JSON the old 2-step
    bullet fallback absorbed cannot occur. Per-episode provenance (one
    episode's source kind and timestamp) replaces the per-batch summary.
    """
    record_type = record.get("type", "unknown")
    data = record.get("data", {}) or {}
    rendered = render_episode(record_type, data)
    if not rendered:
        return None

    source_type = _derive_source_type([record])
    prompt = DISTILL_EPISODE_PROMPT.format(episode=rendered)

    result = generate(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        format=_PATTERNS_SCHEMA,
        caller="distill.episode",
    )
    if result is None:
        logger.warning("Episode distill failed (LLM returned None)")
        return None

    raw_patterns = _parse_refined_patterns(result)

    # Decision gate: reject low-quality patterns
    patterns = [p for p in raw_patterns if _is_valid_pattern(p)]
    rejected = len(raw_patterns) - len(patterns)

    ts = record.get("ts", "")
    logger.info(
        "Episode %s (prompt %d chars) → %d patterns (%d rejected)",
        ts[:16], len(prompt), len(patterns), rejected,
    )
    return _BatchOutput(
        refined=result,
        patterns=tuple(patterns),
        source_type=source_type,
        episode_ids=(ts,) if ts else (),
    )


def _distill_episodes(
    records: List[Dict],
    knowledge: KnowledgeStore,
    source_date: Optional[str],
    dry_run: bool,
) -> _CategoryResult:
    """Distill each engagement episode individually, then dedup + store.

    ADR-0060: one LLM call per episode (no fixed-size batching, no noise
    gate). The resulting patterns flow through the unchanged embed → cosine
    dedup → store tail; dedup runs against the full live pool, so a pattern
    re-observed from a recurring episode is caught at the pattern level
    (SKIP / UPDATE) without any episode-level pre-clustering.
    """
    logger.info("Distilling %d episodes individually", len(records))

    all_patterns: List[str] = []
    all_source_types: List[str] = []
    all_episode_ids: List[List[str]] = []
    all_results: List[str] = []

    for record in records:
        out = _distill_one(record)
        if out is None:
            continue
        all_results.append(out.refined)
        all_patterns.extend(out.patterns)
        # ADR-0021/0060: provenance is now per-episode — each pattern carries
        # the source kind and timestamp of the single episode it came from.
        for _ in out.patterns:
            all_source_types.append(out.source_type)
            all_episode_ids.append(list(out.episode_ids))

    if not all_patterns:
        return _CategoryResult(results=tuple(all_results), added=0, updated=0)

    # ADR-0019: bulk-embed new patterns inline so dedup can run on cosine
    # similarity instead of SequenceMatcher + LLM gate.
    new_embeddings_arr = embed_texts(all_patterns)
    if new_embeddings_arr is None or new_embeddings_arr.shape[0] != len(all_patterns):
        logger.warning(
            "Failed to embed %d new patterns; storing without embedding (dedup degraded)",
            len(all_patterns),
        )
        new_embeddings: List[Optional[np.ndarray]] = [None] * len(all_patterns)
    else:
        new_embeddings = [new_embeddings_arr[i] for i in range(len(all_patterns))]

    # ADR-0026: dedup scope is the full live pool. Cross-axis overlap is
    # acceptable — the semantic coordinate is shared regardless of which
    # view a pattern is routed through at query time.
    # is_live gate (valid_until, ADR-0051) is enforced inside
    # _dedup_patterns; this pre-filter exists for the decay-floor log.
    # ADR-0056: effective_importance is pure time decay, so the floor now
    # drops any pattern older than ~58 days from the dedup comparison scope,
    # letting a re-observed insight re-enter as a fresh record (ADR-0053 §4).
    existing_patterns = list(knowledge.get_raw_patterns())
    pre_filter = len(existing_patterns)
    existing_patterns = [
        p for p in existing_patterns
        if effective_importance(p) >= DEDUP_IMPORTANCE_FLOOR
    ]
    if pre_filter > len(existing_patterns):
        logger.info("Dedup scope: %d/%d patterns (decay floor %.2f)",
                    len(existing_patterns), pre_filter, DEDUP_IMPORTANCE_FLOOR)

    (
        add_patterns, add_embeddings,
        add_indices, skipped, updated,
    ) = _dedup_patterns(
        all_patterns, new_embeddings, existing_patterns,
        mutate_existing=not dry_run,
    )

    if dry_run:
        logger.info(
            "Dry run — %d patterns found, %d skipped, %d would soft-invalidate",
            len(all_patterns), skipped, updated,
        )
        return _CategoryResult(results=tuple(all_results), added=0, updated=0)

    if updated:
        logger.info(
            "Dedup: %d soft-invalidated (bitemporal) and replaced with new patterns",
            updated,
        )

    _store_new_patterns(
        knowledge, source_date,
        add_patterns, add_embeddings, add_indices,
        all_source_types, all_episode_ids,
    )

    return _CategoryResult(results=tuple(all_results), added=len(add_patterns), updated=updated)


def _store_new_patterns(
    knowledge: KnowledgeStore,
    source_date: Optional[str],
    add_patterns: Sequence[str],
    add_embeddings: Sequence[Optional[np.ndarray]],
    add_indices: Sequence[int],
    all_source_types: Sequence[str],
    all_episode_ids: Sequence[List[str]],
) -> None:
    """Persist deduped patterns with ADR-0021 provenance."""
    ts = now_iso()
    for pattern, emb, src_idx in zip(
        add_patterns, add_embeddings, add_indices
    ):
        emb_list: Optional[List[float]] = (
            [float(x) for x in emb] if emb is not None else None
        )
        source_type = all_source_types[src_idx] if src_idx < len(all_source_types) else "unknown"
        episode_ids = all_episode_ids[src_idx] if src_idx < len(all_episode_ids) else []
        provenance = {
            "source_type": source_type,
            "source_episode_ids": episode_ids,
            "pipeline_version": "distill@0.60",
        }
        knowledge.add_learned_pattern(
            pattern,
            source=source_date,
            embedding=emb_list,
            provenance=provenance,
            valid_from=ts,
        )
        logger.info("Added pattern (source=%s): %s", source_type, pattern[:80])


def _dedup_patterns(
    new_patterns: Sequence[str],
    new_embeddings: Sequence[Optional[np.ndarray]],
    existing_patterns: Sequence[dict],
    *,
    mutate_existing: bool = True,
) -> Tuple[
    List[str],
    List[Optional[np.ndarray]],
    List[int],
    int,
    int,
]:
    """Remove duplicates by comparing new patterns against existing ones.

    Returns ``(add_patterns, add_embeddings, add_indices, skip_count,
    update_count)``.
    - SKIP: cosine >= SIM_DUPLICATE (near-exact duplicate)
    - UPDATE: cosine >= SIM_UPDATE against existing → soft-invalidate the old
      pattern (``valid_until = now``) and ADD the new pattern. The old row is
      kept for audit / replay (ADR-0021 bitemporal) rather than mutated in
      place. ADR-0056: no importance boost — the LLM rating was retired and
      extraction weight is pure time decay, so the re-observed pattern simply
      re-enters with a fresh timestamp.
    - ADD: cosine <  SIM_UPDATE against everything

    Patterns whose embedding is None (Ollama failure) are always ADD'd
    so distillation degrades gracefully when the embed model is down.
    Existing patterns without embeddings are ignored as dedup candidates.
    """
    add_patterns: List[str] = []
    add_embeddings: List[Optional[np.ndarray]] = []
    add_indices: List[int] = []
    skip_count = 0
    update_count = 0

    ts = now_iso()

    existing_with_emb = _live_embedded(existing_patterns)

    for input_idx, (new_text, new_emb) in enumerate(
        zip(new_patterns, new_embeddings)
    ):
        if new_emb is None:
            add_patterns.append(new_text)
            add_embeddings.append(None)
            add_indices.append(input_idx)
            continue

        best_existing_sim, best_existing_pat = _best_existing_sim(new_emb, existing_with_emb)
        best_new_sim, best_new_idx = _best_accepted_sim(new_emb, add_embeddings)

        action = _dedup_action(best_existing_sim, best_existing_pat, best_new_sim, best_new_idx)
        if action == "skip":
            skip_count += 1
            logger.info("SKIP (%.2f): %s", max(best_existing_sim, best_new_sim), new_text[:60])
        elif action == "update":
            # ADR-0021: soft-invalidate old, keep row for audit, and ADD the
            # re-observed pattern with a fresh timestamp (no importance boost,
            # ADR-0056).
            assert best_existing_pat is not None  # guaranteed by _dedup_action
            if mutate_existing:
                best_existing_pat["valid_until"] = ts
            add_patterns.append(new_text)
            add_embeddings.append(new_emb)
            add_indices.append(input_idx)
            update_count += 1
            logger.debug("UPDATE (%.2f): invalidate + re-add: %s",
                         best_existing_sim, new_text[:60])
        elif action == "skip_new":
            skip_count += 1
            logger.debug("SKIP-NEW (%.2f): %s", best_new_sim, new_text[:60])
        else:
            add_patterns.append(new_text)
            add_embeddings.append(new_emb)
            add_indices.append(input_idx)

    return (
        add_patterns, add_embeddings,
        add_indices, skip_count, update_count,
    )


def _live_embedded(existing_patterns: Sequence[dict]) -> List[Tuple[Dict, np.ndarray]]:
    """Pre-compute existing embeddings (live patterns with embeddings only)."""
    existing_with_emb: List[Tuple[Dict, np.ndarray]] = []
    for p in existing_patterns:
        if not is_live(p):
            continue  # bitemporally invalidated — ignore
        emb = p.get("embedding")
        if isinstance(emb, list):
            existing_with_emb.append((p, np.asarray(emb, dtype=np.float32)))
    return existing_with_emb


def _best_existing_sim(
    new_emb: np.ndarray, existing_with_emb: Sequence[Tuple[Dict, np.ndarray]]
) -> Tuple[float, Optional[Dict]]:
    """Best cosine similarity vs existing patterns."""
    best_sim = -1.0
    best_pat: Optional[Dict] = None
    for pat_dict, pat_emb in existing_with_emb:
        sim = cosine(new_emb, pat_emb)
        if sim > best_sim:
            best_sim = sim
            best_pat = pat_dict
    return best_sim, best_pat


def _best_accepted_sim(
    new_emb: np.ndarray, add_embeddings: Sequence[Optional[np.ndarray]]
) -> Tuple[float, int]:
    """Best cosine similarity vs already-accepted new patterns (cross-batch)."""
    best_sim = -1.0
    best_idx = -1
    for idx, accepted_emb in enumerate(add_embeddings):
        if accepted_emb is None:
            continue
        sim = cosine(new_emb, accepted_emb)
        if sim > best_sim:
            best_sim = sim
            best_idx = idx
    return best_sim, best_idx


def _dedup_action(
    best_existing_sim: float,
    best_existing_pat: Optional[Dict],
    best_new_sim: float,
    best_new_idx: int,
) -> str:
    """Decide: ``skip`` / ``update`` existing / ``skip_new`` (boost in batch) / ``add``."""
    if best_existing_sim >= SIM_DUPLICATE or best_new_sim >= SIM_DUPLICATE:
        return "skip"
    if best_existing_sim >= SIM_UPDATE and best_existing_pat is not None and best_existing_sim >= best_new_sim:
        return "update"
    if best_new_sim >= SIM_UPDATE and best_new_idx >= 0:
        return "skip_new"
    return "add"


def _is_valid_pattern(pattern: str) -> bool:
    """Decision gate: is this pattern worth storing?

    Rejects labels, keywords, and fragments that aren't actionable patterns.
    """
    if len(pattern) < 30:
        return False
    if pattern.count(" ") < 3:
        return False
    return True


def summarize_record(record_type: str, data: dict) -> str:
    """Create a one-line summary of an episode record."""
    if record_type == "interaction":
        direction = data.get("direction", "?")
        agent = data.get("agent_name", "unknown")
        content = data.get("content_summary", "")[:80]
        return f"{direction} with {agent}: {content}"
    elif record_type == "post":
        title = data.get("title", data.get("topic_summary", "untitled"))
        return f"posted: {title}"
    # type="insight" has no branch: retired by ADR-0052 and filtered out at
    # the distill read path; an insight record reaching here is a bug, and
    # the "" fallthrough keeps it out of any prompt.
    elif record_type == "activity":
        action = data.get("action", "unknown")
        target = data.get("target_agent", data.get("post_id", ""))
        base = f"{action} {target}".strip()
        # ADR-0045: the behavioural fact and the pre-action internal note
        # coexist on one line so distill sees "what happened, and what was
        # felt about it" — the dual register ADR-0038 designed for, now with
        # real first-person supply instead of post-hoc reconstruction.
        note = data.get("internal_note", "")
        return f"{base} — noticed: {note}" if note else base
    elif record_type == "dialogue":
        role = data.get("role", "?")
        turn = data.get("turn", "?")
        content = data.get("content", "")[:80]
        seed_marker = " [seed]" if data.get("seed") else ""
        return f"{role} turn {turn}{seed_marker}: {content}"
    return ""
