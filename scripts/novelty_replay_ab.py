#!/usr/bin/env python3
"""Differential replay of the insight novelty gate: full inventory vs top-k.

RFC-0023, packet S7. Answers "does gemma judge coverage differently when it is
shown k retrieved themes instead of the whole known inventory?" — a different
question from ``retrieval_recall_measure.py`` (which asked whether retrieval can
FIND the right skill at all).

Read-only with respect to ``$MOLTBOOK_HOME``: the judge prompts are
reconstructed from the base64 blobs already in ``logs/insight-novelty.jsonl``,
``llm.configure`` is never called (so no telemetry / audit sink is wired), and
every output lands in the path given by ``--out``.

One variable. Both arms replay the SAME chunks with the SAME cluster blocks,
the same system prompt, ``num_predict=2000``, ``drop_truncated=True`` and the
default temperature. The only difference is what fills the prompt's ``{known}``
slot:

* arm ``full``  — the whole inventory line-for-line, exactly as logged.
* arm ``topk``  — the union, over the chunk's clusters, of each cluster's top-k
  inventory lines by cosine (nomic) similarity, with a bm25 ranking recorded
  alongside as a reference column but never mixed in (RFC-0023's v2 reading:
  fusion did not beat cosine).

There is no seed knob: ``core/llm`` does not expose one, and the production gate
runs at the default temperature. That is precisely why ``--full-reps`` exists —
repeating arm ``full`` on identical input measures the judge's own jitter, which
is the floor any arm-to-arm difference has to clear.

Usage::

    python3 scripts/novelty_replay_ab.py --run-prefix 2026-09-04 \
        --full-reps 3 --k 5,10,15 --topk-reps 1 \
        --out docs/evidence/rfc-0023/novelty-replay-ab-20260905.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import statistics
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

# The BM25 implementation is the one already frozen for RFC-0023's recall
# reading — importing it keeps the reference column comparable to that JSON
# instead of introducing a second tokenizer nobody diffed.
from retrieval_recall_measure import (  # noqa: E402
    bm25_scores_from_index,
    build_bm25_index,
)

_KNOWN_HEADER = "## Existing themes"
_CLUSTER_HEADER = "## Candidate clusters"
_OUTPUT_HEADER = "## Output"
_CLUSTER_LEAD = "Each cluster is shown with a few sample patterns."

# ``_render_known_lines`` emits "- name: description" (or "- name" when the
# description is empty), so every inventory entry is one line starting "- ".
_KNOWN_LINE = re.compile(r"^- (?P<name>[^:]+?)(?:: (?P<description>.*))?$")

# ``_cluster_block`` emits "<topic>:" then "  - <sample>" lines.
_TOPIC_LINE = re.compile(r"^(?P<topic>\S[^\n]*?):$")


@dataclass(frozen=True)
class Cluster:
    """One candidate cluster as it appeared in a logged judge chunk."""

    # ``uid`` is chunk- and run-scoped. Within one run ``core/insight.py``
    # already numbers clusters globally before packing, so "cluster-N" is
    # unique there; the prefix exists to stop ids COLLIDING ACROSS RUNS.
    uid: str
    chunk_index: int
    cluster_id: str
    block: str  # verbatim render, reused byte-for-byte by both arms


@dataclass(frozen=True)
class Chunk:
    """One logged judge call: its cluster blocks and its logged verdict."""

    index: int
    clusters: tuple[Cluster, ...]
    logged_covered: frozenset[str]  # uids, from the record's own "covered"
    logged_verdict: str


def _split_prompt(prompt: str) -> tuple[str, str]:
    """Return ``(known_section, clusters_section)`` of a logged judge prompt."""
    known_start = prompt.index(_KNOWN_HEADER) + len(_KNOWN_HEADER)
    cluster_start = prompt.index(_CLUSTER_HEADER)
    output_start = prompt.index(_OUTPUT_HEADER)
    known = prompt[known_start:cluster_start].strip("\n")
    clusters = prompt[cluster_start + len(_CLUSTER_HEADER) : output_start].strip("\n")
    # Drop the template's fixed lead sentence, which sits between the header
    # and the first cluster block and is not part of any block.
    if clusters.startswith(_CLUSTER_LEAD):
        clusters = clusters[len(_CLUSTER_LEAD) :]
    return known, clusters.strip("\n")


def parse_known(section: str) -> list[tuple[str, str]]:
    """Inventory lines back into ``(name, description)`` pairs.

    A description containing ": " is safe — the name group is non-greedy and
    stops at the FIRST colon, which is where ``_render_known_lines`` put it.
    """
    themes: list[tuple[str, str]] = []
    for line in section.splitlines():
        match = _KNOWN_LINE.match(line.rstrip())
        if not match:
            continue
        themes.append((match["name"].strip(), (match["description"] or "").strip()))
    return themes


def parse_clusters(section: str, chunk_index: int) -> list[Cluster]:
    """Cluster blocks back into ``Cluster`` records, blocks kept verbatim.

    Blocks are separated by a blank line in the rendered prompt, and a sample
    line is indented — so a blank-line split is unambiguous even when a sample
    itself ends in a colon.
    """
    clusters: list[Cluster] = []
    for raw in section.split("\n\n"):
        block = raw.strip("\n")
        if not block:
            continue
        head = block.split("\n", 1)[0]
        match = _TOPIC_LINE.match(head)
        if not match:
            raise ValueError(f"chunk {chunk_index}: unparsable cluster head {head!r}")
        cluster_id = match["topic"]
        clusters.append(
            Cluster(
                uid=f"c{chunk_index}/{cluster_id}",
                chunk_index=chunk_index,
                cluster_id=cluster_id,
                block=block,
            )
        )
    return clusters


def _chunk_from_record(record: dict[str, Any]) -> tuple[str, str, Chunk]:
    """One logged judge record back into ``(known_section, Chunk)``.

    The parsed cluster ids are checked against the record's own ``clusters``
    field: that field is written independently of the prompt, so a mismatch
    means the prompt split is wrong and the replay would be judging something
    other than what production judged. The caller then applies the decisive
    check (``_assert_round_trip``) — id-set equality alone can pass on a lossy
    split, e.g. a description whose continuation line is dropped keeps the
    line count intact, and a sample containing a blank line can truncate a
    block while leaving the id set unchanged.
    """
    if record.get("output_truncated"):
        raise SystemExit("a logged output is truncated — its verdict is not the judge's")
    if record.get("prompt_truncated"):
        raise SystemExit("a logged prompt is truncated — it cannot be replayed")
    prompt = base64.b64decode(record["prompt_b64"]).decode("utf-8")
    section, cluster_section = _split_prompt(prompt)
    index = int(record.get("batch_index") or 0)
    clusters = parse_clusters(cluster_section, index)
    parsed_ids = {c.cluster_id for c in clusters}
    logged_ids = set(record.get("clusters") or [])
    if logged_ids != parsed_ids:
        raise SystemExit(
            f"chunk {index}: parsed cluster ids {sorted(parsed_ids)} != "
            f"logged {sorted(logged_ids)} — the prompt split is wrong"
        )
    return (
        section,
        prompt,
        Chunk(
            index=index,
            clusters=tuple(clusters),
            logged_covered=frozenset(f"c{index}/{cid}" for cid in (record.get("covered") or [])),
            logged_verdict=str(record.get("verdict")),
        ),
    )


def _records_for_run(audit_path: Path, run_prefix: str) -> list[dict[str, Any]]:
    """Audit records whose timestamp starts with ``run_prefix``, one regime only.

    The inventory grew 60 -> 485 across runs, so a prefix spanning two sizes
    would confound "shorter inventory" with "different inventory" — that is a
    stop, not a warning.
    """
    records: list[dict[str, Any]] = []
    with audit_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if str(record.get("ts", "")).startswith(run_prefix):
                records.append(record)
    if not records:
        raise SystemExit(f"no audit records with ts prefix {run_prefix!r}")
    known_counts = {r.get("known_themes_count") for r in records}
    if len(known_counts) != 1:
        raise SystemExit(
            f"run {run_prefix!r} straddles inventory sizes {sorted(known_counts)} — "
            "pin a narrower prefix (mixing regimes confounds the arms)"
        )
    return records


def _assert_round_trip(
    chunks: Sequence[Chunk], prompts: Sequence[str], known: Sequence[tuple[str, str]]
) -> None:
    """Rebuild each logged prompt from the parse and demand byte equality.

    This is the check that actually settles reconstruction fidelity. If the
    rebuilt prompt is identical to what production sent, then the ``full`` arm
    replays production exactly and the two arms differ in the ``{known}`` slot
    and nothing else — a claim the id-set and line-count checks can only
    support, never establish.
    """
    from contemplative_agent.core.prompts import INSIGHT_NOVELTY_PROMPT

    known_lines = render_known_lines(known)
    for chunk, logged in zip(chunks, prompts, strict=True):
        rebuilt = INSIGHT_NOVELTY_PROMPT.format(
            known=known_lines, clusters="\n\n".join(c.block for c in chunk.clusters)
        )
        if rebuilt != logged:
            raise SystemExit(
                f"chunk {chunk.index}: the rebuilt prompt differs from the logged one — "
                "the parse is lossy and the full arm would not be replaying production"
            )


def load_run(
    audit_path: Path, run_prefix: str
) -> tuple[list[Chunk], list[tuple[str, str]], dict[str, Any]]:
    """Reconstruct one judge run: its chunks, its inventory, its metadata.

    Only ``verdict="judged"`` records carry a prompt worth replaying, and the
    run is pinned by timestamp prefix so a comparison never straddles two
    inventory sizes (``known_themes_count`` grows 60 -> 485 across runs).
    """
    records = _records_for_run(audit_path, run_prefix)
    chunks: list[Chunk] = []
    prompts: list[str] = []
    known: list[tuple[str, str]] | None = None
    known_section = ""
    for record in sorted(records, key=lambda r: r.get("batch_index") or 0):
        if record.get("verdict") != "judged" or not record.get("prompt_b64"):
            continue
        section, prompt, chunk = _chunk_from_record(record)
        if known is None:
            known = parse_known(section)
            known_section = section
        elif section != known_section:
            raise SystemExit("chunks disagree on the known inventory")
        chunks.append(chunk)
        prompts.append(prompt)
    if known is None:
        raise SystemExit(f"run {run_prefix!r} has no judged record to replay")

    count = records[0]["known_themes_count"]
    if len(known) != count:
        raise SystemExit(
            f"parsed {len(known)} inventory lines but the record says {count} — "
            "the known-section split is lossy"
        )
    run_ids = {str(r["run_id"]) for r in records if r.get("run_id")}
    if len(run_ids) > 1:
        raise SystemExit(
            f"prefix {run_prefix!r} spans run ids {sorted(run_ids)} — cluster uids "
            "would collide across runs; pin one run"
        )
    _assert_round_trip(chunks, prompts, known)
    meta = {
        "run_prefix": run_prefix,
        "run_ids": sorted({str(r.get("run_id")) for r in records if r.get("run_id")}),
        "timestamps": sorted(str(r["ts"]) for r in records),
        "known_themes_count": count,
        "records_total": len(records),
        "records_judged": len(chunks),
        "verdicts_logged": sorted({str(r.get("verdict")) for r in records}),
    }
    return chunks, known, meta


def _generation_model() -> str:
    """The judge model this replay will actually call.

    ``llm`` resolves it from the environment at call time, so an artifact that
    records only the embedding model cannot back its own scoping claim.
    """
    from contemplative_agent.core import llm

    return llm._get_model()


def render_known_lines(themes: Sequence[tuple[str, str]]) -> str:
    """Byte-identical to ``core/insight_novelty.py::_render_known_lines``."""
    return "\n".join(
        f"- {name}: {description}" if description else f"- {name}" for name, description in themes
    )


def rank_known(
    clusters: Sequence[Cluster], known: Sequence[tuple[str, str]]
) -> tuple[dict[str, list[tuple[str, float]]], dict[str, list[tuple[str, float]]], str]:
    """Per-cluster rankings of the inventory: cosine (primary), bm25 (reference).

    The document text is the rendered inventory LINE, not the skill file — that
    line is all the audit log preserves, and it is also exactly what the full
    arm shows the judge, so the two arms differ in how many lines are shown and
    in nothing else.
    """
    from contemplative_agent.core.embeddings import _get_embedding_model, cosine, embed_texts

    names = [name for name, _ in known]
    lines = [f"{name}: {description}" if description else name for name, description in known]
    queries = [c.block for c in clusters]

    def embed_all(texts: Sequence[str], what: str) -> list[np.ndarray]:
        """Embed in small batches with a bounded retry.

        One 549-text POST was refused with HTTP 400 while the host was also
        holding the generation model resident; the same call had succeeded
        moments earlier against an idle host. Batching keeps each payload
        small and three attempts cover the transient — a failure that
        survives them stops the reading rather than degrading it.
        """
        rows: list[np.ndarray] = []
        for start in range(0, len(texts), 64):
            batch = list(texts[start : start + 64])
            for attempt in range(3):
                matrix = embed_texts(batch)
                if matrix is not None and len(matrix) == len(batch):
                    rows.extend(matrix)
                    break
                print(f"  embed retry {attempt + 1}/3 ({what} {start})", flush=True)
                time.sleep(5)
            else:
                raise SystemExit(f"EMBEDDING_UNAVAILABLE for the {what}")
        return rows

    doc_array = np.asarray(embed_all(lines, "inventory"), dtype=np.float64)
    query_array = np.asarray(embed_all(queries, "cluster blocks"), dtype=np.float64)
    if not np.isfinite(doc_array).all() or not np.isfinite(query_array).all():
        raise SystemExit("EMBEDDING_DEGENERATE (non-finite)")
    # ``cosine`` answers 0.0 for a zero-norm vector, which the finiteness check
    # cannot see. An all-zero response would score every document 0.0 and the
    # (-score, name) tie-break would hand back the alphabetically first k names
    # as if they were a ranking — a degraded reading that looks entirely valid.
    if (
        float(np.linalg.norm(doc_array, axis=1).min()) == 0.0
        or float(np.linalg.norm(query_array, axis=1).min()) == 0.0
    ):
        raise SystemExit("EMBEDDING_DEGENERATE (zero-norm row)")

    index = build_bm25_index(names, lines)
    cosine_ranks: dict[str, list[tuple[str, float]]] = {}
    bm25_ranks: dict[str, list[tuple[str, float]]] = {}
    for cluster, query_vector in zip(clusters, query_array, strict=True):
        scored = [(names[i], float(cosine(query_vector, doc_array[i]))) for i in range(len(names))]
        scored.sort(key=lambda item: (-item[1], item[0]))
        cosine_ranks[cluster.uid] = scored
        bm = bm25_scores_from_index(index, cluster.block)
        bm_sorted = sorted(bm.items(), key=lambda item: (-item[1], item[0]))
        bm25_ranks[cluster.uid] = bm_sorted
    return cosine_ranks, bm25_ranks, _get_embedding_model()


def topk_known_for_chunk(
    chunk: Chunk,
    ranks: dict[str, list[tuple[str, float]]],
    known: Sequence[tuple[str, str]],
    k: int,
) -> list[tuple[str, str]]:
    """Union of the chunk's clusters' top-k inventory entries.

    Kept in the inventory's own order rather than in score order: the full arm
    shows alphabetical-by-source order, and reordering would be a second
    variable riding along with the shortening.
    """
    by_name = dict(known)
    order = {name: position for position, (name, _) in enumerate(known)}
    picked: set[str] = set()
    for cluster in chunk.clusters:
        for name, _score in ranks[cluster.uid][:k]:
            picked.add(name)
    return [(name, by_name[name]) for name in sorted(picked, key=lambda n: order[n])]


def judge_chunk(chunk: Chunk, known_lines: str) -> tuple[set[str] | None, str, dict[str, Any]]:
    """One judge call with the production shape. Returns (covered uids, reason, stats).

    ``covered`` is ``None`` on any fail-open path, mirroring
    ``_filter_novel_batches``: an LLM failure and an unparseable verdict both
    leave the chunk's clusters unjudged rather than silently covered.
    """
    from contemplative_agent.core import llm
    from contemplative_agent.core.insight_novelty import _parse_covered_ids
    from contemplative_agent.core.prompts import (
        INSIGHT_NOVELTY_PROMPT,
        INSIGHT_NOVELTY_SYSTEM_PROMPT,
    )

    blocks = "\n\n".join(c.block for c in chunk.clusters)
    prompt = INSIGHT_NOVELTY_PROMPT.format(known=known_lines, clusters=blocks)
    stats = {
        "prompt_chars": len(prompt),
        "prompt_tokens_est": llm._estimate_tokens(prompt)
        + llm._estimate_tokens(INSIGHT_NOVELTY_SYSTEM_PROMPT),
        "known_lines": len(known_lines.splitlines()),
        "clusters": len(chunk.clusters),
    }
    started = time.monotonic()
    out = llm.generate_full(
        prompt,
        system=INSIGHT_NOVELTY_SYSTEM_PROMPT,
        num_predict=2000,
        caller="insight.novelty",
        drop_truncated=True,
    )
    stats["seconds"] = round(time.monotonic() - started, 2)
    if out is None or out.text is None:
        return None, "fail_open_llm", stats
    ids = {c.cluster_id for c in chunk.clusters}
    covered = _parse_covered_ids(out.text, ids)
    stats["output_chars"] = len(out.text)
    if covered is None:
        stats["output_head"] = out.text[:400]
        return None, "fail_open_parse", stats
    return {f"c{chunk.index}/{cid}" for cid in covered}, "judged", stats


def run_arm(
    chunks: Sequence[Chunk],
    known_lines_for: Callable[[Chunk], str],
    label: str,
) -> dict[str, Any]:
    """Judge every chunk once under one ``{known}`` policy."""
    covered: set[str] = set()
    # Only the two reachable reasons. ``fail_open_budget`` belongs to
    # production's packer, which the replay reuses rather than re-runs — a
    # zero here would be structural, not measured, and would read as a finding.
    fail_open: dict[str, list[str]] = {"fail_open_llm": [], "fail_open_parse": []}
    per_chunk: list[dict[str, Any]] = []
    for chunk in chunks:
        known_lines = known_lines_for(chunk)
        chunk_covered, reason, stats = judge_chunk(chunk, known_lines)
        if chunk_covered is None:
            fail_open[reason].extend(c.uid for c in chunk.clusters)
        else:
            covered |= chunk_covered
        per_chunk.append({"chunk": chunk.index, "verdict": reason, **stats})
        print(
            f"  [{label}] chunk {chunk.index}: {reason} "
            f"covered={len(chunk_covered or ())} "
            f"prompt_tok≈{stats['prompt_tokens_est']} {stats['seconds']}s",
            flush=True,
        )
    return {
        "label": label,
        "covered": sorted(covered),
        "fail_open": {reason: sorted(uids) for reason, uids in fail_open.items()},
        "per_chunk": per_chunk,
    }


def _pairwise(reps: Sequence[set[str]]) -> list[dict[str, Any]]:
    """Every unordered pair of repetitions, as agreement numbers."""
    rows: list[dict[str, Any]] = []
    for i in range(len(reps)):
        for j in range(i + 1, len(reps)):
            a, b = reps[i], reps[j]
            union = a | b
            rows.append(
                {
                    "pair": [i + 1, j + 1],
                    "a": len(a),
                    "b": len(b),
                    "both": len(a & b),
                    "disagree": len(a ^ b),
                    "jaccard": round(len(a & b) / len(union), 4) if union else 1.0,
                }
            )
    return rows


def _spread(values: Sequence[float]) -> dict[str, Any]:
    """min / median / max / mean of a sample, with its n — never a lone number."""
    ordered = sorted(values)
    return {
        "n": len(ordered),
        "min": ordered[0],
        "median": statistics.median(ordered),
        "max": ordered[-1],
        "mean": round(statistics.fmean(ordered), 2),
    }


def analyze(path: Path) -> dict[str, Any]:
    """Turn a replay JSON into the pre-registered readings.

    Two things this deliberately does NOT smooth over:

    * **The consensus rule is not the same estimator at every arm size.** A
      majority of 3 reps is 2-of-3; a "majority" of 2 reps is 2-of-2, i.e. an
      intersection. Comparing a 3-rep majority against a 2-rep intersection
      under-counts the 2-rep arm's coverage, which biases drop rates UP and
      new-coverage rates DOWN. Each family therefore reports its own
      ``consensus_rule``, and the honest readings — restricted to the clusters
      the full arm was unanimous about — are computed alongside.
    * **A fail-open cluster was never judged.** Folding it in as "novel" would
      let a bad host read as an arm covering less, so every cluster any rep
      failed open on is excluded from the comparison universe and reported.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    all_uids = [c["uid"] for c in data["clusters"]]
    arms = data["arms"]

    families: dict[str, list[str]] = {}
    for label in arms:
        families.setdefault(label.split("/")[0], []).append(label)
    for labels in families.values():
        labels.sort()

    unjudged = {uid for arm in arms.values() for uids in arm["fail_open"].values() for uid in uids}
    uids = [uid for uid in all_uids if uid not in unjudged]
    total = len(uids)

    covered = {label: set(arm["covered"]) for label, arm in arms.items()}

    def consensus(labels: Sequence[str]) -> set[str]:
        need = len(labels) / 2
        return {uid for uid in uids if sum(uid in covered[la] for la in labels) > need}

    def rule(labels: Sequence[str]) -> str:
        n = len(labels)
        floor = n // 2 + 1
        return f"{floor}-of-{n}" + (" (unanimity = intersection)" if floor == n else " majority")

    full_labels = families["full"]
    votes = {uid: sum(uid in covered[la] for la in full_labels) for uid in uids}
    unanimous_covered = [uid for uid in uids if votes[uid] == len(full_labels)]
    unanimous_novel = [uid for uid in uids if votes[uid] == 0]
    base = consensus(full_labels)

    readings: dict[str, Any] = {
        "clusters_total": len(all_uids),
        "clusters_compared": total,
        "excluded_unjudged": sorted(unjudged),
        "generation_model": data.get("generation_model"),
        "embedding_model": data.get("embedding_model"),
        "jitter": {
            "reps": len(full_labels),
            "per_rep_covered": [len(covered[la]) for la in full_labels],
            "pairwise": _pairwise([covered[la] for la in full_labels]),
            "vote_histogram": {
                str(v): sum(1 for uid in uids if votes[uid] == v)
                for v in range(len(full_labels) + 1)
            },
            "unstable_clusters": total - len(unanimous_covered) - len(unanimous_novel),
            "unstable_rate": (
                round((total - len(unanimous_covered) - len(unanimous_novel)) / total, 4)
                if total
                else 0.0
            ),
            "unanimous_covered": len(unanimous_covered),
            "unanimous_novel": len(unanimous_novel),
            "consensus_covered": len(base),
            "consensus_rule": rule(full_labels),
        },
        "logged_production_run": {
            "covered": len(data["logged"]["covered"]),
            "vs_full_consensus_disagree": len((set(data["logged"]["covered"]) & set(uids)) ^ base),
        },
        "cross_arm_single_rep": {},
        "arms": {},
    }

    for family, labels in families.items():
        if family == "full":
            continue
        readings["cross_arm_single_rep"][f"full_vs_{family}"] = _spread(
            [
                len(covered[a] & set(uids) ^ (covered[b] & set(uids)))
                for a in full_labels
                for b in labels
            ]
        )
    readings["cross_arm_single_rep"]["full_vs_full"] = _spread(
        [row["disagree"] for row in readings["jitter"]["pairwise"]]
    )

    for family, labels in families.items():
        cov = consensus(labels)
        dropped = base - cov
        added = cov - base
        reps = [covered[la] for la in labels]
        readings["arms"][family] = {
            "reps": len(labels),
            "consensus_rule": rule(labels),
            "per_rep_covered": [len(r) for r in reps],
            "consensus_covered": len(cov),
            "dropped_from_full": len(dropped),
            "drop_rate_of_full_covered": (round(len(dropped) / len(base), 4) if base else None),
            "newly_covered": len(added),
            "new_rate_of_all_clusters": round(len(added) / total, 4) if total else 0.0,
            # The estimator-free version: restricted to what the full arm never
            # wavered on, reported at both ends of the rep spread.
            "stable_covered_kept_all_reps": sum(
                1 for uid in unanimous_covered if all(uid in r for r in reps)
            ),
            "stable_covered_kept_any_rep": sum(
                1 for uid in unanimous_covered if any(uid in r for r in reps)
            ),
            "stable_novel_flipped_all_reps": sum(
                1 for uid in unanimous_novel if all(uid in r for r in reps)
            ),
            "stable_novel_flipped_any_rep": sum(
                1 for uid in unanimous_novel if any(uid in r for r in reps)
            ),
            "fail_open_per_rep": [
                sum(len(v) for v in arms[la]["fail_open"].values()) for la in labels
            ],
            "prompt_tokens_est": _spread(
                [c["prompt_tokens_est"] for la in labels for c in arms[la]["per_chunk"]]
            ),
            "known_lines": _spread(
                [c["known_lines"] for la in labels for c in arms[la]["per_chunk"]]
            ),
            "chunks_per_rep": len(arms[labels[0]]["per_chunk"]),
            "within_arm_pairwise": _pairwise(reps) if len(reps) > 1 else [],
            "dropped_uids": sorted(dropped),
            "newly_covered_uids": sorted(added),
        }
    readings["denominators"] = {
        "unanimous_covered": len(unanimous_covered),
        "unanimous_novel": len(unanimous_novel),
        "full_consensus_covered": len(base),
        "clusters_compared": total,
    }
    return readings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    default_home = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
    parser.add_argument(
        "--audit-log", type=Path, default=default_home / "logs" / "insight-novelty.jsonl"
    )
    parser.add_argument("--run-prefix", default="2026-09-04")
    parser.add_argument("--full-reps", type=int, default=3)
    parser.add_argument("--topk-reps", type=int, default=1)
    parser.add_argument("--k", default="5,10,15")
    parser.add_argument(
        "--limit-chunks",
        type=int,
        default=0,
        help="smoke mode: replay only the first N chunks (0 = all)",
    )
    parser.add_argument("--out", type=Path)
    parser.add_argument(
        "--analyze",
        type=Path,
        help="read a replay JSON and print the pre-registered readings, no calls",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="rank the inventory and write the plan without any judge call",
    )
    args = parser.parse_args(argv)

    if args.analyze:
        print(json.dumps(analyze(args.analyze), indent=2, ensure_ascii=False))
        return 0
    if args.out is None:
        parser.error("--out is required unless --analyze is given")

    ks = tuple(int(part) for part in args.k.split(",") if part.strip())
    chunks, known, meta = load_run(args.audit_log, args.run_prefix)
    if args.limit_chunks:
        chunks = chunks[: args.limit_chunks]
    all_clusters = [c for chunk in chunks for c in chunk.clusters]
    print(
        f"run {args.run_prefix}: {len(chunks)} chunk(s), {len(all_clusters)} cluster(s), "
        f"{len(known)} known themes",
        flush=True,
    )

    cosine_ranks, bm25_ranks, embedding_model = rank_known(all_clusters, known)
    full_lines = render_known_lines(known)

    result: dict[str, Any] = {
        "schema": "novelty-replay-ab/1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "args": vars(args) | {"audit_log": str(args.audit_log), "out": str(args.out)},
        "run": meta,
        "embedding_model": embedding_model,
        "generation_model": _generation_model(),
        "clusters": [
            {
                "uid": c.uid,
                "chunk": c.chunk_index,
                "cluster_id": c.cluster_id,
                "block_chars": len(c.block),
                "cosine_top15": [
                    {"name": n, "score": round(s, 4)} for n, s in cosine_ranks[c.uid][:15]
                ],
                "bm25_top15": [
                    {"name": n, "score": round(s, 4)} for n, s in bm25_ranks[c.uid][:15]
                ],
            }
            for c in all_clusters
        ],
        "logged": {
            "covered": sorted(uid for chunk in chunks for uid in chunk.logged_covered),
            "note": "the 2026-09-04 production verdict, for reference only",
        },
        "arms": {},
    }
    if args.retrieval_only:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {args.out} (retrieval only)")
        return 0

    started = time.monotonic()
    for rep in range(args.full_reps):
        label = f"full/rep{rep + 1}"
        print(f"arm {label}", flush=True)
        result["arms"][label] = run_arm(chunks, lambda _chunk: full_lines, label)
    for k in ks:
        for rep in range(args.topk_reps):
            label = f"topk{k}/rep{rep + 1}"
            print(f"arm {label}", flush=True)
            result["arms"][label] = run_arm(
                chunks,
                lambda chunk, k=k: render_known_lines(
                    topk_known_for_chunk(chunk, cosine_ranks, known, k)
                ),
                label,
            )
    result["elapsed_seconds"] = round(time.monotonic() - started, 1)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out} ({result['elapsed_seconds']}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
