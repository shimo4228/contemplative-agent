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
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Literal, Optional, Sequence, Tuple, Union

import numpy as np

from . import episode_render, pattern_dedup
from ._io import now_iso, strip_code_fence
from .embeddings import embed_texts

# Public re-exports (ADR-0079 Phase 3b): render_episode / summarize_record
# are public names of this module; their implementation lives in
# .episode_render.
from .episode_render import render_episode as render_episode, summarize_record as summarize_record
from .knowledge_store import (
    effective_importance,
    epistemic_counts_for,
    pattern_id,
)
from .llm import (
    generate,
    generate_full,
    get_distill_system_prompt,
    validate_identity_content,
)
from .memory import EpisodeLog, KnowledgeStore
from .prompts import (
    DISTILL_EPISODE_PROMPT,
    IDENTITY_DISTILL_PROMPT,
)
from .view_metrics import ViewLookup, instrument_lines
from .views import ViewRegistry

logger = logging.getLogger(__name__)


# Structured-output schema for the per-episode distill call. Constrains the
# model to emit ``{"patterns": [...]}`` at the token level (Ollama format=),
# removing the malformed-JSON risk the 2-step bullet fallback used to absorb.
_PATTERNS_SCHEMA = {
    "type": "object",
    "properties": {"patterns": {"type": "array", "items": {"type": "string"}}},
    "required": ["patterns"],
}

# Per-episode abstain reason codes (ADR-0075: failures carry a reason code,
# no silent fallback; introduced by the ADR-0077 chaos-TDD pilot). Emitted in
# machine-greppable WARNING lines ("reason=<code>") and tallied per-reason in
# the distill summary. Literal-typed so a typo at a future call site fails
# type check instead of silently minting a new reason.
AbstainReason = Literal["llm_none", "empty_render", "shape_violation"]
ParseMode = Literal["json", "bullet_fallback", "shape_violation"]
ABSTAIN_LLM_NONE: AbstainReason = "llm_none"  # generate() returned None (fault or drop)
ABSTAIN_EMPTY_RENDER: AbstainReason = "empty_render"  # episode rendered to an empty prompt
ABSTAIN_SHAPE_VIOLATION: AbstainReason = "shape_violation"  # valid JSON, wrong shape

# Embedding-based dedup thresholds live in ``core/thresholds.py`` since
# ADR-0035 PR2; re-exported under the historical names here so existing call
# sites keep working without ad-hoc late imports.
from .thresholds import (  # noqa: E402 — module-level by design
    DEDUP_IMPORTANCE_FLOOR,
)


def distill(
    days: int = 1,
    dry_run: bool = False,
    episode_log: Optional[EpisodeLog] = None,
    knowledge_store: Optional[KnowledgeStore] = None,
    log_files: Optional[List[Path]] = None,
    instrument_views: Optional[ViewLookup] = None,
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
        instrument_views: Optional view lookup for the dry-run view-supply
            instrument; the diversity instrument runs without it
            (``view_metrics`` — read-only observability, never a gate).

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
    # there is no ingest-time noise gate. Downstream, the two view-querying
    # consumers (distill-identity / amend-constitution) keep low-relevance
    # patterns out via their own view thresholds at query time (ADR-0031),
    # and insight skips legacy ``gated`` rows. (The orphaned ``noise`` view
    # seed this comment used to point at was pruned in ADR-0073.)
    rich = [r for r in records if episode_render._is_rich_episode(r)]
    if not rich:
        msg = "No engagement episodes (comment/reply/post) for distillation."
        logger.info(msg)
        return msg
    logger.info(
        "Distilling %d engagement episodes (filtered from %d records)",
        len(rich),
        len(records),
    )

    # Determine source date range from the in-scope episodes. read_range
    # returns newest-day-first, so the oldest timestamp is last — render the
    # range oldest~newest for readable provenance.
    timestamps = sorted(r.get("ts", "")[:10] for r in rich if r.get("ts"))
    source_date = timestamps[0] if timestamps else None
    if timestamps and timestamps[0] != timestamps[-1]:
        source_date = f"{timestamps[0]}~{timestamps[-1]}"

    result = _distill_episodes(rich, knowledge, source_date, dry_run, instrument_views)

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
            "Distill complete: %d added, %d updated",
            result.added,
            result.updated,
        )

    return "\n\n".join(result.results)


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
    # ADR-0069: reasoning trace behind the identity (distill-identity runs
    # think-ON; this is the manual command, distinct from the autonomous
    # episode distill which stays think-OFF). None when think was off.
    thinking: Optional[str] = None


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
            "distill_identity requires a ViewRegistry since ADR-0019. Pass a ViewRegistry instance."
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

    out = generate_full(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        caller="distill.identity",
        think=True,
        drop_truncated=True,
    )
    if out is None or out.text is None:
        msg = "LLM failed to generate identity revision."
        logger.warning(msg)
        return msg

    # Clean up: strip empty lines and preamble
    lines = [line.strip() for line in out.text.strip().splitlines() if line.strip()]
    new_identity = "\n".join(lines)

    # Validate against forbidden patterns before returning. On failure, return a
    # distinct error message (the str arm of the return contract) rather than
    # echoing the rejected/tainted body — which a caller (and the CLI, which
    # prints any str result) would otherwise surface as if it were valid output.
    # Mirrors the hard-drop behaviour of the sibling insight / rules_distill pipelines.
    if not validate_identity_content(new_identity):
        logger.warning("Generated identity failed validation; discarding")
        return "Generated identity failed forbidden-pattern validation; discarded."

    if not identity_path:
        return new_identity

    return IdentityResult(
        text=new_identity,
        target_path=identity_path,
        pattern_ids=tuple(pattern_id(p) for p in matched),
        epistemic_counts=epistemic_counts_for(matched),
        thinking=out.thinking,
    )


@dataclass(frozen=True)
class _DistillOutcome:
    """What one distill pass produced: rendered results plus store deltas.

    Named for categories back when distillation ran per category; ADR-0019
    retired that axis and ADR-0060 made the unit a single episode, so the old
    name described a dimension the pipeline no longer has.
    """

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


@dataclass(frozen=True)
class _PatternProvenance:
    """Per-pattern provenance from the single episode it was distilled from.

    Replaces the index-aligned ``all_patterns`` / ``all_source_types`` /
    ``all_episode_ids`` parallel arrays with one record per pattern
    (ADR-0021/0060): the pattern text plus the source kind and episode ids
    of its originating episode.
    """

    text: str
    source_type: str
    episode_ids: Tuple[str, ...]


# Sentinel distinguishing "not JSON at all" from a parsed JSON null, which
# is a legitimate (wrong-shaped) JSON value and must abstain, not bullet-scan.
_JSON_PARSE_FAILED = object()


def _parse_patterns(raw: str) -> Tuple[List[str], ParseMode]:
    """Parse per-episode LLM output into ``(patterns, parse_mode)``.

    parse_mode is one of:

    - ``"json"`` — the structured-output ``{"patterns": [str, ...]}`` shape.
    - ``"shape_violation"`` — syntactically valid JSON deviating from that
      shape (top-level array/scalar/null, missing or non-list ``patterns``,
      or a non-string list item — the schema says ``items: string``). Yields
      no patterns: bullet-scanning a JSON body almost always returns [],
      which is indistinguishable from a legitimate empty extraction
      (ADR-0077 F3; previously a silent fallback).
    - ``"bullet_fallback"`` — non-JSON body scanned for ``- `` bullets. Kept
      as graceful degradation for backends that ignore ``format=``
      (bug-audit 2026-07-06 H2), now tagged for observability.
    """
    json_text = strip_code_fence(raw)
    try:
        parsed: object = json_mod.loads(json_text)
    except (json_mod.JSONDecodeError, TypeError):
        parsed = _JSON_PARSE_FAILED
    if parsed is not _JSON_PARSE_FAILED:
        if (
            isinstance(parsed, dict)
            and isinstance(parsed.get("patterns"), list)
            and all(isinstance(item, str) for item in parsed["patterns"])
        ):
            patterns = [item.strip() for item in parsed["patterns"] if item.strip()]
            return patterns, "json"
        # Valid JSON but not the {"patterns": [str, ...]} shape — never
        # iterate it (a str iterates char-wise, a dict key-wise) and never
        # bullet-scan it.
        logger.warning(
            "Distill output shape violation (top-level %s); abstaining",
            type(parsed).__name__ if parsed is not None else "null",
        )
        return [], "shape_violation"
    # Non-JSON body: bullet-point fallback (audit H2).
    raw_patterns: List[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("- "):
            pattern = line[2:].strip()
            if pattern:
                raw_patterns.append(pattern)
    if raw_patterns:
        logger.warning(
            "Distill output was not JSON; recovered %d pattern(s) (parse=bullet_fallback)",
            len(raw_patterns),
        )
    return raw_patterns, "bullet_fallback"


def _distill_one(record: Dict) -> Union[_BatchOutput, AbstainReason]:
    """Distill one engagement episode; ``_BatchOutput`` or an abstain reason.

    ADR-0060: a single LLM call over the rich, world-grounded render of one
    episode. Structured output (``format=``) constrains the model to the
    ``{"patterns": [...]}`` shape, but a backend can still emit valid JSON
    of the wrong shape — that abstains with ``reason=shape_violation``
    instead of silently degrading (ADR-0077 F3). Failures return an
    ``ABSTAIN_*`` reason code, never a bare None, so the caller tallies
    them per reason (ADR-0075). Per-episode provenance (one episode's
    source kind and timestamp) replaces the per-batch summary.
    """
    record_type = record.get("type", "unknown")
    data = record.get("data", {}) or {}
    ts = record.get("ts", "")
    rendered = episode_render.render_episode(record_type, data)
    if not rendered:
        logger.warning("Episode distill abstained: reason=%s ts=%s", ABSTAIN_EMPTY_RENDER, ts[:16])
        return ABSTAIN_EMPTY_RENDER

    source_type = episode_render._derive_source_type([record])
    prompt = DISTILL_EPISODE_PROMPT.format(episode=rendered)

    result = generate(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        format=_PATTERNS_SCHEMA,
        caller="distill.episode",
        drop_truncated=True,
    )
    if result is None:
        logger.warning("Episode distill abstained: reason=%s ts=%s", ABSTAIN_LLM_NONE, ts[:16])
        return ABSTAIN_LLM_NONE

    raw_patterns, parse_mode = _parse_patterns(result)
    if parse_mode == "shape_violation":
        logger.warning(
            "Episode distill abstained: reason=%s ts=%s", ABSTAIN_SHAPE_VIOLATION, ts[:16]
        )
        return ABSTAIN_SHAPE_VIOLATION

    # Decision gate: reject low-quality patterns
    patterns = [p for p in raw_patterns if _is_valid_pattern(p)]
    rejected = len(raw_patterns) - len(patterns)

    logger.info(
        "Episode %s (prompt %d chars) → %d patterns (%d rejected)",
        ts[:16],
        len(prompt),
        len(patterns),
        rejected,
    )
    return _BatchOutput(
        refined=result,
        patterns=tuple(patterns),
        source_type=source_type,
        episode_ids=(ts,) if ts else (),
    )


@dataclass(frozen=True)
class _ExtractResult:
    """Per-episode LLM extraction, before anything is embedded or stored."""

    provenance: tuple[_PatternProvenance, ...]
    results: tuple[str, ...]
    abstained: Counter[str]


@dataclass(frozen=True)
class _DedupResult:
    """What survives dedup, and what dedup did to the existing pool."""

    add_patterns: tuple[str, ...]
    add_embeddings: tuple[Optional[np.ndarray], ...]
    add_indices: tuple[int, ...]
    skipped: int
    updated: int


def _extract_patterns(records: List[Dict]) -> _ExtractResult:
    """One LLM call per episode; collect patterns and tally abstains.

    ADR-0060: no fixed-size batching and no noise gate — each episode is
    distilled on its own, so a failure costs one episode rather than a batch.
    """
    provenance: List[_PatternProvenance] = []
    all_results: List[str] = []
    abstained: Counter[str] = Counter()

    for record in records:
        out = _distill_one(record)
        if isinstance(out, str):
            abstained[out] += 1
            continue
        all_results.append(out.refined)
        # ADR-0021/0060: provenance is per-episode — each pattern carries the
        # source kind and episode ids of the single episode it came from.
        for pattern in out.patterns:
            provenance.append(
                _PatternProvenance(
                    text=pattern,
                    source_type=out.source_type,
                    episode_ids=out.episode_ids,
                )
            )

    # Bug-audit 2026-07-06 round 2 (observability candidate 1) + ADR-0077:
    # a partial Ollama flake drops episodes at the per-episode level — one
    # aggregate line, tallied per abstain reason, distinguishes a backend
    # fault burst from a parse-layer problem and from a clean low-yield run.
    # The episodes are not retried; their content is only reachable in a
    # future run if the window still covers them.
    if abstained:
        logger.warning(
            "Episode distill summary: %d/%d episodes abstained "
            "(llm_none=%d shape_violation=%d empty_render=%d); "
            "their patterns are lost for this run",
            sum(abstained.values()),
            len(records),
            abstained[ABSTAIN_LLM_NONE],
            abstained[ABSTAIN_SHAPE_VIOLATION],
            abstained[ABSTAIN_EMPTY_RENDER],
        )
    else:
        logger.info("Episode distill summary: all %d episodes produced output", len(records))

    return _ExtractResult(
        provenance=tuple(provenance),
        results=tuple(all_results),
        abstained=abstained,
    )


def _embed_patterns(patterns: Sequence[str]) -> List[Optional[np.ndarray]]:
    """Bulk-embed the extracted patterns (ADR-0019).

    Degrades to all-None rather than failing the run: without embeddings dedup
    falls back to storing everything, which is worse than deduping but better
    than losing the distillation entirely. The reason code is logged so a
    degraded run is distinguishable offline from a clean one.
    """
    arr = embed_texts(list(patterns))
    if arr is None or arr.shape[0] != len(patterns):
        logger.warning(
            "Failed to embed %d new patterns; storing without embedding "
            "(dedup degraded, reason=embed_failed)",
            len(patterns),
        )
        return [None] * len(patterns)
    return list(arr)  # iterating a 2-D ndarray yields its rows


def _dedup_against_live_pool(
    knowledge: KnowledgeStore,
    patterns: Sequence[str],
    embeddings: Sequence[Optional[np.ndarray]],
    *,
    mutate_existing: bool,
) -> _DedupResult:
    """Compare new patterns against the live pool.

    ADR-0026: dedup scope is the full live pool. Cross-axis overlap is
    acceptable — the semantic coordinate is shared regardless of which view a
    pattern is routed through at query time.

    ``mutate_existing`` is passed explicitly rather than derived from a dry-run
    flag in scope: this is the one step that writes to the existing pool
    (bitemporal soft-invalidation), so the caller has to say so out loud.
    """
    # is_live gate (valid_until, ADR-0051) is enforced inside
    # pattern_dedup._dedup_patterns; this pre-filter exists for the decay-floor log.
    # ADR-0056: effective_importance is pure time decay, so the floor now
    # drops any pattern older than ~58 days from the dedup comparison scope,
    # letting a re-observed insight re-enter as a fresh record (ADR-0053 §4).
    existing_patterns = list(knowledge.get_raw_patterns())
    pre_filter = len(existing_patterns)
    existing_patterns = [
        p for p in existing_patterns if effective_importance(p) >= DEDUP_IMPORTANCE_FLOOR
    ]
    if pre_filter > len(existing_patterns):
        logger.info(
            "Dedup scope: %d/%d patterns (decay floor %.2f)",
            len(existing_patterns),
            pre_filter,
            DEDUP_IMPORTANCE_FLOOR,
        )

    (
        add_patterns,
        add_embeddings,
        add_indices,
        skipped,
        updated,
    ) = pattern_dedup._dedup_patterns(
        list(patterns),
        list(embeddings),
        existing_patterns,
        mutate_existing=mutate_existing,
    )
    return _DedupResult(
        add_patterns=tuple(add_patterns),
        add_embeddings=tuple(add_embeddings),
        add_indices=tuple(add_indices),
        skipped=skipped,
        updated=updated,
    )


def _instrument_dry_run(
    extracted: _ExtractResult,
    deduped: _DedupResult,
    pattern_count: int,
    instrument_views: Optional[ViewLookup],
) -> None:
    """Log what a real run would have written, plus the read-only instruments."""
    logger.info(
        "Dry run — %d patterns found, %d skipped, %d would soft-invalidate",
        pattern_count,
        deduped.skipped,
        deduped.updated,
    )
    # Read-only composition instruments over the would-be-ADDED set —
    # post-dedup, so skipped duplicates are not counted (codex review
    # 2026-07-03 P3). View supply needs the registry, diversity and
    # grounding run regardless. Observability only — never a gate.
    batch = [
        {
            "pattern": text,
            "embedding": emb.tolist() if emb is not None else None,
            "provenance": {"source_type": extracted.provenance[idx].source_type},
        }
        for text, emb, idx in zip(
            deduped.add_patterns, deduped.add_embeddings, deduped.add_indices, strict=True
        )
    ]
    for line in instrument_lines(batch, instrument_views):
        logger.info("dry-run instrument: %s", line)


def _distill_episodes(
    records: List[Dict],
    knowledge: KnowledgeStore,
    source_date: Optional[str],
    dry_run: bool,
    instrument_views: Optional[ViewLookup] = None,
) -> _DistillOutcome:
    """Distill each engagement episode individually, then dedup + store.

    Four stages: extract (one LLM call per episode) -> embed -> dedup against
    the live pool -> persist, or instrument and stop when ``dry_run``. A
    re-observed pattern from a recurring episode is caught at the pattern level
    (SKIP / UPDATE) in the dedup stage, so no episode-level pre-clustering is
    needed (ADR-0060).
    """
    logger.info("Distilling %d episodes individually", len(records))

    extracted = _extract_patterns(records)
    if not extracted.provenance:
        return _DistillOutcome(results=extracted.results, added=0, updated=0)

    all_patterns = [pp.text for pp in extracted.provenance]
    embeddings = _embed_patterns(all_patterns)
    deduped = _dedup_against_live_pool(
        knowledge,
        all_patterns,
        embeddings,
        mutate_existing=not dry_run,
    )

    if dry_run:
        _instrument_dry_run(extracted, deduped, len(all_patterns), instrument_views)
        return _DistillOutcome(results=extracted.results, added=0, updated=0)

    if deduped.updated:
        logger.info(
            "Dedup: %d soft-invalidated (bitemporal) and replaced with new patterns",
            deduped.updated,
        )

    _store_new_patterns(
        knowledge,
        source_date,
        deduped.add_patterns,
        deduped.add_embeddings,
        deduped.add_indices,
        extracted.provenance,
    )

    return _DistillOutcome(
        results=extracted.results,
        added=len(deduped.add_patterns),
        updated=deduped.updated,
    )


def _store_new_patterns(
    knowledge: KnowledgeStore,
    source_date: Optional[str],
    add_patterns: Sequence[str],
    add_embeddings: Sequence[Optional[np.ndarray]],
    add_indices: Sequence[int],
    provenance: Sequence[_PatternProvenance],
) -> None:
    """Persist deduped patterns with ADR-0021 provenance."""
    ts = now_iso()
    for pattern, emb, src_idx in zip(add_patterns, add_embeddings, add_indices, strict=True):
        emb_list: Optional[List[float]] = [float(x) for x in emb] if emb is not None else None
        source_type = provenance[src_idx].source_type
        episode_ids = list(provenance[src_idx].episode_ids)
        provenance_meta = {
            "source_type": source_type,
            "source_episode_ids": episode_ids,
            "pipeline_version": "distill@0.60",
        }
        knowledge.add_learned_pattern(
            pattern,
            source=source_date,
            embedding=emb_list,
            provenance=provenance_meta,
            valid_from=ts,
        )
        logger.info("Added pattern (source=%s): %s", source_type, pattern[:80])


# Known extraction-failure register (validity check, not a value filter):
# the model is instructed to return an empty list when an episode carries
# nothing durable (distill_episode.md), but occasionally narrates the
# failure instead — a statement about the distillation task, not an
# observation about the agent (§B3 2026-07-03: one reached self_reflection
# rank 16). Episode/task-referential phrases only: bare phrases such as
# "lack sufficient context" or "cannot identify a pattern" are excluded
# because a genuine first-person recognition can use them ("I noticed I
# lack sufficient context before making a claim" — codex-review P2,
# 2026-07-03); "extract" and "generalizable" are the task's own
# vocabulary, not the agent's self-vocabulary.
_EXTRACTION_FAILURE_PHRASES: Tuple[str, ...] = (
    "events appear isolated",
    "the episode does not contain",
    "the episode lacks",
    "the episodes lack",
    "unable to extract a pattern",
    "cannot extract a pattern",
    "no generalizable pattern",
    "nothing generalizable",
)


def _is_valid_pattern(pattern: str) -> bool:
    """Decision gate: is this pattern worth storing?

    Rejects labels, keywords, and fragments that aren't actionable patterns,
    plus extraction-failure meta-statements (see
    ``_EXTRACTION_FAILURE_PHRASES``).
    """
    if len(pattern) < 30:
        return False
    if pattern.count(" ") < 3:
        return False
    lowered = pattern.lower()
    for phrase in _EXTRACTION_FAILURE_PHRASES:
        if phrase in lowered:
            logger.info(
                "Rejected extraction-failure meta-statement (%r): %.60s",
                phrase,
                pattern,
            )
            return False
    return True
