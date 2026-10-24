"""Do per-skill reply rates separate? Two-window reading of ADR-0106 (P1-04.5).

Read-only, stdlib only (bare ``python3`` is fine). Input: the JSON that
``read_comment_outcomes`` writes, for each of two windows, passed as
``--window A.json --window B.json`` (more than two are allowed; they are pooled
per skill). It does not read any log: the two windows are taken on the machine
that holds ``~/.config/moltbook/logs`` and committed under
``docs/evidence/adr-0106/`` (see that directory's README for the two calls).

Pre-registered line, fixed before the 2026-10-24 reading (D-P1-04-2):

    SEPARATES  iff  there is a pair of skills, both with n >= MIN_N pooled
    observed comments, whose reply rates differ by >= GAP_LINE (0.2) AND whose
    95% Wilson intervals do not overlap.

Effect size, not a p-value, decides A (nothing separates: remove stage 7d,
close RFC-0028) versus B (it separates: file an attribution RFC). The chi-square
and the permutation test below are context for the reader, not the line.

The first line of the output is the observed rate (replied / observed
publishes vs joined publishes). ``observed_publishes`` is the denominator the
rates are read against; it is about a third of ``joined_publishes`` (the "500
judged records" population), and a rate over it says nothing about the
unobserved two thirds.

Skills are not independent rows: one comment injects several skills, so one
reply is counted once per injected skill. The permutation test shuffles the
replies across skill-injection rows, which ignores that sharing and therefore
overstates how often chance alone looks this spread (it is conservative toward
"does not separate" only in the sense of being a reference, not a calibrated p).

A skill's reading never flows into adopt / archive (ADR-0106 D6, ADR-0051).

Usage:
    python3 scripts/comment_outcome_separation.py \\
        --window docs/evidence/adr-0106/window-2026-09-12_10-02.json \\
        --window docs/evidence/adr-0106/window-2026-10-03_10-23.json [--json OUT]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path
from typing import Any

GAP_LINE = 0.2
MIN_N = 10  # below this a skill's interval is not reported as a rate
MERGE_BELOW = 5  # expected-count floor for the chi-square (skills below merge to "other")
PERMUTATIONS = 5000
SEED = 20261024
_Z95 = 1.959964

REASON_NO_WINDOWS = "NO_WINDOWS"
REASON_UNREADABLE = "WINDOW_UNREADABLE"
REASON_NO_SKILLS = "NO_SKILLS"


def wilson(successes: int, trials: int) -> tuple[float, float] | None:
    """95% Wilson interval; None for a zero denominator or an impossible count.

    Same formula as ``scripts/_stats.wilson_ci``, kept local so this script
    stands alone (swap for the shared one when P2-01.9 lands).
    """
    if trials <= 0 or successes < 0 or successes > trials:
        return None
    p = successes / trials
    denom = 1.0 + _Z95 * _Z95 / trials
    centre = (p + _Z95 * _Z95 / (2 * trials)) / denom
    half = (_Z95 / denom) * math.sqrt(p * (1 - p) / trials + _Z95 * _Z95 / (4 * trials * trials))
    return max(0.0, centre - half), min(1.0, centre + half)


def _chi2_sf(x: float, k: int) -> float:
    """Survival function of chi-square(k) via the regularized upper gamma Q(k/2, x/2)."""
    if k <= 0 or x < 0:
        return float("nan")
    if x == 0:
        return 1.0
    a, z = k / 2.0, x / 2.0
    if z < a + 1.0:  # series for P, then Q = 1 - P
        term = total = 1.0 / a
        n = a
        for _ in range(500):
            n += 1.0
            term *= z / n
            total += term
            if abs(term) < abs(total) * 1e-12:
                break
        p = total * math.exp(-z + a * math.log(z) - math.lgamma(a))
        return max(0.0, 1.0 - p)
    tiny = 1e-300  # continued fraction for Q (Lentz)
    b = z + 1.0 - a
    c = 1.0 / tiny
    d = 1.0 / b
    h = d
    for i in range(1, 500):
        an = -i * (i - a)
        b += 2.0
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return min(1.0, math.exp(-z + a * math.log(z) - math.lgamma(a)) * h)


def _rate(skill: dict[str, Any]) -> float | None:
    # ``reply_rate`` is renamed ``replied_fraction`` by P1-04.9; accept both.
    n = skill.get("injected_comments")
    r = skill.get("comments_with_reply")
    if isinstance(n, int) and isinstance(r, int) and n > 0:
        return r / n
    return None


def load_window(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        raise ValueError("not a read_comment_outcomes JSON")
    return data


def pool(windows: list[dict[str, Any]]) -> dict[str, tuple[int, int]]:
    """skill -> (replied, injected), summed over windows."""
    out: dict[str, list[int]] = {}
    for w in windows:
        for s in w["skills"]:
            n, r = s.get("injected_comments"), s.get("comments_with_reply")
            if not (isinstance(n, int) and isinstance(r, int) and 0 <= r <= n and n > 0):
                continue
            acc = out.setdefault(str(s.get("skill")), [0, 0])
            acc[0] += r
            acc[1] += n
    return {k: (v[0], v[1]) for k, v in out.items()}


def chi_square(table: dict[str, tuple[int, int]]) -> dict[str, Any]:
    """Homogeneity of (reply, no-reply) across skills; small skills merged to 'other'."""
    total_r = sum(r for r, _ in table.values())
    total_n = sum(n for _, n in table.values())
    if total_n == 0 or total_r in (0, total_n):
        return {"statistic": None, "df": None, "p": None, "note": "degenerate margin"}
    p_all = total_r / total_n
    kept: list[tuple[int, int]] = []
    other_r = other_n = 0
    for r, n in table.values():
        if n * min(p_all, 1 - p_all) < MERGE_BELOW:
            other_r += r
            other_n += n
        else:
            kept.append((r, n))
    if other_n:
        kept.append((other_r, other_n))
    if len(kept) < 2:
        return {"statistic": None, "df": None, "p": None, "note": "fewer than 2 groups after merge"}
    stat = 0.0
    for r, n in kept:
        e_r, e_f = n * p_all, n * (1 - p_all)
        stat += (r - e_r) ** 2 / e_r + ((n - r) - e_f) ** 2 / e_f
    df = len(kept) - 1
    return {"statistic": round(stat, 4), "df": df, "p": round(_chi2_sf(stat, df), 6),
            "groups": len(kept), "merged_into_other": other_n > 0}


def _spread(counts: list[tuple[int, int]]) -> float:
    """Weighted variance of the per-skill rates around the pooled rate."""
    n_all = sum(n for _, n in counts)
    if n_all == 0:
        return 0.0
    p = sum(r for r, _ in counts) / n_all
    return sum(n * (r / n - p) ** 2 for r, n in counts) / n_all


def permutation(table: dict[str, tuple[int, int]], iters: int = PERMUTATIONS,
                seed: int = SEED) -> dict[str, Any]:
    names = sorted(table)
    sizes = [table[k][1] for k in names]
    total_r = sum(table[k][0] for k in names)
    labels = [1] * total_r + [0] * (sum(sizes) - total_r)
    observed = _spread([table[k] for k in names])
    rng = random.Random(seed)
    ge = 0
    for _ in range(iters):
        rng.shuffle(labels)
        pos, counts = 0, []
        for n in sizes:
            counts.append((sum(labels[pos:pos + n]), n))
            pos += n
        if _spread(counts) >= observed - 1e-15:
            ge += 1
    return {"observed_spread": round(observed, 6), "iterations": iters, "seed": seed,
            "p": round((ge + 1) / (iters + 1), 6)}


def analyse(windows: list[dict[str, Any]]) -> dict[str, Any]:
    table = pool(windows)
    joined = sum(int(w.get("joined_publishes", 0) or 0) for w in windows)
    observed = sum(int(w.get("observed_publishes", 0) or 0) for w in windows)
    rows = []
    for name, (r, n) in sorted(table.items()):
        ci = wilson(r, n) if n >= MIN_N else None
        rows.append({"skill": name, "replied": r, "n": n, "rate": round(r / n, 4),
                     "wilson95": [round(ci[0], 4), round(ci[1], 4)] if ci else None})
    eligible = [x for x in rows if x["wilson95"] is not None]
    best: dict[str, Any] | None = None
    qualifying: list[dict[str, Any]] = []
    for i, a in enumerate(eligible):
        for b in eligible[i + 1:]:
            hi, lo = (a, b) if a["rate"] >= b["rate"] else (b, a)
            gap = hi["rate"] - lo["rate"]
            disjoint = lo["wilson95"][1] < hi["wilson95"][0]
            pair = {"high": hi["skill"], "low": lo["skill"], "gap": round(gap, 4),
                    "wilson_disjoint": disjoint}
            if best is None or gap > best["gap"]:
                best = pair
            if gap >= GAP_LINE and disjoint:
                qualifying.append(pair)
    return {
        "windows": [{"since": w.get("since"), "until": w.get("until"),
                     "joined_publishes": w.get("joined_publishes"),
                     "observed_publishes": w.get("observed_publishes")} for w in windows],
        "joined_publishes": joined,
        "observed_publishes": observed,
        "observed_over_joined": round(observed / joined, 4) if joined else None,
        "skills": len(rows),
        "eligible_skills": len(eligible),
        "pooled_replied": sum(r for r, _ in table.values()),
        "pooled_injections": sum(n for _, n in table.values()),
        "chi_square": chi_square(table),
        "permutation": permutation(table) if table else None,
        "max_gap_pair": best,
        "qualifying_pairs": qualifying,
        "line": {"gap": GAP_LINE, "min_n": MIN_N, "needs": "gap >= line and disjoint Wilson 95%"},
        "separates": bool(qualifying),
        "table": rows,
    }


def render(res: dict[str, Any]) -> str:
    obs, joined = res["observed_publishes"], res["joined_publishes"]
    share = res["observed_over_joined"]
    lines = [
        f"observed {obs} of {joined} joined publishes"
        + (f" ({share:.1%})" if share is not None else "")
        + " - rates below are over the observed part only",
    ]
    for w in res["windows"]:
        lines.append(f"window {w['since']}..{w['until']}: joined={w['joined_publishes']} "
                     f"observed={w['observed_publishes']}")
    cs, pm = res["chi_square"], res["permutation"]
    lines.append(f"skills={res['skills']} (n>={MIN_N}: {res['eligible_skills']}) "
                 f"pooled replied/injections={res['pooled_replied']}/{res['pooled_injections']}")
    lines.append(f"chi-square: stat={cs.get('statistic')} df={cs.get('df')} p={cs.get('p')}"
                 + (f" ({cs['note']})" if cs.get("note") else ""))
    if pm:
        lines.append(f"permutation: spread={pm['observed_spread']} p={pm['p']} "
                     f"(iters={pm['iterations']}, seed={pm['seed']})")
    g = res["max_gap_pair"]
    lines.append("max-gap pair: " + (f"{g['high']} vs {g['low']} gap={g['gap']} "
                 f"wilson_disjoint={g['wilson_disjoint']}" if g else "none (fewer than 2 eligible skills)"))
    lines.append(f"pre-registered line: gap >= {GAP_LINE} and disjoint Wilson 95% "
                 f"(n >= {MIN_N} each) -> qualifying pairs: {len(res['qualifying_pairs'])}")
    lines.append("verdict: " + ("SEPARATES (B: attribution RFC)" if res["separates"]
                                else "DOES NOT SEPARATE (A: remove stage 7d, close RFC-0028)"))
    lines.append("")
    lines.append("skill | replied/n | rate | wilson95")
    for r in sorted(res["table"], key=lambda x: -x["n"]):
        ci = r["wilson95"]
        lines.append(f"{r['skill']} | {r['replied']}/{r['n']} | {r['rate']:.3f} | "
                     + (f"{ci[0]:.3f}-{ci[1]:.3f}" if ci else f"n<{MIN_N} (count only)"))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--window", action="append", default=[], type=Path)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    if not args.window:
        print(f"reason={REASON_NO_WINDOWS} pass --window at least once", file=sys.stderr)
        return 2
    windows = []
    for path in args.window:
        try:
            windows.append(load_window(path))
        except (OSError, ValueError) as exc:
            print(f"reason={REASON_UNREADABLE} {path.name}: {exc}", file=sys.stderr)
            return 2
    res = analyse(windows)
    if res["skills"] == 0:
        print(f"reason={REASON_NO_SKILLS} no skill rows in the windows", file=sys.stderr)
        return 2
    sys.stdout.write(render(res))
    if args.json:
        args.json.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
