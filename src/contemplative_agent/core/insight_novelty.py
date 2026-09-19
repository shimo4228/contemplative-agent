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
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from itertools import chain
from pathlib import Path

from . import llm
from ._io import strip_code_fence
from .text_utils import iter_markdown_documents, skill_theme

logger = logging.getLogger(__name__)

# Sample patterns shown to the novelty judge per cluster; enough to convey
# the theme without ballooning a grouping call past the context budget
# (same shape as stocktake's one-call grouping, ADR-0046).
_NOVELTY_SAMPLE_PER_CLUSTER = 3


_NOVELTY_SAMPLE_CHARS = 300


# Token-bounded chunking (2026-07-18): the first scheduled weekly run packed
# all known themes + 117 cluster samples into one 40,074-token prompt against
# the 32,768 window; llm.py's preflight refused the call and the gate
# fail-opened every cluster. The judge prompt is split into budgeted chunks —
# each carries as many cluster blocks as fit under ``window − output reserve``
# together with the known lines those blocks retrieved (RFC-0023 / ADR-0104:
# candidate generation is cosine top-k per cluster, the verdict stays the
# LLM's). Retrieval failure falls back to the full inventory with a reason
# code — the pre-retrieval shape, which past a certain inventory size no
# longer fits the window and fails every cluster open unjudged rather than
# judging them.
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


# Known lines each cluster contributes to its chunk's ``{known}`` slot,
# ranked by cosine (nomic) against the cluster block. The 2026-09-05 replay
# (docs/evidence/rfc-0023/novelty-replay-ab-20260905.md) found no accuracy
# difference between k = 5 / 10 / 15 — the arm-to-arm symmetric difference
# (19-21 of 63 clusters) sat below the same-arm rep-to-rep floor (22) — so k
# is set at the low end of RFC-0023's k ~ 10-15, which recall@10 = 0.77
# motivates: 23% of the reviewer-named skills are outside the top 10 and the
# judge cannot see them at any k this small.
_NOVELTY_TOPK = 10


# Clusters a single judge call may carry. Shortening {known} freed ~28k
# tokens of budget, so the packer would otherwise put ~39 clusters in one
# call at the 2026-09-04 scale — a regime nothing has measured. The
# 2026-09-05 replay judged the production packing of 64 clusters in 10 chunks
# (~6.4 each), and one fail-open costs a whole chunk's clusters their verdict,
# so the blast radius is kept near the measured shape rather than following
# the freed budget.
_NOVELTY_MAX_CLUSTERS_PER_CHUNK = 10


# Embedding batch size for the retrieval pass. Matches the replay script's
# batching: one large POST was refused by Ollama while the generation model
# was resident, small ones were not.
_NOVELTY_EMBED_BATCH = 64


# Sampling temperature of the judge call (RFC-0042 item 1). The gate ran at
# ``generate_full``'s default of 1.0 until 2026-09-19, where a replay of the
# logged prompts found two repetitions of the SAME prompt sharing only half
# their covered set (Jaccard 0.50) while the totals stayed flat — the verdict
# was being decided by the sampling noise, not by the prompt. At 0 the same
# replay is bit-identical across repetitions (docs/evidence/rfc-0041/).
_NOVELTY_TEMPERATURE = 0.0


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
    return "\n".join(_known_line(name, description) for name, description in known_themes)


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


def _known_doc(name: str, description: str) -> str:
    """Retrieval document for one inventory entry.

    The rendered inventory line without its bullet — the same text the judge
    is shown, so the ranking scores exactly what the prompt would carry.
    """
    return f"{name}: {description}" if description else name


def _known_line(name: str, description: str) -> str:
    """One inventory line as the judge sees it: the retrieval doc, bulleted.

    Single formatter for the three readings of an inventory line (the rendered
    block, the retrieval document, the per-line token price) — a format change
    here cannot desynchronize what is ranked from what is shown.
    """
    return f"- {_known_doc(name, description)}"


def _embed_in_batches(texts: Sequence[str]) -> list | None:
    """Embed ``texts`` in small batches. ``None`` on any degeneracy.

    Degenerate means: the call failed, returned the wrong number of rows, or
    returned a non-finite / zero-norm row. A zero row scores every document
    0.0 and the ``(-score, name)`` tie-break would hand back the
    alphabetically first k names as if they were a ranking — a silently
    wrong retrieval, so it is treated as no retrieval at all. No retry: the
    gate runs weekly and the caller falls back to the full inventory.
    """
    import numpy as np

    from .embeddings import embed_texts

    rows: list = []
    for start in range(0, len(texts), _NOVELTY_EMBED_BATCH):
        batch = list(texts[start : start + _NOVELTY_EMBED_BATCH])
        matrix = embed_texts(batch)
        if matrix is None or len(matrix) != len(batch):
            return None
        array = np.asarray(matrix, dtype=np.float64)
        if not np.isfinite(array).all():
            return None
        if float(np.linalg.norm(array, axis=1).min()) == 0.0:
            return None
        rows.extend(array)
    return rows


def _rank_known_for_batches(
    batches: Sequence[_Batch],
    known_themes: Sequence[tuple[str, str]],
) -> dict[str, list[str]] | None:
    """Rank the known inventory against each cluster by cosine (ADR-0104).

    Returns ``{cluster topic: known names, nearest first}`` — ties broken by
    name so the ranking is deterministic — or ``None`` when embedding is
    unavailable or degenerate (:func:`_embed_in_batches`), which the caller
    reports as ``reason=retrieval_unavailable`` and answers with the full
    inventory. Candidate generation only: nothing is dropped by score here,
    the LLM still returns the verdict (ADR-0074 stands).
    """
    from .embeddings import cosine

    names = [name for name, _ in known_themes]
    docs = [_known_doc(name, description) for name, description in known_themes]
    queries = [_cluster_block(topic, patterns) for topic, patterns, _ in batches]

    doc_vectors = _embed_in_batches(docs)
    if doc_vectors is None:
        return None
    query_vectors = _embed_in_batches(queries)
    if query_vectors is None:
        return None

    ranks: dict[str, list[str]] = {}
    for (topic, _patterns, _pids), query_vector in zip(batches, query_vectors, strict=True):
        scored = [(names[i], cosine(query_vector, doc_vectors[i])) for i in range(len(doc_vectors))]
        scored.sort(key=lambda item: (-item[1], item[0]))
        ranks[topic] = [name for name, _score in scored]
    return ranks


def _pack_novelty_chunks(
    batches: Sequence[_Batch],
    known_themes: Sequence[tuple[str, str]],
    ranks: dict[str, list[str]] | None = None,
    k: int = _NOVELTY_TOPK,
) -> tuple[list[tuple[list[_Batch], list[str], list[tuple[str, str]]]], list[_Batch]]:
    """Greedily pack cluster blocks into token-budgeted judge chunks.

    Deterministic and order-preserving. Returns ``(chunks, unbudgetable)``
    where each chunk is ``(batches, rendered_blocks, known_subset)`` and
    ``unbudgetable`` lists clusters that do not fit a chunk even with
    truncated samples — the caller fails those open with an audit reason.

    Each cluster brings its own top-k known lines (``ranks``); a chunk's
    ``{known}`` slot is the union of its clusters' picks, kept in inventory
    order so the shortening is the only variable the judge sees. A line
    already carried by the chunk is free for the next cluster, so the greedy
    cost of a block is ``block + the known lines it ADDS``. A chunk also
    stops at ``_NOVELTY_MAX_CLUSTERS_PER_CHUNK`` clusters regardless of
    budget. With ``ranks=None`` every cluster wants the whole inventory,
    which reproduces the pre-retrieval budgeting exactly (the cluster cap
    aside) — including its overflow: once the inventory alone exceeds the
    budget, that fallback judges nothing and every cluster fails open
    unjudged, which is the state the retrieval exists to leave.
    """
    order = {name: position for position, (name, _) in enumerate(known_themes)}
    by_name = dict(known_themes)
    all_names = [name for name, _ in known_themes]
    line_cost = {
        name: llm._estimate_tokens(_known_line(name, by_name[name]) + "\n") for name in all_names
    }

    def _wanted(topic: str) -> list[str]:
        """Known lines this cluster asks for: its top-k, else everything.

        A cluster missing from ``ranks`` is treated exactly like "no ranking
        at all" — the whole inventory — never the first k names in inventory
        order, which would be an arbitrary slice wearing a ranking's clothes.
        """
        if ranks is None or topic not in ranks:
            return all_names
        return ranks[topic][:k]

    def _known_subset(names: set[str]) -> list[tuple[str, str]]:
        return [(name, by_name[name]) for name in sorted(names, key=lambda n: order[n])]

    budget = _novelty_ctx_window() - _NOVELTY_OUTPUT_RESERVE - _novelty_fixed_tokens("")
    chunks: list[tuple[list[_Batch], list[str], list[tuple[str, str]]]] = []
    unbudgetable: list[_Batch] = []
    cur_batches: list[_Batch] = []
    cur_blocks: list[str] = []
    cur_known: set[str] = set()
    cur_tokens = 0
    for batch in batches:
        topic, patterns, _pids = batch
        wanted = _wanted(topic)
        own_known_cost = sum(line_cost[name] for name in wanted)
        block = _cluster_block(topic, patterns)
        cost = llm._estimate_tokens(block + "\n\n")
        if cost + own_known_cost > budget:
            block = _cluster_block(
                topic,
                patterns,
                sample_n=_NOVELTY_TRUNCATED_SAMPLE_PER_CLUSTER,
                sample_chars=_NOVELTY_TRUNCATED_SAMPLE_CHARS,
            )
            cost = llm._estimate_tokens(block + "\n\n")
            if cost + own_known_cost > budget:
                unbudgetable.append(batch)
                continue
            logger.warning(
                "novelty gate: cluster [%s] samples truncated to fit the "
                "token budget (reason=sample_truncated)",
                topic,
            )
        added_known_cost = sum(line_cost[name] for name in wanted if name not in cur_known)
        full = len(cur_batches) >= _NOVELTY_MAX_CLUSTERS_PER_CHUNK
        if cur_batches and (full or cur_tokens + cost + added_known_cost > budget):
            chunks.append((cur_batches, cur_blocks, _known_subset(cur_known)))
            cur_batches, cur_blocks, cur_known, cur_tokens = [], [], set(), 0
            added_known_cost = own_known_cost
        cur_batches.append(batch)
        cur_blocks.append(block)
        cur_known.update(wanted)
        cur_tokens += cost + added_known_cost
    if cur_batches:
        chunks.append((cur_batches, cur_blocks, _known_subset(cur_known)))
    return chunks, unbudgetable


def _skill_file_themes(skills_dir: Path | None) -> Iterator[tuple[str, str]]:
    """Themes of the adopted skill files, in filename order.

    Yields whatever ``skill_theme`` reports, empty name included — the caller
    dedupes and this source has never filtered on emptiness.
    """
    for path, text in iter_markdown_documents(
        skills_dir, label="novelty gate: unreadable skill file"
    ):
        yield skill_theme(text, fallback_name=path.stem)


def _staged_ledger_themes(staged_ledger_path: Path | None) -> Iterator[tuple[str, str]]:
    """Themes of previously staged candidates, in ledger order.

    Unnamed records are dropped here rather than by the caller, which is where
    that filter has always lived: an unreadable ledger, an unparsable line and
    a nameless record are all "no theme", not a fault.
    """
    if staged_ledger_path is None or not staged_ledger_path.exists():
        return
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
        if not name:
            continue
        yield name, str(record.get("description") or "").strip()


def _load_known_themes(
    skills_dir: Path | None,
    staged_ledger_path: Path | None,
) -> list[tuple[str, str]]:
    """Inventory of themes already surfaced to the human gate.

    Sources: adopted skill files (``skills_dir/*.md``) and the staged
    ledger (one JSON record per previously staged candidate — ADR-0074:
    a candidate counts as "considered" once it reached review, whether
    or not it was adopted). Deduplicated by name, first occurrence wins,
    and the skill files are read first so an adopted skill's description
    beats a staged candidate's.
    """
    themes: list[tuple[str, str]] = []
    seen: set[str] = set()
    sources = chain(_skill_file_themes(skills_dir), _staged_ledger_themes(staged_ledger_path))
    for name, description in sources:
        if name in seen:
            continue
        seen.add(name)
        themes.append((name, description))
    return themes


def _parse_covered_ids(raw: str, known_topics: set[str]) -> set[str] | None:
    """Parse the novelty judge's output into covered cluster ids.

    Tolerates code fences and surrounding prose (``strip_code_fence``,
    then a retry on the outermost ``{``...``}`` slice). Hallucinated ids
    are dropped.
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


# The record grammar of insight-novelty.jsonl (RFC-0034). Two writers share
# the file — the judge record here and the review-budget deferral record in
# :mod:`.insight` — and used to share only ``ts``, so a reader could not tell
# one event family from the other; the replay counted every deferral row as a
# judge verdict of ``None`` and read its absent ``known_themes_count`` as a
# second inventory regime. Named here because this module owns the log's
# grammar, the way ``selection_window`` owns the selection log's.
#
# Absence means the judge family: every record written before this change is
# one, so the longitudinal readings stay one series instead of gaining an
# "unknown" bucket on the day the kinds started (the same rule
# ``SELECTION_RECORD_KIND`` follows).
NOVELTY_JUDGE_RECORD_KIND = "novelty_judge"


NOVELTY_DEFERRAL_RECORD_KIND = "review_budget_deferral"


# The deferral record's own ``reason`` value, and the only field that
# distinguishes a kind-less deferral row from a kind-less judge row. The
# writer is ``insight._append_deferral_audit``; named here because the
# reader below has to know it.
_DEFERRAL_REASON = "review_budget_deferred"


def is_novelty_judge_record(record: dict) -> bool:
    """Whether a record from this log is a judge record.

    A missing ``kind`` alone does not make one: the deferral writer has been
    appending kind-less rows to this same file since the fail-open extraction
    cap shipped, so "written before the kinds" is not the same as "a judge
    record" for this log (code review 2026-09-12 — today's production log
    happens to hold no deferral row, which makes that latent, not absent).
    A legacy row is therefore read structurally, by the field only the
    deferral writer has ever written.
    """
    kind = record.get("kind")
    if kind is not None:
        return kind == NOVELTY_JUDGE_RECORD_KIND
    return record.get("reason") != _DEFERRAL_REASON


def append_novelty_audit_record(audit_path: Path | None, record: dict, *, what: str) -> None:
    """Append one record to insight-novelty.jsonl, best-effort.

    Both writers come through here so "an instrument may never break insight"
    is one decision rather than two copies that drift apart (RFC-0034).
    """
    if audit_path is None:
        return
    try:
        from ._io import append_jsonl_restricted

        append_jsonl_restricted(audit_path, record)
    except Exception as exc:  # instrumentation must never break insight
        logger.warning("insight %s audit record failed: %s", what, exc)


# Bound on the base64-stored judge prompt/output in insight-novelty.jsonl,
# applied per field: ~256 KiB is the worst case for ONE record, and the gate
# writes one record per chunk, so a weekly run's worst case is ~2.5 MiB at the
# measured 10-chunk packing. Same truncation-flag pattern as
# verification-audit's _MAX_AUDIT_CHALLENGE_BYTES.
_MAX_NOVELTY_AUDIT_BYTES = 131072


def _append_novelty_audit(
    audit_path: Path | None,
    *,
    verdict: str,
    batches: Sequence[_Batch],
    covered: set[str] | None,
    known_themes_count: int,
    inventory_count: int,
    known_selection: dict,
    prompt: str | None,
    raw_output: str | None,
    temperature: float | None,
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

    ``temperature`` is the sampling temperature the chunk's judge call ran at,
    ``None`` when no call was made (``fail_open_budget``) — a replay reading
    an old row must not mistake a t=1.0 verdict for a t=0 one, and this log
    spans both regimes (RFC-0042 item 1; absence means the pre-2026-09-19
    default of 1.0).

    ``known_themes_count`` is how many inventory lines THIS chunk showed the
    judge (zero for fail_open_budget, which built no prompt);
    ``inventory_count`` is the whole inventory and ``known_selection`` says
    how the chunk's lines were picked out of it (ADR-0104) — the three
    together let a reading separate "the judge did not see it" from "the
    judge saw it and called it new".
    """
    if audit_path is None:
        return
    try:
        from ._io import b64_audit_fields, now_iso

        def _b64_fields(name: str, text: str | None) -> dict:
            """Bind the shared replay encoder to this log's byte cap."""
            return b64_audit_fields(name, text, max_bytes=_MAX_NOVELTY_AUDIT_BYTES)

        record: dict = {
            "kind": NOVELTY_JUDGE_RECORD_KIND,
            "ts": now_iso("seconds"),
            "verdict": verdict,
            "known_themes_count": known_themes_count,
            "inventory_count": inventory_count,
            "known_selection": known_selection,
            "temperature": temperature,
            "batch_index": batch_index,
            "batch_count": batch_count,
            "clusters": sorted(topic for topic, _, _ in batches),
            "covered": sorted(covered) if covered else [],
            **_b64_fields("prompt", prompt),
            **_b64_fields("output", raw_output),
        }
    except Exception as exc:  # instrumentation must never break insight
        logger.warning("insight novelty audit record failed: %s", exc)
        return
    append_novelty_audit_record(audit_path, record, what="novelty")


def _filter_novel_batches(
    batches: list[_Batch],
    known_themes: Sequence[tuple[str, str]],
    audit_path: Path | None = None,
    k: int = _NOVELTY_TOPK,
) -> NoveltyFilterResult:
    """Drop cluster batches whose theme is already covered (ADR-0074).

    Token-bounded chunked judging (2026-07-18): clusters are packed into
    budgeted chunks, each judged by one LLM call — "is this the same theme?"
    stays a semantic question for the LLM because the 2026-07-09 calibration
    showed embedding separation does not exist (same-theme member-level
    cross-similarity 0.646-0.709 vs distinct-theme up to 0.698; centroids
    fully overlap).

    Each chunk's ``{known}`` slot carries the cosine top-k inventory lines
    its clusters retrieved (ADR-0104), not the whole inventory. Retrieval is
    candidate generation only — no line is dropped by score, the judge still
    decides. When embedding is unavailable the chunk falls back to the full
    inventory, logged with ``reason=retrieval_unavailable`` and recorded in
    the audit's ``known_selection``; once the inventory alone exceeds the
    budget that fallback judges nothing and the whole run fails open unjudged
    (``fail_open_budget``).

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
    from .embeddings import _get_embedding_model
    from .prompts import INSIGHT_NOVELTY_PROMPT, INSIGHT_NOVELTY_SYSTEM_PROMPT

    ranks = _rank_known_for_batches(batches, known_themes)
    if ranks is None:
        logger.warning(
            "novelty gate: candidate retrieval unavailable for %d cluster(s) — "
            "judging against the full inventory of %d theme(s) "
            "(reason=retrieval_unavailable)",
            len(batches),
            len(known_themes),
        )
    known_selection = {
        "mode": "topk" if ranks is not None else "full",
        "k": k if ranks is not None else None,
        "reason": None if ranks is not None else "retrieval_unavailable",
        "embedding_model": _get_embedding_model(),
    }
    chunks, unbudgetable = _pack_novelty_chunks(batches, known_themes, ranks, k)

    fail_open: set[str] = set()
    covered_total: set[str] = set()

    if unbudgetable:
        fail_open.update(topic for topic, _, _ in unbudgetable)
        logger.warning(
            "novelty gate: %d cluster(s) exceed the token budget even with "
            "truncated samples — failing open unjudged (reason=budget_overflow; "
            "known inventory: %d themes).",
            len(unbudgetable),
            len(known_themes),
        )
        # A separate event type, not a member of the chunk sequence — both
        # batch fields stay None rather than reporting a misleading count
        # (codex P2: batch_count=0 with nonempty work). No prompt was built,
        # so the count of lines shown to the judge is zero.
        _append_novelty_audit(
            audit_path,
            verdict="fail_open_budget",
            batches=unbudgetable,
            covered=None,
            known_themes_count=0,
            inventory_count=len(known_themes),
            known_selection=known_selection,
            prompt=None,
            raw_output=None,
            temperature=None,
            batch_index=None,
            batch_count=None,
        )

    for idx, (chunk_batches, chunk_blocks, chunk_known) in enumerate(chunks):
        prompt = INSIGHT_NOVELTY_PROMPT.format(
            known=_render_known_lines(chunk_known), clusters="\n\n".join(chunk_blocks)
        )
        audit_common = {
            "known_themes_count": len(chunk_known),
            "inventory_count": len(known_themes),
            "known_selection": known_selection,
            "temperature": _NOVELTY_TEMPERATURE,
            "batch_index": idx,
            "batch_count": len(chunks),
        }
        out = llm.generate_full(
            prompt,
            system=INSIGHT_NOVELTY_SYSTEM_PROMPT,
            num_predict=2000,
            temperature=_NOVELTY_TEMPERATURE,
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
                prompt=prompt,
                raw_output=None,
                **audit_common,
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
                prompt=prompt,
                raw_output=out.text,
                **audit_common,
            )
            continue

        covered_total |= covered
        _append_novelty_audit(
            audit_path,
            verdict="judged",
            batches=chunk_batches,
            covered=covered,
            prompt=prompt,
            raw_output=out.text,
            **audit_common,
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
