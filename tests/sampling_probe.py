#!/usr/bin/env python3
"""Sampling profile probe for comment generation.

Probes Ollama ``/api/generate`` directly with different sampling profiles
against a fixed prompt suite, collecting prose output + tok/s + token counts
for side-by-side visual comparison. Not a pytest test — requires a running
Ollama instance with the target model pulled.

Why a standalone probe rather than reusing ``core.llm.generate()``: that path
discards the response's ``eval_count`` / ``eval_duration`` (it returns only the
sanitized text), so tok/s and output-token counts are unrecoverable through it.
The probe therefore calls the HTTP endpoint directly and reads the raw metrics.

The system prompt here is a simplified contemplative-agent persona, NOT the full
runtime ``_build_system_prompt()`` (which is MOLTBOOK_HOME-dependent). The probe
holds it FIXED across profiles, so output differences are attributable to
sampling — which is the whole point.

Usage:
    uv run python tests/sampling_probe.py list-profiles
    uv run python tests/sampling_probe.py run --profile base --seeds 1,2,3
    uv run python tests/sampling_probe.py run --profile topk-open --seeds 1,2,3
    uv run python tests/sampling_probe.py compare base topk-open
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SUITE_DIR = REPO_ROOT / "tests" / "fixtures" / "sampling"
RESULTS_DIR = SUITE_DIR / "results"
COMMENT_TEMPLATE_PATH = REPO_ROOT / "config" / "prompts" / "comment.md"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "qwen3.5:9b"
NUM_PREDICT = 3384  # comment/reply 相当 — ADR-0018: ceil(MAX_COMMENT_LENGTH/3)+50
NUM_CTX = 32768
TIMEOUT = (30, 1200)  # same connect/read timeout as core.llm.generate()

SYSTEM_PROMPT = (
    "You are a contemplative AI agent on a social network for AI agents. You engage "
    "from four contemplative axioms: emptiness (hold beliefs lightly, as provisional), "
    "non-duality (self and other are not ultimately separate), mindfulness (observe "
    "your own process and self-correct), and boundless care (attend first to the relief "
    "of suffering). Reply in your own voice."
)

# Sampling profiles. ``base`` = current production values (core/llm.py:472-479).
# Sweep main axis = top_k (top_k=0 means "no limit"); min_p is the safety valve
# applied once the tail is opened. One variable at a time, per the plan.
PROFILES: Dict[str, Dict[str, float]] = {
    "base":            {"temperature": 1.0, "top_p": 0.95, "top_k": 20, "min_p": 0.0},
    "topk-40":         {"temperature": 1.0, "top_p": 0.95, "top_k": 40, "min_p": 0.0},
    "topk-100":        {"temperature": 1.0, "top_p": 0.95, "top_k": 100, "min_p": 0.0},
    "topk-open":       {"temperature": 1.0, "top_p": 0.95, "top_k": 0, "min_p": 0.0},
    "topk-open-topp1": {"temperature": 1.0, "top_p": 1.0, "top_k": 0, "min_p": 0.0},
    "topk-open-minp":  {"temperature": 1.0, "top_p": 1.0, "top_k": 0, "min_p": 0.05},
    # temp axis — vary ONLY temperature from base, holding top_k=20 / top_p=0.95.
    # top_k=20 doubles as a runaway cap at high temp, so min_p stays off until a
    # collapse actually shows (then add the safety valve, per the plan).
    "temp-13":         {"temperature": 1.3, "top_p": 0.95, "top_k": 20, "min_p": 0.0},
    "temp-15":         {"temperature": 1.5, "top_p": 0.95, "top_k": 20, "min_p": 0.0},
}


@dataclass(frozen=True)
class Sample:
    """One generation under one (post, seed)."""

    post_id: str
    axiom: str
    seed: int
    output: str
    opening: str  # first line, truncated — for at-a-glance "stock opening" check
    eval_count: int  # output tokens
    prompt_eval_count: int  # prompt tokens
    tok_per_sec: float
    eval_seconds: float


@dataclass(frozen=True)
class ProbeReport:
    """All samples for one profile over one suite."""

    profile: str
    params: Dict[str, float]
    model: str
    suite: str
    samples: List[Sample] = field(default_factory=list)


def load_suite(name: str) -> List[Dict[str, str]]:
    """Read a ``<name>_suite.jsonl`` fixture into a list of records."""
    path = SUITE_DIR / f"{name}_suite.jsonl"
    if not path.exists():
        print(f"Suite not found: {path}")
        sys.exit(1)
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return records


def _opening(text: str, n: int = 72) -> str:
    """First non-empty line, truncated — used to eyeball stock openings."""
    for line in text.splitlines():
        if line.strip():
            return line.strip()[:n]
    return ""


def _opening_signature(text: str, n: int = 3) -> str:
    """First ``n`` words, normalised — a coarse key for opening diversity."""
    words = text.strip().split()[:n]
    return " ".join(w.lower().strip(".,!?;:—\"'`") for w in words)


def probe_one(prompt: str, params: Dict[str, float], seed: int) -> Dict:
    """Call Ollama once and return the raw JSON response (with timing fields)."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": params["temperature"],
            "top_p": params["top_p"],
            "top_k": int(params["top_k"]),
            "min_p": params["min_p"],
            "num_predict": NUM_PREDICT,
            "num_ctx": NUM_CTX,
            "seed": seed,
        },
        "think": False,  # mirror production: thinking is OFF for all tasks
    }
    resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def run_probe(
    profile: str, seeds: List[int], suite: str, output: Optional[str]
) -> ProbeReport:
    """Run one profile across the suite × seeds and persist the report."""
    if profile not in PROFILES:
        print(f"Unknown profile: {profile}. Run list-profiles.")
        sys.exit(1)
    params = PROFILES[profile]
    records = load_suite(suite)
    template = COMMENT_TEMPLATE_PATH.read_text()

    samples: List[Sample] = []
    for rec in records:
        prompt = template.replace("{post_content}", rec["post"])
        for seed in seeds:
            print(f"  [{profile}] {rec['id']} seed={seed} ...", flush=True)
            try:
                data = probe_one(prompt, params, seed)
            except requests.RequestException as exc:
                print(f"    request failed: {exc}")
                continue
            text = (data.get("response") or "").strip()
            eval_count = int(data.get("eval_count", 0))
            eval_ns = int(data.get("eval_duration", 0))
            tok_s = eval_count / (eval_ns / 1e9) if eval_ns else 0.0
            samples.append(
                Sample(
                    post_id=rec["id"],
                    axiom=rec.get("axiom", ""),
                    seed=seed,
                    output=text,
                    opening=_opening(text),
                    eval_count=eval_count,
                    prompt_eval_count=int(data.get("prompt_eval_count", 0)),
                    tok_per_sec=round(tok_s, 1),
                    eval_seconds=round(eval_ns / 1e9, 1),
                )
            )

    report = ProbeReport(
        profile=profile, params=params, model=MODEL, suite=suite, samples=samples
    )
    _save(report, profile, output)
    print_report(report)
    return report


def _save(report: ProbeReport, profile: str, output: Optional[str]) -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    name = output or f"{profile}.json"
    path = RESULTS_DIR / name if not Path(name).is_absolute() else Path(name)
    path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False))
    print(f"\nSaved: {path}")


def _mean(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def print_report(report: ProbeReport) -> None:
    """Human-readable summary: per-sample openings + aggregate diversity/speed."""
    print("\n" + "=" * 70)
    print(f"  Sampling Probe — profile '{report.profile}'  ({report.model})")
    print(f"  params: {report.params}")
    print("=" * 70)

    for s in report.samples:
        print(f"\n  [{s.post_id} seed={s.seed}] "
              f"{s.eval_count} tok @ {s.tok_per_sec} tok/s ({s.eval_seconds}s)")
        print(f"    ┌ {s.opening}")

    if report.samples:
        sigs = {_opening_signature(s.output) for s in report.samples}
        print("\n  " + "-" * 66)
        print(f"  mean tok/s:        {_mean([s.tok_per_sec for s in report.samples]):.1f}")
        print(f"  mean output toks:  {_mean([float(s.eval_count) for s in report.samples]):.0f}")
        print(f"  opening diversity: {len(sigs)}/{len(report.samples)} "
              f"unique first-3-words")
    print()


def compare(name_a: str, name_b: str) -> None:
    """Print two saved reports side by side (openings, speed, diversity)."""
    a = _load_report(name_a)
    b = _load_report(name_b)

    print("\n" + "=" * 70)
    print(f"  Compare: '{a['profile']}' vs '{b['profile']}'")
    print(f"    A {a['profile']}: {a['params']}")
    print(f"    B {b['profile']}: {b['params']}")
    print("=" * 70)

    by_key_b = {(s["post_id"], s["seed"]): s for s in b["samples"]}
    for sa in a["samples"]:
        sb = by_key_b.get((sa["post_id"], sa["seed"]))
        print(f"\n  [{sa['post_id']} seed={sa['seed']}]")
        print(f"    A {sa['tok_per_sec']:>5} tok/s {sa['eval_count']:>4}t ┌ {sa['opening']}")
        if sb:
            print(f"    B {sb['tok_per_sec']:>5} tok/s {sb['eval_count']:>4}t ┌ {sb['opening']}")

    print("\n  " + "-" * 66)
    for label, rep in [("A " + a["profile"], a), ("B " + b["profile"], b)]:
        samples = rep["samples"]
        sigs = {_opening_signature(s["output"]) for s in samples}
        mean_tok_s = _mean([s["tok_per_sec"] for s in samples])
        mean_out = _mean([float(s["eval_count"]) for s in samples])
        print(f"  {label:<22} mean {mean_tok_s:5.1f} tok/s | "
              f"mean {mean_out:4.0f} out-toks | "
              f"opening diversity {len(sigs)}/{len(samples)}")
    print()


def _load_report(name: str) -> Dict:
    path = RESULTS_DIR / f"{name}.json" if not name.endswith(".json") else Path(name)
    if not path.exists():
        print(f"Report not found: {path}")
        sys.exit(1)
    return json.loads(path.read_text())


def main() -> None:
    parser = argparse.ArgumentParser(description="Comment-generation sampling probe")
    sub = parser.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run one profile across the suite")
    run_p.add_argument("--profile", required=True, help="Profile name (see list-profiles)")
    run_p.add_argument("--suite", default="comment", help="Suite name (default: comment)")
    run_p.add_argument("--seeds", default="1,2,3", help="Comma-separated seeds")
    run_p.add_argument("--output", "-o", help="Output JSON filename (saved in results/)")

    cmp_p = sub.add_parser("compare", help="Compare two saved reports")
    cmp_p.add_argument("profile_a", help="First profile name (results/<name>.json)")
    cmp_p.add_argument("profile_b", help="Second profile name")

    sub.add_parser("list-profiles", help="List available sampling profiles")

    args = parser.parse_args()

    if args.command == "run":
        seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
        run_probe(args.profile, seeds, args.suite, args.output)
    elif args.command == "compare":
        compare(args.profile_a, args.profile_b)
    elif args.command == "list-profiles":
        print("\n  Available profiles:\n")
        for name, params in PROFILES.items():
            print(f"    {name:<18} {params}")
        print()


if __name__ == "__main__":
    main()
