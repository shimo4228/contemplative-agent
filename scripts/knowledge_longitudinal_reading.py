#!/usr/bin/env python3
"""Longitudinal reading of the public knowledge store (P3-02.3, "T-P3").

Run as ``uv run --no-sync python scripts/knowledge_longitudinal_reading.py``
(numpy, a runtime dependency, is needed only for the cosine). Read-only and
manual: the output is frozen under ``docs/evidence/`` and the script is not part
of any gate or CI.

The 2026-08-16 reading (RFC-0006's reason for keeping the heartbeat end state
open) reported three quantities: the corpus grew 1,463 -> 5,832 (4.0x), the
pairwise cosine moved 0.55 -> 0.58, and 75% of the corpus turned over in six
weeks. Its note lives in a gitignored directory and its definitions are not
recoverable, so this script fixes **explicit** definitions and recomputes the
three from the public ``knowledge.json`` alone:

- active(d): rows with ``valid_from`` (or ``distilled``) on or before day d and
  ``valid_until`` empty or after d. Corpus size = |active(d)|.
- turnover over the window (d - W, d], W = ``--window-days`` (default 42):
  ``new_share`` = share of active(d) distilled inside the window;
  ``retired_share`` = share of active(d - W) no longer active at d. Both are
  given because the old note does not say which one "75%" was.
- pairwise cosine at d: mean cosine over all pairs of a seeded sample (at most
  ``--sample``) of active(d), from ``--embeddings`` (an ``.npy`` aligned to the
  rows of ``knowledge.json``, produced with the DATACARD "Reconstructing
  embeddings" procedure). Without it the cosine is ``null`` with a reason,
  never a guess. The public file carries no vectors, so the cosine is
  reproducible only against the same Ollama and model versions (DATACARD).

Because these are new definitions, the numbers need not equal the old ones; the
rerun that reconciles them (owner, Mac) is recorded in the evidence file.
Boundaries: with ``--regimes`` the figure draws a vertical line for every
``regimes.json`` row affecting ``knowledge.patterns``, and the text says that
the growth factor spans the 2026-06-23 per-episode distill and the 2026-06-28
model change (a rise across a boundary is not a growth rate of one regime).

Consumption plan (ADR-0101): (a) the owner when writing the Q2 section of the
research-questions ADR (P3-01.3) and the paper's figure; (b) one run fixes the
three quantities in ``docs/evidence/``, and the script is re-run only when a new
row lands in ``regimes.json`` that affects ``knowledge.patterns`` and at the
P4-02 final sync; (c) retire after the P4-02 final run. It is never put in CI.

Usage:
    knowledge_longitudinal_reading.py KNOWLEDGE_JSON --out-json R.json --out-md R.md
        [--out-svg size.svg] [--regimes regimes.json] [--embeddings emb.npy]
        [--asof YYYY-MM-DD ...] [--window-days 42] [--sample 2000] [--seed 0]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np


def _day(v: object) -> dt.date | None:
    if isinstance(v, str) and len(v) >= 10:
        try:
            return dt.date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def load_rows(path: Path) -> list[dict[str, Any]]:
    return load_rows_from_list(json.loads(path.read_text(encoding="utf-8")))


def load_rows_from_list(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        start = _day(r.get("valid_from")) or _day(r.get("distilled"))
        out.append(
            {
                "start": start,
                "distilled": _day(r.get("distilled")) or start,
                "until": _day(r.get("valid_until")),
            }
        )
    return out


def active_indices(rows: list[dict[str, Any]], d: dt.date) -> list[int]:
    return [
        i
        for i, r in enumerate(rows)
        if r["start"] is not None and r["start"] <= d and (r["until"] is None or r["until"] > d)
    ]


def turnover(rows: list[dict[str, Any]], d: dt.date, window: int) -> dict[str, Any]:
    now = active_indices(rows, d)
    then = active_indices(rows, d - dt.timedelta(days=window))
    lo = d - dt.timedelta(days=window)
    new = [i for i in now if rows[i]["distilled"] is not None and rows[i]["distilled"] > lo]
    still = set(now)
    gone = [i for i in then if i not in still]
    return {
        "window_days": window,
        "active_now": len(now),
        "active_then": len(then),
        "new_share": round(len(new) / len(now), 4) if now else None,
        "retired_share": round(len(gone) / len(then), 4) if then else None,
    }


def mean_pairwise_cosine(
    vectors: np.ndarray, idx: list[int], sample: int, seed: int
) -> dict[str, Any]:
    import numpy as np  # runtime dependency of the package

    rng = random.Random(seed)
    pick = idx if len(idx) <= sample else sorted(rng.sample(idx, sample))
    if len(pick) < 2:
        return {"value": None, "reason": "fewer_than_two_rows", "n": len(pick)}
    m = np.asarray(vectors[pick], dtype=np.float64)
    norms = np.linalg.norm(m, axis=1)
    keep = norms > 0
    m = m[keep] / norms[keep][:, None]
    n = m.shape[0]
    if n < 2:
        return {"value": None, "reason": "no_nonzero_vectors", "n": n}
    total = float((m.sum(axis=0) ** 2).sum() - n)  # sum over i != j of cos
    return {"value": round(total / (n * (n - 1)), 4), "reason": None, "n": n}


def default_asof(rows: list[dict[str, Any]]) -> list[dt.date]:
    starts = [r["start"] for r in rows if r["start"]]
    first, last = min(starts), max(starts)
    out, d = [], first + dt.timedelta(days=(7 - first.weekday()) % 7)
    while d <= last:
        out.append(d)
        d += dt.timedelta(days=7)
    return out


def size_series(rows: list[dict[str, Any]], days: list[dt.date]) -> list[dict[str, Any]]:
    return [{"date": d.isoformat(), "active": len(active_indices(rows, d))} for d in days]


def read(
    rows: list[dict[str, Any]],
    asof: list[dt.date],
    window: int,
    vectors: np.ndarray | None,
    sample: int,
    seed: int,
) -> dict[str, Any]:
    points = []
    for d in asof:
        idx = active_indices(rows, d)
        p: dict[str, Any] = {
            "asof": d.isoformat(),
            "active": len(idx),
            **{"turnover": turnover(rows, d, window)},
        }
        if vectors is None:
            p["pairwise_cosine"] = {"value": None, "reason": "no_embeddings_given", "n": 0}
        else:
            p["pairwise_cosine"] = mean_pairwise_cosine(vectors, idx, sample, seed)
        points.append(p)
    first, last = points[0], points[-1]
    growth = round(last["active"] / first["active"], 2) if first["active"] else None
    return {
        "definitions": "see the module docstring: active(d), new_share / retired_share over (d - W, d], mean pairwise cosine of a seeded sample",
        "window_days": window,
        "sample": sample,
        "seed": seed,
        "points": points,
        "growth_first_to_last": {"from": first["asof"], "to": last["asof"], "factor": growth},
    }


def boundary_dates(
    regimes: Path | None, series: str = "knowledge.patterns"
) -> list[tuple[dt.date, str, str]]:
    if regimes is None:
        return []
    doc = json.loads(regimes.read_text(encoding="utf-8"))
    return sorted(
        (dt.date.fromisoformat(r["date"]), r["id"], r["change"])
        for r in doc["regimes"]
        if series in r.get("affects", [])
    )


def svg(series: list[dict[str, Any]], bounds: list[tuple[dt.date, str, str]]) -> str:
    w, h, ml, mb, mt = 760, 320, 56, 36, 16
    days = [dt.date.fromisoformat(s["date"]) for s in series]
    d0, d1 = min(days), max(days)
    ymax = max(s["active"] for s in series) or 1
    span = max((d1 - d0).days, 1)

    def x(d: dt.date) -> float:
        return ml + (d - d0).days / span * (w - ml - 12)

    def y(v: int) -> float:
        return mt + (1 - v / ymax) * (h - mt - mb)

    pts = " ".join(f"{x(d):.1f},{y(s['active']):.1f}" for d, s in zip(days, series, strict=True))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" font-family="sans-serif" font-size="11">',
        f'<rect width="{w}" height="{h}" fill="#ffffff"/>',
        f'<line x1="{ml}" y1="{h - mb}" x2="{w - 12}" y2="{h - mb}" stroke="#444"/>',
        f'<line x1="{ml}" y1="{mt}" x2="{ml}" y2="{h - mb}" stroke="#444"/>',
        f'<text x="{ml - 6}" y="{mt + 4}" text-anchor="end">{ymax}</text>',
        f'<text x="{ml - 6}" y="{h - mb}" text-anchor="end">0</text>',
        f'<text x="{ml}" y="{h - 10}">{d0.isoformat()}</text>',
        f'<text x="{w - 12}" y="{h - 10}" text-anchor="end">{d1.isoformat()}</text>',
    ]
    for d, rid, _ in bounds:
        if d0 <= d <= d1:
            parts.append(
                f'<line x1="{x(d):.1f}" y1="{mt}" x2="{x(d):.1f}" y2="{h - mb}" stroke="#b44" stroke-dasharray="3 3"/>'
            )
            parts.append(
                f'<text x="{x(d) + 2:.1f}" y="{mt + 10}" fill="#b44" font-size="9">{rid}</text>'
            )
    parts.append(f'<polyline fill="none" stroke="#1f5fa8" stroke-width="2" points="{pts}"/>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def render_md(result: dict[str, Any], bounds: list[tuple[dt.date, str, str]]) -> str:
    lines = [
        "# Knowledge store, longitudinal reading",
        "",
        f"Window W = {result['window_days']} days; sample {result['sample']}, seed {result['seed']}.",
        "",
        "| as of | active | new share (W) | retired share (W) | mean pairwise cosine | n |",
        "|---|---|---|---|---|---|",
    ]
    for p in result["points"]:
        t, c = p["turnover"], p["pairwise_cosine"]
        cv = "null (" + c["reason"] + ")" if c["value"] is None else c["value"]
        lines.append(
            f"| {p['asof']} | {p['active']} | {t['new_share']} | {t['retired_share']} | {cv} | {c['n']} |"
        )
    pts = result["points"]
    if len(pts) > 1:
        lines += ["", "Growth between consecutive as-of dates:", ""]
        for a, b in zip(pts, pts[1:], strict=False):
            f = round(b["active"] / a["active"], 2) if a["active"] else None
            lines.append(f"- {a['asof']} -> {b['asof']}: {a['active']} -> {b['active']} (x{f})")
    if bounds:
        lines += ["", "Boundaries affecting `knowledge.patterns` (drawn in the figure):", ""]
        lines += [f"- {d.isoformat()} {rid}: {chg}" for d, rid, chg in bounds]
        lines += [
            "",
            "A growth factor that spans R05 (per-episode distill) and R06 (model change) is a change of",
            "extractor, not a growth rate of one regime.",
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("knowledge", type=Path)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-md", type=Path)
    ap.add_argument("--out-svg", type=Path)
    ap.add_argument("--regimes", type=Path)
    ap.add_argument("--embeddings", type=Path)
    ap.add_argument("--asof", action="append", type=dt.date.fromisoformat)
    ap.add_argument("--window-days", type=int, default=42)
    ap.add_argument("--sample", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args(argv)

    rows = load_rows(args.knowledge)
    if not rows:
        print("knowledge-longitudinal: empty store", file=sys.stderr)
        return 2
    vectors = None
    if args.embeddings:
        import numpy as np

        vectors = np.load(args.embeddings)
        if vectors.shape[0] != len(rows):
            print(
                f"knowledge-longitudinal: embeddings rows {vectors.shape[0]} != knowledge rows {len(rows)}",
                file=sys.stderr,
            )
            return 2
    asof = sorted(args.asof) if args.asof else default_asof(rows)
    result = read(rows, asof, args.window_days, vectors, args.sample, args.seed)
    args.out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    bounds = boundary_dates(args.regimes)
    if args.out_md:
        args.out_md.write_text(render_md(result, bounds), encoding="utf-8")
    if args.out_svg:
        args.out_svg.write_text(
            svg(size_series(rows, default_asof(rows)), bounds), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
