"""Sleep-time memory distillation: extract patterns from episode logs.

ADR-0009: dedup is embedding-cosine based; subcategorisation has been
removed (replaced by views, which materialise grouping at query time).

ADR-0026 (Phase 2): Step 0 classification is binary — ``gated`` (noise
centroid match → excluded from distillation) vs ``kept`` (everything
else, funneled through a single distill pipeline). The legacy
constitutional/uncategorized split has been collapsed; constitutional
routing now happens at query time via ``ViewRegistry.find_by_view``
(see ``core/constitution.py``).
"""

from __future__ import annotations

import hashlib
import json as json_mod
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

from ._io import append_jsonl_restricted, now_iso, strip_code_fence
from .embeddings import cosine, embed_texts
from .knowledge_store import (
    effective_importance,
    epistemic_counts_for,
    is_live,
    pattern_id,
)
from .llm import generate, get_distill_system_prompt, validate_identity_content
from .memory import EpisodeLog, KnowledgeStore
from .prompts import (
    DISTILL_PROMPT,
    DISTILL_REFINE_PROMPT,
    IDENTITY_DISTILL_PROMPT,
)
from .views import ViewRegistry

logger = logging.getLogger(__name__)

BATCH_SIZE = 30

# Embedding-based dedup + noise thresholds live in ``core/thresholds.py``
# since ADR-0035 PR2; re-exported under the historical names here so
# existing call sites and prompt templates that reference them keep
# working without ad-hoc late imports.
from .thresholds import (  # noqa: E402 — module-level by design
    DEDUP_IMPORTANCE_FLOOR,
    NOISE_THRESHOLD,
    SIM_DUPLICATE,
    SIM_UPDATE,
)


def distill(
    days: int = 1,
    dry_run: bool = False,
    episode_log: Optional[EpisodeLog] = None,
    knowledge_store: Optional[KnowledgeStore] = None,
    log_files: Optional[List[Path]] = None,
    view_registry: Optional[ViewRegistry] = None,
    log_dir: Optional[Path] = None,
) -> str:
    """Distill recent episodes into learned patterns.

    New patterns are embedded inline and dedup uses cosine similarity
    against existing same-category patterns. The legacy LLM-based
    subcategorize step has been removed (ADR-0009); grouping is now
    query-time via views.

    Args:
        days: Number of days of episodes to process.
        dry_run: If True, return results without writing.
        episode_log: EpisodeLog instance (uses default if None).
        knowledge_store: KnowledgeStore instance (uses default if None).
        log_files: Explicit JSONL file paths to process (overrides days).
        view_registry: ViewRegistry for Step 0 noise gating.
        log_dir: Base directory for noise JSONL output (ADR-0027 Phase 1).
            None disables the writer (dry-run / tests).

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

    # Step 0: Classify episodes via embedding centroid distance (ADR-0026:
    # binary gated — noise centroid match is excluded, everything else is
    # kept). Per-category routing moved to query time (views). ADR-0027
    # Phase 1: gated episodes are appended to noise-*.jsonl as seeds
    # unless log_dir is None (dry-run / tests).
    classified = _classify_episodes(
        records,
        view_registry=view_registry,
        log_dir=None if dry_run else log_dir,
    )
    if classified.gated:
        logger.info("Step 0: %d noise episodes gated out of distillation", len(classified.gated))
    logger.info(
        "Step 0: %d kept, %d gated", len(classified.kept), len(classified.gated),
    )

    # Determine source date range from records
    timestamps = [r.get("ts", "")[:10] for r in records if r.get("ts")]
    source_date = timestamps[0] if timestamps else None
    if timestamps and timestamps[0] != timestamps[-1]:
        source_date = f"{timestamps[0]}~{timestamps[-1]}"

    all_results: List[str] = []
    total_added = 0
    total_updated = 0

    # ADR-0026 Phase 3: single distill pass over all kept records.
    if classified.kept:
        cat_results = _distill_category(
            list(classified.kept), knowledge, source_date, dry_run,
        )
        all_results.extend(cat_results.results)
        total_added += cat_results.added
        total_updated += cat_results.updated

    if not dry_run and (total_added or total_updated):
        knowledge.save()
        logger.info("Distill complete: %d added, %d updated", total_added, total_updated)

    return "\n\n".join(all_results)


def enrich(
    knowledge_store: KnowledgeStore,
    dry_run: bool = False,
) -> int:
    """No-op since ADR-0009: subcategorisation is now query-time via views.

    Kept as a stable entry point so the ``enrich`` CLI subcommand is
    callable; it now reports zero work.
    """
    _ = (knowledge_store, dry_run)
    logger.info("enrich is a no-op since ADR-0009.")
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
    """Distill knowledge into an updated identity description.

    Reads the current identity and accumulated knowledge, then asks the LLM
    to write a brief self-description reflecting the agent's actual experience.

    File writing is the caller's responsibility (ADR-0012 approval gate).

    Args:
        knowledge_store: KnowledgeStore instance (uses default if None).
        identity_path: Path to identity.md file.
        view_registry: ViewRegistry used to retrieve self-reflection
            patterns via embedding cosine. Required for ADR-0009 routing;
            patterns lacking embeddings are skipped.

    Returns:
        IdentityResult on success, or error message string.
    """
    knowledge = knowledge_store or KnowledgeStore()
    knowledge.load()

    if view_registry is None:
        msg = (
            "distill_identity requires a ViewRegistry since ADR-0009. "
            "Pass a ViewRegistry instance."
        )
        logger.warning(msg)
        return msg

    # Identity is distilled from self-reflection patterns only. Routing is
    # done via the "self_reflection" view's embedding cosine (ADR-0009,
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

    current_identity = ""
    if identity_path and identity_path.exists():
        current_identity = identity_path.read_text(encoding="utf-8").strip()

    prompt = IDENTITY_DISTILL_PROMPT.format(
        current_identity=current_identity or "(no prior identity)",
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




@dataclass(frozen=True)
class _ClassifiedRecords:
    """Records grouped by the ADR-0026 binary gate.

    ``gated`` episodes are noise-centroid matches excluded from
    distillation; ``kept`` episodes proceed through the single distill
    pipeline. Per-topic routing (constitutional / self_reflection /
    communication / ...) happens at query time via
    ``ViewRegistry.find_by_view``, not via a persisted category.
    """
    kept: Tuple[Dict, ...]
    gated: Tuple[Dict, ...]


def _classify_episodes(
    records: List[Dict],
    view_registry: Optional[ViewRegistry] = None,
    log_dir: Optional[Path] = None,
) -> _ClassifiedRecords:
    """Step 0: Binary gate via noise-centroid distance (ADR-0026).

    Each episode summary is bulk-embedded once and compared against the
    ``noise`` view centroid:

      - noise_sim >= NOISE_THRESHOLD → gated (excluded from distillation)
      - else                          → kept

    A missing view_registry or unavailable centroid degrades safely to
    "all kept" (no LLM fallback, no gating). The legacy three-way
    classify path (constitutional / uncategorized / noise) has been
    collapsed — constitutional routing moved to the insight read path
    and to ``amend_constitution`` via views.

    ADR-0027 Phase 1: when ``log_dir`` is provided, gated episodes are
    appended to ``noise-YYYY-MM-DD.jsonl`` as seeds for later
    re-classification. ``log_dir=None`` keeps the writer disabled (used
    by dry-run and tests).
    """
    if not records:
        return _ClassifiedRecords(kept=(), gated=())

    if view_registry is None:
        logger.warning(
            "_classify_episodes called without view_registry — "
            "all episodes will be kept (ADR-0009 requires views for gating)"
        )
        return _ClassifiedRecords(kept=tuple(records), gated=())

    summaries: List[str] = []
    for r in records:
        record_type = r.get("type", "unknown")
        data = r.get("data", {})
        ts = r.get("ts", "")
        summary = summarize_record(record_type, data)
        episode_line = (
            f"[{ts[:16]}] {record_type}: {summary}"
            if summary
            else f"[{ts[:16]}] {record_type}: (no summary)"
        )
        summaries.append(episode_line)

    embeddings_arr = embed_texts(summaries)
    if embeddings_arr is None or embeddings_arr.shape[0] != len(records):
        logger.warning(
            "Failed to embed %d episodes for classification — defaulting to kept",
            len(records),
        )
        return _ClassifiedRecords(kept=tuple(records), gated=())

    noise_centroid = view_registry.get_centroid("noise")

    kept: List[Dict] = []
    gated: List[Dict] = []
    gated_log_entries: List[Tuple[Dict, float, str]] = []

    for idx, r in enumerate(records):
        emb = embeddings_arr[idx]
        if noise_centroid is not None:
            noise_sim = cosine(emb, noise_centroid)
        else:
            noise_sim = 0.0

        if noise_sim >= NOISE_THRESHOLD:
            gated.append(r)
            gated_log_entries.append((r, float(noise_sim), summaries[idx]))
        else:
            kept.append(r)

        if (idx + 1) % 50 == 0:
            logger.info("Classified %d/%d episodes", idx + 1, len(records))

    if log_dir is not None and gated_log_entries:
        _write_noise_log(log_dir, view_registry, gated_log_entries)

    return _ClassifiedRecords(kept=tuple(kept), gated=tuple(gated))


def _view_centroids_hash(view_registry: Optional[ViewRegistry]) -> str:
    """8-char SHA-256 prefix of all view centroids (ADR-0027 Phase 1).

    Lets Phase 2 re-classify identify which noise records were written
    under which centroid configuration. Views with unavailable centroids
    are skipped — their absence is part of the fingerprint.
    """
    if view_registry is None:
        return "none"
    digest = hashlib.sha256()
    for name in sorted(view_registry.names()):
        centroid = view_registry.get_centroid(name)
        if centroid is None:
            continue
        digest.update(name.encode("utf-8"))
        digest.update(centroid.tobytes())
    return digest.hexdigest()[:8]


def _write_noise_log(
    log_dir: Path,
    view_registry: Optional[ViewRegistry],
    entries: List[Tuple[Dict, float, str]],
) -> None:
    """Append noise-gated episodes to ``noise-YYYY-MM-DD.jsonl`` (ADR-0027 Phase 1).

    Records are append-only seeds: Phase 2 re-classifies them against
    updated centroids, Phase 3 promotes high-salience ones. Gated
    episodes are still excluded from distillation — the writer only
    removes the silent-discard behaviour.
    """
    today = datetime.now(timezone.utc).date().isoformat()
    path = log_dir / f"noise-{today}.jsonl"
    hash_prefix = _view_centroids_hash(view_registry)
    for record, noise_sim, summary in entries:
        payload = {
            "ts": now_iso(timespec="minutes"),
            "episode_ts": record.get("ts", ""),
            "episode_summary": summary,
            "noise_sim": round(noise_sim, 4),
            "view_centroids_hash": hash_prefix,
            "record_type": record.get("type", "unknown"),
        }
        append_jsonl_restricted(path, payload)


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
    """Patterns produced by the 2-step pipeline for one episode batch."""
    refined: str
    patterns: Tuple[str, ...]
    source_type: str
    episode_ids: Tuple[str, ...]


def _render_episode_lines(batch: List[Dict]) -> Tuple[List[str], List[str]]:
    """Format one batch into prompt lines; return (lines, episode timestamps)."""
    episode_lines = []
    batch_episode_ids: List[str] = []
    for r in batch:
        record_type = r.get("type", "unknown")
        data = r.get("data", {})
        ts = r.get("ts", "")
        summary = summarize_record(record_type, data)
        if summary:
            episode_lines.append(f"[{ts[:16]}] {record_type}: {summary}")
            if ts:
                batch_episode_ids.append(ts)
    return episode_lines, batch_episode_ids


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


def _distill_batch(
    batch: List[Dict], batch_idx: int, n_batches: int
) -> Optional[_BatchOutput]:
    """Run the 2-step pipeline for one batch; None when a step fails."""
    episode_lines, batch_episode_ids = _render_episode_lines(batch)
    if not episode_lines:
        return None

    batch_source_type = _derive_source_type(batch)

    prompt = DISTILL_PROMPT.format(episodes="\n".join(episode_lines))

    # Step 1: Extract — free-form output, with rules/axioms as lens
    result = generate(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        caller="distill.category",
    )
    if result is None:
        logger.warning("Batch %d/%d: step 1 (extract) failed", batch_idx + 1, n_batches)
        return None

    # Step 2: Summarize — concise patterns as JSON string array
    refine_prompt = DISTILL_REFINE_PROMPT.format(raw_output=result)
    refined = generate(
        refine_prompt, num_predict=3000, caller="distill.category_refine"
    )
    if refined is None:
        # Audit M1: skip the batch rather than feed step-1 prose to the
        # JSON parser — the bullet fallback would either harvest raw
        # unrefined lines as patterns or silently yield zero while
        # looking like a processed batch.
        logger.warning(
            "Batch %d/%d: step 2 (summarize) failed, skipping batch "
            "(audit M1)",
            batch_idx + 1, n_batches,
        )
        return None

    raw_patterns = _parse_refined_patterns(refined)

    # Decision gate: reject low-quality patterns
    batch_patterns = [p for p in raw_patterns if _is_valid_pattern(p)]
    rejected = len(raw_patterns) - len(batch_patterns)

    logger.info(
        "Batch %d/%d: %d episodes (prompt %d chars) → %d patterns (%d rejected)",
        batch_idx + 1, n_batches, len(batch), len(prompt), len(batch_patterns), rejected,
    )
    return _BatchOutput(
        refined=refined,
        patterns=tuple(batch_patterns),
        source_type=batch_source_type,
        # Keep up to 5 representative timestamps so the pattern can be
        # traced back to its originating episode window.
        episode_ids=tuple(batch_episode_ids[:5]),
    )


def _distill_category(
    records: List[Dict],
    knowledge: KnowledgeStore,
    source_date: Optional[str],
    dry_run: bool,
) -> _CategoryResult:
    """Run the 3-step distill pipeline over the kept records (ADR-0026).

    The per-category dedup scope has been retired alongside the
    ``category`` field: dedup runs against the full live pool.
    """
    batches = [records[i:i + BATCH_SIZE] for i in range(0, len(records), BATCH_SIZE)]
    logger.info("Processing %d episodes in %d batches", len(records), len(batches))

    all_patterns: List[str] = []
    all_source_types: List[str] = []
    all_episode_ids: List[List[str]] = []
    all_results: List[str] = []

    for batch_idx, batch in enumerate(batches):
        out = _distill_batch(batch, batch_idx, len(batches))
        if out is None:
            continue
        all_results.append(out.refined)
        all_patterns.extend(out.patterns)
        # ADR-0021: record source provenance per pattern. Every pattern in
        # this batch shares the same source_type (derived from the batch's
        # episode type mix) and the same representative episode id list.
        for _ in out.patterns:
            all_source_types.append(out.source_type)
            all_episode_ids.append(list(out.episode_ids))

    if not all_patterns:
        return _CategoryResult(results=tuple(all_results), added=0, updated=0)

    # ADR-0009: bulk-embed new patterns inline so dedup can run on cosine
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
            "pipeline_version": "distill@0.26",
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
