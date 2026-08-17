#!/usr/bin/env python
"""ADR-0096 offline check — re-extract 2026-07-25 candidates with the new path.

Production-unwired: reads knowledge.json / audit.jsonl, writes nothing outside
this scratchpad, never touches staging or the run marker. LLM calls go to the
same local Ollama the nightly job uses.

Question asked: with the abstain clause in insight_extraction.md and the
post-extraction worth gate on, (1) is the abstain count non-zero, and (2) do
the five candidates the owner actually adopted survive?
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path

# Repo root, derived from this file's location (docs/evidence/adr-0096/).
WORKTREE = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(WORKTREE / "src"))

HOME = Path(os.environ.get("MOLTBOOK_HOME", Path.home() / ".config" / "moltbook"))
KNOWLEDGE = HOME / "knowledge.json"
AUDIT = HOME / "logs" / "audit.jsonl"
RUN_DAY = "2026-07-25"
N_TOTAL = int(sys.argv[1]) if len(sys.argv) > 1 else 20
DEADLINE_S = 40 * 60

from contemplative_agent.core import insight  # noqa: E402
from contemplative_agent.core import prompts as prompts_mod  # noqa: E402

# Force the WORKTREE prompt texts: the loader prefers $MOLTBOOK_HOME/prompts,
# which still holds the deployed (pre-ADR-0096) copies until the Saturday gate.
EXTRACTION = (WORKTREE / "config/prompts/insight_extraction.md").read_text(encoding="utf-8")
WORTH = (WORKTREE / "config/prompts/insight_worth.md").read_text(encoding="utf-8")
insight.INSIGHT_EXTRACTION_PROMPT = EXTRACTION
prompts_mod.INSIGHT_WORTH_PROMPT = WORTH


def pid(distilled: str, text: str) -> str:
    return hashlib.sha256(f"{distilled}|{text}".encode()).hexdigest()[:12]


def load_labels() -> list[dict]:
    rows = []
    with AUDIT.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("source") == "stage-adopted" and d.get("ts", "")[:10] == RUN_DAY:
                rows.append(
                    {
                        "name": d["path"].rsplit("/", 1)[-1].replace(".md", ""),
                        "approved": d["decision"] == "approved",
                        "source_ids": tuple(d.get("source_ids") or ()),
                    }
                )
    return rows


def load_texts() -> dict[str, str]:
    raw = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    return {pid(p.get("distilled", ""), p.get("pattern", "")): p.get("pattern", "") for p in raw}


def main() -> int:
    labels = load_labels()
    texts = load_texts()
    for lab in labels:
        lab["patterns"] = [texts[i] for i in lab["source_ids"] if i in texts]

    approved = [x for x in labels if x["approved"] and x["patterns"]]
    rejected = sorted(
        (x for x in labels if not x["approved"] and x["patterns"]), key=lambda x: x["name"]
    )
    n_rej = max(0, N_TOTAL - len(approved))
    stride = max(1, len(rejected) // n_rej) if n_rej else 1
    sample = approved + rejected[::stride][:n_rej]
    print(f"labels={len(labels)} approved={len(approved)} sampled={len(sample)}", flush=True)

    started = time.time()
    results = []
    for i, cand in enumerate(sample, 1):
        if time.time() - started > DEADLINE_S:
            print(f"DEADLINE at {i - 1}/{len(sample)}", flush=True)
            break
        t0 = time.time()
        out = insight._extract_skill(cand["patterns"], topic=f"cluster-{i}")
        if isinstance(out, str):
            verdict, stage = out, "extraction"
        else:
            skill_text = out[0]
            verdict = (
                "promoted"
                if insight._worth_gate(skill_text, cand["patterns"])
                else insight.ABSTAIN_NOTHING_PROMOTABLE
            )
            stage = "gate"
        results.append({**{k: cand[k] for k in ("name", "approved")},
                        "n_patterns": len(cand["patterns"]),
                        "verdict": verdict, "stage": stage,
                        "secs": round(time.time() - t0, 1)})
        print(
            f"[{i}/{len(sample)}] {'ADOPTED' if cand['approved'] else 'rejected':8s} "
            f"{cand['name'][:46]:46s} → {verdict} ({stage}, {results[-1]['secs']}s)",
            flush=True,
        )

    n = len(results)
    abst = [r for r in results if r["verdict"] == insight.ABSTAIN_NOTHING_PROMOTABLE]
    faults = [r for r in results if r["verdict"] in insight.FAULT_ABSTAIN_REASONS]
    adopted = [r for r in results if r["approved"]]
    adopted_abst = [r for r in adopted if r["verdict"] == insight.ABSTAIN_NOTHING_PROMOTABLE]
    print("\n=== summary ===", flush=True)
    print(f"n={n}  promoted={n - len(abst) - len(faults)}  "
          f"nothing_promotable={len(abst)} ({len(abst) / n:.0%})  faults={len(faults)}")
    print(f"  in-band declines (extraction wrote the token): "
          f"{sum(1 for r in abst if r['stage'] == 'extraction')}")
    print(f"  gate declines: {sum(1 for r in abst if r['stage'] == 'gate')}")
    print(f"owner-adopted 5: n={len(adopted)} declined={len(adopted_abst)} "
          f"{[r['name'] for r in adopted_abst]}")
    print(f"elapsed={round(time.time() - started)}s")
    Path("offline_worth_check_results.json").write_text(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
