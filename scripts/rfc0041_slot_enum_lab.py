#!/usr/bin/env python3
"""Lab arm for RFC-0041 form A (slot split + enum): the ONE reading (P3-03.9).

Design and the remove-after-one-reading rule: ``rfcs/0041-memory-to-skill-pipeline-redesign.md``
(Review-when) and ``docs/plans/roadmap-2026-10/ROADMAP.md`` P3-03.9. This is a
lab arm, not a pipeline stage: it imports nothing from the production insight
path, writes nothing under ``$MOLTBOOK_HOME`` and is deleted once its JSON is
frozen in ``docs/evidence/rfc-0041/`` (ADR-0101 (c)).

Two readings, both over files the owner prepares on the Mac from the frozen
2026-09-19 insight run (``docs/evidence/rfc-0041/gate-labels-20260919.json``):

1. ``separation`` — does splitting a distill output into trigger / move /
   noticed slots separate same-theme pairs from distinct-theme pairs better than
   embedding the raw text? Input ``--patterns`` JSONL rows
   ``{"id", "theme", "text"}`` (theme = the insight cluster id). Three-point
   calibration, as in the shadow instruments: the embedder's own repeat cosine
   (the ceiling), the same-theme mean, the distinct-theme mean. gap = same −
   distinct. The slot arm clears the declared floor when
   ``gap_slot − gap_raw > 2 * SE`` (the ADR-0090 2-SE rule; SE ignores that
   pairs share patterns, so it is optimistic — read the verdict as "cleared on
   this rule", not as a test).
2. ``enum`` — a constrained answer ``same_as | revises | none`` for a candidate
   against its nearest store skill, at temperature 0, against the gate's
   decision. Input ``--pairs`` JSONL rows ``{"id", "candidate", "neighbor",
   "label"}`` with label ``gate_rejected`` (expected same_as or revises) or
   ``adopted_loo`` (expected none). Reported: confusion counts, balanced
   accuracy with Wilson intervals, and the agreement with the earlier
   duplicate/distinct replay is read by the owner from the README of that
   directory, not recomputed here.

Text discipline (CLAUDE.md, episode-log rule applies to anything an untrusted
body flows through): candidate and neighbor text never reach stdout; the output
JSON holds ids, counts and numbers only.

gemma and nomic are never resident together: run ``--stage slots`` (gemma),
unload, then ``--stage embed`` (nomic), then ``--stage enum`` (gemma). The
stages cache under ``--work`` and ``--stage report`` joins them.

Usage (Mac, outside the JST 0/6/12/18 sessions)::

    uv run --no-sync python scripts/rfc0041_slot_enum_lab.py --stage slots  --patterns P.jsonl --work W/
    uv run --no-sync python scripts/rfc0041_slot_enum_lab.py --stage embed  --patterns P.jsonl --work W/
    uv run --no-sync python scripts/rfc0041_slot_enum_lab.py --stage enum   --pairs Q.jsonl --work W/
    uv run --no-sync python scripts/rfc0041_slot_enum_lab.py --stage report --work W/ --out docs/evidence/rfc-0041/slot-enum-reading.json
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import random
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _stats import wilson_ci  # noqa: E402

HERE = Path(__file__).resolve().parent
SLOTS = ("trigger", "move", "noticed")
RELATIONS = ("same_as", "revises", "none")
SLOT_SCHEMA = {
    "type": "object",
    "properties": {s: {"type": "string"} for s in SLOTS},
    "required": list(SLOTS),
}
ENUM_SCHEMA = {
    "type": "object",
    "properties": {"relation": {"type": "string", "enum": list(RELATIONS)}},
    "required": ["relation"],
}
MAX_PAIRS = 2000
Z_RULE = 2.0


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    sys.exit(f"ERROR: {path}:{n}: {e}")
    return rows


def cosine(a: list[float], b: list[float]) -> float:
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=True)) / (na * nb)


def split_slots(text: str, generate: Callable[..., str | None], prompt: str) -> dict | None:
    """One constrained call; None (an abstain with a reason upstream) on any failure."""
    raw = generate(f"{prompt}\n\nObservation:\n{text}", format=SLOT_SCHEMA, temperature=0.0)
    if raw is None:
        return None
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not all(isinstance(d.get(s), str) for s in SLOTS):
        return None
    return {s: d[s].strip() for s in SLOTS}


def ask_relation(
    candidate: str, neighbor: str, generate: Callable[..., str | None], prompt: str
) -> str | None:
    raw = generate(
        f"{prompt}\n\nCandidate:\n{candidate}\n\nStored skill:\n{neighbor}",
        format=ENUM_SCHEMA,
        temperature=0.0,
    )
    if raw is None:
        return None
    try:
        rel = json.loads(raw).get("relation")
    except (json.JSONDecodeError, AttributeError):
        return None
    return rel if rel in RELATIONS else None


def pair_cosines(
    vectors: dict[str, list[float]], theme: dict[str, str], seed: int = 42
) -> tuple[list[float], list[float]]:
    """(same-theme cosines, distinct-theme cosines), capped at MAX_PAIRS each, seeded."""
    ids = sorted(vectors)
    same, dist = [], []
    for a, b in itertools.combinations(ids, 2):
        (same if theme[a] == theme[b] else dist).append((a, b))
    rng = random.Random(seed)
    for lst in (same, dist):
        if len(lst) > MAX_PAIRS:
            lst[:] = rng.sample(lst, MAX_PAIRS)
    return (
        [cosine(vectors[a], vectors[b]) for a, b in same],
        [cosine(vectors[a], vectors[b]) for a, b in dist],
    )


def _mean_se(xs: list[float]) -> tuple[float, float]:
    n = len(xs)
    if n < 2:
        return (xs[0] if xs else float("nan")), float("nan")
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var / n)


def separation(same: list[float], dist: list[float]) -> dict:
    ms, ses = _mean_se(same)
    md, sed = _mean_se(dist)
    return {
        "n_same": len(same),
        "n_distinct": len(dist),
        "mean_same": ms,
        "mean_distinct": md,
        "gap": ms - md,
        "gap_se": math.hypot(ses, sed),
    }


def compare_arms(raw: dict, slot: dict) -> dict:
    diff = slot["gap"] - raw["gap"]
    se = math.hypot(raw["gap_se"], slot["gap_se"])
    z = diff / se if se > 0 else float("nan")
    return {"gap_slot_minus_raw": diff, "se": se, "z": z, "cleared": bool(z > Z_RULE)}


def enum_agreement(rows: Iterable[tuple[str, str | None]]) -> dict:
    """rows: (label, relation). gate_rejected expects same_as|revises, adopted_loo expects none."""
    counts = {
        "gate_rejected": {"hit": 0, "miss": 0, "abstain": 0},
        "adopted_loo": {"hit": 0, "miss": 0, "abstain": 0},
    }
    for label, rel in rows:
        if label not in counts:
            sys.exit(f"ERROR: unknown label {label!r}")
        c = counts[label]
        if rel is None:
            c["abstain"] += 1
        elif (label == "gate_rejected") == (rel != "none"):
            c["hit"] += 1
        else:
            c["miss"] += 1
    out = {"counts": counts}
    rates = []
    for label, c in counts.items():
        n = c["hit"] + c["miss"]
        out[f"{label}_hit_rate"] = c["hit"] / n if n else None
        out[f"{label}_wilson95"] = wilson_ci(c["hit"], n)
        if n:
            rates.append(c["hit"] / n)
    out["balanced_accuracy"] = sum(rates) / len(rates) if len(rates) == 2 else None
    return out


def _generate():
    from contemplative_agent.core.llm import generate  # noqa: PLC0415

    return lambda prompt, **kw: generate(prompt, caller="rfc0041_lab", **kw)


def _embed():
    from contemplative_agent.core.embeddings import embed_texts  # noqa: PLC0415

    def f(texts: list[str]) -> list[list[float]]:
        arr = embed_texts(texts)
        if arr is None:
            sys.exit("ERROR: embedding backend returned nothing")
        return [list(map(float, v)) for v in arr]

    return f


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["slots", "embed", "enum", "report"])
    ap.add_argument("--patterns", type=Path)
    ap.add_argument("--pairs", type=Path)
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--out", type=Path)
    ns = ap.parse_args(argv)
    ns.work.mkdir(parents=True, exist_ok=True)
    w = ns.work

    if ns.stage == "slots":
        gen, prompt = _generate(), (HERE / "lab" / "rfc0041-slot.md").read_text(encoding="utf-8")
        out, failed = {}, 0
        for r in load_jsonl(ns.patterns):
            s = split_slots(r["text"], gen, prompt)
            if s is None:
                failed += 1
            else:
                out[r["id"]] = s
        (w / "slots.json").write_text(
            json.dumps({"slots": out, "failed": failed}), encoding="utf-8"
        )
        print(f"slots: {len(out)} ok, {failed} failed")
    elif ns.stage == "embed":
        emb = _embed()
        rows = load_jsonl(ns.patterns)
        slots = json.loads((w / "slots.json").read_text(encoding="utf-8"))["slots"]
        rows = [r for r in rows if r["id"] in slots]
        ids = [r["id"] for r in rows]
        raw = emb([r["text"] for r in rows])
        concat = emb(["\n".join(slots[i][s] for s in SLOTS) for i in ids])
        per_slot = {s: emb([slots[i][s] or " " for i in ids]) for s in SLOTS}
        repeat = emb([r["text"] for r in rows[:20]])
        (w / "vectors.json").write_text(
            json.dumps(
                {
                    "ids": ids,
                    "theme": {r["id"]: r["theme"] for r in rows},
                    "raw": raw,
                    "concat": concat,
                    "per_slot": per_slot,
                    "repeat_cosine": [cosine(a, b) for a, b in zip(raw[:20], repeat, strict=True)],
                }
            ),
            encoding="utf-8",
        )
        print(f"embedded {len(ids)} rows")
    elif ns.stage == "enum":
        gen, prompt = _generate(), (HERE / "lab" / "rfc0041-enum.md").read_text(encoding="utf-8")
        out = [
            {
                "id": r["id"],
                "label": r["label"],
                "relation": ask_relation(r["candidate"], r["neighbor"], gen, prompt),
            }
            for r in load_jsonl(ns.pairs)
        ]
        (w / "enum.json").write_text(json.dumps(out), encoding="utf-8")
        print(f"enum: {len(out)} pairs")
    else:
        report: dict = {
            "floor_rule": f"gap_slot - gap_raw > {Z_RULE} SE (ADR-0090 rule; pairs share patterns, SE optimistic)"
        }
        if (w / "vectors.json").exists():
            v = json.loads((w / "vectors.json").read_text(encoding="utf-8"))
            ids, theme = v["ids"], v["theme"]
            arms = {
                "raw": dict(zip(ids, v["raw"], strict=True)),
                "concat": dict(zip(ids, v["concat"], strict=True)),
            }
            for s in SLOTS:
                arms[f"slot_{s}"] = dict(zip(ids, v["per_slot"][s], strict=True))
            sep = {name: separation(*pair_cosines(vecs, theme)) for name, vecs in arms.items()}
            rc = v["repeat_cosine"]
            report["separation"] = {
                "three_point": {"embedder_repeat_cosine_mean": sum(rc) / len(rc) if rc else None},
                "arms": sep,
                "concat_vs_raw": compare_arms(sep["raw"], sep["concat"]),
            }
        if (w / "enum.json").exists():
            e = json.loads((w / "enum.json").read_text(encoding="utf-8"))
            report["enum"] = enum_agreement((r["label"], r["relation"]) for r in e)
        if ns.out is None:
            sys.exit("ERROR: --out is required for --stage report")
        ns.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {ns.out}")


if __name__ == "__main__":
    main()
