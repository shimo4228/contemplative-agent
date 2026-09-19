#!/usr/bin/env python3
"""One-off replay of the insight novelty gate under three tie-break wordings.

RFC-0041. Question: the judge prompt's closing sentences tell the model to
resolve ambiguity toward NEW ("It is safer to over-report novelty ..."). In a
corpus where nearly every cluster is ambiguous, does that sentence — rather
than the evidence — set the pass rate?

Read-only with respect to ``$MOLTBOOK_HOME``. Each logged judge prompt of one
run is decoded from ``logs/insight-novelty.jsonl`` and replayed with the
production call shape (same system prompt, ``num_predict=2000``,
``drop_truncated=True``; ``llm.configure`` is never called, so no telemetry sink
is wired). ``--temperature`` defaults to 1.0, which is what production sent when
this was measured; production runs at 0 since ADR-0074's 2026-09-19 amendment.
The script replays only logs recorded with the old tie-break sentence (it stops
if the sentence is absent), i.e. runs up to 2026-09-19. One variable — the
closing tie-break:

* arm ``new``     — the logged prompt, byte for byte (production wording).
* arm ``none``    — the two tie-break sentences removed.
* arm ``covered`` — replaced by the mirror instruction (ambiguity -> covered).

Arm ``new`` is repeated like the others: its rep-to-rep disagreement is the
judge's own jitter, the floor any arm-to-arm difference has to clear. The
logged production verdict is carried as a further ``new`` sample.

Scoring joins covered cluster ids to the human verdicts of the Saturday gate
(``--labels``: cluster -> held / rejected). Two readings per arm, never summed:
how many gate-rejected candidates the arm would have stopped, and how many
gate-held candidates it would have stopped (the refutation axis — an arm that
stops most of the held ones closed the gate rather than narrowing it).

Usage (dev-group script — run through uv, outside agent session hours)::

    uv run --no-sync python scripts/novelty_tiebreak_replay.py \
        --run-id 7f0b92e8aa5345f4b9f6b481a125125d --reps 2 \
        --labels docs/evidence/rfc-0041/gate-labels-20260919.json \
        --out docs/evidence/rfc-0041/novelty-tiebreak-replay-20260919.json
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT / "src"))

_TIEBREAK_NEW = (
    " When ambiguity arises regarding whether a pattern is novel, assume it is unique "
    "and mark it as NEW. It is safer to over-report novelty than to suppress a "
    "genuinely new skill."
)
_TIEBREAK_COVERED = (
    " When ambiguity arises regarding whether a pattern is novel, assume it is already "
    "covered and list it. A genuinely new theme recurs in later windows; a duplicate "
    "skill costs more than a delayed one."
)
_ARMS: dict[str, str] = {"new": _TIEBREAK_NEW, "none": "", "covered": _TIEBREAK_COVERED}


def _load_chunks(audit_path: Path, run_id: str) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with audit_path.open(encoding="utf-8") as handle:
        for line in handle:
            if run_id not in line:
                continue
            record = json.loads(line)
            if record.get("run_id") != run_id or record.get("verdict") != "judged":
                continue
            if record.get("prompt_truncated") or record.get("output_truncated"):
                raise SystemExit(f"chunk {record.get('batch_index')}: truncated record")
            prompt = base64.b64decode(record["prompt_b64"]).decode("utf-8")
            if prompt.count(_TIEBREAK_NEW) != 1:
                raise SystemExit(
                    f"chunk {record.get('batch_index')}: tie-break sentence not found exactly once "
                    "— the prompt changed and this replay's one variable is undefined"
                )
            chunks.append(
                {
                    "index": int(record.get("batch_index") or 0),
                    "prompt": prompt,
                    "clusters": list(record.get("clusters") or []),
                    "logged_covered": sorted(record.get("covered") or []),
                }
            )
    if not chunks:
        raise SystemExit(f"no judged records for run_id {run_id!r}")
    return sorted(chunks, key=lambda c: c["index"])


def _judge(
    prompt: str, cluster_ids: set[str], temperature: float
) -> tuple[list[str] | None, str, float]:
    from contemplative_agent.core import llm
    from contemplative_agent.core.insight_novelty import _parse_covered_ids
    from contemplative_agent.core.prompts import INSIGHT_NOVELTY_SYSTEM_PROMPT

    started = time.monotonic()
    out = llm.generate_full(
        prompt,
        system=INSIGHT_NOVELTY_SYSTEM_PROMPT,
        num_predict=2000,
        temperature=temperature,
        caller="insight.novelty",
        drop_truncated=True,
    )
    seconds = round(time.monotonic() - started, 2)
    if out is None or out.text is None:
        return None, "fail_open_llm", seconds
    covered = _parse_covered_ids(out.text, cluster_ids)
    if covered is None:
        return None, "fail_open_parse", seconds
    return sorted(covered), "judged", seconds


def _score(covered: set[str], labels: dict[str, str], judged: set[str]) -> dict[str, Any]:
    rejected = {c for c, d in labels.items() if d == "rejected"}
    held = {c for c, d in labels.items() if d == "held"}
    return {
        "covered_total": len(covered),
        "judged_clusters": len(judged),
        "rejected_stopped": len(covered & rejected),
        "rejected_judged": len(rejected & judged),
        "held_stopped": sorted(covered & held),
        "held_judged": len(held & judged),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Replay the novelty gate under three tie-break wordings."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--reps", type=int, default=2)
    parser.add_argument(
        "--temperature",
        type=float,
        default=1.0,
        help="judge temperature; 1.0 is what production sent until 2026-09-19 (now 0, ADR-0074)",
    )
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--audit",
        type=Path,
        default=Path(os.environ.get("MOLTBOOK_HOME", str(Path.home() / ".config/moltbook")))
        / "logs/insight-novelty.jsonl",
    )
    args = parser.parse_args(argv)

    from contemplative_agent.core import llm

    chunks = _load_chunks(args.audit, args.run_id)
    label_doc = json.loads(args.labels.read_text(encoding="utf-8"))
    labels = {item["cluster"]: item["decision"] for item in label_doc["items"]}

    logged = {cid for c in chunks for cid in c["logged_covered"]}
    all_ids = {cid for c in chunks for cid in c["clusters"]}
    result: dict[str, Any] = {
        "run_id": args.run_id,
        "model": llm._get_model(),
        "chunks": len(chunks),
        "clusters": len(all_ids),
        "reps": args.reps,
        "temperature": args.temperature,
        "arms_text": _ARMS,
        "production_logged": _score(logged, labels, all_ids),
        "arms": {},
    }
    for label, replacement in _ARMS.items():
        reps: list[dict[str, Any]] = []
        for rep in range(args.reps):
            covered: set[str] = set()
            judged: set[str] = set()
            fail_open: list[dict[str, Any]] = []
            for chunk in chunks:
                prompt = chunk["prompt"].replace(_TIEBREAK_NEW, replacement)
                ids = set(chunk["clusters"])
                got, reason, seconds = _judge(prompt, ids, args.temperature)
                print(
                    f"  [{label}#{rep}] chunk {chunk['index']}: {reason} "
                    f"covered={len(got or ())}/{len(ids)} {seconds}s",
                    flush=True,
                )
                if got is None:
                    fail_open.append({"chunk": chunk["index"], "reason": reason})
                    continue
                covered |= set(got)
                judged |= ids
            reps.append(
                {
                    "rep": rep,
                    "covered": sorted(covered),
                    "fail_open": fail_open,
                    **_score(covered, labels, judged),
                }
            )
            # Written after every rep: a killed run keeps what it measured.
            result["arms"][label] = reps
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
