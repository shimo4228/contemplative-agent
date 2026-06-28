"""A/B: qwen3.5:9b (think OFF) vs gemma4:e4b (think OFF / ON) for comment generation.

Evidence for ADR-0068 (per-call `think` flag). Exercises the think capability and
compares model/think conditions on latency + quality. Generation only — NO Moltbook
calls, no posting. Side effect is telemetry append only. Results to stdout as JSON.

Reproduce:
    cd <repo root>
    uv run python docs/evidence/adr-0068/ab_gemma_think-20260628.py | tee results.txt

Memory safety: qwen(6.6GB) + gemma(9.6GB) > 16GB RAM, so the previous model is
explicitly `ollama stop`ped before switching to keep one model resident at a time.
Per-model warmup call is excluded from latency (cold model-load isolation).

Run results (2026-06-28, M1 16GB): see gemma-e4b-think-ab-20260628.md.
"""

import json
import os
import statistics
import subprocess
import time
from pathlib import Path

# Agent() construction configures the llm module to production settings
# (identity + axioms + skills from MOLTBOOK_HOME) via configure_llm. Read-only:
# no client/network is created on construction (self._client stays None).
from contemplative_agent.adapters.moltbook.agent import Agent, AutonomyLevel
from contemplative_agent.adapters.moltbook.llm_functions import generate_comment


def _find_repo_root() -> Path:
    """Walk up until the package fixture dir is found (robust to file location)."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "tests" / "fixtures" / "sampling" / "comment_suite.jsonl").exists():
            return parent
    raise RuntimeError("Could not locate repo root (comment_suite.jsonl not found)")


REPO = _find_repo_root()
SUITE = REPO / "tests" / "fixtures" / "sampling" / "comment_suite.jsonl"

QWEN = "qwen3.5:9b"
GEMMA = "gemma4:e4b"


def load_posts() -> list[dict]:
    posts = []
    for line in SUITE.read_text().splitlines():
        line = line.strip()
        if line:
            d = json.loads(line)
            posts.append({"id": d["id"], "axiom": d["axiom"], "post": d["post"]})
    return posts


def run(label: str, model: str, think: bool, posts: list[dict]) -> dict:
    os.environ["OLLAMA_MODEL"] = model
    # Warmup (excluded from latency): forces cold model-load now.
    print(f"[{label}] warmup ({model}, think={think}) ...", flush=True)
    _ = generate_comment(posts[0]["post"], think=think)

    rows = []
    for i, p in enumerate(posts):
        t0 = time.monotonic()
        out = generate_comment(p["post"], think=think)
        dt = time.monotonic() - t0
        rows.append(
            {
                "i": i,
                "id": p["id"],
                "axiom": p["axiom"],
                "sec": round(dt, 1),
                "text": out.text,
                "thinking": out.thinking,
            }
        )
        print(f"[{label}] {p['id']}: {dt:.1f}s", flush=True)

    secs = [r["sec"] for r in rows]
    return {
        "label": label,
        "model": model,
        "think": think,
        "median_sec": round(statistics.median(secs), 1),
        "rows": rows,
    }


def main() -> None:
    posts = load_posts()
    # Construct once: configures llm to production identity/axioms/skills.
    Agent(autonomy=AutonomyLevel.AUTO)

    results = []
    results.append(run("baseline", QWEN, False, posts))

    # Free qwen before loading gemma (avoid >16GB co-residency).
    print(f"[switch] ollama stop {QWEN}", flush=True)
    subprocess.run(["ollama", "stop", QWEN], check=False)

    results.append(run("gemma_nothink", GEMMA, False, posts))
    results.append(run("gemma_think", GEMMA, True, posts))

    print("\n===RESULTS_JSON===")
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
