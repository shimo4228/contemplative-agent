"""Novelty gate for staged insight (ADR-0074): decides which candidate
skill clusters are genuinely new relative to the adopted corpus and the
staged ledger, via a dedicated LLM judge call with its own token budget,
chunk packing, and audit log.

Extracted verbatim from core/insight.py (ADR-0079 Phase 3a). Must not
import from .insight (the extraction pipeline imports this module).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from . import llm
from ._io import strip_code_fence
from .text_utils import skill_theme as skill_theme  # public re-export (consumers: insight, cli)

logger = logging.getLogger(__name__)

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
_NOVELTY_CTX_WINDOW = llm.NUM_CTX


# The judge's own output reservation — how much of the window a chunk must
# leave for the verdict it asks for. It equalled llm.MIN_CLAMPED_NUM_PREDICT
# until 2026-08-01, when that floor dropped to 128 and stopped predicting
# output size at all (ADR-0087 amendment). The value stays here on purpose:
# packing tighter than the pre-flight is the safe direction (the packer can
# only refuse work the guard would have served, never the reverse), and
# re-deriving it from the judge's real verdict sizes is a separate change.
_NOVELTY_OUTPUT_RESERVE = 2048


# Retry shape for a cluster block that alone exceeds the chunk budget
# (only reachable when the known inventory eats most of the window).
_NOVELTY_TRUNCATED_SAMPLE_PER_CLUSTER = 1


_NOVELTY_TRUNCATED_SAMPLE_CHARS = 150


# One cluster batch as produced by _build_cluster_batches.
_Batch = tuple[str, list[str], tuple[str, ...]]


@dataclass(frozen=True)
class NoveltyFilterResult:
    """Outcome of the chunked novelty gate.

    ``fail_open_topics`` names the clusters that reached extraction
    UNJUDGED — their judge chunk failed (LLM / parse / budget), so they
    were kept without a coverage verdict. The fail-open extraction cap
    consumes exactly this set.
    """

    novel: tuple[_Batch, ...]
    skipped_known: int
    fail_open_topics: frozenset[str]


def _render_known_lines(known_themes: Sequence[tuple[str, str]]) -> str:
    return "\n".join(
        f"- {name}: {description}" if description else f"- {name}"
        for name, description in known_themes
    )


def _cluster_block(
    topic: str,
    patterns: list[str],
    sample_n: int = _NOVELTY_SAMPLE_PER_CLUSTER,
    sample_chars: int = _NOVELTY_SAMPLE_CHARS,
) -> str:
    samples = "\n".join(f"  - {p[:sample_chars]}" for p in patterns[:sample_n])
    return f"{topic}:\n{samples}"


def _novelty_fixed_tokens(known_lines: str) -> int:
    """Token cost every judge chunk pays regardless of its cluster blocks."""
    from .prompts import INSIGHT_NOVELTY_PROMPT, INSIGHT_NOVELTY_SYSTEM_PROMPT

    return llm._estimate_tokens(
        INSIGHT_NOVELTY_PROMPT.format(known=known_lines, clusters="")
    ) + llm._estimate_tokens(INSIGHT_NOVELTY_SYSTEM_PROMPT)


def _novelty_ctx_window() -> int:
    """Window the packer budgets against — same source as the generate
    preflight (llm.py C2). An injected backend advertising a SMALLER
    context_window lowers the budget (else every packed chunk would be
    refused by the preflight and fail open, codex P2); a larger one never
    raises it above the module ceiling — packing tighter than the preflight
    is safe, packing looser re-creates the 2026-07-18 refusal.
    """

    backend = llm._backend
    window = getattr(backend, "context_window", None) if backend is not None else None
    if window:
        return min(int(window), _NOVELTY_CTX_WINDOW)
    return _NOVELTY_CTX_WINDOW


def _pack_novelty_chunks(
    batches: Sequence[_Batch],
    known_lines: str,
) -> tuple[list[tuple[list[_Batch], list[str]]], list[_Batch]]:
    """Greedily pack cluster blocks into token-budgeted judge chunks.

    Deterministic and order-preserving. Returns ``(chunks, unbudgetable)``
    where each chunk is ``(batches, rendered_blocks)`` and ``unbudgetable``
    lists clusters that do not fit a chunk even with truncated samples —
    the caller fails those open with an audit reason.
    """
    budget = _novelty_ctx_window() - _NOVELTY_OUTPUT_RESERVE - _novelty_fixed_tokens(known_lines)
    chunks: list[tuple[list[_Batch], list[str]]] = []
    unbudgetable: list[_Batch] = []
    cur_batches: list[_Batch] = []
    cur_blocks: list[str] = []
    cur_tokens = 0
    for batch in batches:
        topic, patterns, _pids = batch
        block = _cluster_block(topic, patterns)
        cost = llm._estimate_tokens(block + "\n\n")
        if cost > budget:
            block = _cluster_block(
                topic,
                patterns,
                sample_n=_NOVELTY_TRUNCATED_SAMPLE_PER_CLUSTER,
                sample_chars=_NOVELTY_TRUNCATED_SAMPLE_CHARS,
            )
            cost = llm._estimate_tokens(block + "\n\n")
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


def _load_known_themes(
    skills_dir: Path | None,
    staged_ledger_path: Path | None,
) -> list[tuple[str, str]]:
    """Inventory of themes already surfaced to the human gate.

    Sources: adopted skill files (``skills_dir/*.md``) and the staged
    ledger (one JSON record per previously staged candidate — ADR-0074:
    a candidate counts as "considered" once it reached review, whether
    or not it was adopted). Deduplicated by name, first occurrence wins.
    """
    themes: list[tuple[str, str]] = []
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


def _parse_covered_ids(raw: str, known_topics: set[str]) -> set[str] | None:
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
    audit_path: Path | None,
    *,
    verdict: str,
    batches: Sequence[_Batch],
    covered: set[str] | None,
    known_themes_count: int,
    prompt: str | None,
    raw_output: str | None,
    batch_index: int | None = None,
    batch_count: int | None = None,
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
        from ._io import append_jsonl_restricted, b64_audit_fields, now_iso

        def _b64_fields(name: str, text: str | None) -> dict:
            """Bind the shared replay encoder to this log's byte cap."""
            return b64_audit_fields(name, text, max_bytes=_MAX_NOVELTY_AUDIT_BYTES)

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
    batches: list[_Batch],
    known_themes: Sequence[tuple[str, str]],
    audit_path: Path | None = None,
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
        out = llm.generate_full(
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
