#!/usr/bin/env python3
"""Select the RFC-0027 fixed comparison set from the production record (read-only).

One-time selection helper for the RFC-0027 one-shot comparison. It reads the
runtime knowledge store and a skills snapshot through explicit paths, never
writes to ``MOLTBOOK_HOME``, never touches staging / adopt, and emits exactly two
files, both confined by ``_validate_output_path`` to ``WRITABLE_ROOTS``
(``docs/evidence/rfc-0027/`` or ``evals/fixtures/``): the case JSON consumed by
``scripts/insight_revision_compare.py`` (``schema_version: 1``), written to
``evals/fixtures/`` as the frozen production fixture, and a selection sidecar
under ``docs/evidence/rfc-0027/`` recording how each case was picked plus its
holdout scene.

The four kinds (reconfirm / insufficient / revise / new) are **diagnostic
labels for the selection rule**, not success labels and not ground truth about
what the pipeline ought to output. They say which corner of the record a case
came from, so a reader can see the input spread; they do not say which answer
is correct.

The case schema forbids extra keys, so the holdout scene (a pattern from a
different day that was NOT fed to either arm) lives in the sidecar, not in the
case file.

CLOSED DEFECT (2026-09-12): ``_case_row`` prefixes the case id with the kind
label, and the first run's comparison harness fed ``case_id`` into the current
arm's extraction prompt (``{subcategory}``), leaking the selection label into
one arm only. The harness side is repaired — ``insight_revision_compare.py``
fills that slot from ``DEFAULT_SUBCATEGORY`` or an explicit per-case
``subcategory`` and rejects any case whose ``subcategory`` contains its
``case_id``, so the id can no longer reach a prompt. The kind prefix stays here
only so the frozen fixture remains byte-reproducible from this file, and
``kind_label`` stays in the sidecar. Evidence: the leaked first run is
``docs/evidence/rfc-0027/comparison-2026-09-12.md``, the post-repair re-run is
``docs/evidence/rfc-0027/comparison-2026-09-12-rerun.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

import numpy as np

from contemplative_agent.core.embeddings import embed_texts

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = REPO_ROOT / "docs" / "evidence" / "rfc-0027"
FIXTURE_ROOT = REPO_ROOT / "evals" / "fixtures"
WRITABLE_ROOTS = (EVIDENCE_ROOT, FIXTURE_ROOT)

# Publication filter: a distilled pattern is the agent's own prose, but it can
# still carry a verbatim span of somebody else's post. Anything matching these
# is dropped from the population rather than transcribed into public evidence.
THIRD_PARTY_MARKERS = (
    re.compile(r"https?://"),
    re.compile(r"@[A-Za-z0-9_]{2,}"),
    # Quoted spans of 25+ characters, in any quote style the distiller uses.
    # A distilled pattern is the agent's own prose, but it quotes the other
    # party verbatim often enough that an unquoted-only filter still shipped
    # somebody else's sentence into public evidence (observed 2026-09-12 on
    # the first generated set). Straight and curly single quotes included.
    re.compile(r"[\"“「『][^\"”」』]{25,}[\"”」』]"),
    re.compile(r"['’][^'’]{25,}['’]"),
)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _publishable(text: str) -> bool:
    return not any(marker.search(text) for marker in THIRD_PARTY_MARKERS)


def _load_population(
    knowledge_path: Path, *, window_start: str, window_end: str
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Load the store once and return the window's live, publishable patterns."""
    records = json.loads(knowledge_path.read_text(encoding="utf-8"))
    counts = {
        "total": len(records),
        "expired": 0,
        "out_of_window": 0,
        "third_party": 0,
        "duplicate": 0,
        "no_embedding": 0,
        "kept": 0,
    }
    seen: set[str] = set()
    kept: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        if record.get("valid_until") is not None:
            counts["expired"] += 1
            continue
        source = str(record.get("source") or "")
        if not (window_start <= source <= window_end):
            counts["out_of_window"] += 1
            continue
        text = str(record.get("pattern") or "").strip()
        if not _publishable(text):
            counts["third_party"] += 1
            continue
        digest = _sha256(text)
        if digest in seen:
            counts["duplicate"] += 1
            continue
        embedding = record.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            counts["no_embedding"] += 1
            continue
        seen.add(digest)
        kept.append(
            {
                "id": f"p{index:05d}-{source}",
                "text": text,
                "source": source,
                "sha256": digest,
                "embedding": np.asarray(embedding, dtype=np.float32),
            }
        )
    counts["kept"] = len(kept)
    return kept, counts


def _load_skills(skills_dir: Path) -> list[dict[str, str]]:
    skills: list[dict[str, str]] = []
    for path in sorted(skills_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            continue
        skills.append({"name": path.stem, "text": text})
    return skills


def _unit(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _cluster(sim: np.ndarray, threshold: float) -> list[list[int]]:
    """Single-link connected components over the pattern-pattern similarity."""
    size = sim.shape[0]
    parent = list(range(size))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for i in range(size):
        for j in range(i + 1, size):
            if sim[i, j] >= threshold:
                a, b = find(i), find(j)
                if a != b:
                    parent[a] = b
    groups: dict[int, list[int]] = {}
    for i in range(size):
        groups.setdefault(find(i), []).append(i)
    return sorted(groups.values(), key=lambda g: (-len(g), g[0]))


def _case_row(
    kind: str,
    members: list[int],
    patterns: list[dict[str, Any]],
    skills: list[dict[str, str]],
    skill_sim: np.ndarray,
    pattern_sim: np.ndarray,
    *,
    max_patterns: int,
    max_skills: int,
) -> dict[str, Any]:
    members = members[:max_patterns]
    centroid = skill_sim[members].mean(axis=0)
    order = np.argsort(-centroid)[:max_skills]
    picked_skills = [skills[i] for i in order]
    case_id = f"{kind}-{patterns[members[0]]['id']}"
    holdout = None
    member_sources = {patterns[i]["source"] for i in members}
    pattern_centroid = pattern_sim[members].mean(axis=0)
    for index in np.argsort(-pattern_centroid):
        if index in members or patterns[index]["source"] in member_sources:
            continue
        holdout = {
            "pattern_id": patterns[index]["id"],
            "source": patterns[index]["source"],
            "text": patterns[index]["text"],
            "similarity_to_case_centroid": round(float(pattern_centroid[index]), 4),
        }
        break
    return {
        "case": {
            "case_id": case_id,
            "patterns": [{"id": patterns[i]["id"], "text": patterns[i]["text"]} for i in members],
            "existing_skills": [{"name": s["name"], "text": s["text"]} for s in picked_skills],
        },
        "selection": {
            "case_id": case_id,
            "kind_label": kind,
            "pattern_ids": [patterns[i]["id"] for i in members],
            "pattern_sources": sorted({patterns[i]["source"] for i in members}),
            "pattern_sha256": [patterns[i]["sha256"] for i in members],
            "top_skill": skills[int(order[0])]["name"],
            "top_skill_similarity": round(float(centroid[int(order[0])]), 4),
            "supplied_skills": [skills[int(i)]["name"] for i in order],
            "cluster_size": len(members),
            "holdout_scene": holdout,
        },
    }


def _geometry(
    patterns: list[dict[str, Any]],
    skills: list[dict[str, str]],
    *,
    cluster_threshold: float,
    max_patterns: int,
) -> tuple[
    np.ndarray, np.ndarray, list[tuple[list[int], float, float]], list[tuple[int, float]], int
]:
    """Similarity matrices plus each candidate's (coverage, cohesion)."""
    pattern_matrix = _unit(np.vstack([p["embedding"] for p in patterns]))
    skill_embeddings = embed_texts([s["text"] for s in skills])
    if skill_embeddings is None or skill_embeddings.shape[0] != len(skills):
        raise RuntimeError("skill embedding failed; selection cannot proceed")
    skill_matrix = _unit(np.asarray(skill_embeddings, dtype=np.float32))
    skill_sim = pattern_matrix @ skill_matrix.T
    pattern_sim = pattern_matrix @ pattern_matrix.T

    clusters = _cluster(pattern_sim, cluster_threshold)
    multi: list[tuple[list[int], float, float]] = []
    singletons: list[tuple[int, float]] = []
    for members in clusters:
        if len(members) >= 3:
            ranked = pattern_sim[np.ix_(members, members)].mean(axis=1)
            trimmed = [members[i] for i in np.argsort(-ranked)[:max_patterns]]
            size = len(trimmed)
            block = pattern_sim[np.ix_(trimmed, trimmed)]
            cohesion = float((block.sum() - size) / (size * size - size))
            coverage = float(skill_sim[trimmed].mean(axis=0).max())
            multi.append((trimmed, coverage, cohesion))
        elif len(members) == 1:
            singletons.append((members[0], float(skill_sim[members[0]].max())))
    if not multi:
        raise RuntimeError("no multi-pattern cluster at this cluster threshold")
    return skill_sim, pattern_sim, multi, singletons, len(clusters)


def _buckets(
    patterns: list[dict[str, Any]],
    multi: list[tuple[list[int], float, float]],
    singletons: list[tuple[int, float]],
    *,
    coverage_high_q: float,
    coverage_low_q: float,
    cohesion_q: float,
    singleton_length_q: float,
) -> tuple[dict[str, list[list[int]]], dict[str, float]]:
    """Split candidates into the four corners at this corpus's quantiles."""
    coverages = np.array([row[1] for row in multi])
    cohesions = np.array([row[2] for row in multi])
    cov_hi = float(np.quantile(coverages, coverage_high_q))
    cov_lo = float(np.quantile(coverages, coverage_low_q))
    coh_mid = float(np.quantile(cohesions, cohesion_q))
    single_cov = np.array([row[1] for row in singletons]) if singletons else np.zeros(1)
    single_len = (
        np.array([len(patterns[i]["text"]) for i, _ in singletons]) if singletons else np.zeros(1)
    )
    cov_single = float(np.quantile(single_cov, coverage_low_q))
    len_cut = float(np.quantile(single_len, singleton_length_q))

    buckets: dict[str, list[list[int]]] = {
        k: [] for k in ("reconfirm", "revise", "new", "insufficient")
    }
    for trimmed, coverage, cohesion in multi:
        if coverage >= cov_hi:
            buckets["reconfirm" if cohesion >= coh_mid else "revise"].append(trimmed)
        elif coverage <= cov_lo:
            buckets["new"].append(trimmed)
    for index, coverage in singletons:
        if coverage <= cov_single and len(patterns[index]["text"]) <= len_cut:
            buckets["insufficient"].append([index])
    thresholds = {
        "coverage_high": round(cov_hi, 4),
        "coverage_low": round(cov_lo, 4),
        "cohesion_split": round(coh_mid, 4),
        "singleton_coverage_max": round(cov_single, 4),
        "singleton_length_max": round(len_cut, 1),
    }
    return buckets, thresholds


def select(
    patterns: list[dict[str, Any]],
    skills: list[dict[str, str]],
    *,
    cluster_threshold: float,
    coverage_high_q: float,
    coverage_low_q: float,
    cohesion_q: float,
    singleton_length_q: float,
    per_kind: int,
    max_patterns: int,
    max_skills: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Place every candidate on two geometric axes and take four corners.

    * coverage = similarity between the case centroid and its nearest existing
      skill: how well the catalogue already speaks to this material.
    * cohesion = mean pairwise similarity inside the case: whether the
      observations repeat one thing or spread across varying conditions.

    The four kinds are the corners of that plane (covered+tight, covered+spread,
    uncovered cluster, thin singleton). They label where a case was drawn from,
    not what either arm ought to answer. Thresholds are quantiles of THIS
    corpus, not absolute numbers: nomic similarity is compressed into a narrow
    band (ADR-0071 calibration), so a fixed cutoff would silently mean
    something different on another store.
    """
    skill_sim, pattern_sim, multi, singletons, cluster_count = _geometry(
        patterns, skills, cluster_threshold=cluster_threshold, max_patterns=max_patterns
    )
    buckets, thresholds = _buckets(
        patterns,
        multi,
        singletons,
        coverage_high_q=coverage_high_q,
        coverage_low_q=coverage_low_q,
        cohesion_q=cohesion_q,
        singleton_length_q=singleton_length_q,
    )

    def rank(kind: str, members: list[int]) -> tuple:
        coverage = float(skill_sim[members].mean(axis=0).max())
        # Take each corner's most extreme members first, so the set is the
        # clearest instance of the corner rather than its boundary.
        primary = -coverage if kind in {"reconfirm", "revise"} else coverage
        return (primary, patterns[members[0]]["id"])

    cases: list[dict[str, Any]] = []
    selections: list[dict[str, Any]] = []
    used: set[int] = set()
    for kind in ("reconfirm", "revise", "new", "insufficient"):
        chosen = 0
        for members in sorted(buckets[kind], key=lambda m: rank(kind, m)):
            if chosen >= per_kind:
                break
            if any(i in used for i in members):
                continue
            row = _case_row(
                kind,
                members,
                patterns,
                skills,
                skill_sim,
                pattern_sim,
                max_patterns=max_patterns,
                max_skills=max_skills,
            )
            used.update(members)
            cases.append(row["case"])
            selections.append(row["selection"])
            chosen += 1
        if chosen < per_kind:
            raise RuntimeError(f"only {chosen} candidate(s) available for kind {kind}")

    stats = {
        "population": len(patterns),
        "skills": len(skills),
        "clusters": cluster_count,
        "multi_pattern_clusters": len(multi),
        "singletons": len(singletons),
        "bucket_sizes": {k: len(v) for k, v in buckets.items()},
        "thresholds": {"cluster_similarity": cluster_threshold, **thresholds},
        "quantiles": {
            "coverage_high_q": coverage_high_q,
            "coverage_low_q": coverage_low_q,
            "cohesion_q": cohesion_q,
            "singleton_length_q": singleton_length_q,
        },
    }
    return cases, selections, stats


def _validate_output_path(path: Path) -> None:
    """Writes are confined to the frozen-evidence and fixture directories.

    The selection reads the live store; keeping its only write targets inside
    the repo is what makes "read-only against MOLTBOOK_HOME" checkable rather
    than asserted.
    """
    resolved = path.expanduser().resolve()
    for root in WRITABLE_ROOTS:
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        return
    allowed = ", ".join(str(root) for root in WRITABLE_ROOTS)
    raise ValueError(f"output path must live under one of: {allowed}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--knowledge", type=Path, required=True)
    parser.add_argument("--skills", type=Path, required=True)
    parser.add_argument("--out-cases", type=Path, required=True)
    parser.add_argument("--out-selection", type=Path, required=True)
    parser.add_argument("--window-start", default="2026-07-01")
    parser.add_argument("--window-end", default="2026-09-11")
    parser.add_argument("--cluster-threshold", type=float, default=0.76)
    parser.add_argument("--coverage-high-q", type=float, default=0.75)
    parser.add_argument("--coverage-low-q", type=float, default=0.25)
    parser.add_argument("--cohesion-q", type=float, default=0.5)
    parser.add_argument("--singleton-length-q", type=float, default=0.25)
    parser.add_argument("--per-kind", type=int, default=3)
    parser.add_argument("--max-patterns", type=int, default=4)
    parser.add_argument("--max-skills", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true", help="print stats only")
    args = parser.parse_args(argv)

    patterns, counts = _load_population(
        args.knowledge, window_start=args.window_start, window_end=args.window_end
    )
    skills = _load_skills(args.skills)
    cases, selections, stats = select(
        patterns,
        skills,
        cluster_threshold=args.cluster_threshold,
        coverage_high_q=args.coverage_high_q,
        coverage_low_q=args.coverage_low_q,
        cohesion_q=args.cohesion_q,
        singleton_length_q=args.singleton_length_q,
        per_kind=args.per_kind,
        max_patterns=args.max_patterns,
        max_skills=args.max_skills,
    )
    stats["filter_counts"] = counts
    stats["window"] = [args.window_start, args.window_end]
    if args.dry_run:
        print(json.dumps(stats, ensure_ascii=False, indent=2))
        return 0

    for path in (args.out_cases, args.out_selection):
        _validate_output_path(path)
    args.out_cases.parent.mkdir(parents=True, exist_ok=True)
    args.out_selection.parent.mkdir(parents=True, exist_ok=True)
    args.out_cases.write_text(
        json.dumps({"schema_version": 1, "cases": cases}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.out_selection.write_text(
        json.dumps({"stats": stats, "selections": selections}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
