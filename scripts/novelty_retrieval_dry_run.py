#!/usr/bin/env python3
"""Novelty-gate retrieval dry run (RFC-0023 entry measurement) — read-only.

Answers one question: **if the insight novelty gate asked retrieval against
the existing skill store instead of a ~40k-token LLM judge, what would
today's clusters look like?** The gate currently sends every cluster's text
plus the whole known-theme inventory to one LLM call and reads back a
``covered`` list. A retrieval gate would instead score each cluster against
the store and call it covered above some similarity threshold. This script
computes the scores that gate would see, prints the distribution the
threshold would have to be chosen from, and puts the LLM's own historical
``covered`` rate beside it — so the exchange is judged on numbers rather than
on the plausibility of the idea.

**It does not decide anything and it writes nothing but ``--out``.** No gate
is fed, no skill is staged, no ledger row is touched. One-shot instrument
(ADR-0075's 2026-08-29 amendment: a read-only measurement carries no audit
log of its own; its result is frozen to ``docs/evidence/`` by the session
that reads it).

**Arms** — two representations of every store skill crossed with two scorers,
plus one fusion:

- ``cosine_theme`` / ``cosine_full`` — nomic embeddings of, respectively, the
  skill's one-line theme (``name — description``, the same string the novelty
  gate's known-theme inventory is built from) and its whole frontmatter-
  stripped body. The two are kept apart because they are different claims: a
  theme match says the *stated purpose* overlaps, a body match says the
  *prose* does, and a gate built on the wrong one would reject for the wrong
  reason.
- ``bm25_theme`` / ``bm25_full`` — Okapi BM25 over the same two
  representations, sharing ``scripts/retrieval_recall_measure.py``'s
  implementation so the two instruments cannot drift into two BM25s.
- ``rrf`` — reciprocal-rank fusion of ``cosine_full`` and ``bm25_full``
  (``1/(rrf_k + rank)``). ``--rrf-k`` defaults to **10, not the TREC-scale
  60**: the corpus here is ~57 documents, and against it ``1/(60+r)`` is
  nearly linear over the whole rank range, which flattens the fusion into a
  rank-sum with no top-rank emphasis — the opposite of what a top-1 reading
  wants.

**Queries.** A cluster's query text is its members' ``pattern`` strings joined
by newline; its query vector is the mean of those members' **stored**
embeddings, so the 7,700-row corpus is never re-embedded (only the 57 skills
are, twice each). A singleton is its own text and its own stored vector.

**Why singletons are in the reading.** ``insight`` drops every group below
``MIN_PATTERNS_REQUIRED`` before the gate ever sees it, so a gate reading
taken over clusters alone has no negative class. The singletons are the
closest available stand-in for "material the store does not cover": their
top-1 distribution is what the candidate thresholds in
``coverage_at_thresholds`` are drawn from, and the ``rare_lane`` block names
the singletons furthest from anything in the store.

**Faults abstain, they never print zero** (ADR-0075). An unavailable or
degenerate embedding response exits 2 with a ``reason=`` code on stderr
rather than writing a file full of 0.0 similarities, which would read as "the
store covers nothing".

Usage::

    uv run python scripts/novelty_retrieval_dry_run.py --out reading.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# scripts/ is not a package; the sibling modules are imported the way every
# other instrument here imports them (running this file puts scripts/ on the
# path, and the test inserts it explicitly).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan import ScanError  # noqa: E402
from retrieval_recall_measure import (  # noqa: E402
    Bm25Index,
    bm25_scores_from_index,
    build_bm25_index,
)

DEFAULT_HOME = Path.home() / ".config" / "moltbook"
DEFAULT_RRF_K = 10
TOP_N = 3
# Cluster/singleton texts are the agent's own distill output (self-authored,
# not external content), so they may be quoted — but a reading is a table,
# not a corpus dump.
TEXT_PREVIEW_CHARS = 120
RARE_LANE_SAMPLES = 10
QUANTILES = (10, 25, 50, 75, 90)
# The three candidate thresholds a retrieval gate would be chosen from, read
# off the singleton (uncovered-ish) top-1 distribution rather than picked.
CANDIDATE_QUANTILES = (50, 75, 90)

COSINE_ARMS = ("cosine_theme", "cosine_full")
BM25_ARMS = ("bm25_theme", "bm25_full")
ARMS = (*COSINE_ARMS, *BM25_ARMS, "rrf")


@dataclass(frozen=True)
class StoreSkillDoc:
    """One adopted skill in its two retrieval representations."""

    name: str
    filename: str
    theme: str
    full: str


@dataclass(frozen=True)
class Query:
    """One cluster or singleton as the retrieval gate would ask it."""

    query_id: str
    kind: str  # "cluster" | "singleton"
    size: int
    text: str
    member_ids: tuple[str, ...]
    previews: tuple[str, ...]
    vector: list[float] | None


# ------------------------------------------------------------------ loading


def _load_patterns(home: Path) -> tuple[list[dict], int, int]:
    """``(live ungated patterns, store size, live count)`` from knowledge.json.

    Mirrors ``core/insight.py::_select_patterns`` in ``--full`` mode plus
    ``_build_cluster_batches``' one hard exclusion (``gated`` patterns are
    ADR-0026 noise, dropped before clustering so noise centroids cannot pull
    real clusters toward themselves).
    """
    from contemplative_agent.core.memory import KnowledgeStore

    path = home / "knowledge.json"
    if not path.exists():
        raise ScanError("KNOWLEDGE_MISSING", str(path))
    store = KnowledgeStore(path=path)
    store.load()
    raw = store.get_raw_patterns()
    if not raw:
        # An empty in-memory list after load() is either a genuinely empty
        # store or a load that refused (tainted / unparsable file). Either
        # way there is no reading, and a 0-cluster report would look like a
        # finding rather than a fault.
        raise ScanError("KNOWLEDGE_EMPTY", str(path))
    live = store.get_live_patterns()
    return [p for p in live if not p.get("gated")], len(raw), len(live)


def _strip_frontmatter(text: str) -> str:
    from contemplative_agent.core.text_utils import split_frontmatter

    _frontmatter, body = split_frontmatter(text)
    return body


def load_skill_docs(skills_dir: Path) -> tuple[tuple[StoreSkillDoc, ...], int]:
    """Read ``skills_dir/*.md`` into ``(theme, full)`` documents; count unreadables.

    Same traversal contract as ``core/skill_selection.py::load_skill_catalog``
    (sorted glob, dotfiles skipped) and the same identity rule: the
    frontmatter ``name:`` wins over the filename stem, because the selector,
    the ledger and the novelty gate all speak the frontmatter name.
    """
    from contemplative_agent.core.text_utils import skill_theme

    if not skills_dir.is_dir():
        raise ScanError("SKILLS_DIR_MISSING", str(skills_dir))
    docs: list[StoreSkillDoc] = []
    unreadable = 0
    for path in sorted(skills_dir.glob("*.md")):
        if path.name.startswith("."):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        # UnicodeDecodeError is a ValueError, not an OSError.
        except (OSError, UnicodeDecodeError):
            unreadable += 1
            continue
        name, description = skill_theme(text, path.stem)
        docs.append(
            StoreSkillDoc(
                name=name,
                filename=path.name,
                theme=f"{name} — {description}".strip(),
                full=_strip_frontmatter(text).strip() or text.strip(),
            )
        )
    if not docs:
        raise ScanError("SKILLS_EMPTY", str(skills_dir))
    return tuple(docs), unreadable


# ----------------------------------------------------------------- queries


def _preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= TEXT_PREVIEW_CHARS else flat[:TEXT_PREVIEW_CHARS] + "…"


def build_queries(patterns: Sequence[dict]) -> tuple[list[Query], list[Query]]:
    """Cluster and singleton queries, using ``core/clustering`` directly.

    ``core/insight.py::_build_cluster_batches`` is mirrored rather than
    called: it returns only the batches the LLM would see, and this reading
    needs the singletons too (they are its negative class). Same thresholds,
    so the clusters are the ones the gate would actually have judged.
    """
    from contemplative_agent.core.clustering import cluster_patterns
    from contemplative_agent.core.insight import BATCH_SIZE, MIN_PATTERNS_REQUIRED
    from contemplative_agent.core.knowledge_store import pattern_id
    from contemplative_agent.core.thresholds import CLUSTER_THRESHOLD_INSIGHT

    clusters, singletons = cluster_patterns(
        list(patterns),
        threshold=CLUSTER_THRESHOLD_INSIGHT,
        min_size=MIN_PATTERNS_REQUIRED,
        max_size=BATCH_SIZE,
    )

    cluster_queries: list[Query] = []
    for index, members in enumerate(clusters, start=1):
        texts = [str(member.get("pattern", "")) for member in members]
        vectors = [member["embedding"] for member in members if member.get("embedding")]
        cluster_queries.append(
            Query(
                query_id=f"cluster-{index}",
                kind="cluster",
                size=len(members),
                text="\n".join(texts),
                member_ids=tuple(pattern_id(member) for member in members),
                previews=tuple(_preview(text) for text in texts),
                vector=_mean_vector(vectors),
            )
        )

    singleton_queries: list[Query] = []
    for member in singletons:
        text = str(member.get("pattern", ""))
        embedding = member.get("embedding")
        singleton_queries.append(
            Query(
                query_id=pattern_id(member),
                kind="singleton",
                size=1,
                text=text,
                member_ids=(pattern_id(member),),
                previews=(_preview(text),),
                vector=list(embedding) if embedding else None,
            )
        )
    return cluster_queries, singleton_queries


def _mean_vector(vectors: Sequence[Sequence[float]]) -> list[float] | None:
    """Centroid of a cluster's stored embeddings, or None when it has none.

    The stored vectors are used rather than re-embedding the joined text:
    7,700 rows already carry an embedding written by the same model, and
    re-embedding them would make the reading cost hours and change what is
    being measured (a joined multi-pattern string is not what the store's
    vectors represent).
    """
    import numpy as np

    usable = [v for v in vectors if v]
    if not usable:
        return None
    widths = {len(v) for v in usable}
    if len(widths) != 1:
        raise ScanError("STORED_EMBEDDING_RAGGED", f"widths={sorted(widths)}")
    return [float(x) for x in np.mean(np.asarray(usable, dtype=np.float64), axis=0)]


# ------------------------------------------------------------------- arms


def _embed_or_abstain(texts: Sequence[str], label: str) -> list[list[float]]:
    """Embed ``texts``, abstaining with a reason code instead of printing zeros.

    ``embed_texts`` fails soft to ``None``, and ``cosine`` fails soft to 0.0
    for a zero-norm or mis-shaped vector — together they would turn "the
    model is down" into "the store covers nothing", which is exactly the
    permissive direction for a gate that rejects candidates.
    """
    import numpy as np

    from contemplative_agent.core.embeddings import embed_texts

    matrix = embed_texts(list(texts))
    if matrix is None or len(matrix) != len(texts):
        raise ScanError("EMBEDDING_UNAVAILABLE", f"{label}: {len(texts)} texts")
    array = np.asarray(matrix, dtype=np.float64)
    if array.ndim != 2 or array.shape[1] == 0:
        raise ScanError("EMBEDDING_DEGENERATE", f"{label}: shape={array.shape}")
    if not np.isfinite(array).all() or not array.any(axis=1).all():
        raise ScanError("EMBEDDING_DEGENERATE", f"{label}: non-finite or zero-norm rows")
    return [[float(x) for x in row] for row in array]


@dataclass(frozen=True)
class Corpus:
    """The skill store prepared for every arm."""

    docs: tuple[StoreSkillDoc, ...]
    theme_vectors: list[list[float]]
    full_vectors: list[list[float]]
    theme_bm25: Bm25Index
    full_bm25: Bm25Index
    embedding_model: str


def build_corpus(docs: Sequence[StoreSkillDoc]) -> Corpus:
    from contemplative_agent.core.embeddings import _get_embedding_model

    names = [doc.name for doc in docs]
    return Corpus(
        docs=tuple(docs),
        theme_vectors=_embed_or_abstain([doc.theme for doc in docs], "skill themes"),
        full_vectors=_embed_or_abstain([doc.full for doc in docs], "skill bodies"),
        theme_bm25=build_bm25_index(names, [doc.theme for doc in docs]),
        full_bm25=build_bm25_index(names, [doc.full for doc in docs]),
        embedding_model=_get_embedding_model(),
    )


def _cosine_scores(
    query_vector: Sequence[float], doc_vectors: Sequence[Sequence[float]], names: Sequence[str]
) -> dict[str, float]:
    import numpy as np

    from contemplative_agent.core.embeddings import cosine

    vector = np.asarray(query_vector, dtype=np.float64)
    return {
        name: float(cosine(vector, np.asarray(doc, dtype=np.float64)))
        for name, doc in zip(names, doc_vectors, strict=True)
    }


def _top_n(scores: dict[str, float]) -> list[dict[str, Any]]:
    """Top ``TOP_N`` (name, score) rows, ties broken by name for determinism."""
    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"skill": name, "score": round(score, 6)} for name, score in ordered[:TOP_N]]


def _rrf_scores(left: dict[str, float], right: dict[str, float], rrf_k: int) -> dict[str, float]:
    fused: dict[str, float] = {}
    for scores in (left, right):
        ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
        for position, (name, _score) in enumerate(ranked, start=1):
            fused[name] = fused.get(name, 0.0) + 1.0 / (rrf_k + position)
    return fused


def score_query(query: Query, corpus: Corpus, rrf_k: int) -> dict[str, list[dict[str, Any]]]:
    """Every arm's top-``TOP_N`` for one query; a cosine arm is omitted when
    the query carries no stored vector (a pattern row written before
    embeddings, or a cluster of such rows). Omitted rather than zero-filled:
    an all-0.0 arm would enter the distributions as a genuine low score."""
    names = [doc.name for doc in corpus.docs]
    out: dict[str, list[dict[str, Any]]] = {}
    bm25_theme = bm25_scores_from_index(corpus.theme_bm25, query.text)
    bm25_full = bm25_scores_from_index(corpus.full_bm25, query.text)
    out["bm25_theme"] = _top_n(bm25_theme)
    out["bm25_full"] = _top_n(bm25_full)
    if query.vector is not None:
        cosine_full = _cosine_scores(query.vector, corpus.full_vectors, names)
        out["cosine_theme"] = _top_n(_cosine_scores(query.vector, corpus.theme_vectors, names))
        out["cosine_full"] = _top_n(cosine_full)
        out["rrf"] = _top_n(_rrf_scores(cosine_full, bm25_full, rrf_k))
    return out


# ------------------------------------------------------------ distributions


def _percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile; no numpy so a caller can read it."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no values")
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (q / 100.0)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _distribution(values: Sequence[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0, **{f"p{q}": None for q in QUANTILES}, "mean": None}
    return {
        "n": len(values),
        **{f"p{q}": round(_percentile(values, q), 6) for q in QUANTILES},
        "mean": round(statistics.fmean(values), 6),
    }


def _top1_values(rows: Sequence[dict[str, Any]], arm: str) -> list[float]:
    return [row["top3"][arm][0]["score"] for row in rows if row["top3"].get(arm)]


# ------------------------------------------------------------- LLM history


def llm_covered_rate(path: Path) -> dict[str, Any]:
    """Historical ``covered / clusters`` rate from the novelty gate's own log.

    Self-written audit (ADR-0075), read by exact path — never globbed out of
    the logs directory, which also holds episode logs the agent must not
    read. Only ``verdict == "judged"`` records count: a ``fail_open_*``
    record has an empty ``covered`` list because the call failed, and
    counting it would read as an LLM that covered nothing.
    """
    if not path.exists():
        return {"available": False, "reason": "NOVELTY_LOG_MISSING", "path": str(path)}
    judged = 0
    clusters = 0
    covered = 0
    unparsable = 0
    other_verdicts = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            unparsable += 1
            continue
        if not isinstance(record, dict):
            unparsable += 1
            continue
        if record.get("verdict") != "judged":
            other_verdicts += 1
            continue
        judged += 1
        clusters += len(record.get("clusters") or [])
        covered += len(record.get("covered") or [])
    if not clusters:
        return {"available": False, "reason": "NO_JUDGED_RECORDS", "path": str(path)}
    return {
        "available": True,
        "path": str(path),
        "judged_records": judged,
        "records_with_another_verdict": other_verdicts,
        "unparsable_lines": unparsable,
        "clusters_judged": clusters,
        "clusters_called_covered": covered,
        "covered_rate": round(covered / clusters, 4),
    }


# ---------------------------------------------------------------- assembly


def _cluster_rows(queries: Sequence[Query], corpus: Corpus, rrf_k: int) -> list[dict[str, Any]]:
    return [
        {
            "cluster_id": query.query_id,
            "kind": query.kind,
            "size": query.size,
            "member_ids": list(query.member_ids),
            "texts": list(query.previews),
            "top3": score_query(query, corpus, rrf_k),
        }
        for query in queries
    ]


def _coverage_at_thresholds(
    cluster_rows: Sequence[dict[str, Any]], singleton_rows: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """For each arm, what a gate at the singleton p50/p75/p90 would call covered.

    The thresholds come from the singletons rather than being chosen: they
    are the closest thing this store has to material it does not cover, so
    "a cluster scores above the median singleton" is a statement with a
    referent, where "a cluster scores above 0.7" is not.
    """
    out: dict[str, Any] = {}
    for arm in ARMS:
        cluster_values = _top1_values(cluster_rows, arm)
        singleton_values = _top1_values(singleton_rows, arm)
        if not cluster_values or not singleton_values:
            out[arm] = {"available": False, "reason": "NO_TOP1_SCORES"}
            continue
        rows = []
        for q in CANDIDATE_QUANTILES:
            threshold = _percentile(singleton_values, q)
            hits = sum(1 for value in cluster_values if value >= threshold)
            rows.append(
                {
                    "from_singleton_quantile": f"p{q}",
                    "threshold": round(threshold, 6),
                    "clusters_covered": hits,
                    "clusters": len(cluster_values),
                    "covered_fraction": round(hits / len(cluster_values), 4),
                }
            )
        out[arm] = {"available": True, "thresholds": rows}
    return out


def _rare_lane(singleton_rows: Sequence[dict[str, Any]], arm: str = "rrf") -> dict[str, Any]:
    """Singletons whose top-1 (``rrf``) falls below the singleton p25.

    The lane the novelty gate exists to protect: material with no near
    neighbour anywhere in the store. Named with ids so the reader can pull
    the rows, and sampled so the reading stays a table.
    """
    values = _top1_values(singleton_rows, arm)
    if not values:
        return {"available": False, "reason": "NO_TOP1_SCORES", "arm": arm}
    cutoff = _percentile(values, 25)
    rare = [
        row
        for row in singleton_rows
        if row["top3"].get(arm) and row["top3"][arm][0]["score"] < cutoff
    ]
    return {
        "available": True,
        "arm": arm,
        "cutoff_singleton_p25": round(cutoff, 6),
        "count": len(rare),
        "singletons_scored": len(values),
        "ids": [row["cluster_id"] for row in rare],
        "samples": [
            {"id": row["cluster_id"], "top1": row["top3"][arm][0], "text": row["texts"][0]}
            for row in rare[:RARE_LANE_SAMPLES]
        ],
    }


def build_reading(
    *,
    cluster_rows: Sequence[dict[str, Any]],
    singleton_rows: Sequence[dict[str, Any]],
    corpus: Corpus,
    home: Path,
    skills_dir: Path,
    rrf_k: int,
    store_size: int,
    live_count: int,
    ungated_count: int,
    unreadable_skills: int,
) -> dict[str, Any]:
    from contemplative_agent.core.insight import BATCH_SIZE, MIN_PATTERNS_REQUIRED
    from contemplative_agent.core.thresholds import CLUSTER_THRESHOLD_INSIGHT

    return {
        "question": (
            "If the insight novelty gate used retrieval against the skill store "
            "instead of a ~40k-token LLM judge, what would today's clusters look like?"
        ),
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "home": str(home),
            "skills_dir": str(skills_dir),
            "store_patterns": store_size,
            "live_patterns": live_count,
            "live_ungated_patterns": ungated_count,
            "clusters": len(cluster_rows),
            "singletons": len(singleton_rows),
            "skills": len(corpus.docs),
            "unreadable_skill_files": unreadable_skills,
            "cluster_threshold": CLUSTER_THRESHOLD_INSIGHT,
            "min_cluster_size": MIN_PATTERNS_REQUIRED,
            "max_cluster_size": BATCH_SIZE,
            "rrf_k": rrf_k,
            "embedding_model": corpus.embedding_model,
            "arms": list(ARMS),
        },
        "clusters": list(cluster_rows),
        "top1_distributions": {
            arm: {
                "clusters": _distribution(_top1_values(cluster_rows, arm)),
                "singletons": _distribution(_top1_values(singleton_rows, arm)),
            }
            for arm in ARMS
        },
        "coverage_at_thresholds": _coverage_at_thresholds(cluster_rows, singleton_rows),
        "rare_lane": _rare_lane(singleton_rows),
        "llm_history": llm_covered_rate(home / "logs" / "insight-novelty.jsonl"),
        "caveats": [
            "Singletons are a stand-in for uncovered material, not a labelled "
            "negative class: insight drops them before the gate, so nobody has "
            "ever judged whether the store covers them.",
            "The store is read as it is now; a skill adopted after a cluster "
            "was judged sits in the corpus anyway.",
            "The LLM covered rate is over historical batches with a different "
            "clustering window, so it bounds the order of magnitude, not the "
            "per-cluster agreement — nothing here is a paired comparison.",
        ],
    }


def _print_summary(reading: dict[str, Any]) -> None:
    provenance = reading["provenance"]
    print(
        f"novelty_retrieval_dry_run: {provenance['clusters']} clusters / "
        f"{provenance['singletons']} singletons over {provenance['skills']} skills "
        f"({provenance['live_ungated_patterns']} live ungated of "
        f"{provenance['store_patterns']} rows, rrf_k={provenance['rrf_k']})"
    )
    print("top-1 score, median (clusters vs singletons):")
    for arm, block in reading["top1_distributions"].items():
        clusters = block["clusters"]
        singletons = block["singletons"]
        print(
            f"  {arm:13s} clusters n={clusters['n']:4d} p50={clusters['p50']}"
            f"   singletons n={singletons['n']:5d} p50={singletons['p50']}"
        )
    print("clusters a retrieval gate would call covered, at singleton-derived thresholds:")
    for arm, block in reading["coverage_at_thresholds"].items():
        if not block.get("available"):
            print(f"  {arm:13s} unavailable ({block.get('reason')})")
            continue
        cells = "  ".join(
            f"{row['from_singleton_quantile']}={row['threshold']}→{row['covered_fraction']}"
            for row in block["thresholds"]
        )
        print(f"  {arm:13s} {cells}")
    rare = reading["rare_lane"]
    if rare.get("available"):
        print(
            f"rare lane (rrf top-1 < singleton p25={rare['cutoff_singleton_p25']}): "
            f"{rare['count']} of {rare['singletons_scored']} singletons"
        )
    history = reading["llm_history"]
    if history.get("available"):
        print(
            f"LLM judge, historical: {history['clusters_called_covered']}/"
            f"{history['clusters_judged']} clusters covered = {history['covered_rate']} "
            f"over {history['judged_records']} judged records"
        )
    else:
        print(f"LLM judge, historical: unavailable ({history.get('reason')})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only dry run of a retrieval-based insight novelty gate (RFC-0023)."
    )
    parser.add_argument(
        "--home",
        type=Path,
        default=Path(os.environ.get("MOLTBOOK_HOME") or DEFAULT_HOME),
        help="MOLTBOOK_HOME (default: $MOLTBOOK_HOME or ~/.config/moltbook)",
    )
    parser.add_argument("--skills-dir", type=Path, default=None, help="default: <home>/skills")
    parser.add_argument("--out", type=Path, required=True, help="where to write the reading JSON")
    parser.add_argument("--rrf-k", type=int, default=DEFAULT_RRF_K)
    parser.add_argument("--quiet", action="store_true", help="write the JSON, print nothing")
    args = parser.parse_args(argv)

    try:
        if args.rrf_k < 1:
            raise ScanError("BAD_RRF_K", str(args.rrf_k))
        home = args.home.expanduser()
        skills_dir = (args.skills_dir or home / "skills").expanduser()
        patterns, store_size, live_count = _load_patterns(home)
        docs, unreadable = load_skill_docs(skills_dir)
        cluster_queries, singleton_queries = build_queries(patterns)
        if not cluster_queries:
            raise ScanError("NO_CLUSTERS", f"{len(patterns)} live ungated patterns")
        corpus = build_corpus(docs)
        reading = build_reading(
            cluster_rows=_cluster_rows(cluster_queries, corpus, args.rrf_k),
            singleton_rows=_cluster_rows(singleton_queries, corpus, args.rrf_k),
            corpus=corpus,
            home=home,
            skills_dir=skills_dir,
            rrf_k=args.rrf_k,
            store_size=store_size,
            live_count=live_count,
            ungated_count=len(patterns),
            unreadable_skills=unreadable,
        )
    except ScanError as exc:
        # `reason=` token per the scripts/_scan.py contract; exit 2 is every
        # instrument's "the reading is unavailable", never a printed zero.
        print(f"novelty_retrieval_dry_run: reason={exc.reason} {exc.detail}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reading, indent=2, ensure_ascii=False), encoding="utf-8")
    if not args.quiet:
        _print_summary(reading)
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
