#!/usr/bin/env python3
"""Read-only stability reading over submolt-scope sweep logs (RFC-0011).

Reads N sweep logs written by `contemplative-agent submolt-scan` (ADR-0086) and
reports, per sweep, the per-submolt score distribution and the rank order it
induces, plus the pairwise rank agreement between sweeps.

It touches ONLY the numeric and identifier fields of `event=score` records. The
`content_b64` field holds untrusted external post text and is never decoded,
printed, or returned — the reading is about ranks, not about what the posts say.

Two guards against reading noise as signal:

  * `split_half_noise_ceiling` — within ONE sweep, the rank agreement between
    the first and second half of each submolt's sample, stepped back up to full
    sample length by Spearman-Brown. A between-sweep rho at or below this is
    indistinguishable from n=20 sampling noise.
  * `post_overlap` — how many scored posts two sweeps share. Rank stability over
    the SAME posts would be trivial; over disjoint posts it is not.

Usage:
    python3 scripts/submolt_scope_stability.py LOG LOG [LOG ...]

Output is JSON on stdout. Deterministic: no sampling, no clock, no network.
"""

from __future__ import annotations

import json
import statistics
import sys
from itertools import combinations
from typing import Any

Summary = dict[str, dict[str, float]]


def load(
    path: str,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, list[float]], dict[str, list[str]]]:
    """Return (scan_start, scan_end, per-submolt scores, per-submolt post ids)."""
    header: dict[str, Any] | None = None
    end: dict[str, Any] | None = None
    scores: dict[str, list[float]] = {}
    posts: dict[str, list[str]] = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            event = rec.get("event")
            if event == "scan_start":
                header = rec
            elif event == "scan_end":
                end = rec
            elif event == "score":
                scores.setdefault(rec["submolt"], []).append(float(rec["score"]))
                posts.setdefault(rec["submolt"], []).append(rec["post_id"])
    if header is None:
        raise ValueError(f"{path}: no scan_start record")
    return header, end, scores, posts


def summarize(scores: dict[str, list[float]], threshold: float) -> Summary:
    """Per-submolt summary. `hit` is the share of sampled posts at/over threshold."""
    return {
        name: {
            "n": len(vals),
            "mean": round(statistics.fmean(vals), 4),
            "p50": round(statistics.median(vals), 4),
            "hit": round(sum(1 for v in vals if v >= threshold) / len(vals), 4),
        }
        for name, vals in scores.items()
    }


def ranked(summary: Summary, key: str) -> list[str]:
    """Names ordered best-first by `key`; ties broken by name for determinism."""
    return [n for n, _ in sorted(summary.items(), key=lambda kv: (-kv[1][key], kv[0]))]


def _avg_ranks(values: list[float]) -> list[float]:
    """Average (tie-corrected) ranks, 1-based."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(a: Summary, b: Summary, key: str) -> tuple[float | None, int]:
    """Spearman rho over the submolts present in both sides (ties averaged)."""
    names = sorted(set(a) & set(b))
    if len(names) < 3:
        return None, len(names)
    ra = _avg_ranks([a[n][key] for n in names])
    rb = _avg_ranks([b[n][key] for n in names])
    ma, mb = statistics.fmean(ra), statistics.fmean(rb)
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb, strict=True))
    den = sum((x - ma) ** 2 for x in ra) ** 0.5 * sum((y - mb) ** 2 for y in rb) ** 0.5
    if den == 0:
        return None, len(names)
    return round(num / den, 4), len(names)


def split_half(scores: dict[str, list[float]]) -> dict[str, Any]:
    """Noise ceiling: an odd/even split of each submolt's own sample.

    Odd/even, not first-half/second-half: the sampler enumerates a feed in
    recency order, so two contiguous halves are not parallel and the reliability
    they yield is biased LOW — which is the direction that would flatter the
    between-sweep comparison this ceiling exists to discipline.

    Each half holds n/2 posts, so the raw value is not comparable with a
    between-sweep rho computed on full samples; Spearman-Brown steps it up to
    full length, and that is the number to compare against.
    """
    a: Summary = {}
    b: Summary = {}
    for name, vals in scores.items():
        if len(vals) < 4:
            continue
        a[name] = {"mean": round(statistics.fmean(vals[0::2]), 4)}
        b[name] = {"mean": round(statistics.fmean(vals[1::2]), 4)}
    rho, n = spearman(a, b, "mean")
    # Spearman-Brown is only meaningful for a positive split-half reliability;
    # a negative rho would step up to a value outside [-1, 1] and be read as a
    # ceiling.
    corrected = round(2 * rho / (1 + rho), 4) if rho is not None and rho > 0 else None
    return {
        "spearman_mean_halves": rho,
        "spearman_mean_full_length_sb": corrected,
        "n_common_submolts": n,
    }


def group_stats(
    scores: dict[str, list[float]], subscribed: set[str], threshold: float
) -> dict[str, Any] | None:
    """Subscribed vs unsubscribed at the POST level.

    Post level, not submolt level: the 2026-08-08 reading recorded that a median
    over per-submolt hit rates lands in the valley of a bimodal subscribed side.
    """
    sub: list[float] = []
    uns: list[float] = []
    for name, vals in scores.items():
        (sub if name in subscribed else uns).extend(vals)
    if not sub or not uns:
        return None
    ms, mu = statistics.fmean(sub), statistics.fmean(uns)
    vs, vu = statistics.variance(sub), statistics.variance(uns)
    pooled = (((len(sub) - 1) * vs + (len(uns) - 1) * vu) / (len(sub) + len(uns) - 2)) ** 0.5
    return {
        "n_subscribed_posts": len(sub),
        "n_unsubscribed_posts": len(uns),
        "mean_subscribed": round(ms, 4),
        "mean_unsubscribed": round(mu, 4),
        "p50_subscribed": round(statistics.median(sub), 4),
        "p50_unsubscribed": round(statistics.median(uns), 4),
        "hit_subscribed": round(sum(1 for v in sub if v >= threshold) / len(sub), 4),
        "hit_unsubscribed": round(sum(1 for v in uns if v >= threshold) / len(uns), 4),
        "cohens_d": round((ms - mu) / pooled, 4) if pooled else None,
    }


def crossers(summary: Summary, subscribed: set[str]) -> dict[str, Any]:
    """Unsubscribed submolts that reach the WEAKEST subscribed submolt's mean.

    The shape the 2026-08-08 reading used for its "6 件" claim, recomputed here
    so the same question can be asked of every sweep.

    BOTH conventions are emitted because they disagree: means sit on a coarse
    grid, so an unsubscribed submolt tying the weakest subscribed one is common,
    and "at or above" vs "strictly above" changes the count. Reporting one alone
    would hide that the membership is tie-sensitive.
    """
    subs = [v["mean"] for n, v in summary.items() if n in subscribed]
    if not subs:
        return {"floor": None, "weakest_subscribed": [], "at_or_above": [], "above": []}
    floor = min(subs)
    by_mean = sorted((n for n in summary if n not in subscribed), key=lambda n: -summary[n]["mean"])
    return {
        "floor": floor,
        "weakest_subscribed": sorted(n for n in subscribed if summary[n]["mean"] == floor),
        "at_or_above": [n for n in by_mean if summary[n]["mean"] >= floor],
        "above": [n for n in by_mean if summary[n]["mean"] > floor],
    }


def mid_ranks(summary: Summary, key: str) -> dict[str, float]:
    """Tie-corrected (mid) ranks, best = 1. Use these to talk about MOVEMENT.

    `ranked`'s ordinals break ties by name, which is fine for naming a top-N set
    but would turn an alphabetical tie-flip into apparent rank movement.
    """
    names = sorted(summary)
    asc = _avg_ranks([-summary[n][key] for n in names])
    return dict(zip(names, (round(r, 1) for r in asc), strict=True))


def mean_ties(summary: Summary) -> int:
    """Submolts sharing a mean with another submolt.

    `ranked` breaks ties by name, so a tie that flips alphabetically between
    sweeps would show up as rank movement that is not in the data. Non-zero here
    means the ordinal ranks must not be read as movement.
    """
    means = [v["mean"] for v in summary.values()]
    return sum(1 for m in means if means.count(m) > 1)


def topn_churn(order_a: list[str], order_b: list[str], n: int) -> dict[str, Any]:
    """Set difference of the top-n membership between two orderings."""
    sa, sb = set(order_a[:n]), set(order_b[:n])
    return {
        "shared": sorted(sa & sb),
        "only_first": sorted(sa - sb),
        "only_second": sorted(sb - sa),
        "churn": len(sa - sb),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(
            "need at least two sweep logs (the reading is a comparison)",
            file=sys.stderr,
        )
        return 2

    sweeps: list[dict[str, Any]] = []
    for path in argv[1:]:
        header, end, scores, posts = load(path)
        threshold = header["relevance_threshold"]
        summary = summarize(scores, threshold)
        sweeps.append(
            {
                "path": path,
                "scan_start_ts": header["ts"],
                "scan_end_ts": end["ts"] if end else None,
                "verdict": end["verdict"] if end else None,
                "sample_size": header["sample_size"],
                "relevance_threshold": threshold,
                "subscribed": header["subscribed"],
                "discovered": header["discovered"],
                "scored": sum(int(v["n"]) for v in summary.values()),
                "distinct_posts": len({q for v in posts.values() for q in v}),
                "split_half_noise_ceiling": split_half(scores),
                "mean_ties": mean_ties(summary),
                "group": group_stats(scores, set(header["subscribed"]), threshold),
                "unsubscribed_vs_weakest_subscribed": crossers(summary, set(header["subscribed"])),
                "summary": summary,
                "rank_by_mean": ranked(summary, "mean"),
                "rank_by_hit": ranked(summary, "hit"),
                "_midranks": mid_ranks(summary, "mean"),
                "_posts": posts,
            }
        )

    label = {i: s["scan_start_ts"][:10] for i, s in enumerate(sweeps)}
    pairs: list[dict[str, Any]] = []
    for i, j in combinations(range(len(sweeps)), 2):
        rho_mean, n_common = spearman(sweeps[i]["summary"], sweeps[j]["summary"], "mean")
        rho_hit, _ = spearman(sweeps[i]["summary"], sweeps[j]["summary"], "hit")
        top_n = len(sweeps[i]["subscribed"])
        a = {q for v in sweeps[i]["_posts"].values() for q in v}
        b = {q for v in sweeps[j]["_posts"].values() for q in v}
        pairs.append(
            {
                "pair": [label[i], label[j]],
                "n_common_submolts": n_common,
                "spearman_mean": rho_mean,
                "spearman_hit": rho_hit,
                "top_n": top_n,
                "topn_by_mean": topn_churn(
                    sweeps[i]["rank_by_mean"], sweeps[j]["rank_by_mean"], top_n
                ),
                "post_overlap": {
                    "n_first": len(a),
                    "n_second": len(b),
                    "shared": len(a & b),
                    "jaccard": round(len(a & b) / len(a | b), 4) if a | b else None,
                },
            }
        )

    names = sorted(set().union(*(set(s["summary"]) for s in sweeps)))
    per_submolt = {
        name: {
            "subscribed": name in sweeps[-1]["subscribed"],
            "series": [
                {
                    "date": label[i],
                    **s["summary"].get(name, {}),
                    "rank_by_mean": (
                        s["rank_by_mean"].index(name) + 1 if name in s["rank_by_mean"] else None
                    ),
                    "midrank_by_mean": s["_midranks"].get(name),
                }
                for i, s in enumerate(sweeps)
            ],
        }
        for name in names
    }

    json.dump(
        {
            "sweeps": [
                {k: v for k, v in s.items() if k not in ("summary", "_posts", "_midranks")}
                for s in sweeps
            ],
            "pairwise": pairs,
            "per_submolt": per_submolt,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
