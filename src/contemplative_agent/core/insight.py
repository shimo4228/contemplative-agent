"""Insight extraction: synthesize learned patterns into behavioral skills.

Global embedding cluster per run. Each cluster → one LLM skill
extraction call. Cross-cluster synthesis and quality control are
deferred to skill-stocktake (external).

The view concept (ADR-0019) does not shape extraction: insight works
directly on ``gated != True`` live patterns so that any clustering
structure comes from the embeddings themselves, not from predefined
seed texts. The only view usage is read-only visibility — dropped
singletons log their nearest *consumed* view (``view_metrics``) so the
operator can see what skill extraction discards; nothing is gated,
ranked, or rescued by it. (The former claims that views drive distill's
noise gate and stocktake's merge went stale: ADR-0060 removed the noise
gate and ADR-0046 moved stocktake grouping to a single LLM call.)
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple, Union

from ._io import read_run_marker, strip_code_fence, write_run_marker
from .artifact_extraction import resolve_artifact_path
from .clustering import cluster_patterns
from .knowledge_store import (
    effective_importance,
    epistemic_counts_for,
    pattern_id,
)
from .llm import (
    NUM_CTX,
    _estimate_tokens,
    generate_full,
    get_distill_system_prompt,
    validate_identity_content,
)
from .memory import KnowledgeStore
from .prompts import INSIGHT_EXTRACTION_PROMPT
from .text_utils import extract_title, split_frontmatter
from .thresholds import CLUSTER_THRESHOLD_INSIGHT as CLUSTER_THRESHOLD, MAX_BATCH as BATCH_SIZE
from .view_metrics import ViewLookup, nearest_view

logger = logging.getLogger(__name__)

MIN_PATTERNS_REQUIRED = 3

# Above this live-pattern count, ``insight --full`` emits an advisory warning.
# Clustering itself is cheap since the ADR-0074 Lance-Williams merge; the cost
# that still scales with the pool is the human review batch (every eligible
# cluster becomes a staged candidate). NOT a quality cap — nothing is dropped.
FULL_RECLUSTER_WARN_N = 500


@dataclass(frozen=True)
class SkillResult:
    """A single generated skill ready for approval.

    ADR-0050: ``pattern_ids`` carries the content-hash ids of the cluster
    members actually passed to the LLM (kept members only), and
    ``epistemic_counts`` their observed/generated tally — both flow into
    the approval gate and audit.jsonl.
    """

    text: str
    filename: str
    target_path: Path
    pattern_ids: Tuple[str, ...] = ()
    epistemic_counts: Dict[str, int] = field(default_factory=dict)
    # ADR-0069: the reasoning trace for this skill (insight runs think-ON).
    # Per-skill (one LLM call per cluster), None when think was off / no trace.
    thinking: Optional[str] = None


@dataclass(frozen=True)
class InsightResult:
    """Result of a successful insight extraction.

    ADR-0074: ``skipped_known`` counts clusters the novelty gate judged
    already covered by an existing or previously staged skill. ``skills``
    may legitimately be empty when every cluster was known — the caller
    still advances the run marker in that case (the window WAS considered).
    """

    skills: Tuple[SkillResult, ...]
    dropped_count: int
    skipped_known: int = 0


def _extract_skill(
    patterns: List[str], topic: str = "mixed"
) -> Optional[Tuple[str, Optional[str]]]:
    """Extract one skill from patterns via LLM.

    Returns ``(skill_text, thinking)`` — the reasoning trace rides along
    because insight runs think-ON (ADR-0069). None on failure.
    """
    # The prompt template variable is still ``{subcategory}`` for backward
    # compatibility with the .md file; here we pass a topic label which
    # is a neutral cluster identifier, not a predefined view name.
    # The session-insights input was retired by ADR-0052 — skill extraction
    # works from patterns only, not from the agent's session narratives.
    prompt = INSIGHT_EXTRACTION_PROMPT.format(
        subcategory=topic,
        patterns="\n".join(f"- {p}" for p in patterns),
    )

    # Axioms-only system (same as distill): skill generation must not be
    # conditioned on the existing skill corpus, or each new skill inherits
    # the vocabulary of the last (audit H6).
    out = generate_full(
        prompt,
        system=get_distill_system_prompt(),
        num_predict=3000,
        caller="insight.skill_extract",
        think=True,
        drop_truncated=True,
    )
    if out is None or out.text is None:
        logger.warning("LLM failed to generate skill extraction.")
        return None

    text = out.text.strip()
    if extract_title(text) is None:
        logger.warning("Skill has no title, dropping.")
        logger.debug("Raw LLM output (first 300 chars): %.300s", out.text)
        return None

    return text, out.thinking


def _cluster_score(cluster: List[dict]) -> float:
    """Ordering key: cluster size × mean effective_importance.

    Favors frequently-recurring topics that are also recent. ADR-0056:
    effective_importance is pure time decay (the LLM rating was retired),
    so this weights large, freshly-reinforced clusters first. Size-only
    biases toward stale chatter; decay alone ignores how often a topic
    recurred.
    """
    if not cluster:
        return 0.0
    mean_imp = sum(effective_importance(p) for p in cluster) / len(cluster)
    return len(cluster) * mean_imp


def _log_dropped_singletons(
    singletons: List[dict],
    view_registry: Optional[ViewLookup] = None,
) -> None:
    """Visibility-only instrument for dropped singleton patterns (review
    2026-06-27 M3).

    ``cluster_patterns`` demotes sub-``min_size`` groups and the >``max_size``
    cluster tails into ``singletons``, which never reach the LLM and so can
    never become skills. Rarity/heterogeneity is the signal, so pooling them
    is the wrong fix; instead this logs how many were dropped and their
    ``effective_importance`` distribution (p50/p90/p99/max) plus the top rows,
    so a rare-singleton lane and floor can later be decided from the real live
    distribution rather than a blind constant. When ``view_registry`` is
    given, each top row also shows its nearest consumed view and cosine
    (``view_metrics.nearest_view``) — where the discarded pattern sits
    relative to the two real view consumers. No lane/threshold is applied
    here — this only logs.
    """
    if not singletons:
        return
    scores = sorted((effective_importance(p) for p in singletons), reverse=True)
    n = len(scores)

    def _pct(q: float) -> float:
        # Linear-position percentile on the descending list: q is the fraction
        # of patterns scoring at or below the returned value, so a high q maps
        # near the top (max). Diagnostic-only, so the exact interpolation rule
        # is immaterial.
        idx = min(n - 1, max(0, int(round((1.0 - q) * (n - 1)))))
        return scores[idx]

    logger.info(
        "insight: %d singleton pattern(s) dropped (never skilled); "
        "effective_importance p50=%.3f p90=%.3f p99=%.3f max=%.3f",
        n,
        _pct(0.50),
        _pct(0.90),
        _pct(0.99),
        scores[0],
    )
    for p in sorted(singletons, key=effective_importance, reverse=True)[:10]:
        nearest = nearest_view(p, view_registry) if view_registry is not None else None
        view_note = f" view≈{nearest[0]}:{nearest[1]:.2f}" if nearest else ""
        logger.info(
            "  dropped singleton score=%.3f%s: %s",
            effective_importance(p),
            view_note,
            (p.get("pattern", "") or "")[:80],
        )


def _build_cluster_batches(
    raw_patterns: List[dict],
    threshold: float = CLUSTER_THRESHOLD,
    min_size: int = MIN_PATTERNS_REQUIRED,
    max_size: int = BATCH_SIZE,
    view_registry: Optional[ViewLookup] = None,
) -> List[Tuple[str, List[str], Tuple[str, ...]]]:
    """Cluster patterns globally; every cluster ≥ ``min_size`` becomes a batch.

    ``gated`` patterns (noise per ADR-0026) are skipped before
    clustering so noise centroids cannot pull meaningful clusters
    toward themselves. Self-reflection patterns are NOT excluded — the
    same observation can seed both a skill and an identity block; LLM
    extraction drops the cluster if no skill can be distilled.

    Patterns without an ``embedding`` field bypass clustering (handled
    inside ``cluster_patterns``).

    Clusters are ordered by ``_cluster_score`` (size × mean
    effective_importance) descending so the LLM sees the strongest
    candidates first — an early LLM failure then costs less.

    Returns:
        List of (topic, pattern_texts, pattern_ids) tuples. Topic names
        are neutral ``cluster-N`` identifiers; the LLM is expected to
        title each skill from the content itself. ``pattern_ids``
        (ADR-0050) attribute only the kept members — the demoted tail
        beyond ``max_size`` never reaches the LLM and is not attributed.
    """
    candidates = [p for p in raw_patterns if not p.get("gated")]
    if len(candidates) < min_size:
        return []

    clusters, singletons = cluster_patterns(
        candidates,
        threshold=threshold,
        min_size=min_size,
        max_size=max_size,
    )
    _log_dropped_singletons(singletons, view_registry)
    if not clusters:
        return []

    clusters.sort(key=_cluster_score, reverse=True)

    batches: List[Tuple[str, List[str], Tuple[str, ...]]] = []
    for idx, cluster in enumerate(clusters, start=1):
        topic = f"cluster-{idx}"
        batches.append(
            (
                topic,
                [p["pattern"] for p in cluster],
                tuple(pattern_id(p) for p in cluster),
            )
        )
    return batches


def _read_last_insight(skills_dir: Optional[Path]) -> Optional[str]:
    """Read the timestamp of the last insight run."""
    return read_run_marker(skills_dir, ".last_insight")


def write_last_insight(skills_dir: Path) -> None:
    """Record the current timestamp as the last insight run."""
    write_run_marker(skills_dir, ".last_insight")


# ---------------------------------------------------------------------------
# ADR-0074: LLM novelty gate
# ---------------------------------------------------------------------------

_FRONTMATTER_SCALAR_RE = {
    "name": re.compile(r"^name:\s*(.+?)\s*$", re.MULTILINE),
    "description": re.compile(r'^description:\s*"?(.*?)"?\s*$', re.MULTILINE),
}

# Sample patterns shown to the novelty judge per cluster; enough to convey
# the theme without ballooning a grouping call past the context budget
# (same shape as stocktake's one-call grouping, ADR-0046).
_NOVELTY_SAMPLE_PER_CLUSTER = 3
_NOVELTY_SAMPLE_CHARS = 300

# Token-bounded chunking (2026-07-18): the first scheduled weekly run packed
# all known themes + 117 cluster samples into one 40,074-token prompt against
# the 32,768 window; llm.py's preflight refused the call and the gate
# fail-opened every cluster. The judge prompt is now split into budgeted
# chunks — each carries the FULL known inventory plus as many cluster blocks
# as fit under ``window − output reserve``.
_NOVELTY_CTX_WINDOW = NUM_CTX
# Matches llm.MIN_CLAMPED_NUM_PREDICT: below this output floor the preflight
# refuses the call anyway, so budgeting less would re-create the failure.
_NOVELTY_OUTPUT_RESERVE = 2048
# Retry shape for a cluster block that alone exceeds the chunk budget
# (only reachable when the known inventory eats most of the window).
_NOVELTY_TRUNCATED_SAMPLE_PER_CLUSTER = 1
_NOVELTY_TRUNCATED_SAMPLE_CHARS = 150

# Fail-open extraction cap (grill 2026-07-18): bounds the blast radius of an
# UNJUDGED fail-open batch — never applied to judged-novel clusters, so it is
# a review-budget circuit breaker, not a quality filter. Deferred clusters
# are not extracted, not staged and not ledger-written ("considered" status
# is never granted unseen), so a real theme can recur in a later window.
_DEFAULT_FAILOPEN_EXTRACTION_CAP = 20
_FAILOPEN_CAP_ENV = "MOLTBOOK_INSIGHT_FAILOPEN_CAP"

# One cluster batch as produced by _build_cluster_batches.
_Batch = Tuple[str, List[str], Tuple[str, ...]]


@dataclass(frozen=True)
class NoveltyFilterResult:
    """Outcome of the chunked novelty gate.

    ``fail_open_topics`` names the clusters that reached extraction
    UNJUDGED — their judge chunk failed (LLM / parse / budget), so they
    were kept without a coverage verdict. The fail-open extraction cap
    consumes exactly this set.
    """

    novel: Tuple[_Batch, ...]
    skipped_known: int
    fail_open_topics: frozenset[str]


def _render_known_lines(known_themes: Sequence[Tuple[str, str]]) -> str:
    return "\n".join(
        f"- {name}: {description}" if description else f"- {name}"
        for name, description in known_themes
    )


def _cluster_block(
    topic: str,
    patterns: List[str],
    sample_n: int = _NOVELTY_SAMPLE_PER_CLUSTER,
    sample_chars: int = _NOVELTY_SAMPLE_CHARS,
) -> str:
    samples = "\n".join(f"  - {p[:sample_chars]}" for p in patterns[:sample_n])
    return f"{topic}:\n{samples}"


def _novelty_fixed_tokens(known_lines: str) -> int:
    """Token cost every judge chunk pays regardless of its cluster blocks."""
    from .prompts import INSIGHT_NOVELTY_PROMPT, INSIGHT_NOVELTY_SYSTEM_PROMPT

    return _estimate_tokens(
        INSIGHT_NOVELTY_PROMPT.format(known=known_lines, clusters="")
    ) + _estimate_tokens(INSIGHT_NOVELTY_SYSTEM_PROMPT)


def _novelty_ctx_window() -> int:
    """Window the packer budgets against — same source as the generate
    preflight (llm.py C2). An injected backend advertising a SMALLER
    context_window lowers the budget (else every packed chunk would be
    refused by the preflight and fail open, codex P2); a larger one never
    raises it above the module ceiling — packing tighter than the preflight
    is safe, packing looser re-creates the 2026-07-18 refusal.
    """
    from . import llm as _llm

    backend = _llm._backend
    window = getattr(backend, "context_window", None) if backend is not None else None
    if window:
        return min(int(window), _NOVELTY_CTX_WINDOW)
    return _NOVELTY_CTX_WINDOW


def _pack_novelty_chunks(
    batches: Sequence[_Batch],
    known_lines: str,
) -> Tuple[List[Tuple[List[_Batch], List[str]]], List[_Batch]]:
    """Greedily pack cluster blocks into token-budgeted judge chunks.

    Deterministic and order-preserving. Returns ``(chunks, unbudgetable)``
    where each chunk is ``(batches, rendered_blocks)`` and ``unbudgetable``
    lists clusters that do not fit a chunk even with truncated samples —
    the caller fails those open with an audit reason.
    """
    budget = _novelty_ctx_window() - _NOVELTY_OUTPUT_RESERVE - _novelty_fixed_tokens(known_lines)
    chunks: List[Tuple[List[_Batch], List[str]]] = []
    unbudgetable: List[_Batch] = []
    cur_batches: List[_Batch] = []
    cur_blocks: List[str] = []
    cur_tokens = 0
    for batch in batches:
        topic, patterns, _pids = batch
        block = _cluster_block(topic, patterns)
        cost = _estimate_tokens(block + "\n\n")
        if cost > budget:
            block = _cluster_block(
                topic,
                patterns,
                sample_n=_NOVELTY_TRUNCATED_SAMPLE_PER_CLUSTER,
                sample_chars=_NOVELTY_TRUNCATED_SAMPLE_CHARS,
            )
            cost = _estimate_tokens(block + "\n\n")
            if cost > budget:
                unbudgetable.append(batch)
                continue
            logger.warning(
                "novelty gate: cluster [%s] samples truncated to fit the "
                "token budget (reason=sample_truncated)",
                topic,
            )
        if cur_batches and cur_tokens + cost > budget:
            chunks.append((cur_batches, cur_blocks))
            cur_batches, cur_blocks, cur_tokens = [], [], 0
        cur_batches.append(batch)
        cur_blocks.append(block)
        cur_tokens += cost
    if cur_batches:
        chunks.append((cur_batches, cur_blocks))
    return chunks, unbudgetable


def skill_theme(text: str, fallback_name: str = "skill") -> Tuple[str, str]:
    """Return ``(name, description)`` for a skill document.

    Reads the YAML frontmatter scalars when present; falls back to the
    first Markdown title (and the given name) for legacy bodies without
    frontmatter. Shared by the novelty gate's known-theme inventory and
    the CLI's staged-ledger writer so both sides agree on identity.
    """
    frontmatter, body = split_frontmatter(text)
    name = None
    description = None
    if frontmatter:
        m = _FRONTMATTER_SCALAR_RE["name"].search(frontmatter)
        name = m.group(1).strip() if m else None
        m = _FRONTMATTER_SCALAR_RE["description"].search(frontmatter)
        description = m.group(1).strip() if m else None
    title = extract_title(body or text)
    return (name or fallback_name, description or title or "")


def _load_known_themes(
    skills_dir: Optional[Path],
    staged_ledger_path: Optional[Path],
) -> List[Tuple[str, str]]:
    """Inventory of themes already surfaced to the human gate.

    Sources: adopted skill files (``skills_dir/*.md``) and the staged
    ledger (one JSON record per previously staged candidate — ADR-0074:
    a candidate counts as "considered" once it reached review, whether
    or not it was adopted). Deduplicated by name, first occurrence wins.
    """
    themes: List[Tuple[str, str]] = []
    seen: set[str] = set()

    if skills_dir is not None and skills_dir.is_dir():
        for path in sorted(skills_dir.glob("*.md")):
            if path.name.startswith("."):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                logger.warning("novelty gate: unreadable skill file %s", path.name)
                continue
            name, description = skill_theme(text, fallback_name=path.stem)
            if name not in seen:
                seen.add(name)
                themes.append((name, description))

    if staged_ledger_path is not None and staged_ledger_path.exists():
        try:
            lines = staged_ledger_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            logger.warning("novelty gate: unreadable staged ledger")
            lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = str(record.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            themes.append((name, str(record.get("description") or "").strip()))

    return themes


def _parse_covered_ids(raw: str, known_topics: set[str]) -> Optional[set[str]]:
    """Parse the novelty judge's output into covered cluster ids.

    Tolerates code fences and surrounding prose (same salvage as
    stocktake's ``_parse_groups``). Hallucinated ids are dropped.
    ``None`` signals an unusable response — the caller fails open.
    """
    text = strip_code_fence(raw)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}") + 1
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(text[start:end])
        except json.JSONDecodeError:
            return None
    covered = data.get("covered") if isinstance(data, dict) else None
    if not isinstance(covered, list):
        return None
    return {c for c in covered if isinstance(c, str) and c in known_topics}


# Bound on the base64-stored judge prompt/output in insight-novelty.jsonl
# (weekly cadence — worst case ~256 KiB/run; same truncation-flag pattern as
# verification-audit's _MAX_AUDIT_CHALLENGE_BYTES).
_MAX_NOVELTY_AUDIT_BYTES = 131072


def _append_novelty_audit(
    audit_path: Optional[Path],
    *,
    verdict: str,
    batches: Sequence[_Batch],
    covered: Optional[set[str]],
    known_themes_count: int,
    prompt: Optional[str],
    raw_output: Optional[str],
    batch_index: Optional[int] = None,
    batch_count: Optional[int] = None,
) -> None:
    """Best-effort replay record for one novelty-judge chunk (ADR-0074/0075).

    The covered→drop decision suppresses skill creation permanently; storing
    the exact judge prompt and raw output (base64 + sha256, bounded) makes the
    parse and the judgment replayable offline — without it a judge that starts
    wrongly suppressing novel themes leaves no corpus to diagnose from.
    One record per chunk (``batch_index`` / ``batch_count``); ``verdict``:
    "judged" | "fail_open_llm" | "fail_open_parse" | "fail_open_budget"
    (the last: no call was possible within the token budget — prompt is None).
    """
    if audit_path is None:
        return
    try:
        from ._io import append_jsonl_restricted, now_iso

        def _b64_fields(name: str, text: Optional[str]) -> dict:
            if text is None:
                return {f"{name}_b64": None}
            raw = text.encode("utf-8", "replace")
            kept = raw[:_MAX_NOVELTY_AUDIT_BYTES]
            return {
                f"{name}_sha256": hashlib.sha256(raw).hexdigest(),
                f"{name}_encoding": "base64:utf-8",
                f"{name}_b64": base64.b64encode(kept).decode("ascii"),
                f"{name}_bytes": len(raw),
                f"{name}_truncated": len(kept) < len(raw),
            }

        record: dict = {
            "ts": now_iso("seconds"),
            "verdict": verdict,
            "known_themes_count": known_themes_count,
            "batch_index": batch_index,
            "batch_count": batch_count,
            "clusters": sorted(topic for topic, _, _ in batches),
            "covered": sorted(covered) if covered else [],
            **_b64_fields("prompt", prompt),
            **_b64_fields("output", raw_output),
        }
        append_jsonl_restricted(audit_path, record)
    except Exception as exc:  # instrumentation must never break insight
        logger.warning("insight novelty audit record failed: %s", exc)


def _filter_novel_batches(
    batches: List[_Batch],
    known_themes: Sequence[Tuple[str, str]],
    audit_path: Optional[Path] = None,
) -> NoveltyFilterResult:
    """Drop cluster batches whose theme is already covered (ADR-0074).

    Token-bounded chunked judging (2026-07-18): clusters are packed into
    budgeted chunks, each judged by one LLM call against the FULL known
    inventory — "is this the same theme?" stays a semantic question for
    the LLM because the 2026-07-09 calibration showed embedding separation
    does not exist (same-theme member-level cross-similarity 0.646-0.709
    vs distinct-theme up to 0.698; centroids fully overlap).

    Fails open PER CHUNK: an LLM failure, unparseable output, or budget
    overflow keeps only that chunk's clusters (unjudged); other chunks'
    verdicts stand. The human review gate is the ultimate filter, so the
    failure mode is extra review load, never a silently dropped theme.
    Covered ids are validated per chunk — a judge cannot suppress a
    cluster it was not shown.
    """
    if not batches or not known_themes:
        return NoveltyFilterResult(tuple(batches), 0, frozenset())

    # Lazy import avoids widening module import cost for non-gate callers.
    from .prompts import INSIGHT_NOVELTY_PROMPT, INSIGHT_NOVELTY_SYSTEM_PROMPT

    known_lines = _render_known_lines(known_themes)
    chunks, unbudgetable = _pack_novelty_chunks(batches, known_lines)

    fail_open: set[str] = set()
    covered_total: set[str] = set()

    if unbudgetable:
        fail_open.update(topic for topic, _, _ in unbudgetable)
        logger.warning(
            "novelty gate: %d cluster(s) exceed the token budget even with "
            "truncated samples — failing open unjudged (reason=budget_overflow; "
            "known inventory: %d themes). This is the quantitative trigger for "
            "a retrieval-assisted gate design.",
            len(unbudgetable),
            len(known_themes),
        )
        # A separate event type, not a member of the chunk sequence — both
        # batch fields stay None rather than reporting a misleading count
        # (codex P2: batch_count=0 with nonempty work).
        _append_novelty_audit(
            audit_path,
            verdict="fail_open_budget",
            batches=unbudgetable,
            covered=None,
            known_themes_count=len(known_themes),
            prompt=None,
            raw_output=None,
            batch_index=None,
            batch_count=None,
        )

    for idx, (chunk_batches, chunk_blocks) in enumerate(chunks):
        prompt = INSIGHT_NOVELTY_PROMPT.format(
            known=known_lines, clusters="\n\n".join(chunk_blocks)
        )
        out = generate_full(
            prompt,
            system=INSIGHT_NOVELTY_SYSTEM_PROMPT,
            num_predict=2000,
            caller="insight.novelty",
            drop_truncated=True,
        )
        chunk_topics = {topic for topic, _, _ in chunk_batches}
        if out is None or out.text is None:
            fail_open.update(chunk_topics)
            logger.warning(
                "novelty gate: LLM call failed for chunk %d/%d — keeping its "
                "%d cluster(s) unjudged (reason=fail_open_llm)",
                idx + 1,
                len(chunks),
                len(chunk_batches),
            )
            _append_novelty_audit(
                audit_path,
                verdict="fail_open_llm",
                batches=chunk_batches,
                covered=None,
                known_themes_count=len(known_themes),
                prompt=prompt,
                raw_output=None,
                batch_index=idx,
                batch_count=len(chunks),
            )
            continue

        covered = _parse_covered_ids(out.text, chunk_topics)
        if covered is None:
            fail_open.update(chunk_topics)
            logger.warning(
                "novelty gate: unparseable judgment for chunk %d/%d — keeping "
                "its %d cluster(s) unjudged (reason=fail_open_parse)",
                idx + 1,
                len(chunks),
                len(chunk_batches),
            )
            _append_novelty_audit(
                audit_path,
                verdict="fail_open_parse",
                batches=chunk_batches,
                covered=None,
                known_themes_count=len(known_themes),
                prompt=prompt,
                raw_output=out.text,
                batch_index=idx,
                batch_count=len(chunks),
            )
            continue

        covered_total |= covered
        _append_novelty_audit(
            audit_path,
            verdict="judged",
            batches=chunk_batches,
            covered=covered,
            known_themes_count=len(known_themes),
            prompt=prompt,
            raw_output=out.text,
            batch_index=idx,
            batch_count=len(chunks),
        )

    novel = tuple(b for b in batches if b[0] not in covered_total)
    if covered_total:
        logger.info(
            "novelty gate: %d/%d cluster(s) already covered (%s)",
            len(covered_total),
            len(batches),
            ", ".join(sorted(covered_total)),
        )
    return NoveltyFilterResult(novel, len(covered_total), frozenset(fail_open))


def _failopen_extraction_cap() -> int:
    """Resolve the fail-open extraction cap (env-overridable config)."""
    raw = os.environ.get(_FAILOPEN_CAP_ENV)
    if raw is None:
        return _DEFAULT_FAILOPEN_EXTRACTION_CAP
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value < 1:
        logger.warning(
            "invalid %s=%r — using default %d",
            _FAILOPEN_CAP_ENV,
            raw,
            _DEFAULT_FAILOPEN_EXTRACTION_CAP,
        )
        return _DEFAULT_FAILOPEN_EXTRACTION_CAP
    return value


def _append_deferral_audit(
    audit_path: Optional[Path],
    *,
    cap: int,
    deferred: Sequence[_Batch],
) -> None:
    """Best-effort record of review-budget deferrals — never a silent drop."""
    if audit_path is None:
        return
    try:
        from ._io import append_jsonl_restricted, now_iso

        record = {
            "ts": now_iso("seconds"),
            "reason": "review_budget_deferred",
            "cap": cap,
            "deferred": [
                {"topic": topic, "size": len(patterns), "pattern_ids": list(pids)}
                for topic, patterns, pids in deferred
            ],
        }
        append_jsonl_restricted(audit_path, record)
    except Exception as exc:  # instrumentation must never break insight
        logger.warning("insight deferral audit record failed: %s", exc)


def _apply_failopen_extraction_cap(
    batches: List[_Batch],
    fail_open_topics: frozenset[str],
    patterns_by_id: Dict[str, dict],
    cap: int,
    audit_path: Optional[Path] = None,
) -> List[_Batch]:
    """Bound the blast radius of a fail-open novelty verdict (grill 2026-07-18).

    Applies ONLY to clusters that reached extraction unjudged (through a
    fail-open chunk); judged-novel clusters always pass, so normal weeks are
    uncapped and this never acts as a quality filter. Deferred clusters are
    dropped BEFORE extraction — never staged, never ledger-written — so a
    real theme recurs in a later window and gets judged then; a transient
    one dies with its week. Priority is deterministic and code-owned:
    member count desc, then time-decay importance sum desc, then topic name.
    """
    fail_open_batches = [b for b in batches if b[0] in fail_open_topics]
    if len(fail_open_batches) <= cap:
        return batches

    def _priority(batch: _Batch) -> Tuple[int, float, str]:
        topic, patterns, pids = batch
        importance = sum(
            effective_importance(patterns_by_id[pid]) for pid in pids if pid in patterns_by_id
        )
        return (-len(patterns), -importance, topic)

    ranked = sorted(fail_open_batches, key=_priority)
    deferred = ranked[cap:]
    deferred_topics = {b[0] for b in deferred}
    kept = [b for b in batches if b[0] not in deferred_topics]
    logger.warning(
        "novelty gate fail-open: deferring %d/%d unjudged cluster(s) beyond "
        "cap %d (reason=review_budget_deferred). Deferred clusters stay "
        "unstaged and un-ledgered, so recurring themes can resurface in a "
        "later window.",
        len(deferred),
        len(fail_open_batches),
        cap,
    )
    _append_deferral_audit(audit_path, cap=cap, deferred=deferred)
    return kept


def extract_insight(
    knowledge_store: Optional[KnowledgeStore] = None,
    skills_dir: Optional[Path] = None,
    full: bool = False,
    instrument_views: Optional[ViewLookup] = None,
    staged_ledger_path: Optional[Path] = None,
    novelty_audit_path: Optional[Path] = None,
) -> Union[str, InsightResult]:
    """Extract behavioral skills from accumulated knowledge.

    Single-pass per cluster: extract skill, validate, return.
    File writing is the caller's responsibility (ADR-0012 approval gate).
    Quality control is deferred to skill-stocktake.

    By default, only processes patterns added since the last insight run.
    Use full=True to process all patterns. ADR-0074: when the run marker
    is missing, the incremental path refuses instead of silently
    reclustering the whole live corpus.

    Args:
        knowledge_store: KnowledgeStore with learned patterns.
        skills_dir: Directory for skill files (used for incremental tracking
            and the novelty gate's adopted-skill inventory).
        full: If True, process all patterns instead of only new ones.
        instrument_views: Optional view lookup for the dropped-singleton
            visibility log (nearest consumed view); never gates anything.
        staged_ledger_path: Previously staged candidates (ADR-0074); feeds
            the novelty gate alongside adopted skills.
        novelty_audit_path: Optional replay log (insight-novelty.jsonl) for
            the novelty gate's judge run (ADR-0075); never gates anything.

    Returns:
        InsightResult on success (possibly with zero skills when every
        cluster was already covered), or error message string.
    """
    if knowledge_store is None:
        return "No knowledge store provided."

    knowledge_store.load()

    raw_patterns = _select_patterns(knowledge_store, skills_dir, full)
    if raw_patterns is None:
        return (
            "No previous insight run marker (.last_insight) found. Refusing to "
            "recluster the entire live corpus implicitly (ADR-0074). Run with "
            "--full to process all patterns deliberately, or create the marker "
            "to scope the incremental window."
        )

    if len(raw_patterns) < MIN_PATTERNS_REQUIRED:
        return (
            f"Insufficient patterns ({len(raw_patterns)}/{MIN_PATTERNS_REQUIRED}). "
            f"Run more sessions and distill first."
        )

    batches = _build_cluster_batches(raw_patterns, view_registry=instrument_views)

    if not batches:
        return (
            f"No clusters met the size floor ({MIN_PATTERNS_REQUIRED}). "
            f"Accumulate more diverse patterns or lower CLUSTER_THRESHOLD."
        )

    # ADR-0074 novelty gate: drop clusters whose theme already reached the
    # human gate (adopted skills + staged ledger). Runs BEFORE extraction so
    # known themes cost one grouping call per token-budgeted chunk, not one
    # generation each.
    skipped_known = 0
    fail_open_topics: frozenset[str] = frozenset()
    known_themes = _load_known_themes(skills_dir, staged_ledger_path)
    if known_themes:
        gate = _filter_novel_batches(batches, known_themes, audit_path=novelty_audit_path)
        batches = list(gate.novel)
        skipped_known = gate.skipped_known
        fail_open_topics = gate.fail_open_topics
    if not batches:
        logger.info(
            "novelty gate: all %d cluster(s) already covered — nothing to extract",
            skipped_known,
        )
        return InsightResult(skills=(), dropped_count=0, skipped_known=skipped_known)

    # ADR-0050: id → pattern dict lookup for per-batch epistemic counts
    # (also feeds the fail-open cap's deterministic priority ordering).
    patterns_by_id = {pattern_id(p): p for p in raw_patterns}
    if len(patterns_by_id) != len(raw_patterns):
        logger.debug(
            "pattern_id collision: %d patterns → %d unique ids "
            "(identical distilled+text rows; counts may undercount)",
            len(raw_patterns),
            len(patterns_by_id),
        )

    # Fail-open extraction cap (grill 2026-07-18): clusters that reached this
    # point UNJUDGED are bounded so a broken gate cannot flood the human
    # review batch again (2026-07-18: 117 unjudged clusters → 106 staged).
    if fail_open_topics:
        batches = _apply_failopen_extraction_cap(
            batches,
            fail_open_topics,
            patterns_by_id,
            cap=_failopen_extraction_cap(),
            audit_path=novelty_audit_path,
        )

    logger.info(
        "Processing %d patterns in %d cluster batches",
        len(raw_patterns),
        len(batches),
    )

    skill_results: List[SkillResult] = []
    dropped_count = 0

    for batch_idx, (topic, batch, batch_pids) in enumerate(batches):
        result = _extract_one_batch(
            topic,
            batch,
            batch_pids,
            batch_idx,
            len(batches),
            skills_dir,
            patterns_by_id,
        )
        if result is None:
            dropped_count += 1
        else:
            skill_results.append(result)

    if not skill_results:
        return "Failed to extract skill from knowledge."

    return InsightResult(
        skills=tuple(skill_results),
        dropped_count=dropped_count,
        skipped_known=skipped_known,
    )


def _select_patterns(
    knowledge_store: KnowledgeStore,
    skills_dir: Optional[Path],
    full: bool,
) -> Optional[List[dict]]:
    """Pick the live patterns to process (full vs incremental).

    ADR-0021/0051: pull live-only patterns so bitemporally superseded
    entries never enter batching.
    ADR-0026: dropped category="uncategorized" gate; gated=True is the
    only hard exclusion (handled by _build_cluster_batches).
    ADR-0074: a missing run marker returns ``None`` (refuse) instead of
    silently falling back to the whole live corpus — the silent fallback
    bypassed the ``FULL_RECLUSTER_WARN_N`` advisory and turned a routine
    incremental run into an unbounded recluster.
    """
    if full:
        patterns = knowledge_store.get_live_patterns()
        if len(patterns) > FULL_RECLUSTER_WARN_N:
            logger.warning(
                "insight --full: reclustering %d live patterns (> %d); "
                "expect a large first review batch (ADR-0074)",
                len(patterns),
                FULL_RECLUSTER_WARN_N,
            )
        return patterns
    last_run = _read_last_insight(skills_dir)
    if last_run:
        raw_patterns = knowledge_store.get_live_patterns_since(last_run)
        logger.info("Incremental mode: %d new patterns since %s", len(raw_patterns), last_run)
        return raw_patterns
    logger.warning(
        "insight: no .last_insight marker — refusing the implicit full recluster (ADR-0074)"
    )
    return None


def _extract_one_batch(
    topic: str,
    batch: List[str],
    batch_pids: Tuple[str, ...],
    batch_idx: int,
    n_batches: int,
    skills_dir: Optional[Path],
    patterns_by_id: Dict[str, dict],
) -> Optional[SkillResult]:
    """Extract + validate one cluster batch; None when dropped."""
    logger.info(
        "Batch %d/%d [%s]: %d patterns",
        batch_idx + 1,
        n_batches,
        topic,
        len(batch),
    )

    extracted = _extract_skill(batch, topic=topic)
    if extracted is None:
        logger.warning(
            "Batch %d/%d [%s]: extraction failed",
            batch_idx + 1,
            n_batches,
            topic,
        )
        return None
    skill_text, thinking = extracted

    if not validate_identity_content(skill_text):
        logger.warning(
            "Batch %d/%d [%s]: forbidden pattern detected",
            batch_idx + 1,
            n_batches,
            topic,
        )
        return None

    resolved = resolve_artifact_path(
        skill_text,
        skills_dir,
        label=f"Batch {batch_idx + 1}/{n_batches} [{topic}]",
    )
    if resolved is None:
        return None

    return SkillResult(
        text=skill_text,
        filename=resolved.filename,
        target_path=resolved.target_path,
        pattern_ids=batch_pids,
        epistemic_counts=epistemic_counts_for(
            [patterns_by_id[pid] for pid in batch_pids if pid in patterns_by_id]
        ),
        thinking=thinking,
    )
