#!/usr/bin/env python3
"""One-off replay: can the local model judge a WRITTEN skill against the store?

RFC-0041. The production novelty gate judges before extraction — three raw
sample lines per cluster against one-line theme descriptions — so the judge
has no artifact to compare (the ADR-0084 shape: a judge placed before the
artifact has no evidence). This script measures the other order: the candidate
skill already exists, and the model compares it with the k nearest store skills
shown in the same projection.

Read-only with respect to ``$MOLTBOOK_HOME`` (reads ``skills/*.md``; writes only
``--out``). ``llm.configure`` is never called, so no telemetry sink is wired.

Two populations, scored separately and never summed:

* ``gate``  — the candidates of one Saturday gate, with the human verdict per
  item (``--candidates``: a JSON list of ``{name, description, solution, when,
  decision}``). Reading: how many gate-rejected candidates the judge stops.
* ``loo``   — leave-one-out over the live store: each store skill is presented
  as a candidate against the remaining store. Every one of them was adopted by
  the owner, so this is the positive control. A judge that calls most of them
  ``duplicate`` is degenerate — on a saturated store "stop everything" scores
  perfectly on ``gate`` and only this population can expose it.

One projection for every skill on both sides — name, description, and the first
``_CLIP`` characters of Solution and When to Use — because the gate's rejected
candidates survive only in that projection. The verdict is a constrained enum
(``duplicate`` / ``distinct``) plus the store name it duplicates; the prompt
carries no tie-break instruction in either direction. The instruction text is
inline because this is a measurement arm; adopting the stage would move it to
``config/prompts/`` (ADR-0054).

Usage (dev-group script — run through uv, outside agent session hours)::

    uv run --no-sync python scripts/post_extraction_judge_replay.py \
        --candidates /path/to/candidates.json --k 5 --reps 2 \
        --out docs/evidence/rfc-0041/post-extraction-judge-replay-20260919.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

_CLIP = 230
_SYSTEM = (
    "You compare one candidate skill with existing skills of the same agent. "
    "You answer with a single JSON object and nothing else."
)
_PROMPT = """## Candidate skill

{candidate}

## Existing skills (the nearest ones in the store)

{store}

## Task

A skill is a behavior: what the agent does, in which situation. Decide whether the candidate is the same behavior in the same situations as one of the existing skills (`duplicate`), or a behavior none of them performs (`distinct`). Shared vocabulary is not evidence either way; compare what the agent would actually do.

Return `{{"verdict": "duplicate" | "distinct", "nearest": "<name of the closest existing skill>"}}`.
"""


def _section(text: str, heading: str) -> str:
    match = re.search(r"##\s*" + re.escape(heading) + r"\s*\n(.*?)(?=\n## |\Z)", text, re.S)
    return " ".join(match.group(1).split())[:_CLIP] if match else ""


def _load_store(skills_dir: Path) -> list[dict[str, str]]:
    store: list[dict[str, str]] = []
    for path in sorted(skills_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        name = re.search(r"^name:\s*(.+)$", text, re.M)
        description = re.search(r'^description:\s*"?(.*?)"?$', text, re.M)
        store.append(
            {
                "name": name.group(1).strip() if name else path.stem,
                "description": description.group(1) if description else "",
                "solution": _section(text, "Solution"),
                "when": _section(text, "When to Use"),
            }
        )
    return store


def _render(skill: dict[str, str]) -> str:
    return (
        f"### {skill['name']}\n{skill['description']}\n"
        f"Does: {skill['solution']}\nWhen: {skill['when']}"
    )


def _embed(skills: list[dict[str, str]]) -> np.ndarray:
    from contemplative_agent.core.embeddings import embed_texts

    vectors = embed_texts([f"{s['name']}: {s['description']}" for s in skills])
    if vectors is None:
        raise SystemExit("embedding failed — the top-k store slice is undefined")
    return vectors


def _judge(
    candidate: dict[str, str], nearest: list[dict[str, str]], temperature: float
) -> dict[str, Any]:
    from contemplative_agent.core import llm

    names = [s["name"] for s in nearest]
    schema = {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["duplicate", "distinct"]},
            "nearest": {"type": "string", "enum": names},
        },
        "required": ["verdict", "nearest"],
    }
    prompt = _PROMPT.format(
        candidate=_render(candidate), store="\n\n".join(_render(s) for s in nearest)
    )
    started = time.monotonic()
    out = llm.generate_full(
        prompt,
        system=_SYSTEM,
        num_predict=200,
        format=schema,
        temperature=temperature,
        caller="measure.post_extraction_judge",
        drop_truncated=True,
    )
    row: dict[str, Any] = {"seconds": round(time.monotonic() - started, 2)}
    if out is None or out.text is None:
        return {**row, "verdict": None, "reason": "llm_none"}
    try:
        parsed = json.loads(out.text)
    except json.JSONDecodeError:
        return {**row, "verdict": None, "reason": "unparseable"}
    if parsed.get("verdict") not in ("duplicate", "distinct"):
        return {**row, "verdict": None, "reason": "off_enum"}
    return {**row, "verdict": parsed["verdict"], "nearest": parsed.get("nearest")}


def _top_k(vector: np.ndarray, store_vectors: np.ndarray, skip: int | None, k: int) -> list[int]:
    scores = store_vectors @ vector
    order = [int(i) for i in scores.argsort()[::-1] if skip is None or int(i) != skip]
    return order[:k]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a post-extraction duplicate judge.")
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--skills-dir",
        type=Path,
        default=Path(os.environ.get("MOLTBOOK_HOME", str(Path.home() / ".config/moltbook")))
        / "skills",
    )
    args = parser.parse_args(argv)

    from contemplative_agent.core import llm

    store = _load_store(args.skills_dir)
    candidates: list[dict[str, str]] = json.loads(args.candidates.read_text(encoding="utf-8"))
    store_vectors = _embed(store)
    store_vectors = store_vectors / np.linalg.norm(store_vectors, axis=1, keepdims=True)
    cand_vectors = _embed(candidates)
    cand_vectors = cand_vectors / np.linalg.norm(cand_vectors, axis=1, keepdims=True)

    result: dict[str, Any] = {
        "model": llm._get_model(),
        "store_size": len(store),
        "k": args.k,
        "reps": args.reps,
        "temperature": args.temperature,
        "clip_chars": _CLIP,
        "prompt": _PROMPT,
        "rows": [],
    }
    jobs: list[tuple[str, dict[str, str], str, list[int]]] = []
    for index, candidate in enumerate(candidates):
        jobs.append(
            (
                "gate",
                candidate,
                candidate["decision"],
                _top_k(cand_vectors[index], store_vectors, None, args.k),
            )
        )
    for index, skill in enumerate(store):
        jobs.append(
            ("loo", skill, "adopted", _top_k(store_vectors[index], store_vectors, index, args.k))
        )

    for rep in range(args.reps):
        for population, candidate, label, nearest_ids in jobs:
            row = _judge(candidate, [store[i] for i in nearest_ids], args.temperature)
            result["rows"].append(
                {
                    "rep": rep,
                    "population": population,
                    "name": candidate["name"],
                    "label": label,
                    **row,
                }
            )
            print(
                f"  [{population}#{rep}] {candidate['name'][:48]} ({label}): "
                f"{row.get('verdict') or row.get('reason')} {row['seconds']}s",
                flush=True,
            )
        # Written after every rep: a killed run keeps what it measured.
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
