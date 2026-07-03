"""F5 measurement: retrieval scoring factor analysis.

Compares three scoring variants over the same production candidate pool:
- V_current:    (alpha*cos + beta*bm25) * trust      (ADR-0021+0022 live)
- V_notrust:    (alpha*cos + beta*bm25) * 1.0        (trust factor neutralised)
- V_cosineonly: cos * 1.0                            (pre-ADR-0021 equivalent)

Reports Jaccard@10, Kendall tau on rank intersection, top-1/top-3 agreement
per view and aggregate.

READ-ONLY. Never writes knowledge.json.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Tuple

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from contemplative_agent.core.embeddings import cosine, embed_one  # noqa: E402 — sys.path hack precedes imports by design
from contemplative_agent.core.forgetting import is_live  # noqa: E402
from contemplative_agent.core.views import (  # noqa: E402
    _compute_bm25_scores,
    _parse_seed_file,
)

KNOWLEDGE_PATH = Path(os.path.expanduser("~/.config/moltbook/knowledge.json"))
USER_VIEWS_DIR = Path(os.path.expanduser("~/.config/moltbook/views"))
REPO_VIEWS_DIR = REPO / "config" / "views"
TOP_K = 10
VIEW_NAMES = [
    "technical",
    "reasoning",
    "communication",
    "self_reflection",
    "constitutional",
    "social",
]


def _rank_variant(
    seed_emb: np.ndarray,
    candidates: List[Dict],
    threshold: float,
    top_k: int,
    *,
    bm25_scores: Optional[Mapping[int, float]],
    alpha: float,
    beta: float,
    use_trust: bool,
) -> List[Dict]:
    """Score and return top_k patterns. trust factor on/off via use_trust."""
    use_bm25 = bm25_scores is not None and beta > 0
    scored: List[Tuple[float, Dict]] = []
    for pat in candidates:
        emb = pat.get("embedding")
        if not emb:
            continue
        if not is_live(pat):
            continue
        vec = np.asarray(emb, dtype=np.float32)
        sim = cosine(seed_emb, vec)
        if sim < threshold:
            continue
        if use_bm25:
            bm = float((bm25_scores or {}).get(id(pat), 0.0))
            base = alpha * sim + beta * bm
        else:
            base = sim
        trust = float(pat.get("trust_score", 1.0)) if use_trust else 1.0
        scored.append((base * trust, pat))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [p for _, p in scored[:top_k]]


def _pat_id(p: Dict) -> str:
    """Stable key across variants (same dict object ids in one run)."""
    return p.get("pattern", "")[:80]


def _jaccard(a: List[Dict], b: List[Dict]) -> float:
    sa, sb = {_pat_id(p) for p in a}, {_pat_id(p) for p in b}
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def _kendall_intersection(a: List[Dict], b: List[Dict]) -> Optional[float]:
    """Kendall tau over the intersection ranks. None if intersection < 2."""
    ra = {_pat_id(p): i for i, p in enumerate(a)}
    rb = {_pat_id(p): i for i, p in enumerate(b)}
    common = [k for k in ra if k in rb]
    if len(common) < 2:
        return None
    ranks_a = [ra[k] for k in common]
    ranks_b = [rb[k] for k in common]
    n = len(common)
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            da = ranks_a[i] - ranks_a[j]
            db = ranks_b[i] - ranks_b[j]
            s = da * db
            if s > 0:
                concordant += 1
            elif s < 0:
                discordant += 1
    total = n * (n - 1) // 2
    if total == 0:
        return None
    return (concordant - discordant) / total


def _top_n_agreement(a: List[Dict], b: List[Dict], n: int) -> int:
    sa = {_pat_id(p) for p in a[:n]}
    sb = {_pat_id(p) for p in b[:n]}
    return len(sa & sb)


def _resolve_view_path(name: str) -> Path:
    user = USER_VIEWS_DIR / f"{name}.md"
    if user.exists():
        return user
    return REPO_VIEWS_DIR / f"{name}.md"


def main(view_filter: Optional[List[str]] = None) -> None:
    assert KNOWLEDGE_PATH.exists(), f"knowledge not found: {KNOWLEDGE_PATH}"
    before_mtime = KNOWLEDGE_PATH.stat().st_mtime_ns

    with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)
    patterns: List[Dict] = list(raw) if isinstance(raw, list) else list(raw.get("patterns", []))
    live_candidates = [p for p in patterns if p.get("embedding") and is_live(p)]
    print(f"[load] {len(patterns)} patterns, {len(live_candidates)} live with embedding")

    targets = view_filter or VIEW_NAMES
    results: Dict[str, Dict] = {}
    for view_name in targets:
        view_path = _resolve_view_path(view_name)
        if not view_path.exists():
            print(f"[skip] view {view_name}: file not found")
            continue
        view = _parse_seed_file(view_path)
        seed_emb = embed_one(view.seed_text)
        if seed_emb is None:
            print(f"[skip] view {view_name}: seed embedding failed")
            continue
        alpha = 1.0 - view.bm25_weight
        beta = view.bm25_weight
        bm25_scores = _compute_bm25_scores(view.seed_text, live_candidates) if beta > 0 else None

        v_current = _rank_variant(
            seed_emb, live_candidates, view.threshold, TOP_K,
            bm25_scores=bm25_scores, alpha=alpha, beta=beta, use_trust=True,
        )
        v_notrust = _rank_variant(
            seed_emb, live_candidates, view.threshold, TOP_K,
            bm25_scores=bm25_scores, alpha=alpha, beta=beta, use_trust=False,
        )
        v_cosineonly = _rank_variant(
            seed_emb, live_candidates, view.threshold, TOP_K,
            bm25_scores=None, alpha=1.0, beta=0.0, use_trust=False,
        )

        jacc_cn = _jaccard(v_current, v_notrust)
        jacc_cc = _jaccard(v_current, v_cosineonly)
        kend_cn = _kendall_intersection(v_current, v_notrust)
        kend_cc = _kendall_intersection(v_current, v_cosineonly)
        top1_cn = _top_n_agreement(v_current, v_notrust, 1)
        top3_cn = _top_n_agreement(v_current, v_notrust, 3)
        top1_cc = _top_n_agreement(v_current, v_cosineonly, 1)
        top3_cc = _top_n_agreement(v_current, v_cosineonly, 3)

        results[view_name] = {
            "threshold": view.threshold,
            "bm25_weight": view.bm25_weight,
            "top_k": TOP_K,
            "current_size": len(v_current),
            "notrust_size": len(v_notrust),
            "cosineonly_size": len(v_cosineonly),
            "jaccard_current_vs_notrust": jacc_cn,
            "jaccard_current_vs_cosineonly": jacc_cc,
            "kendall_current_vs_notrust": kend_cn,
            "kendall_current_vs_cosineonly": kend_cc,
            "top1_match_vs_notrust": top1_cn,
            "top3_match_vs_notrust": top3_cn,
            "top1_match_vs_cosineonly": top1_cc,
            "top3_match_vs_cosineonly": top3_cc,
            "variants": {
                "current": [
                    {
                        "rank": i + 1,
                        "trust_score": p.get("trust_score"),
                        "pattern": p.get("pattern", "")[:120],
                    }
                    for i, p in enumerate(v_current)
                ],
                "notrust": [
                    {
                        "rank": i + 1,
                        "trust_score": p.get("trust_score"),
                        "pattern": p.get("pattern", "")[:120],
                    }
                    for i, p in enumerate(v_notrust)
                ],
                "cosineonly": [
                    {
                        "rank": i + 1,
                        "trust_score": p.get("trust_score"),
                        "pattern": p.get("pattern", "")[:120],
                    }
                    for i, p in enumerate(v_cosineonly)
                ],
            },
        }
        print(
            f"[view] {view_name}: "
            f"J(current,notrust)={jacc_cn:.3f} J(current,cos)={jacc_cc:.3f} "
            f"K(current,notrust)={'-' if kend_cn is None else f'{kend_cn:.3f}'} "
            f"K(current,cos)={'-' if kend_cc is None else f'{kend_cc:.3f}'} "
            f"t1(cn/cc)={top1_cn}/{top1_cc} t3(cn/cc)={top3_cn}/{top3_cc}"
        )

    after_mtime = KNOWLEDGE_PATH.stat().st_mtime_ns
    assert after_mtime == before_mtime, "knowledge.json mtime changed — READ-ONLY invariant violated"

    out_path = Path(__file__).parent / "retrieval-scoring-effect-20260418.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"results": results, "total_patterns": len(patterns), "live": len(live_candidates)}, f, indent=2, ensure_ascii=False)
    print(f"[write] {out_path}")


if __name__ == "__main__":
    argv_views = sys.argv[1:] if len(sys.argv) > 1 else None
    main(argv_views)
